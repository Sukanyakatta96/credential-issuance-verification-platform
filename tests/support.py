import tempfile
from pathlib import Path

from app import create_app, security
from app.config import Config
from app.db import connect
from app.services import catalog, completions, issuers, users

TEST_PASSWORD = "Correct-Horse-9"


def make_config(tmpdir: str, **overrides) -> Config:
    values = dict(
        database_path=str(Path(tmpdir) / "test.db"), data_dir=str(Path(tmpdir) / "data"),
        ground_truth_dir=str(Path(tmpdir) / "data"), jwt_secret="test-jwt-secret-0123456789abcdef0123456789",
        jwt_ttl_minutes=30, signing_master_secret="test-signing-master-secret-0123456789abcdef",
        public_rate_limit_per_minute=1000, login_max_failures=5, login_lockout_seconds=300)
    values.update(overrides)
    return Config(**values)


class World:
    """A small, hand-built dataset used by the behavioural tests."""

    def __init__(self, **config_overrides):
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg = make_config(self.tmp.name, **config_overrides)
        security.reset_throttles()
        self.app = create_app(self.cfg)
        self.client = self.app.test_client()
        self.db = connect(self.cfg.database_path)
        self._seed()

    def _seed(self):
        db = self.db
        db.execute("INSERT INTO instructor VALUES ('INS-0001','Ines Teacher','ines@uni.example','Data')")
        db.execute("INSERT INTO instructor VALUES ('INS-0002','Omar Mentor','omar@uni.example','Design')")
        self.admin = users.create_user(db, {"email": "admin@x.example", "role": "academic_admin", "password": TEST_PASSWORD}, None)
        self.platform = users.create_user(db, {"email": "platform@x.example", "role": "platform_admin", "password": TEST_PASSWORD}, None)
        self.support = users.create_user(db, {"email": "support@x.example", "role": "support_staff", "password": TEST_PASSWORD}, None)
        self.instructor_user = users.create_user(db, {"email": "ines@uni.example", "role": "instructor", "instructor_id": "INS-0001", "password": TEST_PASSWORD}, None)
        self.other_instructor_user = users.create_user(db, {"email": "omar@uni.example", "role": "instructor", "instructor_id": "INS-0002", "password": TEST_PASSWORD}, None)
        self.issuer = issuers.create_issuer(db, self.cfg, "Test University", self.admin["user_id"])
        self.issuer2 = issuers.create_issuer(db, self.cfg, "Second Institute", self.admin["user_id"])
        self.learner = catalog.create_learner(db, {"full_name": "Ada Lovelace", "email": "ada@x.example",
                                                   "date_of_birth": "1990-12-10", "country_code": "GB"}, self.admin["user_id"])
        self.namesake = catalog.create_learner(db, {"full_name": "Ada Lovelace", "email": "ada2@x.example",
                                                    "date_of_birth": "1985-03-02", "country_code": "IN"}, self.admin["user_id"])
        self.learner_user = users.create_user(db, {"email": "ada@x.example", "role": "learner", "learner_id": self.learner["learner_id"], "password": TEST_PASSWORD}, None)
        self.courses = [catalog.create_course(db, {"title": f"Course {i}", "category": "Data", "level": "introductory",
                                                   "credit_hours": 10, "pass_mark": 60, "max_attempts": 2,
                                                   "instructor_id": "INS-0001"}, self.admin["user_id"]) for i in range(3)]
        self.rule = catalog.create_rule(db, {
            "title": "Data Basics Certificate", "credential_type": "certificate", "min_courses_required": 2,
            "min_avg_score": 70, "min_course_score": 65, "validity_months": 12, "effective_from": None,
            "issuer_id": self.issuer["issuer_id"],
            "courses": [{"course_id": self.courses[0]["course_id"], "is_mandatory": True},
                        {"course_id": self.courses[1]["course_id"], "is_mandatory": False},
                        {"course_id": self.courses[2]["course_id"], "is_mandatory": False}]}, self.admin["user_id"])
        self.backdate_catalog()
        self.rule = catalog.get_rule(db, self.rule["rule_id"])

    def backdate_catalog(self):
        """Lets tests change issuers and rules immediately; effective-dated changes need a positive window."""
        long_ago = "2026-01-01T00:00:00Z"
        self.db.execute("UPDATE issuer SET valid_from = ?", (long_ago,))
        self.db.execute("UPDATE issuer_key SET valid_from = ?", (long_ago,))
        self.db.execute("UPDATE credential_rule SET effective_from = ?, created_at = ?", (long_ago, long_ago))
        self.db.execute("UPDATE rule_issuer_assignment SET effective_from = ?", (long_ago,))

    def complete(self, learner_id, course_index, score):
        cid = self.courses[course_index]["course_id"]
        record = completions.enroll(self.db, learner_id, cid, self.admin["user_id"])
        completions.update_progress(self.db, record["completion_id"], 100, self.admin["user_id"])
        return completions.record_assessment(self.db, record["completion_id"], score, self.admin["user_id"])

    def login(self, user_email):
        resp = self.client.post("/api/auth/login", json={"email": user_email, "password": TEST_PASSWORD})
        assert resp.status_code == 200, resp.get_json()
        return {"Authorization": "Bearer " + resp.get_json()["token"]}

    def close(self):
        self.db.close()
        self.tmp.cleanup()
