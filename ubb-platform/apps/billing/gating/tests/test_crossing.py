"""#110: ``apps.billing.gating.crossing`` is the ONE owner of the Crossing
decision — the floor/threshold sign conventions every lane (fast, durable,
start-gate, reconcile, repair, budget gate) imports.

These are the leverage pins: one file guards the compare that 11+ call sites
used to re-derive by hand. The cross-form equivalence tests (transition form
== level form on both edges; mode dispatch == the named predicate) are the
ones that make a future sign error impossible to reintroduce silently.

Pure predicates — no DB, no Redis. BudgetConfig instances are UNSAVED (the
function only reads attributes), so the model-field default for
``enforce_mode`` is pinned without a query.
"""
import datetime

from apps.billing.gating import crossing
from apps.billing.gating.models import BudgetConfig

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


class TestBudgetStopThreshold:
    def test_enforcing_cap_times_hard_stop_pct(self):
        cfg = BudgetConfig(cap_micros=10_000_000, enforce_mode="enforcing",
                           hard_stop_pct=120)
        assert crossing.budget_stop_threshold(cfg) == 12_000_000

    def test_floor_division(self):
        cfg = BudgetConfig(cap_micros=999, enforce_mode="enforcing",
                           hard_stop_pct=50)
        assert crossing.budget_stop_threshold(cfg) == 499  # 999 * 50 // 100

    def test_no_config_can_never_cross(self):
        assert crossing.budget_stop_threshold(None) is None

    def test_capless_config_can_never_cross(self):
        cfg = BudgetConfig(cap_micros=0, enforce_mode="enforcing",
                           hard_stop_pct=100)
        assert crossing.budget_stop_threshold(cfg) is None

    def test_advisory_can_never_cross(self):
        """THE #110 drift pin: enforce_mode is honored HERE, once, for every
        lane (the BudgetService.check semantics — decision 8 on the overspend
        map kept advisory) — an advisory budget alerts but can never stop."""
        cfg = BudgetConfig(cap_micros=10_000_000, enforce_mode="advisory",
                           hard_stop_pct=100)
        assert crossing.budget_stop_threshold(cfg) is None

    def test_model_default_enforce_mode_is_advisory_and_never_crosses(self):
        # A BudgetConfig created without enforce_mode is advisory — the safe
        # default: alerts only, no stop, in every lane.
        cfg = BudgetConfig(cap_micros=10_000_000, hard_stop_pct=100)
        assert crossing.budget_stop_threshold(cfg) is None

    def test_past_budget_stop_at_or_over(self):
        assert crossing.past_budget_stop(12, 12) is True  # AT the line = past
        assert crossing.past_budget_stop(13, 12) is True
        assert crossing.past_budget_stop(11, 12) is False

    def test_past_budget_stop_none_threshold_never(self):
        assert crossing.past_budget_stop(10**12, None) is False


class TestCrossedLive:
    """The mode dispatch the fast lane / hold batch / reconcile share: one
    orientation per mode, threshold pre-resolved once per owner."""

    def test_postpaid_spend_rises_across_the_stop_line(self):
        assert crossing.crossed_live("postpaid", 12, 12) is True
        assert crossing.crossed_live("postpaid", 11, 12) is False

    def test_prepaid_balance_falls_across_the_wallet_line(self):
        line = crossing.floor_line(FLOOR)
        assert crossing.crossed_live("prepaid", -FLOOR - 1, line) is True
        assert crossing.crossed_live("prepaid", -FLOOR, line) is False

    def test_none_threshold_never_crosses_either_mode(self):
        assert crossing.crossed_live("postpaid", 10**12, None) is False
        assert crossing.crossed_live("prepaid", -(10**12), None) is False

    def test_prepaid_dispatch_agrees_with_past_floor(self):
        # The sign-drift killer: the batch compare (value vs pre-resolved
        # line) and the named predicate (balance vs floor magnitude) are ONE
        # decision.
        for bal in (-2 * FLOOR, -FLOOR - 1, -FLOOR, -FLOOR + 1, 0, FLOOR):
            assert crossing.crossed_live(
                "prepaid", bal, crossing.floor_line(FLOOR)
            ) == crossing.past_floor(bal, FLOOR)

    def test_postpaid_dispatch_agrees_with_past_budget_stop(self):
        for spend in (0, 11, 12, 13, 10**9):
            assert crossing.crossed_live("postpaid", spend, 12) == \
                crossing.past_budget_stop(spend, 12)


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
