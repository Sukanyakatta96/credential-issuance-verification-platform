from .. import audit, ids
from ..db import paginate, transaction
from ..errors import conflict, not_found
from datetime import timedelta

from ..timeutil import parse_ts, to_ts, utcnow
from ..validation import like_pattern


def revoke_credential(db, credential_id, reason_code, reason_detail, actor_user_id):
    with transaction(db):
        credential = db.execute("SELECT credential_id, status, issued_at FROM credential WHERE credential_id = ?",
                                (credential_id,)).fetchone()
        if credential is None:
            raise not_found("Credential not found")
        if credential["status"] == "revoked":
            raise conflict("Credential has already been revoked", "ALREADY_REVOKED")
        seq = db.execute("SELECT COUNT(*) FROM revocation WHERE credential_id = ?", (credential_id,)).fetchone()[0] + 1
        revocation_id = ids.revocation_id(credential_id, seq)
        latest_check = db.execute("SELECT MAX(requested_at) FROM verification_request WHERE credential_id = ?",
                                  (credential_id,)).fetchone()[0]
        floor = max(t for t in (credential["issued_at"], latest_check) if t)
        now_ts = to_ts(max(utcnow(), parse_ts(floor) + timedelta(seconds=1)))
        db.execute(
            "INSERT INTO revocation (revocation_id, credential_id, seq, reason_code, reason_detail, effective_at, revoked_by) "
            "VALUES (?,?,?,?,?,?,?)", (revocation_id, credential_id, seq, reason_code, reason_detail, now_ts, actor_user_id))
        db.execute("UPDATE credential SET status = 'revoked' WHERE credential_id = ?", (credential_id,))
        audit.append_event(db, action="credential.revoked", entity_type="credential", entity_id=credential_id,
                           details={"revocation_id": revocation_id, "reason_code": reason_code},
                           actor_type="user", actor_user_id=actor_user_id, occurred_at=now_ts)
    return dict(db.execute("SELECT * FROM revocation WHERE revocation_id = ?", (revocation_id,)).fetchone())


def list_revocations(db, *, q=None, reason_code=None, page, page_size):
    where, params = ["1=1"], []
    if q:
        where.append("(r.credential_id LIKE ? ESCAPE '\\' OR l.full_name LIKE ? ESCAPE '\\')")
        params += [like_pattern(q)] * 2
    if reason_code:
        where.append("r.reason_code = ?")
        params.append(reason_code)
    sql = (
        "SELECT r.*, c.learner_id, l.full_name AS learner_name, c.rule_id, ru.title AS rule_title "
        "FROM revocation r JOIN credential c ON c.credential_id = r.credential_id "
        "JOIN learner l ON l.learner_id = c.learner_id JOIN credential_rule ru ON ru.rule_id = c.rule_id "
        f"WHERE {' AND '.join(where)}"
    )
    return paginate(db, sql, params, page, page_size, "r.effective_at DESC, r.revocation_id DESC")
