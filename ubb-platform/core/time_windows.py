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


def month_bounds(as_of):
    """Calendar-month UTC bounds (DateField pair, half-open) containing as_of.

    Always normalizes to UTC before extracting the date, so callers passing a
    timezone-aware datetime with a non-UTC offset get the correct UTC month.
    """
    # Normalize aware datetimes to UTC; naive datetimes are treated as UTC.
    if hasattr(as_of, "tzinfo") and as_of.tzinfo is not None:
        as_of = as_of.astimezone(timezone.utc)
    day = as_of.date()
    start = day.replace(day=1)
    if day.month == 12:
        end = day.replace(year=day.year + 1, month=1, day=1)
    else:
        end = day.replace(month=day.month + 1, day=1)
    return start, end
