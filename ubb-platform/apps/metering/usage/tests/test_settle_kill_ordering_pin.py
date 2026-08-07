"""#112 (D3): on the settle path, kills fire BEFORE the hold true-up.

This pin outlived the module it was written in. `test_settlement.py`'s subject
was raws produced by the deleted async ingest route, and every other case in it
reached that route through the endpoint suite's fixture — but this one never
did: it builds its own tenant, constructs the staging row directly, and calls
``UsageService.settle_raw`` itself. Its subject is an ordering invariant of code
that still ships, so it is split out here rather than deleted with the lane.

The settle path and the staging table both go in the ticket after next, and this
module goes with them. Until then the invariant it guards is live and pinned.
"""
from unittest.mock import patch

from django.core.cache import cache
from django.test import TransactionTestCase

from apps.billing.wallets.models import Wallet
from apps.metering.usage.models import RawIngestEvent
from apps.metering.usage.services.usage_service import UsageService
from apps.platform.customers.models import Customer
from apps.platform.tenants.models import Tenant
from apps.platform.work.models import Task


class SettleKillOrderingPinTest(TransactionTestCase):
    """Kill execution registers on the settle transaction's on_commit and must
    fire BEFORE the hold true-up that follows the atomic — the order the old
    inline kill loop guaranteed. This holds because settle_raw owns its
    transaction (settle_raw_events calls it with no ambient atomic); a future
    caller wrapping settle_raw in an ambient transaction would silently defer
    kills past the true-up and turn this red. TransactionTestCase: the ordering
    only exists under a real commit.
    """

    def setUp(self):
        cache.clear()
        self.tenant = Tenant.objects.create(
            name="KillOrder", products=["metering", "billing"],
            billing_mode="prepaid")
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="ko1")
        Wallet.objects.create(
            customer=self.customer, balance_micros=20_000_000)

    def tearDown(self):
        cache.clear()

    @patch("apps.platform.events.tasks.process_single_event")
    def test_kills_fire_before_the_hold_true_up(self, _dispatch):
        task = Task.objects.create(
            tenant=self.tenant, customer=self.customer, status="active",
            balance_snapshot_micros=20_000_000,
            provider_cost_limit_micros=1_000_000,
            billing_owner_id=self.customer.id)
        raw = RawIngestEvent.objects.create(
            tenant=self.tenant, customer=self.customer,
            billing_owner_id=self.customer.id, task_id=task.id,
            idempotency_key="ko-1",
            # The settle path reads the caller-supplied correlation id with a
            # default, and this pin is about ordering, so the payload carries
            # only what the kill and the true-up actually turn on. The retired
            # word that used to sit here may not reach into a new file while
            # its migration debt stands.
            payload={"provider_cost_micros": 2_000_000,
                     "billed_cost_micros": 500_000},
            estimate_micros=500_000, estimate_exact=True, held=True,
            status="pending")

        order = []
        with patch("apps.platform.work.services.TaskService.kill_and_announce",
                   side_effect=lambda *a, **k: order.append("kill")), \
             patch("apps.billing.queries.settle_ingest_hold",
                   side_effect=lambda *a, **k: order.append("true_up")):
            result = UsageService.settle_raw(raw)

        self.assertEqual(result, "settled")
        self.assertEqual(order, ["kill", "true_up"])
