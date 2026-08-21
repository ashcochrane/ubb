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

    # THE PRICING BOOK THIS PLAN'S CUSTOMERS ARE PRICED FROM (#362, #151 §7.2).
    #
    # Assigning a plan is all it takes to price a customer: this is where their
    # pricing resolves from, at the ladder's selected-book source
    # (`apps/metering/pricing/services/pricing_service.py`). It is a KERNEL
    # concept for the same reason the fee axes are — subscriptions realizes
    # those as Stripe Prices and metering realizes pricing at rating time, and
    # neither owns the catalogue that says which is which.
    #
    # **NOT NULLABLE, AND THE ARGUMENT IS SPECIFIC.** A nullable reference
    # produces an alert nobody can act on, because *"this plan has no book"* is
    # indistinguishable from *"this plan does not price usage"*. Required makes
    # the second case expressible the honest way — a book holding no rules,
    # which is a state a tenant can see and act on — rather than leaving one
    # null standing for both.
    #
    # ⚠ WHAT SUCH A PLAN'S CUSTOMERS RESOLVE TO IS THE MARKUP RUNG'S ANSWER AND
    # NOT THIS COLUMN'S, AND TODAY THE RUNG IS THE PLAN'S OWN. Every event
    # falls past an empty book to `markup_percentage_micros` below, which
    # defaults to zero and is therefore always a rung — so *"the tenant said
    # nothing"* is served as *"the tenant said zero"*. That is deliberate and
    # documented (`apps/platform/CONTEXT.md`, Markup precedence: an explicit
    # zero pins the customer at provider cost), and it is why an empty book
    # does NOT reach `unknown` while these columns exist. Ticket 22 (#369)
    # deletes them, and the rung then falls to the tenant's declared default or
    # to `unknown`.
    #
    # **REQUIRED MEANS CREATION IS ORDERED**, and that ordering is this
    # column's, not a convention: nothing can write a Plan row before the book
    # row exists, so `PlanService.create` takes the book it will name and the
    # composition layer creates it first (`api/v1/plan_endpoints.py`).
    #
    # `PROTECT`, THE WAY A PRICING RULE ALREADY HOLDS THE BOOK IT LIVES IN. A
    # book a plan prices from may not
    # be deleted out from under it — the plan would then be a plan with no
    # pricing, which is the state this column exists to make unreachable.
    # ⚠ It is also why the sandbox reset takes plans before books when it is
    # wiping configuration (`apps/platform/tenants/tasks.py`); a `PROTECT` the
    # generic sweep reaches in the wrong order fails the WHOLE reset (#358).
    #
    # ⚠ THE KERNEL VALIDATES NOTHING BEYOND THIS FOREIGN KEY. ADR-001 forbids
    # `apps/platform/**` importing a product, so the reference is declared by
    # app label and the database is what refuses a book that does not exist.
    # It names the entity under the name that entity now has (#368). The
    # container split into a Pricing Book and a cost book, and a plan prices
    # its customers, so this reference follows the PRICE half by construction
    # — there is no longer a kind word for it to be wrong about. The rename
    # travelled in the product's own `RenameModel`, which rewrote the
    # reference in migration state, so this was one string edit and no import
    # anywhere broke.
    pricing_book = models.ForeignKey("pricing.PricingBook",
                                     on_delete=models.PROTECT,
                                     related_name="plans")

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

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        _invalidate_markup_cache(self.tenant_id)

    def delete(self, *args, **kwargs):
        tenant_id = self.tenant_id
        result = super().delete(*args, **kwargs)
        _invalidate_markup_cache(tenant_id)
        return result


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

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        _invalidate_markup_cache(self.tenant_id)

    def delete(self, *args, **kwargs):
        tenant_id = self.tenant_id
        result = super().delete(*args, **kwargs)
        _invalidate_markup_cache(tenant_id)
        return result


def _invalidate_markup_cache(tenant_id):
    """Bump the tenant's markup cache version.

    Lazy import: the kernel may not import a product at module scope
    (ADR-001), and metering is an optional consumer of plans. A missing
    metering app must not break a plan write, so the import is best-effort.
    """
    try:
        from apps.metering.pricing.services.markup_cache import MarkupCache
    except ImportError:  # pragma: no cover - metering always installed today
        return
    MarkupCache.invalidate(tenant_id)
