from flask import Blueprint, Response, current_app, g, jsonify, request

from .. import audit
from ..db import get_db, paginate
from ..errors import not_found
from ..security import ROLES, STAFF_ROLES, require_roles
from ..services import integrity, reports, users
from ..validation import like_pattern, page_params, parse_body

bp = Blueprint("admin", __name__)

USER_CREATE = {
    "email": {"type": "email", "required": True},
    "role": {"type": "str", "required": True, "choices": list(ROLES)},
    "learner_id": {"type": "str", "pattern": r"^LRN-\d{6}$"},
    "instructor_id": {"type": "str", "pattern": r"^INS-\d{4}$"},
    "password": {"type": "str", "max_len": 200},
}
USER_UPDATE = {"role": {"type": "str", "choices": list(ROLES)}, "is_active": {"type": "bool"}}


@bp.get("/users")
@require_roles("platform_admin")
def users_list():
    page, size = page_params()
    return jsonify(users.list_users(get_db(), q=request.args.get("q"), role=request.args.get("role"),
                                    page=page, page_size=size))


@bp.post("/users")
@require_roles("platform_admin")
def users_create():
    return jsonify(users.create_user(get_db(), parse_body(USER_CREATE), g.user["user_id"])), 201


@bp.patch("/users/<user_id>")
@require_roles("platform_admin")
def users_update(user_id):
    return jsonify(users.update_user(get_db(), user_id, parse_body(USER_UPDATE, partial=True), g.user))


@bp.post("/users/<user_id>/reset-password")
@require_roles("platform_admin")
def users_reset_password(user_id):
    return jsonify(users.reset_password(get_db(), user_id, g.user["user_id"]))


@bp.get("/audit")
@require_roles(*STAFF_ROLES)
def audit_list():
    page, size = page_params()
    args = request.args
    where, params = ["1=1"], []
    if args.get("q"):
        where.append("(entity_id LIKE ? ESCAPE '\\' OR event_id LIKE ? ESCAPE '\\')")
        params += [like_pattern(args["q"])] * 2
    for column in ("action", "entity_type", "actor_user_id"):
        if args.get(column):
            where.append(f"{column} = ?")
            params.append(args[column])
    if args.get("from"):
        where.append("occurred_at >= ?")
        params.append(args["from"])
    if args.get("to"):
        where.append("occurred_at <= ?")
        params.append(args["to"])
    sql = ("SELECT event_id, seq, occurred_at, actor_type, actor_user_id, action, entity_type, entity_id, details_json, "
           f"prev_hash, event_hash FROM audit_event WHERE {' AND '.join(where)}")
    return jsonify(paginate(get_db(), sql, params, page, size, "seq DESC"))


@bp.get("/audit/actions")
@require_roles(*STAFF_ROLES)
def audit_actions():
    return jsonify([r[0] for r in get_db().execute("SELECT DISTINCT action FROM audit_event ORDER BY action")])


@bp.get("/audit/verify-chain")
@require_roles(*STAFF_ROLES)
def audit_verify_chain():
    return jsonify(audit.verify_chain(get_db()))


@bp.get("/reports/dashboard")
@require_roles(*STAFF_ROLES)
def reports_dashboard():
    return jsonify(reports.dashboard(get_db()))


@bp.get("/reports/me")
@require_roles("learner", "instructor")
def reports_me():
    if g.user["role"] == "learner":
        return jsonify(reports.learner_summary(get_db(), g.user["learner_id"]))
    return jsonify(reports.instructor_summary(get_db(), g.user["instructor_id"]))


@bp.get("/reports/export/<name>")
@require_roles(*STAFF_ROLES)
def reports_export(name):
    content = reports.export_csv(get_db(), name)
    if content is None:
        raise not_found("Unknown export")
    return Response(content, mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment; filename={name}.csv"})


@bp.get("/integrity/scan")
@require_roles("platform_admin", "academic_admin")
def integrity_scan():
    return jsonify(integrity.scan_summary(get_db()))


@bp.get("/integrity/import-rejections")
@require_roles("platform_admin", "academic_admin")
def integrity_rejections():
    return jsonify(integrity.import_rejections(get_db()))


@bp.get("/integrity/evaluation")
@require_roles("platform_admin", "academic_admin")
def integrity_evaluation():
    cfg = current_app.config["APP_CONFIG"]
    return jsonify(integrity.evaluate_against_ground_truth(get_db(), cfg.ground_truth_dir))
