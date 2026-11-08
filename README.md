# Credential Issuance, Revocation & Verification Platform

A complete, runnable application for the workflow **"issue credentials after completion requirements are met, and support revocation and third-party verification"**: Flask API, SQLite database with migrations, single-page web UI, a deterministic synthetic-data generator, a dataset validator, and automated tests.

| Layer | Technology |
|---|---|
| Backend | Python 3.12, Flask 3, raw SQL over `sqlite3` (WAL, foreign keys on), SQL-file migrations |
| Auth | Salted password hashes (Werkzeug), signed JWT access tokens (PyJWT), role-based access control, login lockout |
| Credential integrity | SHA-256 payload hash + **Ed25519** signature (`cryptography`); public keys are published so third parties can verify offline |
| Frontend | Vanilla ES-module single-page app served by Flask (no build step, no CDN, strict CSP) |
| Data | `datagen` package: seeded generator, CSV/JSON/SQL export, validator, ground truth, reproducibility check |
| Tests | `unittest` (91 tests), a dataset validation suite (195 checks), and a Node frontend integration suite (84 checks) |

The application uses a small Python dependency set and a framework-free frontend. The browser UI is served directly by Flask as native JavaScript ES modules, so no frontend build step or CDN is required.

## Quick start

Requires Python 3.10 or later (developed and tested with Python 3.12). Node.js 18 or later is required only for the frontend integration tests.

### Windows (PowerShell)

Run these commands from the project root:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python scripts/init_env.py

python -m datagen.generate --scale starter --validate
python -m app.cli seed --data-dir data/starter --reset
python -m app.cli demo-users
python -m app.cli serve
```

If PowerShell blocks virtual-environment activation, run this once in the current terminal and retry activation:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

Open <http://127.0.0.1:5000>. The `demo-users` command selects one account for each role and sets a password. Use `--password` or `DEMO_USER_PASSWORD` to choose a password; otherwise a random password is printed once. Demo credentials are for local testing only.

### macOS / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
python3 scripts/init_env.py

python3 -m datagen.generate --scale starter --validate
python3 -m app.cli seed --data-dir data/starter --reset
python3 -m app.cli demo-users
python3 -m app.cli serve
```

### Full dataset

For the full assignment volume (20,000 learners, 1,000 courses, 10,000 distinct credentials and 5,000 verification requests):

```bash
python3 -m datagen.generate --scale full --validate --check-reproducibility
python3 -m app.cli seed --data-dir data/full --reset
python3 -m app.cli demo-users
python3 -m app.cli serve
```

On Windows PowerShell, replace `python3` with `python` in these commands. Set `GROUND_TRUTH_DIR=data/full/ground_truth` (or `data/starter/ground_truth`) in `.env` to enable the *Integrity & evaluation* page's comparison with ground truth.

> **Signing-key requirement:** issuer signing keys are derived from `SIGNING_MASTER_SECRET`. Generate the dataset and run the app with the same secret. Both commands read `.env`. If the secrets differ, issuance is rejected with `SIGNING_KEY_MISMATCH`; verification of existing credentials can still work because public keys are stored with the data. The datasets shipped under `data/` were generated with a throw-away demo secret, so regenerate the dataset after creating your own `.env` before testing issuance.

### Running the automated tests

The complete test script is `scripts/run_tests.sh`. It requires Bash, Node.js 18 or later, and `curl` in addition to Python. On Windows, run it from Git Bash or WSL (not directly as a PowerShell script). From macOS/Linux/Git Bash/WSL:

```bash
./scripts/run_tests.sh
```

The Makefile shortcut `make test` also requires `make` to be installed. The Python unit/API/data-generation tests can be run separately with:

```bash
python -m unittest discover -s tests -p "test_*.py" -v
```

The standalone Python command does not run the frontend integration suite. The complete script uses a temporary database, generated secrets and a temporary server; it does not overwrite the normal demo database.

## What you can do in the UI

| Role | Capabilities |
|---|---|
| **Learner** | See own credentials, course progress and who verified their credentials; withdraw from a course; download the signed record; share the public verifier link |
| **Instructor** | See own courses and enrolments; record progress and assessment attempts (only for courses they teach) |
| **Academic administrator** | Register learners, create courses and credential rules, enroll learners, review the eligibility queue and **issue** credentials, **revoke** credentials, change a rule's issuer, run integrity scans and evaluation |
| **Support staff** | Look up learners and credentials (including duplicate-name warnings), run verifications on behalf of a requester, replay past verifications, read audit and revocation history |
| **Platform administrator** | Everything above plus issuer management (register, rotate keys, retire with successor) and user management (create, deactivate, reset passwords) |
| **Third party (no login)** | `#/verify` — check a credential ID, optionally with the holder's name, email, date of birth and the document hash |

## How the key rules work

* **Issuance** happens only through `POST /api/credentials`, which re-evaluates the rule against the learner's completion records inside a transaction (`app/domain/eligibility.py`): rule active and effective, learner active, all mandatory courses completed, enough courses counted (each at or above the per-course floor), average at or above the threshold, no active credential already held, no earlier fraud/misconduct revocation. A failed check returns each check with an explanation (HTTP 422).
* **Completion status is derived**, never typed in: attempts are append-only, and status, attempt count, best score and finalisation time are recomputed from them (`app/domain/completion.py`).
* **Verification** is a pure function of stored data, the evaluation time and the claims presented (`app/domain/verification.py`). Precedence: `not_found > tampered > revoked > expired > valid`. Every check is stored; `POST /api/verifications/<id>/replay` re-runs it at the original time to prove reproducibility.
* **Identity matching never uses a name alone.** A name without email or date of birth returns `insufficient_identifiers`; any supplied identifier that disagrees returns `mismatch`; holder names are masked in public results until identity is matched.
* **Revocation** is permanent and append-only (`REV-<credential-id>-01`), takes effect at `effective_at`, and verification always checks the current revocation state.
* **History is not overwritten**: database triggers make audit events, revocations, verification requests and assessment attempts append-only, freeze credential issuance fields, allow only `active → revoked`, and freeze finalised completions. Audit events are SHA-256 hash-chained and the chain can be verified from the UI/API.

## Synthetic data

`python -m datagen.generate` is one generator for every scale (`--scale starter|full`, or explicit `--learners/--courses/--credentials/--verifications`). Output in `data/<scale>/`:

```
csv/            one file per table (also json/ and sql/)
sql/schema.sql  sql/seed.sql
ground_truth/   ground_truth.csv|json, ground_truth_expected_decisions.csv|json   (never read by the app's detectors)
data_dictionary.json   manifest.json (command, seed, row counts, SHA-256 of every file)   source_manifest.json
validation_report.md|json   reproducibility_report.json
```

* Master data first (instructors, users, issuers + keys, courses, rules + bridge + issuer assignments, learners), then enrolments, assessment attempts and completions, then credentials, revocations, verification requests and the audit chain. Every foreign key points at an existing parent.
* Credential eligibility is decided by the same `evaluate_eligibility` function the application uses; verification outcomes and labels are derived by an independent re-statement of the rules (`datagen/outcomes.py`), not assigned randomly.
* Natural variation: duplicate names (some sharing a date of birth), incomplete / failed / withdrawn courses, revoked and expired credentials, two issuers retired and replaced mid-year, one key rotation, retired and draft rules, eligible-but-not-yet-issued learners.
* **Labelled edge cases** (injected after valid baseline data exists, each recorded in `ground_truth`): credential issued before completion (30), duplicate credential ID (8), revoked credential recorded as valid (25), altered payload hash (20), and the undetected-alteration verification for each (20) — at full scale.
* The 8 duplicate-ID rows are present in `credential.csv` (10,008 rows, 10,000 distinct IDs). The database primary key rejects them on load; they are recorded in `import_rejection` and appear in the integrity scan.
* Seed `20261022`; every output file is byte-identical across regenerations (`--check-reproducibility` regenerates twice and compares 41 file checksums).
* No external data is used (`source_manifest.json`). Names come from embedded generic lists; email addresses use reserved `.example` domains.

Evidence: `docs/VALIDATION_REPORT.md` (195 checks on the full dataset), `docs/reproducibility_report_full.json`, and `docs/TEST_RESULTS.md`.

### Reproducibility

Same seed **and** same signing secret ⇒ identical bytes. The shipped `data/starter` and `data/full` were generated with `SIGNING_MASTER_SECRET=dev-only-signing-master-secret-0123456789abcdef` (a throw-away value for synthetic data, not used for anything real). To reproduce their checksums exactly:

```bash
python3 -m datagen.generate --scale full --signing-secret dev-only-signing-master-secret-0123456789abcdef --out /tmp/full
diff <(python3 -c "import json;print(json.load(open('/tmp/full/manifest.json'))['files'])") \
     <(python3 -c "import json;print(json.load(open('data/full/manifest.json'))['files'])")
```

To keep the archive small, the ZIP omits the **full** dataset's `json/` and `sql/` folders (about 25 MB compressed). They are produced by the command above and their checksums are listed in `data/full/manifest.json`. The starter dataset ships in all three formats.

## Project layout

```
app/                Flask application
  api/              HTTP layer (blueprints): auth, public, directory, workflow, admin
  services/         business operations with transactions (issuance, verification, revocation, ...)
  domain/           pure rule logic (eligibility, completion state, verification) — no I/O
  static/           single-page UI (js/, css/)
  crypto.py audit.py security.py db.py ids.py ...
migrations/         SQL schema (ID formats, enums, triggers)
datagen/            generator, exporter, loader, validator, schema_spec (single source for the data dictionary)
tests/              unit, API, data-generation and frontend integration tests
scripts/            init_env, run_tests, generate_docs, package
docs/               ARCHITECTURE, API, API_ENDPOINTS (generated), DATA_DICTIONARY (generated), REQUIREMENTS_CHECKLIST, TEST_RESULTS, VALIDATION_REPORT
```

## Configuration (`.env`)

See `.env.example`. `JWT_SECRET` and `SIGNING_MASTER_SECRET` are required and must not start with `CHANGE_ME`; the app refuses to start otherwise. Other settings: `DATABASE_PATH`, `DATA_DIR`, `GROUND_TRUTH_DIR`, `JWT_TTL_MINUTES`, `PUBLIC_RATE_LIMIT_PER_MINUTE`, `LOGIN_MAX_FAILURES`, `LOGIN_LOCKOUT_SECONDS`, `HOST`, `PORT`.

## Documentation

* `docs/ARCHITECTURE.md` — requirement analysis, design, decisions and assumptions
* `docs/API.md` and generated `docs/API_ENDPOINTS.md` — conventions and every endpoint with its access rule
* `docs/DATA_DICTIONARY.md` — every field, type, allowed values, uniqueness, validation rule, relationships and cardinality
* `docs/REQUIREMENTS_CHECKLIST.md` — requirement → code → test → result
* `docs/TEST_RESULTS.md`, `docs/VALIDATION_REPORT.md`

## Known limitations (read before the demo)

1. **Browser appearance has not been verified automatically.** The frontend integration suite runs the real JavaScript modules against the live API using a Node DOM shim. It does not render pages in a full browser, so visual layout, colours, accessibility and responsive behaviour still require manual browser testing.
2. The Flask development server is used for `serve`. For production use a WSGI server (for example `gunicorn 'app:create_app()'`) behind TLS; that setup was not exercised here. Behind a proxy, configure the client-IP header so rate limits see real addresses.
3. Login lockout and the public rate limit are in-memory, per process, and reset on restart. SQLite allows one writer at a time (fine for this scope, not for high write volume).
4. Access tokens live in `sessionStorage` and are valid until expiry (account deactivation is checked on every request). The strict CSP and the absence of `innerHTML` reduce XSS exposure.
5. Revocation is permanent; there is no reinstatement. A mistaken revocation is handled by issuing a new credential (allowed unless the earlier revocation was for fraud or misconduct).
6. Timestamps have one-second resolution. To keep replays reproducible when a check and a revocation land in the same second, a revocation's effective time is placed just after prior checks and a check's evaluation time is never earlier than an existing revocation, so a stored time can be up to one second ahead of the wall clock in that rare tie.
7. Learner and instructor accounts in the dataset have no password until `demo-users` or an administrator's *Reset password* sets one.
8. The project ZIP is a local build artifact. It is not automatically published to GitHub or deployed to a public URL.
