"""A delivered unit of work sold at one agreed price produces exactly one
Charge, ever — and nothing else in the lifecycle produces one at all (#416,
slice 5 §5/§11).

#415 pinned the agreed price at start and said in its own commit that a
delivered unit of work sold that way still produced nothing. This is the half
that produces it.

Five claims, and each is independent of the others:

* **ONE CLOSE DECLARING DELIVERY EARNS ONE CHARGE, AND A SECOND IDENTICAL CLOSE
  EARNS NOTHING.** The charge fires on the WINNING transition into the
  delivered state, which is the exactly-once trigger #409 built the close
  around; a replay returns the original's answer, as a replay does everywhere
  else on this contract.
* **NON-DELIVERY NEVER CHARGES.** Failed, cancelled, killed and expired each
  produce nothing — including a piece of work that ran up real supplier cost,
  where exposure is bounded by the ceiling the tenant chose rather than by
  revenue nobody is owed.
* **A TENANT THAT DOES NOT BILL THROUGH UBB IS CHARGED TOO**, and this case is
  the one no gate in the repository could ever ask for. For that posture a
  Charge is a recorded revenue and margin fact rather than a collection, and a
  slice that built only the billing half would leave every gate green.
* **THE CHARGE CARRIES WHAT MAKES IT REPRODUCIBLE** — its own currency, the
  book version and the line that answered, both instants, a key derived from
  the work rather than supplied by a caller, and the Grouping Field values the
  work carried.
* **IT IS DATED AT DELIVERY**, so delivered work is always billable, and it
  carries the start instant beside that so a piece of work spanning a month
  boundary still nets its own revenue against its own cost.

⚠ **THE PROJECTED POSTING IS NOT THIS TICKET'S AND THIS MODULE ASSERTS NOTHING
ABOUT ONE.** §12 makes the Charge reach the money rails as one marked posting
carrying a `task_charge` discriminator, and #417 builds it; the Pricing Receipt
whose subject is a Charge is #418's. What is canonical is the record asserted
here, and the two that follow are projections OF it — which is the whole reason
it is a first-class row rather than a system-generated posting nobody could
correct.

⚠ **THE WIRE KEY FOR THE GROUPING BAG IS NEVER SPELLED HERE**, for the reason
`test_an_agreed_price_is_pinned_before_the_work_runs.py` gives at length: it is
retired vocabulary under a spread ceiling another slice owns, so this module
says what it means through `declared_grouping_values`.
"""
import json
import uuid
from datetime import timedelta

import pytest
from django.db import transaction
from django.test import Client
from django.utils import timezone

from api.v1.tests.test_metering_endpoints import declared_grouping_values
from apps.billing.wallets.models import Wallet
from apps.metering.pricing.models import Charge
from apps.metering.pricing.tests._helpers import a_price_for_whole_work
from apps.metering.usage.services.usage_service import UsageService
from apps.platform.customers.models import Customer
from apps.platform.grouping_fields.services import DimensionService
from apps.platform.tenants.models import Tenant, TenantApiKey
from apps.platform.work.models import Task, TaskType
from apps.platform.work.services import TaskService
from core.money import DEFAULT_CURRENCY
from core.vocabulary import (
    OUTCOME_REASON_CUSTOMER_CANCELLED, OUTCOME_REASON_EXECUTION_FAILED,
    PRICING_MODE_FIXED, TASK_OUTCOME_CANCELLED, TASK_OUTCOME_DELIVERED,
    TASK_OUTCOME_FAILED, TASK_STATUS_COMPLETED, TASK_TYPE_KIND_SUBTASK,
    TASK_TYPE_KIND_TASK,
)

#: The kind of work this tenant sells at one agreed price, and the one it sells
#: per event — so a case says which regime it is about by naming a word.
SOLD_WHOLE = "transcode"
SOLD_PER_EVENT = "chat"

THE_AGREED_PRICE = 8_000_000

#: A declared grouping key at the altitude a whole piece of work sits at, so
#: the snapshot claim has a real value to be about rather than ten blanks.
A_GROUPING_KEY = "region"
A_GROUPING_VALUE = "eu-west"


class ChargeTestBase:
    """One tenant that bills, one customer, and the close under test.

    The posture is the BILLING one by default, because that is the reading of a
    Charge everybody expects. The class whose subject is the OTHER posture
    builds its own tenant rather than switching this one, so a reader never has
    to hold two postures in mind at once — `test_an_agreed_price_is_pinned_
    before_the_work_runs.py` settled that shape and this module follows it.
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
        for kind in (TASK_TYPE_KIND_TASK, TASK_TYPE_KIND_SUBTASK):
            TaskType.objects.create(tenant=self.tenant, key=SOLD_WHOLE,
                                    kind=kind, pricing_mode=PRICING_MODE_FIXED)
            TaskType.objects.create(tenant=self.tenant, key=SOLD_PER_EVENT,
                                    kind=kind)
        if self.PRODUCTS != ["metering"]:
            Wallet.objects.create(customer=self.customer,
                                  balance_micros=1_000_000_000)

    def _auth(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {self.raw_key}"}

    def _start(self, **body):
        body.setdefault("customer_id", str(self.customer.id))
        body.setdefault("task_type", SOLD_WHOLE)
        body.setdefault("idempotency_key", f"attempt-{uuid.uuid4()}")
        response = self.client.post(
            "/api/v1/tasks", data=json.dumps(body),
            content_type="application/json", **self._auth())
        assert response.status_code == 200, response.content
        return response.json()["task_id"]

    def _close(self, task_id, **declaration):
        declaration.setdefault("outcome", TASK_OUTCOME_DELIVERED)
        return self.client.post(
            f"/api/v1/tasks/{task_id}/close", data=json.dumps(declaration),
            content_type="application/json", **self._auth())

    def _priced_work(self, amount=THE_AGREED_PRICE, **line):
        """A line in the tenant's default book, and one piece of work started
        against it — the fixture every claim here shares."""
        a_price_for_whole_work(self.tenant, task_type=SOLD_WHOLE,
                               amount_micros=amount, **line)
        return self._start()

    def _charges_against(self, task_id):
        return Charge.objects.filter(task_id=task_id)


@pytest.mark.django_db
class TestADeliveredUnitOfWorkIsChargedExactlyOnce(ChargeTestBase):
    """AC 1 and AC 9 — one close, one Charge, and the response stops lying."""

    def test_a_close_declaring_delivery_creates_one_charge(self):
        started = self._priced_work()

        body = self._close(started).json()

        assert body["charge_created"] is True
        assert body["replayed"] is False
        assert self._charges_against(started).count() == 1
        assert self._charges_against(started).get().amount_micros == THE_AGREED_PRICE

    def test_a_second_identical_close_creates_no_second_charge(self):
        """AC 1's second half. A retry after a lost response is not a second
        close, and it must not become a second charge — which is why the write
        hangs off the WINNING transition rather than off the request."""
        started = self._priced_work()
        self._close(started)

        replay = self._close(started).json()

        assert replay["replayed"] is True
        assert self._charges_against(started).count() == 1

    def test_a_replay_reports_the_answer_the_original_gave(self):
        """⚠ `charge_created` ON A REPLAY IS THE ORIGINAL'S ANSWER, NOT
        `false`.

        A replay returns what the first call returned everywhere else on this
        contract — the start gate hands back the original piece of work rather
        than a second one — and this field is not an exception to that. A
        retrying caller asking *did my close bill this?* would otherwise be told
        `false` for work that HAD been charged, which is the same class of
        silent misinformation the 409 below exists to remove, pointing the other
        way. `replayed: true` is what tells the caller nothing new happened.
        """
        started = self._priced_work()
        first = self._close(started).json()

        replay = self._close(started).json()

        assert first["charge_created"] is True
        assert replay["charge_created"] is True
        assert replay["replayed"] is True

    def test_work_sold_per_event_is_charged_nothing(self):
        """THE CONTROL, and it is the case that keeps `charge_created` from
        becoming a synonym for *this close won*. Every claim above would be
        satisfied by a close that charged for everything it delivered — and
        that close would bill a flat price for work nobody agreed one for.
        """
        a_price_for_whole_work(self.tenant, task_type=SOLD_WHOLE,
                               amount_micros=THE_AGREED_PRICE)
        started = self._start(task_type=SOLD_PER_EVENT)

        body = self._close(started).json()

        assert body["charge_created"] is False
        assert self._charges_against(started).count() == 0

    def test_contained_work_under_a_priced_parent_is_charged_nothing(self):
        """THE SECOND CONTROL. Contained work carries its container's regime and
        no price of its own (#415), so a close cascading over it must not fan
        out a charge per piece — which is the auto-charge failure #139 §3.1
        exists to refuse.

        ⚠ THE CONTAINED WORK IS THE SAME KIND AS ITS CONTAINER, and it has to
        be: #415's equality rule refuses a mixed tree at birth, so *a piece of
        work sold per event under a priced parent* is not a shape this system
        can produce. What makes the case discriminating is not the regime but
        the PRICE — the container pinned one and the contained work did not, so
        a charge here could only come from reading the regime instead of the
        pinned number.
        """
        parent = self._priced_work()
        contained = self._start(parent_task_id=parent, task_type=SOLD_WHOLE)
        assert Task.objects.get(id=contained).agreed_price_micros is None

        self._close(parent)

        assert self._charges_against(contained).count() == 0
        assert Charge.objects.filter(tenant=self.tenant).count() == 1


@pytest.mark.django_db
class TestNoOtherEndingCharges(ChargeTestBase):
    """AC 2 — every non-delivered outcome creates no Charge. One case each.

    ⚠ THE FOUR ARE NOT ONE CASE REPEATED. Two are declared by the tenant and two
    are written by UBB, they reach the terminal state through different code
    paths, and the last of them never goes near the close endpoint at all — so a
    charge wired to the wrong place would be caught by some of these and not by
    others.
    """

    def test_a_declared_failure_charges_nothing(self):
        started = self._priced_work()

        body = self._close(started, outcome=TASK_OUTCOME_FAILED,
                           outcome_reason=OUTCOME_REASON_EXECUTION_FAILED).json()

        assert body["charge_created"] is False
        assert self._charges_against(started).count() == 0

    def test_a_declared_cancellation_charges_nothing(self):
        started = self._priced_work()

        body = self._close(started, outcome=TASK_OUTCOME_CANCELLED,
                           outcome_reason=OUTCOME_REASON_CUSTOMER_CANCELLED).json()

        assert body["charge_created"] is False
        assert self._charges_against(started).count() == 0

    def test_work_ubb_killed_on_its_ceiling_charges_nothing(self):
        started = self._priced_work()

        with transaction.atomic():
            TaskService.kill_task(started)

        assert self._charges_against(started).count() == 0

    def test_work_nobody_ever_explained_charges_nothing(self):
        started = self._priced_work()

        with transaction.atomic():
            TaskService.expire_task(started)

        assert self._charges_against(started).count() == 0

    def test_a_failure_that_burned_real_supplier_cost_still_charges_nothing(self):
        """AC 2's named case, and the one with money on both sides of it.

        Exposure on work sold at one agreed price that did NOT deliver is
        bounded by the COGS ceiling the tenant chose, not recovered by charging
        for it anyway. A charge here would bill a customer the full agreed price
        for work the tenant's own caller said could not be delivered.
        """
        started = self._priced_work()
        TaskService.accumulate_cost(started, billed_cost_micros=0,
                                    provider_cost_micros=3_000_000)

        self._close(started, outcome=TASK_OUTCOME_FAILED,
                    outcome_reason=OUTCOME_REASON_EXECUTION_FAILED)

        assert self._charges_against(started).count() == 0
        assert Task.objects.get(id=started).total_provider_cost_micros == 3_000_000


@pytest.mark.django_db
class TestAContradictingCloseChargesNothing(ChargeTestBase):
    """AC 3 — a delivery declared on work UBB already stopped."""

    def test_a_delivery_declared_on_killed_work_is_refused_and_charges_nothing(self):
        """This is the case §5 says the refusal exists for, and it is the one
        with revenue in it.

        A silent 200 here would carry the killed state and no indication that no
        charge fired, so the first symptom of a ceiling being ignored would be a
        month-end number lower than expected. Letting the late delivery win
        instead was rejected outright: it makes ignoring the stop signal free,
        and the ceiling stops being a ceiling.
        """
        started = self._priced_work()
        with transaction.atomic():
            TaskService.kill_task(started)

        refused = self._close(started)

        assert refused.status_code == 409
        assert refused.json()["charge_created"] is False
        assert self._charges_against(started).count() == 0


@pytest.mark.django_db
class TestATenantThatDoesNotBillThroughUbbIsChargedToo(ChargeTestBase):
    """AC 4 — ⚠ THE CASE NO GATE IN THIS REPOSITORY COULD ASK FOR.

    Map constraint 2 has two realizations: for a tenant that bills through UBB a
    Charge is a real billable record like any other, and for one that does not it
    is a recorded revenue and margin fact. It is additional functionality
    offered to BOTH — and a slice that built only the first would leave every
    gate in the tree green, because no gate can tell a CORRECT declaration from a
    WRONG one.

    It is also the posture #415 recorded the declaration as *inert* for, which is
    exactly why the case is worth driving rather than describing: inert there
    means the unresolved-price refusal does not fire, never that the regime does
    nothing. A price that resolves is pinned for this tenant precisely so their
    margin reporting has a revenue number in it, and a Charge is that number's
    canonical record.
    """

    PRODUCTS = ["metering"]
    BILLING_MODE = None

    def test_a_delivered_piece_of_work_is_charged_with_no_wallet_in_sight(self):
        started = self._priced_work()

        body = self._close(started).json()

        assert body["charge_created"] is True
        assert self._charges_against(started).count() == 1
        assert self._charges_against(started).get().amount_micros == THE_AGREED_PRICE
        assert not Wallet.objects.filter(customer=self.customer).exists()

    def test_the_charge_is_a_record_rather_than_a_collection(self):
        """The distinction stated as an assertion rather than as prose: the row
        exists, carries the agreed number, and nothing about this tenant's money
        moved — because there is no money of UBB's to move for them."""
        started = self._priced_work()

        self._close(started)

        charge = self._charges_against(started).get()
        assert charge.amount_micros == THE_AGREED_PRICE
        assert charge.currency == DEFAULT_CURRENCY
        assert not Wallet.objects.filter(customer=self.customer).exists()


@pytest.mark.django_db
class TestWhatTheChargeCarries(ChargeTestBase):
    """AC 5 — everything that makes the amount reproducible from the record.

    ⚠ RE-RESOLVING IS NOT AN ALTERNATIVE TO ANY OF IT. #139 §2.3 requires the
    amount to be reproducible from the record *"rather than by re-resolving
    today's config"*, and re-resolution is not a fallback available later on any
    terms: which books are even in play depends on the customer's plan, which
    moves. So each of these is captured at the one instant it is known.
    """

    def test_the_charge_carries_its_own_currency(self):
        """⚠ THE PIECE OF WORK CARRIES NO CURRENCY AT ALL, which is one of the
        three reasons §11 gives for the pinned price not being the canonical
        record. A price list does not need one — the book's own argument is that
        a tenant has exactly one currency — but a movement of money is a fact
        about a currency and records it."""
        self.tenant.default_currency = "eur"
        self.tenant.save(update_fields=["default_currency"])
        started = self._priced_work()

        self._close(started)

        assert self._charges_against(started).get().currency == "eur"
        assert not any(field.name == "currency"
                       for field in Task._meta.get_fields())

    def test_the_charge_names_the_line_that_answered_and_its_book_version(self):
        line = a_price_for_whole_work(self.tenant, task_type=SOLD_WHOLE,
                                      amount_micros=THE_AGREED_PRICE)
        started = self._start()

        self._close(started)

        charge = self._charges_against(started).get()
        assert charge.agreed_price_line_id == line.id
        assert charge.book_version == line.pricing_book.version

    def test_the_book_version_is_the_one_that_answered_not_the_one_in_force_now(self):
        """⚠ THE VERSION MOVES AND THE RECORD MUST NOT. A book's version counter
        steps on every publish, so a Charge reading it at close time would record
        *the version this book is at now* — a number with nothing to do with the
        resolution it exists to explain. It is captured at start, beside the
        amount and the line, and copied from there.
        """
        line = a_price_for_whole_work(self.tenant, task_type=SOLD_WHOLE,
                                      amount_micros=THE_AGREED_PRICE)
        started = self._start()
        at_resolution = Task.objects.get(id=started).agreed_price_book_version

        book = line.pricing_book
        book.version += 4
        book.save(update_fields=["version"])
        self._close(started)

        assert self._charges_against(started).get().book_version == at_resolution
        assert at_resolution != book.version

    def test_the_charge_carries_both_instants(self):
        started = self._priced_work()

        self._close(started)

        work = Task.objects.get(id=started)
        charge = self._charges_against(started).get()
        assert charge.resolved_at == work.created_at
        assert charge.charged_at == work.completed_at
        assert charge.charged_at > charge.resolved_at

    def test_the_idempotency_key_is_derived_from_the_work(self):
        """⚠ DERIVED, NEVER CALLER-SUPPLIED. The identity of the work is already
        unique, and this repository's stance on the point is explicit one table
        over: a caller does not supply amounts or keys the system can derive.
        The assertion is that the key CONTAINS the work's identity rather than
        that it matches a spelling, so the shape may be improved without this
        case pinning a format nobody promised."""
        started = self._priced_work()

        self._close(started)

        charge = self._charges_against(started).get()
        assert str(started) in charge.idempotency_key

    def test_the_charge_snapshots_the_grouping_values_the_work_carried(self):
        """The snapshot is a COPY rather than a read through the work, because
        the work's row is mutable and this one is not."""
        DimensionService.declare(self.tenant, key=A_GROUPING_KEY,
                                 slot="grouping_field_1", scope="task")
        a_price_for_whole_work(self.tenant, task_type=SOLD_WHOLE,
                               amount_micros=THE_AGREED_PRICE)
        started = self._start(**declared_grouping_values(
            {A_GROUPING_KEY: A_GROUPING_VALUE}))

        self._close(started)

        work = Task.objects.get(id=started)
        charge = self._charges_against(started).get()
        carried = [getattr(work, f"grouping_field_{slot}") for slot in range(1, 11)]
        assert A_GROUPING_VALUE in carried
        assert [getattr(charge, f"grouping_field_{slot}")
                for slot in range(1, 11)] == carried


@pytest.mark.django_db
class TestTheChargeIsDatedAtDelivery(ChargeTestBase):
    """AC 8 — dated at delivery, so delivered work is always billable.

    Dating back to the start would keep cost and revenue in one period, and was
    rejected on the direction of its failure: work starting at 23:58 on the 31st
    and closing after the month's push had claimed the period would become
    UNBILLABLE for work that was delivered. The accepted consequence is the
    opposite skew — cost in the earlier period, revenue in the later one —
    tightly bounded by the absolute deadline.
    """

    def test_the_charge_is_dated_at_delivery_and_not_at_the_start(self):
        started = self._priced_work()
        last_month = timezone.now() - timedelta(days=40)
        Task.objects.filter(id=started).update(created_at=last_month)

        self._close(started)

        charge = self._charges_against(started).get()
        assert charge.charged_at > last_month
        assert (charge.charged_at.year, charge.charged_at.month) != (
            last_month.year, last_month.month)

    def test_work_crossing_a_month_boundary_still_nets_its_own_margin(self):
        """§11's promise that *job-level margin remains exact always*, driven
        rather than described.

        The two instants land in different periods on purpose. What keeps the
        margin exact is that the Charge carries the start instant beside the
        charge instant, so a reader netting this revenue against this piece of
        work's own COGS has both halves on one row and never has to guess which
        period the cost was reported in.
        """
        started = self._priced_work()
        UsageService.record_usage(
            self.tenant, self.customer, f"call-{uuid.uuid4()}",
            event_type=SOLD_PER_EVENT, task_id=started,
            provider_cost_micros=3_000_000)
        last_month = timezone.now() - timedelta(days=40)
        Task.objects.filter(id=started).update(created_at=last_month)

        self._close(started)

        work = Task.objects.get(id=started)
        charge = self._charges_against(started).get()
        assert charge.resolved_at == work.created_at
        assert (charge.resolved_at.month != charge.charged_at.month)
        assert (charge.amount_micros - work.total_provider_cost_micros
                == THE_AGREED_PRICE - 3_000_000)

    def test_the_charge_is_dated_by_the_transition_rather_than_by_the_request(self):
        """The instant is the one the winning transition wrote, which is what
        makes it the same instant every projection of this Charge will carry."""
        started = self._priced_work()

        self._close(started)

        work = Task.objects.get(id=started)
        assert work.status == TASK_STATUS_COMPLETED
        assert self._charges_against(started).get().charged_at == work.completed_at
