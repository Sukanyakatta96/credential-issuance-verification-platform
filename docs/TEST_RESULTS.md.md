# Test Execution Results

Environment: Python 3.12.3, Flask 3.1, SQLite 3.45, Node 22, Linux. The recorded run had no network access and no full browser available. All figures below are from the final recorded automated run on the delivered code; they are not a claim that the UI was visually inspected in a browser or that production deployment was tested.

## 1. Automated tests (`./scripts/run_tests.sh`, hermetic)

| Stage | Result |
|---|---|
| Python unit + API + data-generation tests (`unittest`) | **91 run, 0 failures, 0 errors** (domain 22, API 55, data generation 14; about 45–50 s, most of it password hashing) |
| Fresh starter dataset generation + validation | **195/195 checks passed** |
| Starter reproducibility (two regenerations vs primary) | **identical** (41 files) |
| Frontend integration (`tests/frontend_smoke.mjs`) against a live server | **84/84 checks passed**; server log contained no HTTP 500 |

What the frontend suite does: it loads the real ES modules in Node with a small DOM shim and the real HTTP API; for five roles it opens every route (52 page loads including detail pages), checks that role-forbidden pages are blocked, submits forms (login with bad/good password, public verifier, register learner, create course with validation errors, create user, change password, instructor progress and assessment), opens modals, runs issuance → verify → revoke → public re-verification, rotates an issuer key through the confirmation dialog, and runs the integrity scan, ground-truth evaluation and audit chain verification.

## 2. Full-scale run (20,000 / 1,000 / 10,000 / 5,000)

Commands: `python -m datagen.generate --scale full --validate --check-reproducibility`, `python -m app.cli seed --data-dir data/full --reset`.

| Measure | Result |
|---|---|
| Generation | 321,326 rows in about 10 s |
| Validation | **195/195 checks passed**; 103 labelled anomalies, all found by their detecting checks, no unexpected violations (`VALIDATION_REPORT.md`) |
| Reproducibility | **identical across 2 regenerations** (`reproducibility_report_full.json`) |
| Load into SQLite | about 5 s; 0 foreign-key violations; 8 duplicate-ID rows rejected by the primary key and recorded in `import_rejection` |
| Dashboard / eligibility queue | 0.5 s each |
| Credential, learner, completion, verification, audit list endpoints | ≤ 0.05 s |
| Audit hash chain (89,641 events) | verified in 0.44 s |
| Integrity scan (10,000 credentials, 5,000 verifications) | 2.3 s |

### Detection quality against ground truth (`/api/integrity/evaluation`)

| Issue type | Labelled | True positives | False positives | False negatives |
|---|---|---|---|---|
| credential issued before completion | 30 | 30 | 0 | 0 |
| duplicate credential ID | 8 | 8 | 0 | 0 |
| revoked credential verified as active | 25 | 25 | 0 | 0 |
| payload hash altered | 20 | 20 | 0 | 0 |
| altered payload hash not detected (verification) | 20 | 20 | 0 | 0 |

Verification engine vs the independent expected decisions for all 5,000 requests: result accuracy **100%**, identity accuracy **100%**. The *recorded* results are 99.1% correct — the 45 wrong ones are exactly the 25 + 20 injected failures.

## 3. Defects found and fixed during testing

| Found by | Defect | Fix |
|---|---|---|
| API test | A check and a revocation in the same second made a stored "valid" result replay as "revoked" (non-reproducible) | Revocation effective time placed after prior checks; a check's evaluation time is never earlier than an existing revocation; regression test added |
| API test | Rotating/retiring within one second of creation future-dated the new key/assignment, briefly leaving no usable signing key | Reject with `409 TOO_SOON` instead of future-dating |
| Full-scale load | Draft rules going live after the issuer change were assigned to the retired issuer (negative-length window) — rejected by a DB check | Generator assigns the successor directly; validator gained window checks for assignments, issuers and keys |
| Negative validator test | Validator crashed (`KeyError`) on a dangling foreign key | Dependent checks now run only on rows whose parents resolve |
| Security review | Spreadsheet formula injection through exported `requester_org` | Cells starting with `= + - @` are prefixed with `'`; test added |
| Frontend harness | False positive on hidden form error banners; hang on awaiting a confirmation dialog | Harness fixed (the application was correct) |

## 4. Not verified / remaining manual checks

* **Real-browser UI review:** visual layout, light/dark appearance, keyboard navigation, accessibility and responsive behaviour were not tested in a full browser. The Node DOM-shim suite is a functional integration test, not a visual browser test.
* **Production deployment:** a production WSGI server behind TLS, persistent hosting storage, proxy configuration and deployment operations were not exercised.
* **Concurrency and scale-out:** concurrent multi-process load and high-write workloads were not tested. SQLite permits one writer at a time.

These are limitations of the recorded test environment, not failed automated tests. Complete the browser review and deployment checks before presenting the application as production-ready.
