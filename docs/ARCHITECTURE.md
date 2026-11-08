# Architecture, Analysis and Design Decisions

## 1. Reading of the problem statement

**Goal.** Issue credentials only after completion requirements are met; support revocation and third-party verification; keep traceability and immutable audit history; produce measurable outputs; provide a reproducible synthetic dataset with labelled anomalies and a separate ground truth.

**Actors.** Learner, instructor, academic administrator, support staff, platform administrator (plus an unauthenticated *third-party verifier*, who is implied by "third-party verification").

**Core entities (all implemented, each with a primary key and foreign keys).** Learner, Course, CredentialRule, CompletionRecord, Credential, Issuer, VerificationRequest, Revocation, AuditEvent. Added where the statement requires them implicitly:

| Added entity | Why |
|---|---|
| `assessment_attempt` | "generate course completion **and assessment** records"; derived values (score, status) must come from source records |
| `credential_rule_course` (bridge) | "Use bridge tables for many-to-many": rules ↔ courses |
| `credential_completion` (bridge) | Traceability: which completions qualified a credential (credential ↔ completion N:M) |
| `rule_issuer_assignment` | Effective-dated "issuer changes" |
| `issuer_key` | Key rotation; public keys for third-party verification |
| `instructor`, `app_user` | Instructor and platform roles; staff references on issuance/revocation/audit |
| `id_counter`, `import_rejection` | Atomic zero-padded IDs; evidence that the DB rejected duplicate credential IDs |

Cardinalities and lifecycles are documented per entity in `DATA_DICTIONARY.md`.

## 2. Requirement checklist (analysis)

Every statement requirement was turned into an implementation task; the full requirement → code → test → result matrix is in `REQUIREMENTS_CHECKLIST.md`. Areas covered: (1) master-then-transaction data ordering; (2) credential requirements & issuance only after rules pass; (3) unique credential IDs; (4) signed/hashed verifiable metadata; (5) verification and revocation simulation and live operation; (6) immutable audit history; (7) explicit state-change records; (8) outcomes derived from rules; (9) deterministic IDs; (10) baseline volume and seed; (11) four labelled edge cases; (12) derived values; (13) separate ground truth; (14) validation suite; (15) exports and documentation; (16) reproducibility; (17) the four acceptance criteria; (18) the evaluation focus areas.

## 3. System design

```
 Browser (vanilla JS SPA)  ──HTTPS/JSON──►  Flask blueprints (app/api)        ← validation, RBAC, HTTP mapping
                                                    │
                                          services (app/services)             ← transactions, orchestration, audit writes
                                                    │
                           domain (app/domain)  ◄───┤   pure functions: eligibility, completion state, verification
                                                    │
                                   SQLite (migrations/*.sql)                  ← constraints, triggers, indexes
```

* **Separation of concerns.** `api/` parses and authorises; `services/` own transactions (`BEGIN IMMEDIATE`) and write the audit event in the *same* transaction as the state change; `domain/` contains rule logic with no I/O, so the data generator, the validator, the application and the tests all use one definition of the rules.
* **One transaction per business operation.** Issuance allocates the ID, signs, inserts the credential and bridge rows and appends the audit event atomically. A test proves that a signing-key misconfiguration rolls everything back, including the ID counter.
* **Immutability** is enforced in the database (triggers), not only in code, so even a buggy service cannot rewrite history. Tests assert the trigger errors and also show that, if a privileged actor bypasses them, the verification engine and the hash-chain check still detect the change.

### Credential integrity and third-party verification

* On issuance a canonical JSON payload (sorted keys, no whitespace) is built from the claims: credential ID, learner ID, rule and version, issuer, key, issue/expiry time and the qualifying completion IDs. `payload_hash = SHA-256(payload_json)`; `signature = Ed25519(private_key, hex(payload_hash))`.
* Private keys are **derived** from `SIGNING_MASTER_SECRET` + key ID (HMAC-SHA256) and never stored. Public keys are stored and published at `/api/public/issuers/<id>/keys`. A third party can verify with no account and no access to the database by fetching `/api/public/credentials/<id>/document`.
* Verification re-computes the hash from the stored payload, checks the signature against the key recorded on the credential (so rotated and retired issuers still verify), checks that payload identifiers match the record, optionally compares a presented hash, then applies revocation (at the evaluation time) and expiry. Result precedence is `not_found > tampered > revoked > expired > valid`.

### Identity matching

Names are not unique (and the data deliberately contains many duplicates, including same-name-same-birthdate pairs). Matching uses email and date of birth as strong identifiers: name only → `insufficient_identifiers`; every supplied field must agree for `matched`; any disagreement → `mismatch`. Holder names are masked in public responses until identity matches.

### Audit trail

`audit_event` rows carry `prev_hash` and `event_hash` (SHA-256 over the previous hash and the event content). `GET /api/audit/verify-chain` recomputes the chain; the integrity scan reports a broken chain. Audited actions: credential issued/revoked, verification performed, completion enrolled/finalised, issuer created/retired/key rotated, rule created/retired/issuer changed, course/learner/user changes.

## 4. Decisions and assumptions (ambiguities resolved)

| Topic | Decision |
|---|---|
| Stack | Flask + SQLite + vanilla JS because the build sandbox was offline; no framework dependencies were installable. |
| IDs not specified by the statement | `CRS-NNNNNN`, `RUL-NNNNNN`, `ISS-NNN`, `KEY-ISS-NNN-VV`, `INS-NNNN`, `USR-NNNNNN`, `RIA-NNNNNN`, `ASM-<learner>-<course>-NN`, `AUD-NNNNNNNNN`. Specified formats are used exactly. |
| Year in `CRD-YYYY-…` / `VER-YYYY-…` | Year of issue/check; counters are per year (`id_counter`). The dataset is all 2026. |
| Status of credential | `active`/`revoked` stored; `expired` is derived from `expires_at` at the evaluation time, never stored. `credential.status` is a projection that a trigger only lets change `active → revoked` when a revocation row exists; the full history lives in `revocation` and `audit_event`. |
| Reissue | A revoked credential may be reissued (new ID) unless revoked for fraud or academic misconduct. At most one *active* credential per learner and rule (partial unique index). |
| Completion semantics | Counted course = status `completed` and score ≥ the rule's per-course floor. Average is over counted courses. Mandatory courses must all count. |
| Assessment rules | Needs 100% progress; attempt limit per course; no attempts after a pass; terminal states are immutable. |
| Expiry | Optional `validity_months` on the rule (none, 6, 12 or 24 in the data). |
| Rule editing | Rules are not edited after creation (version stays 1); create a new rule and retire the old one. |
| Dataset audit scope | Audit events cover credential/verification/issuer/rule lifecycle and completion *finalisation*. Enrolment and progress rows are themselves timestamped records; auditing every one would add ~80k low-value events. (The live app does audit enrolment.) |
| Duplicate credential IDs | Present in the raw `credential.csv` as labelled rows; the database rejects them and records the rejection. |
| Ground truth | `ground_truth.csv` (anomaly labels) and `ground_truth_expected_decisions.csv` (the correct result for every verification request) live in their own folder. The application's detectors read only database content; the evaluation page reads the files afterwards to compute precision/recall. |
| Public verification disclosure | Reveals credential title, issuer, dates and a masked holder name; the signed document exposes `learner_id` (a pseudonymous identifier), no email or date of birth. |
| Time | UTC everywhere, one-second resolution (see README limitation 6 for the tie rule). |

## 5. Security notes

Password hashing (scrypt via Werkzeug), JWT with expiry, per-request account check, role checks on every endpoint plus row-level checks (learners see only their own data; instructors only their own courses), login lockout, public rate limit, parameterised SQL (identifiers come only from fixed whitelists), `LIKE` wildcard escaping, strict JSON validation with unknown-field rejection, CSV-export formula neutralisation, CSP/`nosniff`/frame-deny headers, no secrets in the repository (`.env` is generated and git-ignored), generic error responses for unexpected failures.
