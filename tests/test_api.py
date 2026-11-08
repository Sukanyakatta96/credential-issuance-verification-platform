import sqlite3
import unittest

from app.services import verification
from tests.support import TEST_PASSWORD, World


class ApiTestCase(unittest.TestCase):
    world_options: dict = {}

    def setUp(self):
        self.w = World(**self.world_options)
        self.client = self.w.client
        self.admin = self.w.login("admin@x.example")
        self.learner_id = self.w.learner["learner_id"]
        self.rule_id = self.w.rule["rule_id"]

    def tearDown(self):
        self.w.close()

    def qualify(self, scores=(80, 75), learner_id=None):
        for index, score in enumerate(scores):
            self.w.complete(learner_id or self.learner_id, index, score)

    def issue(self, learner_id=None, headers=None):
        return self.client.post("/api/credentials", json={"learner_id": learner_id or self.learner_id, "rule_id": self.rule_id},
                                headers=headers or self.admin)

    def issue_ok(self, **kwargs):
        self.qualify(**{k: v for k, v in kwargs.items() if k in ("scores", "learner_id")})
        response = self.issue(learner_id=kwargs.get("learner_id"))
        self.assertEqual(response.status_code, 201, response.get_json())
        return response.get_json()

    def verify(self, credential_id, **extra):
        return self.client.post("/api/public/verify", json={"credential_id": credential_id, **extra})


class AuthenticationTests(ApiTestCase):
    def test_login_and_me(self):
        response = self.client.post("/api/auth/login", json={"email": "admin@x.example", "password": TEST_PASSWORD})
        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        me = self.client.get("/api/auth/me", headers={"Authorization": "Bearer " + body["token"]})
        self.assertEqual(me.get_json()["role"], "academic_admin")
        self.assertNotIn("password_hash", me.get_json())

    def test_bad_credentials_unknown_user_and_missing_token(self):
        for email, password in (("admin@x.example", "wrong-password-1"), ("nobody@x.example", TEST_PASSWORD)):
            response = self.client.post("/api/auth/login", json={"email": email, "password": password})
            self.assertEqual((response.status_code, response.get_json()["error"]["code"]), (401, "INVALID_CREDENTIALS"))
        self.assertEqual(self.client.get("/api/learners").status_code, 401)
        self.assertEqual(self.client.get("/api/learners", headers={"Authorization": "Bearer not.a.token"}).status_code, 401)

    def test_tampered_token_is_rejected(self):
        token = self.admin["Authorization"].split()[1]
        forged = token[:-3] + ("AAA" if not token.endswith("AAA") else "BBB")
        self.assertEqual(self.client.get("/api/auth/me", headers={"Authorization": "Bearer " + forged}).status_code, 401)

    def test_lockout_after_repeated_failures(self):
        for _ in range(5):
            self.client.post("/api/auth/login", json={"email": "admin@x.example", "password": "wrong-password-1"})
        response = self.client.post("/api/auth/login", json={"email": "admin@x.example", "password": TEST_PASSWORD})
        self.assertEqual((response.status_code, response.get_json()["error"]["code"]), (429, "LOGIN_LOCKED"))

    def test_deactivated_user_loses_access_immediately(self):
        platform = self.w.login("platform@x.example")
        self.assertEqual(self.client.patch(f"/api/users/{self.w.support['user_id']}", json={"is_active": False}, headers=platform).status_code, 200)
        support = {"Authorization": "Bearer " + self.client.post("/api/auth/login", json={"email": "support@x.example", "password": TEST_PASSWORD}).get_json().get("token", "x")}
        self.assertEqual(self.client.get("/api/learners", headers=support).status_code, 401)

    def test_change_password(self):
        bad = self.client.post("/api/auth/change-password", json={"current_password": "nope-nope-nope", "new_password": "A-brand-new-pass1"}, headers=self.admin)
        self.assertEqual(bad.status_code, 403)
        weak = self.client.post("/api/auth/change-password", json={"current_password": TEST_PASSWORD, "new_password": "short"}, headers=self.admin)
        self.assertEqual(weak.get_json()["error"]["code"], "WEAK_PASSWORD")
        ok = self.client.post("/api/auth/change-password", json={"current_password": TEST_PASSWORD, "new_password": "A-brand-new-pass1"}, headers=self.admin)
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(self.client.post("/api/auth/login", json={"email": "admin@x.example", "password": "A-brand-new-pass1"}).status_code, 200)

    def test_passwords_are_stored_hashed(self):
        stored = self.w.db.execute("SELECT password_hash FROM app_user WHERE email = 'admin@x.example'").fetchone()[0]
        self.assertNotIn(TEST_PASSWORD, stored)
        self.assertTrue(stored.startswith(("scrypt:", "pbkdf2:")))


class PermissionTests(ApiTestCase):
    def test_role_matrix(self):
        learner_id, rule_id = self.learner_id, self.rule_id
        cred = self.issue_ok()["credential_id"]
        sessions = {r: self.w.login(e) for r, e in {"admin": "admin@x.example", "platform": "platform@x.example", "support": "support@x.example",
                                                     "instructor": "ines@uni.example", "learner": "ada@x.example"}.items()}
        matrix = [
            ("GET", "/api/learners", {"admin": 200, "platform": 200, "support": 200, "instructor": 403, "learner": 403}),
            ("GET", f"/api/learners/{learner_id}", {"admin": 200, "support": 200, "instructor": 403, "learner": 200}),
            ("GET", f"/api/learners/{self.w.namesake['learner_id']}", {"admin": 200, "learner": 403}),
            ("GET", "/api/users", {"admin": 403, "platform": 200, "support": 403, "instructor": 403, "learner": 403}),
            ("GET", "/api/audit", {"admin": 200, "support": 200, "platform": 200, "instructor": 403, "learner": 403}),
            ("GET", "/api/integrity/scan", {"admin": 200, "platform": 200, "support": 403, "instructor": 403, "learner": 403}),
            ("GET", "/api/revocations", {"admin": 200, "support": 200, "instructor": 403, "learner": 403}),
            ("GET", "/api/eligibility/pending", {"admin": 200, "support": 200, "instructor": 403, "learner": 403}),
            ("GET", f"/api/credentials/{cred}", {"admin": 200, "support": 200, "instructor": 403, "learner": 200}),
            ("GET", "/api/reports/dashboard", {"admin": 200, "support": 200, "instructor": 403, "learner": 403}),
            ("GET", "/api/rules", {"admin": 200, "instructor": 200, "learner": 403}),
            ("GET", "/api/issuers", {"admin": 200, "support": 200, "instructor": 403, "learner": 403}),
            ("GET", "/api/verifications", {"admin": 200, "support": 200, "instructor": 403, "learner": 200}),
        ]
        for method, path, expectations in matrix:
            for role, expected in expectations.items():
                response = self.client.open(path, method=method, headers=sessions[role])
                self.assertEqual(response.status_code, expected, f"{role} {method} {path}: {response.get_json()}")
        writes = [
            ("/api/credentials", {"learner_id": learner_id, "rule_id": rule_id}, {"support": 403, "instructor": 403, "learner": 403}),
            (f"/api/credentials/{cred}/revoke", {"reason_code": "fraud"}, {"support": 403, "instructor": 403, "learner": 403}),
            ("/api/issuers", {"name": "Illegal Issuer"}, {"admin": 403, "support": 403, "learner": 403}),
            ("/api/courses", {"title": "x"}, {"support": 403, "instructor": 403, "learner": 403}),
            ("/api/learners", {"full_name": "x"}, {"support": 403, "instructor": 403, "learner": 403}),
        ]
        for path, body, expectations in writes:
            for role, expected in expectations.items():
                self.assertEqual(self.client.post(path, json=body, headers=sessions[role]).status_code, expected, f"{role} POST {path}")

    def test_learner_sees_only_own_credentials_and_instructor_only_own_courses(self):
        self.issue_ok()
        other = self.w.complete(self.w.namesake["learner_id"], 0, 90)
        self.w.complete(self.w.namesake["learner_id"], 1, 90)
        self.assertEqual(self.issue(learner_id=self.w.namesake["learner_id"]).status_code, 201)
        learner = self.w.login("ada@x.example")
        items = self.client.get("/api/credentials", headers=learner).get_json()["items"]
        self.assertEqual({i["learner_id"] for i in items}, {self.learner_id})
        spoof = self.client.get(f"/api/credentials?learner_id={self.w.namesake['learner_id']}", headers=learner).get_json()["items"]
        self.assertEqual({i["learner_id"] for i in spoof}, {self.learner_id})
        completions = self.client.get("/api/completions", headers=learner).get_json()["items"]
        self.assertTrue(completions and all(c["learner_id"] == self.learner_id for c in completions))
        foreign = self.client.get(f"/api/completions/{other['completion_id']}", headers=learner)
        self.assertEqual(foreign.status_code, 403)
        other_instructor = self.w.login("omar@uni.example")
        self.assertEqual(self.client.get(f"/api/completions/{other['completion_id']}", headers=other_instructor).status_code, 403)
        self.assertEqual(self.client.get("/api/completions", headers=other_instructor).get_json()["total"], 0)


class IssuanceTests(ApiTestCase):
    def test_issue_credential_end_to_end(self):
        credential = self.issue_ok()
        self.assertRegex(credential["credential_id"], r"^CRD-\d{4}-000001$")
        self.assertEqual(credential["status"], "active")
        self.assertEqual(len(credential["payload_hash"]), 64)
        self.assertEqual(len(credential["completions"]), 2)
        self.assertEqual(credential["issuer_id"], self.w.issuer["issuer_id"])
        self.assertTrue(any(e["action"] == "credential.issued" for e in credential["audit_trail"]))
        self.assertIsNotNone(credential["expires_at"])

    def test_requirements_are_enforced_with_explanations(self):
        self.w.complete(self.learner_id, 1, 90)
        self.w.complete(self.learner_id, 2, 90)
        response = self.issue()
        body = response.get_json()
        self.assertEqual((response.status_code, body["error"]["code"]), (422, "NOT_ELIGIBLE"))
        failed = [c["code"] for c in body["error"]["details"]["checks"] if not c["passed"]]
        self.assertEqual(failed, ["MANDATORY_COURSES"])
        self.assertEqual(self.w.db.execute("SELECT COUNT(*) FROM credential").fetchone()[0], 0)

    def test_unissued_and_duplicate_requests(self):
        self.issue_ok()
        again = self.issue()
        self.assertEqual(again.status_code, 422)
        self.assertEqual(self.w.db.execute("SELECT COUNT(*) FROM credential").fetchone()[0], 1)

    def test_validation_and_unknown_references(self):
        self.assertEqual(self.client.post("/api/credentials", json={"learner_id": "bad", "rule_id": self.rule_id}, headers=self.admin).status_code, 400)
        self.assertEqual(self.client.post("/api/credentials", json={"learner_id": "LRN-999999", "rule_id": self.rule_id}, headers=self.admin).status_code, 404)
        self.assertEqual(self.client.post("/api/credentials", json={"learner_id": self.learner_id, "rule_id": "RUL-999999"}, headers=self.admin).status_code, 404)
        self.assertEqual(self.client.post("/api/credentials", json={"learner_id": self.learner_id, "rule_id": self.rule_id, "x": 1}, headers=self.admin).status_code, 400)

    def test_ids_are_sequential_and_unique(self):
        first = self.issue_ok()
        self.w.complete(self.w.namesake["learner_id"], 0, 90)
        self.w.complete(self.w.namesake["learner_id"], 1, 90)
        second = self.issue(learner_id=self.w.namesake["learner_id"]).get_json()
        self.assertEqual(int(second["credential_id"][-6:]), int(first["credential_id"][-6:]) + 1)

    def test_suspended_learner_and_retired_rule_cannot_be_issued(self):
        self.qualify()
        self.client.patch(f"/api/learners/{self.learner_id}", json={"status": "suspended"}, headers=self.admin)
        self.assertEqual(self.issue().get_json()["error"]["code"], "NOT_ELIGIBLE")
        self.client.patch(f"/api/learners/{self.learner_id}", json={"status": "active"}, headers=self.admin)
        self.assertEqual(self.client.post(f"/api/rules/{self.rule_id}/retire", headers=self.admin).status_code, 200)
        self.assertEqual(self.issue().get_json()["error"]["code"], "NOT_ELIGIBLE")

    def test_reissue_policy_after_revocation(self):
        credential = self.issue_ok()
        self.client.post(f"/api/credentials/{credential['credential_id']}/revoke", json={"reason_code": "fraud"}, headers=self.admin)
        blocked = self.issue()
        self.assertEqual(blocked.status_code, 422)
        failed = [c["code"] for c in blocked.get_json()["error"]["details"]["checks"] if not c["passed"]]
        self.assertEqual(failed, ["NOT_BLOCKED_BY_REVOCATION"])

        self.w.complete(self.w.namesake["learner_id"], 0, 90)
        self.w.complete(self.w.namesake["learner_id"], 1, 90)
        other = self.issue(learner_id=self.w.namesake["learner_id"]).get_json()
        self.client.post(f"/api/credentials/{other['credential_id']}/revoke", json={"reason_code": "issued_in_error"}, headers=self.admin)
        reissued = self.issue(learner_id=self.w.namesake["learner_id"])
        self.assertEqual(reissued.status_code, 201)
        self.assertNotEqual(reissued.get_json()["credential_id"], other["credential_id"])

    def test_pending_queue_reflects_actual_eligibility(self):
        self.qualify()
        queue = self.client.get("/api/eligibility/pending", headers=self.admin).get_json()
        self.assertEqual([i["learner_id"] for i in queue["items"]], [self.learner_id])
        self.issue()
        self.assertEqual(self.client.get("/api/eligibility/pending", headers=self.admin).get_json()["total"], 0)

    def test_issuance_is_atomic_when_signing_key_is_misconfigured(self):
        self.qualify()
        self.w.app.config["APP_CONFIG"] = self.w.cfg.__class__(**{**self.w.cfg.__dict__, "signing_master_secret": "a-different-master-secret-0123456789"})
        response = self.issue()
        self.assertEqual(response.get_json()["error"]["code"], "SIGNING_KEY_MISMATCH")
        self.assertEqual(self.w.db.execute("SELECT COUNT(*) FROM credential").fetchone()[0], 0)
        self.assertEqual(self.w.db.execute("SELECT COUNT(*) FROM id_counter WHERE counter_name = 'credential'").fetchone()[0], 0)


class VerificationTests(ApiTestCase):
    def test_valid_revoked_flow_and_record_keeping(self):
        credential_id = self.issue_ok()["credential_id"]
        result = self.verify(credential_id).get_json()
        self.assertEqual((result["result_status"], result["identity_status"]), ("valid", "not_requested"))
        self.assertRegex(result["verification_id"], r"^VER-\d{4}-000001$")
        self.client.post(f"/api/credentials/{credential_id}/revoke", json={"reason_code": "learner_request"}, headers=self.admin)
        self.assertEqual(self.verify(credential_id).get_json()["result_status"], "revoked")
        self.assertEqual(self.w.db.execute("SELECT COUNT(*) FROM verification_request").fetchone()[0], 2)

    def test_identity_never_relies_on_name_alone_and_masks_holder(self):
        credential_id = self.issue_ok()["credential_id"]
        name_only = self.verify(credential_id, claimed_name="Ada Lovelace").get_json()
        self.assertEqual(name_only["identity_status"], "insufficient_identifiers")
        self.assertTrue(name_only["credential"]["holder_name_masked"])
        self.assertEqual(name_only["credential"]["holder_name"], "A*** L***")
        namesake = self.verify(credential_id, claimed_name="Ada Lovelace", claimed_email="ada2@x.example").get_json()
        self.assertEqual(namesake["identity_status"], "mismatch")
        wrong_dob = self.verify(credential_id, claimed_name="Ada Lovelace", claimed_dob="1985-03-02").get_json()
        self.assertEqual(wrong_dob["identity_status"], "mismatch")
        matched = self.verify(credential_id, claimed_name="ada  lovelace", claimed_email="ADA@x.example").get_json()
        self.assertEqual(matched["identity_status"], "matched")
        self.assertEqual(matched["credential"]["holder_name"], "Ada Lovelace")

    def test_unknown_credential_and_malformed_input(self):
        self.assertEqual(self.verify("CRD-2026-999999").get_json()["result_status"], "not_found")
        self.assertEqual(self.verify("not-an-id").status_code, 400)
        self.assertEqual(self.verify("CRD-2026-000001", presented_hash="zz").status_code, 400)
        self.assertEqual(self.verify("CRD-2026-000001", claimed_dob="1990-13-45").status_code, 400)
        self.assertEqual(self.client.post("/api/public/verify", data="not json", content_type="application/json").status_code, 400)

    def test_presented_hash_mismatch_is_tampered(self):
        credential = self.issue_ok()
        self.assertEqual(self.verify(credential["credential_id"], presented_hash="a" * 64).get_json()["result_status"], "tampered")
        self.assertEqual(self.verify(credential["credential_id"], presented_hash=credential["payload_hash"]).get_json()["result_status"], "valid")

    def test_database_level_tampering_is_blocked_and_still_detected_if_triggers_are_bypassed(self):
        credential = self.issue_ok()
        cid = credential["credential_id"]
        with self.assertRaises(sqlite3.IntegrityError):
            self.w.db.execute("UPDATE credential SET payload_hash = ? WHERE credential_id = ?", ("0" * 64, cid))
        self.w.db.execute("DROP TRIGGER trg_credential_immutable")
        self.w.db.execute("UPDATE credential SET payload_hash = ? WHERE credential_id = ?", ("0" * 64, cid))
        self.assertEqual(self.verify(cid).get_json()["result_status"], "tampered")
        scan = self.client.get("/api/integrity/scan", headers=self.admin).get_json()
        self.assertEqual(scan["counts"].get("payload_hash_altered"), 1)

    def test_forged_signature_by_wrong_key_is_tampered(self):
        credential = self.issue_ok()
        from app import crypto
        forged = crypto.sign_hash("an-attacker-controlled-secret-0123456789", credential["key_id"], credential["payload_hash"])
        self.w.db.execute("DROP TRIGGER trg_credential_immutable")
        self.w.db.execute("UPDATE credential SET signature_b64 = ? WHERE credential_id = ?", (forged, credential["credential_id"]))
        self.assertEqual(self.verify(credential["credential_id"]).get_json()["result_status"], "tampered")

    def test_expiry_is_evaluated_at_the_requested_time(self):
        credential = self.issue_ok()
        snapshot = verification.load_snapshot(self.w.db, credential["credential_id"])
        far_future = "2099-01-01T00:00:00Z"
        outcome = verification._evaluate(snapshot, far_future, None, None, None, None)
        self.assertEqual(outcome["result_status"], "expired")
        self.assertEqual(verification._evaluate(snapshot, credential["issued_at"], None, None, None, None)["result_status"], "valid")

    def test_replay_is_reproducible_even_after_later_revocation(self):
        credential_id = self.issue_ok()["credential_id"]
        recorded = self.verify(credential_id).get_json()
        self.client.post(f"/api/credentials/{credential_id}/revoke", json={"reason_code": "issued_in_error"}, headers=self.admin)
        replay = self.client.post(f"/api/verifications/{recorded['verification_id']}/replay", headers=self.w.login("support@x.example")).get_json()
        self.assertTrue(replay["reproducible"], replay)
        self.assertEqual(replay["replayed"]["result_status"], "valid")
        self.assertEqual(self.verify(credential_id).get_json()["result_status"], "revoked")

    def test_same_second_ordering_of_check_and_revocation_stays_consistent(self):
        credential_id = self.issue_ok()["credential_id"]
        before = self.verify(credential_id).get_json()
        self.client.post(f"/api/credentials/{credential_id}/revoke", json={"reason_code": "fraud"}, headers=self.admin)
        after = self.verify(credential_id).get_json()
        self.assertEqual((before["result_status"], after["result_status"]), ("valid", "revoked"))
        for result in (before, after):
            replay = self.client.post(f"/api/verifications/{result['verification_id']}/replay", headers=self.admin).get_json()
            self.assertTrue(replay["reproducible"], replay)
        self.assertLess(before["requested_at"], self.w.db.execute("SELECT effective_at FROM revocation").fetchone()[0])

    def test_replay_exposes_a_wrong_historical_result(self):
        credential_id = self.issue_ok()["credential_id"]
        self.client.post(f"/api/credentials/{credential_id}/revoke", json={"reason_code": "fraud"}, headers=self.admin)
        revoked_at = self.w.db.execute("SELECT effective_at FROM revocation").fetchone()[0]
        self.w.db.execute("INSERT INTO verification_request (verification_id, presented_credential_id, credential_id, requested_at, channel, requester_type, "
                          "result_status, identity_status, integrity_ok) VALUES ('VER-2026-900001', ?, ?, ?, 'public_api', 'employer', 'valid', 'not_requested', 1)",
                          (credential_id, credential_id, revoked_at))
        replay = self.client.post("/api/verifications/VER-2026-900001/replay", headers=self.admin).get_json()
        self.assertFalse(replay["reproducible"])
        self.assertEqual(replay["replayed"]["result_status"], "revoked")
        scan = self.client.get("/api/integrity/scan", headers=self.admin).get_json()
        self.assertEqual(scan["counts"].get("revoked_credential_verified_active"), 1)

    def test_staff_verification_records_the_user_and_shows_full_name(self):
        credential_id = self.issue_ok()["credential_id"]
        support = self.w.login("support@x.example")
        result = self.client.post("/api/verifications", json={"credential_id": credential_id}, headers=support).get_json()
        self.assertEqual(result["credential"]["holder_name"], "Ada Lovelace")
        row = self.w.db.execute("SELECT channel, processed_by FROM verification_request WHERE verification_id = ?", (result["verification_id"],)).fetchone()
        self.assertEqual((row["channel"], row["processed_by"]), ("support_desk", self.w.support["user_id"]))
        self.assertEqual(self.client.post("/api/verifications", json={"credential_id": credential_id}, headers=self.w.login("ada@x.example")).status_code, 403)

    def test_public_endpoint_is_rate_limited(self):
        self.w.close()
        self.w = World(public_rate_limit_per_minute=3)
        self.client = self.w.client
        codes = [self.verify("CRD-2026-000001").status_code for _ in range(5)]
        self.assertEqual(codes, [200, 200, 200, 429, 429])

    def test_public_signed_document_allows_offline_verification(self):
        import base64
        credential = self.issue_ok()
        document = self.client.get(f"/api/public/credentials/{credential['credential_id']}/document").get_json()
        keys = self.client.get(f"/api/public/issuers/{credential['issuer_id']}/keys").get_json()["keys"]
        public = next(k["public_key_b64"] for k in keys if k["key_id"] == document["key_id"])
        from app import crypto
        self.assertEqual(crypto.payload_hash(document["payload_json"]), document["payload_hash"])
        self.assertTrue(crypto.verify_signature(public, document["payload_hash"], document["signature_b64"]))
        self.assertEqual(len(base64.b64decode(public)), 32)


class RevocationAndAuditTests(ApiTestCase):
    def test_revoke_records_event_and_blocks_second_revocation(self):
        cid = self.issue_ok()["credential_id"]
        response = self.client.post(f"/api/credentials/{cid}/revoke", json={"reason_code": "academic_misconduct", "reason_detail": "x"}, headers=self.admin)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json()["revocation_id"], f"REV-{cid}-01")
        again = self.client.post(f"/api/credentials/{cid}/revoke", json={"reason_code": "fraud"}, headers=self.admin)
        self.assertEqual((again.status_code, again.get_json()["error"]["code"]), (409, "ALREADY_REVOKED"))
        detail = self.client.get(f"/api/credentials/{cid}", headers=self.admin).get_json()
        self.assertEqual((detail["status"], detail["effective_status"]), ("revoked", "revoked"))
        self.assertEqual([e["action"] for e in detail["audit_trail"]], ["credential.issued", "credential.revoked"])
        self.assertEqual(self.client.post(f"/api/credentials/{cid}/revoke", json={"reason_code": "bogus"}, headers=self.admin).status_code, 400)
        self.assertEqual(self.client.post("/api/credentials/CRD-2026-999999/revoke", json={"reason_code": "fraud"}, headers=self.admin).status_code, 404)

    def test_history_cannot_be_rewritten(self):
        cid = self.issue_ok()["credential_id"]
        self.client.post(f"/api/credentials/{cid}/revoke", json={"reason_code": "fraud"}, headers=self.admin)
        db = self.w.db
        statements = [
            "UPDATE audit_event SET action = 'x' WHERE seq = 1", "DELETE FROM audit_event",
            "UPDATE revocation SET reason_code = 'rule_change'", "DELETE FROM revocation",
            "UPDATE credential SET status = 'active'", "DELETE FROM credential",
            "UPDATE verification_request SET result_status = 'valid'", "DELETE FROM assessment_attempt",
            "UPDATE completion_record SET progress_pct = 0 WHERE status = 'completed'",
        ]
        self.verify(cid)
        for sql in statements:
            with self.assertRaises(sqlite3.IntegrityError, msg=sql):
                db.execute(sql)

    def test_status_cannot_become_revoked_without_a_revocation_record(self):
        cid = self.issue_ok()["credential_id"]
        with self.assertRaises(sqlite3.IntegrityError):
            self.w.db.execute("UPDATE credential SET status = 'revoked' WHERE credential_id = ?", (cid,))

    def test_audit_chain_verification_detects_tampering(self):
        self.issue_ok()
        self.assertTrue(self.client.get("/api/audit/verify-chain", headers=self.admin).get_json()["valid"])
        self.w.db.execute("DROP TRIGGER trg_audit_no_update")
        self.w.db.execute("UPDATE audit_event SET details_json = '{\"forged\":true}' WHERE seq = 3")
        result = self.client.get("/api/audit/verify-chain", headers=self.admin).get_json()
        self.assertFalse(result["valid"])
        self.assertEqual(result["first_broken_event"], "AUD-000000003")
        scan = self.client.get("/api/integrity/scan", headers=self.admin).get_json()
        self.assertIn("audit_chain_broken", scan["counts"])

    def test_audit_list_filters(self):
        cid = self.issue_ok()["credential_id"]
        items = self.client.get(f"/api/audit?q={cid}&action=credential.issued", headers=self.admin).get_json()
        self.assertEqual(items["total"], 1)
        self.assertEqual(items["items"][0]["entity_id"], cid)


class CompletionTests(ApiTestCase):
    def enroll(self, course_index=0, learner_id=None):
        response = self.client.post("/api/completions", json={"learner_id": learner_id or self.learner_id, "course_id": self.w.courses[course_index]["course_id"]}, headers=self.admin)
        self.assertEqual(response.status_code, 201, response.get_json())
        return response.get_json()

    def test_lifecycle_and_derived_values(self):
        record = self.enroll()
        cid = record["completion_id"]
        self.assertEqual((record["status"], record["progress_pct"]), ("enrolled", 0))
        self.assertEqual(self.client.post("/api/completions", json={"learner_id": self.learner_id, "course_id": self.w.courses[0]["course_id"]}, headers=self.admin).status_code, 409)
        instructor = self.w.login("ines@uni.example")
        early = self.client.post(f"/api/completions/{cid}/assessments", json={"score": 90}, headers=instructor)
        self.assertEqual(early.get_json()["error"]["code"], "COURSE_NOT_FINISHED")
        self.assertEqual(self.client.post(f"/api/completions/{cid}/progress", json={"progress_pct": 60}, headers=instructor).get_json()["status"], "in_progress")
        self.assertEqual(self.client.post(f"/api/completions/{cid}/progress", json={"progress_pct": 40}, headers=instructor).status_code, 409)
        self.client.post(f"/api/completions/{cid}/progress", json={"progress_pct": 100}, headers=instructor)
        first = self.client.post(f"/api/completions/{cid}/assessments", json={"score": 55.5}, headers=instructor).get_json()
        self.assertEqual((first["status"], first["final_score"], first["attempts_used"]), ("in_progress", 55.5, 1))
        second = self.client.post(f"/api/completions/{cid}/assessments", json={"score": 40}, headers=instructor).get_json()
        self.assertEqual((second["status"], second["final_score"], second["finalized_at"] is not None), ("failed", 55.5, True))
        self.assertEqual(self.client.post(f"/api/completions/{cid}/assessments", json={"score": 99}, headers=instructor).get_json()["error"]["code"], "COMPLETION_CLOSED")
        self.assertEqual([a["attempt_id"] for a in second["attempts"]], [f"ASM-{cid[4:]}-01", f"ASM-{cid[4:]}-02"])

    def test_pass_boundary_and_validation(self):
        cid = self.enroll()["completion_id"]
        self.client.post(f"/api/completions/{cid}/progress", json={"progress_pct": 100}, headers=self.admin)
        self.assertEqual(self.client.post(f"/api/completions/{cid}/assessments", json={"score": 101}, headers=self.admin).status_code, 400)
        self.assertEqual(self.client.post(f"/api/completions/{cid}/assessments", json={"score": -1}, headers=self.admin).status_code, 400)
        self.assertEqual(self.client.post(f"/api/completions/{cid}/assessments", json={"score": "abc"}, headers=self.admin).status_code, 400)
        done = self.client.post(f"/api/completions/{cid}/assessments", json={"score": 60}, headers=self.admin).get_json()
        self.assertEqual(done["status"], "completed")

    def test_instructor_cannot_touch_other_instructors_courses(self):
        cid = self.enroll()["completion_id"]
        other = self.w.login("omar@uni.example")
        for path, body in ((f"/api/completions/{cid}/progress", {"progress_pct": 10}), (f"/api/completions/{cid}/assessments", {"score": 80})):
            self.assertEqual(self.client.post(path, json=body, headers=other).status_code, 403)

    def test_learner_can_withdraw_only_own_enrolment(self):
        own = self.enroll()["completion_id"]
        foreign = self.enroll(learner_id=self.w.namesake["learner_id"])["completion_id"]
        learner = self.w.login("ada@x.example")
        self.assertEqual(self.client.post(f"/api/completions/{foreign}/withdraw", headers=learner).status_code, 403)
        withdrawn = self.client.post(f"/api/completions/{own}/withdraw", headers=learner).get_json()
        self.assertEqual((withdrawn["status"], withdrawn["finalized_at"] is not None), ("withdrawn", True))
        self.assertEqual(self.client.post(f"/api/completions/{own}/withdraw", headers=learner).status_code, 409)

    def test_enrolment_rules(self):
        self.client.patch(f"/api/courses/{self.w.courses[2]['course_id']}", json={"status": "archived"}, headers=self.admin)
        self.assertEqual(self.client.post("/api/completions", json={"learner_id": self.learner_id, "course_id": self.w.courses[2]["course_id"]}, headers=self.admin).get_json()["error"]["code"], "COURSE_NOT_ACTIVE")
        self.client.patch(f"/api/learners/{self.learner_id}", json={"status": "suspended"}, headers=self.admin)
        self.assertEqual(self.client.post("/api/completions", json={"learner_id": self.learner_id, "course_id": self.w.courses[0]["course_id"]}, headers=self.admin).get_json()["error"]["code"], "LEARNER_NOT_ACTIVE")


class DirectoryTests(ApiTestCase):
    def test_learner_registration_validation_and_duplicates(self):
        good = {"full_name": "Grace Hopper", "email": "Grace@X.example", "date_of_birth": "1985-12-09", "country_code": "us"}
        created = self.client.post("/api/learners", json=good, headers=self.admin)
        self.assertEqual(created.status_code, 201)
        self.assertEqual((created.get_json()["email"], created.get_json()["country_code"]), ("grace@x.example", "US"))
        self.assertEqual(self.client.post("/api/learners", json=good, headers=self.admin).get_json()["error"]["code"], "DUPLICATE_EMAIL")
        for bad in ({**good, "email": "nope"}, {**good, "date_of_birth": "1985-02-31"}, {**good, "country_code": "USA"}, {"full_name": "x"}):
            response = self.client.post("/api/learners", json={**bad, "email": bad.get("email", "other@x.example")}, headers=self.admin)
            self.assertEqual(response.status_code, 400)
            self.assertIn("details", response.get_json()["error"])

    def test_duplicate_names_are_reported_but_allowed(self):
        detail = self.client.get(f"/api/learners/{self.learner_id}", headers=self.admin).get_json()
        self.assertEqual(detail["same_name_count"], 1)
        listing = self.client.get("/api/learners?q=Lovelace", headers=self.admin).get_json()
        self.assertEqual(listing["total"], 2)
        self.assertTrue(all(i["same_name_count"] == 1 for i in listing["items"]))

    def test_search_and_pagination_are_injection_safe(self):
        for q in ("' OR 1=1 --", "%", "_", "'; DROP TABLE learner; --"):
            response = self.client.get("/api/learners", query_string={"q": q}, headers=self.admin)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.get_json()["total"], 0, q)
        self.assertEqual(self.w.db.execute("SELECT COUNT(*) FROM learner").fetchone()[0], 2)
        page = self.client.get("/api/learners?page=2&page_size=1", headers=self.admin).get_json()
        self.assertEqual((page["page"], len(page["items"]), page["total"]), (2, 1, 2))
        self.assertEqual(self.client.get("/api/learners?page=abc", headers=self.admin).status_code, 400)
        self.assertEqual(self.client.get("/api/learners?page_size=100000", headers=self.admin).get_json()["page_size"], 200)

    def test_rule_creation_validation(self):
        base = {"title": "Another Rule", "credential_type": "certificate", "min_courses_required": 2, "min_avg_score": 60, "min_course_score": 50,
                "validity_months": None, "issuer_id": self.w.issuer["issuer_id"],
                "courses": [{"course_id": self.w.courses[0]["course_id"], "is_mandatory": True}, {"course_id": self.w.courses[1]["course_id"], "is_mandatory": False}]}
        self.assertEqual(self.client.post("/api/rules", json=base, headers=self.admin).status_code, 201)
        self.assertEqual(self.client.post("/api/rules", json=base, headers=self.admin).status_code, 409)
        title = {**base, "title": "Third Rule"}
        cases = {"INVALID_THRESHOLD": {**title, "min_courses_required": 3}, "UNKNOWN_COURSE": {**title, "courses": [{"course_id": "CRS-009999", "is_mandatory": False}], "min_courses_required": 1},
                 "DUPLICATE_COURSE": {**title, "courses": base["courses"] + [base["courses"][0]]}, "INVALID_ISSUER": {**title, "issuer_id": "ISS-099"}}
        for code, body in cases.items():
            self.assertEqual(self.client.post("/api/rules", json=body, headers=self.admin).get_json()["error"]["code"], code)

    def test_course_creation_and_update(self):
        body = {"title": "Brand New", "category": "Data", "level": "advanced", "credit_hours": 12, "pass_mark": 65, "max_attempts": 3, "instructor_id": "INS-0002"}
        created = self.client.post("/api/courses", json=body, headers=self.admin)
        self.assertEqual(created.status_code, 201)
        self.assertEqual(self.client.post("/api/courses", json={**body, "instructor_id": "INS-0099"}, headers=self.admin).get_json()["error"]["code"], "UNKNOWN_INSTRUCTOR")
        self.assertEqual(self.client.post("/api/courses", json={**body, "pass_mark": 20}, headers=self.admin).status_code, 400)
        updated = self.client.patch(f"/api/courses/{created.get_json()['course_id']}", json={"status": "archived"}, headers=self.admin)
        self.assertEqual(updated.get_json()["status"], "archived")
        self.assertEqual(self.client.patch(f"/api/courses/{created.get_json()['course_id']}", json={"pass_mark": 10}, headers=self.admin).status_code, 400)


class IssuerLifecycleTests(ApiTestCase):
    def test_key_rotation_keeps_old_credentials_verifiable(self):
        platform = self.w.login("platform@x.example")
        old = self.issue_ok()
        rotated = self.client.post(f"/api/issuers/{old['issuer_id']}/rotate-key", headers=platform).get_json()
        self.assertEqual([k["status"] for k in rotated["keys"]], ["rotated", "active"])
        self.assertEqual(self.verify(old["credential_id"]).get_json()["result_status"], "valid")
        self.w.complete(self.w.namesake["learner_id"], 0, 90)
        self.w.complete(self.w.namesake["learner_id"], 1, 90)
        new = self.issue(learner_id=self.w.namesake["learner_id"]).get_json()
        self.assertEqual(new["key_id"], rotated["keys"][1]["key_id"])
        self.assertEqual(self.verify(new["credential_id"]).get_json()["result_status"], "valid")

    def test_retiring_an_issuer_moves_rules_and_preserves_history(self):
        platform = self.w.login("platform@x.example")
        old = self.issue_ok()
        retired = self.client.post(f"/api/issuers/{self.w.issuer['issuer_id']}/retire", json={"successor_issuer_id": self.w.issuer2["issuer_id"]}, headers=platform)
        self.assertEqual(retired.status_code, 200)
        self.assertEqual(retired.get_json()["status"], "retired")
        rule = self.client.get(f"/api/rules/{self.rule_id}", headers=self.admin).get_json()
        self.assertEqual([a["issuer_id"] for a in rule["issuer_history"]], [self.w.issuer["issuer_id"], self.w.issuer2["issuer_id"]])
        self.assertIsNotNone(rule["issuer_history"][0]["effective_to"])
        verification_result = self.verify(old["credential_id"]).get_json()
        self.assertEqual(verification_result["result_status"], "valid")
        self.assertTrue(verification_result["notes"])
        self.w.complete(self.w.namesake["learner_id"], 0, 90)
        self.w.complete(self.w.namesake["learner_id"], 1, 90)
        self.assertEqual(self.issue(learner_id=self.w.namesake["learner_id"]).get_json()["issuer_id"], self.w.issuer2["issuer_id"])

    def test_issuer_change_validation(self):
        platform = self.w.login("platform@x.example")
        iid = self.w.issuer["issuer_id"]
        self.assertEqual(self.client.post(f"/api/issuers/{iid}/retire", json={"successor_issuer_id": iid}, headers=platform).get_json()["error"]["code"], "INVALID_SUCCESSOR")
        self.assertEqual(self.client.post(f"/api/issuers/{iid}/retire", json={"successor_issuer_id": "ISS-099"}, headers=platform).get_json()["error"]["code"], "INVALID_SUCCESSOR")
        self.assertEqual(self.client.post("/api/issuers", json={"name": "test university"}, headers=platform).get_json()["error"]["code"], "DUPLICATE_NAME")
        self.client.post(f"/api/issuers/{iid}/retire", json={"successor_issuer_id": self.w.issuer2["issuer_id"]}, headers=platform)
        self.assertEqual(self.client.post(f"/api/issuers/{iid}/rotate-key", headers=platform).status_code, 409)

    def test_changing_a_rules_issuer_directly(self):
        response = self.client.post(f"/api/rules/{self.rule_id}/issuer", json={"issuer_id": self.w.issuer2["issuer_id"]}, headers=self.admin)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.post(f"/api/rules/{self.rule_id}/issuer", json={"issuer_id": self.w.issuer2["issuer_id"]}, headers=self.admin).status_code, 409)


class UserAdminTests(ApiTestCase):
    def test_create_reset_and_self_protection(self):
        platform = self.w.login("platform@x.example")
        created = self.client.post("/api/users", json={"email": "new.staff@x.example", "role": "support_staff"}, headers=platform).get_json()
        self.assertIn("temporary_password", created)
        login = self.client.post("/api/auth/login", json={"email": "new.staff@x.example", "password": created["temporary_password"]})
        self.assertEqual(login.status_code, 200)
        self.assertEqual(self.client.post("/api/users", json={"email": "new.staff@x.example", "role": "support_staff"}, headers=platform).get_json()["error"]["code"], "DUPLICATE_EMAIL")
        self.assertEqual(self.client.post("/api/users", json={"email": "l@x.example", "role": "learner"}, headers=platform).get_json()["error"]["code"], "INVALID_LINK")
        self.assertEqual(self.client.post("/api/users", json={"email": "w@x.example", "role": "support_staff", "password": "short"}, headers=platform).get_json()["error"]["code"], "WEAK_PASSWORD")
        reset = self.client.post(f"/api/users/{created['user_id']}/reset-password", headers=platform).get_json()
        self.assertNotEqual(reset["temporary_password"], created["temporary_password"])
        self.assertEqual(self.client.post("/api/auth/login", json={"email": "new.staff@x.example", "password": created["temporary_password"]}).status_code, 401)
        me = self.client.get("/api/auth/me", headers=platform).get_json()["user_id"]
        self.assertEqual(self.client.patch(f"/api/users/{me}", json={"is_active": False}, headers=platform).get_json()["error"]["code"], "SELF_LOCKOUT")
        listing = self.client.get("/api/users", headers=platform).get_json()
        self.assertTrue(all("password_hash" not in u for u in listing["items"]))


class ReportTests(ApiTestCase):
    def test_dashboard_numbers_come_from_the_database(self):
        empty = self.client.get("/api/reports/dashboard", headers=self.admin).get_json()["kpis"]
        self.assertEqual((empty["credentials_total"], empty["verifications_total"], empty["pending_issuance"]), (0, 0, 0))
        self.qualify()
        self.assertEqual(self.client.get("/api/reports/dashboard", headers=self.admin).get_json()["kpis"]["pending_issuance"], 1)
        cid = self.issue().get_json()["credential_id"]
        self.verify(cid)
        self.verify("CRD-2026-999999")
        self.client.post(f"/api/credentials/{cid}/revoke", json={"reason_code": "fraud"}, headers=self.admin)
        data = self.client.get("/api/reports/dashboard", headers=self.admin).get_json()
        k = data["kpis"]
        self.assertEqual((k["credentials_total"], k["credentials_revoked"], k["credentials_active"], k["verifications_total"], k["pending_issuance"]), (1, 1, 0, 2, 0))
        self.assertEqual(k["verification_valid_rate_pct"], 50.0)
        self.assertEqual({r["label"]: r["count"] for r in data["verification_outcomes"]}, {"valid": 1, "not_found": 1})
        self.assertEqual(data["revocation_reasons"], [{"label": "fraud", "count": 1}])

    def test_csv_exports(self):
        self.issue_ok()
        response = self.client.get("/api/reports/export/credentials", headers=self.admin)
        self.assertEqual(response.status_code, 200)
        lines = response.get_data(as_text=True).strip().splitlines()
        self.assertEqual(len(lines), 2)
        self.assertTrue(lines[0].startswith("credential_id,learner_id"))
        self.assertEqual(self.client.get("/api/reports/export/nope", headers=self.admin).status_code, 404)
        self.assertEqual(self.client.get("/api/reports/export/credentials", headers=self.w.login("ada@x.example")).status_code, 403)

    def test_csv_export_neutralises_spreadsheet_formulas(self):
        credential_id = self.issue_ok()["credential_id"]
        self.verify(credential_id, requester_org="=HYPERLINK(\"http://evil.example\")", requester_type="employer")
        body = self.client.get("/api/reports/export/verifications", headers=self.admin).get_data(as_text=True)
        self.assertIn("'=HYPERLINK", body)
        self.assertNotIn(",=HYPERLINK", body)

    def test_security_headers_and_unknown_routes(self):
        response = self.client.get("/api/health")
        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
        self.assertIn("default-src 'self'", response.headers["Content-Security-Policy"])
        self.assertEqual(self.client.get("/api/nothing").status_code, 404)
        self.assertEqual(self.client.get("/").status_code, 200)


if __name__ == "__main__":
    unittest.main()
