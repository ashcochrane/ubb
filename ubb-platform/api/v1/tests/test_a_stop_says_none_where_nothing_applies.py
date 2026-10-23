"""A stop says null where nothing applies, never 0 (#610, ADR-0013 §5).

Two figures rode the stop webhooks as `0` where nothing applied:

  * `task_cogs_ceiling_micros` on the four terminal stops — `task.killed`,
    `task.expired` and their contained-work pair — for a unit with NO ceiling.
    A time window and a customer-wide stop reach uncapped work too, and a real
    ceiling can never be `0` (a start and a declaration both refuse one), so
    the `0` could only ever mean "none" while reading as "a ceiling of nothing".
  * `balance_micros` on `customer.suspended` and `customer.stop_cleared` for a
    customer with NO wallet balance — a postpaid customer, a Pool-line stop on
    one, a pooled seat — where `0` reads as a wallet emptied to nothing.

Each case drives a real producing lane and asserts the EMITTED outbox payload:
the fresh announcement on every lane that reaches the field, and the patrol's
re-mint, which rebuilds a dead-lettered announcement from the record and is the
second place each `0` was spelled. Beside each null, a pin that a real figure
travels unchanged — a fix that nulled every figure would satisfy the nulls.

This module says "a unit of work", "contained work" and "the work" throughout,
on the retired-sense rule the registry records for the plural.
"""
from datetime import timedelta

from apps.billing.gating.models import CustomerSpendPool
from apps.billing.gating.patrol import (
    remint_unannounced_kills, remint_unannounced_signals)
from apps.billing.gating.services.live_counter import LiveCounter
from apps.billing.gating.services.stop_signal_service import announced_balance
from apps.billing.wallets.models import CustomerBillingProfile, Wallet
from apps.platform.customers.models import Customer
from apps.platform.events.models import OutboxEvent
from apps.platform.events.schemas import (
    CustomerStopCleared, CustomerSuspended, SubtaskExpired, TaskExpired, TaskKilled)
from apps.platform.tenants.models import Tenant
from apps.platform.work.tasks import reap_stale_tasks
from api.v1.tests.test_every_stop_names_the_control_that_fired import (
    EveryStopNamesItsControlTestBase)
from core.vocabulary import (
    CUSTOMER_BILLING_MODE_PREPAID, TASK_TYPE_KIND_SUBTASK)

CEILING = "task_cogs_ceiling_micros"
BALANCE = "balance_micros"


class StopTestBase(EveryStopNamesItsControlTestBase):

    def _payloads(self, event_class):
        return [event.payload for event in OutboxEvent.objects.filter(
            event_type=event_class.EVENT_TYPE).order_by("created_at")]

    def _dead_letter(self, event_class):
        """The announcement's delivery failed for good, which is what makes
        the patrol re-mint it."""
        OutboxEvent.objects.filter(
            event_type=event_class.EVENT_TYPE).update(status="failed")

    def _re_minted(self, event_class):
        [payload] = [p for p in self._payloads(event_class)
                     if p["re_announcement"]]
        return payload

    def _postpaid(self):
        self.tenant.billing_mode = "postpaid"
        self.tenant.save(update_fields=["billing_mode"])

    def _a_blocking_pool(self, cap_micros=1_000_000):
        return CustomerSpendPool.objects.create(
            tenant=self.tenant, customer=self.customer,
            cap_micros=cap_micros, enforce_mode="blocking")


class AnAbsentCeilingIsNullTest(StopTestBase):
    """Item 1 — every lane that reaches an uncapped unit, and the re-mint."""

    def test_an_expiry_of_uncapped_work_publishes_no_ceiling(self):
        self._kind("open-ended", silence_window_seconds=0,
                   absolute_deadline_seconds=60)
        unit = self._unit(task_type="open-ended")
        self._age(unit, created=timedelta(minutes=5))

        reap_stale_tasks()

        [payload] = self._payloads(TaskExpired)
        self.assertEqual(payload["task_id"], str(unit.id))
        self.assertIn(CEILING, payload)
        self.assertIsNone(payload[CEILING])

    def test_contained_uncapped_work_expiring_alone_publishes_no_ceiling(self):
        self._kind("pipeline", silence_window_seconds=0,
                   absolute_deadline_seconds=86_400)
        self._kind("piece", kind=TASK_TYPE_KIND_SUBTASK,
                   silence_window_seconds=60, absolute_deadline_seconds=86_400)
        parent = self._unit(task_type="pipeline")
        contained = self._unit(task_type="piece", parent=parent)
        self._age(contained, created=timedelta(minutes=5),
                  reported=timedelta(minutes=2))

        reap_stale_tasks()

        [payload] = self._payloads(SubtaskExpired)
        self.assertEqual(payload["subtask_id"], str(contained.id))
        self.assertIsNone(payload[CEILING])

    def test_a_pool_stop_reaching_uncapped_work_publishes_no_ceiling(self):
        self._a_blocking_pool()
        unit = self._unit()

        self._record(provider_cost_micros=1_000, bills=2_000_000)

        [payload] = self._payloads(TaskKilled)
        self.assertEqual(payload["task_id"], str(unit.id))
        self.assertIsNone(payload[CEILING])

    def test_the_patrols_re_mint_publishes_no_ceiling(self):
        self._a_blocking_pool()
        self._unit()
        self._record(provider_cost_micros=1_000, bills=2_000_000)
        self._dead_letter(TaskKilled)

        self.assertEqual(remint_unannounced_kills(self.tenant), 1)

        self.assertIsNone(self._re_minted(TaskKilled)[CEILING])

    def test_a_real_ceiling_is_published_unchanged_on_both_lanes(self):
        unit = self._unit(ceiling=5_000_000)
        self._record(task_id=str(unit.id), provider_cost_micros=5_000_000)
        [fresh] = self._payloads(TaskKilled)
        self._dead_letter(TaskKilled)

        remint_unannounced_kills(self.tenant)

        self.assertEqual(fresh[CEILING], 5_000_000)
        self.assertEqual(self._re_minted(TaskKilled)[CEILING], 5_000_000)


class AnAbsentWalletBalanceIsNullTest(StopTestBase):
    """Item 2 — the customer stop pair, on every lane that announces it."""

    def test_a_postpaid_customers_pool_stop_and_its_clearing_publish_no_balance(self):
        """The customer HAS a wallet row here (the fixture's) and still holds
        no wallet balance: a postpaid tenant's customers are not prepaid, so
        the rule reads the mode, never whether a row happens to exist."""
        self._postpaid()
        pool = self._a_blocking_pool()

        self._record(provider_cost_micros=1_000, bills=2_000_000)
        pool.cap_micros = 10_000_000
        pool.save(update_fields=["cap_micros"])
        LiveCounter.reconcile(self.customer.id, self.tenant)

        [suspended] = self._payloads(CustomerSuspended)
        [cleared] = self._payloads(CustomerStopCleared)
        self.assertIn(BALANCE, suspended)
        self.assertIsNone(suspended[BALANCE])
        self.assertIsNone(cleared[BALANCE])

    def test_the_patrols_re_mint_of_a_postpaid_clearing_publishes_no_balance(self):
        self._postpaid()
        pool = self._a_blocking_pool()
        self._record(provider_cost_micros=1_000, bills=2_000_000)
        pool.cap_micros = 10_000_000
        pool.save(update_fields=["cap_micros"])
        LiveCounter.reconcile(self.customer.id, self.tenant)
        self._dead_letter(CustomerStopCleared)

        self.assertEqual(remint_unannounced_signals(self.tenant), 1)

        self.assertIsNone(self._re_minted(CustomerStopCleared)[BALANCE])

    def test_a_prepaid_floor_stop_publishes_the_balance_it_crossed_at(self):
        """THE REAL FIGURE, unchanged: the drawdown the floor stopped on."""
        CustomerBillingProfile.objects.create(
            customer=self.customer, min_balance_micros=0)
        self.wallet.balance_micros = 1_000_000
        self.wallet.save(update_fields=["balance_micros"])

        self._record(provider_cost_micros=1_000, bills=2_000_000)

        [suspended] = self._payloads(CustomerSuspended)
        self.assertEqual(suspended[BALANCE], -1_000_000)

    def test_a_prepaid_pool_stop_the_hourly_pass_opened_publishes_the_wallets_balance(self):
        """The pool pass measures spend and passed a literal `0` for the
        balance; a prepaid customer HAS one, so that `0` was a balance nobody
        had read. The pass now names none and the door reads the wallet's."""
        self.tenant.live_counter_maintenance_enabled = False
        self.tenant.save(update_fields=["live_counter_maintenance_enabled"])
        self.wallet.balance_micros = 37_000_000
        self.wallet.save(update_fields=["balance_micros"])
        self._a_blocking_pool()
        self._record(provider_cost_micros=1_000, bills=2_000_000)
        self.assertFalse(self._payloads(CustomerSuspended),
                         "with live maintenance off the recording opens nothing")

        LiveCounter.reconcile(self.customer.id, self.tenant)

        [suspended] = self._payloads(CustomerSuspended)
        self.assertEqual(
            suspended[BALANCE],
            Wallet.objects.get(customer=self.customer).balance_micros)
        self.assertNotIn(suspended[BALANCE], (None, 0))


class TheRuleReadsWhoHoldsAWalletTest(StopTestBase):
    """`announced_balance` is the one rule both doors and the re-mint apply;
    the customers no lane above reaches cheaply are asked of it directly."""

    def test_a_pooled_seat_holds_no_wallet_of_its_own(self):
        business = Customer.objects.create(
            tenant=self.tenant, external_id="biz", account_type="business",
            billing_topology="pooled")
        seat = Customer.objects.create(
            tenant=self.tenant, external_id="seat", account_type="seat",
            parent=business)
        Wallet.objects.create(customer=business, balance_micros=5_000_000)

        self.assertIsNone(announced_balance(seat.id, self.tenant,
                                            measured=5_000_000))
        self.assertEqual(announced_balance(business.id, self.tenant),
                         5_000_000)

    def test_a_tenant_that_holds_no_prepaid_wallets_says_none(self):
        """Every mode the tenant column admits but prepaid — read off the
        column, so a mode added or renamed there is asked here too."""
        modes = {value for value, _ in
                 Tenant._meta.get_field("billing_mode").choices}
        self.assertIn(CUSTOMER_BILLING_MODE_PREPAID, modes)
        for mode in sorted(modes - {CUSTOMER_BILLING_MODE_PREPAID}):
            with self.subTest(mode=mode):
                self.tenant.billing_mode = mode
                self.assertIsNone(announced_balance(
                    self.customer.id, self.tenant, measured=100_000_000))

    def test_a_measured_balance_wins_over_the_durable_one(self):
        self.assertEqual(announced_balance(self.customer.id, self.tenant,
                                           measured=-1_000_000), -1_000_000)
        self.assertEqual(announced_balance(self.customer.id, self.tenant),
                         100_000_000)
