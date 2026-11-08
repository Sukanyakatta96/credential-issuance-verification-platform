import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from app import audit, crypto, ids
from app.domain.completion import derive_completion_state
from app.domain.eligibility import evaluate_eligibility
from app.domain import issue_types as T
from app.domain.payload import build_payload
from app.timeutil import add_months, to_ts

from . import pools
from .outcomes import expected_identity, expected_result

UTC = timezone.utc
REF = datetime(2026, 10, 22, 18, 0, 0, tzinfo=UTC)
GO_LIVE = datetime(2026, 1, 5, 9, 0, 0, tzinfo=UTC)
ISSUER_CHANGE = datetime(2026, 7, 1, 0, 0, 0, tzinfo=UTC)
KEY_ROTATION = datetime(2026, 4, 1, 0, 0, 0, tzinfo=UTC)
CATALOG_START = datetime(2025, 9, 1, 8, 0, 0, tzinfo=UTC)
RULES_EFFECTIVE_EARLY = datetime(2025, 10, 1, 0, 0, 0, tzinfo=UTC)
RULES_EFFECTIVE_LATE = datetime(2026, 3, 1, 0, 0, 0, tzinfo=UTC)
RULE_RETIRED_AT = datetime(2026, 8, 15, 0, 0, 0, tzinfo=UTC)
DRAFT_EFFECTIVE = datetime(2026, 11, 15, 0, 0, 0, tzinfo=UTC)
GENERATOR_VERSION = "1.0.0"

SCALES = {"full": (20000, 1000, 10000, 5000), "starter": (2000, 100, 1000, 500)}


@dataclass
class Params:
    seed: int = 20261022
    learners: int = 20000
    courses: int = 1000
    credentials: int = 10000
    verifications: int = 5000
    signing_secret: str = ""

    @property
    def anomaly_counts(self):
        return {"issued_before_completion": max(2, round(self.credentials * 0.003)),
                "duplicate_id": max(2, round(self.credentials * 0.0008)),
                "revoked_verifies_active": max(2, round(self.verifications * 0.005)),
                "altered_hash": max(2, round(self.verifications * 0.004))}


@dataclass
class Dataset:
    tables: dict
    ground_truth: list
    decisions: list
    counters: dict
    meta: dict = field(default_factory=dict)


def days(n):
    return timedelta(days=n)


def clip(value, low, high):
    return max(low, min(high, value))


def pick_weighted(rng, pairs):
    return rng.choices([p[0] for p in pairs], weights=[p[1] for p in pairs])[0]


def random_time(rng, start, end):
    span = (end - start).total_seconds()
    return (start + timedelta(seconds=int(rng.uniform(0, span)))).replace(microsecond=0)


def slug(text):
    return "".join(ch for ch in text.lower() if ch.isalnum())


def generate(params: Params) -> Dataset:
    if not params.signing_secret:
        raise ValueError("signing_secret is required so issuer public keys match the application")
    rng = random.Random(params.seed)
    signer = crypto.SignerCache(params.signing_secret)
    t: dict[str, list] = {}

    # ---------------------------------------------------------------- staff, issuers, instructors
    n_instructors = max(3, params.courses // 16)
    t["instructor"] = []
    for n in range(1, n_instructors + 1):
        first, last = rng.choice(pools.FIRST_NAMES), rng.choice(pools.LAST_NAMES)
        t["instructor"].append({"instructor_id": ids.instructor_id(n), "full_name": f"{first} {last}",
                                "email": f"{slug(first)}.{slug(last)}.{n}@faculty.example",
                                "department": rng.choice(pools.DEPARTMENTS)})

    users = []
    def add_user(role, email, learner_id=None, instructor_id=None):
        users.append({"user_id": ids.user_id(len(users) + 1), "email": email, "role": role, "learner_id": learner_id,
                      "instructor_id": instructor_id, "is_active": 1, "created_at": "2025-08-15T09:00:00Z"})
        return users[-1]["user_id"]
    admins = [add_user("academic_admin", f"academic.admin{i}@credentials.example") for i in (1, 2, 3)]
    supports = [add_user("support_staff", f"support{i}@credentials.example") for i in (1, 2, 3)]
    platform = [add_user("platform_admin", f"platform.admin{i}@credentials.example") for i in (1, 2)]
    for ins in t["instructor"]:
        add_user("instructor", ins["email"], instructor_id=ins["instructor_id"])

    issuers, keys = [], []
    def add_issuer(n, valid_from, status="active", valid_to=None, successor=None):
        issuers.append({"issuer_id": ids.issuer_id(n), "name": pools.ISSUER_NAMES[n - 1], "status": status,
                        "valid_from": to_ts(valid_from), "valid_to": to_ts(valid_to) if valid_to else None,
                        "successor_issuer_id": ids.issuer_id(successor) if successor else None})
    def add_key(n, version, valid_from, valid_to=None):
        iid = ids.issuer_id(n)
        kid = ids.key_id(iid, version)
        keys.append({"key_id": kid, "issuer_id": iid, "algorithm": "Ed25519", "public_key_b64": signer.public_key_b64(kid),
                     "valid_from": to_ts(valid_from), "valid_to": to_ts(valid_to) if valid_to else None,
                     "status": "rotated" if valid_to else "active"})
    add_issuer(1, CATALOG_START, "retired", ISSUER_CHANGE, 7)
    add_issuer(2, CATALOG_START, "retired", ISSUER_CHANGE, 8)
    for n in (3, 4, 5, 6):
        add_issuer(n, CATALOG_START)
    add_issuer(7, ISSUER_CHANGE)
    add_issuer(8, ISSUER_CHANGE)
    add_key(1, 1, CATALOG_START, ISSUER_CHANGE)
    add_key(2, 1, CATALOG_START, ISSUER_CHANGE)
    add_key(3, 1, CATALOG_START, KEY_ROTATION)
    add_key(3, 2, KEY_ROTATION)
    for n in (4, 5, 6):
        add_key(n, 1, CATALOG_START)
    add_key(7, 1, ISSUER_CHANGE)
    add_key(8, 1, ISSUER_CHANGE)
    t["issuer"], t["issuer_key"] = issuers, keys
    keys_by_issuer: dict[str, list] = {}
    for k in keys:
        keys_by_issuer.setdefault(k["issuer_id"], []).append(k)

    # ---------------------------------------------------------------- courses
    n_categories = min(len(pools.CATEGORIES), max(2, params.courses // 8))
    categories = list(pools.CATEGORIES)[:n_categories]
    courses, course_by_id, titles_seen = [], {}, set()
    for n in range(1, params.courses + 1):
        category = categories[(n - 1) % n_categories]
        level = pick_weighted(rng, [("introductory", 40), ("intermediate", 40), ("advanced", 20)])
        base = f"{rng.choice(pools.CATEGORIES[category])} {rng.choice(pools.LEVEL_SUFFIX[level])}"
        title, part = base, 1
        while title in titles_seen:
            part += 1
            title = f"{base} {part}"
        titles_seen.add(title)
        pass_mark = pick_weighted(rng, [(50, 5), (55, 10), (60, 35), (65, 20), (70, 20), (75, 10)])
        course = {"course_id": ids.course_id(n), "title": title, "category": category, "level": level,
                  "credit_hours": rng.randint(8, 60), "pass_mark": pass_mark,
                  "max_attempts": pick_weighted(rng, [(2, 35), (3, 45), (4, 20)]),
                  "instructor_id": rng.choice(t["instructor"])["instructor_id"],
                  "status": "archived" if rng.random() < 0.05 else "active",
                  "created_at": to_ts(random_time(rng, datetime(2025, 5, 1, tzinfo=UTC), datetime(2025, 8, 30, tzinfo=UTC)))}
        courses.append(course)
        course_by_id[course["course_id"]] = course
    t["course"] = courses
    courses_by_category: dict[str, list] = {}
    for c in courses:
        courses_by_category.setdefault(c["category"], []).append(c["course_id"])

    # ---------------------------------------------------------------- rules, bridge, issuer assignments
    n_rules = max(6, params.courses // 7)
    rules, rule_courses, assignments, rule_titles = [], [], [], set()
    audit_events: list[dict] = []
    def add_audit(when, rank, action, entity_type, entity_id, details, actor_user=None, actor_type=None):
        audit_events.append({"when": when, "rank": rank, "action": action, "entity_type": entity_type,
                             "entity_id": entity_id, "details": details, "actor_user": actor_user,
                             "actor_type": actor_type or ("user" if actor_user else "system")})
    for n in range(1, n_rules + 1):
        category = categories[(n - 1) % n_categories]
        pool = courses_by_category[category]
        k = min(len(pool), rng.choice([3, 3, 4, 4, 5]))
        chosen = rng.sample(pool, k)
        mandatory_n = 1 if k == 3 else rng.choice([1, 2])
        min_courses = k - rng.choice([0, 0, 1]) if k > mandatory_n + 1 else k
        min_courses = max(min_courses, mandatory_n)
        status = pick_weighted(rng, [("active", 88), ("retired", 7), ("draft", 5)])
        if status == "draft":
            effective_from, effective_to = DRAFT_EFFECTIVE, None
        else:
            effective_from = RULES_EFFECTIVE_EARLY if rng.random() < 0.85 else RULES_EFFECTIVE_LATE
            effective_to = RULE_RETIRED_AT if status == "retired" else None
        credential_type = {3: "micro_credential", 4: "certificate"}.get(k, "professional_certificate")
        base_title = f"{category} {credential_type.replace('_', ' ').title()}"
        title, part = base_title, 1
        while title in rule_titles:
            part += 1
            title = f"{base_title} {part}"
        rule_titles.add(title)
        rule = {"rule_id": ids.rule_id(n), "title": title, "credential_type": credential_type, "version": 1,
                "min_courses_required": min_courses, "min_avg_score": float(rng.choice([65, 70, 75])),
                "min_course_score": float(rng.choice([60, 65, 70])),
                "validity_months": pick_weighted(rng, [(None, 50), (6, 15), (12, 20), (24, 15)]),
                "effective_from": to_ts(effective_from), "effective_to": to_ts(effective_to) if effective_to else None,
                "status": status, "created_at": to_ts(effective_from - days(rng.randint(10, 40)))}
        rules.append(rule)
        for index, cid in enumerate(chosen):
            rule_courses.append({"rule_id": rule["rule_id"], "course_id": cid, "is_mandatory": 1 if index < mandatory_n else 0})
        base_issuer = pick_weighted(rng, [(1, 3), (2, 3), (3, 2), (4, 2), (5, 2), (6, 2)])
        def add_assignment(issuer_n, start, end):
            assignments.append({"assignment_id": ids.assignment_id(len(assignments) + 1), "rule_id": rule["rule_id"],
                                "issuer_id": ids.issuer_id(issuer_n), "effective_from": to_ts(start),
                                "effective_to": to_ts(end) if end else None})
        if base_issuer in (1, 2) and effective_from >= ISSUER_CHANGE:
            add_assignment(base_issuer + 6, effective_from, None)
        elif base_issuer in (1, 2):
            add_assignment(base_issuer, effective_from, ISSUER_CHANGE)
            add_assignment(base_issuer + 6, ISSUER_CHANGE, None)
        else:
            add_assignment(base_issuer, effective_from, None)
        add_audit(effective_from - days(rng.randint(1, 9)), 20, "rule.created", "credential_rule", rule["rule_id"],
                  {"title": title, "courses": sorted(chosen)}, admins[0])
    t["credential_rule"], t["credential_rule_course"], t["rule_issuer_assignment"] = rules, rule_courses, assignments
    rule_by_id = {r["rule_id"]: r for r in rules}
    courses_of_rule: dict[str, list] = {}
    rules_of_course: dict[str, list] = {}
    for rc in rule_courses:
        courses_of_rule.setdefault(rc["rule_id"], []).append({"course_id": rc["course_id"], "is_mandatory": rc["is_mandatory"]})
        rules_of_course.setdefault(rc["course_id"], []).append(rc["rule_id"])
    assignments_of_rule: dict[str, list] = {}
    for a in assignments:
        assignments_of_rule.setdefault(a["rule_id"], []).append(a)
    pursuable = [r["rule_id"] for r in rules if r["status"] != "draft"]

    def issuer_at(rule_id, when_ts):
        for a in assignments_of_rule[rule_id]:
            if a["effective_from"] <= when_ts and (a["effective_to"] is None or when_ts < a["effective_to"]):
                return a["issuer_id"]
        return None

    def key_at(issuer_id, when_ts):
        for k in keys_by_issuer[issuer_id]:
            if k["valid_from"] <= when_ts and (k["valid_to"] is None or when_ts < k["valid_to"]):
                return k["key_id"]
        return None

    # ---------------------------------------------------------------- learners
    learners, name_index = [], {}
    duplicate_probability = 0.012
    for n in range(1, params.learners + 1):
        if learners and rng.random() < duplicate_probability:
            twin = rng.choice(learners)
            full_name = twin["full_name"]
            dob = twin["date_of_birth"] if rng.random() < 0.1 else None
            first, last = full_name.split()[0], full_name.split()[-1]
        else:
            first, last, dob = rng.choice(pools.FIRST_NAMES), rng.choice(pools.LAST_NAMES), None
            full_name = f"{first} {last}" if rng.random() < 0.15 else f"{first} {chr(65 + rng.randint(0, 25))}. {last}"
        if dob is None:
            dob = (datetime(1960, 1, 1) + timedelta(days=rng.randint(0, 17500))).strftime("%Y-%m-%d")
        learner = {"learner_id": ids.learner_id(n), "full_name": full_name,
                   "email": f"{slug(first)}.{slug(last)}.{n}@mail.example", "date_of_birth": dob,
                   "country_code": pick_weighted(rng, pools.COUNTRIES),
                   "registered_at": to_ts(random_time(rng, datetime(2025, 6, 1, tzinfo=UTC), datetime(2026, 8, 1, tzinfo=UTC))),
                   "status": pick_weighted(rng, [("active", 965), ("suspended", 20), ("closed", 15)])}
        learners.append(learner)
        name_index.setdefault(full_name.lower(), []).append(learner)
    t["learner"] = learners
    learner_by_id = {l["learner_id"]: l for l in learners}
    for l in learners[:min(300, params.learners // 50)]:
        add_user("learner", l["email"], learner_id=l["learner_id"])
    t["app_user"] = users

    # ---------------------------------------------------------------- enrolments, attempts, completions
    completions, attempts = [], []
    completion_of: dict[tuple, dict] = {}
    level_adjust = {"introductory": 3, "intermediate": 0, "advanced": -4}

    def enrol(learner, course_id, committed, ability):
        course = course_by_id[course_id]
        enrolled_at = datetime.fromisoformat(learner["registered_at"].replace("Z", "+00:00")) + days(rng.uniform(0, 60))
        enrolled_at = min(enrolled_at, REF - days(3)).replace(microsecond=0)
        duration = rng.uniform(28, 70)
        content_done_at = enrolled_at + days(duration)
        withdrawn_at, scores, progress = None, [], 0
        roll = rng.random()
        if roll < (0.02 if committed else 0.15):
            candidate = enrolled_at + days(rng.uniform(5, 60))
            if candidate <= REF:
                withdrawn_at = candidate.replace(microsecond=0)
            progress = rng.randint(0, 85)
        elif rng.random() > (0.98 if committed else 0.65):
            progress = rng.randint(10, 90)
        elif content_done_at > REF:
            progress = clip(int(100 * (REF - enrolled_at).total_seconds() / (duration * 86400)), 1, 99)
        else:
            progress = 100
            when = content_done_at + days(rng.uniform(1, 5))
            for attempt_no in range(1, course["max_attempts"] + 1):
                if when > REF:
                    break
                score = round(clip(ability + rng.gauss(0, 8) + level_adjust[course["level"]] + 4 * (attempt_no - 1), 0, 100), 1)
                scores.append((score, when.replace(microsecond=0)))
                if score >= course["pass_mark"]:
                    break
                when = when + days(rng.uniform(7, 21))
        state = derive_completion_state(pass_mark=course["pass_mark"], max_attempts=course["max_attempts"],
                                        progress_pct=progress, attempt_scores=[s for s, _ in scores],
                                        withdrawn=withdrawn_at is not None)
        finalized = None
        if state["status"] == "completed":
            finalized = scores[state["first_pass_index"]][1]
        elif state["status"] == "failed":
            finalized = scores[-1][1]
        elif state["status"] == "withdrawn":
            finalized = withdrawn_at
        cid = ids.completion_id(learner["learner_id"], course_id)
        record = {"completion_id": cid, "learner_id": learner["learner_id"], "course_id": course_id,
                  "enrolled_at": to_ts(enrolled_at), "progress_pct": progress, "status": state["status"],
                  "attempts_used": state["attempts_used"], "final_score": state["final_score"],
                  "finalized_at": to_ts(finalized) if finalized else None}
        completions.append(record)
        completion_of[(learner["learner_id"], course_id)] = record
        for number, (score, when_attempt) in enumerate(scores, start=1):
            attempts.append({"attempt_id": ids.attempt_id(cid, number), "completion_id": cid, "attempt_no": number,
                             "score": score, "passed": 1 if score >= course["pass_mark"] else 0,
                             "attempted_at": to_ts(when_attempt)})
        if finalized:
            add_audit(finalized, 40, "completion.finalized", "completion_record", cid,
                      {"final_score": state["final_score"], "status": state["status"]})

    for learner in learners:
        ability = clip(rng.gauss(82, 9), 45, 99)
        planned = []
        committed = rng.random() < 0.94
        if rng.random() < 0.95:
            program_courses = [c["course_id"] for c in courses_of_rule[rng.choice(pursuable)]]
            if not committed and len(program_courses) > 1:
                program_courses = rng.sample(program_courses, rng.randint(1, len(program_courses) - 1))
            planned.extend(program_courses)
        if rng.random() < 0.25 or not planned:
            planned.extend(rng.sample([c["course_id"] for c in courses], rng.randint(1, 2)))
        for course_id in dict.fromkeys(planned):
            enrol(learner, course_id, committed, ability)
    t["completion_record"], t["assessment_attempt"] = completions, attempts

    # ---------------------------------------------------------------- eligibility derived from rules
    candidates = []
    completed_by_learner: dict[str, list] = {}
    for rec in completions:
        if rec["status"] == "completed":
            completed_by_learner.setdefault(rec["learner_id"], []).append(rec)
    for learner_id, recs in completed_by_learner.items():
        learner = learner_by_id[learner_id]
        if learner["status"] != "active":
            continue
        candidate_rules = sorted({r for rec in recs for r in rules_of_course.get(rec["course_id"], [])
                                  if rule_by_id[r]["status"] != "draft"})
        for rule_id in candidate_rules:
            rule = rule_by_id[rule_id]
            by_course = {r["course_id"]: r for r in recs}
            latest = max(datetime.fromisoformat(r["finalized_at"].replace("Z", "+00:00")) for r in recs
                         if r["course_id"] in {c["course_id"] for c in courses_of_rule[rule_id]})
            issue_dt = max(latest + days(rng.uniform(0.2, 14)), GO_LIVE,
                           datetime.fromisoformat(rule["effective_from"].replace("Z", "+00:00"))).replace(microsecond=0)
            if issue_dt > REF or (rule["effective_to"] and to_ts(issue_dt) >= rule["effective_to"]):
                continue
            result = evaluate_eligibility(
                rule={**rule, "status": "active"}, rule_courses=courses_of_rule[rule_id], completions_by_course=by_course,
                learner_status=learner["status"], has_active_credential=False, has_blocking_revocation=False,
                as_of=to_ts(issue_dt))
            if result["eligible"]:
                candidates.append({"learner_id": learner_id, "rule_id": rule_id, "issue_dt": issue_dt,
                                   "latest_dt": latest, "completion_ids": result["qualifying_completion_ids"],
                                   "average": result["average_score"]})
    candidates.sort(key=lambda c: (c["learner_id"], c["rule_id"]))
    anomalies = params.anomaly_counts
    needed = params.credentials + anomalies["duplicate_id"]
    if len(candidates) < needed:
        raise RuntimeError(f"Only {len(candidates)} eligible learner/rule pairs exist but {needed} are needed; "
                           "increase learners relative to credentials")
    rng.shuffle(candidates)
    selected, spare = candidates[:params.credentials], candidates[params.credentials:]
    eligible_total = len(candidates)

    # A1: credential issued before completion (still a properly signed credential)
    a1_pool = [c for c in selected if c["latest_dt"] >= datetime(2026, 1, 20, tzinfo=UTC)
               and c["latest_dt"] - days(10) >= datetime.fromisoformat(rule_by_id[c["rule_id"]]["effective_from"].replace("Z", "+00:00"))]
    a1_chosen = rng.sample(a1_pool, min(anomalies["issued_before_completion"], len(a1_pool)))
    a1_keys = set()
    for c in a1_chosen:
        c["issue_dt"] = (c["latest_dt"] - days(rng.uniform(0.5, 9))).replace(microsecond=0)
        a1_keys.add((c["learner_id"], c["rule_id"]))
    selected.sort(key=lambda c: (c["issue_dt"], c["learner_id"], c["rule_id"]))

    # ---------------------------------------------------------------- credentials (signed)
    credentials, bridge = [], []
    credential_truth: dict[str, dict] = {}

    def build_credential(candidate, credential_id):
        rule = rule_by_id[candidate["rule_id"]]
        issued_ts = to_ts(candidate["issue_dt"])
        issuer_id = issuer_at(rule["rule_id"], issued_ts)
        key_id = key_at(issuer_id, issued_ts)
        expires = to_ts(add_months(candidate["issue_dt"], rule["validity_months"])) if rule["validity_months"] else None
        payload = build_payload(credential_id=credential_id, learner_id=candidate["learner_id"], rule=rule,
                                issuer_id=issuer_id, key_id=key_id, issued_at=issued_ts, expires_at=expires,
                                completion_ids=candidate["completion_ids"])
        payload_json = crypto.canonical_json(payload)
        digest = crypto.payload_hash(payload_json)
        return {"credential_id": credential_id, "learner_id": candidate["learner_id"], "rule_id": rule["rule_id"],
                "issuer_id": issuer_id, "key_id": key_id, "issued_at": issued_ts, "expires_at": expires,
                "status": "active", "payload_json": payload_json, "payload_hash": digest,
                "signature_b64": signer.sign(key_id, digest), "issued_by": rng.choice(admins)}

    for number, cand in enumerate(selected, start=1):
        cred = build_credential(cand, ids.credential_id(2026, number))
        credentials.append(cred)
        credential_truth[cred["credential_id"]] = {"row": cred, "intact": True, "revoked_at": None,
                                                   "original_hash": cred["payload_hash"]}
        bridge.extend({"credential_id": cred["credential_id"], "completion_id": cid} for cid in cand["completion_ids"])
        add_audit(cand["issue_dt"], 30, "credential.issued", "credential", cred["credential_id"],
                  {"average_score": cand["average"], "issuer_id": cred["issuer_id"], "learner_id": cred["learner_id"],
                   "payload_hash": cred["payload_hash"], "rule_id": cred["rule_id"]}, cred["issued_by"])
    a1_credential_ids = [c["credential_id"] for c, cand in zip(credentials, selected) if (cand["learner_id"], cand["rule_id"]) in a1_keys]

    # ---------------------------------------------------------------- revocations
    revocations = []
    revoke_pool = [c for c in credentials if c["credential_id"] not in set(a1_credential_ids)]
    n_revoke = round(len(credentials) * 0.06)
    for cred in rng.sample(revoke_pool, min(n_revoke, len(revoke_pool))):
        issued = datetime.fromisoformat(cred["issued_at"].replace("Z", "+00:00"))
        latest = REF - days(1)
        if issued + days(1) >= latest:
            continue
        effective = min(issued + days(rng.uniform(1, 120)), latest).replace(microsecond=0)
        reason, _, detail = rng.choices(pools.REVOCATION_REASONS, weights=[r[1] for r in pools.REVOCATION_REASONS])[0]
        revoker = rng.choice(admins + platform)
        revocations.append({"revocation_id": ids.revocation_id(cred["credential_id"], 1), "credential_id": cred["credential_id"],
                            "seq": 1, "reason_code": reason, "reason_detail": detail, "effective_at": to_ts(effective),
                            "revoked_by": revoker})
        cred["status"] = "revoked"
        credential_truth[cred["credential_id"]]["revoked_at"] = to_ts(effective)
        add_audit(effective, 35, "credential.revoked", "credential", cred["credential_id"],
                  {"reason_code": reason, "revocation_id": revocations[-1]["revocation_id"]}, revoker)
    revocations.sort(key=lambda r: r["revocation_id"])

    # ---------------------------------------------------------------- A4 tamper selection
    a1_set = set(a1_credential_ids)
    tamper_pool = [c for c in credentials if c["status"] == "active" and c["credential_id"] not in a1_set]
    tampered = rng.sample(tamper_pool, min(anomalies["altered_hash"], len(tamper_pool)))
    tampered_ids = {c["credential_id"] for c in tampered}
    for cred in tampered:
        credential_truth[cred["credential_id"]]["intact"] = False

    # ---------------------------------------------------------------- verification requests
    n_total = params.verifications
    n_a3, n_a4 = anomalies["revoked_verifies_active"], len(tampered)
    n_normal = n_total - n_a3 - n_a4
    pool = [c for c in credentials if c["credential_id"] not in tampered_ids]
    weights = [2.5 if c["status"] == "revoked" else 1.0 for c in pool]
    rows = []
    learner_name_index = name_index

    def verification_row(requested_dt, presented_id, cred, channel, requester_type, org, processed_by,
                         presented_hash=None, claims=None):
        claims = claims or {}
        return {"_dt": requested_dt, "presented_credential_id": presented_id, "credential": cred, "channel": channel,
                "requester_type": requester_type, "requester_org": org, "processed_by": processed_by,
                "presented_hash": presented_hash, "claimed_name": claims.get("name"),
                "claimed_email": claims.get("email"), "claimed_dob": claims.get("dob")}

    def make_claims(learner):
        roll = rng.random()
        if roll < 0.55:
            return {}
        kind = pick_weighted(rng, [("name_email", 35), ("name_dob", 15), ("name_only", 20), ("namesake_email", 10),
                                   ("wrong_dob", 8), ("email_only", 7), ("messy_name_email", 5)])
        if kind == "name_email":
            return {"name": learner["full_name"], "email": learner["email"]}
        if kind == "name_dob":
            return {"name": learner["full_name"], "dob": learner["date_of_birth"]}
        if kind == "name_only":
            return {"name": learner["full_name"]}
        if kind == "namesake_email":
            others = [o for o in learner_name_index[learner["full_name"].lower()] if o["learner_id"] != learner["learner_id"]]
            other_email = others[0]["email"] if others else f"someone.else.{rng.randint(1, 10**6)}@mail.example"
            return {"name": learner["full_name"], "email": other_email}
        if kind == "wrong_dob":
            return {"name": learner["full_name"], "email": learner["email"], "dob": "1970-01-01"
                    if learner["date_of_birth"] != "1970-01-01" else "1971-02-02"}
        if kind == "email_only":
            return {"email": learner["email"]}
        return {"name": f"  {learner['full_name'].upper()} ", "email": learner["email"].upper()}

    def channel_mix():
        channel = pick_weighted(rng, [("public_api", 70), ("learner_share", 15), ("support_desk", 15)])
        if channel == "public_api":
            return channel, pick_weighted(rng, [("employer", 55), ("institution", 30), ("other", 15)]), rng.choice(pools.REQUESTER_ORGS), None
        if channel == "learner_share":
            return channel, "learner", None, None
        return channel, "support", None, rng.choice(supports)

    for _ in range(n_normal):
        channel, rtype, org, processed_by = channel_mix()
        if rng.random() < 0.03:
            fake = ids.credential_id(2026, len(credentials) + rng.randint(1, 5000))
            rows.append(verification_row(random_time(rng, GO_LIVE, REF), fake, None, channel, rtype, org, processed_by))
            continue
        cred = rng.choices(pool, weights=weights)[0]
        issued = datetime.fromisoformat(cred["issued_at"].replace("Z", "+00:00"))
        requested = max(random_time(rng, issued + timedelta(hours=1), REF), issued + timedelta(hours=1)) if issued + timedelta(hours=2) < REF else REF
        learner = learner_by_id[cred["learner_id"]]
        presented = None
        if rng.random() < 0.08:
            presented = cred["payload_hash"] if rng.random() < 0.5 else "%064x" % rng.getrandbits(256)
        rows.append(verification_row(requested, cred["credential_id"], cred, channel, rtype, org, processed_by,
                                     presented, make_claims(learner)))
    a3_pool = [c for c in credentials if c["status"] == "revoked"]
    a3_creds = rng.sample(a3_pool, min(n_a3, len(a3_pool)))
    a3_marker, a4_marker = [], []
    for cred in a3_creds:
        revoked = datetime.fromisoformat(credential_truth[cred["credential_id"]]["revoked_at"].replace("Z", "+00:00"))
        when = min(revoked + days(rng.uniform(0.05, 60)), REF).replace(microsecond=0)
        row = verification_row(when, cred["credential_id"], cred, "public_api", "employer", rng.choice(pools.REQUESTER_ORGS), None)
        row["_forced"] = ("valid", "not_requested", 1)
        rows.append(row)
        a3_marker.append(row)
    for cred in tampered:
        issued = datetime.fromisoformat(cred["issued_at"].replace("Z", "+00:00"))
        when = min(issued + days(rng.uniform(1, 100)), REF).replace(microsecond=0)
        row = verification_row(when, cred["credential_id"], cred, "public_api", rng.choice(["employer", "institution"]),
                               rng.choice(pools.REQUESTER_ORGS), None)
        row["_forced"] = ("valid", "not_requested", 1)
        rows.append(row)
        a4_marker.append(row)
    rows.sort(key=lambda r: (r["_dt"], r["presented_credential_id"], r["claimed_email"] or ""))

    verifications, decisions = [], []
    for number, row in enumerate(rows, start=1):
        vid = ids.verification_id(2026, number)
        row["_vid"] = vid
        cred = row["credential"]
        requested_ts = to_ts(row["_dt"])
        truth = credential_truth.get(cred["credential_id"]) if cred else None
        learner = learner_by_id[cred["learner_id"]] if cred else None
        hash_ok = None if not row["presented_hash"] or not truth else row["presented_hash"] == truth["original_hash"]
        exp_status = expected_result(
            exists=cred is not None, issued_at=cred["issued_at"] if cred else None,
            intact=truth["intact"] if truth else True, revoked_at=truth["revoked_at"] if truth else None,
            expires_at=cred["expires_at"] if cred else None, requested_at=requested_ts, presented_hash_ok=hash_ok)
        exp_identity = ("not_requested" if exp_status == "not_found" else
                        expected_identity(learner=learner, name=row["claimed_name"], email=row["claimed_email"], dob=row["claimed_dob"]))
        exp_integrity = None if exp_status == "not_found" else (1 if truth["intact"] else 0)
        if "_forced" in row:
            rec_status, rec_identity, rec_integrity = row["_forced"]
        else:
            rec_status, rec_identity, rec_integrity = exp_status, exp_identity, exp_integrity
        credential_ref = cred["credential_id"] if exp_status != "not_found" else None
        verifications.append({
            "verification_id": vid, "presented_credential_id": row["presented_credential_id"], "credential_id": credential_ref,
            "requested_at": requested_ts, "channel": row["channel"], "requester_type": row["requester_type"],
            "requester_org": row["requester_org"], "presented_hash": row["presented_hash"],
            "claimed_name": row["claimed_name"], "claimed_email": row["claimed_email"], "claimed_dob": row["claimed_dob"],
            "result_status": rec_status, "identity_status": rec_identity, "integrity_ok": rec_integrity,
            "processed_by": row["processed_by"]})
        decisions.append({"verification_id": vid, "expected_result_status": exp_status,
                          "expected_identity_status": exp_identity, "expected_integrity_ok": exp_integrity})
        add_audit(row["_dt"], 50, "verification.performed", "verification_request", vid,
                  {"channel": row["channel"], "credential_id": credential_ref, "identity_status": rec_identity,
                   "result_status": rec_status}, row["processed_by"], None if row["processed_by"] else "public")

    # ---------------------------------------------------------------- inject tampering after verification truth is fixed
    for cred in tampered:
        original = cred["payload_hash"]
        cred["payload_hash"] = ("1" if original[0] == "0" else "0") + original[1:]

    # ---------------------------------------------------------------- A2 duplicate credential IDs (appended raw rows)
    dup_targets = rng.sample([c for c in credentials if c["credential_id"] not in a1_set | tampered_ids and c["status"] == "active"],
                             anomalies["duplicate_id"])
    duplicate_rows = []
    for target, cand in zip(dup_targets, spare):
        cand = dict(cand)
        cand["issue_dt"] = max(cand["issue_dt"], cand["latest_dt"] + timedelta(hours=1))
        if cand["issue_dt"] > REF:
            cand["issue_dt"] = REF
        duplicate_rows.append((build_credential(cand, target["credential_id"]), cand))
    base_count = len(credentials)
    for cred, _ in duplicate_rows:
        credentials.append(cred)

    # ---------------------------------------------------------------- issuer lifecycle audit events
    for n, issuer in enumerate(issuers, start=1):
        add_audit(datetime.fromisoformat(issuer["valid_from"].replace("Z", "+00:00")) - timedelta(hours=1), 10,
                  "issuer.created", "issuer", issuer["issuer_id"], {"name": issuer["name"]}, platform[0])
    add_audit(KEY_ROTATION, 12, "issuer_key.rotated", "issuer", "ISS-003",
              {"new_key": "KEY-ISS-003-02", "retired_key": "KEY-ISS-003-01"}, platform[0])
    for n in (1, 2):
        moved = sum(1 for a in assignments if a["issuer_id"] == ids.issuer_id(n) and a["effective_to"] == to_ts(ISSUER_CHANGE))
        add_audit(ISSUER_CHANGE, 14, "issuer.retired", "issuer", ids.issuer_id(n),
                  {"rules_transferred": moved, "successor": ids.issuer_id(n + 6)}, platform[0])

    audit_events.sort(key=lambda e: (e["when"], e["rank"], e["entity_id"]))
    chain, prev = [], audit.GENESIS_HASH
    for seq, ev in enumerate(audit_events, start=1):
        event_id = ids.audit_event_id(seq)
        occurred = to_ts(ev["when"])
        details_json = audit.dumps_details(ev["details"])
        digest = audit.compute_event_hash(prev, seq, event_id, occurred, ev["actor_type"], ev["actor_user"], ev["action"],
                                          ev["entity_type"], ev["entity_id"], details_json)
        chain.append({"event_id": event_id, "seq": seq, "occurred_at": occurred, "actor_type": ev["actor_type"],
                      "actor_user_id": ev["actor_user"], "action": ev["action"], "entity_type": ev["entity_type"],
                      "entity_id": ev["entity_id"], "details_json": details_json, "prev_hash": prev, "event_hash": digest})
        prev = digest

    t["credential"], t["credential_completion"] = credentials, bridge
    t["revocation"], t["verification_request"], t["audit_event"] = revocations, verifications, chain

    # ---------------------------------------------------------------- ground truth
    truth_rows = []
    def label(issue_type, entity_type, entity_id, related, source, description):
        truth_rows.append({"ground_truth_id": f"GT-{len(truth_rows) + 1:05d}", "issue_type": issue_type,
                           "entity_type": entity_type, "entity_id": entity_id, "related_entity_id": related,
                           "source_file": source, "description": description})
    for cid in sorted(a1_credential_ids):
        label(T.CREDENTIAL_ISSUED_BEFORE_COMPLETION, "credential", cid, None, "credential.csv",
              "issued_at precedes the completion time of at least one qualifying course")
    for offset, (cred, cand) in enumerate(duplicate_rows):
        label(T.DUPLICATE_CREDENTIAL_ID, "credential", cred["credential_id"], cred["learner_id"], "credential.csv",
              f"second row with this credential_id (data row {base_count + offset + 1}) belongs to a different learner")
    for row in a3_marker:
        label(T.REVOKED_CREDENTIAL_VERIFIED_ACTIVE, "verification_request", row["_vid"], row["credential"]["credential_id"],
              "verification_request.csv", "recorded as valid although the credential was revoked before this check")
    for cred in tampered:
        label(T.PAYLOAD_HASH_ALTERED, "credential", cred["credential_id"], None, "credential.csv",
              "stored payload_hash was changed after signing")
    for row in a4_marker:
        label(T.PAYLOAD_HASH_ALTERATION_NOT_DETECTED, "verification_request", row["_vid"], row["credential"]["credential_id"],
              "verification_request.csv", "recorded as valid although the payload hash fails verification")

    counters = {("learner", 0): len(learners), ("course", 0): len(courses), ("rule", 0): len(rules),
                ("issuer", 0): len(issuers), ("assignment", 0): len(assignments), ("user", 0): len(users),
                ("credential", 2026): base_count, ("verification", 2026): len(verifications)}
    meta = {"eligible_pairs": eligible_total, "pending_eligible_not_issued": eligible_total - params.credentials,
            "anomaly_counts": {k: v for k, v in params.anomaly_counts.items()},
            "dataset_reference_time": to_ts(REF), "issuance_go_live": to_ts(GO_LIVE)}
    return Dataset(tables=t, ground_truth=truth_rows, decisions=decisions, counters=counters, meta=meta)
