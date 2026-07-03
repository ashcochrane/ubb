import hashlib
import json
import uuid

from django.db import models

from core.models import BaseModel


class TenantMarkup(BaseModel):
    tenant = models.ForeignKey(
        "tenants.Tenant", on_delete=models.CASCADE, related_name="markups",
    )
    customer = models.ForeignKey(
        "customers.Customer", on_delete=models.CASCADE, related_name="markups",
        null=True, blank=True,
    )
    markup_percentage_micros = models.BigIntegerField(default=0)  # 1_000_000 == 1%
    fixed_uplift_micros = models.BigIntegerField(default=0)

    class Meta:
        db_table = "ubb_tenant_markup"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant"], condition=models.Q(customer__isnull=True),
                name="uq_markup_tenant_default",
            ),
            models.UniqueConstraint(
                fields=["tenant", "customer"], condition=models.Q(customer__isnull=False),
                name="uq_markup_tenant_customer",
            ),
        ]

    def calculate_markup_micros(self, provider_cost_micros: int) -> int:
        percent = (provider_cost_micros * self.markup_percentage_micros + 50_000_000) // 100_000_000
        return percent + self.fixed_uplift_micros


CARD_TYPE_CHOICES = [("cost", "Cost"), ("price", "Price")]
PRICING_MODEL_CHOICES = [
    ("per_unit", "Per unit"),
    ("flat", "Flat"),
    ("graduated", "Graduated"),
    ("package", "Package"),
]

# Tiered models are priced as MARGINAL cumulative differences against a
# per-period unit ladder (PricingPeriodCounter) — never via compute().
TIERED_PRICING_MODELS = ("graduated", "package")

MAX_GRADUATED_TIERS = 20
_TIER_KEYS = {"up_to", "rate_per_unit_micros", "unit_quantity", "flat_micros"}


def _is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def validate_tiers(card_type, pricing_model, tiers):
    """Validate the (card_type, pricing_model, tiers) combination.

    Raises ValueError with a caller-presentable message on any violation.
    Graduated/package are PRICE-card only — cost cards stay per_unit/flat
    (a tiered cost card would need period context inside the cost loop).

    graduated tier shape: {"up_to": int>0 | None, "rate_per_unit_micros": int>=0,
    "unit_quantity": int>0 (optional, default 1_000_000), "flat_micros": int>=0
    (optional, charged once when the ladder first enters the band)}.
    package reuses the card's scalar fields (rate_per_unit_micros = price per
    block, unit_quantity = block size, fixed_micros = one-time period fee) and
    must have tiers == [].
    """
    tiers = tiers if tiers is not None else []
    if not isinstance(tiers, list):
        raise ValueError("tiers must be a list")
    if pricing_model in TIERED_PRICING_MODELS and card_type == "cost":
        raise ValueError(
            f"pricing_model '{pricing_model}' is not allowed on cost cards")
    if pricing_model != "graduated":
        if tiers:
            raise ValueError(
                f"tiers must be empty for pricing_model '{pricing_model}'")
        return
    if not tiers:
        raise ValueError("graduated pricing requires a non-empty tiers list")
    if len(tiers) > MAX_GRADUATED_TIERS:
        raise ValueError(
            f"graduated pricing supports at most {MAX_GRADUATED_TIERS} tiers")
    prev_up_to = 0
    for i, tier in enumerate(tiers):
        if not isinstance(tier, dict):
            raise ValueError(f"tiers[{i}] must be an object")
        unknown = sorted(set(tier) - _TIER_KEYS)
        if unknown:
            raise ValueError(f"tiers[{i}] has unknown keys: {unknown}")
        if "rate_per_unit_micros" not in tier:
            raise ValueError(f"tiers[{i}] is missing rate_per_unit_micros")
        rate = tier["rate_per_unit_micros"]
        if not _is_int(rate) or rate < 0:
            raise ValueError(
                f"tiers[{i}].rate_per_unit_micros must be an integer >= 0")
        unit_quantity = tier.get("unit_quantity", 1_000_000)
        if not _is_int(unit_quantity) or unit_quantity <= 0:
            raise ValueError(f"tiers[{i}].unit_quantity must be an integer > 0")
        flat = tier.get("flat_micros", 0)
        if not _is_int(flat) or flat < 0:
            raise ValueError(f"tiers[{i}].flat_micros must be an integer >= 0")
        if "up_to" not in tier:
            raise ValueError(f"tiers[{i}] is missing up_to")
        up_to = tier["up_to"]
        if i == len(tiers) - 1:
            if up_to is not None:
                raise ValueError(
                    "the last graduated tier must have up_to=None (unbounded)")
        else:
            if up_to is None:
                raise ValueError("only the last graduated tier may have up_to=None")
            if not _is_int(up_to) or up_to <= 0:
                raise ValueError(f"tiers[{i}].up_to must be an integer > 0 or None")
            if up_to <= prev_up_to:
                raise ValueError("tiers up_to values must be strictly increasing")
            prev_up_to = up_to


class Rate(BaseModel):
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE, related_name="rate_cards")
    customer = models.ForeignKey("customers.Customer", on_delete=models.CASCADE,
                                 related_name="rate_cards", null=True, blank=True)
    card_type = models.CharField(max_length=10, choices=CARD_TYPE_CHOICES, db_index=True)
    provider = models.CharField(max_length=100, blank=True, default="", db_index=True)
    event_type = models.CharField(max_length=100, blank=True, default="", db_index=True)
    metric_name = models.CharField(max_length=100)
    dimensions = models.JSONField(default=dict)
    dimensions_hash = models.CharField(max_length=64, blank=True, default="", db_index=True)
    pricing_model = models.CharField(max_length=20, choices=PRICING_MODEL_CHOICES, default="per_unit")
    rate_per_unit_micros = models.BigIntegerField(default=0)
    unit_quantity = models.BigIntegerField(default=1_000_000)
    fixed_micros = models.BigIntegerField(default=0)
    tiers = models.JSONField(default=list, blank=True)
    currency = models.CharField(max_length=3, default="usd")
    product_id = models.CharField(max_length=100, blank=True, default="")
    rate_card = models.ForeignKey("pricing.RateCard", on_delete=models.PROTECT,
                                  related_name="rates", null=True, blank=True)
    book_version_from = models.PositiveIntegerField(default=1)
    book_version_to = models.PositiveIntegerField(null=True, blank=True)
    lineage_id = models.UUIDField(default=uuid.uuid4, editable=False, db_index=True)
    valid_from = models.DateTimeField(auto_now_add=True, db_index=True)
    valid_to = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "ubb_rate_card"
        indexes = [
            models.Index(fields=["tenant", "card_type", "provider", "event_type", "metric_name"],
                         name="idx_ratecard_lookup"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "card_type", "provider", "event_type", "metric_name",
                        "dimensions_hash", "currency"],
                condition=models.Q(valid_to__isnull=True, customer__isnull=True),
                name="uq_ratecard_active_tenant"),
            models.UniqueConstraint(
                fields=["tenant", "customer", "card_type", "provider", "event_type", "metric_name",
                        "dimensions_hash", "currency"],
                condition=models.Q(valid_to__isnull=True, customer__isnull=False),
                name="uq_ratecard_active_customer"),
        ]

    def save(self, *args, **kwargs):
        self.dimensions_hash = hashlib.sha256(
            json.dumps(self.dimensions or {}, sort_keys=True).encode()).hexdigest()
        super().save(*args, **kwargs)

    def compute(self, units):
        if self.pricing_model in TIERED_PRICING_MODELS:
            # No caller may price a tiered card without period context — this is
            # also the guard that keeps tiered cards out of the cost loop.
            raise ValueError(
                f"Rate.compute() cannot price tiered pricing_model "
                f"'{self.pricing_model}' without period context; use compute_marginal()")
        if self.pricing_model == "flat":
            return self.fixed_micros
        units = units or 0
        return (units * self.rate_per_unit_micros + self.unit_quantity // 2) // self.unit_quantity + self.fixed_micros

    def compute_cumulative(self, q):
        """Cumulative period charge T(q) for q total units. Tiered models only.

        graduated: sum over bands the ladder has entered (band lower bound < q)
        of the band's flat_micros plus the half-up-rounded charge for the units
        falling inside the band — the same division as compute().
        package:   T(0) = 0; T(q>0) = ceil(q / unit_quantity) blocks at
        rate_per_unit_micros plus the one-time fixed_micros period fee.

        Events are priced as the marginal difference T(prior+units) - T(prior),
        so marginals telescope: their sum over any event split equals T(total)
        EXACTLY — invoices, wallets, and this closed form always agree.
        """
        q = q or 0
        if q < 0:
            raise ValueError("cumulative quantity cannot be negative")
        if self.pricing_model == "graduated":
            total, lower = 0, 0
            for tier in self.tiers:
                if q <= lower:
                    break
                up_to = tier["up_to"]
                upper = q if up_to is None else min(q, up_to)
                unit_quantity = tier.get("unit_quantity", 1_000_000)
                total += tier.get("flat_micros", 0)  # band entered (lower < q)
                total += ((upper - lower) * tier["rate_per_unit_micros"]
                          + unit_quantity // 2) // unit_quantity
                if up_to is None:
                    break
                lower = up_to
            return total
        if self.pricing_model == "package":
            if q <= 0:
                return 0
            blocks = -(-q // self.unit_quantity)  # ceil division
            return blocks * self.rate_per_unit_micros + self.fixed_micros
        raise ValueError(
            f"compute_cumulative() only supports tiered pricing models, "
            f"not '{self.pricing_model}'")

    def compute_marginal(self, prior_units, units):
        """Marginal charge for `units` more units after `prior_units` this period."""
        prior_units = prior_units or 0
        units = units or 0
        return (self.compute_cumulative(prior_units + units)
                - self.compute_cumulative(prior_units))


class RateCard(BaseModel):
    """Container grouping many Rates, versioned and assigned as a unit.

    Naming wart: the physical table is `ubb_rate_card_container` because the
    legacy `ubb_rate_card` table now backs the `Rate` model (the old, misnamed
    RateCard). The Python names are correct: RateCard = the sheet, Rate = a line.
    """
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE,
                               related_name="rate_card_containers")
    card_type = models.CharField(max_length=10, choices=CARD_TYPE_CHOICES, db_index=True)
    # provider_key pins the book to one provider so the per-provider default
    # invariant is DB-enforceable ("" is the no-provider bucket).
    provider_key = models.CharField(max_length=100, blank=True, default="")
    currency = models.CharField(max_length=3, default="usd")
    key = models.SlugField(max_length=64)
    name = models.CharField(max_length=255, blank=True, default="")
    version = models.PositiveIntegerField(default=1)
    is_default = models.BooleanField(default=False)

    class Meta:
        db_table = "ubb_rate_card_container"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "card_type", "key"], name="uq_ratecard_tenant_key"),
            models.UniqueConstraint(
                fields=["tenant", "card_type", "provider_key", "currency"],
                condition=models.Q(is_default=True),
                name="uq_ratecard_one_default_per_provider"),
        ]

    def __str__(self):
        return f"RateCard({self.key} v{self.version})"


class RateCardAssignment(BaseModel):
    """A customer's assigned PRICE book (one per customer per currency)."""
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE,
                               related_name="rate_card_assignments")
    customer = models.ForeignKey("customers.Customer", on_delete=models.CASCADE,
                                 related_name="rate_card_assignments")
    rate_card = models.ForeignKey(RateCard, on_delete=models.CASCADE,
                                  related_name="assignments")
    currency = models.CharField(max_length=3, default="usd")

    class Meta:
        db_table = "ubb_rate_card_assignment"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "customer", "currency"],
                name="uq_assignment_customer_currency"),
        ]


class PricingPeriodCounter(BaseModel):
    """Per-period cumulative unit ladder for tiered (graduated/package) price cards.

    Keyed on lineage_id (NOT metric_name) so customer overrides, dimensional
    variants and card versions each get their own ladder, while version bumps
    (same lineage) keep marginal continuity across mid-period price changes.
    Period bounds are the calendar month in UTC of the record-time `as_of`.
    """
    tenant = models.ForeignKey(
        "tenants.Tenant", on_delete=models.CASCADE,
        related_name="pricing_period_counters")
    customer = models.ForeignKey(
        "customers.Customer", on_delete=models.CASCADE,
        related_name="pricing_period_counters")
    lineage_id = models.UUIDField(db_index=True)
    metric_name = models.CharField(max_length=100)
    currency = models.CharField(max_length=3, default="usd")
    period_start = models.DateField()
    period_end = models.DateField()
    units_total = models.BigIntegerField(default=0)

    class Meta:
        db_table = "ubb_pricing_period_counter"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "customer", "lineage_id", "period_start"],
                name="uq_pricing_period_counter",
            ),
        ]

    def __str__(self):
        return (f"PricingPeriodCounter({self.lineage_id} "
                f"{self.period_start}: {self.units_total})")
