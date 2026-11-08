import csv
import io

from ..timeutil import to_ts, utcnow
from . import issuance


def _rows(db, sql, params=()):
    return [dict(r) for r in db.execute(sql, params)]


def dashboard(db):
    now_ts = to_ts(utcnow())
    one = lambda sql, p=(): db.execute(sql, p).fetchone()[0]
    total_credentials = one("SELECT COUNT(*) FROM credential")
    revoked = one("SELECT COUNT(*) FROM credential WHERE status = 'revoked'")
    expired = one("SELECT COUNT(*) FROM credential WHERE status = 'active' AND expires_at IS NOT NULL AND expires_at <= ?", (now_ts,))
    verification_total = one("SELECT COUNT(*) FROM verification_request")
    valid_verifications = one("SELECT COUNT(*) FROM verification_request WHERE result_status = 'valid'")
    mean_days = one(
        "SELECT AVG(julianday(c.issued_at) - julianday(m.last_completion)) FROM credential c "
        "JOIN (SELECT cc.credential_id, MAX(cr.finalized_at) AS last_completion FROM credential_completion cc "
        "      JOIN completion_record cr ON cr.completion_id = cc.completion_id GROUP BY cc.credential_id) m "
        "ON m.credential_id = c.credential_id")
    pending = issuance.pending_queue(db, page=1, page_size=1)["total"]
    eligible_total = total_credentials + pending
    return {
        "generated_at": now_ts,
        "kpis": {
            "learners": one("SELECT COUNT(*) FROM learner"),
            "courses": one("SELECT COUNT(*) FROM course"),
            "credentials_total": total_credentials,
            "credentials_active": total_credentials - revoked - expired,
            "credentials_revoked": revoked,
            "credentials_expired": expired,
            "revocation_rate_pct": round(100 * revoked / total_credentials, 2) if total_credentials else 0,
            "verifications_total": verification_total,
            "verification_valid_rate_pct": round(100 * valid_verifications / verification_total, 2) if verification_total else 0,
            "pending_issuance": pending,
            "issuance_coverage_pct": round(100 * total_credentials / eligible_total, 2) if eligible_total else 0,
            "mean_days_completion_to_issuance": round(mean_days, 2) if mean_days is not None else None,
        },
        "credentials_by_month": _rows(db, "SELECT substr(issued_at,1,7) AS month, COUNT(*) AS count FROM credential GROUP BY month ORDER BY month"),
        "verifications_by_month": _rows(db, "SELECT substr(requested_at,1,7) AS month, COUNT(*) AS count FROM verification_request GROUP BY month ORDER BY month"),
        "verification_outcomes": _rows(db, "SELECT result_status AS label, COUNT(*) AS count FROM verification_request GROUP BY result_status ORDER BY count DESC"),
        "identity_outcomes": _rows(db, "SELECT identity_status AS label, COUNT(*) AS count FROM verification_request GROUP BY identity_status ORDER BY count DESC"),
        "revocation_reasons": _rows(db, "SELECT reason_code AS label, COUNT(*) AS count FROM revocation GROUP BY reason_code ORDER BY count DESC"),
        "issuer_breakdown": _rows(db, "SELECT i.name AS label, COUNT(*) AS count FROM credential c JOIN issuer i ON i.issuer_id = c.issuer_id GROUP BY i.issuer_id ORDER BY count DESC"),
        "completion_funnel": _rows(db, "SELECT status AS label, COUNT(*) AS count FROM completion_record GROUP BY status ORDER BY count DESC"),
        "top_rules": _rows(db, "SELECT r.title AS label, COUNT(*) AS count FROM credential c JOIN credential_rule r ON r.rule_id = c.rule_id GROUP BY r.rule_id ORDER BY count DESC LIMIT 8"),
    }


def learner_summary(db, learner_id):
    now_ts = to_ts(utcnow())
    return {
        "credentials": _rows(db,
            "SELECT c.credential_id, r.title AS rule_title, c.issued_at, c.expires_at, c.status, i.name AS issuer_name "
            "FROM credential c JOIN credential_rule r ON r.rule_id = c.rule_id JOIN issuer i ON i.issuer_id = c.issuer_id "
            "WHERE c.learner_id = ? ORDER BY c.issued_at DESC", (learner_id,)),
        "completion_breakdown": _rows(db, "SELECT status AS label, COUNT(*) AS count FROM completion_record WHERE learner_id = ? GROUP BY status", (learner_id,)),
        "now": now_ts,
    }


def instructor_summary(db, instructor_id):
    return {
        "courses": _rows(db,
            "SELECT c.course_id, c.title, c.status, COUNT(r.completion_id) AS enrollments, "
            "SUM(r.status = 'completed') AS completed, SUM(r.status = 'failed') AS failed, "
            "SUM(r.status IN ('enrolled','in_progress')) AS in_progress, ROUND(AVG(r.final_score), 1) AS average_score "
            "FROM course c LEFT JOIN completion_record r ON r.course_id = c.course_id "
            "WHERE c.instructor_id = ? GROUP BY c.course_id ORDER BY c.course_id", (instructor_id,)),
    }


EXPORTS = {
    "credentials": ("SELECT credential_id, learner_id, rule_id, issuer_id, key_id, issued_at, expires_at, status, payload_hash FROM credential ORDER BY credential_id", ()),
    "verifications": ("SELECT verification_id, presented_credential_id, credential_id, requested_at, channel, requester_type, requester_org, result_status, identity_status, integrity_ok FROM verification_request ORDER BY verification_id", ()),
    "revocations": ("SELECT revocation_id, credential_id, seq, reason_code, effective_at, revoked_by FROM revocation ORDER BY revocation_id", ()),
}


def _spreadsheet_safe(value):
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + value
    return value


def export_csv(db, name):
    if name == "pending_issuance":
        rows = issuance.pending_queue(db, page=1, page_size=10_000_000)["items"]
        headers = ["learner_id", "learner_name", "rule_id", "rule_title", "average_score", "latest_completion_at"]
    elif name in EXPORTS:
        sql, params = EXPORTS[name]
        cursor = db.execute(sql, params)
        headers = [d[0] for d in cursor.description]
        rows = [dict(r) for r in cursor]
    else:
        return None
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=headers)
    writer.writeheader()
    writer.writerows([{k: _spreadsheet_safe(v) for k, v in row.items()} for row in rows])
    return buffer.getvalue()
