"""Half-open UTC day windows for sargable datetime filtering.

With TIME_ZONE="UTC", USE_TZ=True and no timezone.activate() anywhere,
``col__date >= d`` is row-for-row equivalent to ``col >= utc_day_start(d)``
and ``col__date <= d`` to ``col < utc_next_day_start(d)`` — but the range
form lets Postgres serve the time component from the existing btrees
instead of casting every row.
"""
from datetime import date, datetime, time, timedelta, timezone


# #78: computed reports are cursor-exempt but parameter-bounded — the one
# ceiling an explicit report window may span (366 = one leap year; an hourly
# report keeps its own tighter one below).
REPORT_WINDOW_MAX_DAYS = 366

# THE TIGHTER CEILING AN HOURLY REPORT SPANS, because the bound is really about
# how many BUCKETS a report may produce and an hour is twenty-four times a day:
# 366 days by hour is nearly nine thousand rows in one response.
#
# NAMED HERE RATHER THAN SPELLED AT EACH ROUTE (#499). It was a literal in two
# places in one route, and the one economic query is a third asker — a rule
# spelled three times is three answers to *how far back may an hourly question
# reach*, and the first one to move would move alone.
HOURLY_REPORT_WINDOW_MAX_DAYS = 92


def utc_day_start(d: date) -> datetime:
    return datetime.combine(d, time.min, tzinfo=timezone.utc)


def utc_next_day_start(d: date) -> datetime:
    return utc_day_start(d + timedelta(days=1))


def month_bounds(as_of):
    """Calendar-month UTC bounds (DateField pair, half-open) containing as_of.

    Always normalizes to UTC before extracting the date, so callers passing a
    timezone-aware datetime with a non-UTC offset get the correct UTC month.

    ``as_of`` may be a `date` as well as a `datetime`. A date has already been
    reduced to a calendar day by whoever wrote it down — a supplied revenue
    record's period opens on one (#502) — so there is no instant left to
    normalize and asking for its month is the same question.
    """
    # Normalize aware datetimes to UTC; naive datetimes are treated as UTC.
    if hasattr(as_of, "tzinfo") and as_of.tzinfo is not None:
        as_of = as_of.astimezone(timezone.utc)
    day = as_of.date() if hasattr(as_of, "date") else as_of
    start = day.replace(day=1)
    if day.month == 12:
        end = day.replace(year=day.year + 1, month=1, day=1)
    else:
        end = day.replace(month=day.month + 1, day=1)
    return start, end


def closed_months(opens, closes=None, *, now):
    """Every calendar month a fact reaches into that has already CLOSED at
    *now*, oldest first (#502, slice 7 §8).

    The one statement of *which months a fact reaches back into*, because three
    callers were each asking it and it is subtle in two directions at once.

    ⚠ **A FACT MAY SPAN MONTHS, AND MARKING ONLY THE ONE IT OPENS IN IS THE
    DEFECT RATHER THAN AN EDGE OF IT.** A tenant supplying revenue for a quarter
    states ONE record covering three months, and under the recognised basis a
    spreading method puts part of the amount in each — so naming only the
    opening month leaves the other two stale at any age, which is exactly what
    the marker channel exists to prevent. ``closes`` is EXCLUSIVE, so a span
    ending on the first of a month does not reach into that month; omit it for a
    fact that is an instant rather than a span.

    ⚠ **THE OPEN MONTH IS NEVER RETURNED, AND THAT IS THE RULE AND NOT A
    ROUNDING.** The caches these answers invalidate are swept hourly and rebuilt
    daily while the month is open, and their consumer skips a marker for a
    non-prior month WITHOUT acking it — so naming the open month would write a
    row nothing consumes until the month rolls past it.
    """
    this_month = month_bounds(now)[0]
    month = month_bounds(opens)[0]
    # The last month the span touches. `closes` is exclusive, so the last day
    # covered is the one before it — which is the difference between a quarter
    # ending 1 July reaching June and reaching July.
    last = (month_bounds(closes - timedelta(days=1))[0]
            if closes is not None else month)
    months = []
    while month <= last and month < this_month:
        months.append(month)
        month = month_bounds(month)[1]
    return months
