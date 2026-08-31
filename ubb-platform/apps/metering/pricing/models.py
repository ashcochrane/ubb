import uuid

from django.db import models
from django.utils import timezone

from apps.platform.grouping_fields.models import SLOT_CHOICES
# THE ALTITUDE VOCABULARY, BY REFERENCE FROM THE MODEL THAT OWNS THE
# DECLARATION (#415). A work-level price line names the same two altitudes a
# `TaskType` does and must never hold a second copy of that wording — the
# import is the `SLOT_CHOICES` line above doing the same job for the same
# reason, and ADR-001 permits a product reading the kernel.
from apps.platform.work.models import TASK_TYPE_KIND_CHOICES
from core.models import BaseModel
from core.transitions import FROZEN, RECORD_RULE, RESOLVE_ONCE, SET_ONCE
from core.vocabulary import (
    DECLARATION_STATUS_DRAFT,
    DECLARATION_STATUS_PUBLISHED,
    DECLARATION_STATUS_VALUES,
    PRICING_METHOD_MARGIN_OVER_COST,
    PRICING_METHOD_VALUES,
    RATE_STRUCTURE_FIXED_COMPONENT,
    RATE_STRUCTURE_PER_UNIT,
    RATE_STRUCTURE_VALUES,
    TASK_TYPE_KIND_TASK,
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

    **IT REPLACED THE TENANT-DEFAULT ROW OF A RECORD THAT NO LONGER EXISTS.**
    That record's tenant-default row was the tenant default by being the one
    with no customer on it, which is a rung read out of an absence; this is the
    rung declared. #357 built this one and #369 deleted the record, its
    per-customer rows and the five routes that read and wrote them, so this is
    now the only rung the ladder has: a customer's own price is a rule in their
    own Pricing Book (#361), and a plan's is a rule in the book the plan names
    (#362). Neither is a percentage on a configuration row any more.

    **NO UPLIFT COLUMN, AND THAT IS THE NON-COMPOSITION RULE (#147 §2).** A
    rule that takes a margin over cost does not also carry a fixed addend, a
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
    #: unit on seventy-odd columns in this tree, and the two columns this one
    #: replaces were both ledgered against G11 for hiding a percentage under
    #: it. This is that entry's own `expected` spelling, taken on a new column
    #: where it cost nothing; both entries were paid by deleting their columns
    #: in #369 rather than by renaming them, and G11 now owes nothing.
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
#: rate and the fixed addend beside it, and a margin rule carries neither.
#:
#: **WHY A `CHECK` IS THE RIGHT MECHANISM HERE AND WAS NOT FOR #326's RULE.**
#: This is a statement about the SHAPE OF A ROW, true at every instant, which is
#: exactly what a check evaluates. #326 needed a trigger because its rule was
#: about which rows may be BORN — a distinction a check cannot draw, since it
#: cannot tell an `INSERT` from the conversion's `UPDATE`. Nothing here depends
#: on how a row arrived.
#:
#: ⚠ **IT IS NOT THE WHOLE OF "RULES NEVER COMPOSE", AND THE SECOND HALF IS
#: DECIDED RATHER THAN PENDING (#366).** A SECOND composition is expressible on
#: this table: `compute` adds `fixed_micros` to the per-unit term, so a
#: `per_unit` rule can carry both. #355 left that to "the shape's own rename",
#: and the rename has now happened — so here is the answer rather than another
#: hand-forward. **It stays legal, and the rename is not what decides it.**
#: Renaming a discriminator says nothing about which rows may exist: the
#: question is whether a row may hold both TERMS, which is a `CHECK` over
#: `rate_per_unit_micros` and `fixed_micros` and would change what an existing
#: rate may be. `compute` is what gives the shape its meaning, and it reads
#: `rate_structure` as WHICH ARITHMETIC RUNS — the per-unit formula, or the
#: fixed component alone — not as a promise that the other term is zero. A
#: tenant charging so much per unit plus a joining fee has configured one rule
#: that a reader can still explain by naming it, which is the property #147 §2
#: asks for. Refusing it needs a ticket with a conversion for the rows that
#: already do it; nothing in slice 4 assigns one.
#:
#: ⚠ The MIRRORED direction is a different fact and stays inexpressible: a
#: `fixed_component` rule's `rate_per_unit_micros` is not added to anything,
#: because `compute` returns before reaching it. That is a property of the
#: method rather than of a constraint, which is why the branch has a test
#: naming the discriminator beside the amount.
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

#: The check that makes a cost book DECLARE the currency its supplier bills in
#: (#368). Named here for the reason the checks above are: this table answers
#: `IntegrityError` from a uniqueness key as well, so every test of this rule
#: asserts the MESSAGE and "the write was rejected" is not evidence on its own.
NAMES_ITS_CURRENCY_CHECK = "ck_cost_book_names_its_currency"

#: The check that stops one rule sitting in a book of costs AND a book of
#: prices at once (#368).
#:
#: ⚠ **AT MOST ONE, NOT EXACTLY ONE, AND THE DIFFERENCE IS NOT A COMPROMISE.**
#: A rule with no book at all has been writable since before the container
#: existed — the column has always been nullable and callers across this
#: tree still rely on it — so refusing one would be a second, unrelated
#: change
#: riding on this commit, with its own conversion. What the split makes
#: impossible is the shape the discriminator used to admit: one rule reachable
#: from both halves, which is the conflation the whole slice exists to end.
SITS_IN_AT_MOST_ONE_BOOK_CHECK = "ck_rate_sits_in_at_most_one_book"

#: The same rule for the record that CHANGES a book (#368): a publish names a
#: book of prices or a book of costs, never both. A draft naming both would be
#: a change whose diff belongs to two catalogues.
PUBLISH_CHANGES_AT_MOST_ONE_BOOK_CHECK = "ck_book_publish_at_most_one_book"

#: THE ARITHMETIC SHAPE OF A RATE, DERIVED FROM THE REGISTRY rather than
#: restated beside it — the construction `PRICING_METHOD_CHOICES` above uses,
#: and the posting's four closed sets before it, for the same reason: a
#: hand-typed list is correct on the day it is written and silently wrong the
#: day `domain-vocabulary/` moves.
#:
#: TWO VALUES AND NOT FOUR, WHICH IS ADR-0003 RATHER THAN THIS FILE. The tiered
#: shapes were deleted end to end rather than gated, so every arrival-time
#: estimate equals the settled price by construction. That is a statement about
#: which values the registry declares, and it is made there.
#:
#: The label is the token, for the reason `PRICING_METHOD_CHOICES` gives:
#: Django's second element is not a translation hook, and English authored here
#: would be a wording nobody can reach.
RATE_STRUCTURE_CHOICES = [(value, value) for value in sorted(RATE_STRUCTURE_VALUES)]


class Rate(BaseModel):
    """A single priced line, on the table its own name asks for (#367).

    ⚠ **THE KIND DISCRIMINATOR IS GONE FROM THIS TABLE, AND ITS ABSENCE IS THE
    STATEMENT.** A rate used to carry a `cost`/`price` word of its own, copied
    from the book it was created under and never read by resolution: the ladder
    selected BOOKS by kind and then asked this table for the rules inside them,
    so the column decided nothing and could disagree with the book it was
    copied from.
    Deleting it rather than re-spelling it is the point of the slice — one
    table wearing a kind word is what stopped the model saying that a book of
    supplier costs and a book of customer prices are different things governed
    by different rules (#148 §5.4).

    ⚠ **AND NOTHING CARRIES IT ANY MORE (#368).** #367's note here said the
    container still held the word "until ticket 21 splits it into two
    separately shaped entities". It has: a rule now points at a `PricingBook`
    or at a `CostBook`, two tables with different columns, and there is no
    value anywhere that a reader could compare to decide which half a rule
    belongs to. The kind of a rule is which column is set, which is a fact the
    database holds rather than a word a writer copied.
    """

    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE, related_name="rules")
    customer = models.ForeignKey("customers.Customer", on_delete=models.CASCADE,
                                 related_name="rules", null=True, blank=True)
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
    # close. All ten reach the published contract under THESE names since #366:
    # `RateChangeIn` and `RateOut` publish the column names, so the dictionary
    # that used to join six published names to their columns is gone and there
    # is no spelling left for the contract and the table to disagree about. (A
    # third schema published them until #367 deleted the immediate add-a-rule
    # body with its route.) All ten are also addressable by the tenant's
    # declared KEY rather than by the slot (#358), on the act that replaced
    # those routes — which is now the only way a rule is opened or retired.
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
    # ⚠ AND IT SITS BESIDE `rate_structure` BELOW, WHICH HOLDS THE RULE'S
    # ARITHMETIC SHAPE AND HAS NOTHING TO DO WITH THIS. Two adjacent character
    # fields, unrelated value sets: HOW A PRICE IS DERIVED (a margin, or a price
    # of its own) versus HOW THE ARITHMETIC RUNS (per unit of quantity, or
    # once). They used to be one character apart, which is why ADR-0006 §3 names
    # the pair; the second is `rate_structure` now and the collision is gone.
    # Read the two comments together before touching either.
    pricing_method = models.CharField(
        max_length=32, choices=PRICING_METHOD_CHOICES, null=True, blank=True)
    #: WHICH COLUMN HOLDS THE RATE'S ARITHMETIC SHAPE, NAMED ONCE (#350).
    #:
    #: The shape decides which arithmetic produced an amount — so much per unit
    #: of quantity, or a component that applies once regardless — and a reader
    #: rebuilding an amount out of a Pricing Receipt has to know which.
    #:
    #: ⚠ **IT EXISTED BECAUSE THE COLUMN'S NAME WAS RETIRED, AND THAT REASON IS
    #: NOW SPENT.** It was the `Posting.RECEIPT_COLUMN` pattern: a way for a
    #: module barred from spelling a retired word to address the column anyway,
    #: written so that its readers would follow the rename rather than go
    #: quietly vacuous on the day it landed. This is that day, and they did.
    #: What survives is the smaller claim it also made — that the receipt's
    #: component key and this column are ONE name, so a reader rebuilding an
    #: amount and the writer that recorded it cannot drift apart. Delete it only
    #: with a reader that reads the column some other way.
    STRUCTURE_COLUMN = "rate_structure"
    rate_structure = models.CharField(
        max_length=20, choices=RATE_STRUCTURE_CHOICES,
        default=RATE_STRUCTURE_PER_UNIT)
    rate_per_unit_micros = models.BigIntegerField(default=0)
    unit_quantity = models.BigIntegerField(default=1_000_000)
    fixed_micros = models.BigIntegerField(default=0)
    currency = models.CharField(max_length=3, default="usd")
    #: WHICH BOOK THIS RULE IS IN — one of two columns, at most one set
    #: (#368). A rule used to point at a single container told apart by a
    #: `cost`/`price` word; the two are separate entities now, so the pointer
    #: is two pointers and `SITS_IN_AT_MOST_ONE_BOOK_CHECK` is what stops a
    #: rule being reachable from both halves. `Rate.book` reads whichever is
    #: set, for the many callers that want the container and not its kind.
    #:
    #: ⚠ **`PROTECT` ON BOTH, AND IT IS WHY WITHDRAWING A BOOK CAN BE
    #: REFUSED.** A book holding rules cannot be deleted out from under them —
    #: which is what makes `pricing_book.withdrawn` an act with a meaning
    #: rather than a silent cascade over a tenant's price history.
    pricing_book = models.ForeignKey("pricing.PricingBook",
                                     on_delete=models.PROTECT,
                                     related_name="rates", null=True, blank=True)
    cost_book = models.ForeignKey("pricing.CostBook", on_delete=models.PROTECT,
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
        # THE TABLE ITS OWN NAME ASKS FOR (#367, #154 §6.2). It sat on the
        # name that belongs to the container beside it, because the misnamed
        # original took it first; this is the rate half of that inversion,
        # corrected by a rename that carries its rows rather than by a rebuild.
        # The container half followed one commit later, and the freed name was
        # not what it took — a book of prices is a `PricingBook` (#368).
        db_table = "ubb_rate"
        indexes = [
            # THE LOOKUP INDEX, WITHOUT THE KIND WORD (#367). It led on
            # `tenant` and then on a discriminator that no query filters —
            # resolution reaches this table through the books it has already
            # selected — so the column's deletion takes a dead leading term out
            # of the index with it and leaves the terms a lookup really uses.
            # Renamed with the table, because an index named for the container
            # on a table named for a rate is the same wart one layer down.
            models.Index(fields=["tenant", "provider", "event_type", "measurement"],
                         name="idx_rate_lookup"),
        ]
        constraints = [
            # ONE ACTIVE RULE PER IDENTITY PER BOOK — NOW TWO CONSTRAINTS,
            # BECAUSE ONE OVER BOTH COLUMNS WOULD ENFORCE NOTHING (#368).
            #
            # ⚠ This is the trap the split walks into and it fails SILENTLY. A
            # single key naming both book columns would carry a NULL in one of
            # them on every row, and Postgres treats NULLs in a unique index as
            # DISTINCT — so no two rows would ever collide and the constraint
            # would be a no-op wearing the old name. Two partial keys, each
            # scoped to the half whose column is present, is what keeps the
            # rule the rule.
            models.UniqueConstraint(
                fields=["pricing_book", "measurement", "currency", "provider",
                        "event_type", "task_type", "subtask_type",
                        "grouping_field_1", "grouping_field_2", "grouping_field_3",
                        "grouping_field_4", "grouping_field_5", "grouping_field_6",
                        "grouping_field_7", "grouping_field_8", "grouping_field_9",
                        "grouping_field_10"],
                condition=models.Q(valid_to__isnull=True,
                                   pricing_book__isnull=False),
                name="uq_rate_active_in_pricing_book"),
            models.UniqueConstraint(
                fields=["cost_book", "measurement", "currency", "provider",
                        "event_type", "task_type", "subtask_type",
                        "grouping_field_1", "grouping_field_2", "grouping_field_3",
                        "grouping_field_4", "grouping_field_5", "grouping_field_6",
                        "grouping_field_7", "grouping_field_8", "grouping_field_9",
                        "grouping_field_10"],
                condition=models.Q(valid_to__isnull=True,
                                   cost_book__isnull=False),
                name="uq_rate_active_in_cost_book"),
            models.CheckConstraint(
                condition=~models.Q(pricing_book__isnull=False,
                                    cost_book__isnull=False),
                name=SITS_IN_AT_MOST_ONE_BOOK_CHECK),
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
            # components this table can express — the per-unit rate and the
            # fixed addend — are `direct_event_price`'s own terms, so the
            # refusal is over a margin rule carrying them. The mirrored refusal
            # (a direct rule carrying a margin term) is not expressible here: no
            # percentage column exists on this table, because markup is still a
            # separate record. The ticket that moves it is the ticket that adds
            # the other half.
            models.CheckConstraint(
                condition=(
                    ~models.Q(pricing_method=PRICING_METHOD_MARGIN_OVER_COST)
                    | models.Q(rate_per_unit_micros=0, fixed_micros=0)),
                name=NEVER_COMPOSES_CHECK),
        ]

    @property
    def book(self):
        """THE CONTAINER THIS RULE IS IN, WHICHEVER KIND IT IS (#368).

        Most readers of a rule's container want the container — its version,
        its key, whose rules it holds — and not which of the two tables it
        came from. This answers that question once, so a caller that genuinely
        needs the kind reads the column it means and everyone else does not
        have to write the disjunction out.

        ⚠ **IT IS NOT A DISCRIMINATOR COMING BACK.** The word that used to sit
        on this table decided things: resolution read it, two routes wrote it,
        and it could disagree with the book it was copied from. This derives
        from the columns and can disagree with nothing — and it answers `None`
        for a rule in no book, which is a state this table has always had.
        """
        return self.pricing_book or self.cost_book

    @property
    def measurement_key(self):
        """The name of the quantity this rate prices.

        DERIVED, NEVER STORED (#326), which is the whole of what the conversion
        bought: the name is the declaration's, so a rate cannot hold a spelling
        the catalogue does not. It is still what the wire carries — every
        schema naming a rule, `RateChangeIn`, `BookChangeIn`, `RateOut` and the
        override bodies among them, publishes this key, and THIS KEY has not
        moved on any of them — and still what the pricing receipt and the audit
        record write, so #326's conversion changed nothing a caller can see.
        ⚠ Those schemas HAVE since been reshaped around it (#366 took their
        slot properties to the column names and renamed the arithmetic shape,
        and #367 deleted the immediate add-a-rule body outright with its
        route); the claim here is about this property, not about the schemas.

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
        """What this rule charges for a measured quantity.

        ⚠ **THE BRANCH BELOW WAS A RETIRED *SENSE*, NOT A RETIRED TERM, AND
        NOTHING MECHANICAL COULD FIND IT.** The value this method compared
        against for a component that applies once was `flat` — retired as a
        `rate_structure` value in `domain-vocabulary/concepts/retired.yaml`,
        where it sits under `retired_senses` rather than `retired_aliases`
        because `values_list(..., flat=True)` is Django's own keyword and
        sweeping the bare token would condemn the ORM. So the forbidden-term
        sweep never had this line as input: it was green over it on the day the
        word was retired and would have stayed green over it forever. It is
        converted by reading the method, not by grepping for a token.

        The comparison goes through the registry's own constant rather than a
        literal, so the day a value moves again this stops compiling instead of
        silently taking the other branch.
        """
        if self.rate_structure == RATE_STRUCTURE_FIXED_COMPONENT:
            return self.fixed_micros
        units = units or 0
        return (units * self.rate_per_unit_micros + self.unit_quantity // 2) // self.unit_quantity + self.fixed_micros


class TaskPrice(BaseModel):
    """WHAT A WHOLE UNIT OF WORK OF ONE DECLARED KIND IS SOLD FOR (#415, #139
    §2.4) — the second kind of line a Pricing Book holds.

    A `Rate` above prices a measured QUANTITY: so much per thousand tokens, so
    much per rendered second. This prices a whole delivered piece of work at
    one agreed number, and the two are lines in the same book on purpose — a
    tenant has one place to look and one place to change (#187 story 30).

    **THE KIND OF WORK DECLARES ONLY *THAT* IT IS SOLD THIS WAY; THE AMOUNT IS
    HERE.** `TaskType.pricing_mode` says `fixed`, and that declaration carries
    no number at all — the same rule #138 established for the Event Type, and
    re-opening it for work would undo what that decision bought. Putting the
    amount in the customer's own policy book is what brings per-customer
    pricing, book selection and the tenant's existing publishing model with it
    rather than inventing a second configuration surface for money.

    ⚠ **THE WORK LADDER IS ONE STEP, NOT THREE** (#139 §2.4). The rate side's
    ladder — the exact Event Type, then a broader rule, then the book's default
    — is about EVENTS. A whole-job price keys on the kind of work and on
    nothing else, so there is no *more specific* line to out-rank a *less
    specific* one and no book-wide fallback beneath either: "a default fixed
    price for all work regardless of kind" is not a thing a tenant could mean.
    What still ranks is WHICH BOOK the line came from, which is
    `pricing_service.FROM_THE_CUSTOMERS_OWN_RULES` over
    `FROM_THE_SELECTED_BOOK`, and that is the whole of the ranking.

    ⚠ **AND A MATCHED LINE SWITCHES THE EVENT-LEVEL LADDER OFF FOR THAT UNIT
    OF WORK** rather than competing with it. The two never rank against each
    other because they answer different questions, and the regime — not the
    presence of a line — is what decides which question is asked.

    ⚠ **NO CURRENCY COLUMN, AND THE ABSENCE IS `PricingBook`'S OWN ARGUMENT
    ONE LINE DOWN.** A tenant has exactly one currency (CUR-1: per-tenant
    single currency, no FX) and the book this line sits in carries none for
    precisely that reason — a column repeating it would be a copy of a choice
    made elsewhere. A rate carries one because the cost half of that table
    prices what a SUPPLIER charged, in the supplier's currency; nothing on this
    table is ever a supplier's number. Which currency a delivered unit of work
    is charged in is the Charge's to record (#416), where it is a fact about a
    money movement rather than about a price list.

    ⚠ **NOTHING WRITES THIS TABLE YET, AND THAT IS A NAMED RESIDUAL RATHER
    THAN AN OVERSIGHT.** Prices are edited in ONE place — the book's
    declare-then-publish act (`services/book_service.py`) — and slice 4 spent
    #367 and #368 deleting every immediate-effect mutation path so that a rule
    could not move without a publish record saying who moved it and when. So
    the surface that opens and closes a work-level line is the publish act's to
    grow, and it is not a small edit: that act's change body REQUIRES the
    quantity a line prices (`BookChangeIn.measurement_key`), which a whole-work
    line does not have, and relaxing it reshapes the planner, the rendered diff
    and the published request together.

    A second write path in the meantime — an admin registration, or a `PUT` of
    its own — was considered and rejected on exactly what those two tickets
    bought: it would put a money-shaped configuration change back outside the
    publish record, one table over from where that hole was closed, and #187
    §25 Q1 rules that *price is a read-only link into the book* precisely
    because there is one place prices are edited. This ticket builds the half
    that decides money — the resolution, the pinning and the refusals — and
    the line's own surface arrives with the act that already owns every other
    line in this book.
    """

    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE,
                               related_name="task_prices")
    #: WHICH BOOK THIS LINE IS IN — a Pricing Book and never a cost book, which
    #: is why there is one pointer here where `Rate` has two. A cost book holds
    #: what a supplier charged; a unit of work is not something UBB's tenant
    #: buys, so there is no cost-side reading of this line for a second column
    #: to express.
    #:
    #: `PROTECT`, for the reason the rate side gives: a book holding lines
    #: cannot be deleted out from under them, which is what makes withdrawing a
    #: book an act with a meaning rather than a silent cascade over a tenant's
    #: price history.
    pricing_book = models.ForeignKey("pricing.PricingBook",
                                     on_delete=models.PROTECT,
                                     related_name="task_prices")
    #: WHICH ALTITUDE THE DECLARATION THIS LINE PRICES IS FOR.
    #:
    #: ⚠ **WITHOUT IT THIS TABLE COULD NOT SAY WHAT #139 §3.3 REFUSES.** That
    #: ruling is *"a fixed-price line on a SUBTASK TYPE is refused at start,
    #: loudly"* — a line written against a declaration meant for contained
    #: work. A `TaskType`'s uniqueness is `(tenant, kind, key)` precisely so
    #: one word can name a kind of work at either altitude and the two are
    #: different declarations; a line keyed on the bare word cannot express
    #: what the declaration it prices already can, so the refusal would have to
    #: fire on *any* line for that word and a tenant could then never run a
    #: priced kind of work as a step of itself. A render job containing render
    #: steps is an ordinary shape, and it would have been told to *price the
    #: kind of work that contains this one* — which it had.
    #:
    #: So a line names the altitude the same way the declaration does, the
    #: resolver asks for the altitude the start is at, and the refusal fires on
    #: exactly the row #139 §3.3 names. A line at the contained altitude is
    #: unreachable by any other path — a start naming a contained declaration
    #: at the top level is refused earlier, as undeclared — so its whole effect
    #: is that loud refusal, which is the point of refusing rather than
    #: ignoring it.
    kind = models.CharField(max_length=8, choices=TASK_TYPE_KIND_CHOICES,
                            default=TASK_TYPE_KIND_TASK)
    #: THE DECLARED KIND OF WORK THIS LINE PRICES, BY KEY — never "" here.
    #:
    #: ⚠ A KEY AND NOT A REFERENCE, WHICH IS THE OPPOSITE OF WHAT #326 DID TO
    #: THE RATE'S QUANTITY, so the difference is worth saying. It is the same
    #: spelling `Rate.task_type` and `Task.task_type` already carry, and the
    #: start gate has resolved the declaration by `(tenant, kind, key)` before
    #: it ever reaches this table — so a reference would re-answer a question
    #: already answered rather than close a gap. It would also import the
    #: declaration's ALTITUDE into this row, which is precisely the refusal
    #: #139 §3.3 puts at the start gate and requires to be loud: a line written
    #: against contained work is a configuration mistake a tenant must be TOLD
    #: about, and a foreign key would make it unwritable and the refusal
    #: unreachable. It further makes a kernel model `PROTECT`-ed by a product
    #: table, which is the sandbox-reset ordering trap three tickets have
    #: already paid for (#354, #358, #362).
    #:
    #: A line naming a kind of work nobody declared resolves for no start,
    #: because a start naming an undeclared kind is refused above this.
    task_type = models.CharField(max_length=64)
    #: THE AGREED PRICE FOR ONE DELIVERED UNIT OF WORK OF THAT KIND.
    #:
    #: ⚠ IT REPLACES METERED REVENUE FOR THAT UNIT — not a fee on top of it and
    #: not a floor under it (#139 §2.1). "Charge the higher of metered or
    #: fixed" already has a home as its own policy-line content (#138), and a
    #: per-unit fee PLUS metered usage is a different product.
    #:
    #: ZERO IS A PRICE. A tenant who agrees to deliver a kind of work for
    #: nothing has said something, and the constraint below admits it while
    #: refusing a negative one: a line that pays the customer to be delivered
    #: to is not a price, it is a sign error.
    amount_micros = models.BigIntegerField()
    #: WHEN THIS LINE TAKES EFFECT, and when it stops — the rate side's two
    #: instants, with the same meanings and the same half-open window
    #: (`valid_from <= t < valid_to`).
    #:
    #: ⚠ THEY ARE WHAT MAKES *RESOLVED AT THE START INSTANT* A CLAIM RATHER
    #: THAN A FIGURE OF SPEECH. Without a line that can be in force at one
    #: instant and not another there would only ever be one answer for the
    #: price half, and the cost/revenue asymmetry `work.Task
    #: .agreed_price_micros` argues could not be stated, let alone tested.
    #:
    #: ⚠ NOT DECLARED INTO A TRANSITION CLASS, AND THIS TABLE DECLARES NONE.
    #: The rate table declares these two exact columns and this one deliberately
    #: does not, which is a difference worth stating rather than leaving silent:
    #: a rate's window is read by every recording forever, so moving it re-costs
    #: work that has already reported, whereas a work-level line is read ONCE
    #: per unit of work and the answer is pinned onto the row that same instant
    #: (`Task.agreed_price_micros`). What protects history here is that pinning,
    #: which holds a VALUE — editing this line cannot move a number a unit of
    #: work already carries. The ticket that gives this table a publish path is
    #: the one that should ask whether its windows want a rule of their own.
    valid_from = models.DateTimeField(default=timezone.now, db_index=True)
    valid_to = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "ubb_task_price"
        constraints = [
            # ONE LINE IN FORCE PER DECLARATION PER BOOK. There is no
            # specificity ladder inside a book here — see the class docstring —
            # so two open lines for one declaration in one book would be two
            # answers with nothing to choose between them, which is a
            # configuration a tenant cannot have meant and the resolver would
            # settle by whichever row came back first.
            #
            # IT CARRIES `kind` FOR THE REASON THE DECLARATION'S OWN KEY DOES
            # (`work.TaskType`: `(tenant, kind, key)`): one word names a kind of
            # work at either altitude and the two are different declarations, so
            # a key without the altitude would refuse a tenant the second line
            # while telling them nothing about why.
            models.UniqueConstraint(
                fields=["pricing_book", "kind", "task_type"],
                condition=models.Q(valid_to__isnull=True),
                name="uq_task_price_active_in_pricing_book"),
            # A PRICE IS NOT NEGATIVE. Zero is admitted and is a real answer;
            # see `amount_micros`.
            models.CheckConstraint(
                condition=models.Q(amount_micros__gte=0),
                name="ck_task_price_amount_not_negative"),
        ]
        indexes = [
            # THE RESOLUTION LOOKUP: every book in play at once, one
            # declaration at one altitude, as of one instant — the shape
            # `_selected_pricing_books` hands the resolver.
            models.Index(fields=["kind", "task_type", "valid_from"],
                         name="idx_task_price_lookup"),
        ]

    def __str__(self):
        return f"TaskPrice({self.kind}:{self.task_type}: {self.amount_micros})"


class Charge(BaseModel):
    """WHAT ONE DELIVERED PIECE OF WORK SOLD AT ONE AGREED PRICE IS OWED FOR,
    once and immutably (#416, #139 §2.3, spec §11).

    **ONLY AN EXPLICIT CLOSE DECLARING DELIVERY EARNS ONE.** Non-delivery never
    charges — failed, cancelled, killed and expired all produce nothing — and
    exposure on work that did not deliver is bounded by the COGS ceiling the
    tenant chose rather than recovered by charging for it anyway.

    ⚠ **THE PINNED PRICE ON THE WORK ITSELF COULD NOT BE THIS RECORD**, and the
    three reasons are the three things this table adds. `work.Task
    .agreed_price_micros` is the DETERMINATION — which price applies — and a
    determination must be able to exist and never become a charge, which is the
    failed case and is ordinary. Beyond that: a unit of work's row is mutable
    and this one is not, and a unit of work carries no currency at all, while a
    movement of money is a fact about one. So the two are one-to-zero-or-one
    with different lifetimes rather than one row wearing two hats.

    ⚠ **A SYSTEM-GENERATED POSTING AS THE CANONICAL RECORD WAS REJECTED.** It
    would have bought every money path for free, but a posting is immutable AND
    undeletable, so a wrong projection could never be corrected — permanent, by
    construction. The projection is #417's and it is a projection OF this row
    precisely so that a wrong one can be rebuilt from a right one.

    **ITS KEY IS DERIVED FROM THE WORK, NEVER SUPPLIED BY A CALLER.** The
    identity of a piece of work is already unique within its tenant and
    customer, and this repository's stance is explicit one table over: a caller
    does not supply amounts or keys the system can derive. Belt and braces
    beside that, and each holds a different failure: the write fires only on the
    WINNING transition into the delivered state (`TaskService._flip` returns
    which call won), the partial uniqueness below makes a second primary charge
    a database error rather than a double charge, and #417's projected posting
    carries a unique money key of its own.

    ⚠ **CORRECTIONS ARE COMPENSATING RECORDS, NEVER EDITS.** Every economic
    column is declared `FROZEN` — ADR-0007 §2's *none after insert* — and
    `pricing/0031` holds the declaration at the database across `save()`,
    `QuerySet.update()` and raw SQL alike. A wrong charge therefore leaves a
    trail: the original stands, and what corrects it is another row of this
    table naming it. See `compensates` below.

    **UBB'S OWN PLATFORM FEE APPLIES TO IT**, which #417 makes an explicit
    property of the projection rather than something the projection inherits by
    accident.
    """

    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE,
                               related_name="charges")
    #: THE PIECE OF WORK THIS IS THE CHARGE FOR.
    #:
    #: `CASCADE`, which is `usage.Posting.task` verbatim and for its reason: a
    #: unit of work's records are records OF it and have no meaning once it is
    #: gone. `PROTECT` was considered and refused — it would make an immutable
    #: money record able to block an ordinary tenant wipe, and it would put this
    #: table into the sandbox reset's pre-sweep ordering problem that #354, #358,
    #: #362 and #415 have each paid for once already.
    task = models.ForeignKey("work.Task", on_delete=models.CASCADE,
                             related_name="charges")
    #: WHAT IS OWED, IN MICROS OF THE CURRENCY BELOW.
    #:
    #: A COPY OF THE PINNED NUMBER RATHER THAN A READ THROUGH IT. The work's row
    #: is mutable; this one is frozen, and a charge that could change because
    #: something else changed would not be a record of a money movement.
    #:
    #: ⚠ SIGNED, AND ONLY BECAUSE A COMPENSATING RECORD MUST BE. The check below
    #: refuses a negative primary charge — a charge that pays the customer is a
    #: sign error, and zero is a real answer for work a tenant agreed to deliver
    #: for nothing (`TaskPrice.amount_micros` argues the same admission).
    amount_micros = models.BigIntegerField()
    #: THE CURRENCY THIS MONEY MOVED IN.
    #:
    #: ⚠ **ITS PRESENCE HERE IS ONE OF THE THREE REASONS THE PINNED PRICE COULD
    #: NOT BE CANONICAL.** A price LIST needs none — `PricingBook` argues that a
    #: tenant has exactly one currency (CUR-1) and a column repeating it would
    #: copy a choice made elsewhere — but a charge is not a price list entry, it
    #: is a fact about money, and a fact about money names its currency.
    #: Lowercase, matching every other currency column in the tree.
    currency = models.CharField(max_length=3)
    #: WHICH LINE ANSWERED, AND WHICH PUBLISHED VERSION OF THE BOOK HELD IT.
    #:
    #: Both are COPIED off the piece of work, which pinned them at the one
    #: instant they were known (#415). Neither is re-derived here and neither
    #: could be: #139 §2.3 requires the amount to be reproducible from the record
    #: *"rather than by re-resolving today's config"*, and re-resolution is not
    #: available later on any terms, because which books are even in play depends
    #: on the customer's plan, which moves.
    #:
    #: A PLAIN UUID AND NOT A FOREIGN KEY, which is `work.Task
    #: .agreed_price_line_id` doing the same thing beside it. Here the reason is
    #: not ADR-001 — this table is in the same app as the line — it is that this
    #: is a RECORD of what answered rather than a live reference to configuration:
    #: the receipt's own `provenance` section carries cross-reference ids as data
    #: for the identical reason. A `PROTECT` key would additionally make an
    #: immutable money record able to refuse a tenant the withdrawal of a book,
    #: forever, and put this table in the pre-sweep ordering the `task` pointer
    #: above declines.
    agreed_price_line_id = models.UUIDField()
    book_version = models.PositiveIntegerField()
    #: WHEN THE PRICE WAS RESOLVED, WHICH IS WHEN THE WORK STARTED.
    #:
    #: ⚠ **IT IS WHAT KEEPS MARGIN EXACT ACROSS A PERIOD BOUNDARY.** The charge
    #: is dated at DELIVERY (see below), so work that starts in one month and
    #: delivers in the next has its cost in the earlier period and its revenue in
    #: the later one. Carrying the start instant here means a reader netting this
    #: revenue against this piece of work's own COGS has both halves on one row
    #: and never has to decide which period the work belonged to.
    resolved_at = models.DateTimeField()
    #: WHEN DELIVERY WAS DECLARED — the instant the winning transition wrote.
    #:
    #: ⚠ **DATED AT DELIVERY, SO DELIVERED WORK IS ALWAYS BILLABLE.** Dating back
    #: to the start would keep cost and revenue in one period, and was rejected on
    #: the DIRECTION of its failure rather than on taste: work starting at 23:58
    #: on the 31st and closing after the month's push had already claimed that
    #: period would become unbillable for work that was delivered, which is a
    #: failure in the worst direction. The accepted consequence is the opposite
    #: skew, and it is tightly bounded by the absolute deadline a kind of work
    #: declares (#412).
    charged_at = models.DateTimeField()
    #: THE EXACTLY-ONCE KEY, DERIVED FROM THE WORK — see the class docstring.
    idempotency_key = models.CharField(max_length=128)
    #: WHICH CHARGE THIS ONE CORRECTS, OR NULL FOR AN ORIGINAL.
    #:
    #: ⚠ **THIS IS THE WHOLE OF WHAT "CORRECTIONS ARE COMPENSATING RECORDS"
    #: MEANS IN COLUMNS.** Every economic field of this table is frozen, so a
    #: wrong charge cannot be rewritten; what can happen is that another row
    #: arrives naming it, and the pair reads as a trail. A reversal carries the
    #: negation of the original and nets it to nothing; a re-statement at a
    #: different number is a second compensating row beside the first. Either way
    #: the original still says what UBB originally charged, which is the property
    #: an edit destroys.
    #:
    #: `PROTECT`, because a trail with its head removed is not a trail.
    #:
    #: ⚠ IT IS ALSO WHAT MAKES "EXACTLY ONE CHARGE, EVER" EXPRESSIBLE. The
    #: uniqueness below is PARTIAL on this column being null, so one piece of
    #: work has at most one ORIGINAL charge for all time while carrying as many
    #: corrections as it turns out to need.
    compensates = models.ForeignKey("self", on_delete=models.PROTECT,
                                    null=True, blank=True,
                                    related_name="compensations")
    #: WHY A CORRECTION WAS MADE — free text, and "" on an original.
    #:
    #: FREE TEXT AND NEVER A VOCABULARY, which is `work.Task.reason_detail`'s
    #: own reasoning: the population of reasons a charge turns out to be wrong is
    #: not knowable in advance, and a closed set would either refuse the real
    #: reason or grow a value per incident.
    correction_note = models.TextField(blank=True, default="")

    # THE GROUPING FIELD SNAPSHOT — the ten slots the work carried, copied.
    #
    # ⚠ A COPY RATHER THAN A READ THROUGH THE WORK, for this table's whole
    # reason: those columns live on a mutable row and this one is frozen. It is
    # also what lets #417's projection inherit them onto the posting from the
    # Charge, so *margin by region* nets this revenue against that same piece of
    # work's COGS in the same bucket with no new code — the inheritance the
    # posting rail already performs, reading one more row.
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

    #: EVERY ECONOMIC COLUMN IS `FROZEN`, AND THE DATABASE HOLDS IT
    #: (`pricing/0031`). ADR-0007 §2 is explicit that a model-level guard alone
    #: is not enforcement, so the declaration here is a statement and the trigger
    #: is the enforcement — G19 walks this mapping and fails on any column no
    #: rule on this table names.
    #:
    #: ⚠ THE TWO POINTERS ARE SPELLED AS THEIR COLUMNS (`task_id`,
    #: `compensates_id`) RATHER THAN AS THEIR FIELDS. This vocabulary is about
    #: COLUMNS — the gate searches a trigger body, and a trigger says
    #: `NEW.task_id` — so declaring `task` would name something no rule can
    #: spell and would be satisfied only by a comment, which is the vacuous shape
    #: #325 paid for.
    #:
    #: `correction_note` is deliberately NOT here and its absence is the
    #: statement: it is display text beside a correction, not an economic fact,
    #: and freezing prose would refuse an operator the ability to finish a
    #: sentence. Nothing reads it for a number.
    transition_classes = {
        "task_id": FROZEN,
        "amount_micros": FROZEN,
        "currency": FROZEN,
        "agreed_price_line_id": FROZEN,
        "book_version": FROZEN,
        "resolved_at": FROZEN,
        "charged_at": FROZEN,
        "idempotency_key": FROZEN,
        "compensates_id": FROZEN,
        **{f"grouping_field_{slot}": FROZEN for slot in range(1, 11)},
    }

    class Meta:
        db_table = "ubb_charge"
        constraints = [
            # EXACTLY ONE ORIGINAL CHARGE PER PIECE OF WORK, FOR ALL TIME.
            #
            # This is the acceptance criterion as a database rule rather than as
            # a code path: the winning-transition guard is what normally stops a
            # second one, and this is what holds when two closes race and both
            # win their own read. It is PARTIAL on `compensates` being null so
            # that a correction — which is a row of this table naming another —
            # is not refused by the rule that stops a double charge.
            models.UniqueConstraint(
                fields=["task"],
                condition=models.Q(compensates__isnull=True),
                name="uq_charge_one_original_per_unit_of_work"),
            # THE DERIVED KEY IS UNIQUE WITHIN THE TENANT.
            #
            # Scoped to the tenant and not globally, matching every other key in
            # this tree: two tenants' records never collide by construction and a
            # global rule would say they might.
            models.UniqueConstraint(
                fields=["tenant", "idempotency_key"],
                name="uq_charge_idempotency_key"),
            # AN ORIGINAL CHARGE IS NOT NEGATIVE, AND A CORRECTION MAY BE.
            #
            # A charge that pays the customer to be delivered to is a sign error
            # rather than a deal, which is `TaskPrice.amount_micros`' own
            # sentence; zero is admitted there and admitted here for the same
            # reason. A COMPENSATING row is exempt because reversing a charge is
            # exactly a negative one, and refusing that would leave a wrong
            # charge with nothing able to correct it.
            models.CheckConstraint(
                condition=(models.Q(compensates__isnull=False)
                           | models.Q(amount_micros__gte=0)),
                name="ck_charge_an_original_is_not_negative"),
            # A CORRECTION SAYS WHY, AND AN ORIGINAL HAS NOTHING TO SAY.
            #
            # The trail is only readable if each correction carries its own
            # reason; an original carrying one would be a charge apologising for
            # itself.
            models.CheckConstraint(
                condition=(models.Q(compensates__isnull=True,
                                    correction_note="")
                           | models.Q(compensates__isnull=False)
                           & ~models.Q(correction_note="")),
                name="ck_charge_a_correction_says_why"),
        ]
        indexes = [
            # THE ROLLUP: what a tenant was owed over a window, by customer and
            # by kind, is read through the work — so the useful order here is the
            # one a period close and a margin report both scan.
            models.Index(fields=["tenant", "charged_at"],
                         name="idx_charge_tenant_charged"),
        ]

    def __str__(self):
        return f"Charge({self.amount_micros} {self.currency} for {self.task_id})"


class CostBook(BaseModel):
    """WHAT A SUPPLIER CHARGES UBB'S TENANT, PINNED TO THAT SUPPLIER AND TO
    THE CURRENCY THEY BILL IN (#368, spec §1).

    **A SEPARATELY SHAPED ENTITY FROM THE PRICING BOOK BELOW, AND THE SHAPES
    ARE THE WHOLE POINT.** One table used to serve as both, told apart by a
    `cost`/`price` word — so a book of supplier costs and a book of customer
    prices had, by construction, the same columns and the same rules, and the
    model could not say that they are different things. They are: a cost is
    OBSERVED, in whatever currency the supplier bills, from whichever supplier
    was used. A price is DECIDED, by the tenant, and does not move because the
    tenant switched supplier (#148 §5.4).

    So this book carries a provider and a currency and the Pricing Book
    carries neither. That is not a tidier spelling of one column — it is two
    entities whose columns disagree, which is the thing a discriminator can
    never express.

    **THE CURRENCY IS DECLARED, NOT STAMPED, AND THE DATABASE HOLDS IT.**
    `ck_cost_book_names_its_currency` refuses the empty string: a cost book
    that does not say which currency its supplier bills in prices nothing it
    can be trusted about. This is why the container's line leaves the unowned
    currency-column list rather than following the rename — see
    `usage/tests/test_posting_rename.py`.

    ⚠ **THE PROVIDER IS REQUIRED TO BE STATED AND `""` IS A STATED VALUE.**
    The empty provider is the tenant's provider-agnostic cost book — a real
    selection tier that `PricingService._selected_cost_books` reads alongside
    the provider's own — so a `CHECK` refusing it would delete a feature under
    cover of a rename. What is enforced at the database is the currency; what
    is enforced by the SHAPE is that this book has a provider column at all
    and the Pricing Book has none. Both halves are asserted, separately and by
    name, in `test_a_book_of_costs_and_a_book_of_prices_are_two_shapes.py`.
    """
    #: WHICH COLUMN POINTS AT A BOOK OF THIS KIND, said by the kind itself
    #: (#368). `Rate` and `PricingBookPublish` each carry one reference per
    #: kind of book, so every reader that has a book and wants its rules —
    #: `book_service`, the routes, the resolver — asks the book which column
    #: is its own rather than testing what type it is. A dispatch written once,
    #: where the answer lives, instead of an `isinstance` at each call site.
    REFERENCE_COLUMN = "cost_book"

    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE,
                               related_name="cost_books")
    #: WHICH SUPPLIER'S PRICES THIS BOOK HOLDS. `""` is the provider-agnostic
    #: bucket, which is a declared choice rather than an absence — see the
    #: class docstring.
    provider_key = models.CharField(max_length=100, blank=True, default="")
    #: WHICH CURRENCY THAT SUPPLIER BILLS IN. No default, and the check below
    #: refuses the empty string: this is a declaration, not a copy of the
    #: tenant's own frozen choice.
    currency = models.CharField(max_length=3)
    key = models.SlugField(max_length=64)
    name = models.CharField(max_length=255, blank=True, default="")
    version = models.PositiveIntegerField(default=1)
    is_default = models.BooleanField(default=False)

    class Meta:
        db_table = "ubb_cost_book"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "key"], name="uq_cost_book_tenant_key"),
            models.UniqueConstraint(
                fields=["tenant", "provider_key", "currency"],
                condition=models.Q(is_default=True),
                name="uq_cost_book_one_default_per_provider"),
            models.CheckConstraint(
                condition=~models.Q(currency=""),
                name=NAMES_ITS_CURRENCY_CHECK),
        ]

    @property
    def rule_currency(self):
        """The currency a rule written into this book is denominated in.

        The book's own declared currency, because that is what the supplier
        bills in. `PricingBook.rule_currency` answers the same question from a
        different place, and asking the BOOK rather than reading a column off
        it is what lets one publish path serve both kinds (#368).
        """
        return self.currency

    def __str__(self):
        return f"CostBook({self.key} v{self.version})"


class PricingBook(BaseModel):
    """WHAT THE TENANT CHARGES THEIR OWN CUSTOMERS, PINNED TO NEITHER A
    SUPPLIER NOR A CURRENCY (#368, spec §1).

    The container the whole pricing surface is built around, on the table its
    own name asks for. It reached this name by two corrections, one ticket
    apart: #367 moved the misnamed rate off `ubb_rate_card`, and this commit
    took the freed name past it — the book is a Pricing Book, so the table it
    sits on is `ubb_pricing_book` rather than the borrowed spelling with a
    suffix bolted on to make room.

    ⚠ **IT CARRIES NO PROVIDER AND NO CURRENCY, AND THE TWO ABSENCES ARE
    DIFFERENT STATEMENTS.**

    * **No provider**, because a tenant's price for a unit of work does not
      change because they switched supplier (#148 §5.4). The provider-agnostic
      default that used to be a selection tier on this side is not a tier any
      more; it is what every Pricing Book is.
    * **No currency**, because a tenant has exactly one (CUR-1: per-tenant
      single currency, no FX) and a column repeating it here was a copy of a
      choice made elsewhere — which is precisely what the unowned
      currency-column list records as a debt. The copy is deleted rather than
      constrained, so the debt is paid rather than moved.

    The Python names have always been correct: a book is a sheet, a Rate is a
    line on one.
    """
    #: The twin of `CostBook.REFERENCE_COLUMN`; see it for why this is an
    #: attribute rather than a type test at each call site.
    REFERENCE_COLUMN = "pricing_book"

    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE,
                               related_name="pricing_books")
    # WHOSE OWN PRICING RULES THIS BOOK HOLDS, OR NOBODY'S (#361, #147 §4.1).
    #
    # A book carrying a customer is that customer's OVERRIDE book: every rule
    # in it is one of that customer's own rules, and resolution reads them at
    # the ladder's `FROM_THE_CUSTOMERS_OWN_RULES` source
    # (`services/pricing_service.py`). A book carrying none is a catalogue the
    # tenant wrote for everybody.
    #
    # **THIS IS WHAT MAKES AN OVERRIDE A WHOLE RULE RATHER THAN A NUMBER
    # (#151 §6).** An override replaces the rule it inherits completely — its
    # method, its terms and the selectors it pins — so it has to BE a rule,
    # written where rules are written and published the way rules are
    # published. Putting the customer on the book rather than on the rule is
    # what buys that: a book is what `PricingBookPublish` changes, what
    # `uq_rate_active_in_pricing_book` scopes uniqueness to, and what
    # `plan_changes` resolves a change against. Scoping rules to a customer INSIDE a shared
    # book would put the customer into a rule's IDENTITY and move all three at
    # once; putting it on the book moves none of them.
    #
    # ⚠ THAT IS ABOUT RULE IDENTITY AND NOT ABOUT THE WHOLE PUBLISH PATH.
    # `plan_changes` IS edited here — a change body may now state a rule's
    # method — which extends what a body carries rather than changing how a
    # rule is identified, closed or reopened. Nothing on the publishing,
    # forward-dating or reversal path knows a customer exists.
    #
    # **NULLABLE BECAUSE MOST BOOKS ARE NOBODY'S**, and the null is not a
    # second meaning: it says this book is not an override book. One override
    # book per customer is the constraint below.
    #
    # `SET_NULL` RATHER THAN `CASCADE`, AND THE REASON IS A REFUSAL FURTHER
    # DOWN THE CHAIN. `Rate.pricing_book` is `PROTECT`, so cascading a customer's
    # deletion into their book would make the database refuse to delete a
    # customer who was ever given a negotiated price — and refuse it from a
    # record nobody deleting a customer asked about, which is how a tenant wipe
    # stops half way (#354, #358). Nulling it leaves the rules, their windows
    # and the receipts that point at them exactly as they were, and leaves the
    # book in a state this schema already has: one nothing selects.
    #
    # ⚠ NOT DECLARED INTO A TRANSITION CLASS, AND THIS TABLE DECLARES NONE. The
    # rule table beside it declares two, so the absence is worth saying rather
    # than leaving silent: whose deal a book carries is configuration a tenant
    # changes — declaring an override and withdrawing it are exactly those two
    # writes — and configuration is not history. What protects history is the
    # receipt, which holds VALUES: withdrawing an override cannot move a number
    # a customer was already charged.
    #
    # ⚠ AN OVERRIDE BOOK IS A PRICING BOOK BY CONSTRUCTION NOW, AND THE
    # `CHECK` THAT USED TO BE OWED IS DISCHARGED BY THE SPLIT RATHER THAN
    # WRITTEN (#368). The comment this replaces said a constraint naming the
    # kind word would be "written to be dropped", and pointed at the route
    # instead. The kind word is gone: a cost book is a different table with no
    # customer column on it, so there is nowhere for a supplier's prices to
    # acquire a customer. That is the strongest form of the property and it
    # cost nothing to state — which is what splitting the entity buys.
    customer = models.ForeignKey("customers.Customer", on_delete=models.SET_NULL,
                                 related_name="pricing_override_books",
                                 null=True, blank=True)
    key = models.SlugField(max_length=64)
    name = models.CharField(max_length=255, blank=True, default="")
    version = models.PositiveIntegerField(default=1)
    is_default = models.BooleanField(default=False)

    class Meta:
        db_table = "ubb_pricing_book"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "key"], name="uq_pricing_book_tenant_key"),
            # ONE DEFAULT PRICING BOOK PER TENANT, AND THE KEY LOST TWO
            # COLUMNS RATHER THAN GAINING A MEANING (#368). It used to be
            # (tenant, kind, provider, currency): the kind is a different table
            # now, the provider is not a thing a price depends on, and the
            # currency is the tenant's. What is left is the sentence the
            # constraint was always trying to say — a tenant has one default
            # book of prices.
            models.UniqueConstraint(
                fields=["tenant"],
                condition=models.Q(is_default=True),
                name="uq_pricing_book_one_default"),
            # ONE OVERRIDE BOOK PER CUSTOMER (#361). A customer with two would
            # have two answers at one rung and nothing deciding between them,
            # which is the second independent ranking layer
            # specificity-before-source exists to dissolve (#147 §5.2).
            #
            # ⚠ IT NAMES THE CUSTOMER AND NOT THE TENANT, and that is not an
            # omission: a customer belongs to exactly one tenant, so a pair
            # naming both would be a wider key that admits nothing more.
            #
            # ⚠ THE CURRENCY LEFT THIS KEY WITH THE COLUMN (#368) AND THE KEY
            # ADMITS EXACTLY WHAT IT ADMITTED BEFORE. #361 keyed it per
            # currency while noting that "exactly one currency is reachable
            # today, which is CUR-1 rather than anything here" — a tenant has
            # one currency, so (customer, currency) and (customer) allowed the
            # same one row. The narrower key is what survives, because a
            # Pricing Book is no longer priced in a currency of its own.
            models.UniqueConstraint(
                fields=["customer"],
                condition=models.Q(customer__isnull=False),
                name="uq_pricing_book_one_override_per_customer"),
        ]

    @property
    def rule_currency(self):
        """The currency a rule written into this book is denominated in.

        The TENANT'S, because a Pricing Book has no currency of its own: a
        tenant has exactly one (CUR-1, per-tenant single currency, no FX), so a
        column here repeated a choice made elsewhere -- which is what the
        unowned currency-column list records as a debt, and why this commit
        deletes the column rather than constraining it.

        It costs a tenant read on the publish path, which is configuration
        rather than the recording hot path, and it buys the one thing a copy
        could never give: this answer cannot disagree with the tenant.
        """
        return self.tenant.default_currency or "usd"

    def __str__(self):
        return f"PricingBook({self.key} v{self.version})"


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
#: same undeclared set the arithmetic shape is refused against at its own route
#: today, and giving it a concept would advertise a set that has no meaning
#: outside this one body. (The kind word that used to be the other example is
#: gone: it is two tables now, so there is no set left to refuse against.)
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
    #: The book this changes — one of two columns, at most one set, the same
    #: shape `Rate` takes for the same reason (#368). A change to a book of
    #: supplier costs and a change to a book of customer prices are ONE act
    #: with one record; what the split changed is the entity a book is, not
    #: what publishing one means. Duplicating this record per kind would put
    #: the discriminator back as a table name.
    #:
    #: `CASCADE` rather than `PROTECT` on both, on purpose: a publish record
    #: explains a book, so it has no meaning once the book is gone, and a
    #: `PROTECT` here would make deleting a book fail on the records describing
    #: it — including under the sandbox reset, where a refusal from a record
    #: nobody asked about is how a tenant wipe stops half way.
    pricing_book = models.ForeignKey("pricing.PricingBook",
                                     on_delete=models.CASCADE,
                                     related_name="publishes",
                                     null=True, blank=True)
    cost_book = models.ForeignKey("pricing.CostBook", on_delete=models.CASCADE,
                                  related_name="publishes",
                                  null=True, blank=True)
    declaration_status = models.CharField(
        max_length=32, default=DECLARATION_STATUS_DRAFT, db_index=True)
    #: WHEN THE CHANGE TAKES EFFECT — the one value both boundaries are written
    #: from. Stated by the caller on the declaring body and defaulted in
    #: `BookService.declare` rather than by a model default, because a
    #: declaration with no stated moment means "now" at the moment it is
    #: *declared*, not at the moment the row happens to be constructed. Which
    #: instants a caller may state is `core.scheduling`'s — bounded ahead at a
    #: platform horizon and refused behind the present (#359).
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
        "pricing_book": RECORD_RULE,
        "cost_book": RECORD_RULE,
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
            models.Index(fields=["pricing_book", "declaration_status"],
                         name="idx_book_publish_pending"),
            models.Index(fields=["cost_book", "declaration_status"],
                         name="idx_cost_book_publish_pending"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(pricing_book__isnull=False,
                                    cost_book__isnull=False),
                name=PUBLISH_CHANGES_AT_MOST_ONE_BOOK_CHECK),
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
    def book(self):
        """The book this publish changes, whichever kind it is (#368).

        `Rate.book`'s twin, for the same readers and with the same caveat: it
        derives from the two columns and so can disagree with nothing. Every
        publish has one — the routes will not create a record without a book —
        so unlike a rule's, this never answers `None` in practice.
        """
        return self.pricing_book or self.cost_book

    @property
    def book_id(self):
        return self.pricing_book_id or self.cost_book_id

    @property
    def is_published(self):
        return self.declaration_status == DECLARATION_STATUS_PUBLISHED


class ResolutionRun(BaseModel):
    """THE RECORD OF A RECOVERY — one mechanism, one actor, one selector (#363).

    Four documents each described a way to put right what UBB could not resolve
    at the time — an unresolved-cost queue, a customer adjustment, a remediation
    path, a correction's decision record — and none of them owned building one.
    They are one mechanism here, because all three of the recovery paths that do
    not move money are the same act: **completing a `NULL` beside a status that
    says the field was never resolved.** This row is that act, written down.

    **A RUN MOVES NO MONEY.** It completes what was never resolved and records
    that it did. What recovering is worth is a projection over these records and
    the receipts behind them; the tenant then acts through the money path UBB
    already has. Stripe owns the billing engine — UBB drives invoicing, credit
    notes and refunds as a control plane and never reimplements them — so a
    UBB-owned adjustment surface would be exactly that reimplementation.

    ⚠ **SCOPED BY CONSTRUCTION, NEVER BY PREDICATE.** A run reaches only
    postings whose status says they were never resolved, and membership **is**
    that status: the candidate set is built from `core.amount_status_pairs`,
    where each pair names the ONE status meaning *not learned*. There is no flag
    to set correctly and no predicate to get right, and therefore no way for a
    run to touch a number that already exists. `waived` is outside a run for the
    same reason rather than by an exclusion somebody remembered to write — a
    waived charge is a decision somebody made, and a run recovers information
    UBB does not have, not decisions it disagrees with.

    **THE SELECTOR IS THREE AXES AND NEVER AN ARBITRARY PREDICATE.** A date
    range, a customer and an Event Type — the same axes the rule ladder itself
    selects on. It is a filter rather than a button because a tenant onboarding
    in August who backfills July has postings unresolved for two different
    causes, and *everything it matches* would apply one repair to postings
    needing another. A predicate is the check the construction argument above
    just refused, so the surface accepts none.

    **THE ACTOR IS SNAPSHOTTED, IN `AuditRecord`'s OWN THREE COLUMNS**
    (ADR-004 §4): an immutable copy taken at the moment of the act, so a later
    rename or deletion of the principal never rewrites what this record says.
    The ledger entry `resolution_run.executed` carries the same actor and the
    same selector; this row carries the OUTCOME, which the ledger has no column
    for and which the next ticket projects from.

    **THE INSTANT OF THE ACT IS `created_at` AND THERE IS NO SECOND COLUMN FOR
    IT.** A run record exists because a run happened, so the row's own creation
    instant *is* when it happened; an execution instant beside it would be two
    columns holding one fact, which is how the two come to disagree.

    ⚠ **NO PATH UPDATES ONE, AND THE DATABASE IS WHAT MAKES THAT TRUE.** Every
    column declares `RECORD_RULE` — not a class of its own, because the honest
    answer per column is *"nothing this column decides; read the record's
    rule"* — and the record's rule is that after the insert nothing may change,
    ever. `pricing/migrations/0025` holds it across every door. That is not
    tidiness: a run is irreversible under the receipt's sealing rule and this
    row is the only surviving explanation of it, so a record that could be
    edited afterwards would make the traceability a claim rather than a fact.
    `updated_at` can therefore never differ from `created_at`, which is what the
    rule means rather than an oversight in it.
    """

    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE,
                               related_name="resolution_runs")
    actor_kind = models.CharField(max_length=32, blank=True, default="")
    actor_id = models.CharField(max_length=255, blank=True, default="")
    actor_display = models.CharField(max_length=255, blank=True, default="")

    # --- The selector, on the three axes the rule ladder uses ---------------
    #
    # Each is nullable/blank and means "unpinned on this axis", which is the
    # same reading a rule's own selectors take: a rule leaving a selector empty
    # matches anything there. Recorded as the caller stated them rather than as
    # a compiled query, because what a governance reader asks afterwards is
    # what this run was POINTED AT, and a query object cannot answer that.
    selected_from = models.DateTimeField(null=True, blank=True)
    selected_to = models.DateTimeField(null=True, blank=True)
    #: ⚠ `CASCADE`, and the two neighbouring rules would both be wrong here. A
    #: `PROTECT` would make deleting a customer fail because a historical run
    #: once named them — a refusal from a record nobody asked about, which is
    #: how a tenant wipe stops half way. A `SET_NULL` is worse: it would leave
    #: the record saying this run was pointed at EVERY customer, which is a
    #: different act from the one that happened. A run scoped to one customer
    #: explains that customer's postings, and those go with them.
    selected_customer = models.ForeignKey(
        "customers.Customer", on_delete=models.CASCADE, null=True, blank=True,
        related_name="resolution_runs")
    selected_event_type = models.CharField(max_length=100, blank=True,
                                           default="")

    # --- The outcome -------------------------------------------------------
    #
    # ⚠ COUNTS AND NOT AMOUNTS. What a recovery is WORTH is a projection over
    # the receipts this run completed, and each of those names this run's id in
    # its provenance — so the money is read from the records that hold it, in
    # their own currencies, rather than summed into a column here that would add
    # two denominations together the day a run spans them.
    postings_examined = models.PositiveIntegerField(default=0)
    costs_settled = models.PositiveIntegerField(default=0)
    prices_resolved = models.PositiveIntegerField(default=0)
    #: Of those examined, how many the run completed nothing on. TWO REASONS
    #: PRODUCE THAT AND THIS COLUMN DELIBERATELY DOES NOT SEPARATE THEM: nothing
    #: the tenant has since configured resolves the posting, or the posting's
    #: own record cannot support a completion (an older shape, or an unresolved
    #: cost whose quantities it never kept). What they have in common is the
    #: whole of what this number claims — the run examined it and left it as it
    #: was. Separating them would put a diagnosis on the act's record, where a
    #: reader would take it for a count of what is recoverable; what is
    #: recoverable is a projection over the postings themselves.
    #:
    #: It is the honest half of the outcome either way: a run that completed
    #: nothing is a run that ran, not a failure, and the number that says so is
    #: what stops a green answer reading as a repair.
    postings_left_unresolved = models.PositiveIntegerField(default=0)
    #: WHETHER THE SELECTOR MATCHED MORE THAN ONE RUN MAY TAKE. A run is bounded
    #: (`resolution_run.MAXIMUM_POSTINGS_PER_RUN`) so that one request cannot
    #: rewrite a whole history synchronously, and the bound is safe precisely
    #: BECAUSE membership is the status: everything this run completed has left
    #: the candidate set, so running the same selector again continues where
    #: this one stopped, with no cursor to carry. Reported rather than silent —
    #: a truncation nobody is told about reads as "that was all of them".
    more_to_do = models.BooleanField(default=False)

    #: WHAT MAY HAPPEN TO THIS RECORD (ADR-0007 §2). Nothing, on every column,
    #: which is why none of them takes a class of its own: `RECORD_RULE` is the
    #: absence of a class said out loud, and the record's rule is stated in the
    #: docstring above and held by `pricing/migrations/0025`. A column-level
    #: `FROZEN` would be that one claim written sixteen times, and G19's walk
    #: would then require each column to be NAMED by the rule — which a blanket
    #: refusal deliberately does not do, because it refuses every update
    #: whatever it touched.
    transition_classes = {
        "id": RECORD_RULE,
        "created_at": RECORD_RULE,
        "updated_at": RECORD_RULE,
        "tenant": RECORD_RULE,
        "actor_kind": RECORD_RULE,
        "actor_id": RECORD_RULE,
        "actor_display": RECORD_RULE,
        "selected_from": RECORD_RULE,
        "selected_to": RECORD_RULE,
        "selected_customer": RECORD_RULE,
        "selected_event_type": RECORD_RULE,
        "postings_examined": RECORD_RULE,
        "costs_settled": RECORD_RULE,
        "prices_resolved": RECORD_RULE,
        "postings_left_unresolved": RECORD_RULE,
        "more_to_do": RECORD_RULE,
    }

    class Meta:
        db_table = "ubb_resolution_run"
        indexes = [
            models.Index(fields=["tenant", "created_at"],
                         name="idx_resolution_run_tenant"),
        ]

    def __str__(self):
        return (f"ResolutionRun({self.postings_examined} examined, "
                f"{self.costs_settled + self.prices_resolved} completed)")

    @property
    def selector(self):
        """The three axes as the caller stated them, for the ledger and the wire.

        One reader, so the entry in the governance ledger and the body the route
        answers cannot come to describe the same run differently.
        """
        return {
            "selected_from": (self.selected_from.isoformat()
                              if self.selected_from else None),
            "selected_to": (self.selected_to.isoformat()
                            if self.selected_to else None),
            "selected_customer_id": (str(self.selected_customer_id)
                                     if self.selected_customer_id else None),
            "selected_event_type": self.selected_event_type or None,
        }
