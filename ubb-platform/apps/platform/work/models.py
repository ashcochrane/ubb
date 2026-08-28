from django.db import models

from core.models import BaseModel
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
    # Declared grouping field keys a start call MUST supply for this kind of work.
    required_dimensions = models.JSONField(default=_empty_list, blank=True)
    retired_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "ubb_task_type"
        constraints = [
            models.UniqueConstraint(fields=["tenant", "kind", "key"],
                                    name="uq_task_type_key"),
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
    # TWO COLUMNS RATHER THAN ONE, which is #140 §3.3's cardinality argument
    # made physical: the code is a small closed set a dashboard can group on,
    # and the sentence is the provider's actual message, which is display-only
    # and never grouped. Merging them would make every distinct provider string
    # its own bucket.
    outcome_reason = models.CharField(max_length=32, blank=True, default="",
                                      choices=OUTCOME_REASON_CHOICES)
    reason_detail = models.TextField(blank=True, default="")

    metadata = models.JSONField(default=dict)
    external_task_id = models.CharField(max_length=255, blank=True, default="")
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "ubb_task"
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
