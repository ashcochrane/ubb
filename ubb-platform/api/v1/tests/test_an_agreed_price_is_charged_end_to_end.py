"""An agreed price, from its declaration to the delivered run's totals (#553,
the spec's end-to-end seam; A9's totals rule, ADR-0021 §3).

declare → plan → publish → read → start → deliver → exactly one Charge → one
Posting, for a tenant that bills through UBB and for one that does not — every
step through the tenant's own routes, and nothing written to a table. What it
holds at the end is the totals rule: the run's BILLED total includes its
Charge's posting, from the close that created it; its provider-cost total,
event count and unpriced count do not.

The forward-dating cases are here too, because what a start pins is the
seam's middle: a start before a dated reprice keeps the old price, a start
after it takes the new one, a run in flight across a reprice keeps its pin,
and a retired price refuses a billing tenant's start and leaves a metering-only
tenant's unpriced. So is the one write to a table, said at the write: an
archived Plan, which no route makes while anyone is on the Plan.

That the Charge's adjustment and its posting are one fact — never separately
durable, never applied twice — is pinned in
`api/v1/tests/test_a_charge_reaches_its_units_billed_total_once.py`.
"""
import uuid
from datetime import timedelta

import pytest
from django.utils import timezone

from api.v1.tests._helpers import PROVIDER, BlueprintRoutes, a_tenant
from apps.platform.plans.models import Plan
from core.vocabulary import USAGE_EVENT_KIND_TASK_CHARGE
from apps.platform.tenants.tests._rails import activate_the_rail

SOLD_WHOLE = "transcode"
PRICE = 8_000_000
NEW_PRICE = 9_500_000
#: One recorded call's supplier cost: the rate times the calls sent, so the
#: run's provider-cost total is a product a reader can check by hand.
RATE_PER_CALL = 250_000
CALLS = "2"
SUPPLIER_COST = 500_000
CALL_MEASUREMENT = {"display_name": "Calls", "value_type": "integer",
                    "unit": "call", "required_for_costing": True,
                    "source_kind": "caller_supplied", "source_path": []}
EVENT = "transcode.call"


class _TheSeam(BlueprintRoutes):
    """One kind of work sold at one agreed price, one Event Type its calls
    record, a cost rate for them, and a customer — declared through the
    routes. The posture is the subclass's."""

    PRODUCTS = ("metering",)
    BILLING_MODE = None

    def setup_method(self):
        # A money-mode tenant needs the payment rail activated first (G27);
        # asked for here, by name, before the tenant is built.
        activate_the_rail()
        super().setup_method()
        self.tenant, self.raw_key = a_tenant(products=self.PRODUCTS,
                                             billing_mode=self.BILLING_MODE)
        self._a_kind(SOLD_WHOLE, pricing_mode="fixed")
        self._event_type(EVENT, provider=PROVIDER,
                         measurements={"calls": CALL_MEASUREMENT})
        self._cost_rules(("add", "calls", RATE_PER_CALL))
        self.customer = self._a_customer()["id"]

    def _start(self):
        return self._call("post", "/api/v1/tasks", {
            "customer_id": self.customer, "task_type": SOLD_WHOLE,
            "idempotency_key": f"start-{uuid.uuid4()}"})

    def _record_a_call(self, task_id):
        return self._call("post", "/api/v1/metering/usage", {
            "customer_id": self.customer, "event_type": EVENT,
            "provider": PROVIDER,
            "idempotency_key": f"call-{uuid.uuid4()}", "task_id": task_id,
            "measurements": {"calls": CALLS}})

    def _deliver(self, task_id):
        return self._call("post", f"/api/v1/tasks/{task_id}/close",
                          {"outcome": "delivered"})

    def _postings_of(self, task_id):
        return self._call(
            "get", f"/api/v1/metering/customers/{self.customer}/usage"
                   f"?task_id={task_id}")["data"]

    # -- the seam ------------------------------------------------------------

    def test_a_declared_price_is_read_pinned_charged_once_and_billed(self):
        book = self._a_pricing_book()
        declared = self._call(
            "post", f"/api/v1/metering/pricing/books/{book['id']}/publishes",
            {"changes": [{"line": "agreed_price", "kind": "add",
                          "task_type": SOLD_WHOLE,
                          "agreed_price_micros": PRICE}]})
        (row,) = declared["diff"]
        assert row["after"] == {"agreed_price_micros": PRICE}
        published = self._call(
            "post", f"/api/v1/metering/pricing/books/{book['id']}/publishes/"
                    f"{declared['id']}/publish")
        (line,) = self._call(
            "get", f"/api/v1/metering/pricing/books/{book['id']}"
                   f"/agreed-prices")["data"]
        assert line["id"] == published["opened_agreed_price_ids"][0]
        assert line["agreed_price_micros"] == PRICE

        started = self._start()
        assert started["agreed_price_micros"] == PRICE
        self._record_a_call(started["task_id"])
        closed = self._deliver(started["task_id"])

        assert closed["charge_created"] is True
        # The billed total holds the Charge — the run's events carry no price
        # of their own under one agreed price.
        assert closed["total_billed_cost_micros"] == PRICE
        # And the totals the Charge never reaches.
        assert closed["total_provider_cost_micros"] == SUPPLIER_COST
        assert closed["recorded_events"] == 1
        assert closed["unpriced_event_count"] == 0
        # Exactly one Charge, as exactly one posting of the charge kind.
        charges = [posting for posting in self._postings_of(started["task_id"])
                   if posting["kind"] == USAGE_EVENT_KIND_TASK_CHARGE]
        assert [posting["billed_cost_micros"] for posting in charges] == [PRICE]
        # The run read back says the same as the close did.
        run = self._call("get", f"/api/v1/tasks/{started['task_id']}")
        assert run["total_billed_cost_micros"] == PRICE
        assert run["total_provider_cost_micros"] == SUPPLIER_COST
        assert run["recorded_events"] == 1

    def test_a_replayed_close_adds_nothing_to_the_billed_total(self):
        self._publish_agreed_price(SOLD_WHOLE, PRICE)
        started = self._start()
        self._deliver(started["task_id"])

        replayed = self._deliver(started["task_id"])

        assert replayed["replayed"] is True
        assert replayed["total_billed_cost_micros"] == PRICE

    # -- what a start pins, across the book's own dates ------------------------

    def test_a_start_before_a_dated_reprice_keeps_the_price_in_force(self):
        self._publish_agreed_price(SOLD_WHOLE, PRICE)
        self._publish_agreed_price(SOLD_WHOLE, NEW_PRICE, kind="reprice",
                                   effective_at=timezone.now()
                                   + timedelta(days=1))

        started = self._start()

        assert started["agreed_price_micros"] == PRICE
        assert self._deliver(started["task_id"])[
            "total_billed_cost_micros"] == PRICE

    def test_a_start_after_a_reprice_takes_the_new_price(self):
        # Dated a few minutes back, inside the clock-skew allowance a publish
        # admits, so the reprice is already in force when the start resolves.
        self._publish_agreed_price(SOLD_WHOLE, PRICE,
                                   effective_at=timezone.now()
                                   - timedelta(minutes=4))
        self._publish_agreed_price(SOLD_WHOLE, NEW_PRICE, kind="reprice",
                                   effective_at=timezone.now()
                                   - timedelta(minutes=2))

        assert self._start()["agreed_price_micros"] == NEW_PRICE

    def test_a_run_in_flight_across_a_reprice_keeps_its_pin(self):
        self._publish_agreed_price(SOLD_WHOLE, PRICE)
        in_flight = self._start()

        self._publish_agreed_price(SOLD_WHOLE, NEW_PRICE, kind="reprice")

        assert self._deliver(in_flight["task_id"])[
            "total_billed_cost_micros"] == PRICE
        assert self._start()["agreed_price_micros"] == NEW_PRICE


@pytest.mark.django_db
class TestTheSeamForATenantThatBillsThroughUbb(_TheSeam):
    PRODUCTS = ("metering", "billing")
    BILLING_MODE = "postpaid"

    def test_a_retired_price_refuses_the_next_start(self):
        self._publish_agreed_price(SOLD_WHOLE, PRICE)
        self._publish_agreed_price(SOLD_WHOLE, None, kind="retire")

        response = self._send("post", "/api/v1/tasks", {
            "customer_id": self.customer, "task_type": SOLD_WHOLE,
            "idempotency_key": "after-the-retirement"})

        assert response.status_code == 422, response.content
        assert response.json()["code"] == "fixed_task_price_unresolved"

    def test_an_archived_plans_price_reaches_neither_a_start_nor_readiness(
            self):
        """Readiness and the start enumerate the same books (owner's review
        of #615). A customer on a Plan is priced from its book — the control
        — and once the Plan is archived neither the start nor the Blueprint
        finds a price there."""
        self._publish_agreed_price(SOLD_WHOLE, PRICE,
                                   book=self._a_plans_book("pro"))
        self._call("post", "/api/v1/customers/acme/plan", {"plan_key": "pro"})
        assert self._start()["agreed_price_micros"] == PRICE
        assert self._resolve(task_type=SOLD_WHOLE, event_types=[EVENT])[
            "readiness"] == "complete"

        # Written to the row, as the selection's own pin does
        # (`apps/metering/pricing/tests/test_a_plan_names_the_book_it_prices_
        # from.py`): the route refuses to archive a Plan anyone is on, so this
        # holds a defence rather than a path a tenant can walk.
        Plan.objects.filter(tenant=self.tenant, key="pro").update(
            archived_at=timezone.now())

        refused = self._send("post", "/api/v1/tasks", {
            "customer_id": self.customer, "task_type": SOLD_WHOLE,
            "idempotency_key": "after-the-archival"})
        assert refused.status_code == 422, refused.content
        assert refused.json()["code"] == "fixed_task_price_unresolved"
        assert self._resolve(task_type=SOLD_WHOLE, event_types=[EVENT])[
            "readiness"] == "blocked"


@pytest.mark.django_db
class TestTheSeamForATenantThatMetersOnly(_TheSeam):
    """The same seam, for a tenant that collects elsewhere: the Pricing Book,
    the publish act and the read are theirs (ADR-0021 §4), the Charge is
    recorded for their own reporting, and the billed total holds it."""

    def test_a_retired_price_leaves_the_next_start_unpriced(self):
        self._publish_agreed_price(SOLD_WHOLE, PRICE)
        self._publish_agreed_price(SOLD_WHOLE, None, kind="retire")

        started = self._start()
        closed = self._deliver(started["task_id"])

        assert started["agreed_price_micros"] is None
        assert closed["charge_created"] is False
        assert closed["total_billed_cost_micros"] == 0
