from django.db import models

from core.models import BaseModel
from core.transitions import FROZEN
from core.vocabulary import (
    OUTCOME_REASON_CUSTOMER_CANCELLED,
    OUTCOME_REASON_EXECUTION_FAILED,
    OUTCOME_REASON_INTERNAL_ERROR,
    OUTCOME_REASON_INVALID_INPUT,
    OUTCOME_REASON_PARENT_CLOSED,
    OUTCOME_REASON_SUPERSEDED,
    OUTCOME_REASON_TIMEOUT,
    OUTCOME_REASON_UNSPECIFIED,
    OUTCOME_REASON_UPSTREAM_PROVIDER_ERROR,
    PRICING_MODE_EVENT_PRICED,
    PRICING_MODE_FIXED,
    TASK_STATUS_ACTIVE,
    TASK_STATUS_CANCELLED,
    TASK_STATUS_COMPLETED,
    TASK_STATUS_EXPIRED,
    TASK_STATUS_FAILED,
    TASK_STATUS_KILLED,
    TASK_STATUS_VALUES,
    TASK_TYPE_KIND_SUBTASK,
    TASK_TYPE_KIND_TASK,
)


# THE DURABLE STATE, AND EACH VALUE IS TOLD APART BY WHO WROTE IT (#408).
#
# THE RULE BOTH VALUE SETS IN THIS MODULE ARE HELD UNDER (ADR-0008 §4): the
# identities come from the generated registry and only the WORDING is written
# here. A value set the registry owns is held by reference so the backend
# cannot keep a second copy of it that drifts, while the English beside each
# value is display text this model is free to spell.
#
#   active     running.
#   completed  THE TENANT DECLARED DELIVERY, and nothing else writes it (I1).
#              An explicit close is the only writer, which is what makes a
#              charge safe to key on it.
#   failed     the tenant declared the work could not be delivered.
#   cancelled  deliberately stopped or withdrawn — an explicit close saying so,
#              or a parent's close cascade over contained work the tenant
#              declared nothing about.
#   killed     UBB STOPPED IT ON A SPEND SIGNAL, and nothing tenant-declared
#              lands here (I2). A ceiling crossing, the patrol, or a parent's
#              kill cascade.
#   expired    nobody ever told UBB how it ended. Either sweeper.
#
# `cancelled` deliberately does NOT map onto `killed`, and that was considered
# and rejected: the kill path emits a terminal event and stamps an announcement
# id, so a tenant cancellation landing there would either fire a spurious spend
# event at the customer's workers or become the only `killed` row with no
# announcement — which means *silently cascaded by a parent*.
TASK_STATUS_CHOICES = [
    (TASK_STATUS_ACTIVE, "Active"),
    (TASK_STATUS_COMPLETED, "Completed"),
    (TASK_STATUS_FAILED, "Failed"),
    (TASK_STATUS_CANCELLED, "Cancelled"),
    (TASK_STATUS_KILLED, "Killed"),
    (TASK_STATUS_EXPIRED, "Expired"),
]

#: EVERY STATE BUT `active`, DERIVED RATHER THAN LISTED. Terminal to anything
#: is never permitted, and `active` is the only non-terminal state — which is
#: the registry's own summary of this concept, not a second rule stated here.
#: Deriving it is what makes that true of a seventh value on the day it is
#: declared, instead of on the day somebody remembers a list in this file.
TERMINAL_TASK_STATUSES = frozenset(TASK_STATUS_VALUES) - {TASK_STATUS_ACTIVE}

# WHICH ALTITUDE A DECLARED KIND OF WORK IS MEANT FOR, held under the same rule
# stated above the state set — by reference, wording only.
TASK_TYPE_KIND_CHOICES = [
    (TASK_TYPE_KIND_TASK, "Task"),
    (TASK_TYPE_KIND_SUBTASK, "Subtask"),
]

# HOW A KIND OF WORK IS SOLD (#414), held by reference under the same rule as
# the sets above — identities from the registry, wording here.
#
#   event_priced  every event is priced as it arrives, against the customer's
#                 resolved rules. This is what every revenue path in UBB has
#                 always done and it is the default below.
#   fixed         one agreed price for the whole delivered piece of work,
#                 REPLACING metered revenue for it. Not a fee on top and not a
#                 floor; the cost side is entirely unchanged (#139 §2).
#
# It is declared on the KIND of work rather than per unit because a price is
# quoted for a kind of thing, not negotiated per call — and a unit of work
# snapshots the answer at start, so no unit in flight can have its regime
# change underneath it.
PRICING_MODE_CHOICES = [
    (PRICING_MODE_EVENT_PRICED, "Event priced"),
    (PRICING_MODE_FIXED, "Fixed price"),
]

# WHY THE CALLER SAID IT DID NOT DELIVER (#409), held by reference under the
# same rule as the two sets above — identities from the registry, wording here.
#
# THIS IS NOT `reason_code`, AND THE TWO MUST NEVER BE TIDIED TOGETHER. That
# one answers why work was STOPPED, it is open, and it is UBB-PRODUCED —
# `apps/platform/work/reasons.py` is its consumer and slice 6 owns it. This one
# answers why the caller could not deliver, it is closed, and it is
# CALLER-SUPPLIED. `parent_closed` below and `reasons.PARENT_KILLED` are two
# concepts for two actors, not a near-miss: the first is what a tenant declares
# for contained work it withdrew when it closed the parent, the second is what
# UBB records when it cascaded a spend stop.
#
# ⚠ AND THE PRODUCER/CONSUMER RECONCILIATION IN `reasons.py` DOES NOT TRANSFER
# HERE. That module reconciles its own closed set with an open registry concept
# by ruling that closed binds UBB's producers while open binds consumers — which
# works only because a stop reason is UBB's own. This value arrives from
# outside, so an unrecognised one is REFUSED at the boundary rather than carried
# through it (spec §6).
OUTCOME_REASON_CHOICES = [
    (OUTCOME_REASON_UPSTREAM_PROVIDER_ERROR, "Upstream provider error"),
    (OUTCOME_REASON_TIMEOUT, "Timeout"),
    (OUTCOME_REASON_INVALID_INPUT, "Invalid input"),
    (OUTCOME_REASON_INTERNAL_ERROR, "Internal error"),
    (OUTCOME_REASON_EXECUTION_FAILED, "Execution failed"),
    (OUTCOME_REASON_CUSTOMER_CANCELLED, "Customer cancelled"),
    (OUTCOME_REASON_SUPERSEDED, "Superseded"),
    (OUTCOME_REASON_PARENT_CLOSED, "Parent closed"),
    (OUTCOME_REASON_UNSPECIFIED, "Unspecified"),
]


def _empty_list():
    return []


class TaskType(BaseModel):
    """The tenant's declared work vocabulary, carrying POLICY (design D7).

    Before this existed, a unit's COGS ceiling came from the per-call
    `provider_cost_limit_micros` or one tenant-wide default
    (RiskConfig.default_task_provider_cost_limit_micros) — so every kind of job
    shared one ceiling, and a job that legitimately costs 50x its sibling forced
    you to either cap both at the large number or let the client declare its own
    spending limit. The ceiling now belongs to the KIND of work, server-side: a
    start call may request lower, never higher.

    IT CARRIES HOW THE WORK IS SOLD AS WELL AS WHAT IT MAY SPEND (#414). Those
    are two different questions about the same declaration — one bounds COGS,
    the other decides whether the tenant's own customer is charged per event or
    one agreed number — and only the second one is frozen. See `pricing_mode`
    below and `transition_classes` beneath the fields.
    """
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE,
                               related_name="task_types")
    key = models.SlugField(max_length=64)
    # WHICH ALTITUDE THIS DECLARATION IS FOR, and it survives the collapse of
    # the unit's two type columns into one (#154 §3.1). A unit says WHAT kind
    # of work it is in one column and its parent link says which altitude it
    # is at; the declaration says which altitude its kind was MEANT for — so a
    # kind meant for contained work can be refused when it is declared rather
    # than when it is used. The uniqueness key below carries it, so one word
    # may name a kind of work at either altitude and the two are different
    # declarations with different policy.
    kind = models.CharField(max_length=8, choices=TASK_TYPE_KIND_CHOICES,
                            default=TASK_TYPE_KIND_TASK)
    # COGS-denominated, matching Task.provider_cost_limit_micros. NULL = fall
    # back to the RiskConfig tenant default, then to uncapped.
    default_provider_cost_limit_micros = models.BigIntegerField(null=True, blank=True)
    # HOW LONG THIS KIND OF WORK MAY GO QUIET (#412), the first rung of the
    # silence ladder — this declaration, then the tenant's own default, then
    # UBB's backstop. The docstring above makes the argument for the ceiling
    # and it is the same argument: one kind of job that legitimately runs
    # twenty minutes between reports should not force you to widen the window
    # for its sibling that reports every second.
    #
    # LIVENESS IS PROVED BY REPORTING USAGE AND BY NOTHING ELSE. There is no
    # keepalive call and no read extends a unit's life — an implicit keepalive
    # on reads was rejected outright, because a console listing, a support
    # query or an admin inspecting a stuck unit would silently resurrect it.
    #
    # NULL = this kind declares nothing, so the ladder falls through. 0 = this
    # kind declares that it has NO silence window, which is a real answer for
    # work that is legitimately quiet for hours; the absolute deadline below
    # still applies to it, so 0 here can never produce an immortal unit.
    silence_window_seconds = models.PositiveIntegerField(null=True, blank=True)
    # HOW LONG THIS KIND OF WORK MAY RUN AT ALL (#412), the first rung of the
    # absolute ladder, and it is measured from creation regardless of activity.
    #
    # ⚠ IT CANNOT BE SWITCHED OFF AT ANY RUNG, AND THE CONSTRAINT BELOW IS WHAT
    # MAKES THAT TRUE RATHER THAN CUSTOMARY. Dropping the absolute ceiling was
    # considered and rejected: it is the guard that stops any tenant getting an
    # immortal unit, and a tenant with no reaper of its own would otherwise have
    # stuck work living forever holding a concurrency slot and a prepaid
    # reservation. NULL falls through to the tenant default and then to UBB's
    # backstop; zero is refused, because a zero-length deadline and a disabled
    # one are the two readings a reader would have to choose between and only
    # one of them is a window.
    absolute_deadline_seconds = models.PositiveIntegerField(null=True, blank=True)
    # HOW THIS KIND OF WORK IS SOLD (#414), and the only column on this model
    # that never moves. See `PRICING_MODE_CHOICES` above for what the two words
    # mean; what follows is why the column is shaped this way.
    #
    # NOT NULL WITH A DEFAULT, because every declaration made before this column
    # existed was made when per-event was the only regime there was. NULL would
    # invent a third state — *nobody said* — for a question every existing row
    # has already answered, and a start would then have to guess which regime a
    # null meant at the moment it resolves a price.
    #
    # ⚠ DECLARED FROZEN, WHICH IS A DELIBERATE COST RATHER THAN A CONVENIENCE
    # (spec §10). Changing how a kind of work is sold means RETIRING it and
    # declaring a replacement, which leaves two rows each carrying its own
    # retirement instant — exactly the *when did this change, and to what* a
    # publish record answers, for free and without minting a third publish
    # mechanism beside the Pricing Book's and the Event Type's. Whether those
    # two are one mechanism generalised or genuinely two is still open (#156
    # §14.2), and shipping a third here would answer it by fiat.
    #
    # The accepted cost is stated rather than hidden: a tenant who mis-declares
    # has to create a new key, and a key change is an integration change for
    # them. The console says so beside the control at declaration time rather
    # than leaving them to discover it when a re-declaration is refused.
    pricing_mode = models.CharField(max_length=16, choices=PRICING_MODE_CHOICES,
                                    default=PRICING_MODE_EVENT_PRICED)
    # Declared grouping field keys a start call MUST supply for this kind of work.
    required_dimensions = models.JSONField(default=_empty_list, blank=True)
    # WHEN THIS KIND OF WORK STOPPED BEING OFFERED, or null while it is live.
    # Retire-never-delete (#138): a start naming a retired kind is refused, and
    # the row stays readable forever because the work already done under it
    # keeps referring to it. It is also the record the frozen column above
    # leans on — a regime change is a retirement plus a redeclaration, and this
    # is the half that says when.
    retired_at = models.DateTimeField(null=True, blank=True)

    #: WHAT MAY HAPPEN TO EACH DECLARED COLUMN (ADR-0007 §2). The rule that
    #: keeps it is a `BEFORE UPDATE` trigger on this table, installed by
    #: `work/migrations/0021`, because declaring is not enforcing and a
    #: model-level guard is the instrument this repository has already watched a
    #: production writer bypass by design.
    #:
    #: The three bounds beside it are deliberately NOT here. A ceiling, a
    #: silence window and an absolute deadline are operational settings a tenant
    #: revises as it learns what its work costs and how long it takes; freezing
    #: them would make the registry unusable and would say something false about
    #: how they are actually used. `Task`'s own columns are a separate piece of
    #: work with its own migration, recorded at `Task.outcome_reason`.
    transition_classes = {"pricing_mode": FROZEN}

    class Meta:
        db_table = "ubb_task_type"
        constraints = [
            models.UniqueConstraint(fields=["tenant", "kind", "key"],
                                    name="uq_task_type_key"),
            # The absolute deadline is either undeclared at this rung or a
            # real window. See the column: this is the rule that keeps "no
            # tenant gets an immortal unit" a property of the database rather
            # than of whichever code path last read the column.
            models.CheckConstraint(
                condition=models.Q(absolute_deadline_seconds__isnull=True)
                | models.Q(absolute_deadline_seconds__gt=0),
                name="ck_task_type_absolute_deadline_positive",
            ),
        ]

    def __str__(self):
        return f"TaskType({self.kind}:{self.key})"


class Task(BaseModel):
    """The registered unit of agent work — groups multiple Postings into a
    single logical workflow execution.

    Lives in platform because both metering (Posting FK) and billing
    (start-gate creation, cost tracking) need to reference it without
    cross-product imports.

    One-rule model: limits are signal points, never billing walls. A unit
    flips to a terminal state the moment its limit trips (the flip is the
    durable record that the stop signal fired), but late events still land,
    bill, and keep counting into both totals — a terminal state prevents the
    creation of a customer charge and never rejects genuine operational usage,
    including usage that arrives after termination.

    WHICH TERMINAL STATE IT FLIPS TO IS THE WHOLE POINT (#408). See
    `TASK_STATUS_CHOICES` above: the five terminal states are told apart by who
    wrote them, so `completed` answers *the tenant declared delivery* and
    `killed` answers *UBB stopped this on a spend signal*, each with no second
    meaning to filter out first.
    """

    tenant = models.ForeignKey(
        "tenants.Tenant", on_delete=models.CASCADE, related_name="tasks"
    )
    customer = models.ForeignKey(
        "customers.Customer", on_delete=models.CASCADE, related_name="tasks"
    )
    # Subtask containment (#38): a subtask IS a Task row with `parent` set —
    # one model, one containment level at launch (the parent must itself be
    # parentless; the generic self-FK makes deepening later a validation
    # change, not a remodel). Immutable after creation — a unit is never
    # re-parented, which is what lets accumulate read it without a lock.
    # Lock-ordering refinement (see core/locking.py): within Task, a
    # transaction that locks both a parent and its child locks the PARENT
    # first (rollup, cascade kill/close, and subtask registration all comply).
    parent = models.ForeignKey(
        "self", on_delete=models.CASCADE, null=True, blank=True,
        related_name="subtasks",
    )
    # THE KIND OF WORK THIS UNIT IS (design D7), at either altitude — ONE
    # column, and `parent` above is the only thing that says which altitude it
    # is at (#154 §3.1). There used to be a second column for a contained
    # unit, set exclusively with this one, so every read had to ask which of
    # the two was populated before it could ask anything useful; the two were
    # the same declaration twice over, and a contained unit is the same record
    # with a parent rather than a second thing.
    #
    # Immutable after creation for the same reason `parent` is: accumulate_cost
    # reads it without a lock, and a re-typed unit would retroactively change
    # what every already-settled event on it means. "" = untyped (a tenant who
    # never declared a vocabulary).
    task_type = models.CharField(max_length=64, blank=True, default="", db_index=True)
    # Task-scoped declared values (design D6), bound to slots by the tenant's
    # GroupingField registry and named for it since #276. Inherited by EVERY
    # event in this task's tree, including events on its subtasks, so a caller
    # sets them once per job instead of on every metered call. Immutable with
    # the task. Ten of them, matching the registry — a slot a tenant can
    # declare but not attribute at task scope would be a slot that works
    # differently depending on where its value came from.
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
    status = models.CharField(
        max_length=20,
        choices=TASK_STATUS_CHOICES,
        default=TASK_STATUS_ACTIVE,
        db_index=True,
    )
    # Both running totals, denominationally explicit, maintained on EVERY
    # accumulate — including events landing after a kill. Only the provider
    # total races provider_cost_limit_micros.
    total_billed_cost_micros = models.BigIntegerField(default=0)
    total_provider_cost_micros = models.BigIntegerField(default=0)
    event_count = models.IntegerField(default=0)
    # HOW MANY OF THOSE EVENTS THE PROVIDER TOTAL COULD NOT INCLUDE (#328).
    #
    # Non-zero makes the total above a FLOOR: this unit really cost at least
    # that much. `Posting.provider_cost_micros` is nullable and a null means UBB
    # has not resolved that cost (#317), so the accumulate primitive adds the
    # known part and increments this instead — the alternative, adding a zero,
    # would produce a unit total indistinguishable from a complete one, which is
    # the ambiguity the nullable column exists to remove.
    #
    # It is a COLUMN rather than something a reader derives, because this total
    # is written on every recording and never rebuilt: a cost that arrives
    # unresolved and is later settled elsewhere leaves no trace in a figure that
    # was only ever added to. The count is written in the same UPDATE as the
    # amount, so the pair cannot come apart.
    #
    # An event whose Event Type declares no supplier cost is NOT counted here.
    # Nothing about it is missing (#327), and a caveat that is always on is a
    # caveat nobody reads.
    unresolved_event_count = models.IntegerField(default=0)
    # HOW MANY OF THOSE EVENTS THE BILLED TOTAL COULD NOT INCLUDE (#351).
    #
    # The mirror of the count above, for the other side of the margin, and it is
    # a second column for the reason the two counts are two keys everywhere
    # else: they are about different events. A unit can hold a settled cost and
    # a price UBB could not resolve, and one number answering for both would let
    # either caveat vanish behind the other.
    #
    # Only `unknown` is counted. A `waived` price and a `not_applicable` one are
    # genuine zeroes rather than missing information — the same rule, and the
    # same argument against a caveat that is always on, as the cost half above.
    unpriced_event_count = models.IntegerField(default=0)

    # Signal-point snapshots — copied from the start call / tenant config at
    # task creation so a config change never affects an in-flight task.
    # Retained as forensics on the task record (what the wallet looked like
    # when the task started) even though the per-task floor check that used
    # to read it is gone — see reasons.py for why that check was deleted
    # rather than repaired. No code currently reads this field; do not add
    # a new floor comparison against it.
    balance_snapshot_micros = models.BigIntegerField()
    # COGS limit: measures what the job actually burns (provider cost),
    # never the tenant's markup policy.
    provider_cost_limit_micros = models.BigIntegerField(null=True, blank=True)

    # HOW THIS UNIT OF WORK IS SOLD, SNAPSHOTTED AT START (#415, spec §9).
    #
    # The same word `TaskType.pricing_mode` carries, at the other scope, and
    # the registry says the repetition is deliberate: they are one concept at
    # two scopes and the model name already supplies the scope. The
    # DECLARATION says how a kind of work is sold; this says how THIS unit was
    # sold, and it is a copy rather than a read for the reason
    # `balance_snapshot_micros` and `provider_cost_limit_micros` above are
    # copies — a configuration change must never reach work already running.
    #
    # It is why the frozen column one table over does not need a publish
    # record (spec §10): nothing in flight or historical can move, because the
    # answer is written down here at start.
    #
    # NOT NULL WITH A DEFAULT, matching the declaration's own column and for
    # the same reason: every unit of work registered before this existed was
    # registered when per-event was the only regime there was, so
    # `event_priced` is what those rows have always meant. A null would invent
    # a third state — *nobody said* — for a question every existing row has
    # already answered.
    pricing_mode = models.CharField(max_length=16, choices=PRICING_MODE_CHOICES,
                                    default=PRICING_MODE_EVENT_PRICED)
    # THE AGREED PRICE THIS UNIT OF WORK WAS QUOTED, PINNED AT START (#415,
    # #139 §2.3), resolved from a work-level line in the customer's own policy
    # book (`pricing.TaskPrice`).
    #
    # ⚠ **PINNED, WHICH IS WHY A PRICE CHANGE MID-JOB CANNOT MOVE IT.** A unit
    # of work spanning a reprice keeps the number it was quoted, while its
    # supplier costs float and resolve at each posting's own timestamp — *the
    # price was promised, the cost is observed.* So one unit of work's revenue
    # and its COGS resolve against DIFFERENT INSTANTS, which looks like a
    # defect to anyone reading a single receipt without this sentence. It is
    # said again at `apps/metering/pricing/receipts.py`, which is where a
    # reader of one receipt will actually be.
    #
    # ⚠ **DETERMINATION, NOT CHARGE.** This says which price applies; whether
    # it is owed at all is decided by how the work ends, and the canonical
    # record of a charge that really arose is the Charge (#416) — a different
    # lifetime, its own currency, and one-to-zero-or-one with this. A unit of
    # work that fails carries this number and is charged nothing.
    #
    # ⚠ **MARKUP NEVER APPLIES TO IT** (#139 §2.5). Markup is a function of
    # provider cost, so applying it here would yield "the agreed price plus a
    # percentage of this unit's COGS" — a price that moves with cost, which
    # destroys the premise. All four markup rungs are bypassed; the number
    # here is the line's own.
    #
    # NULL FOR EVERY UNIT OF WORK PRICED PER EVENT, which is the honest reading
    # rather than a gap: there is no agreed price for such a unit and a zero
    # would be a price of nothing. Non-null exactly where `pricing_mode` above
    # is `fixed`, because a start that could not resolve one is refused before
    # the row is written.
    agreed_price_micros = models.BigIntegerField(null=True, blank=True)
    # WHICH LINE ANSWERED, PINNED BESIDE THE NUMBER IT PRODUCED (#415, #139
    # §2.3).
    #
    # ⚠ **THE AMOUNT ALONE IS NOT A REPRODUCIBLE RECORD.** #139 §2.3 requires a
    # charge to name the matched line so that the amount is "reproducible from
    # the record rather than by re-resolving today's config", and re-resolving
    # is not a fallback available later: which books are even in play depends on
    # the customer's plan, which moves. So the identity of the line is captured
    # in the same write as the number, at the one instant both are known.
    #
    # A PLAIN UUID AND NOT A FOREIGN KEY, which is `billing_owner_id` and
    # `announce_outbox_id` above doing the same thing for the same reason. The
    # line is `apps.metering.pricing.TaskPrice` — a PRODUCT's table — and this
    # model is the KERNEL's; ADR-001 lets a product read the kernel and not the
    # other way round, so a database-level reference here would invert the one
    # dependency the golden rule is about. A reader joins from the product side.
    #
    # NULL wherever `agreed_price_micros` is null, and never independently: the
    # two are written together or not at all, which is what makes the pair a
    # record rather than two facts that can come apart.
    agreed_price_line_id = models.UUIDField(null=True, blank=True)
    # WHICH VERSION OF THE BOOK ANSWERED, PINNED IN THE SAME WRITE (#416, #139
    # §2.3).
    #
    # ⚠ **IT IS THE VERSION AT RESOLUTION, AND THAT IS THE WHOLE REASON IT IS A
    # COLUMN.** A Pricing Book's version counter steps on every publish
    # (`BookService.publish_declared`), so asking the book for it any later
    # answers *the version this book is at now* — a number with nothing to do
    # with the resolution it would be recording. The line's own
    # `Rate.book_version_from` is the nearest thing one table over and it does
    # not answer this either: it says which version OPENED that row, not which
    # version the customer's book stood at when the start gate read it.
    #
    # #416's Charge is required to carry *the resolved book version*, and this
    # is the one instant it is knowable. #415 pinned the amount and the line and
    # left this to the ticket that had a reader for it, which is that one.
    #
    # NULL WHEREVER THE OTHER TWO ARE NULL, and never independently — the
    # amount, the line and the version are ONE record of a resolution, which is
    # why the check below widened to three rather than a fourth rule joining the
    # table.
    agreed_price_book_version = models.PositiveIntegerField(null=True, blank=True)

    # Tier-2 (D4/I6): the billing owner PINNED at task creation
    # (resolve_billing_owner), exactly like Posting.billing_owner_id. The
    # concurrency-slot acquire/release and both reapers read this — they MUST
    # NOT re-resolve the owner (re-parenting would otherwise split the counter
    # or leak the slot). Nullable for back-compat with pre-Tier-2 rows.
    billing_owner_id = models.UUIDField(null=True, blank=True, db_index=True)
    # Tier-2 (D10): heartbeat for the stale-task reaper. Stamped on every
    # accumulate_cost. Null until the first metered event.
    last_event_at = models.DateTimeField(null=True, blank=True)
    # Announcement bookkeeping (delivery spec §B, #43): the OutboxEvent id of
    # this unit's stop announcement (task.limit_exceeded /
    # subtask.limit_exceeded), stamped inside the same transaction as the
    # winning flip + emission. Stays null on silent cascaded stops (the
    # parent's event is the one signal) and on the states a tenant declares
    # (nothing to announce — the tenant already knows). Plain UUID, not an FK —
    # outbox cleanup deletes terminally-successful rows and the stamp must
    # keep meaning "announced" (see apps.platform.events.announcements).
    #
    # ⚠ IT IS STAMPED ON `killed` AND ON `expired` ALIKE (#408). UBB announced
    # both before the six states existed and announces both after; what changed
    # is which state the announcement accompanies, not whether one is sent. The
    # event NAME still says `limit_exceeded` for an expiry, which is the debt
    # the terminal-event split pays — a ledgered debt this ticket neither
    # widens nor pretends to have paid.
    announce_outbox_id = models.UUIDField(null=True, blank=True)

    # WHY THE CALLER SAID IT DID NOT DELIVER, and the sentence beside it (#409).
    #
    # Written by the close that declared the terminal state, in the SAME UPDATE
    # as `status`, so a state and the explanation the caller gave for it can
    # never come apart. "" throughout means nobody gave one: on `completed`
    # because neither field is accepted beside a declared delivery, and on
    # `killed` / `expired` because no caller declared anything at all — those
    # two are UBB's own stops and record their reason under the OTHER concept
    # (`reasons.py`, still in `metadata`), which is the separation
    # `OUTCOME_REASON_CHOICES` above argues for.
    #
    # THE ONE OTHER WRITER IS A PARENT'S CLOSE CASCADE (#413), and it is the
    # same declaration one level down rather than a second kind of writer: the
    # tenant's close is what withdrew the contained work, and `parent_closed` is
    # the caller-supplied reason for exactly that. It is still the close that
    # wrote it.
    #
    # TWO COLUMNS RATHER THAN ONE, which is #140 §3.3's cardinality argument
    # made physical: the code is a small closed set a dashboard can group on,
    # and the sentence is the provider's actual message, which is display-only
    # and never grouped. Merging them would make every distinct provider string
    # its own bucket.
    #
    # ⚠ THE RULE IS SET_ONCE AND THIS MODEL DECLARES NO `transition_classes`,
    # WHICH IS A STATED GAP RATHER THAN AN ANSWER. What is allowed to happen to
    # these two is exactly what the paragraph above says — written once, when
    # the row enters its terminal state, and never again. `reason_detail` has
    # exactly one writer, the close; `outcome_reason` has two, the close and a
    # parent's close cascade, and both are held to write-once by the same rule
    # from different directions: the guard in `TaskService._flip` refuses a
    # second transition, and the cascade beside it selects only work still
    # running, so a row it can reach is by construction one never written.
    # `docs/conventions/django-patterns.md` asks a model holding economic
    # facts to say that per column in a `transition_classes` mapping, and THIS
    # model has never had one: `status`, `parent` and `task_type` all carry
    # their rule in prose here too, and #407 and #408 each shipped a column
    # under the same gap. `TaskType` above now declares one, which narrows the
    # gap to this model rather than closing it.
    #
    # It is NOT declared here, and the reason is that declaring is not
    # enforcing. A column named into a database-defended class owes a trigger
    # on `ubb_task` and a behavioural test per class through all three doors —
    # `save()`, `QuerySet.update()` and raw SQL — which is the shape #318 built
    # for the posting and #414 built one table over, on `ubb_task_type`, in this
    # same app. Declaring these two without it would put a false statement into
    # the module whose whole subject is that declarations are true, and
    # declaring the model's OTHER columns is a separate piece of work with its
    # own migration. Whichever ticket installs that trigger should take all of
    # them together; this comment is here so the next reader finds a decision
    # rather than an omission.
    #
    # ⚠ THIS TABLE DOES CARRY A RULE NOW (#415), AND IT IS NOT ONE OF THESE.
    # `work/migrations/0022` installs a `BEFORE INSERT` trigger holding
    # contained work to the pricing regime of the work containing it — a
    # cross-row rule about who may be BORN, which no `CHECK` can express
    # because it reads two rows. It is declared into no transition class and
    # discharges none of the gap above: a mutability class is a statement
    # about what may happen to a column AFTER insert, and that trigger never
    # fires on one. What it does change is the cost of paying this debt — the
    # `ubb_task` trigger the paragraph above asks for now has a sibling on the
    # same table, so whoever writes it must address triggers BY NAME and
    # assert the table's rules as an exact SET rather than indexing into
    # `pg_trigger`, which promises no order.
    outcome_reason = models.CharField(max_length=32, blank=True, default="",
                                      choices=OUTCOME_REASON_CHOICES)
    reason_detail = models.TextField(blank=True, default="")

    metadata = models.JSONField(default=dict)

    # THE CALLER'S KEY FOR ONE ATTEMPT, CLAIMED PERMANENTLY (#410).
    #
    # TWO FIELDS, TWO JOBS, and this is the identity one. `external_task_id`
    # below stays the caller's free-text JOB LABEL — reusable across attempts,
    # not unique, not required — and promoting that label to the key was
    # rejected: the label is the only place the relationship BETWEEN attempts
    # can live, so if the label were the identity then attempt 2 would have to
    # be called something else and nothing would tie the attempts together in
    # the tenant's own reporting.
    #
    # THE CLAIM NEVER LAPSES. No release when the unit reaches a terminal
    # state, no expiry window. Releasing at terminal was rejected on the case
    # that matters and only on that case: attempt 1 delivers, its response is
    # lost, the retry arrives, and a released key starts a SECOND unit of work
    # that is charged a second time. A permanent claim answers that retry with
    # the unit it already started, for as long as the row exists.
    #
    # ⚠ NULLABLE, WITH THE UNIQUENESS PARTIAL — the top-up's exact shape
    # (`WalletTransaction.idempotency_key`), and required at the API boundary
    # rather than by the column. Two reasons, both about rows this column
    # cannot speak for: every unit of work that predates it was registered
    # without one, and there is no caller-supplied value to invent for them
    # that would not be a fabricated declaration; and a NULL is the honest
    # record of *nobody claimed a key here* in a way `""` is not, because ""
    # is a value and would collide every such row against every other. What
    # makes the key REQUIRED is that the one route which registers a unit of
    # work refuses a request without one — a rule about what a caller may ask
    # for, which is where it belongs.
    idempotency_key = models.CharField(max_length=500, null=True, blank=True)

    external_task_id = models.CharField(max_length=255, blank=True, default="")
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "ubb_task"
        constraints = [
            # THE KEY'S CLAIM, ENFORCED WHERE IT CANNOT BE ROUTED AROUND.
            #
            # (tenant, customer, key) is the POSTING'S OWN SCOPE
            # (`uq_usage_event_idempotency_v2`), on the same argument: both are
            # a caller reporting that something happened FOR A NAMED CUSTOMER,
            # and two of a tenant's customers may each run a `nightly-batch`.
            # Scoping it to the tenant alone would make one customer's key
            # collide with another's and hand back the wrong customer's work.
            #
            # The start gate reads this claim before it does anything else and
            # answers a repeat itself, so the constraint is not what a caller
            # normally meets. It is what holds when two identical starts race:
            # both probe, both find nothing, and exactly one INSERT survives.
            models.UniqueConstraint(
                fields=["tenant", "customer", "idempotency_key"],
                condition=models.Q(idempotency_key__isnull=False),
                name="uq_task_idempotency_key",
            ),
            # WHOLE UNITS OF WORK ONLY, AT THE TABLE (#415, #139 §3.3).
            #
            # An agreed price belongs to a whole unit of work sold that way and
            # to nothing else. Two rows could otherwise carry one: a unit
            # priced per event, where the number would contradict its own
            # regime; and CONTAINED work, where a fan of prices nobody asserted
            # would be born every time a parent's close cascades over its
            # children — the auto-charge failure #139 §3.1 exists to refuse.
            # The parent is already the whole-job altitude and rollup is
            # unconditional, so a step's price would be revenue counted at a
            # level nothing reports at.
            #
            # ⚠ IT IS ONE DIRECTION AND ONLY ONE, which is the difference
            # between a rule and a claim. *A price implies a whole fixed unit*
            # is a property of one row and a check can hold it. The converse —
            # *every whole fixed unit carries a price* — is NOT expressible
            # here and is not true either: contained work under a fixed parent
            # is `fixed` too, by the equality rule the insert trigger holds,
            # and carries no price of its own. What makes a whole fixed unit
            # of work carry one is the start gate refusing to register it
            # otherwise, which is a rule about who may be born and lives in
            # `work/migrations/0022`'s trigger and in the start gate above it.
            models.CheckConstraint(
                condition=(models.Q(agreed_price_micros__isnull=True)
                           | models.Q(pricing_mode=PRICING_MODE_FIXED,
                                      parent__isnull=True)),
                name="ck_task_agreed_price_only_on_a_whole_fixed_unit",
            ),
            # A PRICE IS NOT NEGATIVE, the twin of the line's own check
            # (`pricing.TaskPrice`). Zero is a price — a tenant may agree to
            # deliver a kind of work for nothing — and a number below it is a
            # sign error rather than a deal.
            models.CheckConstraint(
                condition=(models.Q(agreed_price_micros__isnull=True)
                           | models.Q(agreed_price_micros__gte=0)),
                name="ck_task_agreed_price_not_negative",
            ),
            # AN AMOUNT, THE LINE THAT PRODUCED IT AND THE BOOK VERSION THAT
            # HELD THAT LINE MOVE TOGETHER OR NOT AT ALL — the amount/status-pair
            # shape `core.amount_status_pairs` names for the posting, one
            # concept along, at three columns rather than two. A number with no
            # line cannot be reproduced from the record, which is the whole of
            # what #139 §2.3 asks for; a line with no number would say a price
            # was resolved and record none of it; and a resolution with no
            # version cannot say which published state of the book answered.
            #
            # ⚠ IT WIDENED RATHER THAN GAINING A NEIGHBOUR (#416). A fourth
            # rule on this table would let one row break two at once and make
            # every existing refusal assertion here suspect — which is exactly
            # what the THIRD one cost #415, four cases at a stroke. These three
            # columns are one record of one resolution, so one rule is also the
            # truer statement.
            models.CheckConstraint(
                condition=(models.Q(agreed_price_micros__isnull=True,
                                    agreed_price_line_id__isnull=True,
                                    agreed_price_book_version__isnull=True)
                           | models.Q(agreed_price_micros__isnull=False,
                                      agreed_price_line_id__isnull=False,
                                      agreed_price_book_version__isnull=False)),
                name="ck_task_agreed_price_and_its_provenance_move_together",
            ),
        ]
        indexes = [
            models.Index(
                fields=["customer", "-created_at"],
                name="idx_task_customer_created",
            ),
            models.Index(
                fields=["tenant", "status"],
                name="idx_task_tenant_status",
            ),
            # Tier-2 (D10): the reaper scans active tasks by heartbeat staleness.
            models.Index(
                fields=["status", "last_event_at"],
                name="idx_task_status_heartbeat",
            ),
            # Tier-2 (P5): the concurrency cap counts active tasks per owner.
            models.Index(
                fields=["billing_owner_id", "status"],
                name="idx_task_owner_status",
            ),
            # #44 (delivery spec §C.4): the patrol's task sweep scans active
            # LIMITED tasks per tenant every hour — the partial index keeps
            # that scan proportional to the small set of tasks that can still
            # cross, never to tenant history.
            models.Index(
                fields=["tenant"],
                condition=models.Q(status=TASK_STATUS_ACTIVE,
                                   provider_cost_limit_micros__isnull=False),
                name="idx_task_active_limited",
            ),
            # Unit-economics rollup (design D7): mean/p95 cost per KIND of job.
            models.Index(fields=["tenant", "task_type", "-created_at"],
                         name="idx_task_type_created"),
        ]

    def __str__(self):
        return (f"Task({self.id}: {self.status}, "
                f"billed={self.total_billed_cost_micros}, "
                f"provider={self.total_provider_cost_micros})")

    def save(self, *args, **kwargs):
        """Guard the immutable declared kind (D7/D8) — ONE guard, because
        there is one column, at whichever altitude the row sits.

        `_loaded_task_type` is stamped either by `from_db` (a row read back
        from the database) or, right below, immediately after this instance's
        own first INSERT — so the very object returned by `.create()` also
        arms the guard for its next in-memory `.save()`, with no refetch
        required. A freshly constructed, never-yet-saved instance has no
        `_loaded_task_type` and skips the check on that first save.
        """
        was_adding = self._state.adding
        if not was_adding and hasattr(self, "_loaded_task_type"):
            was = self._loaded_task_type
            if self.task_type != was:
                raise ValueError(
                    f"task_type is immutable: {was!r} -> {self.task_type!r}")
        super().save(*args, **kwargs)
        if was_adding:
            self._loaded_task_type = self.task_type

    @classmethod
    def from_db(cls, db, field_names, values):
        instance = super().from_db(db, field_names, values)
        if "task_type" in field_names:
            instance._loaded_task_type = instance.task_type
        return instance
