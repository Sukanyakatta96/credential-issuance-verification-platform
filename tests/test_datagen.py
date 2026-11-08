import csv
import json
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.db import connect, migrate
from app.services import integrity
from datagen.export import checksums_of, export_dataset
from datagen.generator import Params, generate
from datagen.load import load_dataset
from datagen.schema_spec import ENTITIES, TABLE_ORDER
from datagen.validate import validate_dataset

SECRET = "datagen-test-signing-secret-0123456789"
PARAMS = Params(seed=20261022, learners=800, courses=40, credentials=300, verifications=150, signing_secret=SECRET)


def read_csv(path):
    with open(path, newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


class GeneratedDatasetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.out = Path(cls.tmp.name) / "data"
        cls.dataset = generate(PARAMS)
        cls.manifest = export_dataset(cls.dataset, PARAMS, cls.out, ("csv", "json", "sql"), "test")
        cls.tables = {t: read_csv(cls.out / "csv" / f"{t}.csv") for t in TABLE_ORDER}
        cls.report = validate_dataset(str(cls.out))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_volumes_follow_parameters(self):
        counts = self.manifest["row_counts"]
        self.assertEqual(counts["learner"], PARAMS.learners)
        self.assertEqual(counts["course"], PARAMS.courses)
        duplicates = PARAMS.anomaly_counts["duplicate_id"]
        self.assertEqual(counts["credential"], PARAMS.credentials + duplicates)
        self.assertEqual(len({r["credential_id"] for r in self.tables["credential"]}), PARAMS.credentials)
        self.assertEqual(counts["verification_request"], PARAMS.verifications)

    def test_naming_conventions(self):
        self.assertEqual(self.tables["learner"][0]["learner_id"], "LRN-000001")
        self.assertEqual(self.tables["credential"][0]["credential_id"], "CRD-2026-000001")
        self.assertEqual(self.tables["verification_request"][0]["verification_id"], "VER-2026-000001")
        for row in self.tables["completion_record"][:200]:
            self.assertEqual(row["completion_id"], f"CMP-{row['learner_id']}-{row['course_id']}")
        for row in self.tables["revocation"]:
            self.assertEqual(row["revocation_id"], f"REV-{row['credential_id']}-01")

    def test_required_population_characteristics_are_present(self):
        names = [r["full_name"].lower() for r in self.tables["learner"]]
        self.assertGreater(len(names) - len(set(names)), 0, "duplicate names expected")
        statuses = {r["status"] for r in self.tables["completion_record"]}
        self.assertTrue({"completed", "failed", "withdrawn", "in_progress"} <= statuses)
        self.assertGreater(len(self.tables["revocation"]), 0)
        self.assertEqual({r["status"] for r in self.tables["issuer"]}, {"active", "retired"})
        self.assertTrue(any(r["successor_issuer_id"] for r in self.tables["issuer"]))
        self.assertTrue(any(r["status"] == "rotated" for r in self.tables["issuer_key"]))
        results = {r["result_status"] for r in self.tables["verification_request"]}
        self.assertTrue({"valid", "not_found"} <= results)
        identities = {r["identity_status"] for r in self.tables["verification_request"]}
        self.assertTrue({"matched", "mismatch", "insufficient_identifiers", "not_requested"} <= identities)

    def test_ground_truth_is_separate_and_covers_every_required_edge_case(self):
        for table, rows in self.tables.items():
            self.assertNotIn("issue_type", rows[0].keys(), table)
            self.assertNotIn("ground_truth_id", rows[0].keys(), table)
        labels = read_csv(self.out / "ground_truth" / "ground_truth.csv")
        by_type = {}
        for row in labels:
            by_type.setdefault(row["issue_type"], []).append(row)
        self.assertEqual(set(by_type), {"credential_issued_before_completion", "duplicate_credential_id", "revoked_credential_verified_active",
                                        "payload_hash_altered", "payload_hash_alteration_not_detected"})
        counts = PARAMS.anomaly_counts
        self.assertEqual(len(by_type["credential_issued_before_completion"]), counts["issued_before_completion"])
        self.assertEqual(len(by_type["duplicate_credential_id"]), counts["duplicate_id"])
        decisions = read_csv(self.out / "ground_truth" / "ground_truth_expected_decisions.csv")
        self.assertEqual(len(decisions), PARAMS.verifications)
        self.assertTrue(json.loads((self.out / "ground_truth" / "ground_truth.json").read_text()))

    def test_labels_agree_with_the_business_rules(self):
        labels = read_csv(self.out / "ground_truth" / "ground_truth.csv")
        completions = {r["completion_id"]: r for r in self.tables["completion_record"]}
        bridge = {}
        for row in self.tables["credential_completion"]:
            bridge.setdefault(row["credential_id"], []).append(row["completion_id"])
        for row in labels:
            if row["issue_type"] == "credential_issued_before_completion":
                cred = next(c for c in self.tables["credential"] if c["credential_id"] == row["entity_id"])
                self.assertLess(cred["issued_at"], max(completions[c]["finalized_at"] for c in bridge[row["entity_id"]]))
        flagged = {r["entity_id"] for r in labels if r["issue_type"] == "credential_issued_before_completion"}
        seen = set()
        for cred in self.tables["credential"]:
            if cred["credential_id"] in flagged or cred["credential_id"] in seen:
                continue
            seen.add(cred["credential_id"])
            if cred["credential_id"] in bridge:
                self.assertGreaterEqual(cred["issued_at"], max(completions[c]["finalized_at"] for c in bridge[cred["credential_id"]]))
        revoked_ids = {r["credential_id"] for r in self.tables["revocation"]}
        self.assertEqual({c["credential_id"] for c in self.tables["credential"] if c["status"] == "revoked"}, revoked_ids)

    def test_validation_suite_passes_and_finds_every_labelled_anomaly(self):
        failed = [c for c in self.report["checks"] if c["status"] == "FAIL"]
        self.assertEqual(failed, [], failed[:2])
        self.assertGreater(self.report["summary"]["checks"], 100)
        detecting = [c for c in self.report["checks"] if c["expects"]]
        self.assertTrue(detecting and all(c["labelled_anomalies_found"] > 0 for c in detecting))
        self.assertEqual(self.report["informational"]["row_counts"]["learner"], PARAMS.learners)

    def test_validator_actually_fails_on_corrupted_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            copy = Path(tmp) / "data"
            shutil.copytree(self.out, copy)
            path = copy / "csv" / "completion_record.csv"
            rows = read_csv(path)
            rows[0]["learner_id"] = "LRN-999999"
            rows[1]["status"] = "bogus"
            rows[2]["final_score"] = "12.5"
            with open(path, "w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=rows[0].keys(), lineterminator="\n")
                writer.writeheader()
                writer.writerows(rows)
            report = validate_dataset(str(copy))
            names = {c["name"] for c in report["checks"] if c["status"] == "FAIL"}
            self.assertIn("completion_record.learner_id -> learner", names)
            self.assertIn("completion_record.status: required/allowed values", names)
            self.assertIn("completion status/attempts/score derived from attempts", names)

    def test_regeneration_with_same_seed_is_byte_identical(self):
        for attempt in range(2):
            with tempfile.TemporaryDirectory() as tmp:
                dataset = generate(PARAMS)
                export_dataset(dataset, PARAMS, Path(tmp), ("csv", "json", "sql"), "test")
                self.assertEqual(checksums_of(Path(tmp)), checksums_of(self.out), f"attempt {attempt}")

    def test_different_seed_changes_data_and_same_generator_scales(self):
        other = generate(Params(seed=7, learners=600, courses=32, credentials=200, verifications=100, signing_secret=SECRET))
        self.assertNotEqual(other.tables["learner"][5]["email"], self.dataset.tables["learner"][5]["email"])
        self.assertEqual(len(other.tables["learner"]), 600)
        self.assertEqual(len({c["credential_id"] for c in other.tables["credential"]}), 200)

    def test_schema_spec_matches_database_columns(self):
        db = connect(":memory:")
        migrate(db)
        for table, spec in ENTITIES.items():
            actual = [r["name"] for r in db.execute(f"PRAGMA table_info({table})")]
            expected = [f["name"] for f in spec["fields"]]
            self.assertEqual([c for c in actual if c in expected], expected, table)
            self.assertLessEqual(set(actual) - set(expected), {"password_hash"}, table)

    def test_loading_enforces_constraints_and_records_rejections(self):
        db = connect(":memory:")
        migrate(db)
        result = load_dataset(db, str(self.out))
        duplicates = PARAMS.anomaly_counts["duplicate_id"]
        self.assertEqual(result["rejected_rows"], duplicates)
        self.assertEqual(result["loaded"]["credential"], PARAMS.credentials)
        self.assertEqual(db.execute("PRAGMA foreign_key_check").fetchall(), [])
        self.assertEqual(db.execute("SELECT COUNT(*) FROM import_rejection").fetchone()[0], duplicates)
        self.assertEqual(db.execute("SELECT last_value FROM id_counter WHERE counter_name='credential'").fetchone()[0], PARAMS.credentials)

    def test_sql_seed_produces_the_same_database_as_the_loader(self):
        loaded = connect(":memory:")
        migrate(loaded)
        load_dataset(loaded, str(self.out))
        seeded = sqlite3.connect(":memory:")
        seeded.executescript((self.out / "sql" / "schema.sql").read_text(encoding="utf-8"))
        seeded.executescript((self.out / "sql" / "seed.sql").read_text(encoding="utf-8"))
        for table in TABLE_ORDER + ["import_rejection", "id_counter"]:
            self.assertEqual(seeded.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0],
                             loaded.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0], table)
        probe = "SELECT group_concat(payload_hash || signature_b64), (SELECT group_concat(event_hash) FROM audit_event) FROM credential"
        self.assertEqual(tuple(seeded.execute(probe).fetchone()), tuple(loaded.execute(probe).fetchone()))

    def test_application_scanner_recovers_ground_truth_without_seeing_it(self):
        db = connect(":memory:")
        migrate(db)
        load_dataset(db, str(self.out))
        evaluation = integrity.evaluate_against_ground_truth(db, str(self.out / "ground_truth"))
        for row in evaluation["detection"]:
            self.assertGreater(row["labelled"], 0, row)
            self.assertEqual((row["false_positives"], row["false_negatives"]), (0, 0), row)
        engine = evaluation["verification_engine"]
        self.assertEqual((engine["engine_result_accuracy"], engine["engine_identity_accuracy"]), (1.0, 1.0))
        expected_wrong = PARAMS.anomaly_counts["revoked_verifies_active"] + PARAMS.anomaly_counts["altered_hash"]
        self.assertEqual(engine["recorded_result_errors"], expected_wrong)
        scanner_source = Path(integrity.__file__).read_text()
        self.assertNotIn("ground_truth", scanner_source.split("def evaluate_against_ground_truth")[0])

    def test_data_dictionary_covers_every_entity(self):
        dictionary = json.loads((self.out / "data_dictionary.json").read_text())
        for required in ("learner", "course", "credential_rule", "completion_record", "credential", "issuer", "verification_request", "revocation", "audit_event"):
            self.assertIn(required, dictionary)
            for field in dictionary[required]["fields"]:
                self.assertTrue({"name", "type", "required", "allowed", "unit", "unique", "rule"} <= set(field))
        self.assertTrue(json.loads((self.out / "source_manifest.json").read_text())["external_data_used"] is False)


if __name__ == "__main__":
    unittest.main()
