# Data Validation Report

Dataset: seed 20261022, command `python -m datagen.generate --scale full --seed 20261022 --learners 20000 --courses 1000 --credentials 10000 --verifications 5000`.

**195 of 195 checks passed**, 0 failed. Labelled anomalies detected by the checks: 176 (ground truth holds 103 labels; some labels are detected by more than one check).

A check passes when every violation it finds is a labelled, deliberately injected anomaly and every anomaly it is meant to catch was found. Unexpected violations or missed anomalies fail the check.

| Category | Check | Records | Violations | Labelled found | Unexpected | Missed | Status |
|---|---|---|---|---|---|---|---|
| primary_key | learner: primary key unique | 20000 | 0 | 0 | 0 | 0 | PASS |
| id_format | learner: learner_id format | 20000 | 0 | 0 | 0 | 0 | PASS |
| enum_and_required | learner.learner_id: required/allowed values | 20000 | 0 | 0 | 0 | 0 | PASS |
| enum_and_required | learner.full_name: required/allowed values | 20000 | 0 | 0 | 0 | 0 | PASS |
| enum_and_required | learner.email: required/allowed values | 20000 | 0 | 0 | 0 | 0 | PASS |
| enum_and_required | learner.date_of_birth: required/allowed values | 20000 | 0 | 0 | 0 | 0 | PASS |
| enum_and_required | learner.country_code: required/allowed values | 20000 | 0 | 0 | 0 | 0 | PASS |
| enum_and_required | learner.registered_at: required/allowed values | 20000 | 0 | 0 | 0 | 0 | PASS |
| enum_and_required | learner.status: required/allowed values | 20000 | 0 | 0 | 0 | 0 | PASS |
| primary_key | instructor: primary key unique | 62 | 0 | 0 | 0 | 0 | PASS |
| id_format | instructor: instructor_id format | 62 | 0 | 0 | 0 | 0 | PASS |
| enum_and_required | instructor.instructor_id: required/allowed values | 62 | 0 | 0 | 0 | 0 | PASS |
| enum_and_required | instructor.full_name: required/allowed values | 62 | 0 | 0 | 0 | 0 | PASS |
| enum_and_required | instructor.email: required/allowed values | 62 | 0 | 0 | 0 | 0 | PASS |
| enum_and_required | instructor.department: required/allowed values | 62 | 0 | 0 | 0 | 0 | PASS |
| primary_key | app_user: primary key unique | 370 | 0 | 0 | 0 | 0 | PASS |
| id_format | app_user: user_id format | 370 | 0 | 0 | 0 | 0 | PASS |
| enum_and_required | app_user.user_id: required/allowed values | 370 | 0 | 0 | 0 | 0 | PASS |
| enum_and_required | app_user.email: required/allowed values | 370 | 0 | 0 | 0 | 0 | PASS |
| enum_and_required | app_user.role: required/allowed values | 370 | 0 | 0 | 0 | 0 | PASS |
| enum_and_required | app_user.is_active: required/allowed values | 370 | 0 | 0 | 0 | 0 | PASS |
| enum_and_required | app_user.created_at: required/allowed values | 370 | 0 | 0 | 0 | 0 | PASS |
| primary_key | issuer: primary key unique | 8 | 0 | 0 | 0 | 0 | PASS |
| id_format | issuer: issuer_id format | 8 | 0 | 0 | 0 | 0 | PASS |
| enum_and_required | issuer.issuer_id: required/allowed values | 8 | 0 | 0 | 0 | 0 | PASS |
| enum_and_required | issuer.name: required/allowed values | 8 | 0 | 0 | 0 | 0 | PASS |
| enum_and_required | issuer.status: required/allowed values | 8 | 0 | 0 | 0 | 0 | PASS |
| enum_and_required | issuer.valid_from: required/allowed values | 8 | 0 | 0 | 0 | 0 | PASS |
| primary_key | issuer_key: primary key unique | 9 | 0 | 0 | 0 | 0 | PASS |
| id_format | issuer_key: key_id format | 9 | 0 | 0 | 0 | 0 | PASS |
| enum_and_required | issuer_key.key_id: required/allowed values | 9 | 0 | 0 | 0 | 0 | PASS |
| enum_and_required | issuer_key.issuer_id: required/allowed values | 9 | 0 | 0 | 0 | 0 | PASS |
| enum_and_required | issuer_key.algorithm: required/allowed values | 9 | 0 | 0 | 0 | 0 | PASS |
| enum_and_required | issuer_key.public_key_b64: required/allowed values | 9 | 0 | 0 | 0 | 0 | PASS |
| enum_and_required | issuer_key.valid_from: required/allowed values | 9 | 0 | 0 | 0 | 0 | PASS |
| enum_and_required | issuer_key.status: required/allowed values | 9 | 0 | 0 | 0 | 0 | PASS |
| primary_key | course: primary key unique | 1000 | 0 | 0 | 0 | 0 | PASS |
| id_format | course: course_id format | 1000 | 0 | 0 | 0 | 0 | PASS |
| enum_and_required | course.course_id: required/allowed values | 1000 | 0 | 0 | 0 | 0 | PASS |
| enum_and_required | course.title: required/allowed values | 1000 | 0 | 0 | 0 | 0 | PASS |
| enum_and_required | course.category: required/allowed values | 1000 | 0 | 0 | 0 | 0 | PASS |
| enum_and_required | course.level: required/allowed values | 1000 | 0 | 0 | 0 | 0 | PASS |
| enum_and_required | course.credit_hours: required/allowed values | 1000 | 0 | 0 | 0 | 0 | PASS |
| enum_and_required | course.pass_mark: required/allowed values | 1000 | 0 | 0 | 0 | 0 | PASS |
| enum_and_required | course.max_attempts: required/allowed values | 1000 | 0 | 0 | 0 | 0 | PASS |
| enum_and_required | course.instructor_id: required/allowed values | 1000 | 0 | 0 | 0 | 0 | PASS |
| enum_and_required | course.status: required/allowed values | 1000 | 0 | 0 | 0 | 0 | PASS |
| enum_and_required | course.created_at: required/allowed values | 1000 | 0 | 0 | 0 | 0 | PASS |
| primary_key | credential_rule: primary key unique | 142 | 0 | 0 | 0 | 0 | PASS |
| id_format | credential_rule: rule_id format | 142 | 0 | 0 | 0 | 0 | PASS |
| enum_and_required | credential_rule.rule_id: required/allowed values | 142 | 0 | 0 | 0 | 0 | PASS |
| enum_and_required | credential_rule.title: required/allowed values | 142 | 0 | 0 | 0 | 0 | PASS |
| enum_and_required | credential_rule.credential_type: required/allowed values | 142 | 0 | 0 | 0 | 0 | PASS |
| enum_and_required | credential_rule.version: required/allowed values | 142 | 0 | 0 | 0 | 0 | PASS |
| enum_and_required | credential_rule.min_courses_required: required/allowed values | 142 | 0 | 0 | 0 | 0 | PASS |
| enum_and_required | credential_rule.min_avg_score: required/allowed values | 142 | 0 | 0 | 0 | 0 | PASS |
| enum_and_required | credential_rule.min_course_score: required/allowed values | 142 | 0 | 0 | 0 | 0 | PASS |
| enum_and_required | credential_rule.effective_from: required/allowed values | 142 | 0 | 0 | 0 | 0 | PASS |
| enum_and_required | credential_rule.status: required/allowed values | 142 | 0 | 0 | 0 | 0 | PASS |
| enum_and_required | credential_rule.created_at: required/allowed values | 142 | 0 | 0 | 0 | 0 | PASS |
| primary_key | credential_rule_course: primary key unique | 528 | 0 | 0 | 0 | 0 | PASS |
| enum_and_required | credential_rule_course.rule_id: required/allowed values | 528 | 0 | 0 | 0 | 0 | PASS |
| enum_and_required | credential_rule_course.course_id: required/allowed values | 528 | 0 | 0 | 0 | 0 | PASS |
| enum_and_required | credential_rule_course.is_mandatory: required/allowed values | 528 | 0 | 0 | 0 | 0 | PASS |
| primary_key | rule_issuer_assignment: primary key unique | 204 | 0 | 0 | 0 | 0 | PASS |
| id_format | rule_issuer_assignment: assignment_id format | 204 | 0 | 0 | 0 | 0 | PASS |
| enum_and_required | rule_issuer_assignment.assignment_id: required/allowed values | 204 | 0 | 0 | 0 | 0 | PASS |
| enum_and_required | rule_issuer_assignment.rule_id: required/allowed values | 204 | 0 | 0 | 0 | 0 | PASS |
| enum_and_required | rule_issuer_assignment.issuer_id: required/allowed values | 204 | 0 | 0 | 0 | 0 | PASS |
| enum_and_required | rule_issuer_assignment.effective_from: required/allowed values | 204 | 0 | 0 | 0 | 0 | PASS |
| primary_key | completion_record: primary key unique | 77747 | 0 | 0 | 0 | 0 | PASS |
| id_format | completion_record: completion_id format | 77747 | 0 | 0 | 0 | 0 | PASS |
| enum_and_required | completion_record.completion_id: required/allowed values | 77747 | 0 | 0 | 0 | 0 | PASS |
| enum_and_required | completion_record.learner_id: required/allowed values | 77747 | 0 | 0 | 0 | 0 | PASS |
| enum_and_required | completion_record.course_id: required/allowed values | 77747 | 0 | 0 | 0 | 0 | PASS |
| enum_and_required | completion_record.enrolled_at: required/allowed values | 77747 | 0 | 0 | 0 | 0 | PASS |
| enum_and_required | completion_record.progress_pct: required/allowed values | 77747 | 0 | 0 | 0 | 0 | PASS |
| enum_and_required | completion_record.status: required/allowed values | 77747 | 0 | 0 | 0 | 0 | PASS |
| enum_and_required | completion_record.attempts_used: required/allowed values | 77747 | 0 | 0 | 0 | 0 | PASS |
| primary_key | assessment_attempt: primary key unique | 79564 | 0 | 0 | 0 | 0 | PASS |
| id_format | assessment_attempt: attempt_id format | 79564 | 0 | 0 | 0 | 0 | PASS |
| enum_and_required | assessment_attempt.attempt_id: required/allowed values | 79564 | 0 | 0 | 0 | 0 | PASS |
| enum_and_required | assessment_attempt.completion_id: required/allowed values | 79564 | 0 | 0 | 0 | 0 | PASS |
| enum_and_required | assessment_attempt.attempt_no: required/allowed values | 79564 | 0 | 0 | 0 | 0 | PASS |
| enum_and_required | assessment_attempt.score: required/allowed values | 79564 | 0 | 0 | 0 | 0 | PASS |
| enum_and_required | assessment_attempt.passed: required/allowed values | 79564 | 0 | 0 | 0 | 0 | PASS |
| enum_and_required | assessment_attempt.attempted_at: required/allowed values | 79564 | 0 | 0 | 0 | 0 | PASS |
| primary_key | credential: primary key unique | 10008 | 8 | 8 | 0 | 0 | PASS |
| id_format | credential: credential_id format | 10008 | 0 | 0 | 0 | 0 | PASS |
| enum_and_required | credential.credential_id: required/allowed values | 10008 | 0 | 0 | 0 | 0 | PASS |
| enum_and_required | credential.learner_id: required/allowed values | 10008 | 0 | 0 | 0 | 0 | PASS |
| enum_and_required | credential.rule_id: required/allowed values | 10008 | 0 | 0 | 0 | 0 | PASS |
| enum_and_required | credential.issuer_id: required/allowed values | 10008 | 0 | 0 | 0 | 0 | PASS |
| enum_and_required | credential.key_id: required/allowed values | 10008 | 0 | 0 | 0 | 0 | PASS |
| enum_and_required | credential.issued_at: required/allowed values | 10008 | 0 | 0 | 0 | 0 | PASS |
| enum_and_required | credential.status: required/allowed values | 10008 | 0 | 0 | 0 | 0 | PASS |
| enum_and_required | credential.payload_json: required/allowed values | 10008 | 0 | 0 | 0 | 0 | PASS |
| enum_and_required | credential.payload_hash: required/allowed values | 10008 | 0 | 0 | 0 | 0 | PASS |
| enum_and_required | credential.signature_b64: required/allowed values | 10008 | 0 | 0 | 0 | 0 | PASS |
| primary_key | credential_completion: primary key unique | 36442 | 0 | 0 | 0 | 0 | PASS |
| enum_and_required | credential_completion.credential_id: required/allowed values | 36442 | 0 | 0 | 0 | 0 | PASS |
| enum_and_required | credential_completion.completion_id: required/allowed values | 36442 | 0 | 0 | 0 | 0 | PASS |
| primary_key | revocation: primary key unique | 599 | 0 | 0 | 0 | 0 | PASS |
| id_format | revocation: revocation_id format | 599 | 0 | 0 | 0 | 0 | PASS |
| enum_and_required | revocation.revocation_id: required/allowed values | 599 | 0 | 0 | 0 | 0 | PASS |
| enum_and_required | revocation.credential_id: required/allowed values | 599 | 0 | 0 | 0 | 0 | PASS |
| enum_and_required | revocation.seq: required/allowed values | 599 | 0 | 0 | 0 | 0 | PASS |
| enum_and_required | revocation.reason_code: required/allowed values | 599 | 0 | 0 | 0 | 0 | PASS |
| enum_and_required | revocation.effective_at: required/allowed values | 599 | 0 | 0 | 0 | 0 | PASS |
| primary_key | verification_request: primary key unique | 5000 | 0 | 0 | 0 | 0 | PASS |
| id_format | verification_request: verification_id format | 5000 | 0 | 0 | 0 | 0 | PASS |
| enum_and_required | verification_request.verification_id: required/allowed values | 5000 | 0 | 0 | 0 | 0 | PASS |
| enum_and_required | verification_request.presented_credential_id: required/allowed values | 5000 | 0 | 0 | 0 | 0 | PASS |
| enum_and_required | verification_request.requested_at: required/allowed values | 5000 | 0 | 0 | 0 | 0 | PASS |
| enum_and_required | verification_request.channel: required/allowed values | 5000 | 0 | 0 | 0 | 0 | PASS |
| enum_and_required | verification_request.requester_type: required/allowed values | 5000 | 0 | 0 | 0 | 0 | PASS |
| enum_and_required | verification_request.result_status: required/allowed values | 5000 | 0 | 0 | 0 | 0 | PASS |
| enum_and_required | verification_request.identity_status: required/allowed values | 5000 | 0 | 0 | 0 | 0 | PASS |
| enum_and_required | verification_request.integrity_ok: required/allowed values | 5000 | 0 | 0 | 0 | 0 | PASS |
| primary_key | audit_event: primary key unique | 89641 | 0 | 0 | 0 | 0 | PASS |
| id_format | audit_event: event_id format | 89641 | 0 | 0 | 0 | 0 | PASS |
| enum_and_required | audit_event.event_id: required/allowed values | 89641 | 0 | 0 | 0 | 0 | PASS |
| enum_and_required | audit_event.seq: required/allowed values | 89641 | 0 | 0 | 0 | 0 | PASS |
| enum_and_required | audit_event.occurred_at: required/allowed values | 89641 | 0 | 0 | 0 | 0 | PASS |
| enum_and_required | audit_event.actor_type: required/allowed values | 89641 | 0 | 0 | 0 | 0 | PASS |
| enum_and_required | audit_event.action: required/allowed values | 89641 | 0 | 0 | 0 | 0 | PASS |
| enum_and_required | audit_event.entity_type: required/allowed values | 89641 | 0 | 0 | 0 | 0 | PASS |
| enum_and_required | audit_event.entity_id: required/allowed values | 89641 | 0 | 0 | 0 | 0 | PASS |
| enum_and_required | audit_event.details_json: required/allowed values | 89641 | 0 | 0 | 0 | 0 | PASS |
| enum_and_required | audit_event.prev_hash: required/allowed values | 89641 | 0 | 0 | 0 | 0 | PASS |
| enum_and_required | audit_event.event_hash: required/allowed values | 89641 | 0 | 0 | 0 | 0 | PASS |
| foreign_key | app_user.learner_id -> learner | 370 | 0 | 0 | 0 | 0 | PASS |
| foreign_key | app_user.instructor_id -> instructor | 370 | 0 | 0 | 0 | 0 | PASS |
| foreign_key | issuer.successor_issuer_id -> issuer | 8 | 0 | 0 | 0 | 0 | PASS |
| foreign_key | issuer_key.issuer_id -> issuer | 9 | 0 | 0 | 0 | 0 | PASS |
| foreign_key | course.instructor_id -> instructor | 1000 | 0 | 0 | 0 | 0 | PASS |
| foreign_key | credential_rule_course.rule_id -> credential_rule | 528 | 0 | 0 | 0 | 0 | PASS |
| foreign_key | credential_rule_course.course_id -> course | 528 | 0 | 0 | 0 | 0 | PASS |
| foreign_key | rule_issuer_assignment.rule_id -> credential_rule | 204 | 0 | 0 | 0 | 0 | PASS |
| foreign_key | rule_issuer_assignment.issuer_id -> issuer | 204 | 0 | 0 | 0 | 0 | PASS |
| foreign_key | completion_record.learner_id -> learner | 77747 | 0 | 0 | 0 | 0 | PASS |
| foreign_key | completion_record.course_id -> course | 77747 | 0 | 0 | 0 | 0 | PASS |
| foreign_key | assessment_attempt.completion_id -> completion_record | 79564 | 0 | 0 | 0 | 0 | PASS |
| foreign_key | credential.learner_id -> learner | 10008 | 0 | 0 | 0 | 0 | PASS |
| foreign_key | credential.rule_id -> credential_rule | 10008 | 0 | 0 | 0 | 0 | PASS |
| foreign_key | credential.issuer_id -> issuer | 10008 | 0 | 0 | 0 | 0 | PASS |
| foreign_key | credential.key_id -> issuer_key | 10008 | 0 | 0 | 0 | 0 | PASS |
| foreign_key | credential.issued_by -> app_user | 10008 | 0 | 0 | 0 | 0 | PASS |
| foreign_key | credential_completion.credential_id -> credential | 36442 | 0 | 0 | 0 | 0 | PASS |
| foreign_key | credential_completion.completion_id -> completion_record | 36442 | 0 | 0 | 0 | 0 | PASS |
| foreign_key | revocation.credential_id -> credential | 599 | 0 | 0 | 0 | 0 | PASS |
| foreign_key | revocation.revoked_by -> app_user | 599 | 0 | 0 | 0 | 0 | PASS |
| foreign_key | verification_request.credential_id -> credential | 5000 | 0 | 0 | 0 | 0 | PASS |
| foreign_key | verification_request.processed_by -> app_user | 5000 | 0 | 0 | 0 | 0 | PASS |
| foreign_key | audit_event.actor_user_id -> app_user | 89641 | 0 | 0 | 0 | 0 | PASS |
| foreign_key | audit_event.entity_id resolves | 89641 | 0 | 0 | 0 | 0 | PASS |
| duplicates | learner.email unique | 20000 | 0 | 0 | 0 | 0 | PASS |
| duplicates | one active credential per learner and rule | 9401 | 0 | 0 | 0 | 0 | PASS |
| duplicates | completion unique per learner and course | 77747 | 0 | 0 | 0 | 0 | PASS |
| date_ordering | rule.created_at <= effective_from | 142 | 0 | 0 | 0 | 0 | PASS |
| date_ordering | rule.effective_to > effective_from | 142 | 0 | 0 | 0 | 0 | PASS |
| date_ordering | completion enrolled <= finalized | 77747 | 0 | 0 | 0 | 0 | PASS |
| date_ordering | enrolled after learner registered | 77747 | 0 | 0 | 0 | 0 | PASS |
| date_ordering | rule_issuer_assignment.effective_to > effective_from | 204 | 0 | 0 | 0 | 0 | PASS |
| date_ordering | issuer.valid_to > valid_from | 8 | 0 | 0 | 0 | 0 | PASS |
| date_ordering | issuer_key.valid_to > valid_from | 9 | 0 | 0 | 0 | 0 | PASS |
| date_ordering | credential.expires_at > issued_at | 10008 | 0 | 0 | 0 | 0 | PASS |
| date_ordering | revocation after issuance | 599 | 0 | 0 | 0 | 0 | PASS |
| date_ordering | attempts strictly increasing in time | 72099 | 0 | 0 | 0 | 0 | PASS |
| date_ordering | credential issued after every qualifying completion | 10000 | 30 | 30 | 0 | 0 | PASS |
| date_ordering | verification not earlier than issuance | 5000 | 0 | 0 | 0 | 0 | PASS |
| reconciliation | completion status/attempts/score derived from attempts | 77747 | 0 | 0 | 0 | 0 | PASS |
| reconciliation | attempt numbering and limits | 77747 | 0 | 0 | 0 | 0 | PASS |
| reconciliation | attempt pass flags | 77747 | 0 | 0 | 0 | 0 | PASS |
| reconciliation | rule thresholds consistent with course list | 142 | 0 | 0 | 0 | 0 | PASS |
| reconciliation | credential expiry = issued_at + validity_months | 10000 | 0 | 0 | 0 | 0 | PASS |
| business_rules | issuance requirements satisfied | 10000 | 0 | 0 | 0 | 0 | PASS |
| business_rules | bridge completions belong to credential holder | 10000 | 0 | 0 | 0 | 0 | PASS |
| business_rules | issuer matches effective assignment | 10000 | 0 | 0 | 0 | 0 | PASS |
| business_rules | signing key valid at issuance | 10000 | 0 | 0 | 0 | 0 | PASS |
| lifecycle | one open issuer assignment per rule | 142 | 0 | 0 | 0 | 0 | PASS |
| lifecycle | retired issuers have successors | 8 | 0 | 0 | 0 | 0 | PASS |
| integrity | payload hash and signature verify | 10008 | 20 | 20 | 0 | 0 | PASS |
| lifecycle | credential.status matches revocation records | 10000 | 0 | 0 | 0 | 0 | PASS |
| lifecycle | revocation sequence contiguous | 599 | 0 | 0 | 0 | 0 | PASS |
| lifecycle | revoked credential never verifies as active after revocation | 5000 | 25 | 25 | 0 | 0 | PASS |
| lifecycle | tampered credential never verifies as valid | 5000 | 20 | 20 | 0 | 0 | PASS |
| lifecycle | recorded result equals recomputed result | 5000 | 45 | 45 | 0 | 0 | PASS |
| lifecycle | recorded identity status reproducible | 5000 | 0 | 0 | 0 | 0 | PASS |
| business_rules | identity never matched on name alone | 5000 | 0 | 0 | 0 | 0 | PASS |
| audit | audit hash chain intact | 89641 | 0 | 0 | 0 | 0 | PASS |
| audit | audit timestamps non-decreasing | 89641 | 0 | 0 | 0 | 0 | PASS |
| audit | issuance audit hash equals stored payload hash | 10008 | 28 | 28 | 0 | 0 | PASS |
| audit | every credential has exactly one issuance event | 10000 | 0 | 0 | 0 | 0 | PASS |
| audit | finalised completions audited once | 77747 | 0 | 0 | 0 | 0 | PASS |

## Dataset profile

```json
{
  "learners_sharing_a_name": 1468,
  "name_groups_with_duplicates": 715,
  "learners_sharing_name_and_birthdate": 56,
  "completion_status_counts": {
    "completed": 71062,
    "in_progress": 3858,
    "withdrawn": 1966,
    "failed": 861
  },
  "credential_status_counts": {
    "active": 9401,
    "revoked": 599
  },
  "verification_result_counts": {
    "valid": 4197,
    "not_found": 153,
    "tampered": 198,
    "revoked": 378,
    "expired": 74
  },
  "verification_identity_counts": {
    "matched": 1319,
    "mismatch": 400,
    "not_requested": 2862,
    "insufficient_identifiers": 419
  },
  "retired_issuers": 2,
  "rotated_keys": 3,
  "revocation_reason_counts": {
    "issued_in_error": 150,
    "academic_misconduct": 118,
    "learner_request": 146,
    "fraud": 91,
    "rule_change": 94
  },
  "row_counts": {
    "learner": 20000,
    "instructor": 62,
    "app_user": 370,
    "issuer": 8,
    "issuer_key": 9,
    "course": 1000,
    "credential_rule": 142,
    "credential_rule_course": 528,
    "rule_issuer_assignment": 204,
    "completion_record": 77747,
    "assessment_attempt": 79564,
    "credential": 10008,
    "credential_completion": 36442,
    "revocation": 599,
    "verification_request": 5000,
    "audit_event": 89641
  }
}
```
