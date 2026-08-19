"""The forward horizon is a platform constant, and 366 is not an accident
(#359, ruling 14a).

The bound exists to stop **a typo becoming a permanent invisible schedule** —
the only failure mode anybody has described. Everything below is either the
calendar arithmetic that makes 366 the right number, or the structural claim
that no tenant can move it.

**WHY THE CLOCK IS A PARAMETER AND NOT A READ.** `validate_scheduled_instant`
takes `now`, which is what lets the leap-year case be stated as a date rather
than as a duration relative to whenever the suite happens to run. A function
that read its own clock could only be tested by patching one, and the case that
matters — *"the same day next year"* across a leap year — is a statement about
two calendar dates.
"""

import inspect
from datetime import datetime, timedelta, timezone as tz

from django.test import TestCase

from core.problems import Problem
from core.scheduling import (
    CLOCK_SKEW, MAX_FORWARD_SCHEDULING_DAYS, validate_scheduled_instant)

#: A June-to-June year that CONTAINS 29 February 2028, so "the same day next
#: year" is 366 days rather than 365. This is the case the extra day exists for.
A_LEAP_SPANNING_NOW = datetime(2027, 6, 1, tzinfo=tz.utc)
THE_SAME_DAY_NEXT_YEAR = datetime(2028, 6, 1, tzinfo=tz.utc)

#: The ordinary year beside it, for contrast: same two calendar positions, one
#: day shorter, and both are accepted.
AN_ORDINARY_NOW = datetime(2026, 6, 1, tzinfo=tz.utc)
AN_ORDINARY_YEAR_LATER = datetime(2027, 6, 1, tzinfo=tz.utc)

NOW = datetime(2026, 8, 19, 12, 0, tzinfo=tz.utc)


def _refusal(testcase, effective_at, now=NOW):
    with testcase.assertRaises(Problem) as raised:
        validate_scheduled_instant(effective_at, now)
    return raised.exception


class TheHorizonIsBoundedAt366DaysTest(TestCase):

    def test_exactly_366_days_ahead_is_accepted(self):
        self.assertIsNone(validate_scheduled_instant(
            NOW + timedelta(days=MAX_FORWARD_SCHEDULING_DAYS), NOW))

    def test_367_days_ahead_is_refused(self):
        problem = _refusal(self, NOW + timedelta(days=367))

        self.assertEqual(problem.code, "effective_at_too_far_ahead")
        self.assertEqual(problem.status, 422)

    def test_a_microsecond_past_the_horizon_is_refused(self):
        """The bound is a boundary, not a rounding.

        366 days exactly is inside; anything beyond is not. Stating both edges
        is what stops a later `>=` reading as equivalent.
        """
        problem = _refusal(
            self,
            NOW + timedelta(days=MAX_FORWARD_SCHEDULING_DAYS,
                            microseconds=1))

        self.assertEqual(problem.code, "effective_at_too_far_ahead")

    def test_the_same_day_next_year_across_a_leap_year_is_accepted(self):
        """366 rather than 365, and this is the whole reason.

        A contract dated *"the same day next year"* signed in a year whose next
        twelve months contain a leap day is 366 days out. At 365 it would be
        refused for being one day too far, which is a refusal nobody could
        explain to the tenant who signed it.
        """
        self.assertEqual(
            (THE_SAME_DAY_NEXT_YEAR - A_LEAP_SPANNING_NOW).days, 366)

        self.assertIsNone(validate_scheduled_instant(
            THE_SAME_DAY_NEXT_YEAR, A_LEAP_SPANNING_NOW))

    def test_the_same_day_next_year_in_an_ordinary_year_is_accepted_too(self):
        self.assertEqual(
            (AN_ORDINARY_YEAR_LATER - AN_ORDINARY_NOW).days, 365)

        self.assertIsNone(validate_scheduled_instant(
            AN_ORDINARY_YEAR_LATER, AN_ORDINARY_NOW))


class TheBoundIsAPlatformConstantTest(TestCase):
    """It is not a tenant setting, and the structure is what says so.

    A configurable bound invites a tenant to set it to a century, which defeats
    it. Map #137's *"tenant defines everything"* is about **catalogue** — what a
    tenant meters and charges — not about safety rails on a scheduling surface.
    """

    def test_the_bound_is_a_module_constant(self):
        self.assertIsInstance(MAX_FORWARD_SCHEDULING_DAYS, int)
        self.assertEqual(MAX_FORWARD_SCHEDULING_DAYS, 366)

    def test_the_rule_is_never_given_a_tenant_to_consult(self):
        """The strongest form of *"no tenant setting can change it"*: the
        function cannot look one up, because it is never told which tenant it
        is deciding for.
        """
        parameters = list(
            inspect.signature(validate_scheduled_instant).parameters)

        self.assertEqual(parameters, ["effective_at", "now"])

    def test_validating_an_instant_reads_no_row(self):
        """Nor could it reach a tenant by any other route.

        A bound that could be overridden per tenant would have to read
        something; this reads nothing, on the accepting path and on the
        refusing one alike.
        """
        with self.assertNumQueries(0):
            validate_scheduled_instant(NOW + timedelta(days=1), NOW)
        with self.assertNumQueries(0):
            _refusal(self, NOW + timedelta(days=400))

    def test_the_horizon_is_not_the_report_window_ceiling(self):
        """Two 366s, deliberately not one symbol.

        `REPORT_WINDOW_MAX_DAYS` bounds how wide a window a caller may ask the
        database to scan; this bounds how far ahead a decision may be dated. If
        they were one constant, a change to either would silently move the
        other.

        ⚠ **ASSERTED ON THE SOURCE, BECAUSE THE OBVIOUS FORMS BOTH FAIL.**
        Comparing the two VALUES couples exactly what this decouples — an
        intentional change to either would turn it red. And a membership test
        over `vars()` is defeated by an aliased import
        (`REPORT_WINDOW_MAX_DAYS as MAX_FORWARD_SCHEDULING_DAYS` binds the new
        name and not the old, leaving the check green over one shared value).
        The claim is that this module DEFINES its bound rather than borrowing
        one, so the honest reading is of the assignment itself. Found by both
        `/code-review` axes, from two different directions.
        """
        import ast
        import inspect

        from core import scheduling

        tree = ast.parse(inspect.getsource(scheduling))
        assigned = [
            node.value for node in tree.body
            if isinstance(node, ast.Assign)
            and any(getattr(target, "id", None) == "MAX_FORWARD_SCHEDULING_DAYS"
                    for target in node.targets)
        ]

        self.assertEqual(len(assigned), 1)
        self.assertIsInstance(assigned[0], ast.Constant)
        self.assertEqual(assigned[0].value, 366)
        borrowed = [node for node in ast.walk(tree)
                    if isinstance(node, ast.ImportFrom)
                    and (node.module or "").endswith("time_windows")]
        self.assertEqual(borrowed, [])


class AnInstantThatIsNotAScheduleIsRefusedTest(TestCase):
    """The two refusals that are not the horizon.

    Neither is ruling 14a's, and each carries a code of its own rather than the
    generic one: a naive datetime is not a moment at all, and an instant in the
    past is a **retroactive reprice** rather than a schedule. On this route
    `validation_error` already means two other things, so a third meaning would
    leave a caller unable to tell a date it can fix from a body it cannot.
    """

    def test_a_naive_instant_is_refused_before_either_bound_is_read(self):
        """Refused for being naive, not as a consequence of a comparison.

        Comparing a naive datetime to an aware one raises rather than
        answering, so the order here is load-bearing: a naive instant far past
        the horizon must still be told it is naive.
        """
        problem = _refusal(
            self, datetime(2027, 1, 1), now=NOW)

        self.assertEqual(problem.code, "effective_at_naive")

        beyond = _refusal(self, datetime(2099, 1, 1), now=NOW)

        self.assertEqual(beyond.code, "effective_at_naive")

    def test_an_instant_in_the_past_is_refused(self):
        problem = _refusal(self, NOW - timedelta(days=1))

        self.assertEqual(problem.code, "effective_at_in_past")
        self.assertIn("past", str(problem.detail))

    def test_an_instant_inside_the_skew_allowance_is_accepted(self):
        """A caller stamping its own clock's "now" is not backdating.

        Refusing a request because the caller's clock is two hundred
        milliseconds behind tells them their clock is wrong, which is not the
        refusal anybody wanted. The allowance is `usage_service`'s, in the
        other direction.
        """
        self.assertIsNone(validate_scheduled_instant(
            NOW - CLOCK_SKEW + timedelta(seconds=1), NOW))

        problem = _refusal(self, NOW - CLOCK_SKEW - timedelta(seconds=1))

        self.assertEqual(problem.code, "effective_at_in_past")
