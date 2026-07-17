"""Delivery pin 12 (#43, spec §A): the doorbell never 5xxes the accept.

Broker down at accept — the durable row is written, the response is still
200, and delivery happens via the minutely ``sweep_outbox`` (outbox doorbell)
or the 10s settle beat (async ingest doorbell) once the broker recovers. The
post-commit ``.delay()`` is a latency optimization, never a durability
requirement, so a raise from it must be swallowed + logged rather than
surfacing a false error for money/events that durably landed.
"""
import json
import uuid
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, Client

from apps.platform.tenants.models import Tenant, TenantApiKey
from apps.platform.customers.models import Customer
from apps.platform.events.models import OutboxEvent
from apps.billing.wallets.models import Wallet
from apps.metering.usage.models import RawIngestEvent, UsageEvent


class BrokerDownAtAcceptTest(TestCase):
    """Same fixture idiom as test_ingest_endpoint.py: prepaid + enforcing
    tenant, funded wallet, Redis DB-15 wiped via cache.clear()."""

    def setUp(self):
        cache.clear()
        from api.v1 import metering_endpoints
        metering_endpoints._TASK_META_CACHE.clear()
        self.http_client = Client()
        self.tenant = Tenant.objects.create(
            name="BrokerDown", products=["metering", "billing", "metering_async"],
            billing_mode="prepaid", enforcement_mode="enforcing",
        )
        self.key_obj, self.raw_key = TenantApiKey.create_key(self.tenant, label="test")
        self.customer = Customer.objects.create(tenant=self.tenant, external_id="cust1")
        self.wallet = Wallet.objects.create(customer=self.customer, balance_micros=20_000_000)

    def tearDown(self):
        cache.clear()

    def _auth(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {self.raw_key}"}

    def test_sync_record_with_broker_down_is_200_and_sweep_delivers(self):
        """The outbox doorbell leg: the UsageRecorded row is durably written,
        the accept stays 200, and once the broker recovers the minutely sweep
        re-dispatches the still-pending row."""
        with patch("apps.platform.events.tasks.process_single_event") as mock_task:
            mock_task.delay.side_effect = ConnectionError("broker down")
            with self.captureOnCommitCallbacks(execute=True):
                resp = self.http_client.post(
                    "/api/v1/metering/usage",
                    data=json.dumps({
                        "customer_id": str(self.customer.id),
                        "request_id": f"req-{uuid.uuid4()}",
                        "idempotency_key": f"idem-{uuid.uuid4()}",
                        "billed_cost_micros": 1_000_000,
                    }),
                    content_type="application/json",
                    **self._auth(),
                )
        self.assertEqual(resp.status_code, 200)
        event_id = resp.json()["event_id"]
        self.assertTrue(UsageEvent.objects.filter(id=event_id).exists())
        row = OutboxEvent.objects.get(
            event_type="usage.recorded", payload__event_id=event_id)
        self.assertEqual(row.status, "pending")

        # Broker recovers: the sweep re-dispatches the pending row.
        from apps.platform.events.tasks import sweep_outbox
        with patch("apps.platform.events.tasks.process_single_event") as recovered:
            sweep_outbox()
        dispatched = {c.args[0] for c in recovered.delay.call_args_list}
        self.assertIn(str(row.id), dispatched)

    def test_async_ingest_with_broker_down_is_200_and_raws_land(self):
        """The settle doorbell leg: the raw rows are the queue (the 10s beat
        sweep is their guaranteed path); a dead broker at accept costs settle
        latency, never a 5xx for a durably accepted batch."""
        with patch("apps.metering.usage.tasks.settle_raw_events") as mock_settle:
            mock_settle.delay.side_effect = ConnectionError("broker down")
            with self.captureOnCommitCallbacks(execute=True):
                resp = self.http_client.post(
                    "/api/v1/metering/usage/ingest",
                    data=json.dumps({"events": [{
                        "customer_id": str(self.customer.id),
                        "request_id": f"req-{uuid.uuid4()}",
                        "idempotency_key": f"idem-{uuid.uuid4()}",
                        "billed_cost_micros": 1_000_000,
                    }]}),
                    content_type="application/json",
                    **self._auth(),
                )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["accepted"], 1)
        raw = RawIngestEvent.objects.get()
        self.assertEqual(raw.status, "pending")
