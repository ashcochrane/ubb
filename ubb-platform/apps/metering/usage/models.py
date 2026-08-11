from django.contrib.postgres.indexes import GinIndex
from django.db import models
from django.utils import timezone

from core.models import BaseModel
from core.transitions import RECORD_RULE


class Posting(BaseModel):
    """One immutable economic posting — the row that says work was billed for.

    Renamed from the usage-event noun in #269 (slice 2), with its table, so the
    database stops preserving obsolete terminology (ADR-0006 §9, gate G9). The
    record of WHAT WAS MEASURED split off into a child of its own in #270; this
    row keeps the money, the attribution and the identity.
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
    # --- The ten selector columns (design D2/D3) ---
    # One vocabulary for analytics grouping AND rate selection. Four reserved
    # keys plus six tenant slots bound by the GroupingField registry. "" means
    # "not set" on an event and "matches anything" on a Rate; specificity =
    # the count of non-empty selectors.
    event_type = models.CharField(max_length=100, blank=True, default="", db_index=True)
    # Indexed: /analytics/usage groups by provider unconditionally on every call.
    provider = models.CharField(max_length=100, blank=True, default="", db_index=True)
    # Inherited from the event's task chain, never sent by the caller (D6).
    task_type = models.CharField(max_length=64, blank=True, default="", db_index=True)
    subtask_type = models.CharField(max_length=64, blank=True, default="", db_index=True)
    dim1 = models.CharField(max_length=100, blank=True, default="", db_index=True)
    dim2 = models.CharField(max_length=100, blank=True, default="", db_index=True)
    dim3 = models.CharField(max_length=100, blank=True, default="", db_index=True)
    dim4 = models.CharField(max_length=100, blank=True, default="", db_index=True)
    dim5 = models.CharField(max_length=100, blank=True, default="", db_index=True)
    dim6 = models.CharField(max_length=100, blank=True, default="", db_index=True)
    provider_cost_micros = models.BigIntegerField(default=0)
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
        ]
        indexes = [
            models.Index(fields=["customer", "-effective_at"], name="idx_usage_customer_effective"),
            models.Index(fields=["tenant", "-effective_at"], name="idx_usage_tenant_effective"),
            models.Index(fields=["tenant", "task_type", "subtask_type", "-effective_at"],
                         name="idx_usage_work_attribution"),
            models.Index(fields=["tenant", "dim1", "dim2", "-effective_at"],
                         name="idx_usage_dim_attribution"),
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
        if not self._state.adding:
            raise ValueError("Posting records are immutable and cannot be updated.")
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

    Enforcing that at the database is gate G19, which is ``owned_by_slice_3``
    and whose ``DELETE`` condition is cross-table and unexpressible until slice
    4, because one of the two statuses it reads lands in slice 3 and the other
    in slice 4. **No column here is declared into a class the database defends**
    (``core.transitions.DATABASE_DEFENDED``), so slice 3 is still the first
    slice with a protected column, exactly as G19's own note says. A model-level
    ``save()`` guard is deliberately *not* shipped in its place: ADR-0007 §2 is
    explicit that such a guard is not enforcement, and this repository has
    already shipped one that a production writer bypassed by design.

    ``updated_at`` is inherited from ``BaseModel`` and, under the record rule
    above, never moves after insert.
    """
    posting = models.OneToOneField(
        Posting, on_delete=models.CASCADE, related_name="measurement"
    )
    # The bag, keyed by the tenant's own declared measurement codes (#274). The
    # record is singular and its bag is plural, and both are right: a posting has
    # ONE measurement record, and that record holds every quantity the posting
    # was measured by. Only a declared quantity may participate in monetary
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
