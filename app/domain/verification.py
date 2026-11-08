import json
import re

from .. import crypto

RESULT_STATUSES = ("valid", "revoked", "expired", "not_found", "tampered")
IDENTITY_STATUSES = ("matched", "mismatch", "insufficient_identifiers", "not_requested")


def normalize_name(value: str | None) -> str:
    return re.sub(r"\s+", " ", (value or "").strip()).casefold()


def match_identity(*, learner: dict | None, claimed_name: str | None, claimed_email: str | None,
                   claimed_dob: str | None) -> str:
    name = normalize_name(claimed_name)
    email = (claimed_email or "").strip().lower()
    dob = (claimed_dob or "").strip()
    if not (name or email or dob):
        return "not_requested"
    if learner is None:
        return "not_requested"
    if not (email or dob):
        return "insufficient_identifiers"
    comparisons = []
    if name:
        comparisons.append(name == normalize_name(learner["full_name"]))
    if email:
        comparisons.append(email == learner["email"].lower())
    if dob:
        comparisons.append(dob == learner["date_of_birth"])
    return "matched" if all(comparisons) else "mismatch"


def check_integrity(credential: dict, public_key_b64: str | None) -> tuple[bool, list[str]]:
    problems = []
    if crypto.payload_hash(credential["payload_json"]) != credential["payload_hash"]:
        problems.append("stored payload hash does not match the payload content")
    if not public_key_b64 or not crypto.verify_signature(public_key_b64, credential["payload_hash"],
                                                          credential["signature_b64"]):
        problems.append("issuer signature does not verify against the stored payload hash")
    try:
        payload = json.loads(credential["payload_json"])
        if payload.get("credential_id") != credential["credential_id"] or payload.get("learner_id") != credential["learner_id"]:
            problems.append("payload identifiers do not match the credential record")
    except ValueError:
        problems.append("payload is not valid JSON")
    return (not problems, problems)


def evaluate_verification(*, credential: dict | None, public_key_b64: str | None, learner: dict | None,
                          earliest_effective_revocation: str | None, as_of: str, presented_hash: str | None,
                          claimed_name: str | None, claimed_email: str | None, claimed_dob: str | None) -> dict:
    """Deterministic: identical inputs always give an identical result.

    Precedence: not_found > tampered > revoked > expired > valid.
    """
    reasons: list[str] = []
    if credential is None or credential["issued_at"] > as_of:
        reasons.append("no credential with this identifier had been issued at the time of verification")
        return {"result_status": "not_found", "identity_status": "not_requested",
                "integrity_ok": None, "reasons": reasons}

    integrity_ok, problems = check_integrity(credential, public_key_b64)
    reasons.extend(problems)
    presented = (presented_hash or "").strip().lower()
    if presented and presented != credential["payload_hash"]:
        reasons.append("presented document hash differs from the issued payload hash")
        integrity_ok_for_status = False
    else:
        integrity_ok_for_status = integrity_ok

    identity_status = match_identity(learner=learner, claimed_name=claimed_name,
                                     claimed_email=claimed_email, claimed_dob=claimed_dob)

    if not integrity_ok_for_status:
        status = "tampered"
    elif earliest_effective_revocation is not None and earliest_effective_revocation <= as_of:
        status = "revoked"
        reasons.append(f"credential revoked effective {earliest_effective_revocation}")
    elif credential["expires_at"] is not None and credential["expires_at"] <= as_of:
        status = "expired"
        reasons.append(f"credential expired {credential['expires_at']}")
    else:
        status = "valid"
        reasons.append("signature, payload hash, revocation and expiry checks passed")
    return {"result_status": status, "identity_status": identity_status,
            "integrity_ok": integrity_ok, "reasons": reasons}
