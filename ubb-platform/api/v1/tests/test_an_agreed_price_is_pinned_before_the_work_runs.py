"""A unit of work sold at one agreed price resolves that price before it runs,
or is refused before it runs (#415, slice 5 §3/§9/§16).

The second half of the start gate: obligations 3, 8 and 9 of the nine, held
back from #410 because the price field did not exist until #414 declared the
regime.

Four claims, and they are independent of each other:

* **THE PRICE IS RESOLVED AND PINNED AT START**, out of the customer's own
  policy book, with no markup on top of it and no pricing method recorded
  against it — it was agreed, not derived. A later edit to the book cannot
  reach a number already pinned.
* **AN AGREED PRICE BUYS A WHOLE UNIT OF WORK.** A line written against a kind
  of work being started as CONTAINED work is refused loudly rather than
  ignored, and contained work never pins a price of its own.
* **A KIND OF WORK SOLD THAT WAY WITH NO RESOLVABLE PRICE REFUSES STARTS**, at
  the cheapest possible moment — before the work runs rather than after it
  delivered — for a tenant that bills through UBB. For one that does not, the
  declaration is recorded and INERT, and becomes live the day they enable
  billing.
* **REVENUE AND COGS RESOLVE AGAINST DIFFERENT INSTANTS, ON PURPOSE.** The
  price is pinned at start; every supplier cost goes on resolving at its own
  posting's timestamp, exactly as under any other regime. *The price was
  promised, the cost is observed.*

⚠ THE WIRE KEY FOR THE GROUPING BAG IS NEVER SPELLED HERE. It is retired
vocabulary under a spread ceiling another slice owns, so this module says what
it means through `declared_grouping_values`, whose own docstring records the
technique.

⚠ **THE PREPAID RESERVATION IS NOT BUILT AND THIS MODULE DOES NOT PRETEND
OTHERWISE.** §16's first obligation — take a durable reservation for the pinned
price, atomically with the write — did not land in #410 because there was no
price to take it against, and it is not this ticket's either: nothing in
`apps/billing/wallets` holds one, and building it means a release on all six
terminal paths. What the refusal case below asserts is therefore everything
money-shaped that DOES exist: no unit of work registered, no wallet movement,
and no grouping value burned. When a reservation exists, this is the case that
owes it an assertion.
"""
import json
import uuid
from datetime import timedelta

import pytest
from django.db import IntegrityError
from django.test import Client
from django.utils import timezone

from api.v1.tests.test_metering_endpoints import declared_grouping_values
from apps.billing.wallets.models import Wallet
from apps.metering.pricing.models import Rate, TaskPrice
from apps.metering.pricing.services.pricing_service import (
    AGREED_PRICE_ON_CONTAINED_WORK, AGREED_PRICE_UNRESOLVED,
)
from apps.metering.pricing.tests._helpers import (
    a_price_for_whole_work, cost_rate_in_default_book, declares_a_markup,
)
from apps.metering.usage.models import Posting
from apps.metering.usage.services.usage_service import UsageService
from apps.platform.customers.models import Customer
from apps.platform.grouping_fields.models import GroupingFieldValue
from apps.platform.grouping_fields.services import DimensionService
from apps.platform.tenants.models import Tenant, TenantApiKey
from apps.platform.work.models import Task, TaskType
from core.vocabulary import (
    PRICING_METHOD_DIRECT_EVENT_PRICE, PRICING_METHOD_MARGIN_OVER_COST,
    PRICING_METHOD_VALUES, PRICING_MODE_EVENT_PRICED, PRICING_MODE_FIXED,
    TASK_TYPE_KIND_SUBTASK, TASK_TYPE_KIND_TASK,
)

#: The kind of work this module sells at one agreed price, and the one it sells
#: per event — so every case can say which regime it is about by naming a word
#: rather than by configuring one.
SOLD_WHOLE = "transcode"
SOLD_PER_EVENT = "chat"
#: A second kind of work sold whole, at a DIFFERENT price, so that a repeat
#: naming the other one is a repeat naming another price.
ALSO_SOLD_WHOLE = "render"

THE_AGREED_PRICE = 8_000_000
THE_OTHER_AGREED_PRICE = 12_000_000
#: The tenant's markup rung, in micro-percent — a real quarter rather than
#: zero, because a rung of nothing would make a marked-up price EQUAL the
#: agreed one and every assertion about the pinned number satisfiable by the
#: wrong arithmetic (#364).
A_QUARTER = 25_000_000

#: A declared grouping key at the altitude a whole unit of work sits at, so the
#: refusal case can prove a refused start burns no cardinality.
A_GROUPING_KEY = "region"


class AgreedPriceTestBase:
    """One tenant that bills, one customer, and the start call under test.

    The posture is the BILLING one by default, because that is where the
    agreed-price refusals are live at all; the class whose subject is the
    metering-only posture builds its own tenant instead of switching this one,
    so a reader never has to hold two postures in mind at once.
    """

    PRODUCTS = ["metering", "billing"]
    BILLING_MODE = "prepaid"

    def setup_method(self):
        options = {"billing_mode": self.BILLING_MODE} if self.BILLING_MODE else {}
        self.tenant = Tenant.objects.create(
            name="T", products=self.PRODUCTS, **options)
        _, self.raw_key = TenantApiKey.create_key(self.tenant)
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="c1")
        self.client = Client()
        for key in (SOLD_WHOLE, ALSO_SOLD_WHOLE):
            for kind in (TASK_TYPE_KIND_TASK, TASK_TYPE_KIND_SUBTASK):
                TaskType.objects.create(tenant=self.tenant, key=key, kind=kind,
                                        pricing_mode=PRICING_MODE_FIXED)
        for kind in (TASK_TYPE_KIND_TASK, TASK_TYPE_KIND_SUBTASK):
            TaskType.objects.create(tenant=self.tenant, key=SOLD_PER_EVENT,
                                    kind=kind)
        if self.PRODUCTS != ["metering"]:
            Wallet.objects.create(customer=self.customer,
                                  balance_micros=1_000_000_000)

    def _auth(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {self.raw_key}"}

    def _start(self, **body):
        body.setdefault("customer_id", str(self.customer.id))
        body.setdefault("idempotency_key", f"attempt-{uuid.uuid4()}")
        return self.client.post(
            "/api/v1/tasks", data=json.dumps(body),
            content_type="application/json", **self._auth())

    def _price_is(self, amount, **where):
        return a_price_for_whole_work(
            self.tenant, task_type=SOLD_WHOLE, amount_micros=amount, **where)


@pytest.mark.django_db
class TestTheAgreedPriceIsResolvedAndPinned(AgreedPriceTestBase):
    """AC 1, 2 and 3 — where the number comes from, and what never touches it."""

    def test_a_start_pins_the_price_from_the_customers_book(self):
        self._price_is(THE_AGREED_PRICE)
        response = self._start(task_type=SOLD_WHOLE)
        assert response.status_code == 200
        assert response.json()["agreed_price_micros"] == THE_AGREED_PRICE
        registered = Task.objects.get(id=response.json()["task_id"])
        assert registered.agreed_price_micros == THE_AGREED_PRICE
        assert registered.pricing_mode == PRICING_MODE_FIXED

    def test_the_line_that_answered_is_pinned_beside_the_number(self):
        """#139 §2.3 — the amount must be *"reproducible from the record rather
        than by re-resolving today's config"*, and re-resolving is not
        available later on any terms: which books are even in play depends on
        the customer's plan, which moves. So the line's identity is captured in
        the same write as its number, and #416's Charge reads it rather than
        asking the book again.
        """
        line = self._price_is(THE_AGREED_PRICE)
        registered = Task.objects.get(
            id=self._start(task_type=SOLD_WHOLE).json()["task_id"])
        assert registered.agreed_price_line_id == line.id

    def test_the_number_and_its_line_cannot_come_apart(self):
        """The pair, at the database. A number with no line cannot be
        reproduced from the record; a line with no number would say a price was
        resolved and record none of it."""
        with pytest.raises(IntegrityError) as refused:
            Task.objects.create(
                tenant=self.tenant, customer=self.customer,
                balance_snapshot_micros=0, pricing_mode=PRICING_MODE_FIXED,
                agreed_price_micros=THE_AGREED_PRICE)
        assert "ck_task_agreed_price_and_its_line_move_together" in str(
            refused.value)

    def test_a_later_edit_to_the_book_does_not_move_the_pinned_number(self):
        """AC 1's second half, and the whole reason the number is a column
        rather than a lookup. A unit of work spanning a reprice keeps what it
        was quoted."""
        line = self._price_is(THE_AGREED_PRICE)
        registered_id = self._start(task_type=SOLD_WHOLE).json()["task_id"]

        TaskPrice.objects.filter(id=line.id).update(amount_micros=99_000_000)

        assert (Task.objects.get(id=registered_id).agreed_price_micros
                == THE_AGREED_PRICE)

    def test_markup_never_applies_to_a_pinned_price(self):
        """AC 2, against a tenant that HAS a markup rung configured.

        Markup is a function of provider cost alone, so applying it here would
        answer *the agreed price plus a percentage of this unit's COGS* — a
        number that moves with cost, which destroys the premise the tenant sold
        on. The rung is a real quarter rather than zero: at zero a marked-up
        price would equal the agreed one and this case would pass against the
        arithmetic it exists to refuse.
        """
        declares_a_markup(self.tenant, percentage_micros=A_QUARTER)
        self._price_is(THE_AGREED_PRICE)

        pinned = self._start(task_type=SOLD_WHOLE).json()["agreed_price_micros"]

        assert pinned == THE_AGREED_PRICE
        assert pinned != THE_AGREED_PRICE + THE_AGREED_PRICE // 4

    def test_no_third_pricing_method_is_coined_for_an_agreed_price(self):
        """AC 3 — the method stays NULL, and the value set is still two.

        A fixed price is not a third method: null already means *this price was
        not derived*, which is exactly what an agreed number is. The assertion
        compares the registry's set against the two GENERATED constants rather
        than against a literal pair, so what it says is *no third value was
        coined* rather than *two spellings agree* — and a value swapped for
        another reddens it, where a bare count of two would not.
        """
        assert set(PRICING_METHOD_VALUES) == {PRICING_METHOD_MARGIN_OVER_COST,
                                              PRICING_METHOD_DIRECT_EVENT_PRICE}
        assert not any(field.name == "pricing_method"
                       for field in TaskPrice._meta.get_fields())

    def test_a_kind_of_work_sold_per_event_pins_nothing(self):
        """THE CONTROL. Every case above asserts a pinned number, which a start
        gate that pinned one for everybody would satisfy — and that gate would
        put an agreed price on work nobody agreed a price for."""
        self._price_is(THE_AGREED_PRICE)
        response = self._start(task_type=SOLD_PER_EVENT)
        assert response.json()["agreed_price_micros"] is None
        assert Task.objects.get(
            id=response.json()["task_id"]).pricing_mode == PRICING_MODE_EVENT_PRICED

    def test_the_customers_own_book_outranks_the_book_selected_for_them(self):
        """The ladder, which has ONE key here where the rate side has three.

        A work-level line pins exactly one thing — the kind of work — so every
        candidate is equally specific and there is nothing for a specificity
        key to say. What is left is SOURCE, and it is what makes a negotiated
        price a negotiated price.
        """
        self._price_is(THE_AGREED_PRICE)
        self._price_is(THE_OTHER_AGREED_PRICE, customer=self.customer)

        assert (self._start(task_type=SOLD_WHOLE).json()["agreed_price_micros"]
                == THE_OTHER_AGREED_PRICE)

    def test_a_line_in_a_book_this_customer_cannot_reach_prices_nothing(self):
        """Selection happens before resolution: a line in a book nobody is on
        is unreachable however well it names the kind of work."""
        book_nobody_is_on = a_price_for_whole_work(
            self.tenant, task_type=SOLD_WHOLE,
            amount_micros=THE_AGREED_PRICE,
            customer=Customer.objects.create(tenant=self.tenant,
                                             external_id="somebody-else"))
        assert book_nobody_is_on.pricing_book.customer_id != self.customer.id

        assert self._start(task_type=SOLD_WHOLE).json()["code"] == (
            AGREED_PRICE_UNRESOLVED)


@pytest.mark.django_db
class TestAKindOfWorkSoldWholeWithNoPriceRefusesStarts(AgreedPriceTestBase):
    """AC 4 — the refusal, and what it costs a caller that meets it."""

    def test_the_start_is_refused_with_the_named_code(self):
        response = self._start(task_type=SOLD_WHOLE)
        assert response.status_code == 422
        assert response.json()["code"] == AGREED_PRICE_UNRESOLVED

    def test_the_refusal_lands_before_the_work_runs_and_spends_nothing(self):
        """AC 4's second half, asserted only where an assertion discriminates.

        ⚠ **A WALLET ASSERTION WOULD BE VACUOUS HERE AND IS DELIBERATELY
        ABSENT.** A start never debits a wallet — the prepaid reservation that
        would is §16's first obligation and is not built (see this module's
        header) — so *the balance did not move* holds identically on the
        SUCCESS path and would be satisfied by a refusal that never fired. The
        first draft asserted it; it is the shape #410 paid for, where a case
        was green against the exact mutation it existed for. What owes an
        assertion here is the reservation, on the day it exists.

        The grouping value is the one that bites: admitting a start's declared
        values is a WRITE against a key's cardinality cap and it runs ABOVE this
        refusal, so a refusal that returned instead of raising would burn
        keyspace permanently for work that never began (#324). The paired
        control below is what makes it evidence — the same value IS recorded
        when the start succeeds, so the absence is this refusal's doing rather
        than a bag that never reached the registry.
        """
        DimensionService.declare(self.tenant, key=A_GROUPING_KEY,
                                 slot="grouping_field_1", scope="task")

        refused = self._start(task_type=SOLD_WHOLE,
                              **declared_grouping_values({A_GROUPING_KEY: "eu"}))

        assert refused.status_code == 422
        assert Task.objects.count() == 0
        assert not GroupingFieldValue.objects.filter(value="eu").exists()

    def test_a_start_that_succeeds_does_record_that_grouping_value(self):
        """THE PAIRED CONTROL for the case above, and without it the assertion
        that nothing was recorded is a claim about a code path nobody proved
        runs at all."""
        DimensionService.declare(self.tenant, key=A_GROUPING_KEY,
                                 slot="grouping_field_1", scope="task")
        self._price_is(THE_AGREED_PRICE)

        allowed = self._start(task_type=SOLD_WHOLE,
                              **declared_grouping_values({A_GROUPING_KEY: "eu"}))

        assert allowed.status_code == 200
        assert GroupingFieldValue.objects.filter(value="eu").exists()

    def test_a_price_that_resolves_is_not_refused(self):
        """THE CONTROL: a refusal that fired whatever the book held would
        satisfy both cases above and would make the whole regime unusable."""
        self._price_is(THE_AGREED_PRICE)
        assert self._start(task_type=SOLD_WHOLE).status_code == 200

    def test_a_closed_line_no_longer_prices_a_start(self):
        """A line is retired by closing its window, not by deleting it — and a
        start after that instant resolves nothing, which is the same refusal as
        never having written one."""
        line = self._price_is(THE_AGREED_PRICE)
        TaskPrice.objects.filter(id=line.id).update(
            valid_to=timezone.now() - timedelta(minutes=1))

        assert self._start(task_type=SOLD_WHOLE).json()["code"] == (
            AGREED_PRICE_UNRESOLVED)


@pytest.mark.django_db
class TestAMeteringOnlyTenantsDeclarationIsRecordedAndInert(
        AgreedPriceTestBase):
    """The posture trap, which is a start-gate refusal in disguise (#151 §18).

    ⚠ **THIS IS THE CLASS NO GATE COULD SUBSTITUTE FOR.** Every gate in the
    repository stays green over a start gate that refuses a metering-only
    tenant's work for a pricing gap on revenue nobody collects — a *correct*
    declaration refused is indistinguishable from a wrong one, mechanically.
    What is asserted here is that the declaration costs them nothing today and
    starts costing them something the day they enable billing.
    """

    PRODUCTS = ["metering"]
    BILLING_MODE = None

    def test_a_kind_of_work_sold_whole_with_no_price_still_starts(self):
        response = self._start(task_type=SOLD_WHOLE)
        assert response.status_code == 200
        assert response.json()["agreed_price_micros"] is None

    def test_a_price_that_does_resolve_is_still_pinned_for_them(self):
        """Story 38 — *have that recorded even though I do not bill through
        UBB, so that my margin reporting knows what the revenue was.* Inert is
        about the REFUSAL, not about the record."""
        self._price_is(THE_AGREED_PRICE)
        assert (self._start(task_type=SOLD_WHOLE).json()["agreed_price_micros"]
                == THE_AGREED_PRICE)

    def test_enabling_billing_turns_the_declaration_into_a_refusal(self):
        """The trap, driven rather than described: the same call, the same
        book, the same declaration, refused because the posture moved."""
        assert self._start(task_type=SOLD_WHOLE).status_code == 200

        self.tenant.products = ["metering", "billing"]
        self.tenant.billing_mode = "prepaid"
        self.tenant.save(update_fields=["products", "billing_mode"])
        Wallet.objects.create(customer=self.customer,
                              balance_micros=1_000_000_000)

        refused = self._start(task_type=SOLD_WHOLE)
        assert refused.status_code == 422
        assert refused.json()["code"] == AGREED_PRICE_UNRESOLVED

    def test_the_contained_work_refusal_is_live_for_them_all_the_same(self):
        """⚠ THE OTHER HALF OF THE POSTURE SPLIT, AND WITHOUT THIS CASE
        POSTURE-CONDITIONING IT WOULD REDDEN NOTHING.

        Only the UNRESOLVED refusal is inert for a tenant that does not bill.
        A line written against contained work is a mistake in the tenant's own
        book whatever they bill, and #139 §3.3's whole objection to ignoring it
        is that the tenant is left with configuration that does nothing and
        springs to life later. So this refusal is unconditional, and the class
        above would go on passing if somebody made it conditional — which is
        what makes this case the one that holds the split.
        """
        self._price_is(THE_AGREED_PRICE)
        parent = self._start(task_type=SOLD_WHOLE).json()["task_id"]
        a_price_for_whole_work(self.tenant, task_type=ALSO_SOLD_WHOLE,
                               kind=TASK_TYPE_KIND_SUBTASK,
                               amount_micros=THE_OTHER_AGREED_PRICE)

        refused = self._start(parent_task_id=parent,
                              task_type=ALSO_SOLD_WHOLE)

        assert refused.status_code == 422
        assert refused.json()["code"] == AGREED_PRICE_ON_CONTAINED_WORK


@pytest.mark.django_db
class TestOneAgreedPriceBuysAWholeUnitOfWork(AgreedPriceTestBase):
    """AC 5 — a price on contained work is refused at start, loudly."""

    def _a_priced_parent(self):
        self._price_is(THE_AGREED_PRICE)
        return self._start(task_type=SOLD_WHOLE).json()["task_id"]

    def test_a_line_against_a_contained_kind_of_work_is_refused(self):
        """#139 §3.3 verbatim: *a fixed-price line on a SUBTASK TYPE is refused
        at start, loudly* — not ignored.

        The line here is written against the declaration meant for contained
        work, which is the deliberate misconfiguration the ruling names. Its
        rejected alternative was *allowed on both, parent wins*: the tenant
        would have configured something that silently does nothing, and
        removing the parent's own price later would spring the step price to
        life — a pricing change nobody made.
        """
        parent = self._a_priced_parent()
        a_price_for_whole_work(self.tenant, task_type=ALSO_SOLD_WHOLE,
                               kind=TASK_TYPE_KIND_SUBTASK,
                               amount_micros=THE_OTHER_AGREED_PRICE)

        refused = self._start(parent_task_id=parent,
                              task_type=ALSO_SOLD_WHOLE)

        assert refused.status_code == 422
        assert refused.json()["code"] == AGREED_PRICE_ON_CONTAINED_WORK
        assert Task.objects.filter(parent_id=parent).count() == 0

    def test_contained_work_under_a_priced_parent_pins_nothing(self):
        """THE CONTROL, and it is the case the refusal above must not eat. The
        parent is already the whole-work altitude and its rollup is
        unconditional, so contained work carries the regime and no price."""
        parent = self._a_priced_parent()

        contained = self._start(parent_task_id=parent,
                                task_type=ALSO_SOLD_WHOLE)

        assert contained.status_code == 200
        assert contained.json()["agreed_price_micros"] is None
        registered = Task.objects.get(id=contained.json()["task_id"])
        assert registered.pricing_mode == PRICING_MODE_FIXED
        assert registered.agreed_price_micros is None
        assert registered.agreed_price_line_id is None

    def test_a_priced_kind_of_work_can_run_as_a_step_of_itself(self):
        """THE SECOND CONTROL, and it is why the line names an ALTITUDE rather
        than a word.

        A render job containing render steps is an ordinary shape. If a line
        were keyed on the bare word, the refusal above would have to fire on
        any line naming it — so this call would be refused and the tenant told
        to *price the kind of work that contains this one*, which is exactly
        what they had done. The priced parent's own line is at the whole-work
        altitude and nothing prices the contained one, so the step is admitted
        and carries no price.
        """
        parent = self._a_priced_parent()

        contained = self._start(parent_task_id=parent, task_type=SOLD_WHOLE)

        assert contained.status_code == 200
        assert contained.json()["agreed_price_micros"] is None


@pytest.mark.django_db
class TestContainedWorkIsSoldTheWayItsContainerIs(AgreedPriceTestBase):
    """AC 6 at the surface — the sentence a caller actually receives.

    The database's own refusal, through every door, is
    `apps/platform/work/tests/test_containment_shares_the_pricing_regime.py`.
    What belongs here is that the caller is told which regime it contradicted
    rather than meeting an `IntegrityError`.
    """

    def test_a_differing_regime_is_refused_and_names_both(self):
        self._price_is(THE_AGREED_PRICE)
        parent = self._start(task_type=SOLD_WHOLE).json()["task_id"]

        refused = self._start(parent_task_id=parent,
                              task_type=SOLD_PER_EVENT)

        assert refused.status_code == 422
        body = refused.json()
        assert body["code"] == "task_pricing_mode_conflicts_with_parent"
        assert body["parent_pricing_mode"] == PRICING_MODE_FIXED
        assert body["pricing_mode"] == PRICING_MODE_EVENT_PRICED
        assert Task.objects.filter(parent_id=parent).count() == 0

    def test_a_matching_regime_is_admitted(self):
        parent = self._start(task_type=SOLD_PER_EVENT).json()["task_id"]
        contained = self._start(parent_task_id=parent,
                                task_type=SOLD_PER_EVENT)
        assert contained.status_code == 200


@pytest.mark.django_db
class TestThePinnedPriceSurvivesARepeat(AgreedPriceTestBase):
    """AC 7 — the resolved price is a pinned field.

    ⚠ **A CALLER NEVER STATES A PRICE, SO THERE IS NOTHING FOR A REPEAT TO
    CONTRADICT DIRECTLY.** The only way a repeat can mean a different price is
    by naming a different kind of work, which is what the conflict names — and
    re-resolving the price to compare it would be the re-derivation a
    permanently-claimed key exists to prevent, in its worst form: a tenant
    repricing their book would turn every in-flight retry into a conflict about
    a number the caller never sent.
    """

    def test_a_repeat_returns_the_original_price_after_a_reprice(self):
        self._price_is(THE_AGREED_PRICE)
        first = self._start(idempotency_key="k1", task_type=SOLD_WHOLE)

        TaskPrice.objects.filter(tenant=self.tenant).update(
            valid_to=timezone.now())
        self._price_is(THE_OTHER_AGREED_PRICE)

        again = self._start(idempotency_key="k1", task_type=SOLD_WHOLE)

        assert again.status_code == 200
        assert again.json()["replayed"] is True
        assert again.json()["task_id"] == first.json()["task_id"]
        assert again.json()["agreed_price_micros"] == THE_AGREED_PRICE

    def test_a_repeat_naming_a_differently_priced_kind_of_work_is_refused(self):
        """A differing kind of work IS a differing price, which is why a silent
        replay would charge one kind of work's price for another's."""
        self._price_is(THE_AGREED_PRICE)
        a_price_for_whole_work(self.tenant, task_type=ALSO_SOLD_WHOLE,
                               amount_micros=THE_OTHER_AGREED_PRICE)
        self._start(idempotency_key="k1", task_type=SOLD_WHOLE)

        refused = self._start(idempotency_key="k1", task_type=ALSO_SOLD_WHOLE)

        assert refused.status_code == 409
        assert refused.json()["code"] == "idempotency_key_conflict"
        assert refused.json()["field"] == "task_type"
        assert Task.objects.filter(
            agreed_price_micros=THE_OTHER_AGREED_PRICE).count() == 0


@pytest.mark.django_db
class TestRevenueAndCostResolveAgainstDifferentInstants(AgreedPriceTestBase):
    """AC 8 — the cost side is provably unchanged.

    *The price was promised; the cost is observed.* A unit of work's agreed
    price is determined ONCE, at start, and pinned; every supplier cost under it
    resolves at its OWN posting's timestamp against whatever rule was in force
    then. So one unit of work's revenue and its COGS resolve against different
    instants, which looks like a defect to anyone reading a single receipt
    without that sentence — which is why it is written at
    `apps/metering/pricing/receipts.py` and on the column that holds the number.

    ⚠ BOTH SIDES ARE REPRICED IN THIS FIXTURE, which is what makes the case
    discriminating: if the price floated it would move with the book, and if
    the cost were pinned both postings would cost the same. Only the asymmetry
    produces the four numbers asserted below.
    """

    QUANTITY = "prompt_tokens"
    ONE_CALL = 1_000_000
    COST_BEFORE = 4_000_000
    COST_AFTER = 9_000_000

    def _record(self, task_id, at):
        result = UsageService.record_usage(
            self.tenant, self.customer, f"call-{uuid.uuid4()}",
            event_type="chat", task_id=task_id,
            measurements={self.QUANTITY: self.ONE_CALL}, effective_at=at)
        return Posting.objects.get(id=result["event_id"])

    def test_costs_float_while_the_agreed_price_stays_at_the_start_instant(self):
        now = timezone.now()
        long_ago = now - timedelta(hours=3)
        cost_rate_in_default_book(
            self.tenant, measurement_key=self.QUANTITY,
            rate_per_unit_micros=self.COST_BEFORE, unit_quantity=self.ONE_CALL,
            valid_from=long_ago)
        self._price_is(THE_AGREED_PRICE, valid_from=long_ago)

        registered = self._start(task_type=SOLD_WHOLE).json()["task_id"]
        before = self._record(registered, now - timedelta(hours=2))

        # Both books move, at the same instant, in the same direction.
        boundary = now - timedelta(hours=1)
        Rate.objects.filter(tenant=self.tenant, cost_book__isnull=False,
                            valid_to__isnull=True).update(valid_to=boundary)
        cost_rate_in_default_book(
            self.tenant, measurement_key=self.QUANTITY,
            rate_per_unit_micros=self.COST_AFTER, unit_quantity=self.ONE_CALL,
            valid_from=boundary)
        TaskPrice.objects.filter(tenant=self.tenant).update(valid_to=boundary)
        self._price_is(THE_OTHER_AGREED_PRICE, valid_from=boundary)

        after = self._record(registered, now)

        assert before.provider_cost_micros == self.COST_BEFORE
        assert after.provider_cost_micros == self.COST_AFTER
        assert (Task.objects.get(id=registered).agreed_price_micros
                == THE_AGREED_PRICE)
