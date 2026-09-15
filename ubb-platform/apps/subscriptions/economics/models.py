from django.db import models
from core.models import BaseModel
from core.transitions import RECORD_RULE
from core.vocabulary import (
    RECOGNITION_METHOD_STRAIGHT_LINE, RECOGNITION_METHOD_VALUES)

#: The registry's whole set on a Django field, built by comprehension rather
#: than written out, so this module enumerates what a column is entitled to
#: enumerate while holding not one value of its own — the shape the posting's
#: five lists already use (`apps/metering/usage/models.py`).
#:
#: THE LABEL IS THE TOKEN, which is that shape's other half and the more
#: easily lost one. Django's second element is not a translation hook, and
#: ADR-0008 §4 puts every human-facing word in the console's locale catalogue
#: keyed off the concept's `label_key_prefix`. English authored here would be
#: a wording nobody can reach, a second copy to keep in step with
#: `apps/ui/src/locales/en.json`, and — because `choices` travels into the
#: migration — one frozen into this app's history for good.
RECOGNITION_METHOD_CHOICES = [
    (value, value) for value in sorted(RECOGNITION_METHOD_VALUES)
]


class CustomerCostAccumulator(BaseModel):
    """Per-customer, per-month provider + billed cost totals (event-driven)."""
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE, related_name="cost_accumulators")
    customer = models.ForeignKey("customers.Customer", on_delete=models.CASCADE, related_name="cost_accumulators")
    period_start = models.DateField()
    period_end = models.DateField()
    total_provider_cost_micros = models.BigIntegerField(default=0)
    total_billed_cost_micros = models.BigIntegerField(default=0)
    event_count = models.IntegerField(default=0)
    # HOW MANY OF THOSE EVENTS THE PROVIDER TOTAL COULD NOT INCLUDE (#328).
    #
    # The handler adds each event's supplier cost as it arrives, and a cost UBB
    # has not resolved (#317) contributes nothing — so without this the running
    # total would be a floor that reads like a figure. Written in the same
    # atomic increment as the amount, because a total and its completeness that
    # can be updated separately will eventually disagree.
    #
    # An event whose Event Type declares no supplier cost is NOT counted: there
    # is nothing missing about a cost that does not exist (#327).
    unresolved_event_count = models.IntegerField(default=0)
    # HOW MANY OF THOSE EVENTS THE BILLED TOTAL COULD NOT INCLUDE (#351).
    #
    # The mirror of the count above. Until this slice the handler coalesced an
    # absent price to zero on the way in, which was sound while the column could
    # not be null and became the silent-zero the moment it could: a period that
    # billed real money would have read complete with a charge missing from it.
    #
    # A second column rather than one count for both, because the two are about
    # different events — a posting can carry a settled cost and a price UBB
    # could not resolve.
    unpriced_event_count = models.IntegerField(default=0)

    class Meta:
        app_label = "subscriptions"
        db_table = "ubb_customer_cost_accumulator"
        constraints = [models.UniqueConstraint(
            fields=["tenant", "customer", "period_start"],
            name="uq_cost_accumulator_tenant_customer_period")]

    def __str__(self):
        return f"CostAccumulator({self.customer_id}: {self.period_start})"


class CustomerEconomics(BaseModel):
    """Per-customer, per-month margin snapshot. revenue = subscription + usage_billed; cost = provider."""
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE, related_name="customer_economics")
    customer = models.ForeignKey("customers.Customer", on_delete=models.CASCADE, related_name="economics")
    period_start = models.DateField()
    period_end = models.DateField()
    subscription_revenue_micros = models.BigIntegerField(default=0)  # manual + stripe
    usage_billed_micros = models.BigIntegerField(default=0)
    provider_cost_micros = models.BigIntegerField(default=0)
    # WHAT THE FROZEN COST TOTAL LEFT OUT, copied from the accumulator this
    # snapshot is taken from (#328).
    #
    # It makes `provider_cost_micros` above a floor and every figure derived
    # from it a bound: `gross_margin_micros` is a CEILING on the margin, and
    # `margin_percentage` a ceiling on the percentage. The column stays NOT
    # NULL — SQL's null-skipping never reaches a snapshot, so `Sum` over it is
    # complete by construction and what travels is this count, not a null.
    #
    # It is also what the cost-spike comparison consults: a previous period
    # whose cost excluded something is too small a denominator, so the rise
    # computed against it would be too big. See MarginService.evaluate_and_emit.
    unresolved_event_count = models.IntegerField(default=0)
    # WHAT THE FROZEN REVENUE TOTAL LEFT OUT, copied from the same accumulator
    # (#351). It makes `usage_billed_micros` a floor, which bounds the derived
    # figures in the OPPOSITE direction from the count above: an excluded cost
    # makes the margin a ceiling, an excluded price makes it a floor, and a
    # snapshot can be both at once.
    #
    # NOT NULL for the same reason its sibling is — a snapshot is never
    # null-skipped, so what travels is the count rather than a null.
    unpriced_event_count = models.IntegerField(default=0)
    gross_margin_micros = models.BigIntegerField(default=0)
    total_revenue_micros = models.BigIntegerField(default=0)
    revenue_mode = models.CharField(max_length=20, blank=True, default="")
    margin_percentage = models.DecimalField(max_digits=7, decimal_places=2, default=0)
    is_unprofitable = models.BooleanField(default=False)

    class Meta:
        app_label = "subscriptions"
        db_table = "ubb_customer_economics"
        constraints = [models.UniqueConstraint(
            fields=["tenant", "customer", "period_start"],
            name="uq_economics_tenant_customer_period")]

    def __str__(self):
        return f"Economics({self.customer_id}: {self.margin_percentage}%)"


class CustomerRevenueProfile(BaseModel):
    """Manual per-customer recurring revenue the tenant collects externally.

    ⚠ **BEING REPLACED BY `TenantSuppliedRevenue` BELOW, and a reader meeting
    the two side by side needs to know which is which.** #153 §3.3 rules this
    one *replaced* rather than widened: one recurring amount per customer, no
    per-period rows, no source reference, and an amount summed into the same
    column as a Stripe subscription — so a revenue figure's provenance is gone
    the moment it lands. The record below is the replacement and #495 built it;
    **carrying these rows onto it, and retiring this model with its route, is
    the next ticket's** (#496). Until then both exist and only this one is read
    by `RevenueService.manual_revenue_for_window`.
    """
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE, related_name="revenue_profiles")
    customer = models.ForeignKey("customers.Customer", on_delete=models.CASCADE, related_name="revenue_profiles")
    recurring_amount_micros = models.BigIntegerField(default=0)
    interval = models.CharField(max_length=10, default="month")
    currency = models.CharField(max_length=3, default="usd")
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)

    class Meta:
        app_label = "subscriptions"
        db_table = "ubb_customer_revenue_profile"
        constraints = [models.UniqueConstraint(
            fields=["tenant", "customer"], name="uq_revenue_profile_tenant_customer")]


class TenantSuppliedRevenue(BaseModel):
    """WHAT A TENANT EARNED FROM ONE CUSTOMER OVER ONE PERIOD, SOMEWHERE OTHER
    THAN UBB (#495, slice 7 §9; the name is #154 §3.7's).

    A tenant may legitimately meter with UBB and bill its customers elsewhere,
    and #153 §3.2 rules that both postures survive: cost-tracking alone, where
    revenue is `unknown` and margin is **unavailable rather than zero**; and
    cost tracking **plus** a supplied figure, where revenue is `known` at the
    scope it was supplied at and margin is available there. This record is the
    second posture made explicit. `CustomerRevenueProfile` above was carrying
    it badly: one recurring amount per customer, no per-period rows, no source
    reference, and the amount summed into the same column as a Stripe
    subscription — so the provenance of a revenue number was destroyed the
    moment it landed.

    ⚠ **IT IS NOT A CHARGE AND NO SURFACE MAY PRESENT IT AS ONE.** UBB neither
    created nor invoiced this money. `pricing.Charge` is what UBB charged a
    customer for a delivered piece of work; this is a number the tenant states
    it collected elsewhere, admitted for analytics. The two are different
    records on different tables with different lifecycles, and the one thing
    that must never happen is a surface adding them into a figure that calls
    itself a charge.

    **WHAT MAKES THE FIGURE READABLE IS `source_reference`,** which is required
    and must carry a non-space character — refused at the database, so the rule
    holds through a data migration and a shell as well as through the route. It
    is the tenant's own handle for where the number came from — its invoice
    number, its ledger line, its export batch — and it travels to every surface
    that shows the amount. A supplied figure with no stated source is exactly
    the thing this record replaces, and a source reference of three spaces is
    that thing wearing a value.

    **THE SPAN IS THE RECORD'S OWN.** `period_start` opens it; `period_end`
    closes it, half-open, and is null for revenue that is a point in time
    rather than a span. A partial period is therefore expressible by
    construction — a customer who began on the fourteenth is one record from
    the fourteenth to the month end — which is the data-entry burden #153
    §19(f) records the recurring profile as having absorbed automatically.

    **TIME IS THE ONLY AXIS IT MAY BE SPREAD ALONG,** and `recognition_method`
    says how. The record declares no supplier, no Event Type and no event, so
    distributing it across any operational axis would invent a boundary it
    never asserted (slice 7 §5). Distributing it *within its own stated span*
    is interpolation inside a boundary the record itself drew, which is a
    different act, and it happens only when a reader asks for the `recognised`
    basis by name.

    **THE RECORD'S RULE, which `transition_classes` declares the absence of a
    per-column one for, stated here because that is where the convention puts
    it** (`docs/conventions/django-patterns.md`): one row per customer per
    period-open per source reference, which is what the uniqueness key means.
    Recording again at that key **re-states** the figure — the same act,
    performed again, audited each time under `tenant_supplied_revenue.recorded`
    — and recording under a *different* source reference adds a second figure
    beside the first rather than replacing it, because two invoices covering
    one month are two facts.

    ⚠ **NOTHING HERE IS FROZEN, AND THAT IS THE DECISION RATHER THAN AN
    OMISSION.** `pricing.Charge` freezes every economic column because money
    moved and a rewrite would erase the trail of a movement UBB performed. No
    money moved here: the tenant is telling UBB what happened in a system UBB
    does not operate, and a mistyped figure it could never correct would make
    this record worse than the profile it replaces. The trail is the audit
    ledger's, which records every statement of the number with its actor, and
    that is the honest place for it.
    """

    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE,
                               related_name="supplied_revenue")
    customer = models.ForeignKey("customers.Customer", on_delete=models.CASCADE,
                                 related_name="supplied_revenue")
    #: WHAT THE TENANT SAYS IT EARNED, in millionths of a currency unit
    #: (ADR-0006 §1). Not constrained non-negative, deliberately: a tenant
    #: whose own billing system issued a credit note has negative revenue for
    #: that period and saying so is the truthful record. A deliberate zero is
    #: also legal and is NOT the same as no record at all — zero is revenue
    #: known to be nothing, which produces a real negative margin against a
    #: known cost, and no record is revenue UBB does not know (#153 §3.4).
    amount_micros = models.BigIntegerField()
    currency = models.CharField(max_length=3)
    #: WHEN THE PERIOD OPENS. Also the day the `recorded` basis places the
    #: whole amount on, because that is the date the tenant is stating the
    #: figure against.
    period_start = models.DateField()
    #: WHEN IT CLOSES, exclusive — or null for revenue that is an instant
    #: rather than a span. Null is not "unknown": it is the record saying
    #: there is nothing to spread, which is why `straight_line` is refused
    #: without one by the check below rather than silently treated as a day.
    period_end = models.DateField(null=True, blank=True)
    recognition_method = models.CharField(
        max_length=32, choices=RECOGNITION_METHOD_CHOICES)
    #: THE TENANT'S OWN HANDLE FOR WHERE THE NUMBER CAME FROM. Free text
    #: because it names a record in a system UBB has never seen, and part of
    #: the uniqueness key because it is what makes two figures covering one
    #: month two figures rather than a contradiction.
    source_reference = models.CharField(max_length=255)

    #: WHAT MAY HAPPEN TO THIS RECORD (ADR-0007 §2).
    #:
    #: Every column declares `RECORD_RULE` — not a fifth class, but the
    #: absence of a per-column one said out loud, with the rule itself in the
    #: docstring above. The question ADR-0007 §2 asks is *what is allowed to
    #: happen to this?*, and for every column here the honest answer is
    #: "nothing this column decides — read the record's rule", which is
    #: `PostingMeasurement`'s and `PricingBookPublish`'s shape.
    #:
    #: ⚠ `RECORD_RULE` sits outside `DATABASE_DEFENDED`, so the declaration
    #: walk judges nothing here and the rule owes its own tests. They are in
    #: two modules, one per half of it:
    #: `apps/subscriptions/tests/test_tenant_supplied_revenue.py` drives the
    #: uniqueness key and the four checks at the database, through `save()`,
    #: `QuerySet.update()` and raw SQL; and
    #: `api/v1/tests/test_a_tenant_may_supply_the_revenue_ubb_cannot_see.py`
    #: proves the route re-states a figure rather than duplicating it, and
    #: audits each statement.
    transition_classes = {
        "id": RECORD_RULE,
        "created_at": RECORD_RULE,
        "updated_at": RECORD_RULE,
        "tenant": RECORD_RULE,
        "customer": RECORD_RULE,
        "amount_micros": RECORD_RULE,
        "currency": RECORD_RULE,
        "period_start": RECORD_RULE,
        "period_end": RECORD_RULE,
        "recognition_method": RECORD_RULE,
        "source_reference": RECORD_RULE,
    }

    class Meta:
        app_label = "subscriptions"
        db_table = "ubb_tenant_supplied_revenue"
        indexes = [models.Index(fields=["tenant", "customer", "period_start"],
                                name="idx_supplied_revenue_window")]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "customer", "period_start", "source_reference"],
                name="uq_supplied_revenue_period_source"),
            # The closed set at the database, which is where a value set
            # belongs: `choices=` is a form-layer courtesy and a `clean()` is
            # a door, and neither is reached by a data migration or a shell.
            models.CheckConstraint(
                condition=models.Q(recognition_method__in=sorted(RECOGNITION_METHOD_VALUES)),
                name="ck_supplied_revenue_known_method"),
            models.CheckConstraint(
                condition=(models.Q(period_end__isnull=True)
                           | models.Q(period_end__gt=models.F("period_start"))),
                name="ck_supplied_revenue_span_opens_before_it_closes"),
            # A span to divide by is what `straight_line` means. Without one
            # the method would have to fall back to something, and every
            # fallback here is UBB assuming a shape the record did not state
            # — which is the unlabelled proration this record exists to end.
            models.CheckConstraint(
                condition=(~models.Q(recognition_method=RECOGNITION_METHOD_STRAIGHT_LINE)
                           | models.Q(period_end__isnull=False)),
                name="ck_supplied_revenue_straight_line_has_a_span"),
            # A NON-SPACE CHARACTER, not merely a non-empty string. Three
            # spaces satisfy `<> ''` and say nothing, and the route's `strip()`
            # is a door rather than the line — ADR-0007 §2's whole point. The
            # pattern is the smallest thing that expresses "says something".
            models.CheckConstraint(
                condition=models.Q(source_reference__regex=r"\S"),
                name="ck_supplied_revenue_says_where_it_came_from"),
        ]

    def __str__(self):
        return (f"TenantSuppliedRevenue({self.customer_id}: {self.period_start} "
                f"{self.source_reference})")


class MarginThresholdConfig(BaseModel):
    """Per-tenant default (+ optional per-customer override) for unprofitable + spike detection."""
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE, related_name="margin_thresholds")
    customer = models.ForeignKey("customers.Customer", on_delete=models.CASCADE,
                                 related_name="margin_thresholds", null=True, blank=True)
    min_margin_pct = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    consecutive_periods = models.IntegerField(default=1)
    provider_cost_spike_pct = models.DecimalField(max_digits=6, decimal_places=2, default=25)

    class Meta:
        app_label = "subscriptions"
        db_table = "ubb_margin_threshold_config"
        constraints = [
            models.UniqueConstraint(fields=["tenant"], condition=models.Q(customer__isnull=True),
                                    name="uq_margin_threshold_tenant_default"),
            models.UniqueConstraint(fields=["tenant", "customer"], condition=models.Q(customer__isnull=False),
                                    name="uq_margin_threshold_tenant_customer"),
        ]
