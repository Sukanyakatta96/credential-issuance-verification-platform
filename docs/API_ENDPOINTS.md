# API Endpoint Reference (generated)

Generated from the Flask URL map and the `require_roles` decorators. See `docs/API.md` for request and response conventions.

| Method | Path | Access |
|---|---|---|
| GET | `/api/audit` | academic_admin, support_staff, platform_admin |
| GET | `/api/audit/actions` | academic_admin, support_staff, platform_admin |
| GET | `/api/audit/verify-chain` | academic_admin, support_staff, platform_admin |
| POST | `/api/auth/change-password` | any signed-in user |
| POST | `/api/auth/login` | public |
| GET | `/api/auth/me` | any signed-in user |
| GET | `/api/completions` | any signed-in user |
| POST | `/api/completions` | academic_admin, platform_admin |
| GET | `/api/completions/<completion_id>` | any signed-in user |
| POST | `/api/completions/<completion_id>/assessments` | instructor, academic_admin, platform_admin |
| POST | `/api/completions/<completion_id>/progress` | instructor, academic_admin, platform_admin |
| POST | `/api/completions/<completion_id>/withdraw` | learner, academic_admin, platform_admin |
| GET | `/api/courses` | any signed-in user |
| POST | `/api/courses` | academic_admin, platform_admin |
| GET | `/api/courses/<course_id>` | any signed-in user |
| PATCH | `/api/courses/<course_id>` | academic_admin, platform_admin |
| GET | `/api/credentials` | any signed-in user |
| POST | `/api/credentials` | academic_admin, platform_admin |
| GET | `/api/credentials/<credential_id>` | any signed-in user |
| POST | `/api/credentials/<credential_id>/revoke` | academic_admin, platform_admin |
| GET | `/api/eligibility` | academic_admin, support_staff, platform_admin |
| GET | `/api/eligibility/pending` | academic_admin, support_staff, platform_admin |
| GET | `/api/health` | public |
| GET | `/api/integrity/evaluation` | platform_admin, academic_admin |
| GET | `/api/integrity/import-rejections` | platform_admin, academic_admin |
| GET | `/api/integrity/scan` | platform_admin, academic_admin |
| GET | `/api/issuers` | academic_admin, support_staff, platform_admin |
| POST | `/api/issuers` | platform_admin |
| GET | `/api/issuers/<issuer_id>` | academic_admin, support_staff, platform_admin |
| POST | `/api/issuers/<issuer_id>/retire` | platform_admin |
| POST | `/api/issuers/<issuer_id>/rotate-key` | platform_admin |
| GET | `/api/learners` | academic_admin, support_staff, platform_admin |
| POST | `/api/learners` | academic_admin, platform_admin |
| GET | `/api/learners/<learner_id>` | any signed-in user |
| PATCH | `/api/learners/<learner_id>` | academic_admin, platform_admin |
| GET | `/api/meta/course-options` | any signed-in user |
| GET | `/api/public/credentials/<credential_id>/document` | public |
| GET | `/api/public/issuers/<issuer_id>/keys` | public |
| POST | `/api/public/verify` | public |
| GET | `/api/reports/dashboard` | academic_admin, support_staff, platform_admin |
| GET | `/api/reports/export/<name>` | academic_admin, support_staff, platform_admin |
| GET | `/api/reports/me` | learner, instructor |
| GET | `/api/revocations` | academic_admin, support_staff, platform_admin |
| GET | `/api/rules` | academic_admin, support_staff, platform_admin, instructor |
| POST | `/api/rules` | academic_admin, platform_admin |
| GET | `/api/rules/<rule_id>` | academic_admin, support_staff, platform_admin, instructor |
| POST | `/api/rules/<rule_id>/issuer` | academic_admin, platform_admin |
| POST | `/api/rules/<rule_id>/retire` | academic_admin, platform_admin |
| GET | `/api/users` | platform_admin |
| POST | `/api/users` | platform_admin |
| PATCH | `/api/users/<user_id>` | platform_admin |
| POST | `/api/users/<user_id>/reset-password` | platform_admin |
| GET | `/api/verifications` | learner, academic_admin, support_staff, platform_admin |
| POST | `/api/verifications` | support_staff, academic_admin, platform_admin |
| GET | `/api/verifications/<verification_id>` | academic_admin, support_staff, platform_admin |
| POST | `/api/verifications/<verification_id>/replay` | academic_admin, support_staff, platform_admin |
