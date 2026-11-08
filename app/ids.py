import re

LEARNER_RE = re.compile(r"^LRN-\d{6}$")
COURSE_RE = re.compile(r"^CRS-\d{6}$")
CREDENTIAL_RE = re.compile(r"^CRD-\d{4}-\d{6}$")
VERIFICATION_RE = re.compile(r"^VER-\d{4}-\d{6}$")
COMPLETION_RE = re.compile(r"^CMP-LRN-\d{6}-CRS-\d{6}$")


def learner_id(n: int) -> str:
    return f"LRN-{n:06d}"


def course_id(n: int) -> str:
    return f"CRS-{n:06d}"


def instructor_id(n: int) -> str:
    return f"INS-{n:04d}"


def user_id(n: int) -> str:
    return f"USR-{n:06d}"


def rule_id(n: int) -> str:
    return f"RUL-{n:06d}"


def issuer_id(n: int) -> str:
    return f"ISS-{n:03d}"


def key_id(issuer: str, version: int) -> str:
    return f"KEY-{issuer}-{version:02d}"


def assignment_id(n: int) -> str:
    return f"RIA-{n:06d}"


def completion_id(learner: str, course: str) -> str:
    return f"CMP-{learner}-{course}"


def attempt_id(completion: str, attempt_no: int) -> str:
    return f"ASM-{completion[4:]}-{attempt_no:02d}"


def credential_id(year: int, n: int) -> str:
    return f"CRD-{year}-{n:06d}"


def verification_id(year: int, n: int) -> str:
    return f"VER-{year}-{n:06d}"


def revocation_id(credential: str, seq: int) -> str:
    return f"REV-{credential}-{seq:02d}"


def audit_event_id(seq: int) -> str:
    return f"AUD-{seq:09d}"


def next_counter(db, name: str, year: int = 0) -> int:
    db.execute(
        "INSERT INTO id_counter (counter_name, counter_year, last_value) VALUES (?, ?, 1) "
        "ON CONFLICT (counter_name, counter_year) DO UPDATE SET last_value = last_value + 1",
        (name, year),
    )
    return db.execute(
        "SELECT last_value FROM id_counter WHERE counter_name = ? AND counter_year = ?",
        (name, year),
    ).fetchone()[0]


def sync_counter(db, name: str, year: int, value: int) -> None:
    db.execute(
        "INSERT INTO id_counter (counter_name, counter_year, last_value) VALUES (?, ?, ?) "
        "ON CONFLICT (counter_name, counter_year) DO UPDATE SET last_value = MAX(last_value, excluded.last_value)",
        (name, year, value),
    )
