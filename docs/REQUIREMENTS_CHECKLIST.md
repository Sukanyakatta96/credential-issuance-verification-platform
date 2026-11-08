# Requirement-by-Requirement Acceptance Checklist

"Result" is what actually happened when the test ran (final run: `./scripts/run_tests.sh` — 91 Python tests OK, 195/195 dataset validation checks, 84/84 frontend checks; full-scale figures from `docs/TEST_RESULTS.md`). Test names are `tests/<file>.py::<Class>.<method>`; `FE` = `tests/frontend_smoke.mjs`; `VAL` = `datagen/validate.py` checks.

## A. Business workflow and rules

| # | Requirement | Implementation | Test performed | Result | Status |
|---|---|---|---|---|---|
| A1 | Master data first: Learner, Course, CredentialRule, CompletionRecord, Credential | `datagen/generator.py` (order: instructors/users/issuers → courses → rules → learners → completions → credentials); `datagen/schema_spec.py::TABLE_ORDER` | `test_datagen::test_loading_enforces_constraints...` (load with FKs enforced, `PRAGMA foreign_key_check` empty); VAL foreign-key checks | 0 FK violations at both scales | PASS |
| A2 | Dependent records use valid parent IDs | Generator builds children from parent objects; loader enforces FKs | VAL `foreign_key` category (25 checks); `test_validator_actually_fails_on_corrupted_data` proves the checks bite | Pass; corrupted data is flagged | PASS |
| A3a | Define credential requirements | `credential_rule`, `credential_rule_course`; `POST /api/rules`; `app/services/catalog.py::create_rule`; UI *Credential rules* | `test_api::DirectoryTests.test_rule_creation_validation`; FE rule pages | Thresholds validated (4 error codes) | PASS |
| A3b | Generate completion and assessment records | `generator.py::enrol`; `app/services/completions.py` | `CompletionTests.test_lifecycle_and_derived_values`, `test_pass_boundary_and_validation`; VAL reconciliation | Status/score derive from attempts | PASS |
| A3c | Issue unique credential IDs only after rules pass | `app/services/issuance.py::issue_credential` → `domain/eligibility.py`; PK + counter | `IssuanceTests` (requirements enforced, duplicates blocked, IDs sequential), `test_domain::EligibilityTests` (boundaries) | 422 with per-check explanations when rules fail; nothing persisted | PASS |
| A3d | Verifiable signed-record metadata / deterministic hashes | `app/crypto.py` (canonical JSON, SHA-256, Ed25519); `public/credentials/<id>/document` | `test_public_signed_document_allows_offline_verification`, `test_forged_signature_by_wrong_key_is_tampered` | Offline verification works; forged signature detected | PASS |
| A3e | Simulate verification requests and revocations | Live: `/api/public/verify`, `/api/verifications`, `/revoke`; generated: 5,000 requests, 599 revocations | `VerificationTests` (13), `RevocationAndAuditTests`; FE issue → verify → revoke flow | All pass | PASS |
| A3f | Preserve immutable audit history | `audit_event` + triggers + hash chain (`app/audit.py`) | `test_history_cannot_be_rewritten`, `test_audit_chain_verification_detects_tampering`; VAL audit checks; FE "audit hash chain verifies" | Updates/deletes rejected; tampering detected | PASS |
| A4 | State changes persisted as explicit records/events; history not overwritten | `revocation`, `verification_request`, `assessment_attempt`, `audit_event` append-only; `credential.status` only `active→revoked` | Same tests as A3f plus `test_status_cannot_become_revoked_without_a_revocation_record` | Triggers abort invalid changes | PASS |
| A5 | Outcomes and labels from documented rules, not random assignment | Eligibility via shared `evaluate_eligibility`; verification labels via independent `datagen/outcomes.py` | `test_labels_agree_with_the_business_rules`; engine vs ground truth: accuracy 1.0 on 5,000 requests | Pass | PASS |

## B. Entities, relationships, IDs

| # | Requirement | Implementation | Test | Result | Status |
|---|---|---|---|---|---|
| B1 | All nine core entities with PKs and FKs | `migrations/001_initial_schema.sql`; `docs/DATA_DICTIONARY.md` | `test_schema_spec_matches_database_columns` | Spec = DB for 16 tables | PASS |
| B2 | Document cardinality, optional relationships, effective dates, lifecycle states | `datagen/schema_spec.py::RELATIONSHIPS`, per-entity `lifecycle`; generated into the data dictionary | Reviewed; lifecycle rules enforced by VAL `lifecycle` checks | Documented and validated | PASS |
| B3 | Bridge tables for N:M; event history for state changes | `credential_rule_course`, `credential_completion`, `rule_issuer_assignment`, event tables | VAL business_rules checks (bridge belongs to holder, qualifying set equals recomputed set) | Pass | PASS |
| B4 | Anomalies use issue_type/ground_truth labels, not silent corruption | Injected after baseline, labelled in `ground_truth/` | `test_ground_truth_is_separate_and_covers_every_required_edge_case` | Exactly the labelled rows differ | PASS |
| B5 | IDs `CRD-2026-000001`, `LRN-000001`, `CMP-<learner>-<course>`, `VER-2026-000001`, `REV-<credential>-01` | `app/ids.py`; DB `GLOB` CHECKs; VAL id_format | `test_naming_conventions`; `IssuanceTests`; `VerificationTests` | Match exactly; immutable; consistent across files | PASS |

## C. Synthetic data generation steps

| # | Requirement | Implementation | Test / evidence | Result | Status |
|---|---|---|---|---|---|
| C1 | Data dictionary for all entities (type, required, allowed, unit, uniqueness, validation) | `docs/DATA_DICTIONARY.md`, `data/*/data_dictionary.json` | `test_data_dictionary_covers_every_entity` | 16 entities, all attributes present | PASS |
| C2 | Parents first, then child/event tables | Generator and loader order | Loader test above | Pass | PASS |
| C3 | Deterministic IDs, zero-padded, consistent across files | `app/ids.py` used by generator and app | VAL id_format + FK checks | Pass | PASS |
| C4 | Volume: 20,000 learners, 1,000 courses, 10,000 credentials, 5,000 verifications; revoked, duplicate names, incomplete courses, issuer changes; seed 20261022; parameterised scale | `datagen/generate.py` (`--scale`, explicit counts, `--seed`) | Manifest row counts: 20,000 / 1,000 / 10,000 distinct (10,008 rows incl. 8 labelled duplicate-ID rows) / 5,000; 599 revocations; 1,468 learners sharing a name across 715 name groups (VAL profile); 2 retired issuers + 1 key rotation; `test_required_population_characteristics_are_present`, `test_different_seed_changes_data_and_same_generator_scales` | Pass | PASS |
| C5 | Valid baseline first, then labelled edge cases: issued before completion; duplicate credential ID; revoked verifies active; altered hash not detected | `generator.py` (A1–A4 injection after baseline) | 30 / 8 / 25 / 20 (+20) labels at full scale; scanner recovers every one, 0 false positives/negatives | Pass | PASS |
| C6 | Derived values calculated from source records | `domain/completion.py`, credential expiry, statuses | VAL reconciliation checks (status/attempts/score/finalised time recomputed; expiry = issue + months) | 0 unexpected violations | PASS |
| C7 | Separate ground_truth.csv/json; never leaks into features | `data/*/ground_truth/`; scanner source never references it (asserted) | `test_application_scanner_recovers_ground_truth_without_seeing_it` | Pass | PASS |
| C8 | Validation: PK, FK, enums, dates, arithmetic, lifecycle, duplicates | `datagen/validate.py` (195 checks) | `docs/VALIDATION_REPORT.md` | 195/195 pass (every violation is a labelled anomaly; every anomaly found) | PASS |
| C9 | Export CSV/JSON/SQL + README, schema/data dictionary, generator command, seed, source manifest, validation summary | `datagen/export.py`; `manifest.json`, `source_manifest.json`, README | `test_sql_seed_produces_the_same_database_as_the_loader` | All present. **Caveat:** the ZIP omits the full dataset's JSON/SQL for size (regenerable; checksums in manifest) | PASS (with caveat) |
| C10 | Regenerate twice with the same seed; compare counts and checksums | `--check-reproducibility`; `reproducibility_report.json` | `test_regeneration_with_same_seed_is_byte_identical`; full-scale run | 41 files identical across 2 regenerations | PASS |

## D. Acceptance criteria and evaluation focus

| # | Requirement | Implementation | Test | Result | Status |
|---|---|---|---|---|---|
| D1 | Issuance rules are enforced | Service + DB constraints | `IssuanceTests`, `EligibilityTests`; VAL "issuance requirements satisfied" | Pass | PASS |
| D2 | Verification result is reproducible | Pure function; `replay` endpoint | `test_replay_is_reproducible_even_after_later_revocation`, `test_same_second_ordering...`, `test_decision_is_deterministic`; engine accuracy 1.0 | Pass | PASS |
| D3 | Revocation status is current | Verification reads revocations at evaluation time | `test_valid_revoked_flow_and_record_keeping`; FE "public verifier now reports revoked" | Pass | PASS |
| D4 | Identity matching does not rely on name alone | `domain/verification.py::match_identity` | `test_domain::IdentityTests`, `test_identity_never_relies_on_name_alone_and_masks_holder`; VAL "identity never matched on name alone" | Pass | PASS |
| D5 | (a) distributions, (b) IDs/joins, (c) lifecycle consistency, (d) derived values, (e) normal/boundary/failure/exception coverage, (f) separate ground truth, (g) seed/documentation/lawful provenance | See sections A–C; `source_manifest.json` states no external data | VAL profile in `docs/VALIDATION_REPORT.md`; boundary tests in `test_domain` | Pass | PASS |

## E. Application requirements from the brief

| # | Requirement | Implementation | Test | Result | Status |
|---|---|---|---|---|---|
| E1 | One integrated app: frontend, backend, DB connected; all pages, forms, APIs, actions work | `app/` (api, services, static) | FE: every route for each of 5 roles renders without error (50+ page loads); forms/modals exercised: login, register learner, create course, create user, rotate key, issue, revoke, verify, progress, assessment, change password, integrity scan, evaluation, audit chain | 84/84. **Caveat:** not every button in every page was clicked (e.g. rule-creation picker, retire-issuer dialog, reset-password dialog are covered at API level only) | PASS (with caveat) |
| E2 | Roles and permissions work | `app/security.py::require_roles`, row-level checks | `PermissionTests.test_role_matrix` (≈70 role × endpoint assertions), `test_learner_sees_only_own...`; FE blocked-page checks | Pass | PASS |
| E3 | Data actually saved and retrieved; no fake/hardcoded dashboard figures or fake success | All views query SQLite; dashboard in `services/reports.py` | `ReportTests.test_dashboard_numbers_come_from_the_database` (empty → populated, reconciles) | Pass | PASS |
| E4 | Validation and error handling; duplicates, nulls, invalid input, unexpected failures | `app/validation.py`, `app/errors.py`, DB constraints | `DirectoryTests` (validation, duplicates, injection), `VerificationTests.test_unknown_credential_and_malformed_input` | Pass; unknown errors return a generic 500 body | PASS |
| E5 | Secure authentication/authorisation; no hard-coded secrets | Hashing, JWT, lockout, `.env` generation, refuse-to-start without secrets | `AuthenticationTests` (7 tests) | Pass | PASS |
| E6 | Transactions and consistency for critical operations | `transaction()` (`BEGIN IMMEDIATE`) in every service write | `test_issuance_is_atomic_when_signing_key_is_misconfigured` | Rolled back including counter | PASS |
| E7 | Migrations; constraints; no duplicates; history preserved | `migrations/`, `app/db.py::migrate` | Schema loaded in every test; `test_history_cannot_be_rewritten` | Pass | PASS |
| E8 | Search, filtering, pagination, charts, loading states, messages | `ui.js::dataTable`, `charts.js` | FE page loads; `test_search_and_pagination_are_injection_safe` | Functionally pass. **Visual quality not verified in a browser** | PASS (functional) |
| E9 | Responsive, professional UI | `static/css/styles.css` (grid, breakpoints, dark mode) | None automated | **Not verified by a machine; review by eye** | NOT VERIFIED |
| E10 | Edge cases handled in the live app | Ties, expiry, key rotation, retired issuers, reissue policy, closed completions | `IssuerLifecycleTests`, `test_reissue_policy_after_revocation`, `test_expiry_is_evaluated_at_the_requested_time` | Pass | PASS |
| E11 | Code quality: layering, naming, few comments, no unused imports | Layered packages; comments only where a decision needs explaining | Unused-import scan run and cleaned | Pass | PASS |

## F. Deliverables

| Deliverable | Where | Status |
|---|---|---|
| Frontend / backend source, migrations | `app/`, `migrations/` | Done |
| Synthetic datasets, generator, ground truth | `data/starter` (all formats), `data/full` (CSV + ground truth + reports; JSON/SQL regenerable), `datagen/` | Done (see C9 caveat) |
| Automated tests and results | `tests/`, `scripts/run_tests.sh`, `docs/TEST_RESULTS.md` | Done |
| Validation report | `docs/VALIDATION_REPORT.md` | Done |
| Schema / data dictionary, API docs, README, `.env.example`, install and run instructions | `docs/`, `README.md`, `.env.example` | Done |
| GitHub-ready source | Standard layout, `.gitignore`, no secrets | Ready; **not pushed anywhere** |
| One ZIP | `dist/credential-platform.zip` (built by `make package`) | See delivery message |
