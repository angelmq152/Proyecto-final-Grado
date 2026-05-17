from datetime import UTC, datetime


def ensure_aware_utc(dt: datetime) -> datetime:
    """Normalize any datetime to UTC-aware.

    Naive datetimes are treated as UTC (SQLite stores all timestamps without
    timezone info; our convention is that they are always UTC).
    """
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def utc_now() -> datetime:
    """Return the current moment as a UTC-aware datetime."""
    return datetime.now(UTC)
