from flask import Blueprint, jsonify

from .. import security
from ..db import get_db
from ..errors import not_found
from ..ids import CREDENTIAL_RE
from ..services import issuers, verification
from ..validation import parse_body

bp = Blueprint("public", __name__)

VERIFY_SCHEMA = {
    "credential_id": {"type": "str", "required": True, "max_len": 40, "pattern": CREDENTIAL_RE.pattern,
                      "pattern_message": "must look like CRD-2026-000001"},
    "presented_hash": {"type": "str", "max_len": 64, "pattern": r"^[0-9a-fA-F]{64}$",
                       "pattern_message": "must be a 64-character hexadecimal SHA-256 hash"},
    "claimed_name": {"type": "str", "max_len": 120},
    "claimed_email": {"type": "email"},
    "claimed_dob": {"type": "date"},
    "requester_type": {"type": "str", "choices": ["employer", "institution", "learner", "other"], "default": "other"},
    "requester_org": {"type": "str", "max_len": 120},
}


@bp.get("/health")
def health():
    get_db().execute("SELECT 1").fetchone()
    return jsonify({"status": "ok"})


@bp.post("/public/verify")
def public_verify():
    security.enforce_public_rate_limit()
    data = parse_body(VERIFY_SCHEMA)
    result = verification.verify(
        get_db(), presented_credential_id=data["credential_id"], presented_hash=data["presented_hash"],
        claimed_name=data["claimed_name"], claimed_email=data["claimed_email"], claimed_dob=data["claimed_dob"],
        channel="public_api", requester_type=data["requester_type"] or "other", requester_org=data["requester_org"])
    return jsonify(result), 200


@bp.get("/public/issuers/<issuer_id>/keys")
def issuer_public_keys(issuer_id):
    return jsonify(issuers.public_keys(get_db(), issuer_id))


@bp.get("/public/credentials/<credential_id>/document")
def credential_document(credential_id):
    row = get_db().execute(
        "SELECT credential_id, key_id, payload_json, payload_hash, signature_b64 FROM credential WHERE credential_id = ?",
        (credential_id,)).fetchone()
    if row is None:
        raise not_found("Credential not found")
    return jsonify({"credential_id": row["credential_id"], "algorithm": "Ed25519", "key_id": row["key_id"],
                    "payload_json": row["payload_json"], "payload_hash": row["payload_hash"],
                    "signature_b64": row["signature_b64"],
                    "how_to_verify": "Fetch the issuer public key listed for key_id, confirm sha256(payload_json) equals "
                                     "payload_hash, then verify signature_b64 over the ASCII hex payload_hash."})
