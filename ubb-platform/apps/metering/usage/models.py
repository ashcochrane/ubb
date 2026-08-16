from django.contrib.postgres.indexes import GinIndex
from django.db import models
from django.utils import timezone

from core.models import BaseModel
from core.transitions import FROZEN, RECORD_RULE, RESOLVE_ONCE
from core.vocabulary import (
    COSTING_STATUS_KNOWN,
    COSTING_STATUS_NOT_APPLICABLE,
    COSTING_STATUS_UNRESOLVED,
    COSTING_STATUS_VALUES,
    UNRESOLVED_REASON_VALUES,
)


# The two closed sets this model stores, DERIVED from the registry rather than
# restated beside it. `choices=` is Django's own declaration that a column has a
# closed value set, and it is worth having — it reaches forms, the admin and
# `full_clean` — but a hand-typed list is the shape the migration ledger
# recorded as a debt against this file until #317 deleted the entry: correct on
# the day it is written and silently wrong the day `domain-vocabulary/` moves.
# Built from the imported frozensets, it cannot be wrong on any day.
#
# The label is the token. Django's second element is not a translation hook, and
# ADR-0008 §4 puts every human-facing word in the console's locale catalogue
# keyed off the concept's `label_key_prefix`. English authored here would be a
# wording nobody can reach and one more copy to keep in step.
COSTING_STATUS_CHOICES = [(value, value) for value in sorted(COSTING_STATUS_VALUES)]
UNRESOLVED_REASON_CHOICES = [(value, value)
                             for value in sorted(UNRESOLVED_REASON_VALUES)]


class Posting(BaseModel):
    """One economic posting — the row that says work was billed for.

    Renamed from the usage-event noun in #269 (slice 2), with its table, so the
    database stops preserving obsolete terminology (ADR-0006 §9, gate G9). The
    record of WHAT WAS MEASURED split off into a child of its own in #270; this
    row keeps the money, the attribution and the identity.

    **IT NO LONGER CLAIMS TO BE IMMUTABLE AS A WHOLE**, and the word was dropped
    in #317 rather than left to age. ADR-0007 §2 refuses a record-level claim of
    immutability precisely because it hides which columns are actually
    protected, and its Context names the failure this docstring was heading for:
    a docstring asserting that the first door made the row immutable, while
    another door wrote to it.

    **What is true instead is written per column in `transition_classes`
    below**, and the database keeps it (#318). A supplier cost settles exactly
    once — `unresolved` to `known`, amount and status together — through the one
    function that performs that statement, and every other move on those columns
    is refused by a trigger no door can go around. `save()` and `delete()` still
    refuse the writers that come through them, which is not the same thing and
    is not the enforcement: it is a local convenience, and ADR-0007 §2 is
    explicit about the difference.
    """
    tenant = models.ForeignKey(
        "tenants.Tenant", on_delete=models.CASCADE, related_name="postings"
    )
    customer = models.ForeignKey(
        "customers.Customer", on_delete=models.CASCADE, related_name="postings"
    )
    request_id = models.CharField(max_length=255, db_index=True)
    idempotency_key = models.CharField(max_length=500, db_index=True)
    balance_after_micros = models.BigIntegerField(null=True, blank=True)
    # THE ONE OPEN BAG. Caller-supplied, free-form, unbounded and undeclared:
    # FILTERABLE AND READABLE, NEVER GROUPABLE. A second bag folded into this
    # one in #273 (slice 2) and its name went with it, because that name
    # advertised the one capability this bag deliberately does not have —
    # an unbounded free-text keyspace that can become a chart is an unbounded
    # free-text keyspace that can drive an invoice line label. Anything you
    # want to slice or price on is a declared GroupingField.
    #
    # The keys in here are the tenant's own. UBB stores and returns them
    # exactly as they were authored and never reshapes them into English
    # nobody chose — see `migrations/0033_the_second_open_bag_folds.py`.
    metadata = models.JSONField(default=dict)

    # Pricing breakdown (populated when platform prices the event)
    #
    # The nameless inline quantity that used to sit here died in #272 — one
    # integer per posting could only ever describe one thing, which is what made
    # an event carrying both an input and an output amount inexpressible. What
    # is measured lives on the child record, keyed by a declared measurement.
    # The argument for dropping it rather than moving it is in
    # `migrations/0032_the_inline_unit_total_dies.py`.
    #
    # CUR-1: lowercase, matching the seven other currency columns and the
    # payment rail's own casing (#269, spec §K2). No CHECK constraint —
    # see the module note in `tests/test_posting_rename.py` for why the one
    # slice 2 was handed cannot be written truthfully today.
    currency = models.CharField(max_length=3, default="usd")
    # --- The fourteen selector columns (design D2/D3) ---
    # One vocabulary for analytics grouping AND rate selection. Four reserved
    # keys plus ten tenant slots bound by the GroupingField registry. "" means
    # "not set" on an event and "matches anything" on a Rate; specificity =
    # the count of non-empty selectors.
    event_type = models.CharField(max_length=100, blank=True, default="", db_index=True)
    # Indexed: /analytics/usage groups by provider unconditionally on every call.
    provider = models.CharField(max_length=100, blank=True, default="", db_index=True)
    # Inherited from the event's task chain, never sent by the caller (D6).
    task_type = models.CharField(max_length=64, blank=True, default="", db_index=True)
    subtask_type = models.CharField(max_length=64, blank=True, default="", db_index=True)
    # THE TEN TENANT SLOTS, AND NOT ONE OF THEM CARRIES AN INDEX (#276).
    #
    # Six of these used to be individually indexed, on top of a composite that
    # led with two of them — seven index writes per row on the hottest insert
    # path in the system. Widening to ten under that arrangement would have
    # taxed every insert for capacity nobody is using yet, which is why the
    # widening and this cleanup are one change and not two.
    #
    # The per-column indexes went because a cardinality-capped column is around
    # one percent selective, at which the planner reaches for a sequential scan
    # or a composite anyway. The composite went for a sharper reason: NO QUERY
    # SELECTS ROWS BY A SLOT. Every read of one is a `GROUP BY` of a single slot
    # inside a tenant (sometimes a customer) and an `effective_at` window —
    # `apps.metering.queries.get_dimensional_margin`, `get_usage_timeseries`,
    # `get_customer_billed_breakdown`, and the `/analytics/usage` breakdowns.
    # The single predicate on a slot in the tree is `get_dimensional_margin`'s
    # `.exclude(<slot>="")`, a negation on a column whose commonest value is ""
    # — which no btree index would serve. So the columns that select the rows
    # are `tenant`/`customer` and `effective_at`, and those are exactly what
    # `idx_usage_tenant_effective` and `idx_usage_customer_effective` lead with.
    # A composite led by two slots could only ever be scanned whole, and "the
    # first two of ten" is arbitrary in a way "the first two of six" merely
    # looked like it wasn't.
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
    # WHAT THE SUPPLIER CHARGED, AND WHETHER UBB KNOWS IT YET (#317).
    #
    # Nullable, and `NULL` means NOT RESOLVED. Zero keeps a meaning of its own —
    # resolved, and it was exactly nothing. Until this column could be null
    # there was no way to say the first thing, so a charge UBB had not learned
    # about was stored as the same number as a call that cost nothing, and every
    # total over it was wrong in the direction that looks healthy: margin better
    # than it is, spend lower than it is (ADR-0007 §2).
    #
    # The two readings are kept apart BY THE DATABASE — `Meta` below refuses
    # every combination outside the three legal ones — because a rule that only
    # `full_clean` holds is a rule the writers that skip validation do not keep,
    # and most of what writes here skips it.
    #
    # ⚠ SQL's aggregates skip NULL, so a bare `Sum` over this column answers a
    # number that looks complete and is not. Every total built on it is
    # therefore a pair — the resolved sum and `unresolved_event_count` beside
    # it, built together by `core.cost_totals` (#327) and carried through
    # metering, platform, billing, subscriptions and referrals (#328). `or 0`
    # was never the local fix, because `or 0` reproduces exactly the ambiguity
    # this column stopped having.
    #
    # ⚠ AND A NULL HERE IS NOT ONE FACT. `costing_status` below says whether it
    # means "not learned yet" or "there is none", and only the first is counted
    # as excluded — every reader that adds these up takes both columns.
    provider_cost_micros = models.BigIntegerField(null=True, blank=True, default=0)
    # WHETHER THAT COST IS SETTLED. Not nullable: `unresolved` is a status, and a
    # null one would be a fourth state meaning "nobody said" — the ambiguity
    # this column exists to remove, moved one place to the left.
    #
    # It sits HERE, on the economic posting, beside the amount it qualifies, and
    # not on the child measurement record: the status is a statement about the
    # posting, and resolving a cost has to move the status and the amount in one
    # `UPDATE`, which a cross-table pair cannot do.
    #
    # The default is `known`, which is the same reading the migration gives every
    # row that already existed and for the same reason: a writer that says
    # nothing about supplier cost has recorded what UBB actually holds, and
    # inventing an unknown it never observed would make every period partial.
    # The writers that produce `unresolved` are the ones that learn a cost is
    # missing, and they are built by the tickets that follow this one.
    costing_status = models.CharField(
        max_length=32, choices=COSTING_STATUS_CHOICES,
        default=COSTING_STATUS_KNOWN)
    # WHICH INPUT DID NOT ARRIVE. Read only where the status is `unresolved`,
    # and never on its own: a status that says a cost is missing without saying
    # what would settle it is a shrug rather than something a tenant can act on.
    unresolved_reason = models.CharField(
        max_length=32, choices=UNRESOLVED_REASON_CHOICES, null=True, blank=True)
    # WHAT THE CALLER BELIEVES THE CALL COST, WHICH IS NEVER COGS. A separate
    # column rather than a second meaning for the one above: a field whose sense
    # flips with an Event Type's costing declaration is retroactive — change the
    # declaration and every historical row changes meaning. Accepted anywhere,
    # never summed into cost, and unconstrained by the rule below, because a
    # supplier who has not billed yet and a caller who has an opinion are the
    # ordinary state of a call rather than a contradiction.
    claimed_provider_cost_micros = models.BigIntegerField(null=True, blank=True)
    billed_cost_micros = models.BigIntegerField(default=0)
    pricing_provenance = models.JSONField(default=dict, blank=True)
    # The exact unit of work this event belongs to. The ONLY unit attribution
    # — the open bag above is free-form labelling and never silently becomes a
    # limited thing (no label-fallback inference).
    task = models.ForeignKey(
        "work.Task", on_delete=models.CASCADE, related_name="postings",
        null=True, blank=True,
    )
    # When the usage economically HAPPENED (caller-suppliable, bounded by
    # Tenant.backfill_window_days). created_at (BaseModel) is when it ARRIVED;
    # arrival-basis consumers (drawdown repair, platform fee) window on that.
    effective_at = models.DateTimeField(default=timezone.now, db_index=True)
    billing_owner_id = models.UUIDField(null=True, blank=True, db_index=True)
    # Past-limit stop context (#41, spec §H). SYSTEM-owned — never set from
    # the tenant's own open bag; written once at record (sync) / settle
    # (async) inside the recording transaction, immutable with the event.
    # Null = the event landed past nothing. Non-null = a JSON ARRAY of
    # contexts (an event crossing several limits simultaneously carries one
    # entry per limit), each:
    #   {"limit": task_limit|subtask_limit|customer_wide_stop|suspended|
    #             task_not_active,
    #    "stop_scope": task|subtask|customer,
    #    "tripped_at": ISO8601|null, "episode_seq": int|null (customer only),
    #    "task_id": uuid|null, "subtask_id": uuid|null,
    #    "arrived_after": bool — false on the tipping event only}
    # Built by services/stop_context.py; queried by JSONB containment (the
    # partial GIN index below carries the past-limit report + filters).
    stop_context = models.JSONField(null=True, blank=True)

    #: WHAT MAY HAPPEN TO THE COST COLUMNS, AND WHO KEEPS IT (ADR-0007 §2, #318).
    #:
    #: The amount and its status are ONE declaration written twice: they are
    #: `RESOLVE_ONCE` **as a pair**, and the only statement that may move either
    #: is the settlement in `pricing/services/cost_settlement.py`, which moves
    #: both at once and clears the reason with them. Declaring them separately
    #: would admit a row that had settled its amount and not said so.
    #:
    #: `unresolved_reason` carries no class of its own on purpose. It has no
    #: lifecycle apart from the status it qualifies — it is written once with an
    #: `unresolved` posting and cleared by the settlement that resolves it — so
    #: a class here would be a second, weaker statement of the pair's rule. What
    #: keeps it is the same trigger, which refuses to see it move on any other
    #: statement.
    #:
    #: **The enforcement is the trigger installed by `migrations/0037`, not the
    #: `save()` below.** `save()` refuses updates for the writers that go
    #: through it, and that is a convenience rather than the rule: ADR-0007 §2
    #: is explicit that a model-level guard is not enforcement, and names this
    #: repository as the place that already shipped one a production writer
    #: bypassed by design. Every declaration here is held across `save()`,
    #: `QuerySet.update()` and raw SQL alike, and
    #: `apps/platform/tests/test_transition_class_declarations.py` is what says
    #: no column may be declared here without that being true of it.
    transition_classes = {
        "provider_cost_micros": RESOLVE_ONCE,
        "costing_status": RESOLVE_ONCE,
        "claimed_provider_cost_micros": FROZEN,
    }

    class Meta:
        db_table = "ubb_posting"
        # The constraint and index names below still spell the retired noun,
        # deliberately and for the same reason #259 left its own alone: there is
        # no rename operation for a constraint or a Postgres-named index that
        # Django will emit — it can only drop and re-create, which is the
        # add-plus-remove ADR-0007 §1 refuses, on a unique index that is
        # load-bearing while it is gone. ADR-0006 §9's rule is about the TABLE
        # name, and this table now tracks its model.
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "customer", "idempotency_key"],
                name="uq_usage_event_idempotency_v2",
            ),
            # The two closed sets, at the database. The shape is the value-set
            # check slice 2 put on the Event Type's costing declaration: a
            # closed concept that only `clean()` defends is open to anything
            # that writes without validating, which is most of what writes.
            models.CheckConstraint(
                condition=models.Q(
                    costing_status__in=sorted(COSTING_STATUS_VALUES)),
                name="ck_posting_costing_status",
            ),
            models.CheckConstraint(
                condition=(models.Q(unresolved_reason__isnull=True)
                           | models.Q(unresolved_reason__in=sorted(
                               UNRESOLVED_REASON_VALUES))),
                name="ck_posting_unresolved_reason",
            ),
            # THE THREE LEGAL COMBINATIONS, AND THERE ARE ONLY THREE:
            #
            #   known           →  amount IS NOT NULL  and  reason IS NULL
            #   unresolved      →  amount IS NULL      and  reason IS NOT NULL
            #   not_applicable  →  amount IS NULL      and  reason IS NULL
            #
            # This is what makes NULL and 0 stay distinguishable at the
            # database rather than by convention: a row cannot claim to be
            # costed and carry no amount, and cannot claim not to be and carry
            # one. The status column's own value set is checked above rather
            # than left implied by this disjunction, so that a row failing
            # because it named a status nobody declared fails for a different
            # constraint than one failing because its three columns disagree.
            models.CheckConstraint(
                condition=(
                    models.Q(costing_status=COSTING_STATUS_KNOWN,
                             provider_cost_micros__isnull=False,
                             unresolved_reason__isnull=True)
                    | models.Q(costing_status=COSTING_STATUS_UNRESOLVED,
                               provider_cost_micros__isnull=True,
                               unresolved_reason__isnull=False)
                    | models.Q(costing_status=COSTING_STATUS_NOT_APPLICABLE,
                               provider_cost_micros__isnull=True,
                               unresolved_reason__isnull=True)
                ),
                name="ck_posting_costing_status_agrees_with_the_cost",
            ),
        ]
        indexes = [
            models.Index(fields=["customer", "-effective_at"], name="idx_usage_customer_effective"),
            models.Index(fields=["tenant", "-effective_at"], name="idx_usage_tenant_effective"),
            models.Index(fields=["tenant", "task_type", "subtask_type", "-effective_at"],
                         name="idx_usage_work_attribution"),
            # Arrival-basis scans (drawdown repair, platform-fee reconcile).
            models.Index(fields=["tenant", "created_at"], name="idx_usage_tenant_created"),
            # Past-limit report + query filters (#41): JSONB containment on
            # the stop-context array. Partial — a marked posting is the rare
            # exception, so the index stays tiny and unmarked inserts pay
            # nothing.
            GinIndex(fields=["stop_context"], name="idx_usage_stop_context",
                     condition=models.Q(stop_context__isnull=False)),
            # The open bag's filtering index (#273). Default `jsonb_ops`, not
            # `jsonb_path_ops`: it serves the key-exists operator (`?`) that
            # `__has_key` compiles to as well as the containment operator (`@>`)
            # that `__contains` does, and both are live call sites. 0022 is the
            # argument in full — it moved the retiring bag's index to this
            # opclass for these same lookups.
            GinIndex(fields=["metadata"], name="idx_posting_metadata"),
        ]
        ordering = ["-effective_at"]

    def __str__(self):
        return f"Posting({self.request_id}: {self.billed_cost_micros})"

    @property
    def measurements(self):
        """The measured quantities, read from the measurement record (#270).

        Named for the declarations its keys are keys into (#274) — the same word
        the Event Type's own declarations carry, because a quantity is costable
        exactly when one of them matches it. Nothing about that matching moved
        with the name: an unmatched key still contributes nothing, and making
        that visible is slice 3's.

        **This is not a column.** It was one until the split, and every reader
        that used to read the column reads this instead — which is how the move
        is provable to have cost no reader anything. There is exactly one
        encoding of the quantities and it lives on the child; ADR-0006 §4 is why
        this may be *served* read-only and may never be written back.

        It is read-only on purpose: a writer that tries to set it fails loudly
        rather than filling a column that is no longer there.

        An absent child answers ``{}``, which is what every reader saw before
        the split, when a posting with no measurements stored an empty bag. That
        is deliberately still indistinguishable from a pruned one *here* —
        making the difference visible is the next ticket's whole subject, and it
        does it on the contract with a derived status rather than by teaching
        this accessor to lie in a second way.
        """
        try:
            return self.measurement.measurements
        except PostingMeasurement.DoesNotExist:
            return {}

    def save(self, *args, **kwargs):
        # NOT THE ENFORCEMENT — see `transition_classes` above. This door is
        # shut because nothing that goes through it has any business rewriting
        # a posting, and the message says which door is open instead rather
        # than repeating the record-level immutability claim ADR-0007 §2
        # refuses: a supplier cost does settle later, exactly once.
        if not self._state.adding:
            raise ValueError(
                "A posting is not updated through save(). A supplier cost "
                "settles through pricing.services.cost_settlement, once.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("Posting records are immutable and cannot be deleted.")


class PostingMeasurement(BaseModel):
    """What was measured on a posting — the detail that may legitimately expire.

    Singular, per this repository's convention and per the originating
    decision's own recommendation: a posting has *a* measurement, not a set of
    them. One-to-one with its parent, keyed by a unique posting reference, and
    its table tracks its model name (ADR-0006 §9).

    **Why it is a record and not four more columns on the posting.** Two merged
    decisions each published a retention promise and they disagree by years: a
    Pricing Receipt is kept six years, and bulky measurement detail prunes at a
    shorter horizon so that "the money stays explicable after the measurements
    expire". As one row, honouring both means a housekeeping job runs ``UPDATE``
    against the durable economic record to blank a column — a scheduled
    destructive write to the highest-volume six-year table in the system. As two
    rows it is a ``DELETE`` from here, and **the posting is never written to at
    all**. Retention is the load-bearing reason and it is the only one.

    **Absence is expressed by absence.** Where a posting is a synthetic charge —
    a Task sold at one agreed price — this record does not exist. Not an empty
    record, not a record of zeroes: *"this avoids manufacturing an empty
    measurement record merely so a task charge can possess an ID"*. Nothing
    here defaults a child into being, and no code path creates one except the
    metered recording path.

    **The transition classes below are declared, not enforced.** ADR-0007 §2
    requires every column to state what is allowed to happen to it; what this
    record states is that *no column of it states anything on its own*, because
    it has no per-column lifecycle to describe. The record's rule is::

        INSERT   once, in the same transaction as its posting
        UPDATE   never — no column of a measurement record is ever rewritten
        DELETE   permitted only at or after prunable_at, and only while the
                 parent posting is not unresolved

    Enforcing that at the database is **not** gate G19, which slice 3 installed.
    G19's statement covers *field* transition classes, and **no column here is
    declared into a class the database defends**
    (``core.transitions.DATABASE_DEFENDED``) — the protected columns slice 3
    ships are the parent's, declared and defended in #318, and the rule above is
    not one of them. The ``DELETE`` condition above is cross-table and
    unexpressible today, because the second of the two statuses it reads lands
    in slice 4; slice 4 adds it as an **extension** of the installed gate rather
    than by re-owning its row, and G19's `notes` name that deferral so it is
    recorded beside the gate as well as here. A
    model-level ``save()`` guard is deliberately *not* shipped in its place:
    ADR-0007 §2 is explicit that such a guard is not enforcement, and this
    repository has already shipped one that a production writer bypassed by
    design.

    ``updated_at`` is inherited from ``BaseModel`` and, under the record rule
    above, never moves after insert.
    """
    posting = models.OneToOneField(
        Posting, on_delete=models.CASCADE, related_name="measurement"
    )
    # The bag, keyed by the tenant's own declared measurement codes (#274). The
    # record is singular and its bag is plural, and both are right: a posting has
    # ONE measurement record, and that record holds every quantity the posting
    # was measured by.
    #
    # THE FIELD IS NAMED FOR THE ENTITY, NOT FOR THE CONCEPT ITS KEYS BELONG TO,
    # which is the same shape as the bag above: `metadata_key`'s bag is spelled
    # `metadata`, and this one is spelled for `Measurement` — ADR-0006's
    # canonical name for a measurable quantity, and the word the declarations
    # already publish. The retired entries this rename cleared named the concept
    # (`expected: measurement_key`) rather than the field, as that neighbour's
    # did; a key's concept and a bag of them do not share a spelling. Only a declared quantity may participate in monetary
    # calculation — a property of the declaration table, not of this column,
    # which still accepts any key a caller sends and lets an unmatched one
    # contribute nothing. Slice 3 owns making that visible.
    measurements = models.JSONField(default=dict, blank=True)
    # When the quantities were RECORDED, which is not when this row was written:
    # rows folded out of the posting by 0031 carry the moment their posting
    # arrived, long before the fold ran. ``created_at`` answers the other
    # question and the two are different facts.
    recorded_at = models.DateTimeField()
    # The retention horizon — a column, and nothing else. There is no prune job,
    # no schedule, no owner and no default value anywhere in this repository,
    # because no document states the short clock: shipping a column is not the
    # same as starting one, and a clock nobody has decided must not be started
    # by accident. It stays NULL until someone decides what it means.
    prunable_at = models.DateTimeField(null=True, blank=True)

    #: Every column of this record and the class it is declared into (ADR-0007
    #: §2). All of them point at the record rule in the docstring above rather
    #: than at a class of their own, and none of them is a class the database
    #: defends.
    transition_classes = {
        "id": RECORD_RULE,
        "created_at": RECORD_RULE,
        "updated_at": RECORD_RULE,
        "posting": RECORD_RULE,
        "measurements": RECORD_RULE,
        "recorded_at": RECORD_RULE,
        "prunable_at": RECORD_RULE,
    }

    class Meta:
        db_table = "ubb_posting_measurement"

    def __str__(self):
        return f"PostingMeasurement({self.posting_id})"


class BackfillDirtyPeriod(BaseModel):
    """Marker: a posting was backfilled into a PRIOR calendar month for this
    (tenant, customer). Written in the same transaction as the Posting insert
    (savepoint-IntegrityError-swallow on the unique constraint), consumed by the
    hourly ``resnapshot_dirty_periods`` task via the apps.metering.queries
    contract — the consumer re-snapshots the period's margin then deletes the
    marker, so a crash before delete is retried."""
    tenant = models.ForeignKey(
        "tenants.Tenant", on_delete=models.CASCADE, related_name="backfill_dirty_periods"
    )
    customer = models.ForeignKey(
        "customers.Customer", on_delete=models.CASCADE, related_name="backfill_dirty_periods"
    )
    period_start = models.DateField()

    class Meta:
        db_table = "ubb_backfill_dirty_period"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "customer", "period_start"],
                name="uq_backfill_dirty_period",
            ),
        ]

    def __str__(self):
        return f"BackfillDirtyPeriod({self.customer_id}: {self.period_start})"


class Refund(BaseModel):
    """Refund linked to a posting."""
    tenant = models.ForeignKey(
        "tenants.Tenant", on_delete=models.CASCADE, related_name="refunds"
    )
    customer = models.ForeignKey(
        "customers.Customer", on_delete=models.CASCADE, related_name="refunds"
    )
    posting = models.OneToOneField(
        Posting, on_delete=models.CASCADE, related_name="refund"
    )
    amount_micros = models.BigIntegerField()
    reason = models.TextField(blank=True, default="")
    refunded_by_api_key = models.ForeignKey(
        "tenants.TenantApiKey", on_delete=models.SET_NULL, null=True, blank=True
    )

    class Meta:
        db_table = "ubb_refund"

    def __str__(self):
        return f"Refund({self.posting.request_id}: {self.amount_micros})"
