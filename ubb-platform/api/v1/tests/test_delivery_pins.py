"""Delivery pin 12 (#43, spec §A): the doorbell never 5xxes the accept.

Broker down at accept — the durable row is written, the response is still 200,
and delivery happens via the minutely ``sweep_outbox`` (the outbox doorbell)
once the broker recovers. The post-commit ``.delay()`` is a latency
optimization, never a durability requirement, so a raise from it must be
swallowed + logged rather than surfacing a false error for money/events that
durably landed.
"""
import json
import uuid
from unittest.mock import patch

from django.core.cache import cache
from django.test import Client, TestCase

from apps.billing.wallets.models import Wallet
from apps.metering.pricing.tests._helpers import (
    a_rule_that_prices_what_it_measures, priced_at)
from apps.metering.usage.models import Posting
from apps.platform.customers.models import Customer
from apps.platform.events.models import OutboxEvent
from apps.platform.tenants.models import Tenant, TenantApiKey


class BrokerDownAtAcceptTest(TestCase):
    """Prepaid + enforcing tenant, one customer with a funded wallet, Redis
    DB-15 wiped between tests (``cache.clear()`` FLUSHDBs the dedicated test
    db — the idiom in apps/billing/gating/tests/test_live_counter.py).

    This fixture is the module's own. The pin rode the async ingest endpoint's
    shared base class until that route was deleted, and the second case here
    was a test *of that lane* — a dead broker costing settle latency — so it
    went with it. The at-least-once delivery guarantee is not part of what
    went: it is about the outbox, which every recording path still writes, and
    it keeps its proof below on a fixture that owns nothing it does not need.
    """

    def setUp(self):
        cache.clear()
        self.http_client = Client()
        self.tenant = Tenant.objects.create(
            name="Delivery", products=["metering", "billing"],
            billing_mode="prepaid", enforcement_mode="enforcing",
        )
        _, self.raw_key = TenantApiKey.create_key(self.tenant, label="test")
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="cust1")
        self.wallet = Wallet.objects.create(
            customer=self.customer, balance_micros=20_000_000)
        a_rule_that_prices_what_it_measures(self.tenant)

    def tearDown(self):
        cache.clear()

    def _auth(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {self.raw_key}"}

    def test_sync_record_with_broker_down_is_200_and_sweep_delivers(self):
        """The UsageRecorded row is durably written, the accept stays 200, and
        once the broker recovers the minutely sweep re-dispatches the
        still-pending row."""
        with patch("apps.platform.events.tasks.process_single_event") as mock_task:
            mock_task.delay.side_effect = ConnectionError("broker down")
            with self.captureOnCommitCallbacks(execute=True):
                resp = self.http_client.post(
                    "/api/v1/metering/usage",
                    data=json.dumps({
                        "customer_id": str(self.customer.id),
                        "request_id": f"req-{uuid.uuid4()}",
                        "idempotency_key": f"idem-{uuid.uuid4()}",
                        # Billed by the tenant's own rule now (#365).
                        "measurements": priced_at(1_000_000),
                    }),
                    content_type="application/json",
                    **self._auth(),
                )
        self.assertEqual(resp.status_code, 200)
        event_id = resp.json()["event_id"]
        self.assertTrue(Posting.objects.filter(id=event_id).exists())
        row = OutboxEvent.objects.get(
            event_type="usage.recorded", payload__event_id=event_id)
        self.assertEqual(row.status, "pending")

        # Broker recovers: the sweep re-dispatches the pending row.
        from apps.platform.events.tasks import sweep_outbox
        with patch("apps.platform.events.tasks.process_single_event") as recovered:
            sweep_outbox()
        dispatched = {c.args[0] for c in recovered.delay.call_args_list}
        self.assertIn(str(row.id), dispatched)
