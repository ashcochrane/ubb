"""Billing's two reads behind the spend-control reports (#465, slice 6 §14):
the customer-wide signal families' episodes off the ledger and the outbox
pair, by constant, and the pool's utilisation as the status pair — plain data
through `apps.billing.queries`, joined by the composition layer and by
nothing here.

WHERE AN EPISODE COMES FROM. Each ledger line's history is the outbox pair it
announced — `customer.stopped` / `customer.stop_cleared` for the two stop
lines, told apart by the word each carries; the soft floor's own pair for the
wind-down line — read by the payload classes' constants and never a spelled
name (#464). The ledger row backstops the pair: an open episode survives the
outbox's retention because the row still says `stopped`, and a cleared one
whose clearing announcement aged out is closed by the row's own instant. A
row's balance at the crossing is what the suspension announced beside the
stop (the stop pair carries none); the soft floor's pair carries its own.
"""
from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from apps.billing import queries
from apps.billing.gating.models import CustomerSpendPool, StopSignalState
from apps.billing.gating.services.stop_signal_service import (
    CLEAR_BALANCE_RECOVERED, StopSignalService, control_id_of)
from apps.billing.tenant_billing.models import BillingTenantConfig
from apps.platform.customers.models import Customer
from apps.platform.events.models import OutboxEvent
from apps.platform.events.schemas import (
    SoftFloorCleared, SoftFloorCrossed, StopCleared, StopFired)
from apps.platform.tenants.models import Tenant
from apps.platform.work import reasons
from core.crossing import month_label_bounds
from core.vocabulary import (
    CONTROL_FAMILY_CUSTOMER_SPEND_POOL, CONTROL_FAMILY_WALLET_POLICY,
    SPEND_POOL_ENFORCE_MODE_BLOCKING)

FLOOR = 5_000_000


class SignalEpisodesTestBase(TestCase):
    def setUp(self):
        cache.clear()
        self.tenant = Tenant.objects.create(
            name="T", products=["metering", "billing"], billing_mode="prepaid",
            enforcement_mode="enforcing")
        BillingTenantConfig.objects.create(tenant=self.tenant, min_balance_micros=FLOOR)
        self.owner = Customer.objects.create(tenant=self.tenant, external_id="c1")

    def tearDown(self):
        cache.clear()

    def _stop(self, line, *, owner=None, balance_micros=-6_000_000):
        owner = owner or self.owner
        return StopSignalService.drive_stop(
            owner.id, self.tenant, line=line,
            control_id=control_id_of(line, owner.id, self.tenant),
            balance_micros=balance_micros)

    def _clear(self, line, *, owner=None):
        owner = owner or self.owner
        return StopSignalService.drive_clear(
            owner.id, self.tenant, line=line, clear_reason=CLEAR_BALANCE_RECOVERED)

    def _rows(self, **filters):
        return queries.signal_episodes(self.tenant.id, **filters)


class TheTwoStopLinesTest(SignalEpisodesTestBase):
    def test_a_hard_floor_episode_carries_its_control_floor_balance_and_both_instants(self):
        self.assertEqual(self._stop(reasons.HARD_FLOOR), 1)
        self.assertEqual(self._clear(reasons.HARD_FLOOR), 1)
        fired = OutboxEvent.objects.get(event_type=StopFired.EVENT_TYPE)
        cleared = OutboxEvent.objects.get(event_type=StopCleared.EVENT_TYPE)

        [row] = self._rows()
        self.assertEqual(row["control_family"], CONTROL_FAMILY_WALLET_POLICY)
        self.assertEqual(row["reason_code"], reasons.HARD_FLOOR)
        self.assertFalse(row["soft_floor"])
        self.assertEqual(row["owner_id"], str(self.owner.id))
        self.assertEqual(row["episode_seq"], 1)
        self.assertEqual(row["control_id"],
                         str(control_id_of(reasons.HARD_FLOOR, self.owner.id, self.tenant)))
        self.assertEqual(row["opened_at"], fired.created_at)
        self.assertEqual(row["closed_at"], cleared.created_at)
        self.assertEqual(row["floor_micros"], FLOOR)
        self.assertEqual(row["balance_at_crossing_micros"], -6_000_000)
        self.assertIsNone(row["cap_micros"])
        self.assertIsNone(row["period"])

    def test_a_pool_episode_carries_the_pool_amount_and_its_period(self):
        pool = CustomerSpendPool.objects.create(
            tenant=self.tenant, customer=self.owner, cap_micros=100_000_000,
            enforce_mode=SPEND_POOL_ENFORCE_MODE_BLOCKING)
        self.assertEqual(self._stop(reasons.CUSTOMER_SPEND_POOL), 1)

        [row] = self._rows()
        self.assertEqual(row["control_family"], CONTROL_FAMILY_CUSTOMER_SPEND_POOL)
        self.assertEqual(row["reason_code"], reasons.CUSTOMER_SPEND_POOL)
        self.assertEqual(row["control_id"], str(pool.id))
        self.assertEqual(row["cap_micros"], 100_000_000)
        self.assertEqual(row["period"], month_label_bounds(row["opened_at"])[0])
        self.assertIsNone(row["closed_at"])
        self.assertIsNone(row["floor_micros"])

    def test_two_lines_open_at_once_are_two_rows_with_their_own_episodes(self):
        CustomerSpendPool.objects.create(
            tenant=self.tenant, customer=self.owner, cap_micros=1,
            enforce_mode=SPEND_POOL_ENFORCE_MODE_BLOCKING)
        self._stop(reasons.HARD_FLOOR)
        self._clear(reasons.HARD_FLOOR)
        self._stop(reasons.HARD_FLOOR)
        self._stop(reasons.CUSTOMER_SPEND_POOL)

        rows = {(r["reason_code"], r["episode_seq"]): r for r in self._rows()}
        self.assertEqual(set(rows), {(reasons.HARD_FLOOR, 1), (reasons.HARD_FLOOR, 2),
                                     (reasons.CUSTOMER_SPEND_POOL, 1)})
        self.assertIsNotNone(rows[(reasons.HARD_FLOOR, 1)]["closed_at"])
        self.assertIsNone(rows[(reasons.HARD_FLOOR, 2)]["closed_at"])

    def test_the_ledger_backstops_an_open_episode_whose_announcement_aged_out(self):
        self._stop(reasons.HARD_FLOOR)
        OutboxEvent.objects.all().delete()
        state = StopSignalState.objects.get(owner=self.owner, reason=reasons.HARD_FLOOR)

        [row] = self._rows()
        self.assertEqual(row["opened_at"], state.transitioned_at)
        self.assertIsNone(row["closed_at"])
        self.assertIsNone(row["balance_at_crossing_micros"])

    def test_the_ledger_closes_a_cleared_episode_whose_clearing_aged_out(self):
        self._stop(reasons.HARD_FLOOR)
        self._clear(reasons.HARD_FLOOR)
        OutboxEvent.objects.filter(event_type=StopCleared.EVENT_TYPE).delete()
        state = StopSignalState.objects.get(owner=self.owner, reason=reasons.HARD_FLOOR)

        [row] = self._rows()
        self.assertEqual(row["closed_at"], state.transitioned_at)

    def test_the_owner_filter_and_the_window_each_narrow(self):
        other = Customer.objects.create(tenant=self.tenant, external_id="c2")
        self._stop(reasons.HARD_FLOOR)
        self._stop(reasons.HARD_FLOOR, owner=other)
        opened = [r["opened_at"] for r in self._rows()]

        self.assertEqual(len(self._rows()), 2)
        self.assertEqual([r["owner_id"] for r in self._rows(owner_ids={other.id})],
                         [str(other.id)])
        self.assertEqual(len(self._rows(owner_ids={other.id, self.owner.id})), 2)
        self.assertEqual(self._rows(since=timezone.now()), [])
        self.assertEqual(self._rows(until=min(opened)), [])
        self.assertEqual(len(self._rows(since=min(opened))), 2)

    def test_another_tenants_episodes_are_not_this_tenants(self):
        elsewhere = Tenant.objects.create(
            name="E", products=["metering", "billing"], billing_mode="prepaid",
            enforcement_mode="enforcing")
        BillingTenantConfig.objects.create(tenant=elsewhere, min_balance_micros=1)
        theirs = Customer.objects.create(tenant=elsewhere, external_id="e1")
        StopSignalService.drive_stop(
            theirs.id, elsewhere, line=reasons.HARD_FLOOR,
            control_id=control_id_of(reasons.HARD_FLOOR, theirs.id, elsewhere))
        self.assertEqual(self._rows(), [])


class TheWindDownLineTest(SignalEpisodesTestBase):
    def test_a_soft_floor_row_is_a_marker_with_the_pairs_own_figures_and_no_stop_word(self):
        self.assertEqual(StopSignalService.drive_soft_crossed(
            self.owner.id, self.tenant, balance_micros=-1_500_000,
            soft_min_balance_micros=1_000_000), 1)
        self.assertEqual(StopSignalService.drive_soft_cleared(
            self.owner.id, self.tenant, reason=CLEAR_BALANCE_RECOVERED,
            balance_micros=4_000_000, soft_min_balance_micros=1_000_000), 1)
        crossed = OutboxEvent.objects.get(event_type=SoftFloorCrossed.EVENT_TYPE)
        cleared = OutboxEvent.objects.get(event_type=SoftFloorCleared.EVENT_TYPE)

        [row] = self._rows()
        self.assertEqual(row["control_family"], CONTROL_FAMILY_WALLET_POLICY)
        self.assertIsNone(row["reason_code"])
        self.assertTrue(row["soft_floor"])
        self.assertIsNone(row["control_id"])
        self.assertEqual(row["episode_seq"], 1)
        self.assertEqual(row["opened_at"], crossed.created_at)
        self.assertEqual(row["closed_at"], cleared.created_at)
        self.assertEqual(row["floor_micros"], 1_000_000)
        self.assertEqual(row["balance_at_crossing_micros"], -1_500_000)


class PoolUtilisationTest(SignalEpisodesTestBase):
    def test_a_customer_with_no_pool_answers_no_pool(self):
        answer = queries.customer_spend_pool_utilisation(self.tenant.id, self.owner.id)
        self.assertEqual(answer["cap_micros"], 0)
        self.assertIsNone(answer["used_percentage"])
        self.assertIsNone(answer["remaining_micros"])
        self.assertFalse(answer["blocking_occurred"])
        self.assertEqual(answer["known_period_charges_micros"], 0)
        self.assertEqual(answer["unresolved_posting_count"], 0)

    def test_a_declared_pool_is_assessed_over_the_durable_pair(self):
        CustomerSpendPool.objects.create(
            tenant=self.tenant, customer=self.owner, cap_micros=100_000_000,
            enforce_mode=SPEND_POOL_ENFORCE_MODE_BLOCKING)
        answer = queries.customer_spend_pool_utilisation(self.tenant.id, self.owner.id)
        self.assertEqual(answer["cap_micros"], 100_000_000)
        self.assertEqual(answer["enforce_mode"], SPEND_POOL_ENFORCE_MODE_BLOCKING)
        self.assertEqual(answer["period"], month_label_bounds(timezone.now())[0])
        self.assertEqual(answer["used_percentage"], 0)
        self.assertEqual(answer["remaining_micros"], 100_000_000)
        self.assertIsNone(answer["highest_threshold_reached"])
        self.assertFalse(answer["blocking_occurred"])
        self.assertEqual(set(answer), {
            "period", "cap_micros", "enforce_mode", "known_period_charges_micros",
            "unresolved_posting_count", "used_percentage", "remaining_micros",
            "highest_threshold_reached", "blocking_occurred"})
