"""Two published value sets R10-W4 declared, held where a caller meets them.

**Why a usage invoice was skipped** is the registry's closed `skip_reason`. It
was a bare string, and every invoice that was NOT skipped published it as `""` —
a value the declared set does not hold. It applies only to a skipped invoice, so
it is null on every other one, and required (never absent) on both reads.

**A referral programme's reward type** is the registry's closed `reward_type`.
A programme's update stored any string it was sent until R10-W4; it now refuses
a value outside the set, by name, and moves nothing.
"""
import json
from datetime import date

from django.test import Client, TestCase

from apps.billing.invoicing.models import CustomerUsageInvoice
from apps.platform.customers.models import Customer
from apps.platform.tenants.models import Tenant, TenantApiKey
from apps.referrals.models import ReferralProgram
from core.vocabulary import (
    REWARD_TYPE_FLAT_FEE, REWARD_TYPE_REVENUE_SHARE, SKIP_REASON_VALUES,
    USAGE_INVOICE_STATUS_PUSHED, USAGE_INVOICE_STATUS_SKIPPED)


class AUsageInvoiceSaysWhyItWasSkippedTest(TestCase):

    def setUp(self):
        self.http = Client()
        self.tenant = Tenant.objects.create(name="Invoices",
                                            products=["metering", "billing"])
        _, raw = TenantApiKey.create_key(self.tenant, label="k")
        self.auth = {"HTTP_AUTHORIZATION": f"Bearer {raw}"}
        self.customer = Customer.objects.create(tenant=self.tenant,
                                                external_id="c1")

    def _invoice(self, month, status, skip_reason=""):
        return CustomerUsageInvoice.objects.create(
            tenant=self.tenant, customer=self.customer,
            period_start=date(2026, month, 1), period_end=date(2026, month, 28),
            status=status, skip_reason=skip_reason)

    def test_a_skipped_invoice_says_why_and_any_other_says_null(self):
        reasons = sorted(SKIP_REASON_VALUES)
        for month, reason in enumerate(reasons, start=1):
            self._invoice(month, USAGE_INVOICE_STATUS_SKIPPED, reason)
        self._invoice(len(reasons) + 1, USAGE_INVOICE_STATUS_PUSHED)

        for path in (f"/api/v1/billing/customers/{self.customer.id}/usage-invoices",
                     "/api/v1/billing/tenant/usage-invoices"):
            with self.subTest(path=path):
                answered = self.http.get(path, **self.auth)

                self.assertEqual(answered.status_code, 200, answered.content)
                rows = answered.json()["data"]
                self.assertTrue(all("skip_reason" in row for row in rows))
                skipped = sorted(row["skip_reason"] for row in rows
                                 if row["status"] == USAGE_INVOICE_STATUS_SKIPPED)
                self.assertEqual(skipped, reasons)
                (pushed,) = [row for row in rows
                             if row["status"] == USAGE_INVOICE_STATUS_PUSHED]
                self.assertIsNone(pushed["skip_reason"])


class AProgrammesRewardTypeIsTheRegistrysTest(TestCase):

    def setUp(self):
        self.http = Client()
        self.tenant = Tenant.objects.create(name="Referrals",
                                            products=["metering", "referrals"])
        _, raw = TenantApiKey.create_key(self.tenant, label="k")
        self.auth = {"HTTP_AUTHORIZATION": f"Bearer {raw}"}

    def _send(self, method, body):
        return getattr(self.http, method)(
            "/api/v1/referrals/program", data=json.dumps(body),
            content_type="application/json", **self.auth)

    def test_a_reward_type_outside_the_set_is_refused_on_create_and_update(self):
        refused = self._send("post", {"reward_type": "bogus", "reward_value": 5})
        self.assertEqual(refused.status_code, 422, refused.content)
        self.assertFalse(ReferralProgram.objects.filter(tenant=self.tenant).exists())

        created = self._send("post", {"reward_type": REWARD_TYPE_FLAT_FEE,
                                      "reward_value": 5})
        self.assertEqual(created.status_code, 200, created.content)

        refused = self._send("patch", {"reward_type": "bogus"})
        self.assertEqual(refused.status_code, 422, refused.content)
        self.assertEqual(refused.json()["code"], "validation_error")
        self.assertEqual(
            ReferralProgram.objects.get(tenant=self.tenant).reward_type,
            REWARD_TYPE_FLAT_FEE)

        moved = self._send("patch", {"reward_type": REWARD_TYPE_REVENUE_SHARE})
        self.assertEqual(moved.status_code, 200, moved.content)
        self.assertEqual(moved.json()["reward_type"], REWARD_TYPE_REVENUE_SHARE)
