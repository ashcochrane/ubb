"""Wave-5a AR payment-status reconcile.

ALL invoice.* reconcile lives on api/v1. These tests exercise the consolidated
_reconcile_customer_invoice path via the handlers directly:
  - usage standalone invoice (no subscription)  -> CustomerUsageInvoice.payment_status
  - subscription invoice (subscription present) -> SubscriptionInvoice.status
Both are account-checked (event.account must equal the matched row's tenant
stripe_connected_account_id) and follow the Stripe-legal transition table
(AR_ALLOWED): paid/void are final; uncollectible remains payable and voidable.
"""
from types import SimpleNamespace
from datetime import date

import pytest
from django.utils import timezone

from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.subscriptions.models import StripeSubscription, SubscriptionInvoice
from apps.billing.invoicing.models import CustomerUsageInvoice

from api.v1.webhooks import (
    handle_invoice_finalized,
    handle_invoice_paid,
    handle_invoice_voided,
    handle_invoice_uncollectible,
)


def _event(account, *, obj):
    return SimpleNamespace(account=account, data=SimpleNamespace(object=obj))


def _usage_inv_obj(stripe_invoice_id, *, hosted_url="", pdf="", subscription=None):
    return SimpleNamespace(
        id=stripe_invoice_id,
        subscription=subscription,
        parent=None,
        hosted_invoice_url=hosted_url,
        invoice_pdf=pdf,
        amount_paid=0,
        currency="usd",
    )


def _sub_inv_obj(stripe_invoice_id, subscription_id, *, amount_paid=4900,
                 hosted_url="", pdf="", period_start=1738368000,
                 period_end=1740960000, paid_at_ts=1738400000):
    return SimpleNamespace(
        id=stripe_invoice_id,
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


def _basil_sub_inv_obj(stripe_invoice_id, subscription_id, *, amount_paid=4900,
                       hosted_url="", pdf="", period_start=1738368000,
                       period_end=1740960000, paid_at_ts=1738400000):
    """Basil (api_version 2025-03-31.basil) shaped invoice: NO top-level .subscription;
    the subscription id hangs off inv.parent.subscription_details.subscription."""
    return SimpleNamespace(
        id=stripe_invoice_id,
        subscription=None,
        parent=SimpleNamespace(
            subscription_details=SimpleNamespace(subscription=subscription_id)),
        amount_paid=amount_paid,
        currency="usd",
        hosted_invoice_url=hosted_url,
        invoice_pdf=pdf,
        period_start=period_start,
        period_end=period_end,
        status_transitions=SimpleNamespace(paid_at=paid_at_ts),
    )


@pytest.mark.django_db
class TestBasilSubscriptionRouting:
    """B2: the Basil .parent.subscription_details.subscription path (the pinned
    api_version's actual shape) must resolve the subscription id and route to
    SubscriptionInvoice — NOT to CustomerUsageInvoice."""

    def _fixtures(self, acct="acct_basil_1"):
        tenant = Tenant.objects.create(
            name="t", products=["metering", "subscriptions"],
            stripe_connected_account_id=acct,
        )
        customer = Customer.objects.create(tenant=tenant, external_id="c1")
        now = timezone.now()
        sub = StripeSubscription.objects.create(
            tenant=tenant, customer=customer,
            stripe_subscription_id="sub_x",
            stripe_product_name="Pro", status="active",
            amount_micros=49_000_000, currency="usd", interval="month",
            current_period_start=now, current_period_end=now, last_synced_at=now,
        )
        return tenant, customer, sub

    def test_invoice_subscription_id_reads_basil_parent(self):
        from api.v1.webhooks import _invoice_subscription_id
        basil_inv = _basil_sub_inv_obj("in_basil_1", "sub_x")
        assert _invoice_subscription_id(basil_inv) == "sub_x"

    def test_basil_invoice_routes_to_subscription_invoice(self):
        tenant, customer, sub = self._fixtures()
        acct = tenant.stripe_connected_account_id
        handle_invoice_finalized(_event(
            acct, obj=_basil_sub_inv_obj("in_basil_2", "sub_x",
                                         hosted_url="https://pay/b2", pdf="https://pdf/b2")))

        rows = SubscriptionInvoice.objects.filter(stripe_invoice_id="in_basil_2")
        assert rows.count() == 1
        row = rows.first()
        assert row.status == "open"
        assert row.stripe_subscription_id == sub.id
        assert row.hosted_invoice_url == "https://pay/b2"
        # And it must NOT have been treated as a standalone usage invoice.
        assert not CustomerUsageInvoice.objects.filter(
            stripe_invoice_id="in_basil_2").exists()


@pytest.mark.django_db
class TestUsageInvoiceReconcile:
    def _fixtures(self, acct="acct_usage_1"):
        tenant = Tenant.objects.create(
            name="t", products=["metering"], stripe_connected_account_id=acct,
        )
        customer = Customer.objects.create(tenant=tenant, external_id="c1")
        inv = CustomerUsageInvoice.objects.create(
            tenant=tenant, customer=customer,
            period_start=date(2026, 1, 1), period_end=date(2026, 2, 1),
            status="pushed", stripe_invoice_id="in_usage_1",
        )
        return tenant, customer, inv

    def test_finalized_sets_open_and_stores_urls(self):
        tenant, customer, inv = self._fixtures()
        obj = _usage_inv_obj(
            "in_usage_1", hosted_url="https://pay/abc", pdf="https://pdf/abc",
        )
        handle_invoice_finalized(_event(tenant.stripe_connected_account_id, obj=obj))

        inv.refresh_from_db()
        assert inv.payment_status == "open"
        assert inv.hosted_invoice_url == "https://pay/abc"
        assert inv.invoice_pdf == "https://pdf/abc"

    def test_paid_sets_paid_and_paid_at(self):
        tenant, customer, inv = self._fixtures()
        # first finalized -> open
        handle_invoice_finalized(_event(
            tenant.stripe_connected_account_id, obj=_usage_inv_obj("in_usage_1")))
        # then paid
        handle_invoice_paid(_event(
            tenant.stripe_connected_account_id, obj=_usage_inv_obj("in_usage_1")))

        inv.refresh_from_db()
        assert inv.payment_status == "paid"
        assert inv.paid_at is not None

    def test_account_mismatch_no_write(self):
        tenant, customer, inv = self._fixtures()
        handle_invoice_finalized(_event(
            "acct_DIFFERENT", obj=_usage_inv_obj("in_usage_1")))

        inv.refresh_from_db()
        assert inv.payment_status is None  # untouched

    def test_void_and_uncollectible(self):
        tenant, customer, inv = self._fixtures()
        handle_invoice_voided(_event(
            tenant.stripe_connected_account_id, obj=_usage_inv_obj("in_usage_1")))
        inv.refresh_from_db()
        assert inv.payment_status == "void"

        # a second usage invoice for uncollectible
        inv2 = CustomerUsageInvoice.objects.create(
            tenant=tenant, customer=customer,
            period_start=date(2026, 2, 1), period_end=date(2026, 3, 1),
            status="pushed", stripe_invoice_id="in_usage_2",
        )
        handle_invoice_uncollectible(_event(
            tenant.stripe_connected_account_id, obj=_usage_inv_obj("in_usage_2")))
        inv2.refresh_from_db()
        assert inv2.payment_status == "uncollectible"

    def test_monotonic_paid_does_not_regress_to_open(self):
        tenant, customer, inv = self._fixtures()
        handle_invoice_paid(_event(
            tenant.stripe_connected_account_id, obj=_usage_inv_obj("in_usage_1")))
        inv.refresh_from_db()
        assert inv.payment_status == "paid"
        paid_at = inv.paid_at

        # a late finalized arrives -> must NOT regress to open
        handle_invoice_finalized(_event(
            tenant.stripe_connected_account_id, obj=_usage_inv_obj("in_usage_1")))
        inv.refresh_from_db()
        assert inv.payment_status == "paid"
        assert inv.paid_at == paid_at

    def test_uncollectible_then_paid_applies(self):
        """Stripe-legal: an uncollectible invoice remains payable — a late
        invoice.paid must flip the row to paid AND set paid_at."""
        tenant, customer, inv = self._fixtures()
        acct = tenant.stripe_connected_account_id
        handle_invoice_uncollectible(_event(acct, obj=_usage_inv_obj("in_usage_1")))
        inv.refresh_from_db()
        assert inv.payment_status == "uncollectible"

        handle_invoice_paid(_event(acct, obj=_usage_inv_obj("in_usage_1")))
        inv.refresh_from_db()
        assert inv.payment_status == "paid"
        assert inv.paid_at is not None

    def test_void_then_paid_stays_void_without_paid_at(self):
        """void is final: a late invoice.paid must be refused AND must not
        smear paid_at onto the void row (money gates on the APPLIED state)."""
        tenant, customer, inv = self._fixtures()
        acct = tenant.stripe_connected_account_id
        handle_invoice_voided(_event(acct, obj=_usage_inv_obj("in_usage_1")))

        handle_invoice_paid(_event(acct, obj=_usage_inv_obj("in_usage_1")))
        inv.refresh_from_db()
        assert inv.payment_status == "void"
        assert inv.paid_at is None

    def test_paid_then_finalized_stays_paid_but_urls_refresh(self):
        """A refused transition still refreshes URLs (Stripe rotates tokens)."""
        tenant, customer, inv = self._fixtures()
        acct = tenant.stripe_connected_account_id
        handle_invoice_paid(_event(acct, obj=_usage_inv_obj("in_usage_1")))

        handle_invoice_finalized(_event(acct, obj=_usage_inv_obj(
            "in_usage_1", hosted_url="https://pay/late", pdf="https://pdf/late")))
        inv.refresh_from_db()
        assert inv.payment_status == "paid"
        assert inv.hosted_invoice_url == "https://pay/late"
        assert inv.invoice_pdf == "https://pdf/late"


@pytest.mark.django_db
class TestSubscriptionInvoiceReconcile:
    def _fixtures(self, acct="acct_sub_1"):
        tenant = Tenant.objects.create(
            name="t", products=["metering", "subscriptions"],
            stripe_connected_account_id=acct,
        )
        customer = Customer.objects.create(tenant=tenant, external_id="c1")
        now = timezone.now()
        sub = StripeSubscription.objects.create(
            tenant=tenant, customer=customer,
            stripe_subscription_id="sub_ar_1",
            stripe_product_name="Pro", status="active",
            amount_micros=49_000_000, currency="usd", interval="month",
            current_period_start=now, current_period_end=now, last_synced_at=now,
        )
        return tenant, customer, sub

    def test_finalized_creates_open_row_then_paid_flips_same_row(self):
        tenant, customer, sub = self._fixtures()
        acct = tenant.stripe_connected_account_id

        # finalized -> open row created
        handle_invoice_finalized(_event(acct, obj=_sub_inv_obj(
            "in_sub_1", "sub_ar_1", hosted_url="https://pay/s1", pdf="https://pdf/s1")))

        rows = SubscriptionInvoice.objects.filter(stripe_invoice_id="in_sub_1")
        assert rows.count() == 1
        row = rows.first()
        assert row.status == "open"
        assert row.hosted_invoice_url == "https://pay/s1"
        assert row.invoice_pdf == "https://pdf/s1"
        assert row.paid_at is None

        # paid -> SAME row flips to paid (not a 2nd row)
        handle_invoice_paid(_event(acct, obj=_sub_inv_obj("in_sub_1", "sub_ar_1")))

        assert SubscriptionInvoice.objects.filter(stripe_invoice_id="in_sub_1").count() == 1
        row.refresh_from_db()
        assert row.status == "paid"
        assert row.paid_at is not None
        assert row.amount_paid_micros == 49_000_000

    def test_paid_without_prior_finalized_creates_paid_row(self):
        # Born-paid via first-contact invoice.paid: the get_or_create defaults
        # make the row paid; money fields must still land on this path.
        tenant, customer, sub = self._fixtures()
        acct = tenant.stripe_connected_account_id
        handle_invoice_paid(_event(acct, obj=_sub_inv_obj("in_sub_2", "sub_ar_1")))

        row = SubscriptionInvoice.objects.get(stripe_invoice_id="in_sub_2")
        assert row.status == "paid"
        assert row.paid_at is not None
        assert row.amount_paid_micros == 49_000_000

    def test_account_mismatch_no_row(self):
        tenant, customer, sub = self._fixtures()
        handle_invoice_finalized(_event(
            "acct_DIFFERENT", obj=_sub_inv_obj("in_sub_3", "sub_ar_1")))
        assert not SubscriptionInvoice.objects.filter(stripe_invoice_id="in_sub_3").exists()

    def test_void_and_uncollectible(self):
        tenant, customer, sub = self._fixtures()
        acct = tenant.stripe_connected_account_id
        handle_invoice_voided(_event(acct, obj=_sub_inv_obj("in_sub_4", "sub_ar_1")))
        row = SubscriptionInvoice.objects.get(stripe_invoice_id="in_sub_4")
        assert row.status == "void"

        handle_invoice_uncollectible(_event(acct, obj=_sub_inv_obj("in_sub_5", "sub_ar_1")))
        row5 = SubscriptionInvoice.objects.get(stripe_invoice_id="in_sub_5")
        assert row5.status == "uncollectible"

    def test_monotonic_paid_does_not_regress(self):
        tenant, customer, sub = self._fixtures()
        acct = tenant.stripe_connected_account_id
        handle_invoice_paid(_event(acct, obj=_sub_inv_obj("in_sub_6", "sub_ar_1")))
        row = SubscriptionInvoice.objects.get(stripe_invoice_id="in_sub_6")
        assert row.status == "paid"
        paid_at = row.paid_at

        handle_invoice_finalized(_event(acct, obj=_sub_inv_obj("in_sub_6", "sub_ar_1")))
        row.refresh_from_db()
        assert row.status == "paid"
        assert row.paid_at == paid_at

    def test_uncollectible_then_paid_applies(self):
        """Stripe-legal: uncollectible -> paid must apply, with money fields."""
        tenant, customer, sub = self._fixtures()
        acct = tenant.stripe_connected_account_id
        # born uncollectible with NO money yet (amount_paid=0)
        handle_invoice_uncollectible(_event(acct, obj=_sub_inv_obj(
            "in_sub_7", "sub_ar_1", amount_paid=0)))
        row = SubscriptionInvoice.objects.get(stripe_invoice_id="in_sub_7")
        assert row.status == "uncollectible"
        assert row.paid_at is None
        assert row.amount_paid_micros == 0

        # customer pays late -> invoice.paid arrives
        handle_invoice_paid(_event(acct, obj=_sub_inv_obj("in_sub_7", "sub_ar_1")))
        row.refresh_from_db()
        assert row.status == "paid"
        assert row.paid_at is not None
        assert row.amount_paid_micros == 49_000_000

    def test_void_then_paid_stays_void_without_paid_at(self):
        """void is final: a late invoice.paid is refused and must NOT write
        paid_at/amount_paid_micros onto the void row."""
        tenant, customer, sub = self._fixtures()
        acct = tenant.stripe_connected_account_id
        handle_invoice_voided(_event(acct, obj=_sub_inv_obj(
            "in_sub_8", "sub_ar_1", amount_paid=0)))

        handle_invoice_paid(_event(acct, obj=_sub_inv_obj("in_sub_8", "sub_ar_1")))
        row = SubscriptionInvoice.objects.get(stripe_invoice_id="in_sub_8")
        assert row.status == "void"
        assert row.paid_at is None
        assert row.amount_paid_micros == 0

    def test_paid_then_finalized_stays_paid_but_urls_refresh(self):
        tenant, customer, sub = self._fixtures()
        acct = tenant.stripe_connected_account_id
        handle_invoice_paid(_event(acct, obj=_sub_inv_obj("in_sub_9", "sub_ar_1")))

        handle_invoice_finalized(_event(acct, obj=_sub_inv_obj(
            "in_sub_9", "sub_ar_1",
            hosted_url="https://pay/late9", pdf="https://pdf/late9")))
        row = SubscriptionInvoice.objects.get(stripe_invoice_id="in_sub_9")
        assert row.status == "paid"
        assert row.paid_at is not None
        assert row.hosted_invoice_url == "https://pay/late9"
        assert row.invoice_pdf == "https://pdf/late9"
