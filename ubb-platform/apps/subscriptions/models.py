from django.db import models
from core.models import BaseModel


SUBSCRIPTION_STATUS_CHOICES = [
    ("active", "Active"),
    ("past_due", "Past Due"),
    ("canceled", "Canceled"),
    ("incomplete", "Incomplete"),
    ("incomplete_expired", "Incomplete Expired"),
    ("trialing", "Trialing"),
    ("unpaid", "Unpaid"),
    ("paused", "Paused"),
]


class StripeSubscription(BaseModel):
    """Read-only mirror of a Stripe subscription on the tenant's Connected Account."""
    tenant = models.ForeignKey(
        "tenants.Tenant", on_delete=models.CASCADE, related_name="stripe_subscriptions"
    )
    customer = models.ForeignKey(
        "customers.Customer", on_delete=models.CASCADE, related_name="stripe_subscriptions"
    )
    stripe_subscription_id = models.CharField(max_length=255, unique=True, db_index=True)
    stripe_product_name = models.CharField(max_length=255)
    status = models.CharField(max_length=20, choices=SUBSCRIPTION_STATUS_CHOICES, db_index=True)
    amount_micros = models.BigIntegerField()
    currency = models.CharField(max_length=3, default="usd")
    interval = models.CharField(max_length=10)
    current_period_start = models.DateTimeField()
    current_period_end = models.DateTimeField()
    last_synced_at = models.DateTimeField()

    class Meta:
        db_table = "ubb_stripe_subscription"
        indexes = [
            models.Index(fields=["tenant", "status"], name="idx_stripesub_tenant_status"),
        ]

    def __str__(self):
        return f"StripeSubscription({self.stripe_subscription_id}: {self.status})"


class SubscriptionInvoice(BaseModel):
    """Synced from Stripe — tracks each paid invoice for revenue attribution."""
    tenant = models.ForeignKey(
        "tenants.Tenant", on_delete=models.CASCADE, related_name="subscription_invoices"
    )
    customer = models.ForeignKey(
        "customers.Customer", on_delete=models.CASCADE, related_name="subscription_invoices"
    )
    stripe_subscription = models.ForeignKey(
        StripeSubscription, on_delete=models.CASCADE, related_name="invoices"
    )
    stripe_invoice_id = models.CharField(max_length=255, unique=True, db_index=True)
    amount_paid_micros = models.BigIntegerField()
    currency = models.CharField(max_length=3, default="usd")
    period_start = models.DateTimeField()
    period_end = models.DateTimeField()
    paid_at = models.DateTimeField()

    class Meta:
        db_table = "ubb_subscription_invoice"

    def __str__(self):
        return f"SubscriptionInvoice({self.stripe_invoice_id})"


# Import economics models so Django discovers them for migrations
from apps.subscriptions.economics.models import CustomerCostAccumulator, CustomerEconomics  # noqa: E402, F401
