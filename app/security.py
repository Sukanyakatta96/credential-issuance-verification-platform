import threading
import time
from collections import defaultdict, deque
from functools import wraps

import jwt
from flask import current_app, g, request
from werkzeug.security import check_password_hash, generate_password_hash

from .db import get_db
from .errors import ApiError, forbidden, unauthorized

ROLES = ("learner", "instructor", "academic_admin", "support_staff", "platform_admin")
STAFF_ROLES = ("academic_admin", "support_staff", "platform_admin")
ISSUING_ROLES = ("academic_admin", "platform_admin")
MIN_PASSWORD_LENGTH = 10

_lock = threading.Lock()
_login_failures: dict[str, deque] = defaultdict(deque)
_public_hits: dict[str, deque] = defaultdict(deque)


def hash_password(password: str) -> str:
    return generate_password_hash(password)


def verify_password(stored_hash: str | None, password: str) -> bool:
    return bool(stored_hash) and check_password_hash(stored_hash, password)


def validate_password_strength(password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ApiError(400, "WEAK_PASSWORD", f"Password must be at least {MIN_PASSWORD_LENGTH} characters long")


def issue_token(user: dict) -> str:
    cfg = current_app.config["APP_CONFIG"]
    now = int(time.time())
    claims = {"sub": user["user_id"], "role": user["role"], "iat": now, "exp": now + cfg.jwt_ttl_minutes * 60}
    return jwt.encode(claims, cfg.jwt_secret, algorithm="HS256")


def _load_user_from_token() -> dict:
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        raise unauthorized()
    try:
        claims = jwt.decode(header[7:], current_app.config["APP_CONFIG"].jwt_secret, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise unauthorized("Session expired, please sign in again", "TOKEN_EXPIRED")
    except jwt.InvalidTokenError:
        raise unauthorized("Invalid authentication token", "TOKEN_INVALID")
    row = get_db().execute(
        "SELECT user_id, email, role, learner_id, instructor_id, is_active FROM app_user WHERE user_id = ?",
        (claims["sub"],),
    ).fetchone()
    if row is None or not row["is_active"]:
        raise unauthorized("Account is not active", "ACCOUNT_INACTIVE")
    return dict(row)


def require_roles(*roles: str):
    allowed = roles or ROLES

    def decorator(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            user = _load_user_from_token()
            if user["role"] not in allowed:
                raise forbidden()
            g.user = user
            return view(*args, **kwargs)
        wrapper.allowed_roles = allowed
        return wrapper
    return decorator


def current_user() -> dict:
    return g.user


def _client_key() -> str:
    return request.remote_addr or "unknown"


def check_login_allowed(email: str) -> None:
    cfg = current_app.config["APP_CONFIG"]
    key = f"{email}|{_client_key()}"
    cutoff = time.time() - cfg.login_lockout_seconds
    with _lock:
        failures = _login_failures[key]
        while failures and failures[0] < cutoff:
            failures.popleft()
        if len(failures) >= cfg.login_max_failures:
            raise ApiError(429, "LOGIN_LOCKED", "Too many failed sign-in attempts. Try again later.")


def record_login_failure(email: str) -> None:
    with _lock:
        _login_failures[f"{email}|{_client_key()}"].append(time.time())


def clear_login_failures(email: str) -> None:
    with _lock:
        _login_failures.pop(f"{email}|{_client_key()}", None)


def enforce_public_rate_limit() -> None:
    limit = current_app.config["APP_CONFIG"].public_rate_limit_per_minute
    now = time.time()
    with _lock:
        hits = _public_hits[_client_key()]
        while hits and hits[0] < now - 60:
            hits.popleft()
        if len(hits) >= limit:
            raise ApiError(429, "RATE_LIMITED", "Too many verification requests. Please slow down.")
        hits.append(now)


def reset_throttles() -> None:
    with _lock:
        _login_failures.clear()
        _public_hits.clear()
