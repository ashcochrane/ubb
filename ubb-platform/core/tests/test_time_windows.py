"""Unit tests for core.time_windows — half-open UTC day/month window helpers."""
from datetime import date, datetime, timedelta, timezone

from core.time_windows import month_bounds, utc_day_start, utc_next_day_start


class TestUtcDayStart:
    def test_returns_utc_midnight(self):
        assert utc_day_start(date(2026, 6, 1)) == datetime(2026, 6, 1, 0, 0, 0, 0, tzinfo=timezone.utc)

    def test_is_timezone_aware_utc(self):
        dt = utc_day_start(date(2026, 6, 1))
        assert dt.tzinfo == timezone.utc
        assert dt.utcoffset().total_seconds() == 0

    def test_microseconds_are_zero(self):
        dt = utc_day_start(date(2026, 6, 1))
        assert (dt.hour, dt.minute, dt.second, dt.microsecond) == (0, 0, 0, 0)


class TestUtcNextDayStart:
    def test_returns_next_day_midnight(self):
        assert utc_next_day_start(date(2026, 6, 30)) == datetime(2026, 7, 1, tzinfo=timezone.utc)

    def test_month_rollover(self):
        assert utc_next_day_start(date(2026, 5, 31)) == datetime(2026, 6, 1, tzinfo=timezone.utc)

    def test_year_rollover(self):
        assert utc_next_day_start(date(2026, 12, 31)) == datetime(2027, 1, 1, tzinfo=timezone.utc)

    def test_leap_day(self):
        assert utc_next_day_start(date(2028, 2, 28)) == datetime(2028, 2, 29, tzinfo=timezone.utc)
        assert utc_next_day_start(date(2028, 2, 29)) == datetime(2028, 3, 1, tzinfo=timezone.utc)

    def test_inclusive_lte_equivalence_boundary(self):
        """col__date <= d  ==  col < utc_next_day_start(d): the last representable
        microsecond of d is inside the window; the first microsecond of d+1 is not."""
        d = date(2026, 6, 30)
        end = utc_next_day_start(d)
        last_micro_of_d = datetime(2026, 6, 30, 23, 59, 59, 999999, tzinfo=timezone.utc)
        first_micro_of_next = datetime(2026, 7, 1, 0, 0, 0, 0, tzinfo=timezone.utc)
        assert last_micro_of_d < end
        assert not (first_micro_of_next < end)


class TestMonthBounds:
    def test_mid_month(self):
        as_of = datetime(2026, 6, 15, 12, 30, tzinfo=timezone.utc)
        assert month_bounds(as_of) == (date(2026, 6, 1), date(2026, 7, 1))

    def test_december_rolls_into_next_year(self):
        as_of = datetime(2026, 12, 31, 23, 59, tzinfo=timezone.utc)
        assert month_bounds(as_of) == (date(2026, 12, 1), date(2027, 1, 1))

    def test_non_utc_offset_normalized_to_utc_month(self):
        """2026-06-01 05:00 at UTC+9 is 2026-05-31 20:00 UTC —
        month_bounds must return the UTC May bounds, not June."""
        tz_plus_9 = timezone(timedelta(hours=9))
        as_of = datetime(2026, 6, 1, 5, 0, tzinfo=tz_plus_9)
        assert month_bounds(as_of) == (date(2026, 5, 1), date(2026, 6, 1))
