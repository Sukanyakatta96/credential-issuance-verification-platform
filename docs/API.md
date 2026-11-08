# API Conventions

Base path `/api`. JSON in, JSON out. A complete, generated list of endpoints with their access rules is in `API_ENDPOINTS.md`.

**Authentication.** `POST /api/auth/login` with `{"email","password"}` returns `{"token","user"}`. Send `Authorization: Bearer <token>`. Tokens expire (`JWT_TTL_MINUTES`). Five failed logins for an email/IP lock further attempts for `LOGIN_LOCKOUT_SECONDS` (HTTP 429).

**Errors.** Every error has the same shape:

```json
{"error": {"code": "NOT_ELIGIBLE", "message": "…", "details": {…}}}
```

| Status | Meaning | Typical codes |
|---|---|---|
| 400 | Invalid input; `details` maps field → message | `VALIDATION_ERROR`, `WEAK_PASSWORD` |
| 401 | Missing/invalid/expired token or wrong credentials | `UNAUTHENTICATED`, `TOKEN_EXPIRED`, `INVALID_CREDENTIALS` |
| 403 | Role or ownership does not allow it | `FORBIDDEN` |
| 404 | Unknown resource | `NOT_FOUND` |
| 409 | State conflict | `ALREADY_REVOKED`, `COMPLETION_CLOSED`, `DUPLICATE_EMAIL`, `TOO_SOON`, `CONSTRAINT_VIOLATION` |
| 422 | A business rule failed | `NOT_ELIGIBLE` (with the list of checks), `COURSE_NOT_FINISHED`, `INVALID_THRESHOLD`, … |
| 429 | Throttled | `LOGIN_LOCKED`, `RATE_LIMITED` |

**Lists.** `?page=1&page_size=25` (max 200) plus per-resource filters (`q`, `status`, …). Response: `{"items":[…],"page":1,"page_size":25,"total":123}`.

**Row-level access** (beyond the role table): learners are restricted to their own learner, completions, credentials and verification history regardless of query parameters; instructors only see and change completions of courses they teach.

## Key flows

**Check eligibility** — `GET /api/eligibility?learner_id=LRN-000001&rule_id=RUL-000001` (staff) returns each check with `passed` and an explanation, the qualifying completion IDs and the average.

**Issue** — `POST /api/credentials {"learner_id","rule_id"}` (academic/platform admin). `201` with the credential including `payload_json`, `payload_hash`, `signature_b64`, `key_id`, qualifying completions and the audit trail; `422 NOT_ELIGIBLE` with `details.checks` otherwise.

**Revoke** — `POST /api/credentials/<id>/revoke {"reason_code":"fraud|academic_misconduct|issued_in_error|learner_request|rule_change","reason_detail"}` → `201` revocation `REV-<credential-id>-01`; `409 ALREADY_REVOKED` the second time.

**Verify (public, no token)** — `POST /api/public/verify`

```json
{"credential_id":"CRD-2026-000001","claimed_name":"Ada Lovelace","claimed_email":"ada@example.org",
 "claimed_dob":"1990-12-10","presented_hash":"<64 hex>","requester_type":"employer","requester_org":"Acme"}
```

Only `credential_id` is required. Response: `result_status` (`valid|revoked|expired|not_found|tampered`), `identity_status` (`matched|mismatch|insufficient_identifiers|not_requested`), `integrity_ok`, `reasons[]`, `notes[]`, and a `credential` summary (holder name masked unless identity matched). Throttled per client IP.

**Offline verification** — `GET /api/public/credentials/<id>/document` returns `payload_json`, `payload_hash`, `signature_b64`, `key_id`; `GET /api/public/issuers/<issuer_id>/keys` returns the public keys. Check `sha256(payload_json) == payload_hash`, then verify the Ed25519 signature over the ASCII hex hash.

**Replay** — `POST /api/verifications/<id>/replay` re-runs a stored check at its original time and reports `reproducible` plus any `differences`.

**Integrity and evaluation** — `GET /api/integrity/scan` (database-only detectors), `GET /api/integrity/evaluation` (precision/recall per labelled anomaly type and verification-engine accuracy against the ground-truth files).

**Exports** — `GET /api/reports/export/{credentials|verifications|revocations|pending_issuance}` as CSV (spreadsheet formulas neutralised).
