"""Validates an exported dataset using only the CSV files; ground truth is used afterwards to classify findings."""
import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from app import audit, crypto, ids
from app.domain import issue_types as T
from app.domain.completion import derive_completion_state
from app.domain.eligibility import evaluate_eligibility
from app.timeutil import add_months, to_ts

from .load import read_table
from .outcomes import expected_identity, expected_result
from .schema_spec import ENTITIES, TABLE_ORDER

ID_PATTERNS = {
    "learner": ("learner_id", ids.LEARNER_RE), "course": ("course_id", ids.COURSE_RE),
    "credential": ("credential_id", ids.CREDENTIAL_RE), "verification_request": ("verification_id", ids.VERIFICATION_RE),
    "completion_record": ("completion_id", ids.COMPLETION_RE),
    "instructor": ("instructor_id", re.compile(r"^INS-\d{4}$")), "app_user": ("user_id", re.compile(r"^USR-\d{6}$")),
    "issuer": ("issuer_id", re.compile(r"^ISS-\d{3}$")), "issuer_key": ("key_id", re.compile(r"^KEY-ISS-\d{3}-\d{2}$")),
    "credential_rule": ("rule_id", re.compile(r"^RUL-\d{6}$")),
    "rule_issuer_assignment": ("assignment_id", re.compile(r"^RIA-\d{6}$")),
    "assessment_attempt": ("attempt_id", re.compile(r"^ASM-LRN-\d{6}-CRS-\d{6}-\d{2}$")),
    "revocation": ("revocation_id", re.compile(r"^REV-CRD-\d{4}-\d{6}-\d{2}$")),
    "audit_event": ("event_id", re.compile(r"^AUD-\d{9}$")),
}


class Report:
    def __init__(self, labels):
        self.checks = []
        self.labels = defaultdict(set)
        for row in labels:
            self.labels[row["issue_type"]].add(row["entity_id"])

    def add(self, category, name, description, violations, expects=(), total=None):
        violations = set(violations)
        expected = set()
        for issue_type in expects:
            expected |= self.labels.get(issue_type, set())
        unexpected, missed = violations - expected, (expected - violations) if expects else set()
        self.checks.append({
            "category": category, "name": name, "description": description, "records_checked": total,
            "violations": len(violations), "labelled_anomalies_found": len(violations & expected),
            "unexpected_violations": len(unexpected), "labelled_but_not_found": len(missed),
            "status": "PASS" if not unexpected and not missed else "FAIL",
            "unexpected_samples": sorted(unexpected)[:5], "missed_samples": sorted(missed)[:5],
            "expects": list(expects)})


def parse(ts):
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def validate_dataset(data_dir: str) -> dict:
    root = Path(data_dir)
    csv_dir = root / "csv"
    data = {t: read_table(csv_dir, t) for t in TABLE_ORDER}
    gt_path = root / "ground_truth" / "ground_truth.csv"
    labels = []
    if gt_path.is_file():
        import csv
        with gt_path.open(newline="", encoding="utf-8") as handle:
            labels = list(csv.DictReader(handle))
    report = Report(labels)

    # ---- primary keys, ids, enums, required fields
    for table in TABLE_ORDER:
        spec = ENTITIES[table]
        rows = data[table]
        if " + " in spec["pk"]:
            parts = spec["pk"].split(" + ")
            keys = [tuple(r[p] for p in parts) for r in rows]
            dupes = {"|".join(k) for k, n in Counter(keys).items() if n > 1}
        else:
            keys = [r[spec["pk"]] for r in rows]
            dupes = {k for k, n in Counter(keys).items() if n > 1}
        expects = (T.DUPLICATE_CREDENTIAL_ID,) if table == "credential" else ()
        report.add("primary_key", f"{table}: primary key unique", f"No duplicate {spec['pk']} values in {table}.csv",
                   dupes, expects, len(rows))
        if table in ID_PATTERNS:
            column, pattern = ID_PATTERNS[table]
            report.add("id_format", f"{table}: {column} format", f"{column} matches its naming convention",
                       {r[column] for r in rows if not pattern.match(r[column])}, total=len(rows))
        for f in spec["fields"]:
            bad = set()
            for number, r in enumerate(rows, start=1):
                value = r[f["name"]]
                if f["required"] and value is None:
                    bad.add(f"row{number}")
                if f["allowed"] is not None and value is not None and value not in f["allowed"]:
                    bad.add(f"row{number}")
            if f["required"] or f["allowed"] is not None:
                report.add("enum_and_required", f"{table}.{f['name']}: required/allowed values",
                           "Non-null where required and within the allowed set", bad, total=len(rows))

    # ---- foreign keys
    pk_sets = {t: {r[ENTITIES[t]["pk"]] for r in data[t]} for t in TABLE_ORDER if " + " not in ENTITIES[t]["pk"]}
    for table in TABLE_ORDER:
        for column, parent in ENTITIES[table]["foreign_keys"]:
            bad = {f"{r[ENTITIES[table]['pk']] if ' + ' not in ENTITIES[table]['pk'] else r[column]}" for r in data[table]
                   if r[column] is not None and r[column] not in pk_sets[parent]}
            report.add("foreign_key", f"{table}.{column} -> {parent}", "Every reference resolves to an existing parent row",
                       bad, total=len(data[table]))
    report.add("foreign_key", "audit_event.entity_id resolves", "Every audited entity exists",
               {e["event_id"] for e in data["audit_event"]
                if e["entity_type"] in pk_sets and e["entity_id"] not in pk_sets[e["entity_type"]]},
               total=len(data["audit_event"]))

    # Dependent checks run only on rows whose parents resolve; dangling references were reported above.
    for table in TABLE_ORDER:
        foreign = ENTITIES[table]["foreign_keys"]
        if foreign:
            data[table] = [r for r in data[table] if all(r[c] is None or r[c] in pk_sets[p] for c, p in foreign)]
            if " + " not in ENTITIES[table]["pk"]:
                pk_sets[table] = {r[ENTITIES[table]["pk"]] for r in data[table]}

    learners = {r["learner_id"]: r for r in data["learner"]}
    courses = {r["course_id"]: r for r in data["course"]}
    rules = {r["rule_id"]: r for r in data["credential_rule"]}
    completions = {r["completion_id"]: r for r in data["completion_record"]}
    issuers = {r["issuer_id"]: r for r in data["issuer"]}
    keys = {r["key_id"]: r for r in data["issuer_key"]}

    # ---- uniqueness and duplicate detection
    report.add("duplicates", "learner.email unique", "Identity anchor must not repeat",
               {e for e, n in Counter(r["email"] for r in data["learner"]).items() if n > 1}, total=len(learners))
    active_pairs = Counter((c["learner_id"], c["rule_id"]) for c in _unique_first(data["credential"]) if c["status"] == "active")
    report.add("duplicates", "one active credential per learner and rule", "No learner holds two active credentials for a rule",
               {"|".join(k) for k, n in active_pairs.items() if n > 1}, total=len(active_pairs))
    report.add("duplicates", "completion unique per learner and course", "CMP id encodes the pair",
               {r["completion_id"] for r in data["completion_record"]
                if r["completion_id"] != ids.completion_id(r["learner_id"], r["course_id"])}, total=len(completions))

    # ---- date ordering
    def ordering(table, name, description, predicate, key, expects=()):
        rows = data[table]
        report.add("date_ordering", name, description, {key(r) for r in rows if not predicate(r)}, expects, len(rows))
    ordering("credential_rule", "rule.created_at <= effective_from", "Rules are created before they take effect",
             lambda r: r["created_at"] <= r["effective_from"], lambda r: r["rule_id"])
    ordering("credential_rule", "rule.effective_to > effective_from", "Effective window is positive",
             lambda r: r["effective_to"] is None or r["effective_to"] > r["effective_from"], lambda r: r["rule_id"])
    ordering("completion_record", "completion enrolled <= finalized", "Finalisation follows enrolment",
             lambda r: r["finalized_at"] is None or r["finalized_at"] >= r["enrolled_at"], lambda r: r["completion_id"])
    ordering("completion_record", "enrolled after learner registered", "Cannot enrol before registering",
             lambda r: r["enrolled_at"] >= learners[r["learner_id"]]["registered_at"], lambda r: r["completion_id"])
    for table, start, end in (("rule_issuer_assignment", "effective_from", "effective_to"), ("issuer", "valid_from", "valid_to"),
                              ("issuer_key", "valid_from", "valid_to")):
        ordering(table, f"{table}.{end} > {start}", "Effective-dated windows have positive length",
                 lambda r, s=start, e=end: r[e] is None or r[e] > r[s], lambda r, t=table: r[ENTITIES[t]["pk"]])
    ordering("credential", "credential.expires_at > issued_at", "Expiry follows issuance",
             lambda r: r["expires_at"] is None or r["expires_at"] > r["issued_at"], lambda r: r["credential_id"])
    ordering("revocation", "revocation after issuance", "A credential cannot be revoked before it exists",
             lambda r: r["effective_at"] > truth_credential(data, r["credential_id"])["issued_at"], lambda r: r["revocation_id"])

    attempts_by_completion = defaultdict(list)
    for a in data["assessment_attempt"]:
        attempts_by_completion[a["completion_id"]].append(a)
    bad_order = set()
    for cid, items in attempts_by_completion.items():
        items.sort(key=lambda a: a["attempt_no"])
        times = [a["attempted_at"] for a in items]
        if times != sorted(times) or len(set(times)) != len(times) or times[0] < completions[cid]["enrolled_at"]:
            bad_order.add(cid)
    report.add("date_ordering", "attempts strictly increasing in time", "Attempts follow enrolment and each other",
               bad_order, total=len(attempts_by_completion))

    bridge = defaultdict(list)
    for b in data["credential_completion"]:
        bridge[b["credential_id"]].append(b["completion_id"])
    first_credentials = {c["credential_id"]: c for c in _unique_first(data["credential"])}
    premature = set()
    for cid, cred in first_credentials.items():
        for comp in bridge.get(cid, []):
            record = completions.get(comp)
            if record and record["finalized_at"] and cred["issued_at"] < record["finalized_at"]:
                premature.add(cid)
    report.add("date_ordering", "credential issued after every qualifying completion",
               "issued_at is not earlier than the completion time of any qualifying course", premature,
               (T.CREDENTIAL_ISSUED_BEFORE_COMPLETION,), len(first_credentials))
    report.add("date_ordering", "verification not earlier than issuance", "Verification cannot precede issuance unless not_found",
               {v["verification_id"] for v in data["verification_request"] if v["credential_id"]
                and v["requested_at"] < first_credentials[v["credential_id"]]["issued_at"]}, total=len(data["verification_request"]))

    # ---- arithmetic reconciliation
    bad_state, bad_pass, bad_contig = set(), set(), set()
    for cid, rec in completions.items():
        course = courses[rec["course_id"]]
        items = attempts_by_completion.get(cid, [])
        state = derive_completion_state(pass_mark=course["pass_mark"], max_attempts=course["max_attempts"],
                                        progress_pct=rec["progress_pct"], attempt_scores=[a["score"] for a in items],
                                        withdrawn=rec["status"] == "withdrawn")
        if (rec["status"], rec["attempts_used"], rec["final_score"]) != (state["status"], state["attempts_used"], state["final_score"]):
            bad_state.add(cid)
        if rec["status"] == "completed" and items and rec["finalized_at"] != items[state["first_pass_index"]]["attempted_at"]:
            bad_state.add(cid)
        if [a["attempt_no"] for a in items] != list(range(1, len(items) + 1)) or len(items) > course["max_attempts"]:
            bad_contig.add(cid)
        if any(a["passed"] != (1 if a["score"] >= course["pass_mark"] else 0) for a in items) \
                or any(a["passed"] for a in items[:-1]):
            bad_pass.add(cid)
        if items and rec["progress_pct"] != 100:
            bad_state.add(cid)
    report.add("reconciliation", "completion status/attempts/score derived from attempts",
               "status, attempts_used, final_score and finalized_at recompute from assessment_attempt", bad_state, total=len(completions))
    report.add("reconciliation", "attempt numbering and limits", "contiguous attempt_no, within max_attempts", bad_contig, total=len(completions))
    report.add("reconciliation", "attempt pass flags", "passed equals score >= pass_mark and no attempt follows a pass", bad_pass, total=len(completions))

    rule_course_rows = defaultdict(list)
    for rc in data["credential_rule_course"]:
        rule_course_rows[rc["rule_id"]].append(rc)
    bad_threshold = {rid for rid, r in rules.items() if not
                     (sum(c["is_mandatory"] for c in rule_course_rows[rid]) <= r["min_courses_required"] <= len(rule_course_rows[rid]))}
    report.add("reconciliation", "rule thresholds consistent with course list", "mandatory <= min_courses <= course count",
               bad_threshold, total=len(rules))
    report.add("reconciliation", "credential expiry = issued_at + validity_months", "expires_at derives from the rule",
               {cid for cid, c in first_credentials.items()
                if c["expires_at"] != (to_ts(add_months(parse(c["issued_at"]), rules[c["rule_id"]]["validity_months"]))
                                       if rules[c["rule_id"]]["validity_months"] else None)}, total=len(first_credentials))

    # ---- issuance rules re-evaluated from source records
    by_learner = defaultdict(dict)
    for rec in completions.values():
        by_learner[rec["learner_id"]][rec["course_id"]] = rec
    ineligible, bad_links = set(), set()
    for cid, cred in first_credentials.items():
        rule = rules[cred["rule_id"]]
        result = evaluate_eligibility(
            rule={**rule, "status": "active"}, rule_courses=[{"course_id": c["course_id"], "is_mandatory": c["is_mandatory"]} for c in rule_course_rows[rule["rule_id"]]],
            completions_by_course=by_learner.get(cred["learner_id"], {}), learner_status="active",
            has_active_credential=False, has_blocking_revocation=False, as_of=cred["issued_at"])
        if not result["eligible"] or sorted(bridge.get(cid, [])) != result["qualifying_completion_ids"]:
            ineligible.add(cid)
        if any(completions[c]["learner_id"] != cred["learner_id"] for c in bridge.get(cid, [])):
            bad_links.add(cid)
    report.add("business_rules", "issuance requirements satisfied", "Rule thresholds met and bridge rows match qualifying completions",
               ineligible, total=len(first_credentials))
    report.add("business_rules", "bridge completions belong to credential holder", "credential_completion respects learner",
               bad_links, total=len(first_credentials))

    assignments_by_rule = defaultdict(list)
    for a in data["rule_issuer_assignment"]:
        assignments_by_rule[a["rule_id"]].append(a)
    def issuer_for(cred):
        for a in assignments_by_rule[cred["rule_id"]]:
            if a["effective_from"] <= cred["issued_at"] and (a["effective_to"] is None or cred["issued_at"] < a["effective_to"]):
                return a["issuer_id"]
    report.add("business_rules", "issuer matches effective assignment", "Issuer is the one assigned to the rule at issued_at",
               {cid for cid, c in first_credentials.items() if issuer_for(c) != c["issuer_id"]}, total=len(first_credentials))
    report.add("business_rules", "signing key valid at issuance", "key belongs to issuer and is within its validity window",
               {cid for cid, c in first_credentials.items()
                if keys[c["key_id"]]["issuer_id"] != c["issuer_id"] or not (keys[c["key_id"]]["valid_from"] <= c["issued_at"]
                   and (keys[c["key_id"]]["valid_to"] is None or c["issued_at"] < keys[c["key_id"]]["valid_to"]))}, total=len(first_credentials))
    open_assignments = Counter(a["rule_id"] for a in data["rule_issuer_assignment"] if a["effective_to"] is None)
    report.add("lifecycle", "one open issuer assignment per rule", "Issuer changes close the previous assignment",
               {rid for rid in rules if open_assignments[rid] != 1}, total=len(rules))
    report.add("lifecycle", "retired issuers have successors", "Retirement records valid_to and successor",
               {i["issuer_id"] for i in issuers.values() if (i["status"] == "retired") != (i["valid_to"] is not None and i["successor_issuer_id"] is not None)},
               total=len(issuers))

    # ---- cryptographic integrity
    tampered = set()
    for row in data["credential"]:
        payload_ok = crypto.payload_hash(row["payload_json"]) == row["payload_hash"]
        signature_ok = crypto.verify_signature(keys[row["key_id"]]["public_key_b64"], row["payload_hash"], row["signature_b64"])
        payload = json.loads(row["payload_json"])
        fields_ok = all(payload.get(k) == row[k] for k in ("credential_id", "learner_id", "rule_id", "issuer_id", "key_id", "issued_at", "expires_at"))
        if not (payload_ok and signature_ok and fields_ok):
            tampered.add(row["credential_id"])
    report.add("integrity", "payload hash and signature verify", "sha256(payload_json) = payload_hash and the issuer key verifies the signature",
               tampered, (T.PAYLOAD_HASH_ALTERED,), len(data["credential"]))

    # ---- lifecycle / decision consistency
    revocations = defaultdict(list)
    for r in data["revocation"]:
        revocations[r["credential_id"]].append(r)
    report.add("lifecycle", "credential.status matches revocation records", "revoked iff a revocation exists",
               {cid for cid, c in first_credentials.items() if (c["status"] == "revoked") != (cid in revocations)}, total=len(first_credentials))
    report.add("lifecycle", "revocation sequence contiguous", "seq runs 1..n per credential",
               {cid for cid, items in revocations.items() if sorted(r["seq"] for r in items) != list(range(1, len(items) + 1))},
               total=len(revocations))
    report.add("lifecycle", "revoked credential never verifies as active after revocation",
               "No result_status=valid at or after the effective revocation time",
               {v["verification_id"] for v in data["verification_request"] if v["result_status"] == "valid" and v["credential_id"] in revocations
                and min(r["effective_at"] for r in revocations[v["credential_id"]]) <= v["requested_at"]},
               (T.REVOKED_CREDENTIAL_VERIFIED_ACTIVE,), len(data["verification_request"]))
    report.add("lifecycle", "tampered credential never verifies as valid", "No result_status=valid for a credential failing integrity checks",
               {v["verification_id"] for v in data["verification_request"] if v["result_status"] == "valid" and v["credential_id"] in tampered},
               (T.PAYLOAD_HASH_ALTERATION_NOT_DETECTED,), len(data["verification_request"]))
    mismatched_results, mismatched_identity = set(), set()
    for v in data["verification_request"]:
        cred = first_credentials.get(v["presented_credential_id"])
        revoked = min((r["effective_at"] for r in revocations.get(v["presented_credential_id"], [])), default=None)
        hash_ok = None if not v["presented_hash"] or not cred else v["presented_hash"].lower() == cred["payload_hash"]
        expected = expected_result(exists=cred is not None, issued_at=cred["issued_at"] if cred else None,
                                   intact=cred is not None and cred["credential_id"] not in tampered, revoked_at=revoked,
                                   expires_at=cred["expires_at"] if cred else None, requested_at=v["requested_at"], presented_hash_ok=hash_ok)
        if expected != v["result_status"]:
            mismatched_results.add(v["verification_id"])
        identity = "not_requested" if expected == "not_found" else expected_identity(
            learner=learners[cred["learner_id"]], name=v["claimed_name"], email=v["claimed_email"], dob=v["claimed_dob"])
        if identity != v["identity_status"]:
            mismatched_identity.add(v["verification_id"])
    report.add("lifecycle", "recorded result equals recomputed result", "Replaying the rules reproduces each recorded result_status",
               mismatched_results, (T.REVOKED_CREDENTIAL_VERIFIED_ACTIVE, T.PAYLOAD_HASH_ALTERATION_NOT_DETECTED), len(data["verification_request"]))
    report.add("lifecycle", "recorded identity status reproducible", "Identity matching recomputes from claims and learner record",
               mismatched_identity, total=len(data["verification_request"]))
    report.add("business_rules", "identity never matched on name alone", "matched requires email or date of birth",
               {v["verification_id"] for v in data["verification_request"]
                if v["identity_status"] == "matched" and not (v["claimed_email"] or v["claimed_dob"])}, total=len(data["verification_request"]))

    # ---- audit trail
    events = data["audit_event"]
    broken, prev = set(), audit.GENESIS_HASH
    for index, e in enumerate(events, start=1):
        recomputed = audit.compute_event_hash(prev, e["seq"], e["event_id"], e["occurred_at"], e["actor_type"], e["actor_user_id"],
                                              e["action"], e["entity_type"], e["entity_id"], e["details_json"])
        if e["seq"] != index or e["prev_hash"] != prev or recomputed != e["event_hash"] or e["event_id"] != ids.audit_event_id(index):
            broken.add(e["event_id"])
        prev = e["event_hash"]
    report.add("audit", "audit hash chain intact", "seq contiguous, prev_hash linked, event_hash recomputes", broken, total=len(events))
    report.add("audit", "audit timestamps non-decreasing", "occurred_at never goes backwards",
               {b["event_id"] for a, b in zip(events, events[1:]) if b["occurred_at"] < a["occurred_at"]}, total=len(events))
    issued_event_hash = {e["entity_id"]: json.loads(e["details_json"]).get("payload_hash")
                         for e in events if e["action"] == "credential.issued"}
    report.add("audit", "issuance audit hash equals stored payload hash", "History and record agree on what was signed",
               {c["credential_id"] for c in data["credential"] if issued_event_hash.get(c["credential_id"]) != c["payload_hash"]},
               (T.PAYLOAD_HASH_ALTERED, T.DUPLICATE_CREDENTIAL_ID), len(data["credential"]))
    audited = Counter(e["entity_id"] for e in events if e["action"] == "credential.issued")
    report.add("audit", "every credential has exactly one issuance event", "No unaudited issuance",
               {cid for cid in first_credentials if audited[cid] != 1}, total=len(first_credentials))
    finalized = Counter(e["entity_id"] for e in events if e["action"] == "completion.finalized")
    report.add("audit", "finalised completions audited once", "Terminal completion states have one event",
               {cid for cid, r in completions.items() if (r["status"] in ("completed", "failed", "withdrawn")) != (finalized[cid] == 1)},
               total=len(completions))

    names = Counter(l["full_name"].lower() for l in learners.values())
    informational = {
        "learners_sharing_a_name": sum(n for n in names.values() if n > 1),
        "name_groups_with_duplicates": sum(1 for n in names.values() if n > 1),
        "learners_sharing_name_and_birthdate": sum(n for n in Counter((l["full_name"].lower(), l["date_of_birth"]) for l in learners.values()).values() if n > 1),
        "completion_status_counts": dict(Counter(r["status"] for r in completions.values())),
        "credential_status_counts": dict(Counter(c["status"] for c in first_credentials.values())),
        "verification_result_counts": dict(Counter(v["result_status"] for v in data["verification_request"])),
        "verification_identity_counts": dict(Counter(v["identity_status"] for v in data["verification_request"])),
        "retired_issuers": sum(1 for i in issuers.values() if i["status"] == "retired"),
        "rotated_keys": sum(1 for k in keys.values() if k["status"] == "rotated"),
        "revocation_reason_counts": dict(Counter(r["reason_code"] for r in data["revocation"])),
        "row_counts": {t: len(data[t]) for t in TABLE_ORDER},
    }
    failed = [c for c in report.checks if c["status"] == "FAIL"]
    return {"summary": {"checks": len(report.checks), "passed": len(report.checks) - len(failed), "failed": len(failed),
                        "labelled_anomalies_total": sum(len(v) for v in report.labels.values()),
                        "labelled_anomalies_detected": sum(c["labelled_anomalies_found"] for c in report.checks if c["expects"])},
            "informational": informational, "checks": report.checks}


def truth_credential(data, credential_id):
    for c in data["credential"]:
        if c["credential_id"] == credential_id:
            return c
    raise KeyError(credential_id)


def _unique_first(rows):
    seen = set()
    for row in rows:
        if row["credential_id"] not in seen:
            seen.add(row["credential_id"])
            yield row


def render_markdown(report: dict, header: str = "") -> str:
    s = report["summary"]
    lines = ["# Data Validation Report", "", header, "",
             f"**{s['passed']} of {s['checks']} checks passed**, {s['failed']} failed. "
             f"Labelled anomalies detected by the checks: {s['labelled_anomalies_detected']} "
             f"(ground truth holds {s['labelled_anomalies_total']} labels; some labels are detected by more than one check).", "",
             "A check passes when every violation it finds is a labelled, deliberately injected anomaly and every anomaly it is "
             "meant to catch was found. Unexpected violations or missed anomalies fail the check.", "",
             "| Category | Check | Records | Violations | Labelled found | Unexpected | Missed | Status |", "|---|---|---|---|---|---|---|---|"]
    for c in report["checks"]:
        lines.append(f"| {c['category']} | {c['name']} | {c['records_checked']} | {c['violations']} | {c['labelled_anomalies_found']} | "
                     f"{c['unexpected_violations']} | {c['labelled_but_not_found']} | {c['status']} |")
    lines += ["", "## Dataset profile", "", "```json", json.dumps(report["informational"], indent=2), "```", ""]
    return "\n".join(lines)
