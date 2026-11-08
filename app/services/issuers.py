from .. import audit, crypto, ids
from ..db import transaction
from ..errors import conflict, not_found, unprocessable
from ..timeutil import ensure_strictly_after, to_ts, utcnow


def _actor(actor_user_id):
    return {"actor_type": "user" if actor_user_id else "system", "actor_user_id": actor_user_id}


def list_issuers(db):
    return [dict(r) for r in db.execute(
        "SELECT i.*, s.name AS successor_name, "
        "(SELECT COUNT(*) FROM credential c WHERE c.issuer_id = i.issuer_id) AS credential_count, "
        "(SELECT key_id FROM issuer_key k WHERE k.issuer_id = i.issuer_id AND k.status = 'active') AS active_key_id "
        "FROM issuer i LEFT JOIN issuer s ON s.issuer_id = i.successor_issuer_id ORDER BY i.issuer_id")]


def get_issuer(db, issuer_id):
    row = db.execute("SELECT * FROM issuer WHERE issuer_id = ?", (issuer_id,)).fetchone()
    if row is None:
        raise not_found("Issuer not found")
    issuer = dict(row)
    issuer["keys"] = [dict(r) for r in db.execute(
        "SELECT key_id, algorithm, public_key_b64, valid_from, valid_to, status FROM issuer_key "
        "WHERE issuer_id = ? ORDER BY key_id", (issuer_id,))]
    issuer["rule_assignments"] = [dict(r) for r in db.execute(
        "SELECT a.assignment_id, a.rule_id, r.title, a.effective_from, a.effective_to FROM rule_issuer_assignment a "
        "JOIN credential_rule r ON r.rule_id = a.rule_id WHERE a.issuer_id = ? ORDER BY a.effective_from DESC LIMIT 50",
        (issuer_id,))]
    issuer["credential_count"] = db.execute(
        "SELECT COUNT(*) FROM credential WHERE issuer_id = ?", (issuer_id,)).fetchone()[0]
    return issuer


def public_keys(db, issuer_id):
    issuer = db.execute("SELECT issuer_id, name, status, valid_from, valid_to, successor_issuer_id FROM issuer "
                        "WHERE issuer_id = ?", (issuer_id,)).fetchone()
    if issuer is None:
        raise not_found("Issuer not found")
    keys = [dict(r) for r in db.execute(
        "SELECT key_id, algorithm, public_key_b64, valid_from, valid_to, status FROM issuer_key "
        "WHERE issuer_id = ? ORDER BY key_id", (issuer_id,))]
    return {"issuer": dict(issuer), "keys": keys}


def _insert_key(db, cfg, issuer_id, version, valid_from):
    key_id = ids.key_id(issuer_id, version)
    db.execute(
        "INSERT INTO issuer_key (key_id, issuer_id, algorithm, public_key_b64, valid_from, valid_to, status) "
        "VALUES (?,?,'Ed25519',?,?,NULL,'active')",
        (key_id, issuer_id, crypto.derive_public_key_b64(cfg.signing_master_secret, key_id), valid_from))
    return key_id


def create_issuer(db, cfg, name, actor_user_id):
    if db.execute("SELECT 1 FROM issuer WHERE name = ? COLLATE NOCASE", (name,)).fetchone():
        raise conflict("An issuer with this name already exists", "DUPLICATE_NAME")
    now_ts = to_ts(utcnow())
    with transaction(db):
        issuer_id = ids.issuer_id(ids.next_counter(db, "issuer"))
        db.execute("INSERT INTO issuer (issuer_id, name, status, valid_from) VALUES (?,?, 'active', ?)",
                   (issuer_id, name, now_ts))
        key_id = _insert_key(db, cfg, issuer_id, 1, now_ts)
        audit.append_event(db, action="issuer.created", entity_type="issuer", entity_id=issuer_id,
                           details={"name": name, "key_id": key_id}, **_actor(actor_user_id))
    return get_issuer(db, issuer_id)


def rotate_key(db, cfg, issuer_id, actor_user_id):
    issuer = get_issuer(db, issuer_id)
    if issuer["status"] != "active":
        raise conflict("A retired issuer cannot rotate keys", "ISSUER_RETIRED")
    active = next(k for k in issuer["keys"] if k["status"] == "active")
    version = max(int(k["key_id"].rsplit("-", 1)[1]) for k in issuer["keys"]) + 1
    now_ts = ensure_strictly_after(utcnow(), active["valid_from"], "Key rotation")
    with transaction(db):
        db.execute("UPDATE issuer_key SET status = 'rotated', valid_to = ? WHERE key_id = ?", (now_ts, active["key_id"]))
        new_key = _insert_key(db, cfg, issuer_id, version, now_ts)
        audit.append_event(db, action="issuer_key.rotated", entity_type="issuer", entity_id=issuer_id,
                           details={"retired_key": active["key_id"], "new_key": new_key}, **_actor(actor_user_id))
    return get_issuer(db, issuer_id)


def retire_issuer(db, issuer_id, successor_id, actor_user_id):
    issuer = get_issuer(db, issuer_id)
    if issuer["status"] == "retired":
        raise conflict("Issuer is already retired", "ISSUER_RETIRED")
    if successor_id == issuer_id:
        raise unprocessable("An issuer cannot succeed itself", "INVALID_SUCCESSOR")
    successor = db.execute("SELECT status FROM issuer WHERE issuer_id = ?", (successor_id,)).fetchone()
    if successor is None or successor["status"] != "active":
        raise unprocessable("Successor must be an existing active issuer", "INVALID_SUCCESSOR")

    open_assignments = db.execute(
        "SELECT assignment_id, rule_id, effective_from FROM rule_issuer_assignment "
        "WHERE issuer_id = ? AND effective_to IS NULL", (issuer_id,)).fetchall()
    floor = max([issuer["valid_from"]] + [a["effective_from"] for a in open_assignments]
                + [k["valid_from"] for k in issuer["keys"]])
    now_ts = ensure_strictly_after(utcnow(), floor, "Issuer retirement")
    with transaction(db):
        db.execute("UPDATE issuer SET status = 'retired', valid_to = ?, successor_issuer_id = ? WHERE issuer_id = ?",
                   (now_ts, successor_id, issuer_id))
        db.execute("UPDATE issuer_key SET status = 'rotated', valid_to = ? WHERE issuer_id = ? AND status = 'active'",
                   (now_ts, issuer_id))
        for a in open_assignments:
            db.execute("UPDATE rule_issuer_assignment SET effective_to = ? WHERE assignment_id = ?",
                       (now_ts, a["assignment_id"]))
            db.execute(
                "INSERT INTO rule_issuer_assignment (assignment_id, rule_id, issuer_id, effective_from, effective_to) "
                "VALUES (?,?,?,?,NULL)",
                (ids.assignment_id(ids.next_counter(db, "assignment")), a["rule_id"], successor_id, now_ts))
        audit.append_event(db, action="issuer.retired", entity_type="issuer", entity_id=issuer_id,
                           details={"successor": successor_id, "rules_transferred": len(open_assignments)},
                           **_actor(actor_user_id))
    return get_issuer(db, issuer_id)
