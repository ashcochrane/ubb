"""A prepaid start of a kind of work sold at one agreed price reserves that
price against the wallet, and affordability is the balance less what is
already reserved (#461, slice 6 §5, #139 §4.1 — ticket 10 of 20).

THE CLAIM, in one sentence: three concurrent starts cannot each read the same
balance and all pass, because a start writes a durable reservation row keyed on
the unit of work, in the same transaction as the start, and the money-shaped
verdict tests ``balance − open reservations`` against the tenant's own floors —
never a new threshold. A start that would leave the available amount past the
hard floor is refused with `insufficient_funds`; past the soft floor, with
`soft_floor_reached`, at the altitude the soft floor reads (a top-level start;
a contained start under running work passes, as it always has).

WHAT IS PROVED HERE, at the route — the seam six landed slices use for the
start's refusals — and what is proved elsewhere:

* the row, its amount, its owner and its transaction; the two refusals and
  the reading of the balance they are made against; the three postures that
  reserve nothing (event-priced work, a postpaid tenant, a tenant that does
  not bill through UBB); a replay reserving nothing new; the delivered close
  releasing and the drawdown landing so the balance moves by the agreed price
  exactly once; the balance read's two new figures — HERE;
* three concurrent starts against a balance that affords two —
  `apps/billing/tests/test_concurrent_prepaid_starts_reserve_only_what_the_balance_affords.py`,
  in the shape of the money-race modules beside it;
* every terminal path releasing through the kernel's listener registry, and
  the backstop sweep —
  `apps/billing/wallets/tests/test_every_terminal_path_releases_the_reservation.py`.

⚠ THE WALLET LANE IS EVERY MODE BUT POSTPAID, which is the fork the money
verdict and the live counter already make; "prepaid" in the ruling means that
lane. The tenant here declares `prepaid` outright, and the postpaid class
declares the other word — neither spells the mode a tenant is born with.
"""
import json
import uuid

import pytest
from django.test import Client

from apps.billing.wallets.models import (
    RELEASED_BY_TERMINAL_TRANSITION, CustomerBillingProfile, Wallet,
    WalletReservation, WalletTransaction)
from apps.billing.wallets.reservations import open_reservations_micros
from apps.metering.pricing.tests._helpers import a_price_for_whole_work
from apps.platform.customers.models import Customer
from apps.platform.events.dispatch import dispatch_to_handlers
from apps.platform.events.models import OutboxEvent
from apps.platform.tenants.models import Tenant, TenantApiKey
from apps.platform.work.models import Task, TaskType
from core.vocabulary import (
    AFFORDABILITY_REASON_INSUFFICIENT_FUNDS,
    AFFORDABILITY_REASON_SOFT_FLOOR_REACHED, PRICING_MODE_FIXED,
    TASK_OUTCOME_DELIVERED, TASK_TYPE_KIND_SUBTASK, TASK_TYPE_KIND_TASK)

#: The kind of work sold at one agreed price, and the one sold per event.
SOLD_WHOLE = "transcode"
SOLD_PER_EVENT = "chat"

THE_AGREED_PRICE = 8_000_000
#: A balance that affords exactly two of the price above with something left
#: over — so a third start is the one that would leave the available amount
#: past a floor at zero, while the balance itself never goes near it.
AFFORDS_TWO = 20_000_000


class ReservationTestBase:
    """One tenant that bills on the wallet lane, one customer with a wallet
    that affords two starts, and the start call under test."""

    PRODUCTS = ["metering", "billing"]
    BILLING_MODE = "prepaid"
    ENFORCEMENT_MODE = None

    def setup_method(self):
        options = {"billing_mode": self.BILLING_MODE} if self.BILLING_MODE else {}
        if self.ENFORCEMENT_MODE:
            options["enforcement_mode"] = self.ENFORCEMENT_MODE
        self.tenant = Tenant.objects.create(
            name="T", products=self.PRODUCTS, **options)
        _, self.raw_key = TenantApiKey.create_key(self.tenant)
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="c1")
        self.client = Client()
        for kind in (TASK_TYPE_KIND_TASK, TASK_TYPE_KIND_SUBTASK):
            TaskType.objects.create(tenant=self.tenant, key=SOLD_WHOLE,
                                    kind=kind, pricing_mode=PRICING_MODE_FIXED,
                                    uncapped=True)
            TaskType.objects.create(tenant=self.tenant, key=SOLD_PER_EVENT,
                                    kind=kind, uncapped=True)
        a_price_for_whole_work(self.tenant, task_type=SOLD_WHOLE,
                               amount_micros=THE_AGREED_PRICE)
        if self.PRODUCTS != ["metering"]:
            self.wallet = Wallet.objects.create(
                customer=self.customer, balance_micros=AFFORDS_TWO)

    def _auth(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {self.raw_key}"}

    def _start(self, **body):
        body.setdefault("customer_id", str(self.customer.id))
        body.setdefault("task_type", SOLD_WHOLE)
        body.setdefault("idempotency_key", f"attempt-{uuid.uuid4()}")
        return self.client.post(
            "/api/v1/tasks", data=json.dumps(body),
            content_type="application/json", **self._auth())

    def _started(self, **body):
        response = self._start(**body)
        assert response.status_code == 200, response.content
        return response.json()["task_id"]

    def _close(self, task_id, **declaration):
        declaration.setdefault("outcome", TASK_OUTCOME_DELIVERED)
        return self.client.post(
            f"/api/v1/tasks/{task_id}/close", data=json.dumps(declaration),
            content_type="application/json", **self._auth())

    def _balance(self, customer=None):
        response = self.client.get(
            f"/api/v1/billing/customers/{(customer or self.customer).id}/balance",
            **self._auth())
        assert response.status_code == 200, response.content
        return response.json()

    def _drain_the_rails(self):
        """Run every recorded posting through the real dispatcher, which is
        where a delivered unit's Charge draws the wallet down."""
        for row in OutboxEvent.objects.filter(
                event_type="usage.recorded").order_by("created_at"):
            dispatch_to_handlers(row)

    def _reservations(self):
        return WalletReservation.objects.filter(tenant=self.tenant)

    def _floors(self, *, hard=0, soft=None):
        CustomerBillingProfile.objects.update_or_create(
            customer=self.customer,
            defaults={"min_balance_micros": hard,
                      "soft_min_balance_micros": soft})


@pytest.mark.django_db
class TestAPrepaidStartReservesThePinnedPrice(ReservationTestBase):
    """The row: one per start, for the pinned price, on the owner's wallet,
    open until the unit ends."""

    def test_one_reservation_row_for_the_pinned_price(self):
        unit = self._started()

        row = self._reservations().get()
        assert row.task_id == uuid.UUID(unit)
        assert row.owner_id == self.customer.id
        assert row.amount_micros == THE_AGREED_PRICE
        assert row.released_at is None
        assert row.released_by == ""
        assert open_reservations_micros(self.customer.id) == THE_AGREED_PRICE

    def test_a_reservation_moves_neither_the_balance_nor_the_ledger(self):
        """A reservation encumbers the affordability read and nothing else:
        the wallet's balance and its ledger are untouched until the unit's
        Charge draws the wallet down. The repair's audit row records it as
        context for the same reason (`gating/models.py`)."""
        self._started()
        self.wallet.refresh_from_db()
        assert self.wallet.balance_micros == AFFORDS_TWO
        assert not WalletTransaction.objects.filter(wallet=self.wallet).exists()

    def test_a_pooled_seats_reservation_encumbers_its_owners_wallet(self):
        """The reservation is keyed on the BILLING OWNER — the business for a
        pooled seat — because that is the wallet the seat's Charge will draw
        down, and the wallet every other money-aware reader resolves to."""
        business = Customer.objects.create(
            tenant=self.tenant, external_id="biz", account_type="business",
            billing_topology="pooled")
        seat = Customer.objects.create(
            tenant=self.tenant, external_id="seat", account_type="seat",
            parent=business)
        Wallet.objects.create(customer=business, balance_micros=AFFORDS_TWO)

        self._started(customer_id=str(seat.id))

        row = self._reservations().get()
        assert row.owner_id == business.id
        assert open_reservations_micros(business.id) == THE_AGREED_PRICE
        assert open_reservations_micros(seat.id) == 0

    def test_a_replayed_start_reserves_nothing_new(self):
        """THE MONEY-CRITICAL HALF OF A REPLAY (the strong claim
        `test_a_start_claims_its_key.py` wrote the address for): a retry after
        a lost response hands back the same unit and the same reservation —
        a silent second one would be a double encumbrance and, on delivery,
        the shape of a double charge."""
        key = "nightly-batch-1"
        first = self._started(idempotency_key=key)
        replay = self._start(idempotency_key=key)

        assert replay.status_code == 200
        assert replay.json()["replayed"] is True
        assert replay.json()["task_id"] == first
        assert self._reservations().count() == 1
        assert open_reservations_micros(self.customer.id) == THE_AGREED_PRICE


@pytest.mark.django_db
class TestAffordabilityIsTheBalanceLessOpenReservations(ReservationTestBase):
    """The two refusals, made against what is AVAILABLE rather than against
    the balance, and through the start route (Testing Decisions claim 7)."""

    def test_a_start_that_would_leave_available_past_the_hard_floor_is_refused(self):
        self._floors(hard=0)
        self._started()
        self._started()
        assert open_reservations_micros(self.customer.id) == 2 * THE_AGREED_PRICE

        refused = self._start()

        assert refused.status_code == 409, refused.content
        body = refused.json()
        assert body["code"] == "task_start_refused"
        assert body["reason"] == AFFORDABILITY_REASON_INSUFFICIENT_FUNDS
        # THE BALANCE NEVER MOVED, AND THE REFUSAL SAYS WHICH FIGURE IT READ.
        assert body["balance_micros"] == AFFORDS_TWO
        assert body["available_micros"] == AFFORDS_TWO - 2 * THE_AGREED_PRICE

    def test_the_refused_start_is_rolled_back_whole(self):
        """The reservation is written in the same transaction as the start,
        after the unit's row: a refusal at the reservation leaves no unit, no
        third reservation and no wallet movement — the start spent nothing."""
        self._floors(hard=0)
        self._started()
        self._started()

        assert self._start().status_code == 409

        assert Task.objects.filter(tenant=self.tenant).count() == 2
        assert self._reservations().count() == 2
        assert not WalletTransaction.objects.filter(wallet=self.wallet).exists()

    def test_the_verdict_reads_available_money_for_an_event_priced_start_too(self):
        """`check` tests `balance − open reservations` for EVERY start on the
        wallet lane, not only for the ones that reserve. The floor is raised
        after the first reservation to a line the balance clears and the
        available amount does not — so the refusal below can only have read
        the available figure."""
        self._floors(hard=0)
        self._started()
        # A negative magnitude places the line ABOVE zero: at +15M, which the
        # 20M balance clears and the 12M available does not.
        self._floors(hard=-15_000_000)

        refused = self._start(task_type=SOLD_PER_EVENT)

        assert refused.status_code == 409, refused.content
        assert refused.json()["reason"] == AFFORDABILITY_REASON_INSUFFICIENT_FUNDS
        assert refused.json()["balance_micros"] == AFFORDS_TWO
        assert refused.json()["available_micros"] == AFFORDS_TWO - THE_AGREED_PRICE


@pytest.mark.django_db
class TestTheSoftFloorReadsAvailableMoneyAtItsOwnAltitude(ReservationTestBase):
    """Past the wind-down line NEW top-level work is refused with
    `soft_floor_reached` while contained work under a running unit passes —
    the altitude the parent argument names — and the line is compared against
    the available amount, exactly as the hard floor is. Enforcing, because the
    soft floor is a state-changing control and reads only under the switch."""

    ENFORCEMENT_MODE = "enforcing"

    def test_a_top_level_start_that_would_leave_available_past_the_soft_floor_is_refused(self):
        # Hard line at zero; wind-down line at +5M (a negative soft magnitude
        # places it above zero, clamped at or above the hard line).
        self._floors(hard=0, soft=-5_000_000)
        self._started()  # available 12M, clear of the wind-down line

        refused = self._start()  # would leave 4M: past the wind-down line

        assert refused.status_code == 409, refused.content
        assert refused.json()["reason"] == AFFORDABILITY_REASON_SOFT_FLOOR_REACHED
        assert refused.json()["available_micros"] == AFFORDS_TWO - THE_AGREED_PRICE
        assert self._reservations().count() == 1

    def test_a_contained_start_under_running_work_passes_at_that_altitude(self):
        parent = self._started()  # leaves 12M available
        # The wind-down line is then raised to +15M, past the 12M available,
        # so the running parent was admitted and nothing new at its altitude is.
        self._floors(hard=0, soft=-15_000_000)

        assert self._start().status_code == 409  # a second top-level start
        contained = self._start(parent_task_id=parent)

        assert contained.status_code == 200, contained.content
        # Contained work never pins a price of its own (#415), so it reserves
        # nothing: the parent's reservation is the whole encumbrance.
        assert self._reservations().count() == 1


@pytest.mark.django_db
class TestAnEventPricedStartReservesNothing(ReservationTestBase):
    """Event-priced work has no pinned price to reserve — the first of the
    three postures the ruling names, each owed a test of its own."""

    def test_an_event_priced_start_reserves_nothing(self):
        self._started(task_type=SOLD_PER_EVENT)
        assert not self._reservations().exists()
        assert open_reservations_micros(self.customer.id) == 0


@pytest.mark.django_db
class TestAPostpaidStartReservesNothing(ReservationTestBase):
    """A postpaid tenant has no wallet to encumber: the price is pinned for
    the Charge, and nothing is reserved against anything."""

    BILLING_MODE = "postpaid"

    def test_a_postpaid_start_of_a_fixed_price_kind_reserves_nothing(self):
        unit = self._started()
        assert Task.objects.get(id=unit).agreed_price_micros == THE_AGREED_PRICE
        assert not self._reservations().exists()


@pytest.mark.django_db
class TestATenantThatDoesNotBillThroughUbbReservesNothing(ReservationTestBase):
    """A tenant that does not bill through UBB has no wallet: the price that
    resolves is pinned for their margin reporting (#415) and nothing is
    reserved, because there is nothing to reserve it against."""

    PRODUCTS = ["metering"]
    BILLING_MODE = None

    def test_a_start_on_a_tenant_that_does_not_bill_reserves_nothing(self):
        unit = self._started()
        assert Task.objects.get(id=unit).agreed_price_micros == THE_AGREED_PRICE
        assert not self._reservations().exists()
        assert not Wallet.objects.filter(customer=self.customer).exists()


@pytest.mark.django_db
class TestADeliveredCloseReleasesAndTheDrawdownLandsOnce(ReservationTestBase):
    """After a delivered close the reservation is released — through the
    kernel's terminal-transition listener, never by a call from here — and
    the Charge's drawdown lands through the outbox; the balance after both
    equals the balance before less the agreed price, exactly once."""

    def test_the_balance_moves_by_the_agreed_price_exactly_once(self):
        unit = self._started()
        assert self._close(unit).json()["charge_created"] is True

        row = self._reservations().get()
        assert row.released_at is not None
        assert row.released_by == RELEASED_BY_TERMINAL_TRANSITION
        assert open_reservations_micros(self.customer.id) == 0

        self._drain_the_rails()
        self.wallet.refresh_from_db()
        assert self.wallet.balance_micros == AFFORDS_TWO - THE_AGREED_PRICE
        assert WalletTransaction.objects.filter(wallet=self.wallet).count() == 1

        # Neither the release nor the drawdown happens twice.
        self._drain_the_rails()
        self.wallet.refresh_from_db()
        assert self.wallet.balance_micros == AFFORDS_TWO - THE_AGREED_PRICE
        assert WalletTransaction.objects.filter(wallet=self.wallet).count() == 1
        assert self._reservations().count() == 1

    def test_the_released_amount_is_available_again_before_the_drawdown_lands(self):
        """The brief window in which neither the reservation nor the drawdown
        encumbers the balance is the window every metered event already has
        between recording and drawdown (ledger, not wall)."""
        self._floors(hard=0)
        unit = self._started()
        self._started()
        assert self._start().status_code == 409

        self._close(unit)

        assert self._start().status_code == 200


@pytest.mark.django_db
class TestTheBalanceReadShowsReservedAndAvailableBesideTheBalance(
        ReservationTestBase):
    """Two additive figures on the customer's balance read, under their final
    names: what is reserved against the balance and what is available — so a
    reader can show "available" and "balance" without confusing them."""

    def test_the_two_figures_beside_the_balance(self):
        self._started()

        read = self._balance()

        assert read["balance_micros"] == AFFORDS_TWO
        assert read["reserved_micros"] == THE_AGREED_PRICE
        assert read["available_micros"] == AFFORDS_TWO - THE_AGREED_PRICE

    def test_a_released_reservation_no_longer_counts(self):
        unit = self._started()
        self._close(unit)

        read = self._balance()

        assert read["reserved_micros"] == 0
        assert read["available_micros"] == AFFORDS_TWO

    def test_a_customer_with_no_wallet_row_reads_nothing_reserved(self):
        never_credited = Customer.objects.create(
            tenant=self.tenant, external_id="c2")

        read = self._balance(never_credited)

        assert read["balance_micros"] == 0
        assert read["reserved_micros"] == 0
        assert read["available_micros"] == 0

    def test_a_pooled_seat_reads_its_owners_figures(self):
        business = Customer.objects.create(
            tenant=self.tenant, external_id="biz", account_type="business",
            billing_topology="pooled")
        seat = Customer.objects.create(
            tenant=self.tenant, external_id="seat", account_type="seat",
            parent=business)
        Wallet.objects.create(customer=business, balance_micros=AFFORDS_TWO)
        self._started(customer_id=str(seat.id))

        read = self._balance(seat)

        assert read["is_pooled_seat"] is True
        assert read["reserved_micros"] == THE_AGREED_PRICE
        assert read["available_micros"] == AFFORDS_TWO - THE_AGREED_PRICE
