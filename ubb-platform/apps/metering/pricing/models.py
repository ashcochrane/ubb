import uuid

from django.db import models
from django.utils import timezone

from apps.platform.grouping_fields.models import SLOT_CHOICES
from core.models import BaseModel
from core.transitions import FROZEN, RECORD_RULE, RESOLVE_ONCE, SET_ONCE
from core.vocabulary import (
    DECLARATION_STATUS_DRAFT,
    DECLARATION_STATUS_PUBLISHED,
    DECLARATION_STATUS_VALUES,
    PRICING_METHOD_MARGIN_OVER_COST,
    PRICING_METHOD_VALUES,
)


class TenantDefaultMarkup(BaseModel):
    """THE RUNG THAT PRICES WHAT NO RULE MATCHED, DECLARED BY THE TENANT (#357).

    The last rung of the price ladder, and the one that produces most prices:
    where the books in play hold no rule for a quantity, the customer's price is
    a percentage over what the call cost. A tenant declares it here, once, and
    withdraws it by deleting the row.

    **⚠ UBB SHIPS NO CATALOGUE, AND THIS IS THE MODEL THAT SAYS SO.** There is
    no default value on the column, no starter row and no seed anywhere: a
    tenant that has declared nothing has NO markup rung, and resolution answers
    `unknown` rather than zero (`pricing_service._priced_by_markup`). A default
    of `0` would make "nobody has said what to charge" and "charge exactly what
    the call cost" one answer, which is the silently wrong price #356 deleted
    from the resolver — putting it back on the column would be the same defect
    one layer down.

    **IT REPLACES THE TENANT-DEFAULT ROW OF `TenantMarkup`, HERE AND NOT
    LATER.** That record's `customer IS NULL` row was the tenant default by
    being the one with no customer on it, which is a rung read out of an
    absence; this is the rung declared. Its own routes go with it (#369
    deletes the record, its remaining customer-override rows and the routes
    that write them); until then `PUT /pricing/markup` still writes that row
    and that row no longer prices anything, which is stated on the route.

    **NO UPLIFT COLUMN, AND THAT IS THE NON-COMPOSITION RULE (#147 §2).** A
    rule that takes a margin over cost does not also carry a flat addend, a
    floor or a cap — that is what makes a resolved price explicable by naming
    one thing. The per-event fixed uplift the records this replaces carry is
    deleted rather than folded in, so the replacement is not built with one.

    **THE PERCENTAGE IS NOT FROZEN AND IS IN NO TRANSITION CLASS.** A tenant
    re-declaring its default markup is an ordinary correction to configuration,
    not a rewrite of history: every event already priced holds its percentage
    BY VALUE on its own receipt, so an edit here cannot change what any past
    event was charged. That is the whole reason the receipt records values and
    keeps pointers in `provenance`.

    **AND THE DATABASE DOES NOT DEFEND THE SIGN.** A percentage below zero is a
    price under cost, which is an ordinary commercial decision (a loss leader)
    rather than an invariant no business situation can make false — so it is
    not the ADR-0002 shape that belongs in a `CHECK`. The declaring route
    refuses one, as the route it replaces did.
    """

    tenant = models.OneToOneField(
        "tenants.Tenant", on_delete=models.CASCADE,
        related_name="default_markup",
    )
    #: Millionths of a percent: 1_000_000 is 1%. Named for what it holds rather
    #: than under the money suffix — `_micros` means millionths of a CURRENCY
    #: unit on seventy-odd columns in this tree, and the two records this one
    #: replaces are both ledgered against G11 for hiding a percentage under it.
    #: This is that entry's own `expected` spelling, taken on a new column where
    #: it costs nothing.
    markup_micro_percent = models.BigIntegerField()

    class Meta:
        db_table = "ubb_tenant_default_markup"

    def __str__(self):
        return f"TenantDefaultMarkup({self.tenant_id})"

    # THE CACHE IS INVALIDATED AT THE MODEL LAYER, WHICH IS WHERE THE
    # CONVENTION PUTS IT (`docs/conventions/django-patterns.md`, Caching): no
    # write path can bypass a hook here, and the record this rung replaces has
    # always carried the same pair. A rung declared or withdrawn through a
    # route and a rung written from a shell both reach the same bump.
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


class TenantMarkup(BaseModel):
    """The markup record slice 4 replaces — customer overrides, and a stranded
    tenant-default row (#357, deleted by #369).

    Its `customer IS NULL` row was the tenant-default rung until
    :class:`TenantDefaultMarkup` took that job, and it prices nothing now. Its
    per-customer rows are still a rung of the ladder and still resolve, until
    the customer override becomes a rule in the customer's own Pricing Book.
    """

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


#: The check that makes a rate say which quantity it prices, exactly once
#: (#326). Named here rather than spelled at each site because every test of it
#: asserts the MESSAGE: MANY mechanisms on this table answer `IntegrityError`,
#: and "the write was rejected" stopped being evidence the moment there was
#: more than one.
#:
#: ⚠ **NOT A CLOSED LIST, DELIBERATELY, AND IT USED TO READ LIKE ONE.** This
#: comment named five — the partial unique index, this check, the reference's
#: own foreign key and the two triggers `0018` and `0020` install — and #355
#: added two more checks below without that enumeration being wrong so much as
#: OUT OF DATE, which is the failure mode of writing a count in prose at all.
#: Every foreign key and every `NOT NULL` on this table answers the same
#: exception too. What a test needs is not the tally but the habit: name the
#: mechanism you mean.
NAMES_ONE_QUANTITY_CHECK = "ck_rate_names_one_quantity"

#: The check that keeps the method's value set closed at the table (#355).
#:
#: `choices=` reaches forms, the admin and `full_clean`, and it is worth having
#: — but it is not a constraint: `QuerySet.update()` and raw SQL write straight
#: past all three, which the tests of this constant demonstrate rather than
#: assert. A closed value set is an invariant no business situation can make
#: false, which is exactly what ADR-0002 puts in the database.
#:
#: Named for the reason the check above it gives.
DECLARES_A_RATIFIED_METHOD_CHECK = "ck_rate_pricing_method"

#: The check that makes non-composition a property of a ROW rather than a
#: sentence in a comment (#355, #147 §2).
#:
#: A rule declaring that its price is a margin over what the call cost may not
#: also carry a second component that would be added to, floored under or capped
#: over that margin. The two components this table can express are the per-unit
#: rate and the flat addend beside it, and a margin rule carries neither.
#:
#: **WHY A `CHECK` IS THE RIGHT MECHANISM HERE AND WAS NOT FOR #326's RULE.**
#: This is a statement about the SHAPE OF A ROW, true at every instant, which is
#: exactly what a check evaluates. #326 needed a trigger because its rule was
#: about which rows may be BORN — a distinction a check cannot draw, since it
#: cannot tell an `INSERT` from the conversion's `UPDATE`. Nothing here depends
#: on how a row arrived.
#:
#: ⚠ **IT IS NOT THE WHOLE OF "RULES NEVER COMPOSE", AND THE REST IS NOT THIS
#: TICKET'S.** A SECOND composition is expressible on this table and is left
#: legal here: `compute` adds the flat term to the per-unit term, so one rule
#: can carry both. That is a statement about the rule's ARITHMETIC SHAPE, whose
#: two alternatives are `per_unit` and a fixed component and whose exclusivity
#: is decided with the shape's own rename — not about which METHOD derived the
#: price, which is what this check holds. Refusing it here would change what an
#: existing rate may be, in a ticket that renames nothing.
NEVER_COMPOSES_CHECK = "ck_rate_never_composes"

#: HOW A PRICING RULE DERIVES A CUSTOMER PRICE, DERIVED FROM THE REGISTRY rather
#: than restated beside it — the construction the posting's four closed sets
#: already use, and for the same reason: a hand-typed list is correct on the day
#: it is written and silently wrong the day `domain-vocabulary/` moves.
#:
#: The label is the token. Django's second element is not a translation hook
#: (ADR-0008 §4 puts every human-facing word in the console's locale catalogue,
#: keyed off the concept's `label_key_prefix`), so English authored here would be
#: a wording nobody can reach and one more copy to keep in step.
PRICING_METHOD_CHOICES = [(value, value) for value in sorted(PRICING_METHOD_VALUES)]

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
    # close. Only six of these reach the published contract UNDER THEIR OWN
    # SPELLING, and no slice-2 ticket widens that;
    # `api/v1/schemas.py:SLOT_PROPERTY_COLUMNS` holds the join and what is left
    # of the gap. All ten are addressable since #358, by the tenant's declared
    # KEY rather than by the slot, on the act that replaces the three immediate
    # mutation routes — which is what "this entity's published surface is
    # rebuilt in slice 4" meant.
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
    # WHICH DECLARED QUANTITY THIS RATE PRICES — the record itself since #326,
    # where it was the record's NAME as free text. Slice 2 paid the word and
    # said in three places that slice 3 would pay the referential integrity;
    # this is that payment. A typo can no longer sit here costing nothing and
    # looking configured, because there is nothing for it to point at.
    #
    # NULLABLE FOR ONE POPULATION AND NO LIVE WRITER MAY PRODUCE IT: the rows
    # the conversion found naming a quantity no declaration matched. They keep
    # their row and their name (below) and stop resolving, because deleting them
    # would destroy the evidence a tenant needs to fix them and repointing them
    # would invent a declaration the tenant never made. `ck_rate_names_one_
    # quantity` is what stops that null being a door anything else can walk
    # through.
    #
    # PROTECT, for the reason `Measurement.concept` gives for its own: a record
    # deleted out from under the thing that points at it silently changes what
    # historical numbers mean. Here it would stop a rule pricing work that is
    # still being metered. Withdrawing a declaration a rate names is refused,
    # and the route renders that refusal rather than a 500
    # (`api/v1/event_type_endpoints.py`).
    measurement = models.ForeignKey(
        "event_types.Measurement", on_delete=models.PROTECT,
        null=True, blank=True, related_name="rates")
    # THE NAME A CONVERSION COULD NOT PLACE, AND NOTHING ELSE. It is not a
    # second spelling of the reference above — the check below makes the two
    # mutually exclusive, so exactly one of them says which quantity a rate
    # names and no row has both.
    #
    # ITS ONLY WRITER IS MIGRATION `0019`, AND THAT IS ENFORCED RATHER THAN
    # ASSERTED. The check cannot do it: it is evaluated against one row and
    # cannot tell the conversion's UPDATE from a fresh INSERT carrying a loose
    # name, which is the same defect wearing the new column. `0020` installs a
    # `BEFORE INSERT` trigger refusing any rate that references no declaration,
    # and that is what makes a rate naming an undeclared quantity unwritable at
    # every door rather than only at the route.
    undeclared_measurement_key = models.CharField(max_length=100, blank=True,
                                                  default="")
    # HOW THIS RULE DERIVES A CUSTOMER PRICE — one of exactly two, or nothing
    # (#355, #147 §2). A margin applied over what UBB knows the call cost, or an
    # amount attached directly to the event regardless of cost.
    #
    # ONE METHOD PER RULE, AND THE COLUMN IS WHAT MAKES THAT TRUE rather than a
    # convention. A rule that wanted both would be two rules; a rule that wanted
    # one method plus a floor, a cap or a second additive component would make
    # the explanation of a resolved price a chain whose middle terms nobody
    # stored, which is the failure the receipt exists to remove.
    # `NEVER_COMPOSES_CHECK` above is where that stops being a sentence.
    #
    # NULLABLE, AND NULL IS NOT A THIRD METHOD. It means the price was not
    # DERIVED — because it was agreed, or because there is none — and which of
    # those is read off the price STATUS beside the amount on the posting
    # (`usage/models.py`), which already carries `waived`, `unknown` and
    # `not_applicable`. THIS IS THE ONE PLACE THAT ARGUMENT IS MADE IN FULL; the
    # migration, the published schema and the receipt module state the rule and
    # point here, because seven copies of a paragraph are seven things that can
    # go false separately. It is the shape the cost side already ships: the
    # derivation lives on the declaration and the receipt snapshots it.
    #
    # ⚠ EVERY ROW IN THE TREE IS NULL TODAY AND THAT IS THE HONEST READING, not
    # a backfill left undone. The engine that writes a method into a receipt
    # decides it from the rung that supplied the price rather than from a column
    # (`services/pricing_service.py`), and the rule that carries its own method
    # is what the resolver of the next ticket resolves against. Nothing is lost
    # meanwhile: a receipt written today already records which method produced
    # its amount.
    #
    # ⚠ NOT DECLARED INTO A TRANSITION CLASS, AND THAT IS AN ANSWER RATHER THAN
    # A SILENCE. Every term on this table is undeclared — the two effective
    # instants below are the only declared columns, and they are declared
    # because WHEN a rule applied is a fact about history rather than a setting.
    # Whether a rule's terms may be edited in place at all is the publishing
    # model's question, and declaring this column FROZEN now would answer it
    # early and in the wrong ticket. What protects history meanwhile is not this
    # column's mutability but the receipt, which holds VALUES: editing a rule
    # cannot move a number a tenant was already shown.
    #
    # ⚠ AND IT SITS ONE WORD FROM `pricing_model` BELOW, WHICH HOLDS THE RULE'S
    # ARITHMETIC SHAPE AND HAS NOTHING TO DO WITH THIS. Two adjacent character
    # fields, near-identical names, unrelated value sets: HOW A PRICE IS DERIVED
    # (a margin, or a price of its own) versus HOW THE ARITHMETIC RUNS (per unit
    # of quantity, or once). Reach the second through `STRUCTURE_COLUMN` rather
    # than by name, and read the two comments together before touching either.
    pricing_method = models.CharField(
        max_length=32, choices=PRICING_METHOD_CHOICES, null=True, blank=True)
    #: WHICH COLUMN HOLDS THE RATE'S ARITHMETIC SHAPE, NAMED ONCE (#350).
    #:
    #: The shape decides which arithmetic produced an amount — so much per unit
    #: of quantity, or a component that applies once regardless — and a reader
    #: rebuilding an amount out of a Pricing Receipt has to know which.
    #:
    #: The column below still carries the retired spelling of the concept
    #: (`rate_structure`), and re-spelling it is a later ticket's, with the rest
    #: of the retired vocabulary. Until then this constant is how a module that
    #: may not spell the word addresses the column — the same reason
    #: `Posting.RECEIPT_COLUMN` exists, and the same payoff: a reader that goes
    #: through it follows the rename instead of going quietly vacuous on the day
    #: it lands. The two live spellings here are deliberately NOT routed through
    #: it, because this file's own occurrences are what keep it inside the
    #: ledger's counted set for that word.
    STRUCTURE_COLUMN = "pricing_model"
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
            models.Index(fields=["tenant", "card_type", "provider", "event_type", "measurement"],
                         name="idx_ratecard_lookup"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["rate_card", "measurement", "currency", "provider",
                        "event_type", "task_type", "subtask_type",
                        "grouping_field_1", "grouping_field_2", "grouping_field_3",
                        "grouping_field_4", "grouping_field_5", "grouping_field_6",
                        "grouping_field_7", "grouping_field_8", "grouping_field_9",
                        "grouping_field_10"],
                condition=models.Q(valid_to__isnull=True),
                name="uq_rate_active_in_book"),
            # EXACTLY ONE OF THE TWO SAYS WHICH QUANTITY (#326). A live rate
            # references a declaration and carries no loose name; a rate the
            # conversion could not place carries its name and references
            # nothing. Neither both nor neither.
            #
            # This holds the SHAPE of a row, at all times, including across an
            # update that would blank a placeless rate's name and leave it
            # pricing nothing and saying nothing. WHO MAY BE BORN is a
            # different question and a check cannot answer it — see `0020`.
            models.CheckConstraint(
                condition=(
                    models.Q(measurement__isnull=False,
                             undeclared_measurement_key="")
                    | (models.Q(measurement__isnull=True)
                       & ~models.Q(undeclared_measurement_key=""))),
                name=NAMES_ONE_QUANTITY_CHECK),
            # THE METHOD'S VALUE SET, CLOSED AT THE TABLE (#355) — see
            # `DECLARES_A_RATIFIED_METHOD_CHECK` for why the column's `choices=`
            # is not this. The members come from the registry frozenset, so this
            # constraint cannot hold a set the agreed model disagrees with.
            #
            # NULL IS ADMITTED HERE BECAUSE NULL IS NOT A VALUE, and the
            # membership test would answer NULL for it — which a check reads as
            # satisfied. Saying so positively is what stops a reader taking the
            # admission for an oversight.
            models.CheckConstraint(
                condition=(models.Q(pricing_method__isnull=True)
                           | models.Q(pricing_method__in=sorted(
                               PRICING_METHOD_VALUES))),
                name=DECLARES_A_RATIFIED_METHOD_CHECK),
            # RULES NEVER COMPOSE (#355, #147 §2). A margin rule's price is a
            # percentage of what the call cost; a second component added to it
            # would make the resolved price impossible to explain by naming one
            # rule, because the middle term is nowhere on the record.
            #
            # ⚠ THIS ENFORCES ONE DIRECTION OF THE PROPERTY AND ONLY ONE, and
            # saying which is the difference between a rule and a claim. The two
            # components this table can express — the per-unit rate and the flat
            # addend — are `direct_event_price`'s own terms, so the refusal is
            # over a margin rule carrying them. The mirrored refusal (a direct
            # rule carrying a margin term) is not expressible here: no percentage
            # column exists on this table, because markup is still a separate
            # record. The ticket that moves it is the ticket that adds the other
            # half.
            models.CheckConstraint(
                condition=(
                    ~models.Q(pricing_method=PRICING_METHOD_MARGIN_OVER_COST)
                    | models.Q(rate_per_unit_micros=0, fixed_micros=0)),
                name=NEVER_COMPOSES_CHECK),
        ]

    @property
    def measurement_key(self):
        """The name of the quantity this rate prices.

        DERIVED, NEVER STORED (#326), which is the whole of what the conversion
        bought: the name is the declaration's, so a rate cannot hold a spelling
        the catalogue does not. It is still what the wire carries — `RateIn`,
        `RateChangeIn` and `RateOut` all publish this key and none of them
        moved — and still what the pricing receipt and the audit record write,
        so the published surface of this entity is unchanged by the move
        underneath it.

        A deactivated rate answers with the name it was written with, off the
        column that preserved it. That is the point of preserving it: a rate
        that answered `""` would be a rate a tenant cannot recognise, cannot
        fix, and would reasonably delete.
        """
        if self.measurement_id is None:
            return self.undeclared_measurement_key
        return self.measurement.code

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
        """How many selectors this rate pins (design D3), and only that.

        ⚠ **IT DOES NOT DECIDE WHICH RULE ANSWERS, AND IT USED TO SAY IT DID
        (#356).** Resolution ranks on how specifically a rule names the event
        AND on where the rule came from, and a count of pinned selectors is one
        of those two ingredients — so a rule about how they combine, stated
        here, is stated somewhere it cannot be true or false. The composite is
        `ladder_rank` in `services/pricing_service.py`, with the argument for
        the order it puts them in; this is the number it reads.
        """
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


#: THE THREE THINGS A TENANT CAN DO TO A BOOK, AND THERE IS NO FOURTH (#358).
#:
#: Adding a rule, repricing one and retiring one — the three surfaces a book
#: used to have, arriving here as three kinds of one act. A change body names
#: one of these and the service refuses anything else.
#:
#: **Held as a plain tuple rather than as a declared concept, deliberately.**
#: These are not a value set the vocabulary registry owns: they name the shape
#: of one request body on one route, they are never stored on a column a reader
#: interprets, and they never cross the wire in a response. ADR-0006 governs the
#: NAMES the domain publishes; a request enumerating its own three verbs is the
#: same undeclared set `card_type` and the arithmetic shape are refused against
#: at their own routes today, and giving it a concept would advertise a set that
#: has no meaning outside this one body.
CHANGE_ADD = "add"
CHANGE_REPRICE = "reprice"
CHANGE_RETIRE = "retire"
CHANGE_KINDS = (CHANGE_ADD, CHANGE_REPRICE, CHANGE_RETIRE)


class PricingBookPublish(BaseModel):
    """EVERY CHANGE TO A PRICING BOOK IS A PUBLISH, AND A DRAFT IS NOT ONE.

    Adding a rule, repricing one and retiring one used to be three unrelated
    mutation surfaces, each writing immediately, each recorded under its own
    name, and none of them able to say *what the book will look like afterwards*
    before it happened. They are one act now, recorded once, with a diff a
    tenant reads before committing to it — which is also what gives the console
    one thing to show (*"your book changes on 1 August; here is the diff"*)
    instead of three.

    **THE TWO STATES ARE THE ONES THE REGISTRY ALREADY CLOSED.** `draft` and
    `published`, imported from `core.vocabulary` rather than spelled here, so
    the record follows the declared vocabulary instead of restating it. The
    concept is `declaration_status` and the name was settled against
    `publication_status` at the site where that was rejected: a field one word
    away from a model named for a publish record is ADR-0006 §3's named defect
    shape, and "declaration" is already this slice's own noun.

    * **A draft holds the intended changes and writes no rule.** It is freely
      editable and freely discardable, and discarding it reopens nothing
      **because it closed nothing**.
    * **Publishing is the act that writes rows.** It closes each superseded rule
      and opens its replacement, and that is the only statement that changes
      what a customer is charged.

    **ONE CLOCK CLOSES THE BOUNDARY AND OPENS IT.** The outgoing rule's
    effective-to and the incoming rule's effective-from are the same value —
    `effective_at`, this record's own — which with a half-open range is exactly
    no gap and exactly no overlap. `BookService.publish_declared` is where that
    single value is used twice; `NoInstantFallsBetweenTwoVersionsTest` and this
    record's own boundary test are what hold it.

    **THE RECORD IS IMMUTABLE ONCE PUBLISHED**, which is the whole-record rule
    `transition_classes` declares below and a trigger keeps. A price in force at
    any past moment is traceable to a decision somebody made, and a record that
    could be edited afterwards would make that traceability a claim rather than
    a fact.

    ⚠ **THE ACTOR AND THE INSTANT ARE THE PUBLISHER'S, AND A DRAFT CARRIES
    NEITHER.** *Whose decision put this price in force* is the question
    traceability asks, and it has an answer only once a publish has happened.
    Who declared the draft, and who discarded one, are the audit ledger's —
    `pricing_book_publish.declared` and `.discarded` carry their own actor
    snapshots, taken the same way. Stamping a declaring actor here as well
    would be a second copy of a fact the ledger already holds, on the record
    whose columns must all mean one thing.

    The three actor columns are `AuditRecord`'s own shape (ADR-004 §4): an
    immutable snapshot taken at the moment of the act, so a later rename or
    deletion of the principal never rewrites what this record says.

    ⚠ **THE RULE VERSIONS IT CREATED AND CLOSED ARE HELD HERE, NOT AS COLUMNS ON
    THE RULE.** Two reasons, and the second is the load-bearing one. A publish
    is an act and these are the act's outputs, so they belong to its record in
    the way an audit entry's metadata belongs to the entry. And nothing can
    disagree with them: a rule row is created by exactly one statement, and
    `Rate.valid_to` is declared `SET_ONCE` and held by a trigger, so a rule can
    be closed at most once and two publishes cannot both claim to have closed
    it. A pair of nullable columns on the rule would carry the same fact with a
    second writer and no such guarantee.
    """

    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE,
                               related_name="pricing_book_publishes")
    #: The book this changes. `CASCADE` rather than `PROTECT` on purpose: a
    #: publish record explains a book, so it has no meaning once the book is
    #: gone, and a `PROTECT` here would make deleting a book fail on the records
    #: describing it — including under the sandbox reset, where a refusal from a
    #: record nobody asked about is how a tenant wipe stops half way.
    book = models.ForeignKey("pricing.RateCard", on_delete=models.CASCADE,
                             related_name="publishes")
    declaration_status = models.CharField(
        max_length=32, default=DECLARATION_STATUS_DRAFT, db_index=True)
    #: WHEN THE CHANGE TAKES EFFECT — the one value both boundaries are written
    #: from. Chosen by the caller, and defaulted by the route rather than here,
    #: because a declaration with no stated moment means "now" at the moment it
    #: is *declared*, not at the moment the row happens to be constructed.
    effective_at = models.DateTimeField(db_index=True)
    #: THE INTENDED CHANGES, held by value. Each is a mapping naming one of
    #: `CHANGE_KINDS`, the quantity it prices and the selectors that identify
    #: the rule, plus the terms for a kind that writes any. A draft is exactly
    #: this list and nothing else, which is what "a draft writes no rule" means.
    changes = models.JSONField(default=list)
    published_at = models.DateTimeField(null=True, blank=True)
    actor_kind = models.CharField(max_length=32, blank=True, default="")
    actor_id = models.CharField(max_length=255, blank=True, default="")
    actor_display = models.CharField(max_length=255, blank=True, default="")
    #: The rule versions this publish opened and closed, by id. Empty on a
    #: draft, because a draft opened and closed none.
    opened_rule_ids = models.JSONField(default=list)
    closed_rule_ids = models.JSONField(default=list)

    #: WHAT MAY HAPPEN TO THIS RECORD (ADR-0007 §2).
    #:
    #: One column takes a defended class and the rest declare the record's own
    #: rule, which is `PostingMeasurement`'s shape for the same reason: the
    #: question ADR-0007 §2 asks is *what is allowed to happen to this?*, and
    #: for thirteen of these fourteen columns the honest answer is "nothing this
    #: column decides — read the record's rule", stated rather than left absent.
    #:
    #: `declaration_status` is `RESOLVE_ONCE` and it is the real thing rather
    #: than a convenience: `draft` is the unresolved state, `published` is the
    #: one terminal value, and the move happens once. Publishing twice is not a
    #: correction, and returning a published record to draft is a book whose
    #: prices moved with nothing recording that they did.
    #:
    #: **The record's rule, which the trigger holds and this sentence states
    #: once:** while the record is a draft, any column may change — that is what
    #: makes a draft freely editable — and once it is published, none may, ever.
    #: `RECORD_RULE` sits outside `DATABASE_DEFENDED`, so the declaration walk
    #: judges `declaration_status` alone and the behavioural trio in
    #: `pricing/tests/test_every_change_to_a_book_is_a_publish.py` is what
    #: proves the rest, through all three doors.
    #:
    #: ⚠ **DELETE IS NOT IN THE RULE, AND THAT IS DELIBERATE.** Discarding a
    #: draft is a `DELETE`, and refusing one against a *published* record would
    #: read as the natural other half — but a `BEFORE DELETE` trigger cannot
    #: tell a discard from a cascade (#354), and a tenant wipe deletes every row
    #: this table holds. The route is what refuses to discard a published
    #: record, and it can, because it knows which act it is performing.
    transition_classes = {
        "id": RECORD_RULE,
        "created_at": RECORD_RULE,
        "updated_at": RECORD_RULE,
        "tenant": RECORD_RULE,
        "book": RECORD_RULE,
        "declaration_status": RESOLVE_ONCE,
        "effective_at": RECORD_RULE,
        "changes": RECORD_RULE,
        "published_at": RECORD_RULE,
        "actor_kind": RECORD_RULE,
        "actor_id": RECORD_RULE,
        "actor_display": RECORD_RULE,
        "opened_rule_ids": RECORD_RULE,
        "closed_rule_ids": RECORD_RULE,
    }

    class Meta:
        db_table = "ubb_pricing_book_publish"
        indexes = [
            models.Index(fields=["book", "declaration_status"],
                         name="idx_book_publish_pending"),
        ]
        constraints = [
            # The closed set at the database, which is where a value set
            # belongs (ADR-0002: an invariant no business situation can make
            # false). `choices=` is a form-layer courtesy and a `clean()` is a
            # door; neither is reached by a data migration or a shell.
            models.CheckConstraint(
                condition=models.Q(
                    declaration_status__in=sorted(DECLARATION_STATUS_VALUES)),
                name="ck_book_publish_declaration_status"),
        ]

    def __str__(self):
        return f"PricingBookPublish({self.declaration_status} @ {self.effective_at})"

    @property
    def is_published(self):
        return self.declaration_status == DECLARATION_STATUS_PUBLISHED
