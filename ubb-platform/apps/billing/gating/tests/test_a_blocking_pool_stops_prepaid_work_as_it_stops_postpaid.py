"""A blocking pool stops a prepaid customer's active work as it stops a
postpaid customer's (#459, slice 6 §4; Testing Decisions claims 4, 5, 6).

Payment mode decides who invoices and nothing else (#150 §7.1). Every case
here drives the REAL seams — the recording route, the start route, the
drawdown handler — and asserts what a caller gets back, what the ledger
holds and what the outbox carries, never a hand-built payload:

* **the same test shape passes for both postures**, spelled as two classes
  over one mixin, because building a control for one posture only is the
  one thing no gate in the repository can tell (the spec's Further Notes);
* the Charge that reached the boundary is recorded and counted, never
  reversed; the stop reaches `killed` only through the kernel's
  `kill_and_announce`, with the pool's word, `pool_crossing` and the pool
  row's id; the next start is refused with the pool's own refusal word;
* an `alert_only` pool alerts and never stops, in either mode;
* one seat's charge counts toward the seat's pool AND its business's pool,
  the tenant default reaches a seat and never a business, and both levels
  alert, stop and refuse;
* a delivered fixed-price unit moves its pool by exactly its agreed price
  and a second identical close moves it by nothing; unknown revenue is
  excluded and reported, never summed as zero;
* a customer stopped by its pool and by its floor at once holds two open
  episodes, each announced once with its own family and id, and the stop
  flag clears only when both have — through the recording route and the
  drawdown, and again with the live lane switched off so the drawdown
  alone opens both.

This module says "a unit of work", "active work" and "the work" throughout,
on the retired-sense rule the registry records for the plural.
"""
import datetime
import json
import uuid
from dataclasses import asdict
from unittest import mock

from django.core.cache import cache
from django.test import Client, TestCase
from django.utils import timezone

from apps.billing.gating.models import CustomerSpendPool, StopSignalState
from apps.billing.gating.services.customer_spend_pool_service import (
    CustomerSpendPoolService)
from apps.billing.gating.services.live_counter import Door, LiveCounter
from apps.billing.gating.services.risk_service import RiskService
from apps.billing.gating.services.stop_signal_service import StopSignalService
from apps.billing.handlers import handle_usage_recorded_billing
from apps.billing.queries import get_billing_config
from apps.billing.wallets.models import Wallet
from apps.metering.pricing.models import Charge
from apps.metering.pricing.tests._helpers import (
    a_price_for_whole_work, a_rule_that_prices_what_it_measures, what_it_bills)
from apps.metering.usage.models import Posting
from apps.platform.customers.models import Customer
from apps.platform.event_types.tests._helpers import (
    DECLARED, declares_a_caller_supplied_cost)
from apps.platform.events.models import OutboxEvent
from apps.platform.events.schemas import (
    BudgetThresholdReached, CustomerSuspended, StopCleared, StopFired,
    TaskKilled, UsageRecorded)
from apps.platform.tenants.models import Tenant, TenantApiKey
from apps.platform.work import reasons
from apps.platform.work.models import (
    STOP_CAUSE_KEY, STOP_CONTROL_FAMILY_KEY, STOP_CONTROL_ID_KEY,
    STOP_MECHANISM_KEY, Task, TaskType)
from core.vocabulary import (
    AFFORDABILITY_REASON_CUSTOMER_SPEND_POOL_EXCEEDED,
    CONTROL_FAMILY_CUSTOMER_SPEND_POOL, CONTROL_FAMILY_WALLET_POLICY,
    CUSTOMER_BILLING_MODE_POSTPAID, CUSTOMER_BILLING_MODE_PREPAID,
    PRICING_MODE_FIXED, PRICING_STATUS_UNKNOWN,
    SPEND_POOL_ENFORCE_MODE_ALERT_ONLY, SPEND_POOL_ENFORCE_MODE_BLOCKING,
    TASK_OUTCOME_DELIVERED, TASK_STATUS_ACTIVE, TASK_STATUS_KILLED,
    TASK_TYPE_KIND_TASK, TRIGGER_SOURCE_POOL_CROSSING)

#: Where the outbox doorbell rings; patched so executed on-commit callbacks
#: never reach Celery (the seam test's own arrangement).
DOORBELL = "apps.platform.events.tasks.process_single_event"

#: The kind of work one class below sells at one agreed price, and what for.
SOLD_WHOLE = "transcode"
THE_AGREED_PRICE = 8_000_000


class PoolTestBase(TestCase):
    """One enforcing tenant in the posture `MODE` names, one customer, the
    real routes and the real drawdown handler."""

    MODE = CUSTOMER_BILLING_MODE_PREPAID
    #: A wallet a prepaid floor never bites through, so every stop asserted
    #: here is the pool's unless a case lowers it on purpose.
    WALLET = 100_000_000

    def setUp(self):
        cache.clear()
        self.http = Client()
        self.tenant = Tenant.objects.create(
            name="Pool", products=["metering", "billing"],
            billing_mode=self.MODE, enforcement_mode="enforcing")
        _, self.raw_key = TenantApiKey.create_key(self.tenant, label="t")
        self.customer = self._customer("c1", wallet=self.WALLET)
        declares_a_caller_supplied_cost(self.tenant, DECLARED)
        a_rule_that_prices_what_it_measures(self.tenant)
        self._drained = set()

    def tearDown(self):
        cache.clear()

    # -- fixtures -----------------------------------------------------------

    def _customer(self, external_id, *, wallet=None, **fields):
        customer = Customer.objects.create(
            tenant=self.tenant, external_id=external_id, **fields)
        if wallet is not None:
            Wallet.objects.create(customer=customer, balance_micros=wallet)
        return customer

    def _pool(self, customer, cap, mode=SPEND_POOL_ENFORCE_MODE_BLOCKING):
        return CustomerSpendPool.objects.create(
            tenant=self.tenant, customer=customer, cap_micros=cap,
            enforce_mode=mode)

    def _headers(self):
        return {"content_type": "application/json",
                "HTTP_AUTHORIZATION": f"Bearer {self.raw_key}"}

    # -- the real seams -----------------------------------------------------

    def _start(self, customer=None, **body):
        body.setdefault("customer_id", str((customer or self.customer).id))
        body.setdefault("idempotency_key", f"attempt-{uuid.uuid4()}")
        return self.http.post("/api/v1/tasks", data=json.dumps(body),
                              **self._headers())

    def _unit(self, customer=None, **body):
        response = self._start(customer, **body)
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()["task_id"]

    def _record(self, customer=None, *, bills, task_id=None, **extra):
        """One usage report through the recording route. The pool's kill is
        registered on the recording transaction's commit; a `TestCase` never
        commits, so the callbacks are run here with the doorbell silenced."""
        data = {"customer_id": str((customer or self.customer).id),
                "idempotency_key": f"idem-{uuid.uuid4()}",
                "event_type": DECLARED, "provider_cost_micros": 1_000,
                "task_id": task_id}
        data.update(what_it_bills({"bills": bills}))
        data.update(extra)
        with mock.patch(DOORBELL), self.captureOnCommitCallbacks(execute=True):
            response = self.http.post("/api/v1/metering/usage",
                                      data=json.dumps(data), **self._headers())
        self.assertEqual(response.status_code, 200, response.json())
        return response.json()

    def _drain(self):
        """Run the drawdown handler for every `usage.recorded` row not yet
        drained — the durable lane, exactly as the outbox would run it."""
        rows = OutboxEvent.objects.filter(
            event_type=UsageRecorded.EVENT_TYPE,
            tenant_id=self.tenant.id).exclude(id__in=self._drained)
        with mock.patch(DOORBELL), self.captureOnCommitCallbacks(execute=True):
            for row in rows.order_by("created_at"):
                handle_usage_recorded_billing(str(row.id), row.payload)
                self._drained.add(row.id)

    # -- reads ---------------------------------------------------------------

    def _events(self, event_class, **payload):
        qs = OutboxEvent.objects.filter(event_type=event_class.EVENT_TYPE)
        for key, value in payload.items():
            qs = qs.filter(**{f"payload__{key}": str(value)})
        return qs

    def _the_one(self, event_class, **payload):
        return self._events(event_class, **payload).get().payload

    def _refusal(self, response):
        self.assertEqual(response.status_code, 409, response.content)
        return response.json()["reason"]


# ---------------------------------------------------------------------------
# Claim 4 — the same shape, both postures
# ---------------------------------------------------------------------------

class ABlockingPoolStopsWorkMidFlight:
    """The shared shape. Each posture below runs every case; the class that
    binds it says which posture it is about by naming the mode."""

    def test_a_blocking_pool_stops_active_work_and_refuses_the_next_start(self):
        pool = self._pool(self.customer, 5_000_000)
        unit = self._unit()

        ack = self._record(bills=5_000_000, task_id=unit)

        # The acknowledgement says stopped, in the pool's own word.
        self.assertTrue(ack["stop"])
        self.assertEqual(ack["stop_reason"], reasons.CUSTOMER_SPEND_POOL)
        self.assertEqual(ack["stop_scope"], "customer")
        # The active work reached `killed` through the kernel, and the row
        # records the cause, the mechanism and the control.
        row = Task.objects.get(id=unit)
        self.assertEqual(row.status, TASK_STATUS_KILLED)
        self.assertEqual(row.metadata[STOP_CAUSE_KEY], reasons.CUSTOMER_SPEND_POOL)
        self.assertEqual(row.metadata[STOP_MECHANISM_KEY], TRIGGER_SOURCE_POOL_CROSSING)
        self.assertEqual(row.metadata[STOP_CONTROL_FAMILY_KEY],
                         CONTROL_FAMILY_CUSTOMER_SPEND_POOL)
        self.assertEqual(row.metadata[STOP_CONTROL_ID_KEY], str(pool.id))
        payload = self._the_one(TaskKilled)
        self.assertEqual(payload["reason_code"], reasons.CUSTOMER_SPEND_POOL)
        self.assertEqual(payload["trigger_source"], TRIGGER_SOURCE_POOL_CROSSING)
        self.assertEqual(payload["control_family"], CONTROL_FAMILY_CUSTOMER_SPEND_POOL)
        self.assertEqual(payload["control_id"], str(pool.id))
        self.assertIsNone(payload["ceiling_basis"])
        # The customer-wide signal fired once, on the pool's line.
        fired = self._the_one(StopFired)
        self.assertEqual(fired["reason_code"], reasons.CUSTOMER_SPEND_POOL)
        self.assertEqual(fired["control_id"], str(pool.id))
        # And the next start is refused with the pool's refusal word.
        self.assertEqual(self._refusal(self._start()),
                         AFFORDABILITY_REASON_CUSTOMER_SPEND_POOL_EXCEEDED)

    def test_the_charge_that_reached_the_boundary_is_recorded_and_counted(self):
        self._pool(self.customer, 5_000_000)
        unit = self._unit()

        ack = self._record(bills=5_000_000, task_id=unit)
        self._drain()

        self.assertTrue(ack["stop"])
        posting = Posting.objects.get(id=ack["event_id"])
        self.assertEqual(posting.billed_cost_micros, 5_000_000)
        # Both counters and the durable basis include the boundary charge;
        # nothing was reversed.
        self.assertEqual(Door.spend(self.customer.id), 5_000_000)
        self.assertEqual(Door.spend_pool(self.customer.id), 5_000_000)
        label, known, unresolved = CustomerSpendPoolService.period_basis(
            self.tenant.id, self.customer.id)
        self.assertEqual((known, unresolved), (5_000_000, 0))
        # A late report on the killed work still lands and bills (one-rule).
        late = self._record(bills=1_000_000, task_id=unit)
        self.assertEqual(late["stop_reason"], reasons.TASK_NOT_ACTIVE)
        self.assertEqual(Posting.objects.get(id=late["event_id"]).billed_cost_micros,
                         1_000_000)

    def test_an_alert_only_pool_alerts_and_never_stops(self):
        self._pool(self.customer, 5_000_000, SPEND_POOL_ENFORCE_MODE_ALERT_ONLY)
        unit = self._unit()

        ack = self._record(bills=6_000_000, task_id=unit)
        self._drain()

        self.assertFalse(ack["stop"])
        self.assertEqual(Task.objects.get(id=unit).status, TASK_STATUS_ACTIVE)
        self.assertFalse(self._events(StopFired).exists())
        self.assertFalse(self._events(TaskKilled).exists())
        self.assertFalse(StopSignalState.objects.filter(owner=self.customer).exists())
        # 120% of the pool crossed every configured level.
        self.assertEqual(
            sorted(e.payload["level"] for e in self._events(BudgetThresholdReached)),
            [50, 80, 100, 110])
        self.assertEqual(self._start().status_code, 200)


class ABlockingPoolStopsPrepaidWorkTest(ABlockingPoolStopsWorkMidFlight, PoolTestBase):
    MODE = CUSTOMER_BILLING_MODE_PREPAID


class ABlockingPoolStopsPostpaidWorkTest(ABlockingPoolStopsWorkMidFlight, PoolTestBase):
    """The other posture, owed by name: the shape above, for the lane the old
    code already served."""
    MODE = CUSTOMER_BILLING_MODE_POSTPAID


# ---------------------------------------------------------------------------
# Claim 5 — two declared levels
# ---------------------------------------------------------------------------

class TwoDeclaredLevelsTest(PoolTestBase):
    """A pooled business and its seats: a seat's charge counts toward the
    seat's pool and the business's; the tenant default is a seat's."""

    def setUp(self):
        super().setUp()
        self.biz = self._customer("biz", wallet=self.WALLET,
                                  account_type="business", billing_topology="pooled")
        self.seat1 = self._customer("s1", account_type="seat", parent=self.biz)
        self.seat2 = self._customer("s2", account_type="seat", parent=self.biz)

    def _default_pool(self, cap, mode=SPEND_POOL_ENFORCE_MODE_BLOCKING):
        return CustomerSpendPool.objects.create(
            tenant=self.tenant, customer=None, cap_micros=cap, enforce_mode=mode)

    def test_one_seats_charge_counts_toward_its_own_pool_and_its_businesss(self):
        self._default_pool(10_000_000)
        self._pool(self.biz, 20_000_000)

        self._record(self.seat1, bills=1_000_000)
        self._drain()

        self.assertEqual(Door.spend_pool(self.seat1.id), 1_000_000)   # the seat's level
        self.assertEqual(Door.spend(self.biz.id), 1_000_000)          # the business's level

    def test_the_tenant_default_reaches_a_seat_and_never_a_business(self):
        default = self._default_pool(10_000_000)

        self.assertEqual(
            CustomerSpendPoolService.resolve_config_for(self.tenant.id, self.seat1.id).id,
            default.id)
        self.assertIsNone(
            CustomerSpendPoolService.resolve_config_for(self.tenant.id, self.biz.id))
        self.assertIsNone(CustomerSpendPoolService.resolve_config(self.biz))
        # A standalone customer is its own seat: the default is its pool.
        self.assertEqual(
            CustomerSpendPoolService.resolve_config(self.customer).id, default.id)
        # The business's own row is the business's pool.
        own = self._pool(self.biz, 20_000_000)
        self.assertEqual(CustomerSpendPoolService.resolve_config(self.biz).id, own.id)

    def test_the_seat_level_stops_and_refuses_the_seat_alone(self):
        default = self._default_pool(3_000_000)
        unit = self._unit(self.seat1)

        # The business has no pool, so the recording route's live lane opens
        # nothing; the seat's level is counted on the drawdown.
        ack = self._record(self.seat1, bills=3_000_000, task_id=unit)
        self.assertFalse(ack["stop"])
        self._drain()

        self.seat1.refresh_from_db()
        self.assertEqual(self.seat1.status, "suspended")
        self.assertEqual(self.seat1.suspension_reason, reasons.CUSTOMER_SPEND_POOL)
        row = Task.objects.get(id=unit)
        self.assertEqual(row.status, TASK_STATUS_KILLED)
        self.assertEqual(row.metadata[STOP_MECHANISM_KEY], TRIGGER_SOURCE_POOL_CROSSING)
        self.assertEqual(row.metadata[STOP_CONTROL_ID_KEY], str(default.id))
        fired = self._the_one(StopFired, owner_id=self.seat1.id)
        self.assertEqual(fired["control_id"], str(default.id))
        self.assertEqual(self._refusal(self._start(self.seat1)),
                         AFFORDABILITY_REASON_CUSTOMER_SPEND_POOL_EXCEEDED)
        # The business and its other seat carry on: a seat's pool bounds the
        # seat's own charges.
        self.biz.refresh_from_db()
        self.assertEqual(self.biz.status, "active")
        self.assertEqual(self._start(self.seat2).status_code, 200)

    def test_the_business_level_stops_every_seats_work_and_refuses_each(self):
        pool = self._pool(self.biz, 5_000_000)
        u1 = self._unit(self.seat1)
        u2 = self._unit(self.seat2)

        ack = self._record(self.seat1, bills=5_000_000, task_id=u1)

        self.assertTrue(ack["stop"])
        self.assertEqual(ack["stop_reason"], reasons.CUSTOMER_SPEND_POOL)
        self.biz.refresh_from_db()
        self.assertEqual(self.biz.status, "suspended")
        self.assertEqual(self.biz.suspension_reason, reasons.CUSTOMER_SPEND_POOL)
        for unit in (u1, u2):
            row = Task.objects.get(id=unit)
            self.assertEqual(row.status, TASK_STATUS_KILLED, unit)
            self.assertEqual(row.metadata[STOP_CONTROL_ID_KEY], str(pool.id))
        self.assertEqual(self._events(TaskKilled).count(), 2)
        self.assertEqual({e.payload["trigger_source"] for e in self._events(TaskKilled)},
                         {TRIGGER_SOURCE_POOL_CROSSING})
        fired = self._the_one(StopFired, owner_id=self.biz.id)
        self.assertEqual(fired["control_id"], str(pool.id))
        for seat in (self.seat1, self.seat2):
            self.assertEqual(self._refusal(self._start(seat)),
                             AFFORDABILITY_REASON_CUSTOMER_SPEND_POOL_EXCEEDED)

    def test_both_levels_alert(self):
        self._default_pool(2_000_000, SPEND_POOL_ENFORCE_MODE_ALERT_ONLY)
        self._pool(self.biz, 2_000_000, SPEND_POOL_ENFORCE_MODE_ALERT_ONLY)

        self._record(self.seat1, bills=1_000_000)
        self._drain()

        alerted = {(e.payload["customer_id"], e.payload["level"])
                   for e in self._events(BudgetThresholdReached)}
        self.assertEqual(alerted, {(str(self.seat1.id), 50), (str(self.biz.id), 50)})


# ---------------------------------------------------------------------------
# Claim 4 — the Charge is counted exactly once; unknown revenue is excluded
# ---------------------------------------------------------------------------

class TheChargeIsCountedOnceTest(PoolTestBase):
    def setUp(self):
        super().setUp()
        TaskType.objects.create(tenant=self.tenant, key=SOLD_WHOLE,
                                kind=TASK_TYPE_KIND_TASK,
                                pricing_mode=PRICING_MODE_FIXED, uncapped=True)
        a_price_for_whole_work(self.tenant, task_type=SOLD_WHOLE,
                               amount_micros=THE_AGREED_PRICE)

    def _close(self, unit):
        with mock.patch(DOORBELL), self.captureOnCommitCallbacks(execute=True):
            response = self.http.post(
                f"/api/v1/tasks/{unit}/close",
                data=json.dumps({"outcome": TASK_OUTCOME_DELIVERED}),
                **self._headers())
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def test_a_delivered_fixed_price_unit_moves_its_pool_by_its_agreed_price_once(self):
        self._pool(self.customer, 100_000_000, SPEND_POOL_ENFORCE_MODE_ALERT_ONLY)
        unit = self._unit(task_type=SOLD_WHOLE)

        first = self._close(unit)
        self._drain()

        self.assertTrue(first["charge_created"])
        self.assertEqual(Door.spend_pool(self.customer.id), THE_AGREED_PRICE)
        label, known, unresolved = CustomerSpendPoolService.period_basis(
            self.tenant.id, self.customer.id)
        self.assertEqual((known, unresolved), (THE_AGREED_PRICE, 0))

        again = self._close(unit)
        self._drain()

        self.assertTrue(again["replayed"])
        self.assertEqual(Charge.objects.filter(task_id=unit).count(), 1)
        self.assertEqual(self._events(UsageRecorded).count(), 1)
        self.assertEqual(Door.spend_pool(self.customer.id), THE_AGREED_PRICE)
        self.assertEqual(CustomerSpendPoolService.period_basis(
            self.tenant.id, self.customer.id)[1], THE_AGREED_PRICE)

    def test_unknown_revenue_is_excluded_and_reported_never_summed_as_zero(self):
        # The smallest blocking pool there is: any known charge at all stops.
        self._pool(self.customer, 1)
        # A posting whose customer price UBB could not resolve, on the rails
        # exactly as the recording path leaves one (#351): no amount, and a
        # status that says why.
        posting = Posting.objects.create(
            tenant=self.tenant, customer=self.customer, idempotency_key="unpriced",
            provider_cost_micros=1_000, billed_cost_micros=None,
            pricing_status=PRICING_STATUS_UNKNOWN,
            billing_owner_id=self.customer.id)
        row = OutboxEvent.objects.create(
            event_type=UsageRecorded.EVENT_TYPE, tenant_id=self.tenant.id,
            payload=asdict(UsageRecorded(
                tenant_id=str(self.tenant.id), customer_id=str(self.customer.id),
                event_id=str(posting.id), cost_micros=None,
                billed_cost_micros=None, pricing_status=PRICING_STATUS_UNKNOWN,
                billing_owner_id=str(self.customer.id))))
        self._drain()
        self.assertIn(row.id, self._drained)

        # Excluded from the figure, reported beside it — and no stop line
        # opened on a number nobody has stated.
        label, known, unresolved = CustomerSpendPoolService.period_basis(
            self.tenant.id, self.customer.id)
        self.assertEqual((known, unresolved), (0, 1))
        self.assertEqual(LiveCounter.spend_pool_read(self.tenant.id, self.customer.id), 0)
        self.assertTrue(RiskService.check(self.customer)["allowed"])
        self.assertFalse(StopSignalState.objects.filter(owner=self.customer).exists())
        status = self.http.get(
            f"/api/v1/billing/customers/{self.customer.id}/customer-spend-pool/status",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}").json()
        self.assertEqual(status["known_period_charges_micros"], 0)
        self.assertEqual(status["unresolved_posting_count"], 1)
        self.assertFalse(status["blocking_occurred"])


# ---------------------------------------------------------------------------
# Claim 6 — the pool and the floor at once, end to end
# ---------------------------------------------------------------------------

class TwoLinesAtOnceTest(PoolTestBase):
    """A prepaid customer whose one report crosses both its pool and its
    wallet floor. The wallet holds less than the pool allows, so the same
    charge tips both lines."""
    WALLET = 4_000_000

    def _both_open(self, pool):
        fired = {e.payload["reason_code"]: e.payload
                 for e in self._events(StopFired, owner_id=self.customer.id)}
        self.assertEqual(set(fired), {reasons.HARD_FLOOR, reasons.CUSTOMER_SPEND_POOL})
        self.assertEqual(fired[reasons.HARD_FLOOR]["control_family"],
                         CONTROL_FAMILY_WALLET_POLICY)
        self.assertEqual(fired[reasons.HARD_FLOOR]["control_id"],
                         str(get_billing_config(self.tenant.id).id))
        self.assertEqual(fired[reasons.CUSTOMER_SPEND_POOL]["control_family"],
                         CONTROL_FAMILY_CUSTOMER_SPEND_POOL)
        self.assertEqual(fired[reasons.CUSTOMER_SPEND_POOL]["control_id"], str(pool.id))
        self.assertEqual(
            [line["reason"] for line in StopSignalService.open_stop_lines(self.customer.id)],
            [reasons.HARD_FLOOR, reasons.CUSTOMER_SPEND_POOL])
        self.assertEqual(self._events(CustomerSuspended, customer_id=self.customer.id).count(), 1)
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.status, "suspended")

    def test_a_customer_stopped_by_its_pool_and_its_floor_holds_two_episodes(self):
        pool = self._pool(self.customer, 5_000_000)
        unit = self._unit()

        # The recording route: one report, both lines cross on the live lane.
        ack = self._record(bills=5_000_000, task_id=unit)
        self.assertTrue(ack["stop"])
        self._both_open(pool)
        # The work is stopped by the pool, and both customer-scope entries of
        # the tipping report say this report opened them.
        row = Task.objects.get(id=unit)
        self.assertEqual(row.status, TASK_STATUS_KILLED)
        self.assertEqual(row.metadata[STOP_CAUSE_KEY], reasons.CUSTOMER_SPEND_POOL)
        context = {entry["limit"]: entry
                   for entry in Posting.objects.get(id=ack["event_id"]).stop_context
                   if entry["stop_scope"] == "customer"}
        self.assertEqual(set(context), {reasons.HARD_FLOOR, reasons.CUSTOMER_SPEND_POOL})
        self.assertFalse(context[reasons.HARD_FLOOR]["arrived_after"])
        self.assertFalse(context[reasons.CUSTOMER_SPEND_POOL]["arrived_after"])

        # The drawdown: the durable lane sees both crossings and announces
        # neither a second time.
        self._drain()
        self._both_open(pool)

        # The wallet recovers: the floor's line clears and the pool still holds.
        with mock.patch(DOORBELL), self.captureOnCommitCallbacks(execute=True):
            credited = self.http.post("/api/v1/billing/credit", data=json.dumps({
                "customer_id": self.customer.external_id,
                "amount_micros": 20_000_000, "source": "topup",
                "reference": "tp1", "idempotency_key": "tp1"}), **self._headers())
        self.assertEqual(credited.status_code, 200, credited.content)
        cleared = self._events(StopCleared, owner_id=self.customer.id)
        self.assertEqual([e.payload["reason_code"] for e in cleared], [reasons.HARD_FLOOR])
        verdict = LiveCounter.read(self.customer.id, self.tenant)
        self.assertTrue(verdict["stop"])
        self.assertEqual(verdict["stop_reason"], reasons.CUSTOMER_SPEND_POOL)
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.status, "suspended")
        self.assertEqual(self._refusal(self._start()),
                         AFFORDABILITY_REASON_CUSTOMER_SPEND_POOL_EXCEEDED)

        # The pool's period turns over: the pool clears, nothing holds the
        # customer, the flag lifts and work may begin again.
        now = timezone.now()
        next_month = (now.replace(day=1) + datetime.timedelta(days=40)).replace(day=1)
        with mock.patch(DOORBELL), self.captureOnCommitCallbacks(execute=True):
            LiveCounter.reconcile(self.customer.id, self.tenant, now=next_month)
        self.assertEqual(StopSignalService.open_stop_lines(self.customer.id), [])
        self.assertFalse(LiveCounter.read(self.customer.id, self.tenant)["stop"])
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.status, "active")
        self.assertEqual(
            sorted(e.payload["reason_code"] for e in
                   self._events(StopCleared, owner_id=self.customer.id)),
            sorted([reasons.HARD_FLOOR, reasons.CUSTOMER_SPEND_POOL]))

    def test_the_drawdown_alone_opens_both_lines_when_the_live_lane_is_off(self):
        """The other lane, by name: with real-time counter maintenance off
        the recording route detects nothing, and the drawdown opens the
        floor's line and the pool's — once each — and stops the work."""
        self.tenant.live_counter_maintenance_enabled = False
        self.tenant.save(update_fields=["live_counter_maintenance_enabled"])
        pool = self._pool(self.customer, 5_000_000)
        unit = self._unit()

        ack = self._record(bills=5_000_000, task_id=unit)
        self.assertFalse(ack["stop"])
        self.assertEqual(Task.objects.get(id=unit).status, TASK_STATUS_ACTIVE)

        self._drain()

        self._both_open(pool)
        row = Task.objects.get(id=unit)
        self.assertEqual(row.status, TASK_STATUS_KILLED)
        self.assertEqual(row.metadata[STOP_CAUSE_KEY], reasons.CUSTOMER_SPEND_POOL)
        self.assertEqual(row.metadata[STOP_MECHANISM_KEY], TRIGGER_SOURCE_POOL_CROSSING)
        self.assertEqual(self._the_one(TaskKilled)["control_id"], str(pool.id))
        self.assertTrue(LiveCounter.read(self.customer.id, self.tenant)["stop"])
