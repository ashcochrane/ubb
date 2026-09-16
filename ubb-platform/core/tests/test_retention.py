"""The two clocks this platform keeps, and what each one still holds.

#500, spec §13. The arithmetic is here because it is arithmetic: no tenant, no
database, no request. What the one economic query DOES with these two dates is
proved at its own two seams.
"""
from datetime import date

from django.test import SimpleTestCase, override_settings

from core.retention import (
    ECONOMIC_HORIZON_FIELD,
    ECONOMIC_RETENTION_YEARS,
    MEASUREMENT_HORIZON_FIELD,
    MEASUREMENT_RETENTION_DAYS_SETTING,
    NO_MEASUREMENT_CLOCK,
    retention_horizons,
)


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
    """The shorter clock — which has no number, and whose number is #190's.

    ⚠ **NOTHING HERE STARTS A CLOCK.** The column exists, a trigger defends the
    exemption, and no schedule, owner or default writes it. What this module
    does is make the horizon a value the API reports, so that setting it is a
    configuration change rather than a contract change.
    """

    def test_with_no_clock_configured_it_is_the_economic_horizon(self):
        """⚠ THE COMPOSITION OF FOUR FACTS, AND THE ANSWER IS NOT `None`.

        The migration ships the column with no clock behind it, the recording
        path leaves it NULL, the only post-insert write in the tree is a test
        helper, and the trigger's message for the NULL case reads *not released
        by any clock*. Composed: a measurement record lives exactly as long as
        the posting it hangs off, which is the economic horizon. Publishing the
        shorter date as absent would have made the API say *we do not know*
        about the one thing it does know.
        """
        with override_settings(**{MEASUREMENT_RETENTION_DAYS_SETTING:
                                  NO_MEASUREMENT_CLOCK}):
            horizons = retention_horizons(date(2026, 9, 16))

        assert horizons.measurement == horizons.economic == date(2020, 9, 16)

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

    def test_a_settings_module_that_never_declared_it_still_answers(self):
        """⚠ REMOVE THE SETTING ENTIRELY AND THE ANSWER IS STILL THE ECONOMIC
        HORIZON.

        The read is a `getattr` with a default rather than an attribute access.
        `config.settings` does declare the knob, so that an operator can find
        it and #190 can set it — but a deployment whose settings module has
        never heard of it gets the safe direction rather than an
        `AttributeError` mid-request.
        """
        from django.conf import settings

        with override_settings():
            delattr(settings._wrapped, MEASUREMENT_RETENTION_DAYS_SETTING)
            horizons = retention_horizons(date(2026, 9, 16))

        assert horizons.measurement == horizons.economic


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
