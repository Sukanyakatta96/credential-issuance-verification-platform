from .. import audit, crypto, ids
from ..db import paginate, transaction
from ..domain.eligibility import evaluate_eligibility
from ..domain.payload import build_payload
from ..errors import ApiError, conflict, not_found, unprocessable
from ..timeutil import add_months, to_ts, utcnow
from ..validation import like_pattern

BLOCKING_REVOCATION_REASONS = ("fraud", "academic_misconduct")


def _rule_row(db, rule_id):
    row = db.execute("SELECT * FROM credential_rule WHERE rule_id = ?", (rule_id,)).fetchone()
    if row is None:
        raise not_found("Credential rule not found")
    return dict(row)


def evaluate(db, learner_id, rule_id, as_of=None):
    learner = db.execute("SELECT learner_id, full_name, status FROM learner WHERE learner_id = ?", (learner_id,)).fetchone()
    if learner is None:
        raise not_found("Learner not found")
    rule = _rule_row(db, rule_id)
    as_of = as_of or to_ts(utcnow())
    rule_courses = [dict(r) for r in db.execute(
        "SELECT course_id, is_mandatory FROM credential_rule_course WHERE rule_id = ?", (rule_id,))]
    completions = {r["course_id"]: dict(r) for r in db.execute(
        "SELECT cr.completion_id, cr.course_id, cr.status, cr.final_score, cr.finalized_at FROM completion_record cr "
        "JOIN credential_rule_course rc ON rc.course_id = cr.course_id AND rc.rule_id = ? WHERE cr.learner_id = ?",
        (rule_id, learner_id))}
    has_active = db.execute(
        "SELECT 1 FROM credential WHERE learner_id = ? AND rule_id = ? AND status = 'active'",
        (learner_id, rule_id)).fetchone() is not None
    placeholders = ",".join("?" * len(BLOCKING_REVOCATION_REASONS))
    blocked = db.execute(
        "SELECT 1 FROM credential c JOIN revocation r ON r.credential_id = c.credential_id "
        f"WHERE c.learner_id = ? AND c.rule_id = ? AND r.reason_code IN ({placeholders})",
        (learner_id, rule_id, *BLOCKING_REVOCATION_REASONS)).fetchone() is not None
    result = evaluate_eligibility(rule=rule, rule_courses=rule_courses, completions_by_course=completions,
                                  learner_status=learner["status"], has_active_credential=has_active,
                                  has_blocking_revocation=blocked, as_of=as_of)
    result.update({"learner_id": learner_id, "learner_name": learner["full_name"], "rule_id": rule_id,
                   "rule_title": rule["title"], "evaluated_as_of": as_of})
    return result


def pending_queue(db, *, rule_id=None, q=None, page=1, page_size=25):
    now_ts = to_ts(utcnow())
    rules_sql = ("SELECT * FROM credential_rule WHERE status = 'active' AND effective_from <= ? "
                 "AND (effective_to IS NULL OR ? < effective_to)")
    params: list = [now_ts, now_ts]
    if rule_id:
        rules_sql += " AND rule_id = ?"
        params.append(rule_id)
    entries = []
    for rule in db.execute(rules_sql, params).fetchall():
        rule = dict(rule)
        rule_courses = [dict(r) for r in db.execute(
            "SELECT course_id, is_mandatory FROM credential_rule_course WHERE rule_id = ?", (rule["rule_id"],))]
        blocked = {r[0] for r in db.execute(
            "SELECT c.learner_id FROM credential c JOIN revocation r ON r.credential_id = c.credential_id "
            "WHERE c.rule_id = ? AND r.reason_code IN ('fraud','academic_misconduct')", (rule["rule_id"],))}
        grouped: dict[str, dict] = {}
        for row in db.execute(
            "SELECT cr.learner_id, cr.completion_id, cr.course_id, cr.status, cr.final_score, cr.finalized_at, l.full_name "
            "FROM completion_record cr "
            "JOIN credential_rule_course rc ON rc.course_id = cr.course_id AND rc.rule_id = ? "
            "JOIN learner l ON l.learner_id = cr.learner_id AND l.status = 'active' "
            "WHERE cr.status = 'completed' AND cr.final_score >= ? "
            "AND NOT EXISTS (SELECT 1 FROM credential c WHERE c.learner_id = cr.learner_id AND c.rule_id = ? "
            "AND c.status = 'active')", (rule["rule_id"], rule["min_course_score"], rule["rule_id"])):
            entry = grouped.setdefault(row["learner_id"], {"name": row["full_name"], "completions": {}})
            entry["completions"][row["course_id"]] = dict(row)
        for learner_id, info in grouped.items():
            if len(info["completions"]) < rule["min_courses_required"]:
                continue
            result = evaluate_eligibility(
                rule=rule, rule_courses=rule_courses, completions_by_course=info["completions"],
                learner_status="active", has_active_credential=False,
                has_blocking_revocation=learner_id in blocked, as_of=now_ts)
            if result["eligible"]:
                entries.append({"learner_id": learner_id, "learner_name": info["name"], "rule_id": rule["rule_id"],
                                "rule_title": rule["title"], "average_score": result["average_score"],
                                "latest_completion_at": result["latest_completion_at"]})
    if q:
        needle = q.casefold()
        entries = [e for e in entries if needle in e["learner_name"].casefold() or needle in e["learner_id"].casefold()
                   or needle in e["rule_title"].casefold()]
    entries.sort(key=lambda e: (e["latest_completion_at"] or "", e["learner_id"], e["rule_id"]))
    total = len(entries)
    start = (page - 1) * page_size
    return {"items": entries[start:start + page_size], "page": page, "page_size": page_size, "total": total}


def effective_issuer_and_key(db, rule_id, at_ts):
    issuer = db.execute(
        "SELECT i.* FROM rule_issuer_assignment a JOIN issuer i ON i.issuer_id = a.issuer_id "
        "WHERE a.rule_id = ? AND a.effective_from <= ? AND (a.effective_to IS NULL OR ? < a.effective_to)",
        (rule_id, at_ts, at_ts)).fetchone()
    if issuer is None or issuer["status"] != "active":
        raise conflict("No active issuer is assigned to this rule", "NO_ACTIVE_ISSUER")
    key = db.execute(
        "SELECT * FROM issuer_key WHERE issuer_id = ? AND status = 'active' AND valid_from <= ? "
        "AND (valid_to IS NULL OR ? < valid_to)", (issuer["issuer_id"], at_ts, at_ts)).fetchone()
    if key is None:
        raise conflict("The assigned issuer has no active signing key", "NO_ACTIVE_KEY")
    return dict(issuer), dict(key)


def issue_credential(db, cfg, learner_id, rule_id, actor_user_id):
    with transaction(db):
        now = utcnow()
        now_ts = to_ts(now)
        result = evaluate(db, learner_id, rule_id, as_of=now_ts)
        if not result["eligible"]:
            failed = [c for c in result["checks"] if not c["passed"]]
            raise unprocessable("Issuance requirements are not met: " + "; ".join(c["label"] for c in failed),
                                "NOT_ELIGIBLE", {"checks": result["checks"]})
        rule = _rule_row(db, rule_id)
        issuer, key = effective_issuer_and_key(db, rule_id, now_ts)
        if crypto.derive_public_key_b64(cfg.signing_master_secret, key["key_id"]) != key["public_key_b64"]:
            raise ApiError(500, "SIGNING_KEY_MISMATCH",
                           "SIGNING_MASTER_SECRET does not match the issuer's registered public key")
        number = ids.next_counter(db, "credential", now.year)
        credential_id = ids.credential_id(now.year, number)
        expires_at = to_ts(add_months(now, rule["validity_months"])) if rule["validity_months"] else None
        payload = build_payload(credential_id=credential_id, learner_id=learner_id, rule=rule,
                                issuer_id=issuer["issuer_id"], key_id=key["key_id"], issued_at=now_ts,
                                expires_at=expires_at, completion_ids=result["qualifying_completion_ids"])
        payload_json = crypto.canonical_json(payload)
        digest = crypto.payload_hash(payload_json)
        signature = crypto.sign_hash(cfg.signing_master_secret, key["key_id"], digest)
        db.execute(
            "INSERT INTO credential (credential_id, learner_id, rule_id, issuer_id, key_id, issued_at, expires_at, status, "
            "payload_json, payload_hash, signature_b64, issued_by) VALUES (?,?,?,?,?,?,?,'active',?,?,?,?)",
            (credential_id, learner_id, rule_id, issuer["issuer_id"], key["key_id"], now_ts, expires_at,
             payload_json, digest, signature, actor_user_id))
        db.executemany("INSERT INTO credential_completion (credential_id, completion_id) VALUES (?,?)",
                       [(credential_id, c) for c in result["qualifying_completion_ids"]])
        audit.append_event(
            db, action="credential.issued", entity_type="credential", entity_id=credential_id,
            details={"learner_id": learner_id, "rule_id": rule_id, "issuer_id": issuer["issuer_id"],
                     "payload_hash": digest, "average_score": result["average_score"]},
            actor_type="user" if actor_user_id else "system", actor_user_id=actor_user_id, occurred_at=now_ts)
    return get_credential(db, credential_id)


def list_credentials(db, *, q=None, status=None, rule_id=None, issuer_id=None, learner_id=None, page, page_size):
    where, params = ["1=1"], []
    if q:
        where.append("(c.credential_id LIKE ? ESCAPE '\\' OR l.full_name LIKE ? ESCAPE '\\' OR l.learner_id LIKE ? ESCAPE '\\')")
        params += [like_pattern(q)] * 3
    for column, value in (("c.rule_id", rule_id), ("c.issuer_id", issuer_id), ("c.learner_id", learner_id)):
        if value:
            where.append(f"{column} = ?")
            params.append(value)
    now_ts = to_ts(utcnow())
    if status == "active":
        where.append("c.status = 'active' AND (c.expires_at IS NULL OR c.expires_at > ?)")
        params.append(now_ts)
    elif status == "expired":
        where.append("c.status = 'active' AND c.expires_at IS NOT NULL AND c.expires_at <= ?")
        params.append(now_ts)
    elif status == "revoked":
        where.append("c.status = 'revoked'")
    sql = (
        "SELECT c.credential_id, c.learner_id, l.full_name AS learner_name, c.rule_id, r.title AS rule_title, "
        "c.issuer_id, i.name AS issuer_name, c.issued_at, c.expires_at, c.status "
        "FROM credential c JOIN learner l ON l.learner_id = c.learner_id JOIN credential_rule r ON r.rule_id = c.rule_id "
        f"JOIN issuer i ON i.issuer_id = c.issuer_id WHERE {' AND '.join(where)}"
    )
    result = paginate(db, sql, params, page, page_size, "c.issued_at DESC, c.credential_id DESC")
    for item in result["items"]:
        item["effective_status"] = _effective_status(item, now_ts)
    return result


def _effective_status(credential, now_ts):
    if credential["status"] == "revoked":
        return "revoked"
    if credential["expires_at"] and credential["expires_at"] <= now_ts:
        return "expired"
    return "active"


def get_credential(db, credential_id):
    row = db.execute(
        "SELECT c.*, l.full_name AS learner_name, r.title AS rule_title, i.name AS issuer_name, i.status AS issuer_status "
        "FROM credential c JOIN learner l ON l.learner_id = c.learner_id JOIN credential_rule r ON r.rule_id = c.rule_id "
        "JOIN issuer i ON i.issuer_id = c.issuer_id WHERE c.credential_id = ?", (credential_id,)).fetchone()
    if row is None:
        raise not_found("Credential not found")
    credential = dict(row)
    credential["effective_status"] = _effective_status(credential, to_ts(utcnow()))
    credential["completions"] = [dict(r) for r in db.execute(
        "SELECT cr.completion_id, cr.course_id, c.title AS course_title, cr.final_score, cr.finalized_at "
        "FROM credential_completion cc JOIN completion_record cr ON cr.completion_id = cc.completion_id "
        "JOIN course c ON c.course_id = cr.course_id WHERE cc.credential_id = ? ORDER BY cr.course_id", (credential_id,))]
    credential["revocations"] = [dict(r) for r in db.execute(
        "SELECT revocation_id, seq, reason_code, reason_detail, effective_at, revoked_by FROM revocation "
        "WHERE credential_id = ? ORDER BY seq", (credential_id,))]
    credential["verification_count"] = db.execute(
        "SELECT COUNT(*) FROM verification_request WHERE credential_id = ?", (credential_id,)).fetchone()[0]
    credential["audit_trail"] = [dict(r) for r in db.execute(
        "SELECT event_id, occurred_at, action, actor_type, actor_user_id FROM audit_event "
        "WHERE entity_type = 'credential' AND entity_id = ? ORDER BY seq", (credential_id,))]
    return credential
