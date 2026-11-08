import sqlite3

from .. import audit, ids
from ..db import paginate, transaction
from ..errors import ApiError, conflict, not_found, unprocessable
from ..timeutil import ensure_strictly_after, to_ts, utcnow
from ..validation import like_pattern


def _actor(actor_user_id):
    return {"actor_type": "user" if actor_user_id else "system", "actor_user_id": actor_user_id}


def list_learners(db, *, q, status, page, page_size):
    where, params = ["1=1"], []
    if q:
        where.append("(l.full_name LIKE ? ESCAPE '\\' OR l.email LIKE ? ESCAPE '\\' OR l.learner_id LIKE ? ESCAPE '\\')")
        params += [like_pattern(q)] * 3
    if status:
        where.append("l.status = ?")
        params.append(status)
    sql = (
        "SELECT l.learner_id, l.full_name, l.email, l.date_of_birth, l.country_code, l.registered_at, l.status, "
        "(SELECT COUNT(*) FROM learner o WHERE o.full_name = l.full_name COLLATE NOCASE) - 1 AS same_name_count, "
        "(SELECT COUNT(*) FROM credential c WHERE c.learner_id = l.learner_id) AS credential_count "
        f"FROM learner l WHERE {' AND '.join(where)}"
    )
    return paginate(db, sql, params, page, page_size, "l.learner_id")


def get_learner(db, learner_id):
    row = db.execute("SELECT * FROM learner WHERE learner_id = ?", (learner_id,)).fetchone()
    if row is None:
        raise not_found("Learner not found")
    learner = dict(row)
    learner["same_name_count"] = db.execute(
        "SELECT COUNT(*) FROM learner WHERE full_name = ? COLLATE NOCASE AND learner_id != ?",
        (learner["full_name"], learner_id)).fetchone()[0]
    learner["same_name_and_birthdate_count"] = db.execute(
        "SELECT COUNT(*) FROM learner WHERE full_name = ? COLLATE NOCASE AND date_of_birth = ? AND learner_id != ?",
        (learner["full_name"], learner["date_of_birth"], learner_id)).fetchone()[0]
    learner["completion_count"] = db.execute(
        "SELECT COUNT(*) FROM completion_record WHERE learner_id = ?", (learner_id,)).fetchone()[0]
    learner["credential_count"] = db.execute(
        "SELECT COUNT(*) FROM credential WHERE learner_id = ?", (learner_id,)).fetchone()[0]
    return learner


def create_learner(db, data, actor_user_id):
    with transaction(db):
        try:
            number = ids.next_counter(db, "learner")
            learner_id = ids.learner_id(number)
            db.execute(
                "INSERT INTO learner (learner_id, full_name, email, date_of_birth, country_code, registered_at, status) "
                "VALUES (?,?,?,?,?,?, 'active')",
                (learner_id, data["full_name"], data["email"], data["date_of_birth"],
                 data["country_code"].upper(), to_ts(utcnow())))
        except sqlite3.IntegrityError as exc:
            if "learner.email" in str(exc):
                raise conflict("A learner with this email already exists", "DUPLICATE_EMAIL")
            raise
        audit.append_event(db, action="learner.registered", entity_type="learner", entity_id=learner_id,
                           details={"email": data["email"]}, **_actor(actor_user_id))
    return get_learner(db, learner_id)


def update_learner(db, learner_id, data, actor_user_id):
    get_learner(db, learner_id)
    if not data:
        raise ApiError(400, "VALIDATION_ERROR", "No updatable fields supplied")
    assignments = ", ".join(f"{k} = ?" for k in data)
    with transaction(db):
        try:
            db.execute(f"UPDATE learner SET {assignments} WHERE learner_id = ?", [*data.values(), learner_id])
        except sqlite3.IntegrityError as exc:
            if "learner.email" in str(exc):
                raise conflict("A learner with this email already exists", "DUPLICATE_EMAIL")
            raise
        audit.append_event(db, action="learner.updated", entity_type="learner", entity_id=learner_id,
                           details={"fields": sorted(data)}, **_actor(actor_user_id))
    return get_learner(db, learner_id)


def list_courses(db, *, q, category, level, status, instructor_id, page, page_size):
    where, params = ["1=1"], []
    if q:
        where.append("(c.title LIKE ? ESCAPE '\\' OR c.course_id LIKE ? ESCAPE '\\')")
        params += [like_pattern(q)] * 2
    for column, value in (("category", category), ("level", level), ("status", status), ("instructor_id", instructor_id)):
        if value:
            where.append(f"c.{column} = ?")
            params.append(value)
    sql = (
        "SELECT c.*, i.full_name AS instructor_name, "
        "(SELECT COUNT(*) FROM completion_record r WHERE r.course_id = c.course_id) AS enrollment_count, "
        "(SELECT COUNT(*) FROM completion_record r WHERE r.course_id = c.course_id AND r.status = 'completed') AS completed_count "
        f"FROM course c JOIN instructor i ON i.instructor_id = c.instructor_id WHERE {' AND '.join(where)}"
    )
    return paginate(db, sql, params, page, page_size, "c.course_id")


def get_course(db, course_id):
    row = db.execute(
        "SELECT c.*, i.full_name AS instructor_name FROM course c JOIN instructor i ON i.instructor_id = c.instructor_id "
        "WHERE c.course_id = ?", (course_id,)).fetchone()
    if row is None:
        raise not_found("Course not found")
    course = dict(row)
    course["status_breakdown"] = {r["status"]: r["n"] for r in db.execute(
        "SELECT status, COUNT(*) AS n FROM completion_record WHERE course_id = ? GROUP BY status", (course_id,))}
    course["rules"] = [dict(r) for r in db.execute(
        "SELECT r.rule_id, r.title, r.status, rc.is_mandatory FROM credential_rule_course rc "
        "JOIN credential_rule r ON r.rule_id = rc.rule_id WHERE rc.course_id = ? ORDER BY r.rule_id", (course_id,))]
    return course


def list_categories(db):
    return [r[0] for r in db.execute("SELECT DISTINCT category FROM course ORDER BY category")]


def list_instructors(db):
    return [dict(r) for r in db.execute("SELECT instructor_id, full_name, department FROM instructor ORDER BY full_name")]


def create_course(db, data, actor_user_id):
    if db.execute("SELECT 1 FROM instructor WHERE instructor_id = ?", (data["instructor_id"],)).fetchone() is None:
        raise unprocessable("Instructor does not exist", "UNKNOWN_INSTRUCTOR")
    with transaction(db):
        course_id = ids.course_id(ids.next_counter(db, "course"))
        db.execute(
            "INSERT INTO course (course_id, title, category, level, credit_hours, pass_mark, max_attempts, instructor_id, status, created_at) "
            "VALUES (?,?,?,?,?,?,?,?, 'active', ?)",
            (course_id, data["title"], data["category"], data["level"], data["credit_hours"], data["pass_mark"],
             data["max_attempts"], data["instructor_id"], to_ts(utcnow())))
        audit.append_event(db, action="course.created", entity_type="course", entity_id=course_id,
                           details={"title": data["title"]}, **_actor(actor_user_id))
    return get_course(db, course_id)


def update_course(db, course_id, data, actor_user_id):
    get_course(db, course_id)
    if not data:
        raise ApiError(400, "VALIDATION_ERROR", "No updatable fields supplied")
    if "instructor_id" in data and db.execute(
            "SELECT 1 FROM instructor WHERE instructor_id = ?", (data["instructor_id"],)).fetchone() is None:
        raise unprocessable("Instructor does not exist", "UNKNOWN_INSTRUCTOR")
    assignments = ", ".join(f"{k} = ?" for k in data)
    with transaction(db):
        db.execute(f"UPDATE course SET {assignments} WHERE course_id = ?", [*data.values(), course_id])
        audit.append_event(db, action="course.updated", entity_type="course", entity_id=course_id,
                           details={"fields": sorted(data)}, **_actor(actor_user_id))
    return get_course(db, course_id)


def list_rules(db, *, q, status, page, page_size):
    where, params = ["1=1"], []
    if q:
        where.append("(r.title LIKE ? ESCAPE '\\' OR r.rule_id LIKE ? ESCAPE '\\')")
        params += [like_pattern(q)] * 2
    if status:
        where.append("r.status = ?")
        params.append(status)
    sql = (
        "SELECT r.*, (SELECT COUNT(*) FROM credential_rule_course rc WHERE rc.rule_id = r.rule_id) AS course_count, "
        "(SELECT COUNT(*) FROM credential c WHERE c.rule_id = r.rule_id) AS credential_count, "
        "(SELECT i.name FROM rule_issuer_assignment a JOIN issuer i ON i.issuer_id = a.issuer_id "
        "  WHERE a.rule_id = r.rule_id AND a.effective_to IS NULL) AS current_issuer "
        f"FROM credential_rule r WHERE {' AND '.join(where)}"
    )
    return paginate(db, sql, params, page, page_size, "r.rule_id")


def get_rule(db, rule_id):
    row = db.execute("SELECT * FROM credential_rule WHERE rule_id = ?", (rule_id,)).fetchone()
    if row is None:
        raise not_found("Credential rule not found")
    rule = dict(row)
    rule["courses"] = [dict(r) for r in db.execute(
        "SELECT rc.course_id, rc.is_mandatory, c.title, c.pass_mark, c.status FROM credential_rule_course rc "
        "JOIN course c ON c.course_id = rc.course_id WHERE rc.rule_id = ? ORDER BY rc.is_mandatory DESC, rc.course_id",
        (rule_id,))]
    rule["issuer_history"] = [dict(r) for r in db.execute(
        "SELECT a.assignment_id, a.issuer_id, i.name AS issuer_name, a.effective_from, a.effective_to "
        "FROM rule_issuer_assignment a JOIN issuer i ON i.issuer_id = a.issuer_id WHERE a.rule_id = ? "
        "ORDER BY a.effective_from", (rule_id,))]
    rule["credential_count"] = db.execute("SELECT COUNT(*) FROM credential WHERE rule_id = ?", (rule_id,)).fetchone()[0]
    return rule


def create_rule(db, data, actor_user_id):
    course_ids = [c["course_id"] for c in data["courses"]]
    if len(set(course_ids)) != len(course_ids):
        raise unprocessable("A course can only appear once in a rule", "DUPLICATE_COURSE")
    mandatory_count = sum(1 for c in data["courses"] if c["is_mandatory"])
    if not mandatory_count <= data["min_courses_required"] <= len(course_ids):
        raise unprocessable(
            "min_courses_required must be at least the number of mandatory courses and at most the number of courses",
            "INVALID_THRESHOLD")
    placeholders = ",".join("?" * len(course_ids))
    found = {r[0] for r in db.execute(f"SELECT course_id FROM course WHERE course_id IN ({placeholders})", course_ids)}
    if found != set(course_ids):
        raise unprocessable("Unknown courses: " + ", ".join(sorted(set(course_ids) - found)), "UNKNOWN_COURSE")
    issuer = db.execute("SELECT status FROM issuer WHERE issuer_id = ?", (data["issuer_id"],)).fetchone()
    if issuer is None or issuer["status"] != "active":
        raise unprocessable("Issuer must exist and be active", "INVALID_ISSUER")
    now = to_ts(utcnow())
    effective_from = data.get("effective_from") or now
    with transaction(db):
        rule_id = ids.rule_id(ids.next_counter(db, "rule"))
        try:
            db.execute(
                "INSERT INTO credential_rule (rule_id, title, credential_type, version, min_courses_required, min_avg_score, "
                "min_course_score, validity_months, effective_from, effective_to, status, created_at) "
                "VALUES (?,?,?,1,?,?,?,?,?,NULL,'active',?)",
                (rule_id, data["title"], data["credential_type"], data["min_courses_required"], data["min_avg_score"],
                 data["min_course_score"], data["validity_months"], effective_from, now))
        except sqlite3.IntegrityError as exc:
            if "credential_rule.title" in str(exc):
                raise conflict("A rule with this title already exists", "DUPLICATE_TITLE")
            raise
        db.executemany("INSERT INTO credential_rule_course (rule_id, course_id, is_mandatory) VALUES (?,?,?)",
                       [(rule_id, c["course_id"], 1 if c["is_mandatory"] else 0) for c in data["courses"]])
        db.execute("INSERT INTO rule_issuer_assignment (assignment_id, rule_id, issuer_id, effective_from, effective_to) "
                   "VALUES (?,?,?,?,NULL)",
                   (ids.assignment_id(ids.next_counter(db, "assignment")), rule_id, data["issuer_id"], effective_from))
        audit.append_event(db, action="rule.created", entity_type="credential_rule", entity_id=rule_id,
                           details={"title": data["title"], "courses": course_ids}, **_actor(actor_user_id))
    return get_rule(db, rule_id)


def retire_rule(db, rule_id, actor_user_id):
    rule = get_rule(db, rule_id)
    if rule["status"] == "retired":
        raise conflict("Rule is already retired", "ALREADY_RETIRED")
    effective_to = ensure_strictly_after(utcnow(), rule["effective_from"], "Retiring a rule")
    with transaction(db):
        db.execute("UPDATE credential_rule SET status = 'retired', effective_to = ? WHERE rule_id = ?",
                   (effective_to, rule_id))
        audit.append_event(db, action="rule.retired", entity_type="credential_rule", entity_id=rule_id,
                           details={"effective_to": effective_to}, **_actor(actor_user_id))
    return get_rule(db, rule_id)


def reassign_rule_issuer(db, rule_id, issuer_id, actor_user_id):
    rule = get_rule(db, rule_id)
    issuer = db.execute("SELECT status FROM issuer WHERE issuer_id = ?", (issuer_id,)).fetchone()
    if issuer is None or issuer["status"] != "active":
        raise unprocessable("Issuer must exist and be active", "INVALID_ISSUER")
    current = next((a for a in rule["issuer_history"] if a["effective_to"] is None), None)
    if current and current["issuer_id"] == issuer_id:
        raise conflict("This issuer is already assigned to the rule", "NO_CHANGE")
    now_ts = ensure_strictly_after(utcnow(), current["effective_from"], "Changing the issuer") if current else to_ts(utcnow())
    with transaction(db):
        if current:
            db.execute("UPDATE rule_issuer_assignment SET effective_to = ? WHERE assignment_id = ?",
                       (now_ts, current["assignment_id"]))
        db.execute("INSERT INTO rule_issuer_assignment (assignment_id, rule_id, issuer_id, effective_from, effective_to) "
                   "VALUES (?,?,?,?,NULL)",
                   (ids.assignment_id(ids.next_counter(db, "assignment")), rule_id, issuer_id, now_ts))
        audit.append_event(db, action="rule.issuer_changed", entity_type="credential_rule", entity_id=rule_id,
                           details={"from": current["issuer_id"] if current else None, "to": issuer_id},
                           **_actor(actor_user_id))
    return get_rule(db, rule_id)
