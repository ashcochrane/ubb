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
    quantity = models.IntegerField(default=1)
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
    amount_paid_micros = models.BigIntegerField(default=0)
    currency = models.CharField(max_length=3, default="usd")
    # NULL until the invoice carries the data: an open (finalized, unpaid) row may
    # arrive before period/paid_at are known.
    period_start = models.DateTimeField(null=True, blank=True)
    period_end = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, default="open")  # open|paid|void|uncollectible
    hosted_invoice_url = models.CharField(max_length=1000, blank=True, default="")
    invoice_pdf = models.CharField(max_length=1000, blank=True, default="")

    class Meta:
        db_table = "ubb_subscription_invoice"

    def __str__(self):
        return f"SubscriptionInvoice({self.stripe_invoice_id})"


class TenantBillingPlan(BaseModel):
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE, related_name="billing_plans")
    key = models.CharField(max_length=64)
    name = models.CharField(max_length=255)
    access_fee_micros = models.BigIntegerField(default=0)
    per_seat_micros = models.BigIntegerField(default=0)
    interval = models.CharField(max_length=5, default="month")  # month|year
    usage_mode = models.CharField(max_length=12, default="invoice_item")  # invoice_item|none
    stripe_access_product_id = models.CharField(max_length=255, blank=True, default="")
    stripe_access_price_id = models.CharField(max_length=255, blank=True, default="")
    stripe_seat_product_id = models.CharField(max_length=255, blank=True, default="")
    stripe_seat_price_id = models.CharField(max_length=255, blank=True, default="")
    provisioned_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "ubb_billing_plan"
        constraints = [models.UniqueConstraint(fields=["tenant", "key"], name="uq_billing_plan_tenant_key")]


class CustomerSubscriptionItem(BaseModel):
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE, related_name="sub_items")
    customer = models.ForeignKey("customers.Customer", on_delete=models.CASCADE, related_name="sub_items")
    stripe_subscription = models.ForeignKey(
        "subscriptions.StripeSubscription", on_delete=models.CASCADE, related_name="line_items"
    )
    stripe_subscription_item_id = models.CharField(max_length=255, unique=True)
    axis = models.CharField(max_length=8)  # access|seat
    stripe_price_id = models.CharField(max_length=255)
    unit_amount_micros = models.BigIntegerField(default=0)
    quantity = models.IntegerField(default=1)
    plan = models.ForeignKey(TenantBillingPlan, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        db_table = "ubb_customer_sub_item"


# Import economics models so Django discovers them for migrations
from apps.subscriptions.economics.models import CustomerCostAccumulator, CustomerEconomics, CustomerRevenueProfile, MarginThresholdConfig  # noqa: E402, F401
