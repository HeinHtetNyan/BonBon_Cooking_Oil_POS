"""
Timezone-safe datetime helpers.

Rule: UTC everywhere internally. Convert to local time only at the API
boundary (response serialization) when the client requests it.

All functions return timezone-aware datetimes — never naive.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, timezone


def utcnow() -> datetime:
    """Return current UTC time as a timezone-aware datetime."""
    return datetime.now(UTC)


def to_utc(dt: datetime) -> datetime:
    """
    Ensure a datetime is UTC.

    - Naive datetimes are assumed to be UTC and made aware.
    - Aware datetimes are converted to UTC.
    """
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def start_of_day(dt: datetime) -> datetime:
    """Return UTC midnight for the given datetime's calendar day."""
    return dt.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=UTC)


def end_of_day(dt: datetime) -> datetime:
    """Return last microsecond of the given datetime's calendar day (UTC)."""
    return dt.replace(hour=23, minute=59, second=59, microsecond=999999, tzinfo=UTC)


def date_range(start: date, end: date) -> list[date]:
    """Generate inclusive list of dates from start to end."""
    result = []
    current = start
    while current <= end:
        result.append(current)
        current += timedelta(days=1)
    return result


def aware_datetime(year: int, month: int, day: int, **kwargs: int) -> datetime:
    """Convenience constructor for UTC-aware datetimes in tests."""
    return datetime(year, month, day, tzinfo=UTC, **kwargs)
