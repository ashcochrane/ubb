from django.db import models

from core.models import BaseModel

INTERVAL_CHOICES = [("month", "Month"), ("year", "Year")]


class Plan(BaseModel):
    """A tenant's commercial offer, with three axes.

    Two axes are realized by Stripe (licensed Prices on a Subscription); the
    third — what the plan's customers are charged for metered compute — Stripe
    cannot represent, because it has no knowledge of provider cost. That axis
    is the Pricing Book below, and until #369 it was also two columns on this
    row. That is why Plan is a kernel concept: subscriptions and metering each
    realize one part of it, and neither owns it (ADR-001 rule 1 — any product
    may import apps.platform.*).

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
    # NOT THIS COLUMN'S, AND SINCE #369 THE PLAN SUPPLIES NO RUNG. An event
    # that falls past an empty book reaches the tenant's declared default
    # markup rung, and where the tenant has declared none it reaches `unknown`
    # — a price nobody has stated, with no amount at all. Until #369 this row
    # carried a percentage column defaulting to zero, so it was ALWAYS a rung
    # and *"the tenant said nothing"* was served as *"the tenant said zero"*.
    # That was documented rather than accidental (`apps/platform/CONTEXT.md`,
    # Markup precedence: an explicit zero pins the customer at provider cost) —
    # but a default is not a declaration, and deleting the column is what makes
    # `unknown` reachable for a customer on a plan.
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

    # THE UBB-REALIZED AXIS IS THE BOOK ABOVE, AND IT USED TO BE TWO COLUMNS
    # HERE (#369). A percentage and a per-event flat addend sat on this row and
    # were read as a rung of the markup ladder. Both are gone: what a plan's
    # customers are charged is the rules in the Pricing Book the plan names, and
    # where that book prices nothing the answer is the tenant's declared default
    # markup rung or `unknown`. Deleted rather than renamed — the percentage
    # column hid millionths of a percent under the money suffix (G11), and a
    # rename would have moved that spelling onto a column with no reader left.

    # Opaque Stripe binding — written only by apps/subscriptions.
    stripe_access_product_id = models.CharField(max_length=255, blank=True, default="")
    stripe_access_price_id = models.CharField(max_length=255, blank=True, default="")
    stripe_seat_product_id = models.CharField(max_length=255, blank=True, default="")
    stripe_seat_price_id = models.CharField(max_length=255, blank=True, default="")
    provisioned_at = models.DateTimeField(null=True, blank=True)
    # Bumped once per re-price of a provisioned axis. Stripe Prices are
    # immutable, so a fee edit mints a NEW Price and existing subscribers are
    # grandfathered on the old one unless explicitly migrated. The usage axis
    # has no Stripe object and is therefore always live — the asymmetry is
    # deliberate, and it is why only the two fee columns move this number.
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

        False for a usage-only plan ($0 access, $0 seat, priced entirely from
        the Pricing Book it names), which has no Stripe Product, Price, or
        Subscription at all.
        """
        return self.access_fee_micros > 0 or self.per_seat_micros > 0


class CustomerPlanAssignment(BaseModel):
    """Which plan a customer is on.

    This row — not the Stripe subscription — is the source of truth for plan
    membership, which is what lets a usage-only customer be on a real plan
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


# THE MARKUP-CACHE INVALIDATION HOOKS LEFT WITH THE COLUMNS THEY GUARDED
# (#369). Both models above bumped `MarkupCache`'s per-tenant version key from
# `save()` and `delete()`, because a plan's percentage and a customer's plan
# membership were each read by `MarkupService.resolve` and a cached rung had to
# be dropped when either moved. That rung is deleted: resolve reads the tenant's
# declared default and nothing else, and that record bumps the same key from its
# own model layer. A bump left here would be a write no read depends on, and a
# reader would take it for evidence that a plan still feeds the ladder.
