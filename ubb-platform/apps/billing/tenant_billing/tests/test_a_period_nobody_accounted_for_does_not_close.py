"""A period holding money nobody has accounted for does not close (#329).

Slice 2 built the safeguard beside the table it reads and deliberately left it
unwired, saying in its own comment that slice 3 owns every behaviour that reads
it. This module is the wiring, and what it holds is the two halves of a
distinction that is easy to state and easy to lose:

**A held name is an outstanding TENANT DECISION.** Something arrived under a
name nobody declared. Three remediations are available — map it, register it,
dismiss it — and until one is taken, nobody has said what that spend was. The
close **refuses**, because *"the month is closed"* must never mean *"the month
is closed except for the parts nobody looked at"*.

**An unresolved cost is missing SUPPLIER information**, and it may never arrive.
One late invoice must not freeze a tenant's billing, so the period **closes on
time, excludes it, and says how many it excluded**. A total that states its own
completeness is #327's pair; this is the pair reaching the one event that ends a
month.

**The two windows are not the same window, and that is deliberate.** The guard
places a held name by ``occurred_at`` — the moment the call happened, never the
moment somebody got round to the repair — so a January charge repaired in March
blocks January and never appears in February. The exclusion count is read on the
ARRIVAL basis, because that is the basis the period's own fee accrues on (F4.2)
and a report about what a period left out has to be about the rows that period
accounts for.
"""
from datetime import date, datetime, timezone as dt_timezone
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase

from apps.billing.tenant_billing.models import (
    BillingTenantConfig,
    TenantBillingPeriod,
)
from apps.billing.tenant_billing.services import TenantBillingService
from apps.billing.tenant_billing.tasks import close_tenant_billing_periods
from apps.metering.usage.models import Posting
from apps.platform.customers.models import Customer
from apps.platform.event_types.models import (
    EventType,
    Measurement,
    QuarantinedKey,
)
from apps.platform.event_types.quarantine import (
    PeriodHoldsUnresolvedValues,
    dismiss_as_non_economic,
    hold_an_unrecognised_quantity,
    register_the_held_name,
)
from apps.platform.tenants.models import Tenant
from core.cost_totals import UNRESOLVED_EVENT_COUNT_KEY
from core.vocabulary import (
    COSTING_METHOD_CALCULATED,
    COSTING_STATUS_UNRESOLVED,
    SOURCE_KIND_CALLER_SUPPLIED,
    UNIT_TOKEN,
    UNRESOLVED_REASON_COST_RATE_MISSING,
)

#: A period that has already ended, so the sweeper's own filter selects it.
JANUARY_OPENS = date(2026, 1, 1)
JANUARY_CLOSES = date(2026, 2, 1)
FEBRUARY_CLOSES = date(2026, 3, 1)

#: The instant the two adjacent periods share. It belongs to exactly one of
#: them, and which one is what a half-open window decides.
THE_BOUNDARY = datetime(2026, 2, 1, 0, 0, 0, tzinfo=dt_timezone.utc)
MID_JANUARY = datetime(2026, 1, 15, 12, 0, 0, tzinfo=dt_timezone.utc)

EVENT_TYPE_KEY = "acme.embed"


def _tenant(name="T"):
    """A tenant whose fee configuration is stated rather than defaulted.

    ⚠ NOT TIDINESS — the lazily-created default is a `float` on a
    `DecimalField` (`BillingTenantConfig.platform_fee_percentage`), and
    `get_or_create` hands back the unsaved value rather than the coerced one,
    so the FIRST close of a tenant that has no config row raises `TypeError`
    inside `_calculate_fees`. It self-heals on the next sweep, because by then
    the row is read back from the database as a `Decimal` — which is why it has
    never been noticed. It is out of this ticket's extent and recorded here so
    the next reader does not diagnose it a second time.
    """
    tenant = Tenant.objects.create(
        name=name, stripe_connected_account_id=f"acct_{name}",
        platform_fee_percentage=Decimal("1.00"))
    BillingTenantConfig.objects.create(
        tenant=tenant, platform_fee_percentage=Decimal("1.00"))
    return tenant


def _period(tenant, *, opens=JANUARY_OPENS, closes=JANUARY_CLOSES):
    return TenantBillingPeriod.objects.create(
        tenant=tenant, period_start=opens, period_end=closes, status="open")


def _a_name_nobody_declared(tenant, *, occurred_at=MID_JANUARY,
                            held_name="reasoning_tokens"):
    """A quantity code arriving beneath a declared Event Type that omits it.

    The held row is what an unrecognised name becomes: the event is kept whole,
    the name is held, and the tenant is asked. Everything below is about what a
    period close does while that question is unanswered.
    """
    EventType.objects.get_or_create(
        tenant=tenant, key=EVENT_TYPE_KEY,
        defaults={"costing_method": COSTING_METHOD_CALCULATED})
    return hold_an_unrecognised_quantity(
        tenant=tenant, event_type_key=EVENT_TYPE_KEY,
        measurement_key=held_name, quantity="12", occurred_at=occurred_at)


def _declared(tenant, code):
    event_type = EventType.objects.get(tenant=tenant, key=EVENT_TYPE_KEY)
    return Measurement.objects.create(
        event_type=event_type, code=code, unit=UNIT_TOKEN,
        source_kind=SOURCE_KIND_CALLER_SUPPLIED)


def _held_row(tenant):
    """The tenant's one still-held name, re-read rather than passed around."""
    return QuarantinedKey.objects.unresolved().get(tenant=tenant)


def _a_posting(tenant, *, arrived_at, key, **cost):
    """One posting in the window, with its arrival time written after the fact.

    ``created_at`` is ``auto_now_add``, so it can only be set by an update —
    and it is the ARRIVAL basis the period's fee accrues on, so it is the one
    that has to land inside the period for the posting to be this period's.
    """
    customer, _ = Customer.objects.get_or_create(
        tenant=tenant, external_id="c1")
    posting = Posting.objects.create(
        tenant=tenant, customer=customer, idempotency_key=key,
        billed_cost_micros=1_000_000, **cost)
    Posting.objects.filter(id=posting.id).update(
        created_at=arrived_at, effective_at=arrived_at)
    return posting


def _a_cost_ubb_never_learned(tenant, *, arrived_at=MID_JANUARY, key="i1"):
    """A posting whose supplier cost is unresolved: the excluded case."""
    return _a_posting(
        tenant, arrived_at=arrived_at, key=key, provider_cost_micros=None,
        costing_status=COSTING_STATUS_UNRESOLVED,
        unresolved_reason=UNRESOLVED_REASON_COST_RATE_MISSING)


def _a_cost_ubb_learned(tenant, *, arrived_at=MID_JANUARY, key="i1"):
    """Its twin, resolved. The pair is what makes a count evidence."""
    return _a_posting(tenant, arrived_at=arrived_at, key=key,
                      provider_cost_micros=800_000)


class TheGuardRunsBeforeTheReconcileTest(TestCase):
    """A period that will not close does not first do the work of closing.

    Reconciliation reads every posting in the window and rewrites the period's
    totals, and none of that survives a refusal. The saving is one wasted pass
    per attempt — the sweeper runs monthly, not hourly — but the ordering also
    decides what a refusal MEANS: refusing after the rewrite would leave a
    period whose stored totals had moved and whose status had not.
    """

    def test_a_refused_period_is_not_reconciled_first(self):
        """The ordering, observed rather than mocked.

        The period's stored totals are deliberately wrong. Reconciliation would
        correct them from the postings in the window; the guard refuses before
        it can. So the totals standing untouched after the refusal is the
        reconcile provably not having run — asserted through real behaviour,
        with nothing patched, which is what makes it survive a refactor that
        moves the call rather than deletes it.
        """
        tenant = _tenant()
        period = _period(tenant)
        TenantBillingPeriod.objects.filter(id=period.id).update(
            total_usage_cost_micros=999_999, event_count=7)
        _a_cost_ubb_learned(tenant)
        _a_name_nobody_declared(tenant)

        with self.assertRaises(PeriodHoldsUnresolvedValues):
            TenantBillingService.close_period(period)

        period.refresh_from_db()
        assert period.total_usage_cost_micros == 999_999
        assert period.event_count == 7

        # The control: with the name decided, the same call DOES reconcile —
        # so the assertion above is about the guard's placement and not about a
        # reconcile that never worked on this fixture.
        dismiss_as_non_economic(_held_row(tenant))
        TenantBillingService.close_period(period)

        period.refresh_from_db()
        assert period.total_usage_cost_micros == 1_000_000
        assert period.event_count == 1

    def test_the_guard_is_asked_with_the_periods_own_bounds(self):
        """AC 1's other half: which window, and passed how.

        The two instants are keyword-only at the guard, and the reason is worth
        restating where the call is made: they are the same type, and an
        inverted window matches nothing, reports nothing held, and lets the
        period close — the exact outcome the guard exists to prevent. So the
        call is asserted BY KEYWORD rather than by position; a positional call
        would not even reach the guard. The arguments a call was made with are
        the one thing no amount of observed behaviour shows, which is why this
        is the test that patches and the one above is not.
        """
        tenant = _tenant()
        period = _period(tenant)
        asked = []

        with patch("apps.billing.tenant_billing.services.refuse_a_silent_close",
                   side_effect=lambda **kwargs: asked.append(kwargs)):
            TenantBillingService.close_period(period)

        # The WHOLE argument map, not a key at a time: a per-key assertion
        # passes while a fourth argument rides along beside it, and the bounds
        # are exactly the period's own — no widening, no rounding, no "now".
        assert asked == [{
            "tenant": tenant,
            "opened_at": datetime(2026, 1, 1, tzinfo=dt_timezone.utc),
            "closes_at": datetime(2026, 2, 1, tzinfo=dt_timezone.utc),
        }]

    def test_an_already_closed_period_is_not_refused_by_a_name_held_later(self):
        """Closing is idempotent, and a guard must not take that away.

        The month closed. A name arriving afterwards, dated inside it, is a real
        problem and a real refusal — for the close that has not happened. Making
        every later call on the CLOSED period raise would report a month as
        unaccounted-for for a close that already succeeded, and it would do it
        forever, because nothing can un-close a period to satisfy the guard.
        """
        tenant = _tenant()
        period = _period(tenant)
        TenantBillingService.close_period(period)
        period.refresh_from_db()
        assert period.status == "closed"

        _a_name_nobody_declared(tenant)

        # No refusal, and the guard is never even consulted — asked for by
        # keyword-argument capture rather than by "it did not raise", which
        # would also pass against a guard that ran and found nothing.
        asked = []
        with patch("apps.billing.tenant_billing.services.refuse_a_silent_close",
                   side_effect=lambda **kwargs: asked.append(kwargs)):
            TenantBillingService.close_period(period)

        assert asked == []


class AnUndecidedNameRefusesTheCloseTest(TestCase):
    """Refusal, and the three answers that lift it."""

    def test_the_period_does_not_close_and_the_refusal_names_what_is_held(self):
        """AC 2. A refusal that does not say what is held cannot be acted on.

        An operator reading it has to know which name to go and decide, and the
        period has to be exactly as it was — a period half-closed by a guard
        that fired late would be worse than one that closed silently.
        """
        tenant = _tenant()
        period = _period(tenant)
        _a_name_nobody_declared(tenant)

        with self.assertRaises(PeriodHoldsUnresolvedValues) as refusal:
            TenantBillingService.close_period(period)

        assert "reasoning_tokens" in str(refusal.exception)
        assert refusal.exception.held == ("reasoning_tokens",)
        period.refresh_from_db()
        assert period.status == "open"

    def test_a_dismissed_name_does_not_block_the_close(self):
        """AC 4. Dismissal IS the tenant's answer, and a close that still
        refused afterwards would leave the period permanently unclosable."""
        tenant = _tenant()
        period = _period(tenant)
        dismiss_as_non_economic(_a_name_nobody_declared(tenant))

        TenantBillingService.close_period(period)

        period.refresh_from_db()
        assert period.status == "closed"

    def test_a_registered_name_does_not_block_the_close(self):
        """The other end of the same rule: a decision taken is a decision."""
        tenant = _tenant()
        period = _period(tenant)
        held = _a_name_nobody_declared(tenant)
        register_the_held_name(held, _declared(tenant, "reasoning_tokens"))

        TenantBillingService.close_period(period)

        period.refresh_from_db()
        assert period.status == "closed"

    def test_a_held_charge_refuses_one_period_and_not_its_neighbour(self):
        """AC 5. The instant two adjacent periods share belongs to the later.

        A closed window at both ends would place a charge landing exactly on the
        boundary in two months at once, and the same held supplier charge would
        then refuse two different closes — one of which no remediation can ever
        clear, because clearing it clears the other too.
        """
        tenant = _tenant()
        january = _period(tenant)
        _a_name_nobody_declared(tenant, occurred_at=THE_BOUNDARY)

        TenantBillingService.close_period(january)

        january.refresh_from_db()
        assert january.status == "closed"

        february = _period(tenant, opens=JANUARY_CLOSES, closes=FEBRUARY_CLOSES)
        with self.assertRaises(PeriodHoldsUnresolvedValues):
            TenantBillingService.close_period(february)


class ThePeriodClosesOnTimeAndSaysWhatItExcludedTest(TestCase):
    """The other half of the line: supplier information, not a tenant decision.

    Nobody at this tenant has a decision outstanding. What is missing is a
    number from a supplier, which may never arrive at all — so the month closes
    when it is due and states how much of itself it could not account for.
    """

    def test_an_unresolved_cost_does_not_refuse_the_close(self):
        """AC 3. One missing supplier invoice must not freeze a tenant's
        billing, and this is the assertion that says so."""
        tenant = _tenant()
        period = _period(tenant)
        _a_cost_ubb_never_learned(tenant)

        TenantBillingService.close_period(period)

        period.refresh_from_db()
        assert period.status == "closed"

    def test_the_close_states_the_supplier_total_and_what_it_left_out(self):
        """AC 3's second half. Both keys or neither — a total that says nothing
        about its own completeness is the ambiguity this slice deletes, and a
        count logged only when it is non-zero cannot be told from a count
        nobody wrote."""
        tenant = _tenant()
        period = _period(tenant)
        _a_cost_ubb_never_learned(tenant, key="i1")
        _a_cost_ubb_never_learned(tenant, key="i2")

        with self.assertLogs("apps.billing.tenant_billing.services",
                             level="INFO") as logs:
            TenantBillingService.close_period(period)

        closed = [r for r in logs.records if r.msg == "tenant_billing.period_closed"]
        assert len(closed) == 1
        assert closed[0].data[UNRESOLVED_EVENT_COUNT_KEY] == 2
        assert closed[0].data["total_provider_cost_micros"] == 0

    def test_a_period_that_accounted_for_everything_says_so_too(self):
        """The control that makes the count above evidence: the same statement,
        with a zero in it, on a period whose costs are all known."""
        tenant = _tenant()
        period = _period(tenant)
        _a_cost_ubb_learned(tenant)

        with self.assertLogs("apps.billing.tenant_billing.services",
                             level="INFO") as logs:
            TenantBillingService.close_period(period)

        closed = [r for r in logs.records if r.msg == "tenant_billing.period_closed"]
        assert closed[0].data[UNRESOLVED_EVENT_COUNT_KEY] == 0
        assert closed[0].data["total_provider_cost_micros"] == 800_000

    def test_a_decided_name_and_an_outstanding_cost_close_together(self):
        """AC 3 AS WRITTEN, which is a conjunction and not two facts.

        *"A period whose held names have all been decided closes on time even
        with unresolved costs outstanding, and reports what it excluded."* The
        two sibling tests above each hold one half of that still: one has a
        decided name and no outstanding cost, the other an outstanding cost and
        no name. Neither constructs the case the criterion names, and the case
        is the whole point of the line the ticket draws — a decision taken and
        supplier information still missing are different things, and only the
        first was ever allowed to hold a month open.
        """
        tenant = _tenant()
        period = _period(tenant)
        dismiss_as_non_economic(_a_name_nobody_declared(tenant))
        _a_cost_ubb_never_learned(tenant, key="i1")

        with self.assertLogs("apps.billing.tenant_billing.services",
                             level="INFO") as logs:
            TenantBillingService.close_period(period)

        period.refresh_from_db()
        assert period.status == "closed"
        closed = [r for r in logs.records if r.msg == "tenant_billing.period_closed"]
        assert closed[0].data[UNRESOLVED_EVENT_COUNT_KEY] == 1

    def test_a_close_with_no_trusted_read_behind_it_states_that_instead(self):
        """A zero that means "nobody counted" is the defect, not the report.

        Reconciliation declines to believe a window where metering sees no
        postings but the period's own counter says it holds some. Handing that
        back as a pair would publish *"this month excluded nothing"* for exactly
        the window it just refused to trust — the silent zero this slice exists
        to delete, one layer up and wearing the pair's own clothes. So the close
        says something different, and says it at warning.
        """
        tenant = _tenant()
        period = _period(tenant)
        # The period's counter says it holds events; no posting matches the
        # window, which is the disagreement the branch exists for. Re-read
        # afterwards because reconciliation compares against the instance it is
        # handed, and an `update` leaves that instance saying zero.
        TenantBillingPeriod.objects.filter(id=period.id).update(event_count=3)
        period.refresh_from_db()

        with self.assertLogs("apps.billing.tenant_billing.services",
                             level="INFO") as logs:
            TenantBillingService.close_period(period)

        period.refresh_from_db()
        assert period.status == "closed"
        assert [r.msg for r in logs.records] == [
            "tenant_billing.period_closed_without_a_trusted_total"]
        assert logs.records[0].levelname == "WARNING"


class TheSweeperTellsARefusalFromAFailureTest(TestCase):
    """AC 6. A period working exactly as designed is not a failure.

    The generic branch below the refusal logs an exception with a traceback and
    a message saying the close FAILED. An operator triaging that has nothing to
    act on: nothing is broken, a tenant has a decision outstanding, and the two
    need different people. So the refusal is caught above the generic branch and
    reported as what it is.
    """

    def test_a_refusal_is_logged_as_a_refusal_and_names_the_held_items(self):
        tenant = _tenant()
        _period(tenant)
        _a_name_nobody_declared(tenant)

        with self.assertLogs("apps.billing.tenant_billing.tasks") as logs:
            close_tenant_billing_periods()

        refusals = [r for r in logs.records
                    if r.msg == "tenant_billing.period_close_refused"]
        assert len(refusals) == 1
        assert refusals[0].levelname == "WARNING"
        assert refusals[0].exc_info is None
        assert refusals[0].data["held"] == ["reasoning_tokens"]
        # The distinguishing half: nothing reported a failure. Asserted over the
        # whole run rather than over the refusing period, because a second log
        # line about the same period is exactly the confusion this separates.
        assert [r for r in logs.records if r.levelname == "ERROR"] == []

    def test_a_refused_period_does_not_stop_the_next_one_closing(self):
        """The sweeper moves on. A tenant with an outstanding decision must not
        hold up every other tenant's month.

        WHAT THIS SHOWS AND WHAT IT CANNOT. It kills the two mutations that
        matter, and it kills them whichever order the periods come back in: a
        refusal that RE-RAISES fails the whole task, and a refusal caught by the
        generic branch instead reports a failure — the sibling test above
        catches that one. What it cannot pin is iteration order, because the
        sweeper's queryset declares none, so a contrived `break` after the
        refusal would survive whenever the clean period happened to come first.
        Saying so is cheaper than a fixture that pretends otherwise.
        """
        refusing = _tenant("refusing")
        _period(refusing)
        _a_name_nobody_declared(refusing)
        ordinary = _tenant("ordinary")
        clean = _period(ordinary)

        with self.assertLogs("apps.billing.tenant_billing.tasks") as logs:
            close_tenant_billing_periods()

        clean.refresh_from_db()
        assert clean.status == "closed"
        assert [r.msg for r in logs.records].count(
            "tenant_billing.period_close_refused") == 1

    def test_a_real_failure_is_still_reported_as_a_failure(self):
        """The negative control for the branch above. Without it, "the refusal
        is not logged as a failure" would pass just as well against a task that
        had stopped reporting failures at all."""
        tenant = _tenant()
        _period(tenant)

        with patch.object(TenantBillingService, "close_period",
                          side_effect=ValueError("something actually broke")), \
                self.assertLogs("apps.billing.tenant_billing.tasks",
                                level="ERROR") as logs:
            close_tenant_billing_periods()

        assert logs.records[0].levelname == "ERROR"
        assert logs.records[0].exc_info is not None
