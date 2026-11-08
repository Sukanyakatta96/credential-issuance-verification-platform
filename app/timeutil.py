from datetime import datetime, timedelta, timezone

TS_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def to_ts(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime(TS_FORMAT)


def parse_ts(value: str) -> datetime:
    return datetime.strptime(value, TS_FORMAT).replace(tzinfo=timezone.utc)


def add_months(value: datetime, months: int) -> datetime:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = value.day
    while True:
        try:
            return value.replace(year=year, month=month, day=day)
        except ValueError:
            day -= 1


def days(n: float) -> timedelta:
    return timedelta(days=n)


def ensure_strictly_after(now: datetime, earlier_ts: str, what: str = "this change") -> str:
    """Effective-dated records need a positive window; refuse rather than future-date a change."""
    from .errors import conflict
    if now <= parse_ts(earlier_ts):
        raise conflict(f"{what} cannot take effect within the same second as the record it replaces; retry in a moment",
                       "TOO_SOON")
    return to_ts(now)
