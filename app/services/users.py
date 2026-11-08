import secrets
import sqlite3

from .. import audit, ids
from ..db import paginate, transaction
from ..errors import ApiError, conflict, not_found, unprocessable
from ..security import hash_password, validate_password_strength, verify_password
from ..timeutil import to_ts, utcnow
from ..validation import like_pattern

PUBLIC_COLUMNS = "u.user_id, u.email, u.role, u.learner_id, u.instructor_id, u.is_active, u.created_at, " \
                 "(u.password_hash IS NOT NULL) AS has_password"


def _actor(actor_user_id):
    return {"actor_type": "user" if actor_user_id else "system", "actor_user_id": actor_user_id}


def list_users(db, *, q=None, role=None, page, page_size):
    where, params = ["1=1"], []
    if q:
        where.append("(u.email LIKE ? ESCAPE '\\' OR u.user_id LIKE ? ESCAPE '\\')")
        params += [like_pattern(q)] * 2
    if role:
        where.append("u.role = ?")
        params.append(role)
    return paginate(db, f"SELECT {PUBLIC_COLUMNS} FROM app_user u WHERE {' AND '.join(where)}",
                    params, page, page_size, "u.user_id")


def get_user(db, user_id):
    row = db.execute(f"SELECT {PUBLIC_COLUMNS} FROM app_user u WHERE u.user_id = ?", (user_id,)).fetchone()
    if row is None:
        raise not_found("User not found")
    return dict(row)


def generate_temporary_password() -> str:
    return secrets.token_urlsafe(12)


def create_user(db, data, actor_user_id):
    if data["role"] == "learner":
        if not data.get("learner_id") or db.execute("SELECT 1 FROM learner WHERE learner_id = ?", (data["learner_id"],)).fetchone() is None:
            raise unprocessable("A learner account must reference an existing learner_id", "INVALID_LINK")
    elif data["role"] == "instructor":
        if not data.get("instructor_id") or db.execute("SELECT 1 FROM instructor WHERE instructor_id = ?", (data["instructor_id"],)).fetchone() is None:
            raise unprocessable("An instructor account must reference an existing instructor_id", "INVALID_LINK")
    password = data.get("password")
    generated = password is None
    password = password or generate_temporary_password()
    validate_password_strength(password)
    with transaction(db):
        user_id = ids.user_id(ids.next_counter(db, "user"))
        try:
            db.execute(
                "INSERT INTO app_user (user_id, email, role, learner_id, instructor_id, is_active, created_at, password_hash) "
                "VALUES (?,?,?,?,?,1,?,?)",
                (user_id, data["email"], data["role"], data.get("learner_id") if data["role"] == "learner" else None,
                 data.get("instructor_id") if data["role"] == "instructor" else None, to_ts(utcnow()),
                 hash_password(password)))
        except sqlite3.IntegrityError as exc:
            if "app_user.email" in str(exc):
                raise conflict("A user with this email already exists", "DUPLICATE_EMAIL")
            raise
        audit.append_event(db, action="user.created", entity_type="app_user", entity_id=user_id,
                           details={"role": data["role"]}, **_actor(actor_user_id))
    user = get_user(db, user_id)
    if generated:
        user["temporary_password"] = password
    return user


def update_user(db, user_id, data, acting_user):
    user = get_user(db, user_id)
    if user_id == acting_user["user_id"] and (data.get("is_active") is False or
                                              ("role" in data and data["role"] != user["role"])):
        raise unprocessable("You cannot deactivate or change the role of your own account", "SELF_LOCKOUT")
    if not data:
        raise ApiError(400, "VALIDATION_ERROR", "No updatable fields supplied")
    new_role = data.get("role", user["role"])
    if new_role == "learner" and not user["learner_id"]:
        raise unprocessable("Account has no linked learner record", "INVALID_LINK")
    if new_role == "instructor" and not user["instructor_id"]:
        raise unprocessable("Account has no linked instructor record", "INVALID_LINK")
    fields = {k: (int(v) if isinstance(v, bool) else v) for k, v in data.items()}
    assignments = ", ".join(f"{k} = ?" for k in fields)
    with transaction(db):
        db.execute(f"UPDATE app_user SET {assignments} WHERE user_id = ?", [*fields.values(), user_id])
        audit.append_event(db, action="user.updated", entity_type="app_user", entity_id=user_id,
                           details={"fields": sorted(fields)}, actor_type="user", actor_user_id=acting_user["user_id"])
    return get_user(db, user_id)


def reset_password(db, user_id, acting_user_id):
    get_user(db, user_id)
    password = generate_temporary_password()
    with transaction(db):
        db.execute("UPDATE app_user SET password_hash = ? WHERE user_id = ?", (hash_password(password), user_id))
        audit.append_event(db, action="user.password_reset", entity_type="app_user", entity_id=user_id,
                           details={}, actor_type="user", actor_user_id=acting_user_id)
    return {"user_id": user_id, "temporary_password": password}


def change_own_password(db, user_id, current_password, new_password):
    row = db.execute("SELECT password_hash FROM app_user WHERE user_id = ?", (user_id,)).fetchone()
    if row is None or not verify_password(row["password_hash"], current_password):
        raise ApiError(403, "WRONG_PASSWORD", "Current password is incorrect")
    validate_password_strength(new_password)
    with transaction(db):
        db.execute("UPDATE app_user SET password_hash = ? WHERE user_id = ?", (hash_password(new_password), user_id))
        audit.append_event(db, action="user.password_changed", entity_type="app_user", entity_id=user_id,
                           details={}, actor_type="user", actor_user_id=user_id)
