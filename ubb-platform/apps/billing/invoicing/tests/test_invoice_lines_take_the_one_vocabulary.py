"""Invoice lines under the one grouping vocabulary (#503, slice 7 §11).

**A tenant chooses how its invoice lines are grouped from the same discovery
contract every chart uses**, and the unbounded free-text key that drove the
labels is gone. The three claims that make that more than a rename all say the
same thing from different sides — **a customer's invoice depends on revenue
state only**:

* a fixed-price unit of work is ONE line, and the calls underneath it are
  `not_applicable`, so they produce none;
* a waived charge carries no liability, so it produces none either — and it is
  still reported, on the exposure surface that exists for exactly that;
* an unresolved SUPPLIER COST never delays, blocks or alters any of it.

⚠ **THE SEAM IS THE BILLING SERVICE AND NOT THE READ CONTRACT**, because what a
customer is charged for is what the service assembles: the read contract answers
in labels and amounts, and the decision that a label becomes a line is the
invoice's. The read contract's own tests (`apps/metering/tests/test_queries.py`)
cover the shapes this one composes.
"""
import datetime
import uuid

import pytest
from django.utils import timezone

from apps.billing.invoicing.models import PostpaidUsageConfig
from apps.billing.invoicing.services.postpaid_service import PostpaidUsageService
from apps.metering.pricing.models import Charge
from apps.metering.pricing.services.charge_projection import project_the_charge
from apps.metering.queries import get_waived_loss, grouping_axis
from apps.metering.usage.models import Posting
from apps.platform.customers.models import Customer
from apps.platform.event_types.models import EventCategory, EventType
from apps.platform.grouping_fields.services import DimensionService
from apps.platform.tenants.models import Tenant
from apps.platform.work.models import Task
from core.vocabulary import (
    ANALYTICS_GROUPING_KIND_FIELD,
    ANALYTICS_GROUPING_KIND_ROLLUP,
    ANALYTICS_ROLLUP_EVENT_CATEGORY,
    COSTING_METHOD_CALCULATED,
    COSTING_STATUS_KNOWN,
    COSTING_STATUS_UNRESOLVED,
    NOT_APPLICABLE_REASON_FIXED_TASK_PRICING,
    PRICING_STATUS_KNOWN,
    PRICING_STATUS_NOT_APPLICABLE,
    PRICING_STATUS_UNKNOWN,
    PRICING_STATUS_WAIVED,
    UNRESOLVED_REASON_COST_RATE_MISSING,
)

PS, PE = datetime.date(2026, 6, 1), datetime.date(2026, 7, 1)
MID = timezone.make_aware(timezone.datetime(2026, 6, 15))


def a_tenant():
    return Tenant.objects.create(name="T", billing_mode="postpaid",
                                 products=["metering", "billing"])


def a_posting(tenant, customer, key, **overrides):
    """A metered posting inside the period, priced and costed unless told
    otherwise. Every field this module varies is an override."""
    fields = {"tenant": tenant, "customer": customer, "idempotency_key": key,
              "effective_at": MID,
              "provider_cost_micros": 200_000,
              "costing_status": COSTING_STATUS_KNOWN,
              "billed_cost_micros": 500_000,
              "pricing_status": PRICING_STATUS_KNOWN}
    fields.update(overrides)
    return Posting.objects.create(**fields)


def grouped_by(tenant, axis):
    PostpaidUsageConfig.objects.create(tenant=tenant, invoice_line_grouping=axis)


def a_declared_field(tenant, key, slot="grouping_field_1", **kwargs):
    DimensionService.declare(tenant, key=key, slot=slot, scope="event", **kwargs)
    return grouping_axis(ANALYTICS_GROUPING_KIND_FIELD, key)


@pytest.mark.django_db
class TestTheAxisComesFromTheDiscoveryContract:
    """AC1 — the parameter accepts the field and rollup kinds, and nothing else."""

    def test_a_declared_field_labels_the_lines(self):
        tenant = a_tenant()
        customer = Customer.objects.create(tenant=tenant, external_id="c1")
        axis = a_declared_field(tenant, "region")
        grouped_by(tenant, axis)
        a_posting(tenant, customer, "i1", grouping_field_1="emea")
        a_posting(tenant, customer, "i2", grouping_field_1="apac",
                  billed_cost_micros=300_000)

        total, lines = PostpaidUsageService.aggregate_lines(
            tenant, customer, PS, PE)

        assert lines == [("emea", 500_000), ("apac", 300_000)]
        assert total == 800_000

    def test_a_rollup_labels_the_lines_by_their_heading(self):
        """ROLLUPS ARE ACTIVELY PREFERRED — fewer, more meaningful lines.

        Two Event Types filed under one category produce ONE line, which is the
        whole reason the invoice surface takes the rollup kind at all.
        """
        tenant = a_tenant()
        customer = Customer.objects.create(tenant=tenant, external_id="c1")
        category = EventCategory.objects.create(tenant=tenant, key="inference")
        for key in ("chat", "embed"):
            EventType.objects.create(tenant=tenant, key=key, category=category,
                                     costing_method=COSTING_METHOD_CALCULATED)
        EventType.objects.create(tenant=tenant, key="storage",
                                 costing_method=COSTING_METHOD_CALCULATED)
        grouped_by(tenant, grouping_axis(ANALYTICS_GROUPING_KIND_ROLLUP,
                                         ANALYTICS_ROLLUP_EVENT_CATEGORY))
        a_posting(tenant, customer, "i1", event_type="chat")
        a_posting(tenant, customer, "i2", event_type="embed",
                  billed_cost_micros=100_000)
        a_posting(tenant, customer, "i3", event_type="storage",
                  billed_cost_micros=70_000)

        _, lines = PostpaidUsageService.aggregate_lines(tenant, customer, PS, PE)

        # "storage" is filed under no heading, so it is an absence like any
        # other on an invoice: a line a reader can still be charged under.
        assert lines == [("inference", 600_000), ("(other)", 70_000)]

    def test_the_free_text_key_names_no_axis_at_all(self):
        """The hatch this replaces, refused rather than quietly re-read.

        `tag:<key>` used to read the free-form bag straight onto an invoice
        line. It names no axis the discovery contract publishes, and the read
        contract says so instead of falling through to a column nobody asked
        for.
        """
        tenant = a_tenant()
        customer = Customer.objects.create(tenant=tenant, external_id="c1")
        grouped_by(tenant, "tag:seat")
        a_posting(tenant, customer, "i1", metadata={"seat": "alice"})

        with pytest.raises(ValueError, match="grouping kind"):
            PostpaidUsageService.aggregate_lines(tenant, customer, PS, PE)


@pytest.mark.django_db
class TestAFixedPriceUnitOfWorkIsOneLine:
    """AC2 — one line labelled by that unit; its constituent calls produce none.

    ⚠ **THE TEST THAT WOULD FAIL IF THEY RENDERED AS ZERO** is the one below
    that counts the lines, not the one that reads the amount: rendering the
    constituents as zero-revenue lines leaves every amount correct and the
    invoice a hundred lines longer, which is the defect §11 names — *worse on an
    invoice than on a dashboard*.
    """

    def _a_fixed_price_unit(self, tenant, customer, *, constituents):
        task = Task.objects.create(tenant=tenant, customer=customer,
                                   task_type="summarise",
                                   balance_snapshot_micros=0)
        for index in range(constituents):
            # What #418 writes under a fixed-price unit: the call happened, the
            # supplier was paid, and the customer owes nothing FOR IT — the
            # unit's own price is the liability.
            a_posting(tenant, customer, f"call-{index}", task=task,
                      task_type="summarise",
                      billed_cost_micros=None,
                      pricing_status=PRICING_STATUS_NOT_APPLICABLE,
                      not_applicable_reason=NOT_APPLICABLE_REASON_FIXED_TASK_PRICING)
        charge = Charge.objects.create(
            tenant=tenant, task=task, amount_micros=2_500_000, currency="usd",
            agreed_price_line_id=uuid.uuid4(), book_version=1,
            resolved_at=MID, charged_at=MID, idempotency_key="charge-1")
        return project_the_charge(charge)

    def test_the_unit_is_one_line_and_its_calls_are_none(self):
        tenant = a_tenant()
        customer = Customer.objects.create(tenant=tenant, external_id="c1")
        grouped_by(tenant, grouping_axis(ANALYTICS_GROUPING_KIND_FIELD,
                                         "task_type"))
        self._a_fixed_price_unit(tenant, customer, constituents=3)

        total, lines = PostpaidUsageService.aggregate_lines(
            tenant, customer, PS, PE)

        assert lines == [("summarise", 2_500_000)]
        assert total == 2_500_000

    def test_a_hundred_calls_still_produce_a_one_line_invoice(self):
        """THE CLAIM AT THE SCALE THAT MAKES IT MATTER. Three constituents
        rendering as zero would look like a rounding detail; a hundred is the
        invoice §11 describes."""
        tenant = a_tenant()
        customer = Customer.objects.create(tenant=tenant, external_id="c1")
        grouped_by(tenant, grouping_axis(ANALYTICS_GROUPING_KIND_FIELD,
                                         "task_type"))
        self._a_fixed_price_unit(tenant, customer, constituents=100)

        _, lines = PostpaidUsageService.aggregate_lines(tenant, customer, PS, PE)

        assert len(lines) == 1

    def test_the_calls_are_present_and_it_is_their_STATE_that_excludes_them(self):
        """THE OTHER DIRECTION, without which the test above is satisfied by an
        exclusion that excluded everything.

        The same postings, differing only in the revenue state they carry, DO
        produce their own lines — so what keeps them off the invoice is the
        state and not the fact that they sit under a unit of work.
        """
        tenant = a_tenant()
        customer = Customer.objects.create(tenant=tenant, external_id="c1")
        grouped_by(tenant, grouping_axis(ANALYTICS_GROUPING_KIND_FIELD,
                                         "task_type"))
        task = Task.objects.create(tenant=tenant, customer=customer,
                                   task_type="metered", balance_snapshot_micros=0)
        a_posting(tenant, customer, "call-0", task=task, task_type="metered")

        _, lines = PostpaidUsageService.aggregate_lines(tenant, customer, PS, PE)

        assert lines == [("metered", 500_000)]


@pytest.mark.django_db
class TestAWaivedChargeProducesNoLineAndIsStillReported:
    """AC3 — no liability, so no line; and it must not vanish with the line."""

    def _a_waived_posting(self, tenant, customer):
        return a_posting(tenant, customer, "waived-1",
                         grouping_field_1="emea",
                         billed_cost_micros=None,
                         pricing_status=PRICING_STATUS_WAIVED)

    def test_a_waived_charge_produces_no_invoice_line(self):
        tenant = a_tenant()
        customer = Customer.objects.create(tenant=tenant, external_id="c1")
        grouped_by(tenant, a_declared_field(tenant, "region"))
        self._a_waived_posting(tenant, customer)

        total, lines = PostpaidUsageService.aggregate_lines(
            tenant, customer, PS, PE)

        assert lines == []
        assert total == 0

    def test_a_waived_charge_does_not_empty_the_line_beside_it(self):
        """The exclusion is per posting and not per label: a waived call and a
        charged one under the same heading leave the heading charged for what
        was charged."""
        tenant = a_tenant()
        customer = Customer.objects.create(tenant=tenant, external_id="c1")
        grouped_by(tenant, a_declared_field(tenant, "region"))
        self._a_waived_posting(tenant, customer)
        a_posting(tenant, customer, "i1", grouping_field_1="emea")

        _, lines = PostpaidUsageService.aggregate_lines(tenant, customer, PS, PE)

        assert lines == [("emea", 500_000)]

    def test_the_waived_charge_appears_on_the_exposure_report(self):
        """WHAT THE LINE'S ABSENCE MUST NOT COST. A waived charge is a decision
        with a real loss behind it — the supplier cost UBB paid with nothing
        charged for it — and the exposure surface is where a tenant sees it."""
        tenant = a_tenant()
        customer = Customer.objects.create(tenant=tenant, external_id="c1")
        grouped_by(tenant, a_declared_field(tenant, "region"))
        self._a_waived_posting(tenant, customer)

        _, lines = PostpaidUsageService.aggregate_lines(tenant, customer, PS, PE)
        exposure = get_waived_loss(tenant.id)

        assert lines == []
        # One row per currency, carrying what UBB paid the supplier for a call
        # nobody was charged for — which is what the loss IS, and why the
        # absence of an invoice line is not the absence of the fact.
        assert [(row["currency"], row["provider_cost_micros"],
                 row["waived_event_count"]) for row in exposure["rows"]] == [
            ("usd", 200_000, 1)]


@pytest.mark.django_db
class TestOnlyRevenueStateDecidesALine:
    """AC5 — an unresolved COST never delays, blocks or alters a line, and the
    unresolved REVENUE beside it is what the line's own count is for."""

    def test_an_unresolved_supplier_cost_leaves_the_line_exactly_as_it_was(self):
        tenant = a_tenant()
        customer = Customer.objects.create(tenant=tenant, external_id="c1")
        grouped_by(tenant, a_declared_field(tenant, "region"))
        a_posting(tenant, customer, "i1", grouping_field_1="emea",
                  provider_cost_micros=None,
                  costing_status=COSTING_STATUS_UNRESOLVED,
                  unresolved_reason=UNRESOLVED_REASON_COST_RATE_MISSING)

        total, lines = PostpaidUsageService.aggregate_lines(
            tenant, customer, PS, PE)

        assert lines == [("emea", 500_000)]
        assert total == 500_000

    def test_a_settled_cost_produces_the_identical_line(self):
        """THE OTHER DIRECTION, and it is what makes the first one evidence:
        the two answers are the same, so the cost state changed nothing."""
        tenant = a_tenant()
        customer = Customer.objects.create(tenant=tenant, external_id="c1")
        grouped_by(tenant, a_declared_field(tenant, "region"))
        a_posting(tenant, customer, "i1", grouping_field_1="emea")

        total, lines = PostpaidUsageService.aggregate_lines(
            tenant, customer, PS, PE)

        assert lines == [("emea", 500_000)]
        assert total == 500_000

    def test_an_unresolved_customer_price_is_what_the_lines_count_reports(self):
        """The REVENUE side, which does reach the invoice — as a floor that says
        so, per line, exactly as #351 built it."""
        tenant = a_tenant()
        customer = Customer.objects.create(tenant=tenant, external_id="c1")
        axis = a_declared_field(tenant, "region")
        a_posting(tenant, customer, "i1", grouping_field_1="emea")
        a_posting(tenant, customer, "i2", grouping_field_1="emea",
                  billed_cost_micros=None,
                  pricing_status=PRICING_STATUS_UNKNOWN)
        from apps.metering.queries import get_customer_billed_breakdown

        rows = get_customer_billed_breakdown(tenant.id, customer.id, PS, PE,
                                             axis)

        assert rows == [("emea", 500_000, 1)]
