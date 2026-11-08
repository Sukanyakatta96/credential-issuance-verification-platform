def build_payload(*, credential_id, learner_id, rule, issuer_id, key_id, issued_at, expires_at, completion_ids):
    return {
        "credential_id": credential_id,
        "learner_id": learner_id,
        "rule_id": rule["rule_id"],
        "rule_title": rule["title"],
        "rule_version": rule["version"],
        "issuer_id": issuer_id,
        "key_id": key_id,
        "issued_at": issued_at,
        "expires_at": expires_at,
        "completion_ids": sorted(completion_ids),
    }
