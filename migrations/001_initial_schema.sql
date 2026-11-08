CREATE TABLE learner (
    learner_id      TEXT PRIMARY KEY CHECK (learner_id GLOB 'LRN-[0-9][0-9][0-9][0-9][0-9][0-9]'),
    full_name       TEXT NOT NULL CHECK (length(trim(full_name)) BETWEEN 2 AND 120),
    email           TEXT NOT NULL UNIQUE CHECK (email LIKE '%_@_%._%' AND email = lower(email)),
    date_of_birth   TEXT NOT NULL CHECK (date_of_birth GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'),
    country_code    TEXT NOT NULL CHECK (length(country_code) = 2),
    registered_at   TEXT NOT NULL,
    status          TEXT NOT NULL CHECK (status IN ('active', 'suspended', 'closed'))
);
CREATE INDEX idx_learner_name ON learner (full_name COLLATE NOCASE);

CREATE TABLE instructor (
    instructor_id   TEXT PRIMARY KEY CHECK (instructor_id GLOB 'INS-[0-9][0-9][0-9][0-9]'),
    full_name       TEXT NOT NULL,
    email           TEXT NOT NULL UNIQUE,
    department      TEXT NOT NULL
);

CREATE TABLE app_user (
    user_id         TEXT PRIMARY KEY CHECK (user_id GLOB 'USR-[0-9][0-9][0-9][0-9][0-9][0-9]'),
    email           TEXT NOT NULL UNIQUE CHECK (email = lower(email)),
    role            TEXT NOT NULL CHECK (role IN ('learner', 'instructor', 'academic_admin', 'support_staff', 'platform_admin')),
    learner_id      TEXT REFERENCES learner (learner_id),
    instructor_id   TEXT REFERENCES instructor (instructor_id),
    is_active       INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    created_at      TEXT NOT NULL,
    password_hash   TEXT,
    CHECK (role != 'learner' OR learner_id IS NOT NULL),
    CHECK (role != 'instructor' OR instructor_id IS NOT NULL)
);

CREATE TABLE issuer (
    issuer_id           TEXT PRIMARY KEY CHECK (issuer_id GLOB 'ISS-[0-9][0-9][0-9]'),
    name                TEXT NOT NULL UNIQUE,
    status              TEXT NOT NULL CHECK (status IN ('active', 'retired')),
    valid_from          TEXT NOT NULL,
    valid_to            TEXT,
    successor_issuer_id TEXT REFERENCES issuer (issuer_id),
    CHECK (valid_to IS NULL OR valid_to > valid_from),
    CHECK (status = 'retired' OR valid_to IS NULL)
);

CREATE TABLE issuer_key (
    key_id          TEXT PRIMARY KEY CHECK (key_id GLOB 'KEY-ISS-[0-9][0-9][0-9]-[0-9][0-9]'),
    issuer_id       TEXT NOT NULL REFERENCES issuer (issuer_id),
    algorithm       TEXT NOT NULL CHECK (algorithm = 'Ed25519'),
    public_key_b64  TEXT NOT NULL,
    valid_from      TEXT NOT NULL,
    valid_to        TEXT,
    status          TEXT NOT NULL CHECK (status IN ('active', 'rotated')),
    CHECK (valid_to IS NULL OR valid_to > valid_from),
    CHECK (status = 'rotated' OR valid_to IS NULL)
);
CREATE INDEX idx_issuer_key_issuer ON issuer_key (issuer_id);

CREATE TABLE course (
    course_id       TEXT PRIMARY KEY CHECK (course_id GLOB 'CRS-[0-9][0-9][0-9][0-9][0-9][0-9]'),
    title           TEXT NOT NULL,
    category        TEXT NOT NULL,
    level           TEXT NOT NULL CHECK (level IN ('introductory', 'intermediate', 'advanced')),
    credit_hours    INTEGER NOT NULL CHECK (credit_hours BETWEEN 1 AND 200),
    pass_mark       INTEGER NOT NULL CHECK (pass_mark BETWEEN 40 AND 100),
    max_attempts    INTEGER NOT NULL CHECK (max_attempts BETWEEN 1 AND 10),
    instructor_id   TEXT NOT NULL REFERENCES instructor (instructor_id),
    status          TEXT NOT NULL CHECK (status IN ('active', 'archived')),
    created_at      TEXT NOT NULL
);
CREATE INDEX idx_course_instructor ON course (instructor_id);
CREATE INDEX idx_course_title ON course (title COLLATE NOCASE);

CREATE TABLE credential_rule (
    rule_id                 TEXT PRIMARY KEY CHECK (rule_id GLOB 'RUL-[0-9][0-9][0-9][0-9][0-9][0-9]'),
    title                   TEXT NOT NULL UNIQUE,
    credential_type         TEXT NOT NULL CHECK (credential_type IN ('certificate', 'micro_credential', 'professional_certificate')),
    version                 INTEGER NOT NULL DEFAULT 1 CHECK (version >= 1),
    min_courses_required    INTEGER NOT NULL CHECK (min_courses_required >= 1),
    min_avg_score           REAL NOT NULL CHECK (min_avg_score BETWEEN 0 AND 100),
    min_course_score        REAL NOT NULL CHECK (min_course_score BETWEEN 0 AND 100),
    validity_months         INTEGER CHECK (validity_months IS NULL OR validity_months BETWEEN 1 AND 120),
    effective_from          TEXT NOT NULL,
    effective_to            TEXT,
    status                  TEXT NOT NULL CHECK (status IN ('draft', 'active', 'retired')),
    created_at              TEXT NOT NULL,
    CHECK (effective_to IS NULL OR effective_to > effective_from)
);

CREATE TABLE credential_rule_course (
    rule_id         TEXT NOT NULL REFERENCES credential_rule (rule_id),
    course_id       TEXT NOT NULL REFERENCES course (course_id),
    is_mandatory    INTEGER NOT NULL CHECK (is_mandatory IN (0, 1)),
    PRIMARY KEY (rule_id, course_id)
) WITHOUT ROWID;
CREATE INDEX idx_rule_course_course ON credential_rule_course (course_id);

CREATE TABLE rule_issuer_assignment (
    assignment_id   TEXT PRIMARY KEY CHECK (assignment_id GLOB 'RIA-[0-9][0-9][0-9][0-9][0-9][0-9]'),
    rule_id         TEXT NOT NULL REFERENCES credential_rule (rule_id),
    issuer_id       TEXT NOT NULL REFERENCES issuer (issuer_id),
    effective_from  TEXT NOT NULL,
    effective_to    TEXT,
    CHECK (effective_to IS NULL OR effective_to > effective_from)
);
CREATE INDEX idx_assignment_rule ON rule_issuer_assignment (rule_id, effective_from);
CREATE INDEX idx_assignment_issuer ON rule_issuer_assignment (issuer_id);

CREATE TABLE completion_record (
    completion_id   TEXT PRIMARY KEY CHECK (completion_id GLOB 'CMP-LRN-[0-9][0-9][0-9][0-9][0-9][0-9]-CRS-[0-9][0-9][0-9][0-9][0-9][0-9]'),
    learner_id      TEXT NOT NULL REFERENCES learner (learner_id),
    course_id       TEXT NOT NULL REFERENCES course (course_id),
    enrolled_at     TEXT NOT NULL,
    progress_pct    INTEGER NOT NULL CHECK (progress_pct BETWEEN 0 AND 100),
    status          TEXT NOT NULL CHECK (status IN ('enrolled', 'in_progress', 'completed', 'failed', 'withdrawn')),
    attempts_used   INTEGER NOT NULL CHECK (attempts_used >= 0),
    final_score     REAL CHECK (final_score IS NULL OR final_score BETWEEN 0 AND 100),
    finalized_at    TEXT,
    UNIQUE (learner_id, course_id),
    CHECK (completion_id = 'CMP-' || learner_id || '-' || course_id),
    CHECK ((status IN ('completed', 'failed', 'withdrawn')) = (finalized_at IS NOT NULL)),
    CHECK (status != 'completed' OR (progress_pct = 100 AND final_score IS NOT NULL)),
    CHECK (finalized_at IS NULL OR finalized_at >= enrolled_at)
);
CREATE INDEX idx_completion_course ON completion_record (course_id, status);
CREATE INDEX idx_completion_learner ON completion_record (learner_id);

CREATE TABLE assessment_attempt (
    attempt_id      TEXT PRIMARY KEY CHECK (attempt_id GLOB 'ASM-LRN-[0-9][0-9][0-9][0-9][0-9][0-9]-CRS-[0-9][0-9][0-9][0-9][0-9][0-9]-[0-9][0-9]'),
    completion_id   TEXT NOT NULL REFERENCES completion_record (completion_id),
    attempt_no      INTEGER NOT NULL CHECK (attempt_no >= 1),
    score           REAL NOT NULL CHECK (score BETWEEN 0 AND 100),
    passed          INTEGER NOT NULL CHECK (passed IN (0, 1)),
    attempted_at    TEXT NOT NULL,
    UNIQUE (completion_id, attempt_no)
);

CREATE TABLE credential (
    credential_id   TEXT PRIMARY KEY CHECK (credential_id GLOB 'CRD-[0-9][0-9][0-9][0-9]-[0-9][0-9][0-9][0-9][0-9][0-9]'),
    learner_id      TEXT NOT NULL REFERENCES learner (learner_id),
    rule_id         TEXT NOT NULL REFERENCES credential_rule (rule_id),
    issuer_id       TEXT NOT NULL REFERENCES issuer (issuer_id),
    key_id          TEXT NOT NULL REFERENCES issuer_key (key_id),
    issued_at       TEXT NOT NULL,
    expires_at      TEXT,
    status          TEXT NOT NULL CHECK (status IN ('active', 'revoked')),
    payload_json    TEXT NOT NULL,
    payload_hash    TEXT NOT NULL CHECK (length(payload_hash) = 64),
    signature_b64   TEXT NOT NULL,
    issued_by       TEXT REFERENCES app_user (user_id),
    CHECK (expires_at IS NULL OR expires_at > issued_at)
);
CREATE INDEX idx_credential_learner ON credential (learner_id);
CREATE INDEX idx_credential_rule ON credential (rule_id);
CREATE INDEX idx_credential_issuer ON credential (issuer_id);
CREATE INDEX idx_credential_issued_at ON credential (issued_at);
CREATE UNIQUE INDEX uq_credential_one_active_per_rule ON credential (learner_id, rule_id) WHERE status = 'active';

CREATE TABLE credential_completion (
    credential_id   TEXT NOT NULL REFERENCES credential (credential_id),
    completion_id   TEXT NOT NULL REFERENCES completion_record (completion_id),
    PRIMARY KEY (credential_id, completion_id)
) WITHOUT ROWID;
CREATE INDEX idx_cred_completion_completion ON credential_completion (completion_id);

CREATE TABLE revocation (
    revocation_id   TEXT PRIMARY KEY CHECK (revocation_id GLOB 'REV-CRD-[0-9][0-9][0-9][0-9]-[0-9][0-9][0-9][0-9][0-9][0-9]-[0-9][0-9]'),
    credential_id   TEXT NOT NULL REFERENCES credential (credential_id),
    seq             INTEGER NOT NULL CHECK (seq >= 1),
    reason_code     TEXT NOT NULL CHECK (reason_code IN ('fraud', 'academic_misconduct', 'issued_in_error', 'learner_request', 'rule_change')),
    reason_detail   TEXT,
    effective_at    TEXT NOT NULL,
    revoked_by      TEXT REFERENCES app_user (user_id),
    UNIQUE (credential_id, seq),
    CHECK (revocation_id = 'REV-' || credential_id || '-' || printf('%02d', seq))
);
CREATE INDEX idx_revocation_effective ON revocation (effective_at);

CREATE TABLE verification_request (
    verification_id         TEXT PRIMARY KEY CHECK (verification_id GLOB 'VER-[0-9][0-9][0-9][0-9]-[0-9][0-9][0-9][0-9][0-9][0-9]'),
    presented_credential_id TEXT NOT NULL,
    credential_id           TEXT REFERENCES credential (credential_id),
    requested_at            TEXT NOT NULL,
    channel                 TEXT NOT NULL CHECK (channel IN ('public_api', 'support_desk', 'learner_share')),
    requester_type          TEXT NOT NULL CHECK (requester_type IN ('employer', 'institution', 'learner', 'support', 'other')),
    requester_org           TEXT,
    presented_hash          TEXT,
    claimed_name            TEXT,
    claimed_email           TEXT,
    claimed_dob             TEXT,
    result_status           TEXT NOT NULL CHECK (result_status IN ('valid', 'revoked', 'expired', 'not_found', 'tampered')),
    identity_status         TEXT NOT NULL CHECK (identity_status IN ('matched', 'mismatch', 'insufficient_identifiers', 'not_requested')),
    integrity_ok            INTEGER CHECK (integrity_ok IN (0, 1)),
    processed_by            TEXT REFERENCES app_user (user_id),
    CHECK (credential_id IS NOT NULL OR result_status = 'not_found')
);
CREATE INDEX idx_verification_credential ON verification_request (credential_id);
CREATE INDEX idx_verification_requested_at ON verification_request (requested_at);
CREATE INDEX idx_verification_result ON verification_request (result_status);

CREATE TABLE audit_event (
    event_id        TEXT PRIMARY KEY CHECK (event_id GLOB 'AUD-[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]'),
    seq             INTEGER NOT NULL UNIQUE CHECK (seq >= 1),
    occurred_at     TEXT NOT NULL,
    actor_type      TEXT NOT NULL CHECK (actor_type IN ('user', 'public', 'system')),
    actor_user_id   TEXT REFERENCES app_user (user_id),
    action          TEXT NOT NULL,
    entity_type     TEXT NOT NULL,
    entity_id       TEXT NOT NULL,
    details_json    TEXT NOT NULL,
    prev_hash       TEXT NOT NULL CHECK (length(prev_hash) = 64),
    event_hash      TEXT NOT NULL UNIQUE CHECK (length(event_hash) = 64),
    CHECK (actor_type = 'user' OR actor_user_id IS NULL)
);
CREATE INDEX idx_audit_entity ON audit_event (entity_type, entity_id);
CREATE INDEX idx_audit_action ON audit_event (action);
CREATE INDEX idx_audit_occurred ON audit_event (occurred_at);

CREATE TABLE id_counter (
    counter_name    TEXT NOT NULL,
    counter_year    INTEGER NOT NULL,
    last_value      INTEGER NOT NULL,
    PRIMARY KEY (counter_name, counter_year)
) WITHOUT ROWID;

CREATE TABLE import_rejection (
    rejection_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    source_file     TEXT NOT NULL,
    row_number      INTEGER NOT NULL,
    record_key      TEXT NOT NULL,
    reason          TEXT NOT NULL,
    raw_json        TEXT NOT NULL
);

CREATE TRIGGER trg_audit_no_update BEFORE UPDATE ON audit_event
BEGIN SELECT RAISE(ABORT, 'audit_event is append-only'); END;
CREATE TRIGGER trg_audit_no_delete BEFORE DELETE ON audit_event
BEGIN SELECT RAISE(ABORT, 'audit_event is append-only'); END;

CREATE TRIGGER trg_revocation_no_update BEFORE UPDATE ON revocation
BEGIN SELECT RAISE(ABORT, 'revocation is append-only'); END;
CREATE TRIGGER trg_revocation_no_delete BEFORE DELETE ON revocation
BEGIN SELECT RAISE(ABORT, 'revocation is append-only'); END;

CREATE TRIGGER trg_verification_no_update BEFORE UPDATE ON verification_request
BEGIN SELECT RAISE(ABORT, 'verification_request is append-only'); END;
CREATE TRIGGER trg_verification_no_delete BEFORE DELETE ON verification_request
BEGIN SELECT RAISE(ABORT, 'verification_request is append-only'); END;

CREATE TRIGGER trg_attempt_no_update BEFORE UPDATE ON assessment_attempt
BEGIN SELECT RAISE(ABORT, 'assessment_attempt is append-only'); END;
CREATE TRIGGER trg_attempt_no_delete BEFORE DELETE ON assessment_attempt
BEGIN SELECT RAISE(ABORT, 'assessment_attempt is append-only'); END;

CREATE TRIGGER trg_credential_no_delete BEFORE DELETE ON credential
BEGIN SELECT RAISE(ABORT, 'credential cannot be deleted'); END;
CREATE TRIGGER trg_credential_immutable BEFORE UPDATE ON credential
WHEN NEW.credential_id IS NOT OLD.credential_id OR NEW.learner_id IS NOT OLD.learner_id
  OR NEW.rule_id IS NOT OLD.rule_id OR NEW.issuer_id IS NOT OLD.issuer_id
  OR NEW.key_id IS NOT OLD.key_id OR NEW.issued_at IS NOT OLD.issued_at
  OR NEW.expires_at IS NOT OLD.expires_at OR NEW.payload_json IS NOT OLD.payload_json
  OR NEW.payload_hash IS NOT OLD.payload_hash OR NEW.signature_b64 IS NOT OLD.signature_b64
  OR NEW.issued_by IS NOT OLD.issued_by
BEGIN SELECT RAISE(ABORT, 'credential issuance fields are immutable'); END;
CREATE TRIGGER trg_credential_status_transition BEFORE UPDATE OF status ON credential
WHEN NEW.status != OLD.status AND NOT (OLD.status = 'active' AND NEW.status = 'revoked'
     AND EXISTS (SELECT 1 FROM revocation r WHERE r.credential_id = NEW.credential_id))
BEGIN SELECT RAISE(ABORT, 'invalid credential status transition'); END;

CREATE TRIGGER trg_completion_terminal_immutable BEFORE UPDATE ON completion_record
WHEN OLD.status IN ('completed', 'failed', 'withdrawn')
BEGIN SELECT RAISE(ABORT, 'finalized completion_record is immutable'); END;
CREATE TRIGGER trg_completion_no_delete BEFORE DELETE ON completion_record
BEGIN SELECT RAISE(ABORT, 'completion_record cannot be deleted'); END;
