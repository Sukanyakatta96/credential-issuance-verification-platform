from pathlib import Path

from .. import audit
from ..domain import issue_types as T
from ..domain.verification import check_integrity
from ..errors import ApiError
from ..timeutil import to_ts, utcnow
from . import verification as verification_service


def _finding(issue_type, entity_type, entity_id, related=None, detail=""):
    return {"issue_type": issue_type, "entity_type": entity_type, "entity_id": entity_id,
            "related_entity_id": related, "detail": detail}


def run_scan(db) -> list[dict]:
    """Detects anomalies using database content only. Ground-truth labels are never consulted here."""
    findings = []

    for row in db.execute(
        "SELECT c.credential_id, c.issued_at, MAX(cr.finalized_at) AS completed_at, "
        "SUM(cr.status != 'completed') AS open_courses FROM credential c "
        "JOIN credential_completion cc ON cc.credential_id = c.credential_id "
        "JOIN completion_record cr ON cr.completion_id = cc.completion_id "
        "GROUP BY c.credential_id HAVING c.issued_at < MAX(cr.finalized_at) OR SUM(cr.status != 'completed') > 0"):
        findings.append(_finding(T.CREDENTIAL_ISSUED_BEFORE_COMPLETION, "credential", row["credential_id"], None,
                                 f"issued {row['issued_at']} but qualifying coursework finished {row['completed_at']}"))

    for row in db.execute("SELECT record_key, source_file, row_number, reason FROM import_rejection "
                          "WHERE source_file = 'credential.csv' AND reason LIKE '%credential.credential_id%'"):
        findings.append(_finding(T.DUPLICATE_CREDENTIAL_ID, "credential", row["record_key"], None,
                                 f"row {row['row_number']} of {row['source_file']} rejected: {row['reason']}"))

    tampered_ids = set()
    keys = {r["key_id"]: r["public_key_b64"] for r in db.execute("SELECT key_id, public_key_b64 FROM issuer_key")}
    for row in db.execute("SELECT credential_id, learner_id, key_id, payload_json, payload_hash, signature_b64 FROM credential"):
        ok, problems = check_integrity(dict(row), keys.get(row["key_id"]))
        if not ok:
            tampered_ids.add(row["credential_id"])
            findings.append(_finding(T.PAYLOAD_HASH_ALTERED, "credential", row["credential_id"], None, "; ".join(problems)))

    for row in db.execute(
        "SELECT v.verification_id, v.credential_id, r.effective_at FROM verification_request v "
        "JOIN revocation r ON r.credential_id = v.credential_id "
        "WHERE v.result_status = 'valid' AND r.effective_at <= v.requested_at GROUP BY v.verification_id"):
        findings.append(_finding(T.REVOKED_CREDENTIAL_VERIFIED_ACTIVE, "verification_request", row["verification_id"],
                                 row["credential_id"], f"credential revoked {row['effective_at']} before this check"))

    if tampered_ids:
        for row in db.execute("SELECT verification_id, credential_id FROM verification_request WHERE result_status = 'valid'"):
            if row["credential_id"] in tampered_ids:
                findings.append(_finding(T.PAYLOAD_HASH_ALTERATION_NOT_DETECTED, "verification_request",
                                         row["verification_id"], row["credential_id"],
                                         "recorded as valid although the credential payload hash fails verification"))

    for row in db.execute(
        "SELECT c.credential_id FROM credential c WHERE (c.status = 'revoked') != "
        "EXISTS (SELECT 1 FROM revocation r WHERE r.credential_id = c.credential_id)"):
        findings.append(_finding("status_revocation_mismatch", "credential", row["credential_id"], None,
                                 "credential status disagrees with its revocation records"))

    chain = audit.verify_chain(db)
    if not chain["valid"]:
        findings.append(_finding("audit_chain_broken", "audit_event", chain["first_broken_event"], None, chain["problem"]))
    return findings


def scan_summary(db, per_type_limit: int = 100) -> dict:
    findings = run_scan(db)
    counts: dict[str, int] = {}
    samples: dict[str, list] = {}
    for f in findings:
        counts[f["issue_type"]] = counts.get(f["issue_type"], 0) + 1
        samples.setdefault(f["issue_type"], [])
        if len(samples[f["issue_type"]]) < per_type_limit:
            samples[f["issue_type"]].append(f)
    return {"generated_at": to_ts(utcnow()), "total_findings": len(findings), "counts": counts, "findings": samples,
            "audit_chain": audit.verify_chain(db)}


def import_rejections(db, limit=200):
    return [dict(r) for r in db.execute(
        "SELECT rejection_id, source_file, row_number, record_key, reason FROM import_rejection ORDER BY rejection_id LIMIT ?",
        (limit,))]


def _read_csv(path: Path):
    import csv
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def evaluate_against_ground_truth(db, ground_truth_dir: str) -> dict:
    gt_dir = Path(ground_truth_dir)
    labels_path = gt_dir / "ground_truth.csv"
    decisions_path = gt_dir / "ground_truth_expected_decisions.csv"
    if not labels_path.is_file() or not decisions_path.is_file():
        raise ApiError(404, "GROUND_TRUTH_UNAVAILABLE",
                       "Ground-truth files were not found. Generate a dataset and set GROUND_TRUTH_DIR.")
    labels = _read_csv(labels_path)
    expected_by_type: dict[str, set] = {t: set() for t in T.ALL_ISSUE_TYPES}
    for row in labels:
        expected_by_type.setdefault(row["issue_type"], set()).add(row["entity_id"])

    detected_by_type: dict[str, set] = {t: set() for t in T.ALL_ISSUE_TYPES}
    for f in run_scan(db):
        if f["issue_type"] in detected_by_type:
            detected_by_type[f["issue_type"]].add(f["entity_id"])

    detection = []
    for issue_type in T.ALL_ISSUE_TYPES:
        expected, detected = expected_by_type[issue_type], detected_by_type[issue_type]
        tp, fp, fn = len(expected & detected), len(detected - expected), len(expected - detected)
        detection.append({
            "issue_type": issue_type, "labelled": len(expected), "detected": len(detected),
            "true_positives": tp, "false_positives": fp, "false_negatives": fn,
            "precision": round(tp / (tp + fp), 4) if tp + fp else None,
            "recall": round(tp / (tp + fn), 4) if tp + fn else None,
        })

    expected_rows = _read_csv(decisions_path)
    confusion: dict[str, dict[str, int]] = {}
    engine_correct = recorded_correct = identity_correct = 0
    recorded_wrong_samples = []
    for row in expected_rows:
        replay = verification_service.replay(db, row["verification_id"])
        engine_status = replay["replayed"]["result_status"]
        recorded_status = replay["recorded"]["result_status"]
        confusion.setdefault(row["expected_result_status"], {}).setdefault(engine_status, 0)
        confusion[row["expected_result_status"]][engine_status] += 1
        engine_correct += engine_status == row["expected_result_status"]
        identity_correct += replay["replayed"]["identity_status"] == row["expected_identity_status"]
        if recorded_status == row["expected_result_status"]:
            recorded_correct += 1
        elif len(recorded_wrong_samples) < 25:
            recorded_wrong_samples.append({"verification_id": row["verification_id"],
                                           "expected": row["expected_result_status"], "recorded": recorded_status})
    total = len(expected_rows)
    return {
        "generated_at": to_ts(utcnow()),
        "detection": detection,
        "verification_engine": {
            "requests_evaluated": total,
            "engine_result_accuracy": round(engine_correct / total, 4) if total else None,
            "engine_identity_accuracy": round(identity_correct / total, 4) if total else None,
            "recorded_result_accuracy": round(recorded_correct / total, 4) if total else None,
            "recorded_result_errors": total - recorded_correct,
            "confusion_matrix": confusion,
            "recorded_error_samples": recorded_wrong_samples,
        },
    }
