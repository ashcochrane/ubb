"""Wave-5a AR-visibility CAPSTONE (Stripe MOCKED).

Proves the FULL accounts-receivable reconcile loop end-to-end against the real
handlers, driving SYNTHETIC Stripe events (same construction style as
api/v1/tests/test_ar_reconcile.py) — no network, no real Stripe.

Covered end-to-end:
  * usage standalone invoice: finalized -> payment_failed -> paid
      (open + url/pdf stored; payment_failed_at stamped + hosted url ROTATED;
       then paid + paid_at; monotonic open->...->paid never regresses)
  * subscription invoice: finalized -> voided
      (open SubscriptionInvoice row created w/ url/pdf; then void)
  * idempotency / duplicate delivery (no error, no double-apply)
  * out-of-order finalized AFTER paid does NOT regress paid -> open (monotonic)
  * event.account mismatch -> no write
  * /me visibility: billing owner sees the reconciled rows (w/ refreshed url);
    a pooled seat sees nothing (consolidated bill belongs to the business)

NOTE (documented limitation, asserted below in
TestSubscriptionPaymentFailedLimitation): the connector
`handle_invoice_payment_failed` writes `payment_failed_at` with
update_fields, but `SubscriptionInvoice` has no such column — so a
SUBSCRIPTION invoice.payment_failed currently RAISES. The url-refresh-on-
payment-failed proof therefore runs on the USAGE invoice, where the full path
works. See the final test class for the pinned reality.
"""
from types import SimpleNamespace
from datetime import date

from django.test import TestCase, Client
from django.utils import timezone

from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.subscriptions.models import StripeSubscription, SubscriptionInvoice
from apps.billing.invoicing.models import CustomerUsageInvoice
from core.widget_auth import create_widget_token

from api.v1.webhooks import (
    handle_invoice_finalized,
    handle_invoice_paid,
    handle_invoice_voided,
)
from apps.billing.connectors.stripe.webhooks import handle_invoice_payment_failed


# --- synthetic event helpers (mirror test_ar_reconcile.py) ------------------

def _event(account, *, obj):
    return SimpleNamespace(account=account, data=SimpleNamespace(object=obj))


def _usage_obj(invoice_id, *, hosted_url="", pdf=""):
    """A standalone usage invoice object — no subscription linkage."""
    return SimpleNamespace(
        id=invoice_id,
        customer="cus_capstone",
        subscription=None,
        parent=None,
        hosted_invoice_url=hosted_url,
        invoice_pdf=pdf,
        amount_paid=0,
        currency="usd",
    )


def _sub_obj(invoice_id, subscription_id, *, amount_paid=4900, hosted_url="",
             pdf="", period_start=1738368000, period_end=1740960000,
             paid_at_ts=1738400000):
    """A subscription invoice object — Basil legacy `.subscription` linkage."""
    return SimpleNamespace(
        id=invoice_id,
        customer="cus_capstone",
        subscription=subscription_id,
        parent=None,
        amount_paid=amount_paid,
        currency="usd",
        hosted_invoice_url=hosted_url,
        invoice_pdf=pdf,
        period_start=period_start,
        period_end=period_end,
        status_transitions=SimpleNamespace(paid_at=paid_at_ts),
    )


class TestWave5aARCapstone(TestCase):
    """The full AR loop, mocked, driven through the real handlers."""

    ACCT = "acct_capstone"

    def setUp(self):
        self.client = Client()
        self.tenant = Tenant.objects.create(
            name="Capstone",
            products=["metering", "subscriptions", "billing"],
            stripe_connected_account_id=self.ACCT,
        )
        # Billing owner = an individual customer (owns its own bill).
        self.owner = Customer.objects.create(
            tenant=self.tenant, external_id="owner",
            account_type="individual",
        )
        now = timezone.now()
        self.sub = StripeSubscription.objects.create(
            tenant=self.tenant, customer=self.owner,
            stripe_subscription_id="sub_capstone",
            stripe_product_name="Pro", status="active",
            amount_micros=49_000_000, currency="usd", interval="month",
            current_period_start=now, current_period_end=now, last_synced_at=now,
        )
        # A pre-pushed standalone usage invoice (no subscription).
        self.usage_inv = CustomerUsageInvoice.objects.create(
            tenant=self.tenant, customer=self.owner,
            period_start=date(2026, 1, 1), period_end=date(2026, 2, 1),
            total_billed_micros=12_340_000,
            status="pushed", stripe_invoice_id="in_usage_cap",
        )

    def _token(self, customer):
        return create_widget_token(
            self.tenant.widget_secret, str(customer.id), str(self.tenant.id)
        )

    def _me(self, path, customer):
        return self.client.get(
            path, HTTP_AUTHORIZATION=f"Bearer {self._token(customer)}"
        )

    # -- 1a. usage: finalized -> payment_failed (url rotates) -> paid ---------

    def test_usage_invoice_full_loop_with_url_rotation_on_payment_failed(self):
        acct = self.ACCT

        # finalized -> open + url/pdf stored
        handle_invoice_finalized(_event(acct, obj=_usage_obj(
            "in_usage_cap", hosted_url="https://pay/v1", pdf="https://pdf/v1")))
        self.usage_inv.refresh_from_db()
        self.assertEqual(self.usage_inv.payment_status, "open")
        self.assertEqual(self.usage_inv.hosted_invoice_url, "https://pay/v1")
        self.assertEqual(self.usage_inv.invoice_pdf, "https://pdf/v1")
        self.assertIsNone(self.usage_inv.payment_failed_at)
        first_url = self.usage_inv.hosted_invoice_url

        # payment_failed -> payment_failed_at stamped + hosted url ROTATED to a
        # NEW value (Stripe rotates the token); payment_status stays open (the
        # failed attempt is not a terminal status, so it does NOT regress).
        handle_invoice_payment_failed(_event(acct, obj=_usage_obj(
            "in_usage_cap", hosted_url="https://pay/v2-ROTATED",
            pdf="https://pdf/v2-ROTATED")))
        self.usage_inv.refresh_from_db()
        self.assertIsNotNone(self.usage_inv.payment_failed_at)
        # THE load-bearing assertion: the stored url actually changed.
        self.assertNotEqual(self.usage_inv.hosted_invoice_url, first_url)
        self.assertEqual(self.usage_inv.hosted_invoice_url, "https://pay/v2-ROTATED")
        self.assertEqual(self.usage_inv.invoice_pdf, "https://pdf/v2-ROTATED")
        self.assertEqual(self.usage_inv.payment_status, "open")  # not regressed

        # paid -> paid + paid_at
        handle_invoice_paid(_event(acct, obj=_usage_obj("in_usage_cap")))
        self.usage_inv.refresh_from_db()
        self.assertEqual(self.usage_inv.payment_status, "paid")
        self.assertIsNotNone(self.usage_inv.paid_at)
        # url was not cleared by the (blank-url) paid event
        self.assertEqual(self.usage_inv.hosted_invoice_url, "https://pay/v2-ROTATED")

    # -- 1b. subscription: finalized -> voided -------------------------------

    def test_subscription_invoice_finalized_creates_open_row_then_voided(self):
        acct = self.ACCT

        # finalized -> creates an OPEN SubscriptionInvoice row w/ url/pdf
        handle_invoice_finalized(_event(acct, obj=_sub_obj(
            "in_sub_cap", "sub_capstone",
            hosted_url="https://pay/s1", pdf="https://pdf/s1")))
        rows = SubscriptionInvoice.objects.filter(stripe_invoice_id="in_sub_cap")
        self.assertEqual(rows.count(), 1)
        row = rows.first()
        self.assertEqual(row.status, "open")
        self.assertEqual(row.hosted_invoice_url, "https://pay/s1")
        self.assertEqual(row.invoice_pdf, "https://pdf/s1")
        self.assertIsNone(row.paid_at)

        # voided -> status void (same row, no second row)
        handle_invoice_voided(_event(acct, obj=_sub_obj("in_sub_cap", "sub_capstone")))
        self.assertEqual(
            SubscriptionInvoice.objects.filter(stripe_invoice_id="in_sub_cap").count(), 1)
        row.refresh_from_db()
        self.assertEqual(row.status, "void")

    # -- 2. idempotency / ordering -------------------------------------------

    def test_duplicate_paid_delivery_is_idempotent(self):
        acct = self.ACCT
        handle_invoice_finalized(_event(acct, obj=_usage_obj("in_usage_cap")))
        handle_invoice_paid(_event(acct, obj=_usage_obj("in_usage_cap")))
        self.usage_inv.refresh_from_db()
        first_paid_at = self.usage_inv.paid_at
        self.assertEqual(self.usage_inv.payment_status, "paid")

        # re-deliver the SAME paid event: no error, no double, paid_at frozen
        handle_invoice_paid(_event(acct, obj=_usage_obj("in_usage_cap")))
        self.usage_inv.refresh_from_db()
        self.assertEqual(self.usage_inv.payment_status, "paid")
        self.assertEqual(self.usage_inv.paid_at, first_paid_at)

    def test_out_of_order_finalized_after_paid_does_not_regress(self):
        acct = self.ACCT
        handle_invoice_paid(_event(acct, obj=_usage_obj("in_usage_cap")))
        self.usage_inv.refresh_from_db()
        self.assertEqual(self.usage_inv.payment_status, "paid")
        paid_at = self.usage_inv.paid_at

        # a LATE finalized arrives out of order -> must NOT regress paid -> open
        handle_invoice_finalized(_event(acct, obj=_usage_obj(
            "in_usage_cap", hosted_url="https://late")))
        self.usage_inv.refresh_from_db()
        self.assertEqual(self.usage_inv.payment_status, "paid")  # monotonic
        self.assertEqual(self.usage_inv.paid_at, paid_at)
        # url still refreshes (non-status field) even when status is terminal
        self.assertEqual(self.usage_inv.hosted_invoice_url, "https://late")

    def test_subscription_duplicate_finalized_does_not_create_second_row(self):
        acct = self.ACCT
        handle_invoice_finalized(_event(acct, obj=_sub_obj("in_sub_dup", "sub_capstone")))
        handle_invoice_finalized(_event(acct, obj=_sub_obj("in_sub_dup", "sub_capstone")))
        self.assertEqual(
            SubscriptionInvoice.objects.filter(stripe_invoice_id="in_sub_dup").count(), 1)

    # -- 3. account mismatch -> no write -------------------------------------

    def test_account_mismatch_no_write_usage(self):
        handle_invoice_finalized(_event(
            "acct_WRONG", obj=_usage_obj("in_usage_cap", hosted_url="https://x")))
        self.usage_inv.refresh_from_db()
        self.assertIsNone(self.usage_inv.payment_status)  # untouched
        self.assertEqual(self.usage_inv.hosted_invoice_url, "")

    def test_account_mismatch_no_row_subscription(self):
        handle_invoice_finalized(_event(
            "acct_WRONG", obj=_sub_obj("in_sub_mismatch", "sub_capstone")))
        self.assertFalse(
            SubscriptionInvoice.objects.filter(stripe_invoice_id="in_sub_mismatch").exists())

    # -- 4. /me visibility ----------------------------------------------------

    def test_me_endpoints_surface_reconciled_rows_for_billing_owner(self):
        acct = self.ACCT
        # drive both invoices to their reconciled states
        handle_invoice_finalized(_event(acct, obj=_usage_obj(
            "in_usage_cap", hosted_url="https://pay/u1", pdf="https://pdf/u1")))
        handle_invoice_payment_failed(_event(acct, obj=_usage_obj(
            "in_usage_cap", hosted_url="https://pay/u2-ROT", pdf="https://pdf/u2-ROT")))
        handle_invoice_paid(_event(acct, obj=_usage_obj("in_usage_cap")))
        handle_invoice_finalized(_event(acct, obj=_sub_obj(
            "in_sub_cap", "sub_capstone", hosted_url="https://pay/s1", pdf="https://pdf/s1")))

        # billing owner sees the reconciled usage invoice
        usage_resp = self._me("/api/v1/me/usage-invoices", self.owner)
        self.assertEqual(usage_resp.status_code, 200)
        u = usage_resp.json()["data"]
        self.assertEqual(len(u), 1)
        self.assertEqual(u[0]["payment_status"], "paid")
        self.assertEqual(u[0]["hosted_invoice_url"], "https://pay/u2-ROT")  # rotated
        self.assertEqual(u[0]["stripe_invoice_id"], "in_usage_cap")

        # billing owner sees the reconciled subscription invoice
        sub_resp = self._me("/api/v1/me/subscription-invoices", self.owner)
        self.assertEqual(sub_resp.status_code, 200)
        s = sub_resp.json()["data"]
        self.assertEqual(len(s), 1)
        self.assertEqual(s[0]["status"], "open")
        self.assertEqual(s[0]["hosted_invoice_url"], "https://pay/s1")

    def test_me_endpoints_empty_for_pooled_seat(self):
        # a pooled seat under a business does NOT own the consolidated bill
        business = Customer.objects.create(
            tenant=self.tenant, external_id="biz", account_type="business",
            billing_topology="pooled",
        )
        seat = Customer.objects.create(
            tenant=self.tenant, external_id="seat", account_type="seat",
            parent=business,
        )
        # both invoices belong to the BUSINESS
        CustomerUsageInvoice.objects.create(
            tenant=self.tenant, customer=business,
            period_start=date(2026, 2, 1), period_end=date(2026, 3, 1),
            status="pushed", stripe_invoice_id="in_biz_usage",
            payment_status="paid", hosted_invoice_url="https://biz/u",
        )
        now = timezone.now()
        biz_sub = StripeSubscription.objects.create(
            tenant=self.tenant, customer=business,
            stripe_subscription_id="sub_biz",
            stripe_product_name="Pro", status="active",
            amount_micros=49_000_000, currency="usd", interval="month",
            current_period_start=now, current_period_end=now, last_synced_at=now,
        )
        SubscriptionInvoice.objects.create(
            tenant=self.tenant, customer=business, stripe_subscription=biz_sub,
            stripe_invoice_id="in_biz_sub", amount_paid_micros=49_000_000,
            status="paid", hosted_invoice_url="https://biz/s",
        )

        # the pooled seat sees NOTHING (sibling-spend isolation)
        seat_usage = self._me("/api/v1/me/usage-invoices", seat)
        self.assertEqual(seat_usage.status_code, 200)
        self.assertEqual(seat_usage.json()["data"], [])
        seat_sub = self._me("/api/v1/me/subscription-invoices", seat)
        self.assertEqual(seat_sub.status_code, 200)
        self.assertEqual(seat_sub.json()["data"], [])

        # while the business DOES see both
        biz_usage = self._me("/api/v1/me/usage-invoices", business)
        self.assertEqual(len(biz_usage.json()["data"]), 1)
        biz_sub_resp = self._me("/api/v1/me/subscription-invoices", business)
        self.assertEqual(len(biz_sub_resp.json()["data"]), 1)


class TestSubscriptionPaymentFailedLimitation(TestCase):
    """Pin the documented reality: a SUBSCRIPTION invoice.payment_failed cannot
    stamp payment_failed_at because SubscriptionInvoice has no such column.

    The connector handler writes it with update_fields, so the call RAISES
    ValueError. In production the webhook dispatcher catches this and marks the
    StripeWebhookEvent failed+retryable (no url refresh). This is a latent gap in
    the AR loop for subscription invoices — flagged, not papered over. (The usage
    invoice path, exercised above, works end-to-end.)
    """

    ACCT = "acct_pf_limit"

    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="PFLimit", products=["metering", "subscriptions"],
            stripe_connected_account_id=self.ACCT,
        )
        self.customer = Customer.objects.create(tenant=self.tenant, external_id="c1")
        now = timezone.now()
        self.sub = StripeSubscription.objects.create(
            tenant=self.tenant, customer=self.customer,
            stripe_subscription_id="sub_pf_limit",
            stripe_product_name="Pro", status="active",
            amount_micros=49_000_000, currency="usd", interval="month",
            current_period_start=now, current_period_end=now, last_synced_at=now,
        )
        self.row = SubscriptionInvoice.objects.create(
            tenant=self.tenant, customer=self.customer, stripe_subscription=self.sub,
            stripe_invoice_id="in_pf_limit", amount_paid_micros=0,
            status="open", hosted_invoice_url="https://orig",
        )

    def test_subscription_payment_failed_raises_due_to_missing_column(self):
        ev = _event(self.ACCT, obj=_sub_obj("in_pf_limit", "sub_pf_limit",
                                             hosted_url="https://rotated"))
        with self.assertRaises(ValueError):
            handle_invoice_payment_failed(ev)
        # and the url was NOT refreshed (the write never committed)
        self.row.refresh_from_db()
        self.assertEqual(self.row.hosted_invoice_url, "https://orig")
