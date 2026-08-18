"""The three ways a nullable price breaks a reader, one test each (#351).

`Posting.billed_cost_micros` went nullable in the same commit as this module.
Thirty-nine sites read that column, and a grep for `Sum("billed_cost_micros")`
finds seventeen of them — it cannot see Python arithmetic over the same value,
and the twenty-two it misses fail in three distinct ways. **The three shapes are
not variations on one bug**: two raise and one does not, and the one that does
not is the dangerous one.

    1. `TypeError` inside a REPORT.   `sum(...)` / `+=` over the raw value.
    2. `TypeError` inside a HANDLER.  `value > 0` on an outbox payload.
    3. `F("total") + value`, where    SQL propagates `NULL` through addition
       null propagation reaches a     and the running total becomes `NULL`.
       running total.

⚠ **A CORRECTION TO THE SLICE'S OWN SPEC, MEASURED RATHER THAN ASSUMED.** The
spec files shape 3 as *"a silently wrong number — no exception, no log line"*,
and in this repository it is not silent: both accumulator columns
(`TenantBillingPeriod.total_usage_cost_micros` and `CustomerCostAccumulator`'s
pair) are **NOT NULL**, so Postgres refuses the write and the failure surfaces
as an `IntegrityError` inside an outbox handler — a poisoned retry loop rather
than a quiet total. The defect is real and the repair is unchanged; what is
wrong is the shape, and it matters because a reader who believed the silent
version would go hunting for corrupted historical figures that do not exist.
`test_an_unresolved_price_leaves_the_running_total_a_number` below was run
against the guard removed, and that is what it reported.

Each shape has its own test below, driven through the real surface, because a
shared fixture asserting "no exception" would say nothing about which of the
three it had exercised.

**The past-limit report is the known blind spot**, which is why shape 1 is
tested there rather than anywhere cheaper. #153 §17.6 predicted this exact
failure — *"the moment either goes nullable this is a `TypeError` inside a
report endpoint"* — and a contract-derived surface enumeration has already
missed the same endpoint once, because its response is untyped and no schema
names its rows.

⚠ **THE POSTINGS BELOW ARE WRITTEN THROUGH THE ORM** and the recording route is
never called, for the reason the sibling module gives: the recording request's
correlation key is a retired word at a ledger this file must not widen.
"""
from datetime import date, timedelta

import pytest
from django.test import Client
from django.utils import timezone

from apps.billing.tenant_billing.models import TenantBillingPeriod
from apps.billing.tenant_billing.services import TenantBillingService
from apps.metering.usage.models import Posting
from apps.platform.customers.models import Customer
from apps.platform.tenants.models import Tenant, TenantApiKey
from apps.platform.work import reasons
from core.cost_totals import UNPRICED_EVENT_COUNT_KEY
from core.vocabulary import (
    NOT_APPLICABLE_REASON_TENANT_NOT_BILLING,
    PRICING_STATUS_KNOWN,
    PRICING_STATUS_NOT_APPLICABLE,
    PRICING_STATUS_UNKNOWN,
    PRICING_STATUS_WAIVED,
)

KNOWN_PRICE_MICROS = 3_000_000


def _posting(tenant, customer, key, *, status=PRICING_STATUS_KNOWN,
             price=KNOWN_PRICE_MICROS, **kwargs):
    """One posting in one of the four pricing states.

    The amount and the status move together because the database refuses every
    other combination (`ck_posting_pricing_status_agrees_with_the_price`), so a
    fixture that got them out of step would fail as a WRITE rather than quietly
    test a row that cannot exist.
    """
    if status == PRICING_STATUS_KNOWN:
        amount, reason = price, None
    elif status == PRICING_STATUS_NOT_APPLICABLE:
        amount, reason = None, NOT_APPLICABLE_REASON_TENANT_NOT_BILLING
    else:  # waived, unknown
        amount, reason = None, None
    return Posting.objects.create(
        tenant=tenant, customer=customer, idempotency_key=key,
        billed_cost_micros=amount, pricing_status=status,
        not_applicable_reason=reason, **kwargs)


@pytest.mark.django_db
class TestShapeOneAReportThatWouldHaveFiveHundredEd:
    """The past-limit report, over a posting UBB could not price.

    Two sites in one endpoint: the episode row's `sum(...)` generator and the
    per-limit `+=` accumulation. Both read the raw value, both would have raised
    `TypeError` on the first unpriced posting past a limit, and neither is
    reachable from a schema — the response is untyped.
    """

    def setup_method(self):
        self.tenant = Tenant.objects.create(name="T", products=["metering"])
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="c1")
        _, self.raw_key = TenantApiKey.create_key(self.tenant)
        self.stop = [{"limit": reasons.CUSTOMER_WIDE_STOP,
                      "stop_scope": "customer", "episode_seq": 1,
                      "tripped_at": timezone.now().isoformat(),
                      "arrived_after": True}]

    def _report(self):
        # Unwindowed, like the sibling pin module's helper: an ISO datetime's
        # `+00:00` offset is a space once it is a query-string value, so the
        # endpoint refuses it with a 422 that has nothing to do with pricing.
        return Client().get(
            f"/api/v1/customers/{self.customer.id}/past-limit-report",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}")

    def test_the_report_answers_rather_than_raising(self):
        _posting(self.tenant, self.customer, "k1", stop_context=self.stop)
        _posting(self.tenant, self.customer, "k2",
                 status=PRICING_STATUS_UNKNOWN, stop_context=self.stop)
        assert self._report().status_code == 200

    def test_the_total_is_a_floor_and_the_count_says_how_far_it_falls_short(self):
        """The AC's assertion: the completeness count the report reports.

        The rule is the one the cost half's docstring states and this half now
        applies — an unresolved amount is skipped and COUNTED, so the total is a
        floor that says how far short it falls.
        """
        _posting(self.tenant, self.customer, "k1", stop_context=self.stop)
        _posting(self.tenant, self.customer, "k2",
                 status=PRICING_STATUS_UNKNOWN, stop_context=self.stop)
        body = self._report().json()

        episode, = [e for e in body["episodes"]
                    if e["limit"] == reasons.CUSTOMER_WIDE_STOP]
        assert episode["total_billed_cost_micros"] == KNOWN_PRICE_MICROS
        assert episode[UNPRICED_EVENT_COUNT_KEY] == 1
        assert episode["event_count"] == 2

        totals = body["totals_per_limit"][reasons.CUSTOMER_WIDE_STOP]
        assert totals["billed_cost_micros"] == KNOWN_PRICE_MICROS
        assert totals[UNPRICED_EVENT_COUNT_KEY] == 1

    @pytest.mark.parametrize(
        "status", [PRICING_STATUS_WAIVED, PRICING_STATUS_NOT_APPLICABLE])
    def test_a_price_that_is_settled_at_nothing_is_not_counted(self, status):
        """The other half of the rule, and the reason the STATUS decides.

        A waive is a decision reported as a loss and a `not_applicable` subject
        generates no customer revenue at all; both contribute a genuine zero, so
        neither is missing information. All three statuses carry a `NULL`
        amount, so the amount cannot tell them apart — which is precisely why
        the count is taken over the status and not over the null.
        """
        _posting(self.tenant, self.customer, "k1", stop_context=self.stop)
        _posting(self.tenant, self.customer, "k2", status=status,
                 stop_context=self.stop)
        body = self._report().json()
        episode, = [e for e in body["episodes"]
                    if e["limit"] == reasons.CUSTOMER_WIDE_STOP]
        assert episode["total_billed_cost_micros"] == KNOWN_PRICE_MICROS
        assert episode[UNPRICED_EVENT_COUNT_KEY] == 0
        assert episode["event_count"] == 2


@pytest.mark.django_db
class TestShapeTwoAHandlerThatWouldHaveFiveHundredEd:
    """Billing's `usage.recorded` handler, over the payload's legacy price field.

    The comparison was `if billed_cost_micros > 0`, and `None > 0` is a
    `TypeError`. An outbox handler that raises does not fail a request — it
    retries with backoff — so this would have shown up as a stuck queue rather
    than as an error a caller could see.

    ⚠ THE PAYLOAD FIELD WAS TYPED `int`, NOT `int | None`, and that is the
    finding this ticket was sent to make. A frozen dataclass does not enforce
    its annotations at runtime, so the recording path would have assigned the
    column's `None` straight into a field the published document declares an
    integer: no exception at the write, and two products reading it.
    """

    def setup_method(self):
        self.tenant = Tenant.objects.create(
            name="T", products=["metering", "billing"], billing_mode="postpaid")
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="c1")

    def _payload(self, price, status):
        return {"tenant_id": str(self.tenant.id),
                "customer_id": str(self.customer.id),
                "event_id": "e1", "cost_micros": price,
                "billed_cost_micros": price, "pricing_status": status,
                "effective_at": timezone.now().isoformat()}

    def test_the_handler_answers_rather_than_raising(self):
        from apps.billing.handlers import handle_usage_recorded_billing
        handle_usage_recorded_billing("e1", self._payload(None, PRICING_STATUS_UNKNOWN))

    def test_it_accumulates_no_money_for_a_price_it_does_not_have(self):
        """Not merely "does not raise": there is no amount to accumulate.

        The handler's branch is about MONEY — the drawdown, the accumulation
        and the live spend counters all take an amount, and there is none. What
        it must not do is invent one.
        """
        from apps.billing.handlers import handle_usage_recorded_billing
        handle_usage_recorded_billing("e1", self._payload(None, PRICING_STATUS_UNKNOWN))
        assert not TenantBillingPeriod.objects.filter(
            tenant=self.tenant, total_usage_cost_micros__gt=0).exists()

    def test_a_resolved_price_still_accumulates(self):
        """The control. Every assertion above is about something NOT happening,
        and a handler that had stopped working entirely would satisfy them all.
        """
        from apps.billing.handlers import handle_usage_recorded_billing
        handle_usage_recorded_billing(
            "e1", self._payload(KNOWN_PRICE_MICROS, PRICING_STATUS_KNOWN))
        period = TenantBillingPeriod.objects.get(tenant=self.tenant)
        assert period.total_usage_cost_micros == KNOWN_PRICE_MICROS


@pytest.mark.django_db
class TestShapeThreeARunningTotalThatWouldHaveGoneNull:
    """Tenant billing's accumulation — null propagation into a running total.

    `F("total_usage_cost_micros") + None` is not a Python error. It compiles to
    SQL, and SQL propagates `NULL` through addition, so one unpriced posting
    makes this `UPDATE` write `NULL` over a tenant's running period total.

    ⚠ **RUN WITH THE GUARD REMOVED, THE ASSERTION BELOW FAILS AS AN
    `IntegrityError`, NOT AS A NULL READ BACK** — the column is NOT NULL, so
    Postgres refuses the row. See the module docstring: that is a correction to
    the spec's characterisation of this shape, and it is recorded rather than
    smoothed over because the two failure modes send a reader to different
    places.

    **The guard is asserted at the accumulation and not at its caller**, which
    is what the AC asks for: there is one caller today, and a second added later
    would not know to repeat it.
    """

    def setup_method(self):
        self.tenant = Tenant.objects.create(
            name="T", products=["metering", "billing"], billing_mode="postpaid")

    def test_an_unresolved_price_leaves_the_running_total_a_number(self):
        TenantBillingService.accumulate_usage(self.tenant, KNOWN_PRICE_MICROS)
        TenantBillingService.accumulate_usage(self.tenant, None)
        period = TenantBillingPeriod.objects.get(tenant=self.tenant)
        assert period.total_usage_cost_micros is not None
        assert period.total_usage_cost_micros == KNOWN_PRICE_MICROS

    def test_the_event_is_still_counted_though_its_price_is_not_added(self):
        """⚠ WHY THIS COALESCES RATHER THAN RETURNING EARLY.

        The first draft of the repair skipped the whole `UPDATE` on a `None`,
        which fixed the null and quietly broke something else: the event count
        stopped moving. The event HAPPENED — what is absent is its price — so a
        period that dropped it would undercount its own traffic, and a reader
        dividing spend by events would get an answer wrong by exactly the
        postings UBB could not price.
        """
        TenantBillingService.accumulate_usage(self.tenant, KNOWN_PRICE_MICROS)
        TenantBillingService.accumulate_usage(self.tenant, None)
        period = TenantBillingPeriod.objects.get(tenant=self.tenant)
        assert period.event_count == 2
        assert period.total_usage_cost_micros == KNOWN_PRICE_MICROS

    def test_a_period_whose_first_posting_is_unpriced_still_opens(self):
        """The other half of what an early return broke.

        `get_or_create_current_period` sat below the guard, so a tenant whose
        first postings of the month were all unpriced would have had no open
        billing period at all — and the next priced posting would have opened
        one that silently began mid-month.
        """
        TenantBillingService.accumulate_usage(self.tenant, None)
        period = TenantBillingPeriod.objects.get(tenant=self.tenant)
        assert period.status == "open"
        assert period.total_usage_cost_micros == 0
        assert period.event_count == 1
