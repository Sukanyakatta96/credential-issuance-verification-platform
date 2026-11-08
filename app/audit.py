import hashlib
import json

from . import ids
from .timeutil import to_ts, utcnow

GENESIS_HASH = "0" * 64


def compute_event_hash(prev_hash: str, seq: int, event_id: str, occurred_at: str, actor_type: str,
                       actor_user_id: str | None, action: str, entity_type: str, entity_id: str,
                       details_json: str) -> str:
    material = "|".join([
        prev_hash, str(seq), event_id, occurred_at, actor_type, actor_user_id or "",
        action, entity_type, entity_id, details_json,
    ])
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def dumps_details(details: dict) -> str:
    return json.dumps(details, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def append_event(db, *, action: str, entity_type: str, entity_id: str, details: dict | None = None,
                 actor_type: str = "system", actor_user_id: str | None = None, occurred_at: str | None = None) -> str:
    last = db.execute("SELECT seq, event_hash FROM audit_event ORDER BY seq DESC LIMIT 1").fetchone()
    seq = (last["seq"] if last else 0) + 1
    prev_hash = last["event_hash"] if last else GENESIS_HASH
    event_id = ids.audit_event_id(seq)
    occurred_at = occurred_at or to_ts(utcnow())
    details_json = dumps_details(details or {})
    event_hash = compute_event_hash(prev_hash, seq, event_id, occurred_at, actor_type, actor_user_id,
                                    action, entity_type, entity_id, details_json)
    db.execute(
        "INSERT INTO audit_event (event_id, seq, occurred_at, actor_type, actor_user_id, action, entity_type, "
        "entity_id, details_json, prev_hash, event_hash) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (event_id, seq, occurred_at, actor_type, actor_user_id, action, entity_type, entity_id,
         details_json, prev_hash, event_hash),
    )
    return event_id


def verify_chain(db) -> dict:
    expected_prev = GENESIS_HASH
    expected_seq = 1
    checked = 0
    for row in db.execute(
        "SELECT seq, event_id, occurred_at, actor_type, actor_user_id, action, entity_type, entity_id, "
        "details_json, prev_hash, event_hash FROM audit_event ORDER BY seq"
    ):
        problem = None
        if row["seq"] != expected_seq:
            problem = f"sequence gap: expected {expected_seq}, found {row['seq']}"
        elif row["prev_hash"] != expected_prev:
            problem = "prev_hash does not match previous event_hash"
        else:
            recomputed = compute_event_hash(
                row["prev_hash"], row["seq"], row["event_id"], row["occurred_at"], row["actor_type"],
                row["actor_user_id"], row["action"], row["entity_type"], row["entity_id"], row["details_json"],
            )
            if recomputed != row["event_hash"]:
                problem = "event_hash does not match event content"
        if problem:
            return {"valid": False, "events_checked": checked, "first_broken_event": row["event_id"], "problem": problem}
        expected_prev = row["event_hash"]
        expected_seq += 1
        checked += 1
    return {"valid": True, "events_checked": checked, "first_broken_event": None, "problem": None}
