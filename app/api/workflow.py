from flask import Blueprint, current_app, g, jsonify, request

from ..db import get_db
from ..errors import ApiError, forbidden
from ..ids import CREDENTIAL_RE, LEARNER_RE
from ..security import ISSUING_ROLES, STAFF_ROLES, require_roles
from ..services import completions, issuance, revocation, verification
from ..validation import page_params, parse_body

bp = Blueprint("workflow", __name__)

ENROLL = {"learner_id": {"type": "str", "required": True, "pattern": LEARNER_RE.pattern},
          "course_id": {"type": "str", "required": True, "pattern": r"^CRS-\d{6}$"}}
PROGRESS = {"progress_pct": {"type": "int", "required": True, "min": 0, "max": 100}}
ASSESSMENT = {"score": {"type": "float", "required": True, "min": 0, "max": 100}}
ISSUE = {"learner_id": {"type": "str", "required": True, "pattern": LEARNER_RE.pattern},
         "rule_id": {"type": "str", "required": True, "pattern": r"^RUL-\d{6}$"}}
REVOKE = {"reason_code": {"type": "str", "required": True,
                          "choices": ["fraud", "academic_misconduct", "issued_in_error", "learner_request", "rule_change"]},
          "reason_detail": {"type": "str", "max_len": 500}}
STAFF_VERIFY = {
    "credential_id": {"type": "str", "required": True, "pattern": CREDENTIAL_RE.pattern,
                      "pattern_message": "must look like CRD-2026-000001"},
    "presented_hash": {"type": "str", "max_len": 64, "pattern": r"^[0-9a-fA-F]{64}$"},
    "claimed_name": {"type": "str", "max_len": 120}, "claimed_email": {"type": "email"}, "claimed_dob": {"type": "date"},
    "requester_type": {"type": "str", "choices": ["employer", "institution", "learner", "support", "other"], "default": "support"},
    "requester_org": {"type": "str", "max_len": 120},
}


def _completion_scope_filters():
    user = g.user
    if user["role"] == "learner":
        return {"learner_id": user["learner_id"]}
    if user["role"] == "instructor":
        return {"instructor_id": user["instructor_id"]}
    return {}


def _ensure_completion_visible(completion):
    user = g.user
    if user["role"] == "learner" and completion["learner_id"] != user["learner_id"]:
        raise forbidden()
    if user["role"] == "instructor" and completion["instructor_id"] != user["instructor_id"]:
        raise forbidden()


@bp.get("/completions")
@require_roles()
def completions_list():
    page, size = page_params()
    scope = _completion_scope_filters()
    args = request.args
    return jsonify(completions.list_completions(
        get_db(), learner_id=scope.get("learner_id") or args.get("learner_id"), course_id=args.get("course_id"),
        status=args.get("status"), instructor_id=scope.get("instructor_id"), q=args.get("q"), page=page, page_size=size))


@bp.get("/completions/<completion_id>")
@require_roles()
def completion_detail(completion_id):
    completion = completions.get_completion(get_db(), completion_id)
    _ensure_completion_visible(completion)
    return jsonify(completion)


@bp.post("/completions")
@require_roles(*ISSUING_ROLES)
def completion_enroll():
    data = parse_body(ENROLL)
    return jsonify(completions.enroll(get_db(), data["learner_id"], data["course_id"], g.user["user_id"])), 201


@bp.post("/completions/<completion_id>/progress")
@require_roles("instructor", *ISSUING_ROLES)
def completion_progress(completion_id):
    completions.ensure_assessable_by(get_db(), g.user, completion_id)
    data = parse_body(PROGRESS)
    return jsonify(completions.update_progress(get_db(), completion_id, data["progress_pct"], g.user["user_id"]))


@bp.post("/completions/<completion_id>/assessments")
@require_roles("instructor", *ISSUING_ROLES)
def completion_assessment(completion_id):
    completions.ensure_assessable_by(get_db(), g.user, completion_id)
    data = parse_body(ASSESSMENT)
    return jsonify(completions.record_assessment(get_db(), completion_id, round(data["score"], 1), g.user["user_id"])), 201


@bp.post("/completions/<completion_id>/withdraw")
@require_roles("learner", *ISSUING_ROLES)
def completion_withdraw(completion_id):
    completion = completions.get_completion(get_db(), completion_id)
    if g.user["role"] == "learner" and completion["learner_id"] != g.user["learner_id"]:
        raise forbidden()
    return jsonify(completions.withdraw(get_db(), completion_id, g.user["user_id"]))


@bp.get("/eligibility")
@require_roles(*STAFF_ROLES)
def eligibility_check():
    learner_id, rule_id = request.args.get("learner_id", ""), request.args.get("rule_id", "")
    if not LEARNER_RE.match(learner_id) or not rule_id:
        raise ApiError(400, "VALIDATION_ERROR", "learner_id and rule_id query parameters are required")
    return jsonify(issuance.evaluate(get_db(), learner_id, rule_id))


@bp.get("/eligibility/pending")
@require_roles(*STAFF_ROLES)
def eligibility_pending():
    page, size = page_params()
    return jsonify(issuance.pending_queue(get_db(), rule_id=request.args.get("rule_id"), q=request.args.get("q"),
                                          page=page, page_size=size))


@bp.get("/credentials")
@require_roles()
def credentials_list():
    page, size = page_params()
    args = request.args
    learner_id = args.get("learner_id")
    if g.user["role"] == "learner":
        learner_id = g.user["learner_id"]
    elif g.user["role"] == "instructor":
        raise forbidden()
    return jsonify(issuance.list_credentials(
        get_db(), q=args.get("q"), status=args.get("status"), rule_id=args.get("rule_id"),
        issuer_id=args.get("issuer_id"), learner_id=learner_id, page=page, page_size=size))


@bp.get("/credentials/<credential_id>")
@require_roles()
def credential_detail(credential_id):
    credential = issuance.get_credential(get_db(), credential_id)
    if g.user["role"] == "instructor" or (g.user["role"] == "learner" and credential["learner_id"] != g.user["learner_id"]):
        raise forbidden()
    return jsonify(credential)


@bp.post("/credentials")
@require_roles(*ISSUING_ROLES)
def credential_issue():
    data = parse_body(ISSUE)
    cfg = current_app.config["APP_CONFIG"]
    return jsonify(issuance.issue_credential(get_db(), cfg, data["learner_id"], data["rule_id"], g.user["user_id"])), 201


@bp.post("/credentials/<credential_id>/revoke")
@require_roles(*ISSUING_ROLES)
def credential_revoke(credential_id):
    data = parse_body(REVOKE)
    return jsonify(revocation.revoke_credential(get_db(), credential_id, data["reason_code"], data["reason_detail"],
                                                g.user["user_id"])), 201


@bp.get("/revocations")
@require_roles(*STAFF_ROLES)
def revocations_list():
    page, size = page_params()
    return jsonify(revocation.list_revocations(get_db(), q=request.args.get("q"),
                                               reason_code=request.args.get("reason_code"), page=page, page_size=size))


@bp.get("/verifications")
@require_roles("learner", *STAFF_ROLES)
def verifications_list():
    page, size = page_params()
    args = request.args
    holder = g.user["learner_id"] if g.user["role"] == "learner" else None
    return jsonify(verification.list_verifications(
        get_db(), q=args.get("q"), result_status=args.get("result_status"), channel=args.get("channel"),
        credential_id=args.get("credential_id"), holder_learner_id=holder, page=page, page_size=size))


@bp.get("/verifications/<verification_id>")
@require_roles(*STAFF_ROLES)
def verification_detail(verification_id):
    return jsonify(verification.get_verification(get_db(), verification_id))


@bp.post("/verifications")
@require_roles("support_staff", *ISSUING_ROLES)
def verification_run():
    data = parse_body(STAFF_VERIFY)
    result = verification.verify(
        get_db(), presented_credential_id=data["credential_id"], presented_hash=data["presented_hash"],
        claimed_name=data["claimed_name"], claimed_email=data["claimed_email"], claimed_dob=data["claimed_dob"],
        channel="support_desk", requester_type=data["requester_type"] or "support",
        requester_org=data["requester_org"], processed_by=g.user["user_id"])
    return jsonify(result), 201


@bp.post("/verifications/<verification_id>/replay")
@require_roles(*STAFF_ROLES)
def verification_replay(verification_id):
    return jsonify(verification.replay(get_db(), verification_id))
