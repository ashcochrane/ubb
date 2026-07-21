"""Representative record() sites fire through real HTTP (#82, ADR-004 §4).

The sweep pin (test_audit_sweep) proves every mutating route *declares* an audit
action; these prove the wiring actually writes a ledger entry — one per bucket
the sweep covers: hand-moved money (tenant principal), a widget-initiated top-up
(actor kind ``end_customer``), and that secrets never reach the metadata.
"""
import json

from django.test import Client, TestCase

from apps.platform.audit.models import AuditRecord
from apps.platform.customers.models import Customer
from apps.platform.tenants.models import Tenant, TenantApiKey
from apps.billing.wallets.models import Wallet
from core.widget_auth import create_widget_token


class MoneyRecordThroughHttpTest(TestCase):
    def setUp(self):
        self.http = Client()
        self.tenant = Tenant.objects.create(name="Acme", products=["metering", "billing"])
        self.key_obj, self.key = TenantApiKey.create_key(self.tenant, label="primary")
        self.customer = Customer.objects.create(tenant=self.tenant, external_id="c1")
        Wallet.objects.create(customer=self.customer)

    def _hdr(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {self.key}"}

    def test_credit_records_wallet_credited_with_api_key_actor(self):
        resp = self.http.post(
            "/api/v1/billing/credit",
            data=json.dumps({"customer_id": "c1", "amount_micros": 5_000_000,
                             "source": "goodwill", "reference": "ref-1",
                             "idempotency_key": "cr-1"}),
            content_type="application/json", **self._hdr())
        self.assertEqual(resp.status_code, 200)
        rec = AuditRecord.objects.get(action="wallet.credited")
        self.assertEqual(rec.actor_kind, "api_key")
        self.assertEqual(rec.actor_display, "primary")
        self.assertEqual(rec.tenant_id, self.tenant.id)
        self.assertEqual(rec.metadata["amount_micros"], 5_000_000)
        self.assertEqual(rec.metadata["source"], "goodwill")

    def test_credit_replay_records_once(self):
        body = json.dumps({"customer_id": "c1", "amount_micros": 5_000_000,
                           "source": "goodwill", "reference": "ref-2",
                           "idempotency_key": "cr-2"})
        for _ in range(2):  # same idempotency key twice
            self.http.post("/api/v1/billing/credit", data=body,
                           content_type="application/json", **self._hdr())
        self.assertEqual(
            AuditRecord.objects.filter(action="wallet.credited").count(), 1)


class WidgetTopUpActorTest(TestCase):
    def setUp(self):
        self.http = Client()
        # No Stripe connector => the top-up takes the event branch (no Stripe).
        self.tenant = Tenant.objects.create(name="Acme", products=["metering", "billing"])
        self.customer = Customer.objects.create(tenant=self.tenant, external_id="c1")
        Wallet.objects.create(customer=self.customer)
        self.token = create_widget_token(
            self.tenant.widget_secret, str(self.customer.id), str(self.tenant.id))

    def test_widget_top_up_records_end_customer_actor(self):
        resp = self.http.post(
            "/api/v1/me/top-up",
            data=json.dumps({"amount_micros": 1_000_000,
                             "success_url": "https://ok", "cancel_url": "https://no",
                             "idempotency_key": "tu-1"}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.token}")
        self.assertEqual(resp.status_code, 202)
        rec = AuditRecord.objects.get(action="top_up.requested")
        self.assertEqual(rec.actor_kind, "end_customer")
        self.assertEqual(rec.actor_display, "c1")  # the tenant's handle
        self.assertEqual(rec.metadata["trigger"], "widget")
        self.assertEqual(rec.metadata["amount_micros"], 1_000_000)


class WebhookSecretNeverAuditedTest(TestCase):
    def setUp(self):
        self.http = Client()
        self.tenant = Tenant.objects.create(name="Acme", products=["metering", "billing"])
        self.key_obj, self.key = TenantApiKey.create_key(self.tenant, label="primary")

    def test_webhook_config_create_never_records_the_secret(self):
        secret = "s" * 40  # a signing secret that must never reach the ledger
        resp = self.http.post(
            "/api/v1/webhooks/configs",
            data=json.dumps({"url": "https://example.com/hook", "secret": secret,
                             "event_types": ["*"], "is_active": True}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.key}")
        self.assertEqual(resp.status_code, 201)
        rec = AuditRecord.objects.get(action="webhook_config.created")
        self.assertEqual(rec.metadata["url"], "https://example.com/hook")
        self.assertNotIn(secret, json.dumps(rec.metadata))
        self.assertNotIn("secret", rec.metadata)
