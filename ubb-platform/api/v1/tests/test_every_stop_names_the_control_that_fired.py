"""Every stop names the control that fired (#458, slice 6 §1, §15; Testing
Decisions claim 10).

A webhook subscriber routes a stop to the control that caused it by reading
three fields — `control_family`, `control_id` and, where a ceiling fired,
`ceiling_basis` — never by parsing a name. Each case here drives a real lane
through the ROUTE and asserts the EMITTED outbox payload, never a hand-built
one: the kernel stamps the family from the one map in `core.controls`, the
caller passes the control's identity, and the announcement reads both back
off the row it just wrote.

The five shapes the criterion names:

  * a COGS-ceiling stop — `ceiling`, the declaration's id, `cost`; the
    tenant's own id where the unit runs undeclared on the tenant rung;
  * a silence-window and an absolute-deadline stop — `ceiling`, `time`;
  * a cascade kill — contained work carries its PARENT's family and id on
    its row (a cascade announces nothing: the parent's event is the one
    signal, which is #38's rule and not this ticket's);
  * a customer stop — `wallet_policy` with the row that carried the floor,
    or `customer_spend_pool` with the pool row, and NO ceiling basis (the
    customer pair does not carry the field: §15 puts it on the four terminal
    stops only, and "null" for a stop that was not a ceiling's is what its
    absence says here).

This module says "a unit of work", "contained work" and "the work"
throughout, on the retired-sense rule the registry records for the plural.
"""
import json
import uuid
from datetime import timedelta

from django.core.cache import cache
from django.test import Client, TestCase
from django.utils import timezone

from apps.billing.gating.models import CustomerSpendPool
from apps.billing.wallets.models import CustomerBillingProfile, Wallet
from apps.metering.pricing.tests._helpers import (
    a_rule_that_prices_what_it_measures, what_it_bills)
from apps.platform.customers.models import Customer
from apps.platform.event_types.tests._helpers import (
    DECLARED, declares_a_caller_supplied_cost)
from apps.platform.events.models import OutboxEvent
from apps.platform.events.schemas import (
    StopFired, SubtaskKilled, TaskExpired, TaskKilled)
from apps.platform.tenants.models import Tenant, TenantApiKey
from apps.platform.work import reasons
from apps.platform.work.models import (
    STOP_CAUSE_KEY, STOP_CONTROL_FAMILY_KEY, STOP_CONTROL_ID_KEY, Task,
    TaskType)
from apps.platform.work.services import TaskService
from apps.platform.work.tasks import reap_stale_tasks
from core.vocabulary import (
    CEILING_BASIS_COST, CEILING_BASIS_TIME, CONTROL_FAMILY_CEILING,
    CONTROL_FAMILY_CUSTOMER_SPEND_POOL, CONTROL_FAMILY_WALLET_POLICY,
    TASK_STATUS_KILLED, TASK_TYPE_KIND_SUBTASK, TASK_TYPE_KIND_TASK)


class EveryStopNamesItsControlTestBase(TestCase):
    def setUp(self):
        cache.clear()
        self.http_client = Client()
        self.tenant = Tenant.objects.create(
            name="Controls", products=["metering", "billing"],
            billing_mode="prepaid", enforcement_mode="enforcing")
        _, self.raw_key = TenantApiKey.create_key(self.tenant, label="t")
        self.customer = Customer.objects.create(tenant=self.tenant, external_id="c1")
        self.wallet = Wallet.objects.create(
            customer=self.customer, balance_micros=100_000_000)
        declares_a_caller_supplied_cost(self.tenant, DECLARED)
        a_rule_that_prices_what_it_measures(self.tenant)

    def tearDown(self):
        cache.clear()

    def _record(self, **extra):
        data = {"customer_id": str(self.customer.id),
                "idempotency_key": f"idem-{uuid.uuid4()}",
                "event_type": DECLARED}
        data.update(what_it_bills(extra))
        data.update(extra)
        # The ceiling's kill is registered on the recording transaction's
        # commit; a `TestCase` never commits, so the callbacks are run here.
        with self.captureOnCommitCallbacks(execute=True):
            response = self.http_client.post(
                "/api/v1/metering/usage", data=json.dumps(data),
                content_type="application/json",
                HTTP_AUTHORIZATION=f"Bearer {self.raw_key}")
        self.assertEqual(response.status_code, 200, response.json())
        return response.json()

    def _kind(self, key, *, kind=TASK_TYPE_KIND_TASK, ceiling=None, **windows):
        return TaskType.objects.create(
            tenant=self.tenant, key=key, kind=kind,
            task_cogs_ceiling_micros=ceiling, uncapped=ceiling is None,
            **windows)

    def _unit(self, *, ceiling=None, task_type="", parent=None):
        return TaskService.create_task(
            self.tenant, self.customer, balance_snapshot_micros=0,
            task_cogs_ceiling_micros=ceiling, task_type=task_type,
            parent=parent, billing_owner_id=self.customer.id)

    def _the_one(self, event_class):
        return OutboxEvent.objects.get(event_type=event_class.EVENT_TYPE).payload

    def _age(self, unit, *, created=None, reported=None):
        fields = {}
        if created is not None:
            fields["created_at"] = timezone.now() - created
        if reported is not None:
            fields["last_event_at"] = timezone.now() - reported
        Task.objects.filter(id=unit.id).update(**fields)


class ACeilingStopNamesTheDeclarationTest(EveryStopNamesItsControlTestBase):
    def test_a_cogs_ceiling_stop_under_a_declared_kind(self):
        kind = self._kind("summarise", ceiling=5_000_000)
        unit = self._unit(ceiling=5_000_000, task_type="summarise")

        self._record(task_id=str(unit.id), provider_cost_micros=5_000_000)

        payload = self._the_one(TaskKilled)
        self.assertEqual(payload["reason_code"], reasons.TASK_COGS_CEILING)
        self.assertEqual(payload["control_family"], CONTROL_FAMILY_CEILING)
        self.assertEqual(payload["control_id"], str(kind.id))
        self.assertEqual(payload["ceiling_basis"], CEILING_BASIS_COST)

    def test_an_undeclared_unit_on_the_tenant_rung_names_the_tenant(self):
        unit = self._unit(ceiling=5_000_000)

        self._record(task_id=str(unit.id), provider_cost_micros=5_000_000)

        payload = self._the_one(TaskKilled)
        self.assertEqual(payload["control_family"], CONTROL_FAMILY_CEILING)
        self.assertEqual(payload["control_id"], str(self.tenant.id))
        self.assertEqual(payload["ceiling_basis"], CEILING_BASIS_COST)

    def test_the_family_and_the_id_are_recorded_on_the_row_the_event_names(self):
        """What the re-mint reads back (§15): the row, not the caller."""
        kind = self._kind("summarise", ceiling=5_000_000)
        unit = self._unit(ceiling=5_000_000, task_type="summarise")

        self._record(task_id=str(unit.id), provider_cost_micros=5_000_000)

        unit.refresh_from_db()
        self.assertEqual(unit.metadata[STOP_CONTROL_FAMILY_KEY], CONTROL_FAMILY_CEILING)
        self.assertEqual(unit.metadata[STOP_CONTROL_ID_KEY], str(kind.id))
        self.assertEqual(unit.ceiling_basis, CEILING_BASIS_COST)


class AWindowStopIsTheCeilingsOnTimeTest(EveryStopNamesItsControlTestBase):
    def test_a_silence_window_stop(self):
        kind = self._kind("quiet", silence_window_seconds=60,
                          absolute_deadline_seconds=86_400)
        unit = self._unit(task_type="quiet")
        self._age(unit, created=timedelta(minutes=5), reported=timedelta(minutes=2))

        reap_stale_tasks()

        payload = self._the_one(TaskExpired)
        self.assertEqual(payload["reason_code"], reasons.SILENCE_WINDOW)
        self.assertEqual(payload["control_family"], CONTROL_FAMILY_CEILING)
        self.assertEqual(payload["control_id"], str(kind.id))
        self.assertEqual(payload["ceiling_basis"], CEILING_BASIS_TIME)

    def test_an_absolute_deadline_stop(self):
        kind = self._kind("bounded", silence_window_seconds=0,
                          absolute_deadline_seconds=60)
        unit = self._unit(task_type="bounded")
        self._age(unit, created=timedelta(minutes=5), reported=timedelta(seconds=1))

        reap_stale_tasks()

        payload = self._the_one(TaskExpired)
        self.assertEqual(payload["reason_code"], reasons.ABSOLUTE_DEADLINE)
        self.assertEqual(payload["control_family"], CONTROL_FAMILY_CEILING)
        self.assertEqual(payload["control_id"], str(kind.id))
        self.assertEqual(payload["ceiling_basis"], CEILING_BASIS_TIME)


class ACascadeCarriesTheParentsControlTest(EveryStopNamesItsControlTestBase):
    def test_contained_work_killed_with_its_parent_records_the_parents_family_and_id(self):
        kind = self._kind("pipeline", ceiling=5_000_000)
        self._kind("piece", kind=TASK_TYPE_KIND_SUBTASK)
        parent = self._unit(ceiling=5_000_000, task_type="pipeline")
        contained = self._unit(task_type="piece", parent=parent)

        # The contained unit's report rolls up and crosses the PARENT's
        # ceiling: the parent is the kill target and the cascade takes the
        # contained work with it, silently.
        self._record(task_id=str(contained.id), provider_cost_micros=5_000_000)

        contained.refresh_from_db()
        parent.refresh_from_db()
        self.assertEqual(parent.status, TASK_STATUS_KILLED)
        self.assertEqual(contained.status, TASK_STATUS_KILLED)
        self.assertEqual(contained.metadata[STOP_CAUSE_KEY], reasons.PARENT_KILLED)
        self.assertEqual(contained.metadata[STOP_CONTROL_FAMILY_KEY],
                         CONTROL_FAMILY_CEILING)
        self.assertEqual(contained.metadata[STOP_CONTROL_ID_KEY], str(kind.id))
        # A cascade's word is nobody's ceiling: no basis on the contained row.
        self.assertIsNone(contained.ceiling_basis)
        # The parent's announcement is the one signal; the contained piece
        # announced nothing and so a subscriber learns the control from it.
        payload = self._the_one(TaskKilled)
        self.assertEqual(payload["task_id"], str(parent.id))
        self.assertEqual(payload["control_id"], str(kind.id))
        self.assertFalse(OutboxEvent.objects.filter(
            event_type=SubtaskKilled.EVENT_TYPE).exists())


class ACustomerStopNamesItsControlTest(EveryStopNamesItsControlTestBase):
    def test_the_wallet_floor_names_the_row_that_carried_it(self):
        profile = CustomerBillingProfile.objects.create(
            customer=self.customer, min_balance_micros=0)
        self.wallet.balance_micros = 1_000_000
        self.wallet.save(update_fields=["balance_micros"])

        ack = self._record(provider_cost_micros=1_000, bills=2_000_000)

        self.assertTrue(ack["stop"])
        payload = self._the_one(StopFired)
        self.assertEqual(payload["reason_code"], reasons.HARD_FLOOR)
        self.assertEqual(payload["control_family"], CONTROL_FAMILY_WALLET_POLICY)
        self.assertEqual(payload["control_id"], str(profile.id))
        self.assertNotIn("ceiling_basis", payload)

    def test_the_wallet_floor_names_the_tenants_configuration_where_no_override_exists(self):
        from apps.billing.queries import get_billing_config
        config = get_billing_config(self.tenant.id)
        self.wallet.balance_micros = 1_000_000
        self.wallet.save(update_fields=["balance_micros"])

        self._record(provider_cost_micros=1_000, bills=2_000_000)

        payload = self._the_one(StopFired)
        self.assertEqual(payload["control_family"], CONTROL_FAMILY_WALLET_POLICY)
        self.assertEqual(payload["control_id"], str(config.id))

    def test_the_pool_names_the_pool_row(self):
        self.tenant.billing_mode = "postpaid"
        self.tenant.save(update_fields=["billing_mode"])
        pool = CustomerSpendPool.objects.create(
            tenant=self.tenant, customer=self.customer,
            cap_micros=1_000_000, enforce_mode="blocking")

        ack = self._record(provider_cost_micros=1_000, bills=2_000_000)

        self.assertTrue(ack["stop"])
        payload = self._the_one(StopFired)
        self.assertEqual(payload["reason_code"], reasons.CUSTOMER_SPEND_POOL)
        self.assertEqual(payload["control_family"],
                         CONTROL_FAMILY_CUSTOMER_SPEND_POOL)
        self.assertEqual(payload["control_id"], str(pool.id))
        self.assertNotIn("ceiling_basis", payload)
