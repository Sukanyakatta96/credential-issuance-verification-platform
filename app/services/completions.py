from .. import audit, ids
from ..db import paginate, transaction
from ..domain.completion import TERMINAL_STATUSES, derive_completion_state
from ..errors import ApiError, conflict, not_found, unprocessable
from ..timeutil import to_ts, utcnow


def _actor(actor_user_id):
    return {"actor_type": "user" if actor_user_id else "system", "actor_user_id": actor_user_id}


def list_completions(db, *, learner_id=None, course_id=None, status=None, instructor_id=None, q=None, page, page_size):
    where, params = ["1=1"], []
    for column, value in (("cr.learner_id", learner_id), ("cr.course_id", course_id), ("cr.status", status),
                          ("c.instructor_id", instructor_id)):
        if value:
            where.append(f"{column} = ?")
            params.append(value)
    if q:
        where.append("(l.full_name LIKE ? ESCAPE '\\' OR cr.completion_id LIKE ? ESCAPE '\\')")
        escaped = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        params += [escaped, escaped]
    sql = (
        "SELECT cr.*, l.full_name AS learner_name, c.title AS course_title, c.pass_mark "
        "FROM completion_record cr JOIN learner l ON l.learner_id = cr.learner_id "
        f"JOIN course c ON c.course_id = cr.course_id WHERE {' AND '.join(where)}"
    )
    return paginate(db, sql, params, page, page_size, "cr.completion_id")


def get_completion(db, completion_id):
    row = db.execute(
        "SELECT cr.*, l.full_name AS learner_name, c.title AS course_title, c.pass_mark, c.max_attempts, "
        "c.instructor_id, c.status AS course_status FROM completion_record cr "
        "JOIN learner l ON l.learner_id = cr.learner_id JOIN course c ON c.course_id = cr.course_id "
        "WHERE cr.completion_id = ?", (completion_id,)).fetchone()
    if row is None:
        raise not_found("Completion record not found")
    completion = dict(row)
    completion["attempts"] = [dict(r) for r in db.execute(
        "SELECT attempt_id, attempt_no, score, passed, attempted_at FROM assessment_attempt "
        "WHERE completion_id = ? ORDER BY attempt_no", (completion_id,))]
    return completion


def enroll(db, learner_id, course_id, actor_user_id):
    learner = db.execute("SELECT status FROM learner WHERE learner_id = ?", (learner_id,)).fetchone()
    course = db.execute("SELECT status FROM course WHERE course_id = ?", (course_id,)).fetchone()
    if learner is None:
        raise not_found("Learner not found")
    if course is None:
        raise not_found("Course not found")
    if learner["status"] != "active":
        raise unprocessable("Only active learners can be enrolled", "LEARNER_NOT_ACTIVE")
    if course["status"] != "active":
        raise unprocessable("Archived courses cannot accept enrolments", "COURSE_NOT_ACTIVE")
    completion_id = ids.completion_id(learner_id, course_id)
    with transaction(db):
        if db.execute("SELECT 1 FROM completion_record WHERE completion_id = ?", (completion_id,)).fetchone():
            raise conflict("Learner is already enrolled in this course", "ALREADY_ENROLLED")
        db.execute(
            "INSERT INTO completion_record (completion_id, learner_id, course_id, enrolled_at, progress_pct, status, "
            "attempts_used, final_score, finalized_at) VALUES (?,?,?,?,0,'enrolled',0,NULL,NULL)",
            (completion_id, learner_id, course_id, to_ts(utcnow())))
        audit.append_event(db, action="completion.enrolled", entity_type="completion_record", entity_id=completion_id,
                           details={}, **_actor(actor_user_id))
    return get_completion(db, completion_id)


def _require_open(completion):
    if completion["status"] in TERMINAL_STATUSES:
        raise conflict(f"Completion record is already {completion['status']} and can no longer change",
                       "COMPLETION_CLOSED")


def update_progress(db, completion_id, progress_pct, actor_user_id):
    with transaction(db):
        completion = get_completion(db, completion_id)
        _require_open(completion)
        if progress_pct < completion["progress_pct"]:
            raise conflict("Progress cannot decrease", "PROGRESS_REGRESSION")
        status = derive_completion_state(
            pass_mark=completion["pass_mark"], max_attempts=completion["max_attempts"], progress_pct=progress_pct,
            attempt_scores=[a["score"] for a in completion["attempts"]])["status"]
        db.execute("UPDATE completion_record SET progress_pct = ?, status = ? WHERE completion_id = ?",
                   (progress_pct, status, completion_id))
    return get_completion(db, completion_id)


def record_assessment(db, completion_id, score, actor_user_id):
    with transaction(db):
        completion = get_completion(db, completion_id)
        _require_open(completion)
        if completion["progress_pct"] < 100:
            raise conflict("All course content must be completed (100% progress) before an assessment can be recorded",
                           "COURSE_NOT_FINISHED")
        scores = [a["score"] for a in completion["attempts"]]
        if len(scores) >= completion["max_attempts"]:
            raise conflict("The maximum number of assessment attempts has been used", "ATTEMPTS_EXHAUSTED")
        attempt_no = len(scores) + 1
        now_ts = to_ts(utcnow())
        passed = 1 if score >= completion["pass_mark"] else 0
        db.execute("INSERT INTO assessment_attempt (attempt_id, completion_id, attempt_no, score, passed, attempted_at) "
                   "VALUES (?,?,?,?,?,?)",
                   (ids.attempt_id(completion_id, attempt_no), completion_id, attempt_no, score, passed, now_ts))
        state = derive_completion_state(
            pass_mark=completion["pass_mark"], max_attempts=completion["max_attempts"], progress_pct=100,
            attempt_scores=[*scores, score])
        finalized_at = now_ts if state["status"] in TERMINAL_STATUSES else None
        db.execute("UPDATE completion_record SET status = ?, attempts_used = ?, final_score = ?, finalized_at = ? "
                   "WHERE completion_id = ?",
                   (state["status"], state["attempts_used"], state["final_score"], finalized_at, completion_id))
        if finalized_at:
            audit.append_event(db, action="completion.finalized", entity_type="completion_record",
                               entity_id=completion_id,
                               details={"status": state["status"], "final_score": state["final_score"]},
                               **_actor(actor_user_id))
    return get_completion(db, completion_id)


def withdraw(db, completion_id, actor_user_id):
    with transaction(db):
        completion = get_completion(db, completion_id)
        _require_open(completion)
        now_ts = to_ts(utcnow())
        db.execute("UPDATE completion_record SET status = 'withdrawn', finalized_at = ? WHERE completion_id = ?",
                   (now_ts, completion_id))
        audit.append_event(db, action="completion.finalized", entity_type="completion_record", entity_id=completion_id,
                           details={"status": "withdrawn", "final_score": completion["final_score"]},
                           **_actor(actor_user_id))
    return get_completion(db, completion_id)


def instructor_owns_course(db, instructor_id, course_id) -> bool:
    row = db.execute("SELECT 1 FROM course WHERE course_id = ? AND instructor_id = ?", (course_id, instructor_id)).fetchone()
    return row is not None


def ensure_assessable_by(db, user, completion_id):
    completion = get_completion(db, completion_id)
    if user["role"] == "instructor" and completion["instructor_id"] != user["instructor_id"]:
        raise ApiError(403, "FORBIDDEN", "You can only manage completions for courses you teach")
    return completion
