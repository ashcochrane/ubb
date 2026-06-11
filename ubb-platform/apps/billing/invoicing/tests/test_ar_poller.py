"""Wave-5a: Stripe-driven polling backstop for AR invoice payment-status reconcile.

Webhooks are the fast path but Stripe drops retries after ~3 days; this hourly
poller (4-day lookback) repairs any payment-status it missed. Stripe is mocked.
"""
import datetime
from unittest.mock import patch, MagicMock

import pytest
from django.test import TestCase
from django.utils import timezone

from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer


def _stripe_invoice(id, status, *, hosted=None, pdf=None, subscription=None):
    """Build a MagicMock that looks like a Stripe Invoice object."""
    inv = MagicMock()
    inv.id = id
    inv.status = status
    inv.hosted_invoice_url = hosted
    inv.invoice_pdf = pdf
    # _invoice_subscription_id reads .subscription (legacy) or .parent (Basil).
    inv.subscription = subscription
    inv.parent = None
    inv.amount_paid = 0
    inv.currency = "usd"
    inv.period_start = None
    inv.period_end = None
    inv.status_transitions = None
    return inv


def _invoice_list(*invoices):
    """A MagicMock standing in for stripe.Invoice.list's return (auto_paging_iter)."""
    listing = MagicMock()
    listing.auto_paging_iter.return_value = iter(invoices)
    return listing


@pytest.mark.django_db
class TestArPoller:
    PS = datetime.date(2026, 6, 1)
    PE = datetime.date(2026, 7, 1)

    def _tenant_customer(self):
        t = Tenant.objects.create(
            name="PP", products=["metering", "billing"], billing_mode="postpaid",
            stripe_connected_account_id="acct_x", charges_enabled=True,
        )
        c = Customer.objects.create(tenant=t, external_id="c1", stripe_customer_id="cus_1")
        return t, c

    def test_usage_invoice_payment_status_repaired_with_urls(self):
        from apps.billing.invoicing.tasks import reconcile_invoice_payment_status
        from apps.billing.invoicing.models import CustomerUsageInvoice
        t, c = self._tenant_customer()
        rec = CustomerUsageInvoice.objects.create(
            tenant=t, customer=c, period_start=self.PS, period_end=self.PE,
            status="pushed", stripe_invoice_id="in_x", payment_status=None,
        )
        stripe_inv = _stripe_invoice(
            "in_x", "paid", hosted="https://h", pdf="https://p.pdf")
        with patch("apps.billing.invoicing.tasks.stripe.Invoice.list",
                   return_value=_invoice_list(stripe_inv)) as mock_list:
            reconcile_invoice_payment_status()
        rec.refresh_from_db()
        assert rec.payment_status == "paid"
        assert rec.paid_at is not None
        assert rec.hosted_invoice_url == "https://h"
        assert rec.invoice_pdf == "https://p.pdf"
        # listed against the connected account
        assert mock_list.call_args.kwargs.get("stripe_account") == "acct_x"

    def test_subscription_invoice_status_flips_to_paid(self):
        from apps.billing.invoicing.tasks import reconcile_invoice_payment_status
        from apps.subscriptions.models import StripeSubscription, SubscriptionInvoice
        t, c = self._tenant_customer()
        now = timezone.now()
        sub = StripeSubscription.objects.create(
            tenant=t, customer=c, stripe_subscription_id="sub_1",
            stripe_product_name="P", status="active", amount_micros=1_000_000,
            interval="month", quantity=1, current_period_start=now,
            current_period_end=now, last_synced_at=now,
        )
        si = SubscriptionInvoice.objects.create(
            tenant=t, customer=c, stripe_subscription=sub,
            stripe_invoice_id="in_s", status="open",
        )
        stripe_inv = _stripe_invoice("in_s", "paid", subscription="sub_1")
        with patch("apps.billing.invoicing.tasks.stripe.Invoice.list",
                   return_value=_invoice_list(stripe_inv)):
            reconcile_invoice_payment_status()
        si.refresh_from_db()
        assert si.status == "paid"

    def test_empty_stripe_invoice_id_row_is_not_queried(self):
        from apps.billing.invoicing.tasks import reconcile_invoice_payment_status
        from apps.billing.invoicing.models import CustomerUsageInvoice
        t, c = self._tenant_customer()
        rec = CustomerUsageInvoice.objects.create(
            tenant=t, customer=c, period_start=self.PS, period_end=self.PE,
            status="pushed", stripe_invoice_id="", payment_status=None,
        )
        # Stripe returns an invoice with a blank id — must never match the row.
        stripe_inv = _stripe_invoice("", "paid")
        with patch("apps.billing.invoicing.tasks.stripe.Invoice.list",
                   return_value=_invoice_list(stripe_inv)):
            reconcile_invoice_payment_status()
        rec.refresh_from_db()
        assert rec.payment_status is None

    def test_terminal_status_not_regressed(self):
        from apps.billing.invoicing.tasks import reconcile_invoice_payment_status
        from apps.billing.invoicing.models import CustomerUsageInvoice
        t, c = self._tenant_customer()
        rec = CustomerUsageInvoice.objects.create(
            tenant=t, customer=c, period_start=self.PS, period_end=self.PE,
            status="pushed", stripe_invoice_id="in_x", payment_status="paid",
        )
        # Stripe (wrongly) says open — must not regress a terminal paid row.
        stripe_inv = _stripe_invoice("in_x", "open")
        with patch("apps.billing.invoicing.tasks.stripe.Invoice.list",
                   return_value=_invoice_list(stripe_inv)):
            reconcile_invoice_payment_status()
        rec.refresh_from_db()
        assert rec.payment_status == "paid"

    def test_non_charge_ready_tenant_skipped(self):
        from apps.billing.invoicing.tasks import reconcile_invoice_payment_status
        Tenant.objects.create(
            name="NoStripe", products=["metering", "billing"], billing_mode="postpaid",
            stripe_connected_account_id="", charges_enabled=False,
        )
        with patch("apps.billing.invoicing.tasks.stripe.Invoice.list") as mock_list:
            reconcile_invoice_payment_status()
        mock_list.assert_not_called()


class RepairTransitionParityTest(TestCase):
    """The backstop repairs along the SAME Stripe-legal transition table as the
    webhook fast path: uncollectible -> paid is a legal repair (with money
    fields); a genuinely illegal move (paid -> open) is loud-logged, never
    applied. unittest-style assertLogs because the 'apps' logger does not
    propagate to root (pytest caplog would miss it)."""

    PS = datetime.date(2026, 6, 1)
    PE = datetime.date(2026, 7, 1)

    def _tenant_customer(self):
        t = Tenant.objects.create(
            name="PP", products=["metering", "billing"], billing_mode="postpaid",
            stripe_connected_account_id="acct_x", charges_enabled=True,
        )
        c = Customer.objects.create(tenant=t, external_id="c1", stripe_customer_id="cus_1")
        return t, c

    def test_usage_uncollectible_to_paid_repairs(self):
        from apps.billing.invoicing.tasks import _repair_usage_invoice
        from apps.billing.invoicing.models import CustomerUsageInvoice
        from apps.billing.connectors.stripe.invoice_routing import _refresh_urls
        t, c = self._tenant_customer()
        rec = CustomerUsageInvoice.objects.create(
            tenant=t, customer=c, period_start=self.PS, period_end=self.PE,
            status="pushed", stripe_invoice_id="in_unc",
            payment_status="uncollectible",
        )
        inv = _stripe_invoice("in_unc", "paid", hosted="https://h", pdf="https://p.pdf")
        repaired = _repair_usage_invoice(
            CustomerUsageInvoice, t, "in_unc", inv, "paid", _refresh_urls)
        self.assertEqual(repaired, 1)
        rec.refresh_from_db()
        self.assertEqual(rec.payment_status, "paid")
        self.assertIsNotNone(rec.paid_at)
        self.assertEqual(rec.hosted_invoice_url, "https://h")

    def test_usage_paid_to_open_logs_regression(self):
        from apps.billing.invoicing.tasks import _repair_usage_invoice
        from apps.billing.invoicing.models import CustomerUsageInvoice
        from apps.billing.connectors.stripe.invoice_routing import _refresh_urls
        t, c = self._tenant_customer()
        rec = CustomerUsageInvoice.objects.create(
            tenant=t, customer=c, period_start=self.PS, period_end=self.PE,
            status="pushed", stripe_invoice_id="in_pd",
            payment_status="paid", paid_at=timezone.now(),
        )
        inv = _stripe_invoice("in_pd", "open")
        with self.assertLogs("apps.billing.invoicing.tasks", level="ERROR") as logs:
            repaired = _repair_usage_invoice(
                CustomerUsageInvoice, t, "in_pd", inv, "open", _refresh_urls)
        self.assertEqual(repaired, 0)
        self.assertTrue(any("ar.reconcile_unexpected_regression" in m for m in logs.output))
        rec.refresh_from_db()
        self.assertEqual(rec.payment_status, "paid")

    def _subscription_invoice(self, t, c, stripe_invoice_id, status):
        from apps.subscriptions.models import StripeSubscription, SubscriptionInvoice
        now = timezone.now()
        sub = StripeSubscription.objects.create(
            tenant=t, customer=c, stripe_subscription_id=f"sub_{stripe_invoice_id}",
            stripe_product_name="P", status="active", amount_micros=1_000_000,
            interval="month", quantity=1, current_period_start=now,
            current_period_end=now, last_synced_at=now,
        )
        return SubscriptionInvoice.objects.create(
            tenant=t, customer=c, stripe_subscription=sub,
            stripe_invoice_id=stripe_invoice_id, status=status,
        )

    def test_subscription_uncollectible_to_paid_repairs(self):
        from apps.billing.invoicing.tasks import _repair_subscription_invoice
        from apps.subscriptions.models import SubscriptionInvoice
        from apps.billing.connectors.stripe.invoice_routing import _refresh_urls
        t, c = self._tenant_customer()
        si = self._subscription_invoice(t, c, "in_s_unc", "uncollectible")
        inv = _stripe_invoice("in_s_unc", "paid", subscription="sub_in_s_unc")
        inv.amount_paid = 4900
        repaired = _repair_subscription_invoice(
            SubscriptionInvoice, t, "in_s_unc", inv, "paid", _refresh_urls)
        self.assertEqual(repaired, 1)
        si.refresh_from_db()
        self.assertEqual(si.status, "paid")
        self.assertIsNotNone(si.paid_at)
        self.assertEqual(si.amount_paid_micros, 49_000_000)

    def test_subscription_paid_to_open_logs_regression(self):
        from apps.billing.invoicing.tasks import _repair_subscription_invoice
        from apps.subscriptions.models import SubscriptionInvoice
        from apps.billing.connectors.stripe.invoice_routing import _refresh_urls
        t, c = self._tenant_customer()
        si = self._subscription_invoice(t, c, "in_s_pd", "paid")
        si.paid_at = timezone.now()
        si.save(update_fields=["paid_at"])
        inv = _stripe_invoice("in_s_pd", "open", subscription="sub_in_s_pd")
        with self.assertLogs("apps.billing.invoicing.tasks", level="ERROR") as logs:
            repaired = _repair_subscription_invoice(
                SubscriptionInvoice, t, "in_s_pd", inv, "open", _refresh_urls)
        self.assertEqual(repaired, 0)
        self.assertTrue(any("ar.reconcile_unexpected_regression" in m for m in logs.output))
        si.refresh_from_db()
        self.assertEqual(si.status, "paid")
