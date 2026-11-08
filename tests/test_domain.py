import unittest

from app import crypto
from app.domain.completion import derive_completion_state
from app.domain.eligibility import evaluate_eligibility
from app.domain.verification import evaluate_verification, match_identity

RULE = {"rule_id": "RUL-000001", "status": "active", "effective_from": "2026-01-01T00:00:00Z", "effective_to": None,
        "min_courses_required": 2, "min_avg_score": 70.0, "min_course_score": 65.0, "title": "T", "version": 1}
COURSES = [{"course_id": "A", "is_mandatory": 1}, {"course_id": "B", "is_mandatory": 0}, {"course_id": "C", "is_mandatory": 0}]
NOW = "2026-06-01T00:00:00Z"


def comp(course, score, status="completed"):
    return {"completion_id": f"CMP-{course}", "course_id": course, "status": status, "final_score": score, "finalized_at": "2026-05-01T00:00:00Z"}


def evaluate(done, **overrides):
    args = dict(rule=RULE, rule_courses=COURSES, completions_by_course={c["course_id"]: c for c in done}, learner_status="active",
                has_active_credential=False, has_blocking_revocation=False, as_of=NOW)
    args.update(overrides)
    return evaluate_eligibility(**args)


class CompletionStateTests(unittest.TestCase):
    def test_enrolled_then_in_progress(self):
        self.assertEqual(derive_completion_state(pass_mark=60, max_attempts=3, progress_pct=0, attempt_scores=[])["status"], "enrolled")
        self.assertEqual(derive_completion_state(pass_mark=60, max_attempts=3, progress_pct=30, attempt_scores=[])["status"], "in_progress")

    def test_pass_boundary_is_inclusive(self):
        state = derive_completion_state(pass_mark=60, max_attempts=3, progress_pct=100, attempt_scores=[59.9, 60.0])
        self.assertEqual((state["status"], state["first_pass_index"], state["final_score"]), ("completed", 1, 60.0))

    def test_exhausted_attempts_fail(self):
        state = derive_completion_state(pass_mark=60, max_attempts=2, progress_pct=100, attempt_scores=[40, 55])
        self.assertEqual((state["status"], state["final_score"], state["attempts_used"]), ("failed", 55, 2))

    def test_withdrawal_never_overrides_a_pass(self):
        self.assertEqual(derive_completion_state(pass_mark=60, max_attempts=2, progress_pct=100, attempt_scores=[80], withdrawn=True)["status"], "completed")
        self.assertEqual(derive_completion_state(pass_mark=60, max_attempts=2, progress_pct=20, attempt_scores=[], withdrawn=True)["status"], "withdrawn")


class EligibilityTests(unittest.TestCase):
    def test_eligible_exactly_at_average_threshold(self):
        result = evaluate([comp("A", 75), comp("B", 65)])
        self.assertTrue(result["eligible"], result["checks"])
        self.assertEqual(result["average_score"], 70.0)
        self.assertEqual(result["qualifying_completion_ids"], ["CMP-A", "CMP-B"])

    def test_average_just_below_threshold_fails(self):
        result = evaluate([comp("A", 69.9), comp("B", 69.9)])
        self.assertFalse(result["eligible"])
        self.assertEqual([c["code"] for c in result["checks"] if not c["passed"]], ["MIN_AVERAGE"])

    def test_course_below_per_course_floor_does_not_count(self):
        result = evaluate([comp("A", 90), comp("B", 64.9)])
        self.assertFalse(result["eligible"])
        self.assertEqual(result["counted_courses"], 1)

    def test_missing_mandatory_course_blocks_even_with_enough_courses(self):
        result = evaluate([comp("B", 90), comp("C", 90)])
        self.assertFalse(result["eligible"])
        self.assertIn("MANDATORY_COURSES", [c["code"] for c in result["checks"] if not c["passed"]])

    def test_incomplete_statuses_never_count(self):
        for status in ("in_progress", "failed", "withdrawn", "enrolled"):
            self.assertFalse(evaluate([comp("A", 99, status), comp("B", 99, status)])["eligible"], status)

    def test_state_blockers(self):
        done = [comp("A", 90), comp("B", 90)]
        self.assertFalse(evaluate(done, learner_status="suspended")["eligible"])
        self.assertFalse(evaluate(done, has_active_credential=True)["eligible"])
        self.assertFalse(evaluate(done, has_blocking_revocation=True)["eligible"])
        self.assertFalse(evaluate(done, as_of="2025-12-31T23:59:59Z")["eligible"])
        self.assertFalse(evaluate(done, rule={**RULE, "status": "retired"})["eligible"])
        self.assertFalse(evaluate(done, rule={**RULE, "effective_to": NOW})["eligible"])


class IdentityTests(unittest.TestCase):
    learner = {"full_name": "Ada  Lovelace", "email": "ada@x.example", "date_of_birth": "1990-12-10"}

    def test_name_alone_is_never_enough(self):
        self.assertEqual(match_identity(learner=self.learner, claimed_name="Ada Lovelace", claimed_email=None, claimed_dob=None), "insufficient_identifiers")

    def test_strong_identifier_plus_name_matches_case_and_spacing_insensitively(self):
        self.assertEqual(match_identity(learner=self.learner, claimed_name=" ADA lovelace ", claimed_email="ADA@X.EXAMPLE", claimed_dob=None), "matched")

    def test_any_wrong_supplied_field_is_a_mismatch(self):
        self.assertEqual(match_identity(learner=self.learner, claimed_name="Ada Lovelace", claimed_email="ada@x.example", claimed_dob="1990-12-11"), "mismatch")
        self.assertEqual(match_identity(learner=self.learner, claimed_name="Someone Else", claimed_email="ada@x.example", claimed_dob=None), "mismatch")

    def test_no_claims_means_not_requested(self):
        self.assertEqual(match_identity(learner=self.learner, claimed_name=None, claimed_email="", claimed_dob=None), "not_requested")


class VerificationDecisionTests(unittest.TestCase):
    def setUp(self):
        self.secret, self.key_id = "unit-test-secret-0123456789", "KEY-ISS-001-01"
        payload = '{"credential_id":"CRD-2026-000001","learner_id":"LRN-000001"}'
        digest = crypto.payload_hash(payload)
        self.credential = {"credential_id": "CRD-2026-000001", "learner_id": "LRN-000001", "payload_json": payload, "payload_hash": digest,
                           "signature_b64": crypto.sign_hash(self.secret, self.key_id, digest), "issued_at": "2026-02-01T00:00:00Z", "expires_at": "2026-08-01T00:00:00Z"}
        self.public = crypto.derive_public_key_b64(self.secret, self.key_id)

    def decide(self, as_of="2026-03-01T00:00:00Z", revoked=None, credential=None, presented=None):
        return evaluate_verification(credential=credential or self.credential, public_key_b64=self.public, learner=None,
                                     earliest_effective_revocation=revoked, as_of=as_of, presented_hash=presented,
                                     claimed_name=None, claimed_email=None, claimed_dob=None)["result_status"]

    def test_valid_then_expired_at_the_exact_boundary(self):
        self.assertEqual(self.decide(), "valid")
        self.assertEqual(self.decide(as_of="2026-07-31T23:59:59Z"), "valid")
        self.assertEqual(self.decide(as_of="2026-08-01T00:00:00Z"), "expired")

    def test_revocation_effective_time_is_respected(self):
        self.assertEqual(self.decide(revoked="2026-04-01T00:00:00Z"), "valid")
        self.assertEqual(self.decide(as_of="2026-04-01T00:00:00Z", revoked="2026-04-01T00:00:00Z"), "revoked")

    def test_revoked_beats_expired(self):
        self.assertEqual(self.decide(as_of="2026-09-01T00:00:00Z", revoked="2026-04-01T00:00:00Z"), "revoked")

    def test_not_found_before_issuance(self):
        self.assertEqual(self.decide(as_of="2026-01-31T23:59:59Z"), "not_found")
        unknown = evaluate_verification(credential=None, public_key_b64=None, learner=None, earliest_effective_revocation=None,
                                        as_of="2026-03-01T00:00:00Z", presented_hash=None, claimed_name=None, claimed_email=None,
                                        claimed_dob=None)
        self.assertEqual(unknown["result_status"], "not_found")

    def test_altered_hash_and_altered_payload_are_both_detected(self):
        altered_hash = {**self.credential, "payload_hash": "0" * 64}
        altered_payload = {**self.credential, "payload_json": self.credential["payload_json"].replace("000001", "000009")}
        self.assertEqual(self.decide(credential=altered_hash), "tampered")
        self.assertEqual(self.decide(credential=altered_payload), "tampered")

    def test_presented_hash_mismatch_is_tampered_and_match_is_valid(self):
        self.assertEqual(self.decide(presented="f" * 64), "tampered")
        self.assertEqual(self.decide(presented=self.credential["payload_hash"].upper()), "valid")

    def test_unknown_signing_key_is_tampered(self):
        result = evaluate_verification(credential=self.credential, public_key_b64=None, learner=None, earliest_effective_revocation=None,
                                       as_of="2026-03-01T00:00:00Z", presented_hash=None, claimed_name=None, claimed_email=None, claimed_dob=None)
        self.assertEqual(result["result_status"], "tampered")

    def test_decision_is_deterministic(self):
        outcomes = {self.decide(as_of="2026-05-05T05:05:05Z", revoked="2026-06-01T00:00:00Z") for _ in range(25)}
        self.assertEqual(outcomes, {"valid"})


if __name__ == "__main__":
    unittest.main()
