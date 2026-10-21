"""A kind of work sold at one agreed price, through the Code Builder (#586, with
the owner's readiness ruling of 2026-10-20 on #553 and its clarification the
same day — comments 6279555404 and 6279967254).

A Blueprint is CUSTOMER-INDEPENDENT. Whether a start of a fixed-price kind can
find a price is a property of the tenant's PUBLISHED pricing configuration —
the default Pricing Book, every live Plan's book and each customer's own book —
and never of a runtime customer, how many customers there are or which Plan
any of them is on:

* a tenant that bills through UBB is BLOCKED only when no such book holds an
  agreed price in force for the kind (a start would be refused for every
  customer); one price anywhere makes the call complete;
* a tenant that meters without billing is never blocked by a missing price,
  because nothing refuses its start;
* whenever the DEFAULT book holds none, either posture is told so by an
  advisory — a customer with no price of their own or from their Plan is
  refused at start where UBB bills, and has no authoritative revenue figure
  where it does not.

The snapshot keeps the default book's price, which Verify materialises, and
the one tenant-level outcome; no customer, no Plan and no other book's amount.

**Everything goes through the tenant's own routes**, as the Blueprint's own
suite does: kinds, Event Types, books, prices, customers and Plans are declared
the way a tenant declares them, and every assertion is over a response or over
the snapshot the resolution stored. The one write to a row is said at the
write.
"""
import json
from datetime import timedelta

import pytest
from django.test import Client
from django.utils import timezone

from apps.platform.code_builder.models import BlueprintSnapshot

from ._helpers import EVENT, PROVIDER, BlueprintRoutes, a_tenant

START = "api_v1_task_endpoints_start_task"

#: The kind of work sold whole, and the prices each book holds for it — three
#: different figures, so finding one in the snapshot says which book it came
#: from.
SOLD_WHOLE = "transcode"
THE_DEFAULT_PRICE = 8_000_000
A_CUSTOMERS_PRICE = 6_543_210
A_PLANS_PRICE = 7_123_456

#: The three codes this module is about.
MISSING = "agreed_price_missing"
REFUSED_AT_START = "default_agreed_price_missing_refused_at_start"
NO_REVENUE_FIGURE = "default_agreed_price_missing_no_revenue_figure"

THE_SAMPLE = {"input_tokens": "100"}


class _Routes(BlueprintRoutes):
    """A tenant in the posture `BILLS` names, with one kind of work sold at
    one agreed price and one published Event Type to record inside it."""

    BILLS = True

    def setup_method(self):
        self.tenant, self.raw_key = (
            a_tenant(products=("metering", "billing"), billing_mode="postpaid")
            if self.BILLS else a_tenant())
        self.client = Client()
        self._kinds({"key": SOLD_WHOLE, "pricing_mode": "fixed",
                     "uncapped": True})
        self._event_type(provider=PROVIDER)

    # -- reading what was resolved ------------------------------------------

    def _resolved(self, **selection):
        selection.setdefault("task_type", SOLD_WHOLE)
        selection.setdefault("event_types", [EVENT])
        return self._resolve(**selection)

    def _the_start(self, blueprint):
        (start,) = [call for call in blueprint["calls"]
                    if call["operation_id"] == START]
        return start

    def _about_the_price(self, blueprint):
        """Each diagnostic reported over the agreed price, as
        `(severity, code, object, key, field, request)`."""
        return [(d["severity"], d["code"], d["object_kind"], d["key"],
                 d["field"], d["remediation_request"])
                for d in blueprint["diagnostics"]
                if d["object_kind"] == "agreed_price"]

    def _stored(self, blueprint):
        return BlueprintSnapshot.objects.get(
            tenant=self.tenant,
            configuration_fingerprint=blueprint["configuration_fingerprint"],
        ).content

    def _kept(self, blueprint):
        """What the snapshot keeps of the kind's agreed price."""
        return self._stored(blueprint)["identity"]["configuration"][
            "agreed_price"]

    # -- the books a price may sit in ----------------------------------------

    def _a_price_in_the_default_book(self, amount=THE_DEFAULT_PRICE, **when):
        return self._publish_agreed_price(SOLD_WHOLE, amount, **when)

    def _a_price_in_a_customers_own_book(self, amount=A_CUSTOMERS_PRICE,
                                         external_id="acme"):
        customer = self._a_customer(external_id)
        book = self._the_customers_own_book(customer["id"])
        self._publish_agreed_price(SOLD_WHOLE, amount, book=book)
        return customer, book

    def _a_price_in_a_plans_book(self, amount=A_PLANS_PRICE, plan_key="pro"):
        book = self._a_plans_book(plan_key)
        self._publish_agreed_price(SOLD_WHOLE, amount, book=book)
        return book

    def _a_plan_on_a_tenant_that_no_longer_bills(self, amount=A_PLANS_PRICE):
        """A Plan with a price in its book, on a tenant that meters without
        billing. Plans are a billing route, so the Plan is made while the
        tenant bills and billing is then turned off — through the tenant
        row's own `save`, which validates the posture and clears the cached
        product list: no route in this module's reach turns a product off."""
        self.tenant.products = ["metering", "billing"]
        self.tenant.save()
        book = self._a_price_in_a_plans_book(amount)
        self.tenant.products = ["metering"]
        self.tenant.save()
        return book


# ---------------------------------------------------------------------------
# A tenant that bills through UBB
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestATenantThatBillsIsBlockedOnlyWhereNoBookHoldsAPrice(_Routes):

    def test_no_price_in_any_book_blocks_the_start_and_names_what_is_missing(
            self):
        blueprint = self._resolved()

        assert blueprint["readiness"] == "blocked"
        assert self._the_start(blueprint)["readiness"] == "blocked"
        # The blocking diagnostic names the object and the field, and links
        # to the console's Pricing Books rather than offering a request: the
        # Pricing Book editor is where an agreed price is declared (Seam D).
        assert self._about_the_price(blueprint) == [
            ("blocking", MISSING, "agreed_price", SOLD_WHOLE,
             "agreed_price_micros", None),
            ("advisory", REFUSED_AT_START, "agreed_price", SOLD_WHOLE,
             "agreed_price_micros", None)]
        # Nothing else lowers it: the start is blocked by the price alone.
        assert [d["code"] for d in blueprint["diagnostics"]
                if d["severity"] == "blocking"] == [MISSING]

    def test_a_price_only_in_a_customers_own_book_completes_it_with_the_advisory(
            self):
        self._a_price_in_a_customers_own_book()

        blueprint = self._resolved()

        assert blueprint["readiness"] == "complete"
        assert self._about_the_price(blueprint) == [
            ("advisory", REFUSED_AT_START, "agreed_price", SOLD_WHOLE,
             "agreed_price_micros", None)]

    def test_a_price_only_in_a_plans_book_completes_it_though_nobody_is_on_the_plan(
            self):
        """A Plan's book counts whether or not any customer is on the Plan:
        Plan assignments are never read."""
        self._a_price_in_a_plans_book()

        blueprint = self._resolved()

        assert blueprint["readiness"] == "complete"
        assert self._about_the_price(blueprint) == [
            ("advisory", REFUSED_AT_START, "agreed_price", SOLD_WHOLE,
             "agreed_price_micros", None)]

    def test_a_price_only_in_an_archived_plans_book_is_no_price(self):
        """An archived Plan prices nobody — a start never reaches its book —
        so a price there is one no start can find."""
        self._a_price_in_a_plans_book()
        self._call("delete", "/api/v1/plans/pro")

        assert self._resolved()["readiness"] == "blocked"

    def test_a_price_in_the_default_book_completes_it_with_no_advisory(self):
        published = self._a_price_in_the_default_book()

        blueprint = self._resolved()

        assert blueprint["readiness"] == "complete"
        assert self._about_the_price(blueprint) == []
        # The price and where it came from are the DEFAULT book's.
        # Its provenance is the book, the version the publish made it and the
        # instant it opened — as the book and its agreed-prices read say.
        assert self._kept(blueprint) == {
            "has_any_effective_runtime_agreed_price": True,
            "default_book_agreed_price": {
                "book_key": "catalogue",
                "agreed_price_micros": THE_DEFAULT_PRICE,
                "book_version_from": self._a_pricing_book()["version"],
                "valid_from": self._the_line_published(published)[
                    "valid_from"],
                "valid_to": None}}

    def test_the_kept_price_is_the_default_books_when_others_hold_one_too(self):
        self._a_price_in_a_customers_own_book()
        self._a_price_in_a_plans_book()
        self._a_price_in_the_default_book()

        kept = self._kept(self._resolved())

        assert kept["default_book_agreed_price"]["agreed_price_micros"] == (
            THE_DEFAULT_PRICE)

    def test_a_price_dated_to_open_later_is_no_price_now(self):
        self._a_price_in_the_default_book(
            effective_at=timezone.now() + timedelta(days=7))

        blueprint = self._resolved()

        assert blueprint["readiness"] == "blocked"
        assert [code for _, code, *_ in self._about_the_price(blueprint)] == [
            MISSING, REFUSED_AT_START]
        assert self._kept(blueprint) == {
            "has_any_effective_runtime_agreed_price": False,
            "default_book_agreed_price": None}

    def test_a_retired_price_is_no_price(self):
        self._a_price_in_the_default_book()
        self._publish_agreed_price(SOLD_WHOLE, None, kind="retire")

        assert self._resolved()["readiness"] == "blocked"

    def _the_line_published(self, published):
        (line_id,) = published["opened_agreed_price_ids"]
        book = self._a_pricing_book()
        lines = self._call(
            "get", f"/api/v1/metering/pricing/books/{book['id']}/"
                   f"agreed-prices?include_history=true")["data"]
        (line,) = [line for line in lines if line["id"] == line_id]
        return line


# ---------------------------------------------------------------------------
# A tenant that meters without billing
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestATenantThatMetersWithoutBillingIsNeverBlockedByAPrice(_Routes):
    BILLS = False

    def test_no_price_anywhere_is_complete_with_the_advisory(self):
        blueprint = self._resolved()

        assert blueprint["readiness"] == "complete"
        assert self._about_the_price(blueprint) == [
            ("advisory", NO_REVENUE_FIGURE, "agreed_price", SOLD_WHOLE,
             "agreed_price_micros", None)]
        assert self._kept(blueprint) == {
            "has_any_effective_runtime_agreed_price": False,
            "default_book_agreed_price": None}

    def test_a_price_only_in_a_customers_own_book_keeps_the_same_advisory(self):
        """Symmetric with billing: the advisory is about the DEFAULT path, so
        a customer's own price does not silence it."""
        self._a_price_in_a_customers_own_book()

        blueprint = self._resolved()

        assert blueprint["readiness"] == "complete"
        assert self._about_the_price(blueprint) == [
            ("advisory", NO_REVENUE_FIGURE, "agreed_price", SOLD_WHOLE,
             "agreed_price_micros", None)]
        assert self._kept(blueprint)[
            "has_any_effective_runtime_agreed_price"] is True

    def test_a_price_only_in_a_plans_book_keeps_the_same_advisory(self):
        self._a_plan_on_a_tenant_that_no_longer_bills()

        blueprint = self._resolved()

        assert blueprint["readiness"] == "complete"
        assert [code for _, code, *_ in self._about_the_price(blueprint)] == [
            NO_REVENUE_FIGURE]
        assert self._kept(blueprint)[
            "has_any_effective_runtime_agreed_price"] is True

    def test_a_price_in_the_default_book_is_complete_with_no_advisory(self):
        self._a_price_in_the_default_book()

        blueprint = self._resolved()

        assert blueprint["readiness"] == "complete"
        assert self._about_the_price(blueprint) == []
        assert self._kept(blueprint)["default_book_agreed_price"][
            "agreed_price_micros"] == THE_DEFAULT_PRICE


# ---------------------------------------------------------------------------
# Only what is the same for every customer reaches the snapshot
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestTheBlueprintIsTheSameWhoeverTheCustomersAre(_Routes):

    def test_no_customers_and_several_give_the_same_blueprint(self):
        """Zero customers, then three — two on the Plan and one off it: the
        readiness, the diagnostics and the fingerprint are what they were,
        and there is still one snapshot."""
        self._a_price_in_a_plans_book()
        alone = self._resolved()

        for external_id in ("c1", "c2", "c3"):
            self._a_customer(external_id)
        for external_id in ("c1", "c2"):
            self._call("post", f"/api/v1/customers/{external_id}/plan",
                       {"plan_key": "pro"})
        crowded = self._resolved()

        assert crowded == alone
        assert BlueprintSnapshot.objects.filter(tenant=self.tenant).count() == 1

    def test_no_customer_plan_or_other_books_amount_is_in_the_snapshot(self):
        customer, own_book = self._a_price_in_a_customers_own_book()
        plans_book = self._a_price_in_a_plans_book()
        self._call("post", f"/api/v1/customers/{customer['external_id']}/plan",
                   {"plan_key": "pro"})
        self._a_price_in_the_default_book()
        plan = self._call("get", "/api/v1/plans/pro")

        blueprint = self._resolved()

        text = json.dumps(self._stored(blueprint))
        for absent in (customer["id"], customer["external_id"], plan["id"],
                       own_book["id"], plans_book["id"],
                       str(A_CUSTOMERS_PRICE), str(A_PLANS_PRICE)):
            assert absent not in text, absent
        # The control: the default book's price IS kept.
        assert str(THE_DEFAULT_PRICE) in text


# ---------------------------------------------------------------------------
# What moves the fingerprint (B3)
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestTheFingerprintMovesWithTheOutcomeAndTheDefaultPriceOnly(_Routes):

    def _fingerprint(self):
        return self._resolved()["configuration_fingerprint"]

    def test_repricing_a_customers_own_book_leaves_it_where_it_was(self):
        _, book = self._a_price_in_a_customers_own_book()
        before = self._fingerprint()

        self._publish_agreed_price(SOLD_WHOLE, A_CUSTOMERS_PRICE + 1,
                                   book=book, kind="reprice")

        assert self._fingerprint() == before

    def test_repricing_a_plans_book_leaves_it_where_it_was(self):
        book = self._a_price_in_a_plans_book()
        before = self._fingerprint()

        self._publish_agreed_price(SOLD_WHOLE, A_PLANS_PRICE + 1, book=book,
                                   kind="reprice")

        assert self._fingerprint() == before

    def test_the_first_price_moves_it_and_retiring_the_last_moves_it_back(
            self):
        """Blocked to complete and back, with the price only ever in one
        customer's own book — whose amount is in no snapshot. The outcome is
        what moved, so retiring the price is the blocked Blueprint again."""
        blocked = self._fingerprint()
        _, book = self._a_price_in_a_customers_own_book()
        complete = self._fingerprint()

        self._publish_agreed_price(SOLD_WHOLE, None, book=book, kind="retire")

        assert complete != blocked
        assert self._fingerprint() == blocked

    def test_repricing_the_default_book_moves_it(self):
        self._a_price_in_the_default_book()
        before = self._fingerprint()

        self._publish_agreed_price(SOLD_WHOLE, THE_DEFAULT_PRICE + 1,
                                   kind="reprice")

        assert self._fingerprint() != before


# ---------------------------------------------------------------------------
# Verify materialises the default book's price, and only that (B4)
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestVerifyRunsWithTheDefaultBooksPriceAndPicksNoOther(_Routes):

    def _verified(self):
        fingerprint = self._resolved()["configuration_fingerprint"]
        response = self._send(
            "post", f"/api/v1/code-builder/blueprints/{fingerprint}/verify",
            {"records": [{"event_type": EVENT, "measurements": THE_SAMPLE}],
             "grouping_fields": {}})
        assert response.status_code == 200, response.content
        return response.json()

    def test_a_default_price_is_what_the_run_is_charged(self):
        self._cost_rules(("add", "input_tokens", 3))
        self._a_price_in_the_default_book()

        body = self._verified()

        assert body["refusal"] is None
        assert body["verified"] is True
        close = body["task"]["close"]
        assert close["outcome"] == "delivered"
        # The run's billed total is the Charge: the price and nothing else,
        # because the events of a kind sold whole carry no price of their own.
        assert close["total_billed_cost_micros"] == THE_DEFAULT_PRICE

    def test_a_price_only_in_a_customers_own_book_is_refused_at_start(self):
        """The Blueprint is complete — a customer path exists — and its
        advisory said a customer with no price of their own is refused. The
        run's customer is that customer: Verify surfaces the real refusal,
        and neither picks the priced book nor makes a price up."""
        self._cost_rules(("add", "input_tokens", 3))
        self._a_price_in_a_customers_own_book()

        body = self._verified()

        assert body["verified"] is False
        assert body["refusal"]["operation_id"] == START
        assert body["refusal"]["problem"]["code"] == (
            "fixed_task_price_unresolved")
        assert body["task"] == {"task_type": SOLD_WHOLE, "start": None,
                                "close": None}
        assert body["records"] == []
