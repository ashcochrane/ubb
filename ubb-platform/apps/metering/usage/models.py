from django.contrib.postgres.indexes import GinIndex
from django.db import models
from django.utils import timezone

from core.models import BaseModel


class Posting(BaseModel):
    """One immutable economic posting — the row that says work was billed for.

    Renamed from the usage-event noun in #269 (slice 2), with its table, so the
    database stops preserving obsolete terminology (ADR-0006 §9, gate G9). The
    record of WHAT WAS MEASURED splits off into a child of its own in #270; this
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
    metadata = models.JSONField(default=dict)

    # Pricing breakdown (populated when platform prices the event)
    units = models.BigIntegerField(null=True, blank=True)
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
    usage_metrics = models.JSONField(default=dict, blank=True)
    tags = models.JSONField(null=True, blank=True)
    # The exact unit of work this event belongs to. The ONLY unit attribution
    # — tags are free-form analytics labels and never silently become a
    # limited thing (no tag-fallback inference).
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
    # tenant tags or request metadata; written once at record (sync) / settle
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
            # the stop-context array. Partial — tagged events are the rare
            # exception, so the index stays tiny and untagged inserts pay
            # nothing.
            GinIndex(fields=["stop_context"], name="idx_usage_stop_context",
                     condition=models.Q(stop_context__isnull=False)),
        ]
        ordering = ["-effective_at"]

    def __str__(self):
        return f"Posting({self.request_id}: {self.billed_cost_micros})"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValueError("Posting records are immutable and cannot be updated.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("Posting records are immutable and cannot be deleted.")


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
