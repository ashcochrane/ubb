"""Two published value sets R10-W4 declared, held where a caller meets them.

**Why a usage invoice was skipped** is the registry's closed `skip_reason`. It
was a bare string, and every invoice that was NOT skipped held and published
`""` — a value the declared set does not hold. It applies only to a skipped
invoice, so it is null on every other one — STORED as null, never translated
at the read, and held at the table by `ck_usage_invoice_skip_reason_known` —
and required (never absent) on both reads. (Before the cutover, #190, a case
here also ran `invoicing/0011` through the executor and back, moving every
stored `""` to null; that data step left with the squashed chain.)

**A referral programme's reward type** is the registry's closed `reward_type`.
A programme's update stored any string it was sent until R10-W4; it now refuses
a value outside the set, by name, and moves nothing.
"""
import json
from datetime import date

from django.db import IntegrityError, transaction
from django.test import Client, SimpleTestCase, TestCase

from api.v1.tests._helpers import a_tenant
from apps.billing.invoicing.models import CustomerUsageInvoice
from apps.platform.customers.models import Customer
from apps.referrals.models import ReferralProgram
from core.vocabulary import (
    REWARD_TYPE_FLAT_FEE, REWARD_TYPE_REVENUE_SHARE, SKIP_REASON_VALUES,
    USAGE_INVOICE_STATUS_PUSHED, USAGE_INVOICE_STATUS_SKIPPED)


class AUsageInvoiceSaysWhyItWasSkippedTest(TestCase):

    def setUp(self):
        self.http = Client()
        self.tenant, raw = a_tenant("Invoices",
                                    products=("metering", "billing"))
        self.auth = {"HTTP_AUTHORIZATION": f"Bearer {raw}"}
        self.customer = Customer.objects.create(tenant=self.tenant,
                                                external_id="c1")

    def _invoice(self, month, status, skip_reason=None):
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

    def test_the_table_holds_null_or_the_registrys_six_and_nothing_else(self):
        invoice = self._invoice(1, USAGE_INVOICE_STATUS_PUSHED)
        invoice.refresh_from_db()
        self.assertIsNone(invoice.skip_reason)
        for refused in ("", "not_a_reason"):
            with self.subTest(value=refused):
                with self.assertRaisesRegex(IntegrityError,
                                            "ck_usage_invoice_skip_reason_known"):
                    with transaction.atomic():
                        CustomerUsageInvoice.objects.filter(
                            pk=invoice.pk).update(skip_reason=refused)


class AProgrammesRewardTypeIsTheRegistrysTest(TestCase):

    def setUp(self):
        self.http = Client()
        self.tenant, raw = a_tenant("Referrals",
                                    products=("metering", "referrals"))
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


class AWithheldStatusIsNotOfferedTest(SimpleTestCase):
    """The owner's review of #620: a value the registry withholds — a
    legitimate state no legal production transition creates today — is not
    offered by its model either, so an ordinary writer validating through the
    field cannot emit it. What each field offers is exactly what can occur."""

    def test_each_status_offers_its_occurring_values_only(self):
        from apps.billing.tenant_billing.models import TenantInvoice
        from apps.referrals.models import ReferralProgram
        from core.vocabulary import (
            REFERRAL_PROGRAM_STATUS_VALUES,
            REFERRAL_PROGRAM_STATUS_WITHHELD_VALUES,
            TENANT_INVOICE_STATUS_VALUES, TENANT_INVOICE_STATUS_WITHHELD_VALUES)

        for model, declared, withheld in (
                (TenantInvoice, TENANT_INVOICE_STATUS_VALUES,
                 TENANT_INVOICE_STATUS_WITHHELD_VALUES),
                (ReferralProgram, REFERRAL_PROGRAM_STATUS_VALUES,
                 REFERRAL_PROGRAM_STATUS_WITHHELD_VALUES)):
            with self.subTest(model=model.__name__):
                offered = {value for value, _ in
                           model._meta.get_field("status").choices}
                self.assertTrue(withheld)
                self.assertEqual(offered, set(declared) - set(withheld))
