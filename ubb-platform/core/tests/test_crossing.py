"""#110: ``core.crossing`` is the ONE owner of the Crossing
decision — the floor/threshold sign conventions every lane (fast, durable,
start-gate, reconcile, repair, pool gate) imports.

These are the leverage pins: one file guards the compare that 11+ call sites
used to re-derive by hand. The cross-form equivalence tests (transition form
== level form on both edges; the pre-resolved line == the named predicate)
are the ones that make a future sign error impossible to reintroduce
silently.

Pure predicates — no DB, no Redis. CustomerSpendPool instances are UNSAVED (the
function only reads attributes), so the model-field default for
``enforce_mode`` is pinned without a query.
"""
import datetime

from core import crossing
from apps.billing.gating.models import CustomerSpendPool

FLOOR = 1_000_000  # min_balance magnitude; the comparable line is -1_000_000


class TestWalletFloorLevel:
    def test_past_floor_strictly_below_the_line(self):
        assert crossing.past_floor(-FLOOR - 1, FLOOR) is True
        assert crossing.past_floor(-FLOOR, FLOOR) is False  # AT the line = not past
        assert crossing.past_floor(0, FLOOR) is False
        assert crossing.past_floor(FLOOR, FLOOR) is False

    def test_zero_floor_means_the_zero_line(self):
        assert crossing.past_floor(-1, 0) is True
        assert crossing.past_floor(0, 0) is False

    def test_unconfigured_floor_is_never_past(self):
        # The soft floor resolves to None when unconfigured — no line to be past.
        assert crossing.past_floor(-(10**12), None) is False

    def test_floor_line_is_the_negated_magnitude(self):
        assert crossing.floor_line(FLOOR) == -FLOOR
        assert crossing.floor_line(0) == 0


class TestWalletFloorTransition:
    def test_crossed_floor_old_at_or_above_new_below(self):
        assert crossing.crossed_floor(-FLOOR, -FLOOR - 1, FLOOR) is True
        assert crossing.crossed_floor(0, -FLOOR - 1, FLOOR) is True

    def test_landing_exactly_on_the_line_is_not_a_crossing(self):
        assert crossing.crossed_floor(-FLOOR + 1, -FLOOR, FLOOR) is False

    def test_already_past_is_not_a_crossing(self):
        # The durable lane fires on the TRANSITION only — a repeat debit past
        # the line must not re-fire.
        assert crossing.crossed_floor(-FLOOR - 1, -2 * FLOOR, FLOOR) is False

    def test_unconfigured_floor_never_crosses(self):
        assert crossing.crossed_floor(0, -(10**12), None) is False

    def test_transition_form_equals_level_form_on_both_edges(self):
        # crossed == (not past(old)) and past(new) — the equivalence that keeps
        # handlers.py (transition) and RiskService (level) on one convention.
        values = (-2 * FLOOR, -FLOOR - 1, -FLOOR, -FLOOR + 1, 0, FLOOR)
        for old in values:
            for new in values:
                assert crossing.crossed_floor(old, new, FLOOR) == (
                    not crossing.past_floor(old, FLOOR)
                    and crossing.past_floor(new, FLOOR))


class TestWalletFloorRecovery:
    def test_recovered_at_or_above_the_line(self):
        assert crossing.recovered_floor(-FLOOR, FLOOR) is True  # AT the line = recovered
        assert crossing.recovered_floor(0, FLOOR) is True
        assert crossing.recovered_floor(-FLOOR - 1, FLOOR) is False

    def test_recovered_is_the_exact_negation_of_past(self):
        for bal in (-2 * FLOOR, -FLOOR - 1, -FLOOR, -FLOOR + 1, 0, FLOOR):
            assert crossing.recovered_floor(bal, FLOOR) == (
                not crossing.past_floor(bal, FLOOR))

    def test_unconfigured_floor_is_always_recovered(self):
        # #40 §F: a soft floor UNCONFIGURED mid-episode leaves no line to be
        # past — the clearing side treats that as recovered.
        assert crossing.recovered_floor(-(10**12), None) is True


class TestSpendPoolStopThreshold:
    def test_blocking_cap_times_hard_stop_pct(self):
        cfg = CustomerSpendPool(cap_micros=10_000_000, enforce_mode="blocking",
                           hard_stop_pct=120)
        assert crossing.spend_pool_stop_threshold(cfg) == 12_000_000

    def test_floor_division(self):
        cfg = CustomerSpendPool(cap_micros=999, enforce_mode="blocking",
                           hard_stop_pct=50)
        assert crossing.spend_pool_stop_threshold(cfg) == 499  # 999 * 50 // 100

    def test_no_config_can_never_cross(self):
        assert crossing.spend_pool_stop_threshold(None) is None

    def test_capless_config_can_never_cross(self):
        cfg = CustomerSpendPool(cap_micros=0, enforce_mode="blocking",
                           hard_stop_pct=100)
        assert crossing.spend_pool_stop_threshold(cfg) is None

    def test_alert_only_can_never_cross(self):
        """THE #110 drift pin: enforce_mode is honored HERE, once, for every
        lane (the CustomerSpendPoolService.check semantics — decision 8 on the overspend
        map kept alert_only) — an alert_only pool alerts but can never stop."""
        cfg = CustomerSpendPool(cap_micros=10_000_000, enforce_mode="alert_only",
                           hard_stop_pct=100)
        assert crossing.spend_pool_stop_threshold(cfg) is None

    def test_model_default_enforce_mode_is_alert_only_and_never_crosses(self):
        # A CustomerSpendPool created without enforce_mode is alert_only — the safe
        # default: alerts only, no stop, in every lane.
        cfg = CustomerSpendPool(cap_micros=10_000_000, hard_stop_pct=100)
        assert crossing.spend_pool_stop_threshold(cfg) is None

    def test_past_spend_pool_stop_at_or_over(self):
        assert crossing.past_spend_pool_stop(12, 12) is True  # AT the line = past
        assert crossing.past_spend_pool_stop(13, 12) is True
        assert crossing.past_spend_pool_stop(11, 12) is False

    def test_past_spend_pool_stop_none_threshold_never(self):
        assert crossing.past_spend_pool_stop(10**12, None) is False


class TestTheLineAgreesWithThePredicate:
    """The mode-keyed dispatcher the fast lane and reconcile once shared
    left with #459 (each lane names the line it compares); what survives is
    the sign-drift killer — the wallet's pre-resolved line and its named
    predicate are ONE decision."""

    def test_the_wallet_line_agrees_with_past_floor(self):
        for bal in (-2 * FLOOR, -FLOOR - 1, -FLOOR, -FLOOR + 1, 0, FLOOR):
            assert (bal < crossing.floor_line(FLOOR)) == crossing.past_floor(bal, FLOOR)

    def test_no_mode_keyed_dispatcher_survives(self):
        assert not hasattr(crossing, "crossed_live")


class TestMonthMath:
    def test_label_and_bounds(self):
        now = datetime.datetime(2026, 7, 22, 10, 0, tzinfo=datetime.timezone.utc)
        label, start, end = crossing.month_label_bounds(now)
        assert label == "2026-07"
        assert start == datetime.date(2026, 7, 1)
        assert end == datetime.date(2026, 8, 1)  # exclusive

    def test_december_rolls_the_year(self):
        now = datetime.datetime(2026, 12, 3, tzinfo=datetime.timezone.utc)
        label, start, end = crossing.month_label_bounds(now)
        assert label == "2026-12"
        assert start == datetime.date(2026, 12, 1)
        assert end == datetime.date(2027, 1, 1)

    def test_same_month_none_means_current(self):
        now = datetime.datetime(2026, 7, 22, tzinfo=datetime.timezone.utc)
        assert crossing.same_month(None, now) is True

    def test_same_month_plain(self):
        now = datetime.datetime(2026, 7, 22, tzinfo=datetime.timezone.utc)
        assert crossing.same_month(
            datetime.datetime(2026, 7, 1, tzinfo=datetime.timezone.utc), now) is True
        assert crossing.same_month(
            datetime.datetime(2026, 6, 30, 23, 59, tzinfo=datetime.timezone.utc), now) is False

    def test_same_month_normalizes_aware_offsets_to_utc(self):
        # 2026-08-01T00:30+02:00 IS 2026-07-31T22:30Z — July, not August.
        now = datetime.datetime(2026, 7, 22, tzinfo=datetime.timezone.utc)
        eff = datetime.datetime(
            2026, 8, 1, 0, 30,
            tzinfo=datetime.timezone(datetime.timedelta(hours=2)))
        assert crossing.same_month(eff, now) is True

    def test_same_month_naive_taken_as_is(self):
        # Legacy naive payloads compare without normalization (byte-for-byte
        # the pre-#110 behavior of every copy).
        now = datetime.datetime(2026, 7, 22, tzinfo=datetime.timezone.utc)
        assert crossing.same_month(datetime.datetime(2026, 7, 2), now) is True
        assert crossing.same_month(datetime.datetime(2026, 8, 2), now) is False


# --- the Ceiling (#452, slice 6 §3) -----------------------------------------
#
# The third orientation joins the module rather than living beside the row it
# assesses: the same `>=` used to be spelled three times — strictly-above on
# the live ingest lane, at-or-above on the patrol and the analytics count — and
# a unit landing EXACTLY on its ceiling survived the event that landed it and
# was killed by the patrol within the hour with no tipping event to attribute.
# Every case below is about the boundary, because the boundary is the defect.

CEILING = 10_000_000


class TestCeilingReached:
    def test_at_or_above_the_line_is_reached(self):
        assert crossing.ceiling_reached(CEILING, CEILING) is True  # AT = reached
        assert crossing.ceiling_reached(CEILING + 1, CEILING) is True
        assert crossing.ceiling_reached(CEILING - 1, CEILING) is False
        assert crossing.ceiling_reached(0, CEILING) is False

    def test_no_ceiling_is_never_reached(self):
        assert crossing.ceiling_reached(10**12, None) is False

    def test_a_zero_ceiling_is_reached_by_nothing_at_all(self):
        # `>=` on the line, so a ceiling of zero is reached before the first
        # report — a real answer, and the reason a zero is refused at the
        # start rather than made a special case here.
        assert crossing.ceiling_reached(0, 0) is True

    # The query form (`ceiling_reached_q`) is pinned to the level form on REAL
    # rows, over every boundary shape, in the work app's
    # `TheRowAssessesItsOwnCeilingTest` — a `Q` compared with a `Q` here would
    # only re-state the derivation, which is the vacuous shape.


class TestCeilingStatus:
    """The registry's four-way rule as code — each case is one row of
    `spend-controls.yaml`'s `value_semantics`, in the registry's own order."""

    def test_no_ceiling_is_not_applicable_whatever_the_cost(self):
        for known in (0, CEILING, 10**12):
            for unresolved in (0, 3):
                assert crossing.ceiling_status(
                    ceiling_micros=None, known_micros=known,
                    unresolved_count=unresolved) == "not_applicable"

    def test_known_at_or_above_is_reached_whatever_remains_unresolved(self):
        # Known-over always fires (#150 §4.2): an unresolved cost can only add
        # to a total that has already reached the line.
        for unresolved in (0, 1):
            assert crossing.ceiling_status(
                ceiling_micros=CEILING, known_micros=CEILING,
                unresolved_count=unresolved) == "ceiling_reached"
            assert crossing.ceiling_status(
                ceiling_micros=CEILING, known_micros=CEILING + 1,
                unresolved_count=unresolved) == "ceiling_reached"

    def test_known_below_with_something_unresolved_is_indeterminate(self):
        assert crossing.ceiling_status(
            ceiling_micros=CEILING, known_micros=CEILING - 1,
            unresolved_count=1) == "indeterminate"

    def test_known_below_with_nothing_unresolved_is_within(self):
        assert crossing.ceiling_status(
            ceiling_micros=CEILING, known_micros=CEILING - 1,
            unresolved_count=0) == "within_ceiling"

    def test_every_answer_is_one_of_the_registrys_four(self):
        from core.vocabulary import CEILING_STATUS_VALUES
        answers = {
            crossing.ceiling_status(ceiling_micros=c, known_micros=k,
                                    unresolved_count=u)
            for c in (None, CEILING) for k in (0, CEILING - 1, CEILING)
            for u in (0, 1)}
        assert answers == CEILING_STATUS_VALUES


class TestCeilingUtilisation:
    """Information beside the assessment (#150 §9): a whole percentage of the
    ceiling the KNOWN total has used, rounded down so it never overstates,
    and the headroom left — both over the known total in every evaluated
    state, both absent where no ceiling applies."""

    def test_percentage_is_whole_and_rounded_down(self):
        assert crossing.ceiling_used_percentage(0, CEILING) == 0
        assert crossing.ceiling_used_percentage(CEILING // 2, CEILING) == 50
        assert crossing.ceiling_used_percentage(CEILING - 1, CEILING) == 99
        assert crossing.ceiling_used_percentage(CEILING, CEILING) == 100
        assert crossing.ceiling_used_percentage(CEILING * 2, CEILING) == 200

    def test_remaining_is_the_headroom_and_never_negative(self):
        assert crossing.ceiling_remaining_micros(0, CEILING) == CEILING
        assert crossing.ceiling_remaining_micros(CEILING - 1, CEILING) == 1
        assert crossing.ceiling_remaining_micros(CEILING, CEILING) == 0
        # Past the line there is no headroom left, and the percentage beside
        # it is what says by how much — a negative "remaining" would be the
        # same fact spelled as a number a reader has to negate.
        assert crossing.ceiling_remaining_micros(CEILING + 5, CEILING) == 0

    def test_no_ceiling_has_no_utilisation(self):
        assert crossing.ceiling_used_percentage(CEILING, None) is None
        assert crossing.ceiling_remaining_micros(CEILING, None) is None

    def test_a_share_of_nothing_is_not_a_share(self):
        # A zero ceiling is `ceiling_reached` (the compare says so) and has
        # no headroom, but a percentage of zero is not a number.
        assert crossing.ceiling_used_percentage(0, 0) is None
        assert crossing.ceiling_remaining_micros(0, 0) == 0

    def test_the_assessment_travels_as_one_value(self):
        # The three answers composed once, so a reader cannot take the
        # figures without the status that says how to read them.
        assert crossing.ceiling_assessment(
            ceiling_micros=CEILING, known_micros=CEILING // 4,
            unresolved_count=2) == crossing.CeilingAssessment(
                "indeterminate", 25, CEILING - CEILING // 4)
        assert crossing.ceiling_assessment(
            ceiling_micros=None, known_micros=CEILING,
            unresolved_count=0) == crossing.CeilingAssessment(
                "not_applicable", None, None)
