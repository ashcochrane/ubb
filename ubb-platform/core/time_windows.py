"""Half-open UTC day windows for sargable datetime filtering.

With TIME_ZONE="UTC", USE_TZ=True and no timezone.activate() anywhere,
``col__date >= d`` is row-for-row equivalent to ``col >= utc_day_start(d)``
and ``col__date <= d`` to ``col < utc_next_day_start(d)`` — but the range
form lets Postgres serve the time component from the existing btrees
instead of casting every row.
"""
from datetime import date, datetime, time, timedelta, timezone


def utc_day_start(d: date) -> datetime:
    return datetime.combine(d, time.min, tzinfo=timezone.utc)


def utc_next_day_start(d: date) -> datetime:
    return utc_day_start(d + timedelta(days=1))
