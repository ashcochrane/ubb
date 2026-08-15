import uuid

from django.db import models
from django.utils import timezone

from apps.platform.grouping_fields.models import SLOT_CHOICES
from core.models import BaseModel
from core.transitions import FROZEN, SET_ONCE


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

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        from apps.metering.pricing.services.markup_cache import MarkupCache
        MarkupCache.invalidate(self.tenant_id)

    def delete(self, *args, **kwargs):
        tenant_id = self.tenant_id
        result = super().delete(*args, **kwargs)
        from apps.metering.pricing.services.markup_cache import MarkupCache
        MarkupCache.invalidate(tenant_id)
        return result


CARD_TYPE_CHOICES = [("cost", "Cost"), ("price", "Price")]
# per_unit/flat only: ADR-0003 — the MVP launches without tiered pricing
# (graduated/package deleted end to end, not gated), so every arrival-time
# estimate equals the settled price by construction.
PRICING_MODEL_CHOICES = [
    ("per_unit", "Per unit"),
    ("flat", "Flat"),
]


class Rate(BaseModel):
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE, related_name="rate_cards")
    customer = models.ForeignKey("customers.Customer", on_delete=models.CASCADE,
                                 related_name="rate_cards", null=True, blank=True)
    card_type = models.CharField(max_length=10, choices=CARD_TYPE_CHOICES, db_index=True)
    # --- The fourteen selector columns (design D3) ---
    # "" means WILDCARD here (it means "not set" on a Posting). Among rates
    # matching an event, the winner has the most non-empty selectors. This is
    # the ONE matching semantic — the old JSONB `dimensions` subset match and
    # the exact-equality provider/event_type match were two different rules on
    # one query.
    provider = models.CharField(max_length=100, blank=True, default="", db_index=True)
    event_type = models.CharField(max_length=100, blank=True, default="", db_index=True)
    task_type = models.CharField(max_length=64, blank=True, default="")
    subtask_type = models.CharField(max_length=64, blank=True, default="")
    # Ten, matching the registry and the Posting since #276: a slot a tenant
    # can declare and attribute but cannot PRICE on would be a grouping axis
    # that silently is not a rate selector, which is the split D3 exists to
    # close. Only six of these reach the published contract, and no slice-2
    # ticket widens that — this entity's published surface is rebuilt in slice
    # 4. `api/v1/schemas.py:SLOT_PROPERTY_COLUMNS` holds the join and the gap.
    grouping_field_1 = models.CharField(max_length=100, blank=True, default="")
    grouping_field_2 = models.CharField(max_length=100, blank=True, default="")
    grouping_field_3 = models.CharField(max_length=100, blank=True, default="")
    grouping_field_4 = models.CharField(max_length=100, blank=True, default="")
    grouping_field_5 = models.CharField(max_length=100, blank=True, default="")
    grouping_field_6 = models.CharField(max_length=100, blank=True, default="")
    grouping_field_7 = models.CharField(max_length=100, blank=True, default="")
    grouping_field_8 = models.CharField(max_length=100, blank=True, default="")
    grouping_field_9 = models.CharField(max_length=100, blank=True, default="")
    grouping_field_10 = models.CharField(max_length=100, blank=True, default="")
    # WHICH DECLARED QUANTITY THIS RATE PRICES, BY NAME — and free text on
    # purpose, not by omission. Slice 2 pays the word; slice 3 replaces this
    # with a reference to the declared record the name is a name *of*, at which
    # point a rate naming a quantity nobody declared stops being writable.
    # Until then the two sides agree by spelling alone, exactly as they did
    # under the retired name. ADR-0007 §3 is what sanctions shipping the final
    # name over a half-built implementation, and
    # `tests/test_the_rates_quantity_name_takes_the_canonical_name.py` is where
    # the boundary is held to the tree so the free text is not read as an
    # oversight.
    measurement_key = models.CharField(max_length=100)
    pricing_model = models.CharField(max_length=20, choices=PRICING_MODEL_CHOICES, default="per_unit")
    rate_per_unit_micros = models.BigIntegerField(default=0)
    unit_quantity = models.BigIntegerField(default=1_000_000)
    fixed_micros = models.BigIntegerField(default=0)
    currency = models.CharField(max_length=3, default="usd")
    rate_card = models.ForeignKey("pricing.RateCard", on_delete=models.PROTECT,
                                  related_name="rates", null=True, blank=True)
    book_version_from = models.PositiveIntegerField(default=1)
    book_version_to = models.PositiveIntegerField(null=True, blank=True)
    lineage_id = models.UUIDField(default=uuid.uuid4, editable=False, db_index=True)
    # WHEN THIS RULE TAKES EFFECT, CHOSEN BY THE CALLER — past, future or
    # omitted (#325). It was `auto_now_add=True`, which does not default: it
    # OVERWRITES whatever was supplied, on every insert. A tenant could
    # therefore only ever say "effective from the instant I clicked save",
    # which made the remediation loop this slice exists to close unclosable —
    # an event replayed from January resolves against the rules effective in
    # January, there were none, and the correction came back a plausible
    # number that was not the answer.
    #
    # `default=timezone.now` is the same behaviour for every caller that
    # supplies nothing, said as a default rather than as an override, which is
    # the whole difference: a default is a value a caller may replace.
    valid_from = models.DateTimeField(default=timezone.now, db_index=True)
    valid_to = models.DateTimeField(null=True, blank=True)

    #: WHAT MAY HAPPEN TO THE TWO COLUMNS RESOLUTION READS (ADR-0007 §2).
    #:
    #: Removing the flag above and stopping there would have left the column
    #: UNCONSTRAINED, which is a different defect and one the same rule
    #: refuses in the same breath: mutability is declared per field **and**
    #: enforced by the database.
    #:
    #: `valid_from` is FROZEN — none after insert. When a rule took effect is
    #: a fact *about* the rule, and moving it retroactively re-costs work that
    #: has already reported. Nothing in the system would disagree with itself
    #: afterwards; the totals would simply become different totals from the
    #: ones the tenant was shown, with no record that they moved.
    #:
    #: `valid_to` is SET_ONCE — null to a value, once. It is not FROZEN
    #: because closing a rule is a legitimate late arrival: a rate is written
    #: open-ended and stays that way until it is retired or repriced, which is
    #: how both live writers use it. What is refused is the SECOND write —
    #: moving the close, or taking it back. Reopening a rule over a period
    #: that has already reported is a rewrite of history rather than an edit.
    #:
    #: ⚠ That last sentence is the USUAL case and not the whole rule, and the
    #: difference has an owner. A trigger cannot ask whether anyone has read a
    #: row, so `SET_ONCE` refuses a reopen even where nothing has reported yet
    #: — which forecloses the cancellation mechanism the pricing-versions
    #: decision §6.5 describes. Named, with the choice it leaves open, in
    #: `test_a_rate_is_effective_from_a_chosen_moment.py`'s slice-4 class.
    #:
    #: **The enforcement is the trigger installed by `migrations/0018`, not
    #: anything here.** ADR-0007 §2 is explicit that a model-level guard is
    #: not enforcement. Both declarations are held across `save()`,
    #: `QuerySet.update()` and raw SQL alike, on BOTH halves of this table —
    #: one model carries the cost and the price side and the rule does not get
    #: to know which. `apps/platform/tests/test_transition_class_declarations.py`
    #: is what says no column may be declared here without that being true of
    #: it, and it covers these two without naming either.
    transition_classes = {
        "valid_from": FROZEN,
        "valid_to": SET_ONCE,
    }

    class Meta:
        db_table = "ubb_rate_card"
        indexes = [
            models.Index(fields=["tenant", "card_type", "provider", "event_type", "measurement_key"],
                         name="idx_ratecard_lookup"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["rate_card", "measurement_key", "currency", "provider",
                        "event_type", "task_type", "subtask_type",
                        "grouping_field_1", "grouping_field_2", "grouping_field_3",
                        "grouping_field_4", "grouping_field_5", "grouping_field_6",
                        "grouping_field_7", "grouping_field_8", "grouping_field_9",
                        "grouping_field_10"],
                condition=models.Q(valid_to__isnull=True),
                name="uq_rate_active_in_book"),
        ]

    #: The slot half is read off the registry rather than restated, so a rate
    #: cannot end up selecting on a different set of slots from the one a tenant
    #: can declare. The four reserved axes are spelled out because they are not
    #: in that vocabulary — they are always present and never declared.
    SELECTORS = ("provider", "event_type", "task_type", "subtask_type",
                 *(slot for slot, _ in SLOT_CHOICES))

    @property
    def selector_tuple(self):
        return tuple(getattr(self, s) for s in self.SELECTORS)

    @property
    def specificity(self):
        """How many selectors this rate pins. The resolution tie-breaker (D3):
        a rate pinning provider+event_type+one slot beats one pinning provider
        alone, so a tenant writes a broad default plus narrow overrides."""
        return sum(1 for v in self.selector_tuple if v)

    def compute(self, units):
        if self.pricing_model == "flat":
            return self.fixed_micros
        units = units or 0
        return (units * self.rate_per_unit_micros + self.unit_quantity // 2) // self.unit_quantity + self.fixed_micros


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
