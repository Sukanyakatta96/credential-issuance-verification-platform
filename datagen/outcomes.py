"""Independent re-statement of the verification rules used to derive ground-truth labels.

It deliberately does not import the application's verification module.
"""


def expected_result(*, exists, issued_at, intact, revoked_at, expires_at, requested_at, presented_hash_ok):
    if not exists or issued_at > requested_at:
        return "not_found"
    if not intact or presented_hash_ok is False:
        return "tampered"
    if revoked_at is not None and revoked_at <= requested_at:
        return "revoked"
    if expires_at is not None and expires_at <= requested_at:
        return "expired"
    return "valid"


def expected_identity(*, learner, name, email, dob):
    norm = lambda s: " ".join((s or "").split()).lower()
    if not (norm(name) or (email or "").strip() or (dob or "").strip()):
        return "not_requested"
    if not ((email or "").strip() or (dob or "").strip()):
        return "insufficient_identifiers"
    checks = []
    if norm(name):
        checks.append(norm(name) == norm(learner["full_name"]))
    if (email or "").strip():
        checks.append(email.strip().lower() == learner["email"])
    if (dob or "").strip():
        checks.append(dob.strip() == learner["date_of_birth"])
    return "matched" if all(checks) else "mismatch"
