# Data Dictionary

Generated from `datagen/schema_spec.py`, which also drives the CSV column order, the validator's enum and required-field checks, and a test that compares it with the real database columns.

Conventions: timestamps are UTC `YYYY-MM-DDTHH:MM:SSZ`; dates are `YYYY-MM-DD`; percentages are 0-100; empty CSV cells are NULL; identifiers are immutable.

## Relationships and cardinality

| From | To | Cardinality | Notes |
|---|---|---|---|
| Learner | CompletionRecord | 1:N | A learner has many completion records; one per course (unique learner+course). |
| Course | CompletionRecord | 1:N | A course has many completion records. |
| Learner | Course | N:M | Resolved by CompletionRecord (bridge with its own attributes and lifecycle). |
| CompletionRecord | AssessmentAttempt | 1:N | Zero to max_attempts attempts; zero while only enrolled or withdrawn. |
| CredentialRule | Course | N:M | Resolved by credential_rule_course; each row marks the course mandatory or optional. |
| CredentialRule | Issuer | N:M over time | Resolved by rule_issuer_assignment with effective dates; at most one open assignment per rule. |
| Issuer | IssuerKey | 1:N | Exactly one active key per active issuer; rotated keys stay for historical verification. |
| Issuer | Issuer | 1:0..1 | A retired issuer may point to a successor. |
| Learner | Credential | 1:N | A learner can hold many credentials; at most one active credential per rule. |
| CredentialRule | Credential | 1:N | Every credential is issued under exactly one rule. |
| Credential | CompletionRecord | N:M | Resolved by credential_completion; lists the completions that qualified the credential. |
| Credential | Revocation | 1:0..N | Optional; revocation is append-only and the credential then becomes terminal. |
| Credential | VerificationRequest | 1:0..N | Optional; a verification for an unknown ID has no credential_id. |
| User | Learner / Instructor | 1:0..1 | Learner and instructor roles link to their record; staff roles link to none. |
| Any entity | AuditEvent | 1:N | Referenced by (entity_type, entity_id); events are hash-chained. |

Load order (parents before children): `learner` → `instructor` → `app_user` → `issuer` → `issuer_key` → `course` → `credential_rule` → `credential_rule_course` → `rule_issuer_assignment` → `completion_record` → `assessment_attempt` → `credential` → `credential_completion` → `revocation` → `verification_request` → `audit_event`

## Learner — `learner`

A person who enrols in courses and can hold credentials. Names are deliberately not unique.

- **Primary key:** `learner_id`
- **Kind:** master

| Field | Type | Required | Allowed values | Unit | Unique | Validation rule |
|---|---|---|---|---|---|---|
| `learner_id` | string | yes |  |  | yes | LRN-NNNNNN, immutable |
| `full_name` | string | yes |  |  |  | 2-120 chars; NOT unique (duplicate names are intentional) |
| `email` | string | yes |  |  | yes | lower-case, valid email; primary identity anchor with date_of_birth |
| `date_of_birth` | date (YYYY-MM-DD) | yes |  |  |  | between 1960-01-01 and 2008-12-31 |
| `country_code` | string | yes | IN, US, GB, DE, CA, AU, SG, AE, BR, ZA, FR, NG |  |  | ISO 3166-1 alpha-2 |
| `registered_at` | timestamp (UTC, YYYY-MM-DDTHH:MM:SSZ) | yes |  |  |  | not after the dataset reference time |
| `status` | string | yes | active, suspended, closed |  |  |  |

## Instructor — `instructor`

Staff member who teaches courses and records assessments.

- **Primary key:** `instructor_id`
- **Kind:** master

| Field | Type | Required | Allowed values | Unit | Unique | Validation rule |
|---|---|---|---|---|---|---|
| `instructor_id` | string | yes |  |  | yes | INS-NNNN |
| `full_name` | string | yes |  |  |  |  |
| `email` | string | yes |  |  | yes |  |
| `department` | string | yes |  |  |  |  |

## User (login account) — `app_user`

Login account. Passwords are never part of the dataset; accounts start without a usable password.

- **Primary key:** `user_id`
- **Kind:** master
- **Foreign keys:** `learner_id` → `learner`, `instructor_id` → `instructor`

| Field | Type | Required | Allowed values | Unit | Unique | Validation rule |
|---|---|---|---|---|---|---|
| `user_id` | string | yes |  |  | yes | USR-NNNNNN |
| `email` | string | yes |  |  | yes |  |
| `role` | string | yes | learner, instructor, academic_admin, support_staff, platform_admin |  |  |  |
| `learner_id` | string | no |  |  |  | required when role=learner |
| `instructor_id` | string | no |  |  |  | required when role=instructor |
| `is_active` | integer | yes | 0, 1 |  |  |  |
| `created_at` | timestamp (UTC, YYYY-MM-DDTHH:MM:SSZ) | yes |  |  |  |  |

## Issuer — `issuer`

Organisation that signs credentials. Issuers can be retired and replaced by a successor.

- **Primary key:** `issuer_id`
- **Kind:** master
- **Foreign keys:** `successor_issuer_id` → `issuer`
- **Lifecycle:** active -> retired (terminal); retirement records valid_to and successor_issuer_id

| Field | Type | Required | Allowed values | Unit | Unique | Validation rule |
|---|---|---|---|---|---|---|
| `issuer_id` | string | yes |  |  | yes | ISS-NNN |
| `name` | string | yes |  |  | yes |  |
| `status` | string | yes | active, retired |  |  |  |
| `valid_from` | timestamp (UTC, YYYY-MM-DDTHH:MM:SSZ) | yes |  |  |  |  |
| `valid_to` | timestamp (UTC, YYYY-MM-DDTHH:MM:SSZ) | no |  |  |  | required iff status=retired; > valid_from |
| `successor_issuer_id` | string | no |  |  |  | set only when retired; must exist |

## IssuerKey — `issuer_key`

Ed25519 public key used to verify signatures. Rotation closes the old key and opens a new one.

- **Primary key:** `key_id`
- **Kind:** master
- **Foreign keys:** `issuer_id` → `issuer`
- **Lifecycle:** active -> rotated (terminal)

| Field | Type | Required | Allowed values | Unit | Unique | Validation rule |
|---|---|---|---|---|---|---|
| `key_id` | string | yes |  |  | yes | KEY-ISS-NNN-VV |
| `issuer_id` | string | yes |  |  |  |  |
| `algorithm` | string | yes | Ed25519 |  |  |  |
| `public_key_b64` | string | yes |  |  |  | base64 of the 32-byte raw public key |
| `valid_from` | timestamp (UTC, YYYY-MM-DDTHH:MM:SSZ) | yes |  |  |  |  |
| `valid_to` | timestamp (UTC, YYYY-MM-DDTHH:MM:SSZ) | no |  |  |  | required iff status=rotated |
| `status` | string | yes | active, rotated |  |  |  |

## Course — `course`

A taught course with an assessment pass mark and attempt limit.

- **Primary key:** `course_id`
- **Kind:** master
- **Foreign keys:** `instructor_id` → `instructor`

| Field | Type | Required | Allowed values | Unit | Unique | Validation rule |
|---|---|---|---|---|---|---|
| `course_id` | string | yes |  |  | yes | CRS-NNNNNN |
| `title` | string | yes |  |  |  |  |
| `category` | string | yes |  |  |  |  |
| `level` | string | yes | introductory, intermediate, advanced |  |  |  |
| `credit_hours` | integer | yes |  | hours |  | 1-200 |
| `pass_mark` | integer | yes |  | percent |  | 40-100 |
| `max_attempts` | integer | yes |  | attempts |  | 1-10 |
| `instructor_id` | string | yes |  |  |  |  |
| `status` | string | yes | active, archived |  |  |  |
| `created_at` | timestamp (UTC, YYYY-MM-DDTHH:MM:SSZ) | yes |  |  |  |  |

## CredentialRule — `credential_rule`

Requirements for earning a credential: course set (via bridge), thresholds, validity and effective dates.

- **Primary key:** `rule_id`
- **Kind:** master
- **Lifecycle:** draft -> active -> retired; retired rules stop issuing at effective_to

| Field | Type | Required | Allowed values | Unit | Unique | Validation rule |
|---|---|---|---|---|---|---|
| `rule_id` | string | yes |  |  | yes | RUL-NNNNNN |
| `title` | string | yes |  |  | yes |  |
| `credential_type` | string | yes | certificate, micro_credential, professional_certificate |  |  |  |
| `version` | integer | yes |  |  |  | >= 1 |
| `min_courses_required` | integer | yes |  | courses |  | >= number of mandatory courses, <= courses in rule |
| `min_avg_score` | number | yes |  | percent |  | 0-100; average of counted courses |
| `min_course_score` | number | yes |  | percent |  | 0-100; per-course floor for a course to count |
| `validity_months` | integer | no |  | months |  | null = never expires |
| `effective_from` | timestamp (UTC, YYYY-MM-DDTHH:MM:SSZ) | yes |  |  |  |  |
| `effective_to` | timestamp (UTC, YYYY-MM-DDTHH:MM:SSZ) | no |  |  |  | > effective_from |
| `status` | string | yes | draft, active, retired |  |  |  |
| `created_at` | timestamp (UTC, YYYY-MM-DDTHH:MM:SSZ) | yes |  |  |  | <= effective_from |

## CredentialRule-Course (bridge, N:M) — `credential_rule_course`

Bridge between rules and courses. A course can belong to several rules.

- **Primary key:** `rule_id + course_id`
- **Kind:** bridge
- **Foreign keys:** `rule_id` → `credential_rule`, `course_id` → `course`

| Field | Type | Required | Allowed values | Unit | Unique | Validation rule |
|---|---|---|---|---|---|---|
| `rule_id` | string | yes |  |  |  |  |
| `course_id` | string | yes |  |  |  |  |
| `is_mandatory` | integer | yes | 0, 1 |  |  |  |

## RuleIssuerAssignment (effective-dated) — `rule_issuer_assignment`

Which issuer signs a rule, with effective dates. Issuer changes close one row and open another.

- **Primary key:** `assignment_id`
- **Kind:** history
- **Foreign keys:** `rule_id` → `credential_rule`, `issuer_id` → `issuer`

| Field | Type | Required | Allowed values | Unit | Unique | Validation rule |
|---|---|---|---|---|---|---|
| `assignment_id` | string | yes |  |  | yes | RIA-NNNNNN |
| `rule_id` | string | yes |  |  |  |  |
| `issuer_id` | string | yes |  |  |  |  |
| `effective_from` | timestamp (UTC, YYYY-MM-DDTHH:MM:SSZ) | yes |  |  |  |  |
| `effective_to` | timestamp (UTC, YYYY-MM-DDTHH:MM:SSZ) | no |  |  |  | > effective_from; at most one open row per rule |

## CompletionRecord — `completion_record`

A learner's enrolment in a course. Status, attempts and score are derived from assessment attempts.

- **Primary key:** `completion_id`
- **Kind:** transaction
- **Foreign keys:** `learner_id` → `learner`, `course_id` → `course`
- **Lifecycle:** enrolled -> in_progress -> completed | failed | withdrawn (terminal states are immutable)

| Field | Type | Required | Allowed values | Unit | Unique | Validation rule |
|---|---|---|---|---|---|---|
| `completion_id` | string | yes |  |  | yes | CMP-<learner_id>-<course_id> |
| `learner_id` | string | yes |  |  |  |  |
| `course_id` | string | yes |  |  |  |  |
| `enrolled_at` | timestamp (UTC, YYYY-MM-DDTHH:MM:SSZ) | yes |  |  |  |  |
| `progress_pct` | integer | yes |  | percent |  | 0-100; 100 required before assessment |
| `status` | string | yes | enrolled, in_progress, completed, failed, withdrawn |  |  |  |
| `attempts_used` | integer | yes |  |  |  | = count of assessment_attempt rows |
| `final_score` | number | no |  | percent |  | = max attempt score; null when no attempts |
| `finalized_at` | timestamp (UTC, YYYY-MM-DDTHH:MM:SSZ) | no |  |  |  | set iff status in (completed, failed, withdrawn); completed => time of first passing attempt |

## AssessmentAttempt — `assessment_attempt`

Append-only assessment result. Source of truth for score and completion status.

- **Primary key:** `attempt_id`
- **Kind:** event
- **Foreign keys:** `completion_id` → `completion_record`

| Field | Type | Required | Allowed values | Unit | Unique | Validation rule |
|---|---|---|---|---|---|---|
| `attempt_id` | string | yes |  |  | yes | ASM-<learner_id>-<course_id>-NN |
| `completion_id` | string | yes |  |  |  |  |
| `attempt_no` | integer | yes |  |  |  | 1..max_attempts, contiguous, no attempts after a pass |
| `score` | number | yes |  | percent |  | 0-100, one decimal |
| `passed` | integer | yes | 0, 1 |  |  | = score >= course.pass_mark |
| `attempted_at` | timestamp (UTC, YYYY-MM-DDTHH:MM:SSZ) | yes |  |  |  | strictly increasing per completion |

## Credential — `credential`

Signed credential issued once a rule is satisfied. Immutable apart from the active -> revoked transition.

- **Primary key:** `credential_id`
- **Kind:** transaction
- **Foreign keys:** `learner_id` → `learner`, `rule_id` → `credential_rule`, `issuer_id` → `issuer`, `key_id` → `issuer_key`, `issued_by` → `app_user`
- **Lifecycle:** active -> revoked (terminal); expiry is derived from expires_at, never stored

| Field | Type | Required | Allowed values | Unit | Unique | Validation rule |
|---|---|---|---|---|---|---|
| `credential_id` | string | yes |  |  | yes | CRD-YYYY-NNNNNN, YYYY = issue year |
| `learner_id` | string | yes |  |  |  |  |
| `rule_id` | string | yes |  |  |  |  |
| `issuer_id` | string | yes |  |  |  |  |
| `key_id` | string | yes |  |  |  |  |
| `issued_at` | timestamp (UTC, YYYY-MM-DDTHH:MM:SSZ) | yes |  |  |  | >= completion time of every qualifying course |
| `expires_at` | timestamp (UTC, YYYY-MM-DDTHH:MM:SSZ) | no |  |  |  | = issued_at + rule.validity_months |
| `status` | string | yes | active, revoked |  |  | revoked iff a revocation row exists |
| `payload_json` | string | yes |  |  |  | canonical JSON of the signed claims |
| `payload_hash` | string | yes |  |  |  | SHA-256 hex of payload_json |
| `signature_b64` | string | yes |  |  |  | Ed25519 signature over the ASCII hex payload_hash |
| `issued_by` | string | no |  |  |  |  |

## Credential-Completion (bridge, N:M) — `credential_completion`

Which completion records qualified a credential (traceability).

- **Primary key:** `credential_id + completion_id`
- **Kind:** bridge
- **Foreign keys:** `credential_id` → `credential`, `completion_id` → `completion_record`

| Field | Type | Required | Allowed values | Unit | Unique | Validation rule |
|---|---|---|---|---|---|---|
| `credential_id` | string | yes |  |  |  |  |
| `completion_id` | string | yes |  |  |  |  |

## Revocation — `revocation`

Append-only record that a credential stopped being valid at effective_at.

- **Primary key:** `revocation_id`
- **Kind:** event
- **Foreign keys:** `credential_id` → `credential`, `revoked_by` → `app_user`

| Field | Type | Required | Allowed values | Unit | Unique | Validation rule |
|---|---|---|---|---|---|---|
| `revocation_id` | string | yes |  |  | yes | REV-<credential_id>-NN |
| `credential_id` | string | yes |  |  |  |  |
| `seq` | integer | yes |  |  |  | >= 1; part of the ID suffix |
| `reason_code` | string | yes | fraud, academic_misconduct, issued_in_error, learner_request, rule_change |  |  |  |
| `reason_detail` | string | no |  |  |  |  |
| `effective_at` | timestamp (UTC, YYYY-MM-DDTHH:MM:SSZ) | yes |  |  |  | > credential.issued_at |
| `revoked_by` | string | no |  |  |  |  |

## VerificationRequest — `verification_request`

A third-party or staff check of a credential, with the recorded outcome. Append-only.

- **Primary key:** `verification_id`
- **Kind:** event
- **Foreign keys:** `credential_id` → `credential`, `processed_by` → `app_user`

| Field | Type | Required | Allowed values | Unit | Unique | Validation rule |
|---|---|---|---|---|---|---|
| `verification_id` | string | yes |  |  | yes | VER-YYYY-NNNNNN |
| `presented_credential_id` | string | yes |  |  |  | exactly what the verifier typed or scanned |
| `credential_id` | string | no |  |  |  | resolved credential; null iff result_status=not_found |
| `requested_at` | timestamp (UTC, YYYY-MM-DDTHH:MM:SSZ) | yes |  |  |  | evaluation time used for revocation and expiry |
| `channel` | string | yes | public_api, support_desk, learner_share |  |  |  |
| `requester_type` | string | yes | employer, institution, learner, support, other |  |  |  |
| `requester_org` | string | no |  |  |  |  |
| `presented_hash` | string | no |  |  |  | 64 hex chars when supplied |
| `claimed_name` | string | no |  |  |  |  |
| `claimed_email` | string | no |  |  |  |  |
| `claimed_dob` | date (YYYY-MM-DD) | no |  |  |  |  |
| `result_status` | string | yes | valid, revoked, expired, not_found, tampered |  |  | precedence: not_found > tampered > revoked > expired > valid |
| `identity_status` | string | yes | matched, mismatch, insufficient_identifiers, not_requested |  |  | name alone is never sufficient; needs email or date_of_birth |
| `integrity_ok` | integer | no | 0, 1 |  |  | null iff not_found |
| `processed_by` | string | no |  |  |  |  |

## AuditEvent — `audit_event`

Immutable, hash-chained history of state changes.

- **Primary key:** `event_id`
- **Kind:** event
- **Foreign keys:** `actor_user_id` → `app_user`

| Field | Type | Required | Allowed values | Unit | Unique | Validation rule |
|---|---|---|---|---|---|---|
| `event_id` | string | yes |  |  | yes | AUD-NNNNNNNNN, equals seq |
| `seq` | integer | yes |  |  | yes | contiguous from 1 |
| `occurred_at` | timestamp (UTC, YYYY-MM-DDTHH:MM:SSZ) | yes |  |  |  | non-decreasing with seq |
| `actor_type` | string | yes | user, public, system |  |  |  |
| `actor_user_id` | string | no |  |  |  | set iff actor_type=user |
| `action` | string | yes |  |  |  |  |
| `entity_type` | string | yes |  |  |  |  |
| `entity_id` | string | yes |  |  |  |  |
| `details_json` | string | yes |  |  |  | canonical JSON |
| `prev_hash` | string | yes |  |  |  | event_hash of the previous event; 64 zeros for the first |
| `event_hash` | string | yes |  |  | yes | SHA-256 over prev_hash and event content |

## Supporting tables (application only)

- `id_counter` — atomic counters behind `CRD-YYYY-NNNNNN`, `VER-YYYY-NNNNNN` and the other generated IDs.
- `import_rejection` — rows refused by database constraints during import (for example the duplicate credential IDs).
- `schema_migration` — applied migration files.

## Database-enforced rules

Defined in `migrations/001_initial_schema.sql`: ID format `CHECK`s, enum `CHECK`s, `UNIQUE` and partial-unique indexes (one active credential per learner and rule), foreign keys, and triggers that make `audit_event`, `revocation`, `verification_request` and `assessment_attempt` append-only, make credential issuance fields immutable, allow only `active → revoked` (and only when a revocation row exists), and freeze finalised completion records.
