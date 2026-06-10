"""
Wave 5a: AR/payment-status + hosted-invoice-link columns round-trip tests.
"""
import datetime
import pytest
from django.utils import timezone

from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer


@pytest.mark.django_db
class TestCustomerUsageInvoiceARFields:
    def test_ar_fields_round_trip(self):
        from apps.billing.invoicing.models import CustomerUsageInvoice

        t = Tenant.objects.create(name="T-ar")
        c = Customer.objects.create(tenant=t, external_id="c-ar-1")

        inv = CustomerUsageInvoice.objects.create(
            tenant=t,
            customer=c,
            period_start=datetime.date(2026, 6, 1),
            period_end=datetime.date(2026, 7, 1),
            total_billed_micros=5_000_000,
            currency="usd",
            stripe_invoice_id="in_usage_001",
            payment_status="paid",
            hosted_invoice_url="https://x",
            invoice_pdf="https://x.pdf",
        )
        inv.refresh_from_db()

        assert inv.payment_status == "paid"
        assert inv.hosted_invoice_url == "https://x"
        assert inv.invoice_pdf == "https://x.pdf"
        assert inv.paid_at is None
        assert inv.payment_failed_at is None

    def test_payment_status_nullable(self):
        """payment_status=NULL means 'not yet collectible'."""
        from apps.billing.invoicing.models import CustomerUsageInvoice

        t = Tenant.objects.create(name="T-ar2")
        c = Customer.objects.create(tenant=t, external_id="c-ar-2")

        inv = CustomerUsageInvoice.objects.create(
            tenant=t,
            customer=c,
            period_start=datetime.date(2026, 6, 1),
            period_end=datetime.date(2026, 7, 1),
        )
        inv.refresh_from_db()
        assert inv.payment_status is None

    def test_stripe_invoice_id_has_db_index(self):
        """stripe_invoice_id on CustomerUsageInvoice is now indexed."""
        from apps.billing.invoicing.models import CustomerUsageInvoice

        field = CustomerUsageInvoice._meta.get_field("stripe_invoice_id")
        assert field.db_index is True

    def test_paid_at_and_failed_at_fields(self):
        from apps.billing.invoicing.models import CustomerUsageInvoice

        t = Tenant.objects.create(name="T-ar3")
        c = Customer.objects.create(tenant=t, external_id="c-ar-3")
        now = timezone.now()

        inv = CustomerUsageInvoice.objects.create(
            tenant=t,
            customer=c,
            period_start=datetime.date(2026, 6, 1),
            period_end=datetime.date(2026, 7, 1),
            payment_status="paid",
            paid_at=now,
        )
        inv.refresh_from_db()
        assert inv.paid_at is not None
        assert inv.payment_failed_at is None


@pytest.mark.django_db
class TestSubscriptionInvoiceARFields:
    def _make_stripe_sub(self, tenant, customer, sub_id="sub_ar_001"):
        from apps.subscriptions.models import StripeSubscription

        now = timezone.now()
        return StripeSubscription.objects.create(
            tenant=tenant,
            customer=customer,
            stripe_subscription_id=sub_id,
            stripe_product_name="Pro Plan",
            status="active",
            amount_micros=49_000_000,
            currency="usd",
            interval="month",
            current_period_start=now,
            current_period_end=now,
            last_synced_at=now,
        )

    def test_ar_fields_round_trip(self):
        from apps.subscriptions.models import SubscriptionInvoice

        t = Tenant.objects.create(name="T-sub-ar")
        c = Customer.objects.create(tenant=t, external_id="c-sub-ar-1")
        now = timezone.now()
        sub = self._make_stripe_sub(t, c)

        inv = SubscriptionInvoice.objects.create(
            tenant=t,
            customer=c,
            stripe_subscription=sub,
            stripe_invoice_id="in_sub_ar_001",
            amount_paid_micros=49_000_000,
            currency="usd",
            period_start=now,
            period_end=now,
            paid_at=now,
            status="open",
            hosted_invoice_url="https://y",
            invoice_pdf="https://y.pdf",
        )
        inv.refresh_from_db()

        assert inv.status == "open"
        assert inv.hosted_invoice_url == "https://y"
        assert inv.invoice_pdf == "https://y.pdf"

    def test_status_default_is_open(self):
        from apps.subscriptions.models import SubscriptionInvoice

        t = Tenant.objects.create(name="T-sub-ar2")
        c = Customer.objects.create(tenant=t, external_id="c-sub-ar-2")
        now = timezone.now()
        sub = self._make_stripe_sub(t, c, sub_id="sub_ar_002")

        inv = SubscriptionInvoice.objects.create(
            tenant=t,
            customer=c,
            stripe_subscription=sub,
            stripe_invoice_id="in_sub_ar_002",
            amount_paid_micros=49_000_000,
            currency="usd",
            period_start=now,
            period_end=now,
            paid_at=now,
        )
        inv.refresh_from_db()
        assert inv.status == "open"

    def test_hosted_url_and_pdf_blank_by_default(self):
        from apps.subscriptions.models import SubscriptionInvoice

        t = Tenant.objects.create(name="T-sub-ar3")
        c = Customer.objects.create(tenant=t, external_id="c-sub-ar-3")
        now = timezone.now()
        sub = self._make_stripe_sub(t, c, sub_id="sub_ar_003")

        inv = SubscriptionInvoice.objects.create(
            tenant=t,
            customer=c,
            stripe_subscription=sub,
            stripe_invoice_id="in_sub_ar_003",
            amount_paid_micros=10_000_000,
            currency="usd",
            period_start=now,
            period_end=now,
            paid_at=now,
        )
        inv.refresh_from_db()
        assert inv.hosted_invoice_url == ""
        assert inv.invoice_pdf == ""
