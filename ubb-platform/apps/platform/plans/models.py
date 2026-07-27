from django.db import models

from core.models import BaseModel

INTERVAL_CHOICES = [("month", "Month"), ("year", "Year")]


class Plan(BaseModel):
    """A tenant's commercial offer, with three axes.

    Two axes are realized by Stripe (licensed Prices on a Subscription);
    the third — markup on metered compute — Stripe cannot represent, because
    it has no knowledge of provider cost. That is why Plan is a kernel
    concept: subscriptions and metering each realize one part of it, and
    neither owns it (ADR-001 rule 1 — any product may import apps.platform.*).

    The stripe_* fields are an OPAQUE external binding: the kernel stores
    them and never interprets them. Only apps/subscriptions reads or writes
    them.
    """
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE,
                               related_name="plans")
    key = models.SlugField(max_length=64)
    name = models.CharField(max_length=255)

    # Stripe-realized axes. 0 means "this axis is absent", not "free" — an
    # absent axis produces no Stripe Price and no subscription item.
    access_fee_micros = models.BigIntegerField(default=0)
    per_seat_micros = models.BigIntegerField(default=0)
    interval = models.CharField(max_length=5, choices=INTERVAL_CHOICES, default="month")

    # UBB-realized axis. Units match TenantMarkup exactly: 1_000_000 == 1%.
    markup_percentage_micros = models.BigIntegerField(default=0)
    fixed_uplift_micros = models.BigIntegerField(default=0)

    # Opaque Stripe binding — written only by apps/subscriptions.
    stripe_access_product_id = models.CharField(max_length=255, blank=True, default="")
    stripe_access_price_id = models.CharField(max_length=255, blank=True, default="")
    stripe_seat_product_id = models.CharField(max_length=255, blank=True, default="")
    stripe_seat_price_id = models.CharField(max_length=255, blank=True, default="")
    provisioned_at = models.DateTimeField(null=True, blank=True)
    # Bumped once per re-price of a provisioned axis. Stripe Prices are
    # immutable, so a fee edit mints a NEW Price and existing subscribers are
    # grandfathered on the old one unless explicitly migrated. Markup has no
    # Stripe object and is therefore always live — the asymmetry is deliberate.
    pricing_version = models.PositiveIntegerField(default=1)

    archived_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "ubb_plan"
        constraints = [
            models.UniqueConstraint(fields=["tenant", "key"], name="uq_plan_tenant_key"),
        ]

    def __str__(self):
        return f"Plan({self.key})"

    @property
    def has_stripe_axes(self) -> bool:
        """True when this plan charges a fee Stripe must bill.

        False for a markup-only plan (e.g. $0 access + 50% markup), which has
        no Stripe Product, Price, or Subscription at all.
        """
        return self.access_fee_micros > 0 or self.per_seat_micros > 0


class CustomerPlanAssignment(BaseModel):
    """Which plan a customer is on.

    This row — not the Stripe subscription — is the source of truth for plan
    membership, which is what lets a markup-only customer be on a real plan
    with zero presence in Stripe Billing.
    """
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE,
                               related_name="plan_assignments")
    customer = models.ForeignKey("customers.Customer", on_delete=models.CASCADE,
                                 related_name="plan_assignments")
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT,
                             related_name="assignments")
    assigned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "ubb_customer_plan_assignment"
        constraints = [
            models.UniqueConstraint(fields=["tenant", "customer"],
                                    name="uq_plan_assignment_customer"),
        ]

    def __str__(self):
        return f"CustomerPlanAssignment({self.customer_id} -> {self.plan_id})"
