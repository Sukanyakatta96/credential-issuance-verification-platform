import re
from datetime import date

from flask import request

from .errors import bad_request

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def _parse_date(value: str) -> bool:
    try:
        date.fromisoformat(value)
        return bool(DATE_RE.match(value))
    except ValueError:
        return False


def parse_value(name: str, raw, spec: dict, errors: dict):
    kind = spec.get("type", "str")
    if raw is None or (isinstance(raw, str) and raw.strip() == ""):
        if spec.get("required"):
            errors[name] = "is required"
        return spec.get("default")
    try:
        if kind == "str":
            if not isinstance(raw, str):
                raise ValueError("must be a string")
            value = raw.strip()
            if len(value) > spec.get("max_len", 500):
                raise ValueError(f"must be at most {spec.get('max_len', 500)} characters")
            if len(value) < spec.get("min_len", 0):
                raise ValueError(f"must be at least {spec['min_len']} characters")
            if "choices" in spec and value not in spec["choices"]:
                raise ValueError("must be one of: " + ", ".join(spec["choices"]))
            if "pattern" in spec and not re.match(spec["pattern"], value):
                raise ValueError(spec.get("pattern_message", "has an invalid format"))
            return value
        if kind == "email":
            value = str(raw).strip().lower()
            if not EMAIL_RE.match(value) or len(value) > 254:
                raise ValueError("must be a valid email address")
            return value
        if kind == "date":
            value = str(raw).strip()
            if not _parse_date(value):
                raise ValueError("must be a valid date in YYYY-MM-DD format")
            return value
        if kind == "timestamp":
            value = str(raw).strip()
            if not TS_RE.match(value):
                raise ValueError("must be a UTC timestamp like 2026-01-31T09:30:00Z")
            return value
        if kind in ("int", "float"):
            if isinstance(raw, bool):
                raise ValueError("must be a number")
            value = int(raw) if kind == "int" else float(raw)
            if kind == "int" and isinstance(raw, float) and raw != value:
                raise ValueError("must be a whole number")
            if "min" in spec and value < spec["min"]:
                raise ValueError(f"must be at least {spec['min']}")
            if "max" in spec and value > spec["max"]:
                raise ValueError(f"must be at most {spec['max']}")
            return value
        if kind == "bool":
            if not isinstance(raw, bool):
                raise ValueError("must be true or false")
            return raw
        if kind == "list":
            if not isinstance(raw, list):
                raise ValueError("must be a list")
            if len(raw) < spec.get("min_items", 0):
                raise ValueError(f"must contain at least {spec['min_items']} items")
            if len(raw) > spec.get("max_items", 100):
                raise ValueError(f"must contain at most {spec.get('max_items', 100)} items")
            return raw
    except (ValueError, TypeError) as exc:
        errors[name] = str(exc) if str(exc) else "is invalid"
    return None


def parse_body(schema: dict, partial: bool = False) -> dict:
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise bad_request("Request body must be a JSON object")
    errors: dict = {}
    cleaned: dict = {}
    for name, spec in schema.items():
        if partial and name not in body:
            continue
        cleaned[name] = parse_value(name, body.get(name), spec, errors)
    unknown = sorted(set(body) - set(schema))
    if unknown:
        errors["_unknown"] = "unexpected fields: " + ", ".join(unknown)
    if errors:
        raise bad_request("Validation failed", errors)
    return cleaned


def page_params(default_size: int = 25, max_size: int = 200) -> tuple[int, int]:
    try:
        page = max(1, int(request.args.get("page", 1)))
        size = int(request.args.get("page_size", default_size))
    except ValueError:
        raise bad_request("page and page_size must be integers")
    return page, max(1, min(size, max_size))


def like_pattern(term: str) -> str:
    escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"
