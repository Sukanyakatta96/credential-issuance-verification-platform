from flask import Blueprint, g, jsonify

from .. import security
from ..db import get_db
from ..errors import ApiError
from ..services import users
from ..validation import parse_body

bp = Blueprint("auth", __name__)

LOGIN_SCHEMA = {"email": {"type": "email", "required": True}, "password": {"type": "str", "required": True, "max_len": 200}}
PASSWORD_SCHEMA = {"current_password": {"type": "str", "required": True, "max_len": 200},
                   "new_password": {"type": "str", "required": True, "max_len": 200}}


@bp.post("/auth/login")
def login():
    data = parse_body(LOGIN_SCHEMA)
    security.check_login_allowed(data["email"])
    row = get_db().execute("SELECT * FROM app_user WHERE email = ?", (data["email"],)).fetchone()
    valid = row is not None and row["is_active"] and security.verify_password(row["password_hash"], data["password"])
    if not valid:
        security.record_login_failure(data["email"])
        raise ApiError(401, "INVALID_CREDENTIALS", "Email or password is incorrect")
    security.clear_login_failures(data["email"])
    user = {k: row[k] for k in ("user_id", "email", "role", "learner_id", "instructor_id")}
    return jsonify({"token": security.issue_token(user), "user": user})


@bp.get("/auth/me")
@security.require_roles()
def me():
    return jsonify(g.user)


@bp.post("/auth/change-password")
@security.require_roles()
def change_password():
    data = parse_body(PASSWORD_SCHEMA)
    users.change_own_password(get_db(), g.user["user_id"], data["current_password"], data["new_password"])
    return jsonify({"message": "Password updated"})
