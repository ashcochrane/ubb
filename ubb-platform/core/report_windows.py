"""THE CALENDAR-DATE REPORT WINDOW — one meaning for every report route that
takes a pair of dates (#542, #543, #514; W5 rulings 1–6).

Six report routes take a calendar-date window: the one economic query, the
task analytics, the two margin report routes, the referral earnings and the end
customer's own usage summary (`/me/economics`, W5). Before this module the
first five disagreed three ways — about what `end_date` means (inclusive
on two, exclusive on two), about a lone date (honoured, silently dropped, or an
unbounded read) and about the default (month to date, or all of history). Each
one now resolves its window here and nowhere else.

**The rule, as published.**

- Both dates are calendar dates in UTC, and both are INCLUSIVE.
- A lone start runs to today; a lone end starts on the first day of its own
  month; neither is the current UTC month to date. A supplied date is never
  dropped.
- The resolved window may not run backwards, and spans at most
  `REPORT_WINDOW_MAX_DAYS` calendar dates — a full leap year and never one more.
- Longer retained history is read as consecutive, non-overlapping windows, the
  next one starting on the calendar day after the previous one's end date. There
  is no pagination over a report (#514's ruling).

⚠⚠ **THE INCLUSIVE DATES ARE CONVERTED ONCE, HERE, TO ONE HALF-OPEN UTC
INTERVAL, AND NOTHING DOWNSTREAM DOES ITS OWN `+1 DAY`** (amendment A).
`ReportWindow.between` is the only place the day after the end date is
computed (through `core.time_windows.utc_next_day_start`):
`[start_date 00:00 UTC, (end_date + 1 day) 00:00 UTC)`. A query reads
`opens_at`/`closes_at` (or the same interval as two dates, `opens`/`closes`),
which is how the four readings this replaced stop being four.

⚠ **THE BOUND IS A DURATION OF THAT INTERVAL, AND THAT IS WHY 366 MEANS 366
DATES.** An inclusive window of N calendar dates is N whole days of time, so the
calendar-date reports and the datetime-windowed spend-control reports
(`api/v1/spend_control_endpoints.py`, OUT of this module's scope — their
half-open datetime pair is a different abstraction and stays explicit) are held
to the same 366 days. The old `(end - start).days > 366` admitted 367 dates.

⚠ **OUT OF SCOPE, DELIBERATELY** (ruling 5): the pricing filters' `selected_*`
run selectors and the spend-control `since`/`until`. Both are datetime windows,
half-open on purpose, and say so on their own routes.
"""
import inspect
from datetime import date, datetime, timedelta
from typing import NamedTuple

from django.utils import timezone

from core.problems import Problem
from core.time_windows import (
    HOURLY_REPORT_WINDOW_MAX_DAYS, REPORT_WINDOW_MAX_DAYS, utc_day_start,
    utc_next_day_start)


class ReportWindow(NamedTuple):
    """A resolved calendar-date window, in its two spellings.

    ``start_date``/``end_date`` are what the caller asked about and what a
    response echoes: both inclusive. ``opens_at``/``closes_at`` are the same
    window as the one half-open UTC interval every query reads. ``today`` is the
    UTC day the window was resolved against, so a default window and anything
    else that reads the clock for the same answer read it once.
    """

    start_date: date
    end_date: date
    opens_at: datetime
    closes_at: datetime
    today: date

    @classmethod
    def between(cls, start_date, end_date, *, today=None):
        """THE ONE CONVERSION: inclusive public dates → a half-open UTC interval.

        No default and no bound — a read contract asked about an explicit
        stretch (a test, a horizon check) builds its window here, and a route
        resolves one through `resolve_report_window`, which ends here too.
        """
        return cls(start_date=start_date, end_date=end_date,
                   opens_at=utc_day_start(start_date),
                   closes_at=utc_next_day_start(end_date),
                   today=today if today is not None else _utc_today())

    @property
    def opens(self) -> date:
        """The interval's first day — the same instant as ``opens_at``."""
        return self.opens_at.date()

    @property
    def closes(self) -> date:
        """The interval's EXCLUSIVE bound as a day — the same instant as
        ``closes_at``, for a half-open read over date columns."""
        return self.closes_at.date()


def _utc_today():
    # `timezone.now()` is UTC (TIME_ZONE="UTC", nothing activates another).
    return timezone.now().date()


def resolve_report_window(start_date, end_date, *, hourly=False,
                          start_name="start_date", end_name="end_date"):
    """The window a report route answers, defaulted first and bounded second.

    ⚠ **THE BOUND IS APPLIED TO THE RESOLVED WINDOW, NEVER TO THE REQUEST**
    (#542). Bounding only a supplied pair is how `?start_date=2000-01-01` alone
    was an unbounded read at the Read floor on one route and a silently
    ignored parameter on two others. Here every shape of request resolves to a
    pair first, so none reaches a query unbounded.

    An hourly report keeps the tighter ceiling, because the bound is really about
    how many BUCKETS an answer may carry and an hour is twenty-four times a day.

    The parameter names are the route's own, so a refusal names what the caller
    sent (the referral earnings route calls its pair `period_start`/`period_end`).
    """
    today = _utc_today()
    if start_date is None and end_date is None:
        start_date, end_date = today.replace(day=1), today
    elif end_date is None:
        end_date = today
    elif start_date is None:
        start_date = end_date.replace(day=1)
    if start_date > end_date:
        raise Problem("validation_error",
                      f"{start_name} must not fall after {end_name}")
    window = ReportWindow.between(start_date, end_date, today=today)
    ceiling = HOURLY_REPORT_WINDOW_MAX_DAYS if hourly else REPORT_WINDOW_MAX_DAYS
    if window.closes_at - window.opens_at > timedelta(days=ceiling):
        kind = "an hourly report window" if hourly else "a report window"
        raise Problem(
            "validation_error",
            f"{kind} spans at most {ceiling} calendar dates, both ends "
            f"inclusive; read a longer stretch as consecutive windows")
    return window


def report_window_description(start_name="start_date", end_name="end_date"):
    """THE ONE DESCRIPTION OF A CALENDAR-DATE REPORT WINDOW (ruling 6), with the
    route's own parameter names in it. Every calendar-date report route
    publishes it, through `states_its_report_window`."""
    return (
        f"**The window.** `{start_name}` and `{end_name}` are calendar dates in "
        f"UTC, and both are inclusive: the window runs from the start of "
        f"`{start_name}` to the end of `{end_name}`. Send `{start_name}` alone "
        f"and the window runs to today; send `{end_name}` alone and it starts on "
        f"the first day of that date's month; send neither and it is the current "
        f"UTC month to date. A supplied date is never ignored. One request spans "
        f"at most {REPORT_WINDOW_MAX_DAYS} calendar dates, and `{start_name}` "
        f"may not fall after `{end_name}`; either is refused with "
        f"`validation_error`. Longer retained history is read through "
        f"consecutive, non-overlapping windows: the next window starts on the "
        f"calendar day after the previous window's `{end_name}`.")


#: What each date of a calendar-date window means, published on the parameter.
START_DATE_DESCRIPTION = "The first calendar date (UTC) in the window, inclusive."
END_DATE_DESCRIPTION = "The last calendar date (UTC) in the window, inclusive."


def states_its_report_window(start_name="start_date", end_name="end_date"):
    """Append the one window description to a report route's own.

    Goes directly beneath the router decorator, which reads the view's
    docstring (`inspect.cleandoc`) when it builds the operation — so the
    fragment is joined to an already-clean docstring and the published
    description is one paragraph list, not an indented code block.
    """
    def decorate(view):
        own = inspect.cleandoc(view.__doc__ or "")
        fragment = report_window_description(start_name, end_name)
        view.__doc__ = f"{own}\n\n{fragment}" if own else fragment
        return view
    return decorate
