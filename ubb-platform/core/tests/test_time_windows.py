"""Unit tests for core.time_windows — half-open UTC day window helpers."""
from datetime import date, datetime, timezone

from core.time_windows import utc_day_start, utc_next_day_start


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
