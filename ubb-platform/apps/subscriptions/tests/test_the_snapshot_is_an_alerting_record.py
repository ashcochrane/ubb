"""The margin snapshot is DEMOTED, not deleted (#502, slice 7 §8).

**Margin is derived at read time from postings, Charges and revenue records. A
closed period's reported cost and margin move when its facts resolve.** What the
stored per-customer record keeps is the one job a derivation cannot do: remember
what the evaluator last alerted on, so a webhook fires once per transition and a
consecutive-periods rule has something to look back at.

So the claim is asked in BOTH directions, and either half alone would be
satisfied by a defect:

* **no reporting surface reads a margin figure from it** — a stored figure is a
  cache of facts that move, and a report reading one publishes a number UBB
  already knows is wrong;
* **the alerting reads remain** — severing the reporting reads without
  re-sourcing the two webhooks would turn a tenant's alerting off silently,
  which is the same defect wearing the opposite sign.

⚠ **The webhook spellings are read off the registry, never typed.** ADR-0008 §2:
where #153 and the registry disagree on a spelling the registry wins, and #153
§6.4 spells both of these with a prefix the registry retired in #154. Naming the
constants makes that impossible to get wrong here.

⚠ **The other half of this removal is #190's.** Slice 7 severed the reader; #190
deletes the rows. Neither is complete without the other, and only this half is in
#189 — so nothing in this module asserts that the table is empty.
"""
import ast
import datetime
from pathlib import Path

import pytest
from django.test import Client
from django.utils import timezone

from apps.metering.pricing.services.cost_settlement import settle_provider_cost
from apps.metering.pricing.services.price_resolution import (
    PriceResolution, resolve_customer_price)
from apps.metering.usage.models import BackfillDirtyPeriod, Posting
from apps.platform.customers.models import Customer
from apps.platform.events.models import OutboxEvent
from apps.platform.tenants.models import Tenant, TenantApiKey
from apps.subscriptions.economics.models import (
    CustomerCostAccumulator, CustomerEconomics, MarginThresholdConfig)
from apps.subscriptions.economics.services import MarginService
from apps.subscriptions.tasks import (
    RESNAPSHOT_MARKER_MIN_AGE, resnapshot_dirty_periods)
from core.vocabulary import (
    COSTING_STATUS_KNOWN, COSTING_STATUS_UNRESOLVED, PRICING_STATUS_UNKNOWN,
    RECOGNITION_METHOD_ON_RECEIPT, RECOGNITION_METHOD_STRAIGHT_LINE,
    UNRESOLVED_REASON_COST_RATE_MISSING,
    WEBHOOK_EVENT_TYPE_CUSTOMER_UNPROFITABLE,
    WEBHOOK_EVENT_TYPE_PROVIDER_COST_SPIKE)

# apps/subscriptions/tests/test_the_snapshot_is_an_alerting_record.py
# -> ubb-platform/
PLATFORM_ROOT = Path(__file__).resolve().parents[3]

#: Where production code lives. Tests name the record freely — they are what
#: drives it — and a migration names the table it is altering rather than
#: reading an answer out of it.
SEARCH_ROOTS = ("apps", "api", "core")
SKIP_PARTS = ("tests", "migrations")

#: EVERY PRODUCTION MODULE THAT MAY NAME THE ALERTING RECORD, and the one thing
#: each does with it. A role rather than a bare path, because "this file is
#: allowed" is what a reporting read would inherit if it landed in one of them:
#: a reader checking this map has to be able to say which of the four a new
#: reference would be.
#:
#: ⚠ **There is exactly ONE reading door, and that is the point of the map.**
#: Before this commit the evaluator and the alerting list each reached for the
#: record themselves, so nothing could tell an alerting read from a reporting
#: one — and the assertion below would have had to be a list of exceptions
#: rather than a claim.
THE_ALERTING_RECORDS_OWN_MODULES = {
    "apps/subscriptions/economics/models.py":
        "declares it",
    "apps/subscriptions/economics/alerting.py":
        "reads it — the one door onto what it remembers",
    "apps/subscriptions/economics/services.py":
        "maintains it — the monthly write and the evaluator that flags it",
    "apps/subscriptions/models.py":
        "re-exports it with the app's other models",
}

#: EVERY PRODUCTION MODULE THAT MAY READ THROUGH THE DOOR, and what it is doing
#: there. The map above would be satisfied by a reporting surface that imported
#: `state_of` and never named the record — the door re-publishes the very columns
#: it encloses, so widening WHO MAY WALK THROUGH IT has to be a line in a diff
#: too, or the seam is a formality.
THE_ALERTING_DOORS_CALLERS = {
    "apps/subscriptions/economics/services.py":
        "the evaluator — reads the state, the look-back and the period before",
    "apps/subscriptions/api/margin_endpoints.py":
        "the unprofitable list — the alerting surface #153 §8.3 keeps",
}

#: The cross-product read contract, named on its own because it is where a
#: reporting read of this record would live: other products and the API layer
#: read subscriptions through it and nowhere else. Two of its functions served
#: the snapshot's margin columns and are severed here.
THE_READ_CONTRACT = "apps/subscriptions/queries.py"

#: The door itself, as a dotted path, because that is how an importer spells it,
#: and as a repo path, because the door naturally mentions itself.
THE_ALERTING_DOOR = "apps.subscriptions.economics.alerting"
ALERTING_DOOR_PATH = "apps/subscriptions/economics/alerting.py"

#: What those two answered, and what answers it now. Spelled out so the
#: assertion below fails with the capability rather than with a name.
THE_SEVERED_READS = {
    "get_customer_economics":
        "one customer's stored margin row — now `customer_id=` as a filter on "
        "GET /metering/analytics/economics",
    "get_economics_summary":
        "the tenant-wide margin total off the stored margin columns — now the "
        "same query with no grouping and no bucket",
}


def _names_in(path: Path) -> set[str]:
    """Every identifier one module mentions, whatever it mentions it as.

    ⚠ **A DEFINITION IS A MENTION**, which is the case a walk like this quietly
    misses: the module that declares the record names it once, as a `ClassDef`,
    and a walk reading only uses would have left the declaration out of its own
    map and then read as if the map were arbitrary.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, (ast.ClassDef, ast.FunctionDef)):
            names.add(node.name)
        elif isinstance(node, ast.alias):
            names.add(node.name.rsplit(".", 1)[-1])
            if node.asname:
                names.add(node.asname)
    return names


def _imports_the_door(path: Path) -> bool:
    """Whether one module IMPORTS the alerting door, in either spelling.

    ⚠ **A SUBSTRING SEARCH IS WRONG IN BOTH DIRECTIONS HERE, AND THE FIRST DRAFT
    WAS.** It matched the read contract's TOMBSTONE, which names the door in
    prose to say where the record went — a mention, not a read — and it missed
    the evaluator, which spells the import `from apps.subscriptions.economics
    import alerting` and so never writes the dotted path at all. What is being
    asked is who can call through the door, which is a question about imports.
    """
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom):
            if node.module == THE_ALERTING_DOOR:
                return True
            if (node.module == THE_ALERTING_DOOR.rsplit(".", 1)[0]
                    and any(alias.name == "alerting" for alias in node.names)):
                return True
        elif isinstance(node, ast.Import):
            if any(alias.name == THE_ALERTING_DOOR for alias in node.names):
                return True
    return False


def _production_modules():
    for root in SEARCH_ROOTS:
        for path in sorted((PLATFORM_ROOT / root).rglob("*.py")):
            if any(part in SKIP_PARTS for part in path.parts):
                continue
            yield path.relative_to(PLATFORM_ROOT).as_posix(), path


class TestNoReportingSurfaceReadsAMarginFigureFromIt:
    """Direction one: the reporting reads are gone.

    A walk rather than a grep, and over the whole of production rather than over
    the subscriptions app: the surfaces that read this record for a margin were
    in three different products, and the next one will not announce itself
    either.
    """

    def test_only_the_alerting_modules_name_it(self):
        read = 0
        found = {}
        for relative, path in _production_modules():
            read += 1
            if "CustomerEconomics" in _names_in(path):
                found[relative] = path
        # The walk having happened is the vacuity guard: a `rglob` that matched
        # nothing would satisfy the claim below for free, and this repository
        # has shipped two gates that went quietly empty rather than red.
        assert read > 200, f"the walk only read {read} modules"
        assert sorted(found) == sorted(THE_ALERTING_RECORDS_OWN_MODULES), (
            "The margin snapshot is an ALERTING record. A module naming it is "
            "either one of the four that own it or a reporting read of a "
            "figure that moves after the period closes — ask "
            "GET /metering/analytics/economics instead. Roles: "
            f"{THE_ALERTING_RECORDS_OWN_MODULES}")

    def test_only_the_alerting_modules_walk_through_the_door(self):
        """The hole the map above leaves, closed at its own address.

        `alerting.py` hands back the record's margin columns as plain data. A
        reporting surface that imported `state_of` would therefore read a stored
        margin without ever naming `CustomerEconomics`, satisfy the walk above
        and be exactly the defect this module exists to refuse. So who imports
        the door is asked as well as who names the record.
        """
        found = {relative: path for relative, path in _production_modules()
                 if relative != ALERTING_DOOR_PATH and _imports_the_door(path)}
        assert sorted(found) == sorted(THE_ALERTING_DOORS_CALLERS), (
            "The alerting record's door hands back margin figures, so a module "
            "importing it is reading one. It is either an alerting surface or "
            "a report that should ask GET /metering/analytics/economics. "
            f"Roles: {THE_ALERTING_DOORS_CALLERS}")

    def test_the_read_contract_serves_nothing_off_it(self):
        """Said at its own address as well as by the walk above.

        The walk asks which modules NAME the record; this asks the module where
        a cross-product reporting read would live whether it still exports the
        two that served one. A function kept as a thin pass-through would pass
        one of these and not the other.
        """
        from apps.subscriptions import queries

        for gone, what_it_answered in THE_SEVERED_READS.items():
            assert not hasattr(queries, gone), (
                f"{THE_READ_CONTRACT}::{gone} answered {what_it_answered}")
        assert "CustomerEconomics" not in _names_in(
            PLATFORM_ROOT / THE_READ_CONTRACT)


@pytest.mark.django_db
class TestTheAlertingReadsRemain:
    """Direction two: both webhooks still fire, once per transition.

    Driven through `MarginService` rather than asserted about `alerting.py`
    directly — what a subscriber receives is the external behaviour, and a seam
    that emitted the right payload while the evaluator stopped calling it would
    satisfy a test of the seam.
    """

    @pytest.fixture(autouse=True)
    def fixture(self):
        self.tenant = Tenant.objects.create(name="Alerting",
                                            products=["metering"])
        self.customer = Customer.objects.create(tenant=self.tenant,
                                                external_id="c1")
        self.period_start = datetime.date(2026, 6, 1)
        self.period_end = datetime.date(2026, 7, 1)

    def _snapshot(self, *, cost, billed, period_start=None):
        period_start = period_start or self.period_start
        CustomerCostAccumulator.objects.create(
            tenant=self.tenant, customer=self.customer,
            period_start=period_start, period_end=self.period_end,
            total_provider_cost_micros=cost, total_billed_cost_micros=billed,
            event_count=1)
        return MarginService.snapshot_customer(
            self.tenant.id, self.customer.id, period_start, self.period_end)

    def _emitted(self, event_type):
        return OutboxEvent.objects.filter(event_type=event_type)

    def test_the_unprofitable_webhook_fires_once_per_transition(self):
        MarginThresholdConfig.objects.create(tenant=self.tenant,
                                             min_margin_pct=10)
        econ = self._snapshot(cost=950_000, billed=1_000_000)

        MarginService.evaluate_and_emit(econ)

        econ.refresh_from_db()
        assert econ.is_unprofitable is True
        emitted = self._emitted(WEBHOOK_EVENT_TYPE_CUSTOMER_UNPROFITABLE)
        assert emitted.count() == 1
        # The figures the alarm carries are the ALERTING record's own, which is
        # what "re-sourced from the alerting record" means: the tenant is told
        # the number the flag was raised on, not a number a report would give
        # for that period today.
        assert emitted.get().payload["gross_margin_micros"] == (
            econ.gross_margin_micros)
        assert emitted.get().payload["margin_pct"] == float(
            econ.margin_percentage)

        MarginService.evaluate_and_emit(econ)

        assert self._emitted(
            WEBHOOK_EVENT_TYPE_CUSTOMER_UNPROFITABLE).count() == 1

    def test_the_cost_spike_webhook_fires_once_per_transition(self):
        CustomerEconomics.objects.create(
            tenant=self.tenant, customer=self.customer,
            period_start=datetime.date(2026, 5, 1), period_end=self.period_start,
            usage_billed_micros=1_000_000, provider_cost_micros=100_000,
            gross_margin_micros=900_000, margin_percentage=90)
        econ = self._snapshot(cost=200_000, billed=1_000_000)

        MarginService.evaluate_and_emit(econ)

        emitted = self._emitted(WEBHOOK_EVENT_TYPE_PROVIDER_COST_SPIKE)
        assert emitted.count() == 1
        payload = emitted.get().payload
        # Both sides of the comparison come off the alerting record — the
        # previous period is the denominator and remembering it is the one
        # thing a read-time derivation cannot do for the evaluator.
        assert payload["prev_provider_cost_micros"] == 100_000
        assert payload["current_provider_cost_micros"] == 200_000

        MarginService.evaluate_and_emit(econ)

        assert self._emitted(
            WEBHOOK_EVENT_TYPE_PROVIDER_COST_SPIKE).count() == 1

    def test_the_unprofitable_list_still_answers_from_the_flag(self):
        """The alerting surface #153 §8.3 keeps, unchanged by the demotion.

        The discriminating case is the customer whose stored margin is healthy
        and whose flag is set: the list follows the FLAG, because the flag is
        what the tenant was sent a webhook about.
        """
        _, raw_key = TenantApiKey.create_key(self.tenant)
        flagged = self._snapshot(cost=1, billed=9_000_000)
        flagged.is_unprofitable = True
        flagged.save(update_fields=["is_unprofitable", "updated_at"])

        response = Client().get(
            f"/api/v1/margin/unprofitable?period_start={self.period_start}",
            HTTP_AUTHORIZATION=f"Bearer {raw_key}")

        assert response.status_code == 200, response.content
        listed = response.json()["customers"]
        assert [row["external_id"] for row in listed] == ["c1"]
        assert listed[0]["gross_margin_micros"] == flagged.gross_margin_micros

    def test_the_records_cost_column_cannot_be_unknown(self):
        """What makes the spike comparison safe, pinned where it is now used.

        The ratio divides by the previous period's supplier cost, so a `None`
        there would be a `TypeError` in the evaluator rather than a wrong
        number. The column is `NOT NULL` with a count beside it saying what the
        frozen total left out — and the evaluator declines to compare at all
        when that count is non-zero, because too small a denominator invents a
        spike rather than understating one.

        This claim used to sit beside the tenant-wide margin total, as the
        reason that total could sum the column without reporting a floor. That
        total is severed; the property is still load-bearing, so it moves here
        rather than leaving with its old reason.
        """
        for column in ("provider_cost_micros", "unresolved_event_count"):
            assert CustomerEconomics._meta.get_field(column).null is False


@pytest.mark.django_db
class TestTheCacheIsInvalidatableAtAnyAge:
    """AC 3: no age-bounded repair horizon is left acting as an authority.

    **Caches survive; authorities do not.** The hourly accumulator repair covers
    the current calendar month and the two before it — a horizon that was fine
    while it only had to catch drift, and that quietly became the thing deciding
    whether a figure was right. Compose it with a supplier cost resolved long
    after the fact and replayed at its original instant, and a period the
    evaluator has already flagged never hears that its cost changed.

    So the marker channel is what invalidates these two caches, and it is bound
    by nothing but the month having closed: a settlement writes one whatever its
    age, and consuming one repairs the accumulator from the posting ledger
    before re-snapshotting, so the three-month horizon is not in the path at
    all. Three causes write one marker — a cost settled late, a price resolved
    late, and a figure a tenant supplied about a month that closed — and each
    has its case below.

    ⚠ **ONE INPUT HAS NO MARKER AND CANNOT HAVE ONE, WHICH IS STATED RATHER THAN
    LEFT TO BE DISCOVERED.** `subscription_revenue_micros` comes from
    `RevenueService.accrued_subscription_revenue`, which is NOMINAL: it reads the
    mirrored subscription's amount and interval and never its dates, so the same
    row values every window it is ever asked about. Change the mirror and every
    month back to the beginning is re-valued — there is no bounded set of months
    to name, and a marker per subscription change would mean marking all of
    history.

    That is not a gap in the channel; it is the same argument §8 makes about
    cost, one step further. A figure with no per-period fact behind it should
    not be frozen into a per-period row at all, and the REPORTED subscription
    revenue already is not: it is derived at read time from the same row, so a
    tenant reading `GET /metering/analytics/economics` sees the mirror as it
    stands. What can go stale is the alerting record's copy, and what that costs
    is an alarm computed against a subscription amount that has since changed.
    **The rows are #190's**, and this is one of the reasons the cutover is the
    right place to decide what a period keeps.
    """

    @pytest.fixture(autouse=True)
    def fixture(self):
        self.tenant = Tenant.objects.create(name="Old news",
                                            products=["metering"])
        self.customer = Customer.objects.create(tenant=self.tenant,
                                                external_id="c1")
        today = timezone.now().date()
        opens = today.replace(day=1)
        # SIX MONTHS BACK — outside the repair horizon by three times over, so
        # the test cannot pass by accident on a month the hourly reconcile still
        # sweeps. Stepping month by month rather than subtracting days keeps it
        # on a calendar boundary whatever the day of the month is.
        for _ in range(6):
            opens = (opens - datetime.timedelta(days=1)).replace(day=1)
        self.closed_period = opens
        self.closes = (opens + datetime.timedelta(days=32)).replace(day=1)

    def _an_unresolved_posting(self, *, billed):
        return Posting.objects.create(
            tenant=self.tenant, customer=self.customer, idempotency_key="k1",
            event_type="chat.completion", billed_cost_micros=billed,
            provider_cost_micros=None,
            costing_status=COSTING_STATUS_UNRESOLVED,
            unresolved_reason=UNRESOLVED_REASON_COST_RATE_MISSING,
            effective_at=datetime.datetime(
                self.closed_period.year, self.closed_period.month, 15,
                12, tzinfo=datetime.timezone.utc))

    def _a_flagged_period(self, *, cost, billed, unresolved):
        CustomerCostAccumulator.objects.create(
            tenant=self.tenant, customer=self.customer,
            period_start=self.closed_period, period_end=self.closes,
            total_provider_cost_micros=cost, total_billed_cost_micros=billed,
            unresolved_event_count=unresolved, event_count=1)
        return MarginService.snapshot_customer(
            self.tenant.id, self.customer.id, self.closed_period, self.closes)

    def _consume_the_markers(self):
        """Run the hourly task over markers old enough to be consumed."""
        BackfillDirtyPeriod.objects.update(
            created_at=timezone.now() - RESNAPSHOT_MARKER_MIN_AGE
            - datetime.timedelta(hours=1))
        resnapshot_dirty_periods()

    def test_settling_a_cost_marks_its_closed_period_dirty(self):
        posting = self._an_unresolved_posting(billed=1_000_000)

        settle_provider_cost(posting_id=posting.pk,
                             provider_cost_micros=750_000)

        marker = BackfillDirtyPeriod.objects.get(
            tenant=self.tenant, customer=self.customer)
        assert marker.period_start == self.closed_period

    def test_the_alerting_record_moves_when_that_cost_resolves(self):
        """End to end, and the case the three-month horizon could not reach.

        The accumulator is left saying what it said when the cost was unknown —
        nothing hourly will repair a period this old — so the only way the
        figures below can move is the marker path repairing it from the ledger.
        """
        posting = self._an_unresolved_posting(billed=1_000_000)
        econ = self._a_flagged_period(cost=0, billed=1_000_000, unresolved=1)
        assert econ.provider_cost_micros == 0

        settle_provider_cost(posting_id=posting.pk,
                             provider_cost_micros=750_000)
        self._consume_the_markers()

        econ.refresh_from_db()
        assert econ.provider_cost_micros == 750_000
        assert econ.unresolved_event_count == 0
        assert econ.gross_margin_micros == 250_000
        assert BackfillDirtyPeriod.objects.count() == 0

    def test_a_price_resolving_late_marks_its_closed_period_too(self):
        """THE SYMMETRIC DOOR, and the one a review found uninstrumented.

        A customer price resolves through its own conditional update, exactly as
        a supplier cost settles through its own, and it moves the SAME cached
        figures — `usage_billed_micros`, and through it the margin the flag is
        raised on. Instrumenting the cost door alone leaves a cache repairable
        in one direction only.

        ⚠ AND THIS IS THE DIRECTION THAT CAN CLEAR AN ALARM. An excluded cost
        makes a margin a ceiling, an excluded price makes it a FLOOR — so the
        customer named unprofitable while a price was missing is the one who may
        have been fine all along.
        """
        posting = Posting.objects.create(
            tenant=self.tenant, customer=self.customer, idempotency_key="k2",
            event_type="chat.completion", provider_cost_micros=250_000,
            costing_status=COSTING_STATUS_KNOWN, billed_cost_micros=None,
            pricing_status=PRICING_STATUS_UNKNOWN,
            effective_at=datetime.datetime(
                self.closed_period.year, self.closed_period.month, 15, 12,
                tzinfo=datetime.timezone.utc))
        econ = self._a_flagged_period(cost=250_000, billed=0, unresolved=0)
        assert econ.gross_margin_micros == -250_000

        assert resolve_customer_price(
            posting_id=posting.pk,
            billed_cost_micros=1_000_000) is PriceResolution.RESOLVED
        self._consume_the_markers()

        econ.refresh_from_db()
        assert econ.usage_billed_micros == 1_000_000
        assert econ.gross_margin_micros == 750_000

    def test_a_supplied_span_marks_every_closed_month_it_touches(self):
        """A record is ONE row and may be several months (#502).

        The margin surfaces read supplied revenue under the recognised basis, so
        a spreading method puts part of a quarter's amount in each of its three
        months. Marking only the month the span opens in would leave the other
        two stale at any age — the defect the marker channel exists to prevent,
        arriving through the channel itself.
        """
        _, raw_key = TenantApiKey.create_key(self.tenant)
        opens = self.closed_period
        closes = self.closes
        for _ in range(2):
            closes = (closes + datetime.timedelta(days=32)).replace(day=1)

        response = Client().post(
            f"/api/v1/margin/customers/{self.customer.id}/supplied-revenue",
            data={"amount_micros": 3_000_000, "currency": "usd",
                  "period_start": opens.isoformat(),
                  "period_end": closes.isoformat(),
                  "recognition_method": RECOGNITION_METHOD_STRAIGHT_LINE,
                  "source_reference": "INV-QUARTER-1"},
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {raw_key}")

        assert response.status_code == 200, response.content
        marked = set(BackfillDirtyPeriod.objects.filter(
            tenant=self.tenant, customer=self.customer
        ).values_list("period_start", flat=True))
        # All three months of the span, and the span's exclusive end does not
        # reach into the month it lands on.
        month, expected = opens, set()
        while month < closes:
            expected.add(month)
            month = (month + datetime.timedelta(days=32)).replace(day=1)
        assert len(expected) == 3
        assert marked == expected

    def test_a_figure_the_tenant_supplies_late_marks_its_period_too(self):
        """The other input, and it is not a posting at all.

        A tenant that bills its customers elsewhere states what it earned, and
        it may state it about a month that closed long ago. Revenue is half of
        every margin the evaluator flags on, so a supplied figure that could not
        reach a closed period would leave the alarm standing on the half of the
        answer UBB happened to have first.
        """
        _, raw_key = TenantApiKey.create_key(self.tenant)
        self._a_flagged_period(cost=500_000, billed=0, unresolved=0)

        response = Client().post(
            f"/api/v1/margin/customers/{self.customer.id}/supplied-revenue",
            data={"amount_micros": 2_000_000, "currency": "usd",
                  "period_start": self.closed_period.isoformat(),
                  "recognition_method": RECOGNITION_METHOD_ON_RECEIPT,
                  "source_reference": "INV-LATE-1"},
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {raw_key}")

        assert response.status_code == 200, response.content
        marker = BackfillDirtyPeriod.objects.get(
            tenant=self.tenant, customer=self.customer)
        assert marker.period_start == self.closed_period

        self._consume_the_markers()

        econ = CustomerEconomics.objects.get(
            tenant=self.tenant, customer=self.customer,
            period_start=self.closed_period)
        assert econ.supplied_revenue_micros == 2_000_000
