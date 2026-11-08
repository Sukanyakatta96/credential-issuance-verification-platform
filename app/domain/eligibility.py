from statistics import mean


def _check(code: str, label: str, passed: bool, detail: str) -> dict:
    return {"code": code, "label": label, "passed": passed, "detail": detail}


def evaluate_eligibility(*, rule: dict, rule_courses: list[dict], completions_by_course: dict[str, dict],
                         learner_status: str, has_active_credential: bool, has_blocking_revocation: bool,
                         as_of: str) -> dict:
    """Pure rule evaluation. Every issuance decision, in the app and in the data generator, goes through here."""
    checks = []

    in_window = (rule["status"] == "active" and rule["effective_from"] <= as_of
                 and (rule["effective_to"] is None or as_of < rule["effective_to"]))
    checks.append(_check("RULE_EFFECTIVE", "Credential rule is active and effective", in_window,
                         f"status={rule['status']}, effective {rule['effective_from']} to {rule['effective_to'] or 'open-ended'}"))

    checks.append(_check("LEARNER_ACTIVE", "Learner account is active", learner_status == "active",
                         f"learner status is {learner_status}"))

    counted = {}
    for course in rule_courses:
        completion = completions_by_course.get(course["course_id"])
        if (completion and completion["status"] == "completed" and completion["final_score"] is not None
                and completion["final_score"] >= rule["min_course_score"]):
            counted[course["course_id"]] = completion

    mandatory = [c["course_id"] for c in rule_courses if c["is_mandatory"]]
    missing_mandatory = [c for c in mandatory if c not in counted]
    checks.append(_check("MANDATORY_COURSES", "All mandatory courses completed at or above the minimum course score",
                         not missing_mandatory,
                         "all satisfied" if not missing_mandatory else "missing: " + ", ".join(missing_mandatory)))

    checks.append(_check("MIN_COURSES", f"At least {rule['min_courses_required']} qualifying courses completed",
                         len(counted) >= rule["min_courses_required"],
                         f"{len(counted)} of {rule['min_courses_required']} required"))

    average = round(mean(c["final_score"] for c in counted.values()), 2) if counted else 0.0
    checks.append(_check("MIN_AVERAGE", f"Average score of counted courses at least {rule['min_avg_score']}",
                         bool(counted) and average >= rule["min_avg_score"], f"average is {average}"))

    checks.append(_check("NO_ACTIVE_CREDENTIAL", "Learner does not already hold an active credential for this rule",
                         not has_active_credential,
                         "an active credential already exists" if has_active_credential else "none held"))

    checks.append(_check("NOT_BLOCKED_BY_REVOCATION",
                         "No earlier credential for this rule was revoked for fraud or misconduct",
                         not has_blocking_revocation,
                         "blocked by a fraud/misconduct revocation" if has_blocking_revocation else "no blocking revocation"))

    return {
        "eligible": all(c["passed"] for c in checks),
        "checks": checks,
        "qualifying_completion_ids": sorted(c["completion_id"] for c in counted.values()),
        "average_score": average,
        "counted_courses": len(counted),
        "latest_completion_at": max((c["finalized_at"] for c in counted.values()), default=None),
    }
