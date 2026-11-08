from .. import audit, ids
from ..db import paginate, transaction
from ..domain.verification import evaluate_verification
from ..errors import not_found
from ..timeutil import to_ts, utcnow
from ..validation import like_pattern


def load_snapshot(db, credential_id):
    row = db.execute("SELECT * FROM credential WHERE credential_id = ?", (credential_id,)).fetchone()
    if row is None:
        return None
    credential = dict(row)
    key = db.execute("SELECT public_key_b64 FROM issuer_key WHERE key_id = ?", (credential["key_id"],)).fetchone()
    learner = db.execute("SELECT learner_id, full_name, email, date_of_birth FROM learner WHERE learner_id = ?",
                         (credential["learner_id"],)).fetchone()
    earliest = db.execute("SELECT MIN(effective_at) FROM revocation WHERE credential_id = ?",
                          (credential_id,)).fetchone()[0]
    issuer = db.execute("SELECT issuer_id, name, status, valid_to, successor_issuer_id FROM issuer WHERE issuer_id = ?",
                        (credential["issuer_id"],)).fetchone()
    title = db.execute("SELECT title FROM credential_rule WHERE rule_id = ?", (credential["rule_id"],)).fetchone()
    return {"credential": credential, "public_key_b64": key["public_key_b64"] if key else None,
            "learner": dict(learner) if learner else None, "earliest_revocation": earliest,
            "issuer": dict(issuer) if issuer else None, "rule_title": title["title"] if title else None}


def _evaluate(snapshot, as_of, presented_hash, claimed_name, claimed_email, claimed_dob):
    return evaluate_verification(
        credential=snapshot["credential"] if snapshot else None,
        public_key_b64=snapshot["public_key_b64"] if snapshot else None,
        learner=snapshot["learner"] if snapshot else None,
        earliest_effective_revocation=snapshot["earliest_revocation"] if snapshot else None,
        as_of=as_of, presented_hash=presented_hash, claimed_name=claimed_name,
        claimed_email=claimed_email, claimed_dob=claimed_dob)


def mask_name(full_name: str) -> str:
    return " ".join(part[0] + "***" for part in full_name.split())


def verify(db, *, presented_credential_id, presented_hash=None, claimed_name=None, claimed_email=None,
           claimed_dob=None, channel, requester_type, requester_org=None, processed_by=None):
    with transaction(db):
        now_ts = to_ts(utcnow())
        snapshot = load_snapshot(db, presented_credential_id)
        if snapshot and snapshot["earliest_revocation"] and now_ts < snapshot["earliest_revocation"]:
            now_ts = snapshot["earliest_revocation"]
        outcome = _evaluate(snapshot, now_ts, presented_hash, claimed_name, claimed_email, claimed_dob)
        year = int(now_ts[:4])
        verification_id = ids.verification_id(year, ids.next_counter(db, "verification", year))
        credential_id = snapshot["credential"]["credential_id"] if snapshot and outcome["result_status"] != "not_found" else None
        db.execute(
            "INSERT INTO verification_request (verification_id, presented_credential_id, credential_id, requested_at, channel, "
            "requester_type, requester_org, presented_hash, claimed_name, claimed_email, claimed_dob, result_status, "
            "identity_status, integrity_ok, processed_by) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (verification_id, presented_credential_id, credential_id, now_ts, channel, requester_type, requester_org,
             presented_hash or None, claimed_name or None, (claimed_email or None), claimed_dob or None,
             outcome["result_status"], outcome["identity_status"],
             None if outcome["integrity_ok"] is None else int(outcome["integrity_ok"]), processed_by))
        audit.append_event(
            db, action="verification.performed", entity_type="verification_request", entity_id=verification_id,
            details={"credential_id": credential_id, "result_status": outcome["result_status"],
                     "identity_status": outcome["identity_status"], "channel": channel},
            actor_type="user" if processed_by else "public", actor_user_id=processed_by, occurred_at=now_ts)
    return build_response(verification_id, now_ts, snapshot, outcome, full_detail=processed_by is not None)


def build_response(verification_id, requested_at, snapshot, outcome, full_detail):
    credential_view = None
    if snapshot and outcome["result_status"] != "not_found":
        c = snapshot["credential"]
        reveal = full_detail or outcome["identity_status"] == "matched"
        holder = snapshot["learner"]["full_name"] if reveal else mask_name(snapshot["learner"]["full_name"])
        issuer = snapshot["issuer"]
        credential_view = {
            "credential_id": c["credential_id"], "title": snapshot["rule_title"], "holder_name": holder,
            "holder_name_masked": not reveal, "issuer_id": c["issuer_id"], "issuer_name": issuer["name"],
            "issuer_status": issuer["status"], "issued_at": c["issued_at"], "expires_at": c["expires_at"],
            "key_id": c["key_id"], "payload_hash": c["payload_hash"],
        }
    notes = []
    if credential_view and credential_view["issuer_status"] == "retired":
        notes.append("The issuing organisation has since been retired; the credential remains verifiable "
                     "against the issuer's published key.")
    return {"verification_id": verification_id, "requested_at": requested_at,
            "result_status": outcome["result_status"], "identity_status": outcome["identity_status"],
            "integrity_ok": outcome["integrity_ok"], "reasons": outcome["reasons"], "notes": notes,
            "credential": credential_view}


def list_verifications(db, *, q=None, result_status=None, channel=None, credential_id=None, holder_learner_id=None,
                       page, page_size):
    where, params = ["1=1"], []
    if q:
        where.append("(v.verification_id LIKE ? ESCAPE '\\' OR v.presented_credential_id LIKE ? ESCAPE '\\' "
                     "OR v.requester_org LIKE ? ESCAPE '\\')")
        params += [like_pattern(q)] * 3
    for column, value in (("v.result_status", result_status), ("v.channel", channel), ("v.credential_id", credential_id)):
        if value:
            where.append(f"{column} = ?")
            params.append(value)
    if holder_learner_id:
        where.append("v.credential_id IN (SELECT credential_id FROM credential WHERE learner_id = ?)")
        params.append(holder_learner_id)
    sql = f"SELECT v.* FROM verification_request v WHERE {' AND '.join(where)}"
    return paginate(db, sql, params, page, page_size, "v.requested_at DESC, v.verification_id DESC")


def get_verification(db, verification_id):
    row = db.execute("SELECT * FROM verification_request WHERE verification_id = ?", (verification_id,)).fetchone()
    if row is None:
        raise not_found("Verification request not found")
    return dict(row)


def replay(db, verification_id):
    record = get_verification(db, verification_id)
    snapshot = load_snapshot(db, record["presented_credential_id"])
    outcome = _evaluate(snapshot, record["requested_at"], record["presented_hash"], record["claimed_name"],
                        record["claimed_email"], record["claimed_dob"])
    recorded = {"result_status": record["result_status"], "identity_status": record["identity_status"],
                "integrity_ok": record["integrity_ok"]}
    replayed = {"result_status": outcome["result_status"], "identity_status": outcome["identity_status"],
                "integrity_ok": None if outcome["integrity_ok"] is None else int(outcome["integrity_ok"])}
    differences = [f"{k}: recorded {recorded[k]!r}, replayed {replayed[k]!r}" for k in recorded if recorded[k] != replayed[k]]
    return {"verification_id": verification_id, "evaluated_as_of": record["requested_at"], "recorded": recorded,
            "replayed": replayed, "reasons": outcome["reasons"], "reproducible": not differences,
            "differences": differences}
