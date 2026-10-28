"""The two clocks this platform keeps, and what each one still holds.

#500, spec §13. The arithmetic is here because it is arithmetic: no tenant, no
database, no request. What the one economic query DOES with these two dates is
proved at its own two seams.
"""
import os
import runpy
from datetime import date
from pathlib import Path
from unittest import mock

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, override_settings

from core.retention import (
    ECONOMIC_HORIZON_FIELD,
    ECONOMIC_RETENTION_YEARS,
    MEASUREMENT_HORIZON_FIELD,
    MEASUREMENT_RETENTION_DAYS_SETTING,
    retention_horizons,
)

SETTINGS_FILE = Path(__file__).resolve().parents[2] / "config" / "settings.py"


class TestTheEconomicHorizon(SimpleTestCase):
    """Six years, the horizon the receipt floor already promised (#148 §10.1)."""

    def test_it_is_six_calendar_years_back_from_the_day_asked_about(self):
        horizons = retention_horizons(date(2026, 9, 16))

        assert horizons.economic == date(2020, 9, 16)
        assert ECONOMIC_RETENTION_YEARS == 6

    def test_a_leap_day_falls_forward_rather_than_back(self):
        """⚠ THE ONE DAY THE SUBTRACTION HAS NO ANSWER, AND THE DIRECTION IS A
        RULING RATHER THAN AN ACCIDENT.

        Six years before 2028-02-29 is a date no calendar has. A horizon is a
        PROMISE about what is still held, so the day to land on is the one that
        claims LESS history rather than more: 2022-03-01, not 2022-02-28.
        """
        horizons = retention_horizons(date(2028, 2, 29))

        assert horizons.economic == date(2022, 3, 1)

    def test_the_one_knob_in_this_module_does_not_move_it(self):
        """The asymmetry, asserted rather than only argued: the shorter clock's
        setting moves the shorter clock and nothing else.

        ⚠ **THE WIDER CLAIM IS NOT WHAT THIS PROVES**, and the name says so.
        *No tenant may move it, because no tenant is asked* is a property of the
        function's arguments — `core.scheduling`'s forward horizon has the same
        one and for the same reason — and what a test can show is that the one
        knob that exists does not reach it. A tenant row cannot be smuggled in
        here without a signature change, which a reader of the signature sees.
        """
        with override_settings(**{MEASUREMENT_RETENTION_DAYS_SETTING: 30}):
            configured = retention_horizons(date(2026, 9, 16))

        # Against the LITERAL rather than against the unconfigured answer: two
        # equal wrong dates would satisfy a self-comparison.
        assert configured.economic == date(2020, 9, 16)
        assert configured.measurement == date(2026, 8, 17), (
            "the guard on the line above — the ONE knob in this module did "
            "move the horizon it is for, so the other staying put is a fact "
            "about independence rather than about a setting nothing reads")


class TestTheMeasurementHorizon(SimpleTestCase):
    """The shorter clock: 400 days by default (#190 comment 5785029955, W5
    ruling 7), a setting the environment may override, and enforced by the
    daily prune (`apps/metering/usage/pruning.py`).
    """

    def test_a_cleared_setting_is_refused_rather_than_answered_six_years(self):
        """⚠ NEVER A SILENT SIX YEARS (ruling 7). Until W5 a missing number
        answered the economic horizon, which was true while nothing pruned a
        measurement. The daily prune now enforces this clock, so publishing six
        years of detail it does not keep would be a false promise."""
        with override_settings(**{MEASUREMENT_RETENTION_DAYS_SETTING: None}):
            with self.assertRaises(ImproperlyConfigured):
                retention_horizons(date(2026, 9, 16))

    def test_a_configured_number_of_days_moves_it_forward(self):
        with override_settings(**{MEASUREMENT_RETENTION_DAYS_SETTING: 90}):
            horizons = retention_horizons(date(2026, 9, 16))

        assert horizons.measurement == date(2026, 6, 18)
        assert horizons.economic == date(2020, 9, 16)

    def test_it_can_never_claim_more_history_than_the_economic_clock_holds(self):
        """A number longer than six years is clamped, and that is not defensive
        decoration.

        A measurement record is a child of its posting and cascades with it, so
        a measurement clock set to a century would publish an availability date
        for rows the economic clock has already released. The clamp makes the
        shorter horizon shorter-or-equal by construction rather than by whoever
        types the number.
        """
        with override_settings(**{MEASUREMENT_RETENTION_DAYS_SETTING: 40_000}):
            horizons = retention_horizons(date(2026, 9, 16))

        assert horizons.measurement == horizons.economic

    def test_a_number_below_zero_has_no_reading_and_rounds_toward_less(self):
        """⚠ IT MUST NOT PUBLISH A HORIZON IN THE FUTURE.

        `0` already means *release everything older than today*, so a negative
        number could only ever name a day no series can start from. It rounds
        to zero rather than raising, because rounding toward LESS history is
        the direction this module rounds in everywhere — a platform that
        promises less than it kept is recoverable and one that promises more is
        not — and because a settings typo should not take the surface down.
        """
        with override_settings(**{MEASUREMENT_RETENTION_DAYS_SETTING: -5}):
            horizons = retention_horizons(date(2026, 9, 16))

        assert horizons.measurement == date(2026, 9, 16)
        with override_settings(**{MEASUREMENT_RETENTION_DAYS_SETTING: 0}):
            assert retention_horizons(date(2026, 9, 16)).measurement == (
                horizons.measurement)

    def test_a_settings_module_that_never_declared_it_is_refused(self):
        """Inverted by W5 at its own address: it held that a settings module
        that had never heard of the knob still answered the economic horizon.
        That answer is now the false promise ruling 7 forbids, so the read says
        what is wrong instead of publishing it."""
        from django.conf import settings

        with override_settings():
            delattr(settings._wrapped, MEASUREMENT_RETENTION_DAYS_SETTING)
            with self.assertRaises(ImproperlyConfigured):
                retention_horizons(date(2026, 9, 16))


class TestTheShippedSetting(SimpleTestCase):
    """What `config/settings.py` makes of the environment (ruling 7): 400 when
    the variable is absent, the environment's number when it is set, and a
    refusal to start — never six years — when it is not a number."""

    def _evaluated(self, **environment):
        with mock.patch.dict(os.environ, environment):
            if MEASUREMENT_RETENTION_DAYS_SETTING not in environment:
                os.environ.pop(MEASUREMENT_RETENTION_DAYS_SETTING, None)
            return runpy.run_path(str(SETTINGS_FILE))[
                MEASUREMENT_RETENTION_DAYS_SETTING]

    def test_absent_from_the_environment_it_is_400_days(self):
        assert self._evaluated() == 400

    def test_the_environment_overrides_it(self):
        assert self._evaluated(**{MEASUREMENT_RETENTION_DAYS_SETTING: "90"}) == 90

    def test_an_empty_value_stops_the_process_rather_than_defaulting(self):
        with self.assertRaises(ValueError):
            self._evaluated(**{MEASUREMENT_RETENTION_DAYS_SETTING: ""})


class TestTheNamesOnTheWire(SimpleTestCase):
    """The two field names are #153 §12.3's own, and ADR-0007 §3 makes them
    final the moment they reach `openapi/v1.json`.

    They are named HERE rather than at the schema so that the query filling
    them and the document publishing them cannot drift apart by a typo; the
    schema's own attribute names are held to these by
    `api/v1/tests/test_the_one_economic_query.py`.
    """

    def test_they_are_the_names_the_sketch_gives(self):
        assert ECONOMIC_HORIZON_FIELD == "economic_data_available_from"
        assert MEASUREMENT_HORIZON_FIELD == "measurement_data_available_from"
