from flask import Blueprint, current_app, g, jsonify, request

from ..db import get_db
from ..errors import forbidden
from ..security import ISSUING_ROLES, STAFF_ROLES, require_roles
from ..services import catalog, issuers
from ..validation import page_params, parse_body

bp = Blueprint("directory", __name__)

LEARNER_CREATE = {
    "full_name": {"type": "str", "required": True, "min_len": 2, "max_len": 120},
    "email": {"type": "email", "required": True},
    "date_of_birth": {"type": "date", "required": True},
    "country_code": {"type": "str", "required": True, "min_len": 2, "max_len": 2, "pattern": r"^[A-Za-z]{2}$",
                     "pattern_message": "must be a two-letter ISO country code"},
}
LEARNER_UPDATE = {
    "full_name": {"type": "str", "min_len": 2, "max_len": 120},
    "email": {"type": "email"},
    "country_code": {"type": "str", "min_len": 2, "max_len": 2, "pattern": r"^[A-Za-z]{2}$"},
    "status": {"type": "str", "choices": ["active", "suspended", "closed"]},
}
COURSE_CREATE = {
    "title": {"type": "str", "required": True, "min_len": 3, "max_len": 160},
    "category": {"type": "str", "required": True, "max_len": 80},
    "level": {"type": "str", "required": True, "choices": ["introductory", "intermediate", "advanced"]},
    "credit_hours": {"type": "int", "required": True, "min": 1, "max": 200},
    "pass_mark": {"type": "int", "required": True, "min": 40, "max": 100},
    "max_attempts": {"type": "int", "required": True, "min": 1, "max": 10},
    "instructor_id": {"type": "str", "required": True, "pattern": r"^INS-\d{4}$"},
}
COURSE_UPDATE = {
    "title": {"type": "str", "min_len": 3, "max_len": 160},
    "category": {"type": "str", "max_len": 80},
    "instructor_id": {"type": "str", "pattern": r"^INS-\d{4}$"},
    "status": {"type": "str", "choices": ["active", "archived"]},
}
RULE_CREATE = {
    "title": {"type": "str", "required": True, "min_len": 3, "max_len": 160},
    "credential_type": {"type": "str", "required": True, "choices": ["certificate", "micro_credential", "professional_certificate"]},
    "min_courses_required": {"type": "int", "required": True, "min": 1, "max": 50},
    "min_avg_score": {"type": "float", "required": True, "min": 0, "max": 100},
    "min_course_score": {"type": "float", "required": True, "min": 0, "max": 100},
    "validity_months": {"type": "int", "min": 1, "max": 120},
    "effective_from": {"type": "timestamp"},
    "issuer_id": {"type": "str", "required": True, "pattern": r"^ISS-\d{3}$"},
    "courses": {"type": "list", "required": True, "min_items": 1, "max_items": 50},
}
COURSE_ITEM = {"course_id": {"type": "str", "required": True, "pattern": r"^CRS-\d{6}$"},
               "is_mandatory": {"type": "bool", "required": True}}
ISSUER_CREATE = {"name": {"type": "str", "required": True, "min_len": 3, "max_len": 120}}
ISSUER_RETIRE = {"successor_issuer_id": {"type": "str", "required": True, "pattern": r"^ISS-\d{3}$"}}
RULE_ISSUER = {"issuer_id": {"type": "str", "required": True, "pattern": r"^ISS-\d{3}$"}}


def _validated_course_items(items):
    from ..errors import bad_request
    cleaned, errors = [], {}
    from ..validation import parse_value
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            errors[f"courses[{index}]"] = "must be an object"
            continue
        entry = {}
        for name, spec in COURSE_ITEM.items():
            entry[name] = parse_value(f"courses[{index}].{name}", item.get(name), spec, errors)
        cleaned.append(entry)
    if errors:
        raise bad_request("Validation failed", errors)
    return cleaned


@bp.get("/learners")
@require_roles(*STAFF_ROLES)
def learners_list():
    page, size = page_params()
    return jsonify(catalog.list_learners(get_db(), q=request.args.get("q"), status=request.args.get("status"),
                                         page=page, page_size=size))


@bp.get("/learners/<learner_id>")
@require_roles()
def learner_detail(learner_id):
    if g.user["role"] == "learner" and g.user["learner_id"] != learner_id:
        raise forbidden()
    if g.user["role"] == "instructor":
        raise forbidden()
    return jsonify(catalog.get_learner(get_db(), learner_id))


@bp.post("/learners")
@require_roles(*ISSUING_ROLES)
def learner_create():
    data = parse_body(LEARNER_CREATE)
    return jsonify(catalog.create_learner(get_db(), data, g.user["user_id"])), 201


@bp.patch("/learners/<learner_id>")
@require_roles(*ISSUING_ROLES)
def learner_update(learner_id):
    data = parse_body(LEARNER_UPDATE, partial=True)
    if "country_code" in data:
        data["country_code"] = data["country_code"].upper()
    return jsonify(catalog.update_learner(get_db(), learner_id, data, g.user["user_id"]))


@bp.get("/courses")
@require_roles()
def courses_list():
    page, size = page_params()
    args = request.args
    instructor_id = args.get("instructor_id")
    if g.user["role"] == "instructor" and args.get("mine") == "1":
        instructor_id = g.user["instructor_id"]
    return jsonify(catalog.list_courses(get_db(), q=args.get("q"), category=args.get("category"),
                                        level=args.get("level"), status=args.get("status"),
                                        instructor_id=instructor_id, page=page, page_size=size))


@bp.get("/courses/<course_id>")
@require_roles()
def course_detail(course_id):
    return jsonify(catalog.get_course(get_db(), course_id))


@bp.post("/courses")
@require_roles(*ISSUING_ROLES)
def course_create():
    return jsonify(catalog.create_course(get_db(), parse_body(COURSE_CREATE), g.user["user_id"])), 201


@bp.patch("/courses/<course_id>")
@require_roles(*ISSUING_ROLES)
def course_update(course_id):
    return jsonify(catalog.update_course(get_db(), course_id, parse_body(COURSE_UPDATE, partial=True), g.user["user_id"]))


@bp.get("/meta/course-options")
@require_roles()
def course_options():
    return jsonify({"categories": catalog.list_categories(get_db()), "instructors": catalog.list_instructors(get_db())})


@bp.get("/rules")
@require_roles(*STAFF_ROLES, "instructor")
def rules_list():
    page, size = page_params()
    return jsonify(catalog.list_rules(get_db(), q=request.args.get("q"), status=request.args.get("status"),
                                      page=page, page_size=size))


@bp.get("/rules/<rule_id>")
@require_roles(*STAFF_ROLES, "instructor")
def rule_detail(rule_id):
    return jsonify(catalog.get_rule(get_db(), rule_id))


@bp.post("/rules")
@require_roles(*ISSUING_ROLES)
def rule_create():
    data = parse_body(RULE_CREATE)
    data["courses"] = _validated_course_items(data["courses"])
    return jsonify(catalog.create_rule(get_db(), data, g.user["user_id"])), 201


@bp.post("/rules/<rule_id>/retire")
@require_roles(*ISSUING_ROLES)
def rule_retire(rule_id):
    return jsonify(catalog.retire_rule(get_db(), rule_id, g.user["user_id"]))


@bp.post("/rules/<rule_id>/issuer")
@require_roles(*ISSUING_ROLES)
def rule_change_issuer(rule_id):
    data = parse_body(RULE_ISSUER)
    return jsonify(catalog.reassign_rule_issuer(get_db(), rule_id, data["issuer_id"], g.user["user_id"]))


@bp.get("/issuers")
@require_roles(*STAFF_ROLES)
def issuers_list():
    return jsonify(issuers.list_issuers(get_db()))


@bp.get("/issuers/<issuer_id>")
@require_roles(*STAFF_ROLES)
def issuer_detail(issuer_id):
    return jsonify(issuers.get_issuer(get_db(), issuer_id))


@bp.post("/issuers")
@require_roles("platform_admin")
def issuer_create():
    data = parse_body(ISSUER_CREATE)
    cfg = current_app.config["APP_CONFIG"]
    return jsonify(issuers.create_issuer(get_db(), cfg, data["name"], g.user["user_id"])), 201


@bp.post("/issuers/<issuer_id>/rotate-key")
@require_roles("platform_admin")
def issuer_rotate_key(issuer_id):
    cfg = current_app.config["APP_CONFIG"]
    return jsonify(issuers.rotate_key(get_db(), cfg, issuer_id, g.user["user_id"]))


@bp.post("/issuers/<issuer_id>/retire")
@require_roles("platform_admin")
def issuer_retire(issuer_id):
    data = parse_body(ISSUER_RETIRE)
    return jsonify(issuers.retire_issuer(get_db(), issuer_id, data["successor_issuer_id"], g.user["user_id"]))
