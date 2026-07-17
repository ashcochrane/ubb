from django.db import models
from core.models import BaseModel


class RiskConfig(BaseModel):
    tenant = models.OneToOneField("tenants.Tenant", on_delete=models.CASCADE, related_name="risk_config")
    max_requests_per_minute = models.IntegerField(default=60)
    max_concurrent_requests = models.IntegerField(default=10)
    gate_fail_closed = models.BooleanField(default=False)
    # One-rule (#37): tenant default for Task.provider_cost_limit_micros —
    # COGS-denominated (what the job burns), applied at the start-gate when a
    # start call names no explicit limit. NULL = no default: absent both, the
    # task is uncapped and no signal ever fires.
    default_task_provider_cost_limit_micros = models.BigIntegerField(null=True, blank=True)
    # Subtasks (#38): the same fallback for units registered with a parent
    # (parent_task_id at the start-gate). Same denomination, same NULL = no
    # default, same coverage gate.
    default_subtask_provider_cost_limit_micros = models.BigIntegerField(null=True, blank=True)

    class Meta:
        db_table = "ubb_risk_config"

    def __str__(self):
        return f"RiskConfig({self.tenant.name}: {self.max_requests_per_minute}rpm, {self.max_concurrent_requests}concurrent)"


def default_alert_levels():
    return [50, 80, 100, 110]


BUDGET_ENFORCE_MODES = [("advisory", "Advisory"), ("enforcing", "Enforcing")]


STOP_SIGNAL_FAMILIES = [("floor_stop", "Floor stop"), ("soft_floor", "Soft floor")]
STOP_SIGNAL_STATES = [("stopped", "Stopped"), ("cleared", "Cleared")]


class StopSignalState(BaseModel):
    """The durable per-owner-per-family signal ledger (#39, spec §D).

    One row per (billing owner, signal family) holding the current stop/clear
    state and the per-family episode sequence. Every stop/resume emission —
    fast Redis lane, durable drawdown handler, hourly reconcile — routes
    through a winning transition on this row (see
    services/stop_signal_service.py); only the winner emits the outbox event,
    so a crossing observed by several lanes signals exactly once per episode.
    ``episode_seq`` is the stop-episode id the stop-context tagging and the
    past-limit report (#41) key on; it only ever increments (a stop opens
    episode N, the paired clear closes it), so episode ids never collide
    across the owner's history.

    Families at launch: ``floor_stop`` (the customer-wide hard stop — wallet
    floor / budget cap) and ``soft_floor`` (model support here; exercised by
    the soft-floor ticket, #40).
    """

    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE,
                               related_name="stop_signal_states")
    owner = models.ForeignKey("customers.Customer", on_delete=models.CASCADE,
                              related_name="stop_signal_states")
    family = models.CharField(max_length=20, choices=STOP_SIGNAL_FAMILIES)
    state = models.CharField(max_length=10, choices=STOP_SIGNAL_STATES)
    episode_seq = models.BigIntegerField(default=0)
    reason = models.CharField(max_length=64, blank=True, default="")
    transitioned_at = models.DateTimeField()
    # Announcement bookkeeping (delivery spec §B, #43): the OutboxEvent id of
    # this row's LAST announcement, stamped inside the same atomic unit as the
    # transition/re-mint that emitted it — stamp and event commit or vanish
    # together. Deliberately a plain UUID, not an FK: outbox cleanup deletes
    # terminally-successful rows after 30/90 days, and the stamp must keep
    # meaning "announced" then (see apps.platform.events.announcements).
    announce_outbox_id = models.UUIDField(null=True, blank=True)

    class Meta:
        db_table = "ubb_stop_signal_state"
        constraints = [
            models.UniqueConstraint(fields=["owner", "family"],
                                    name="uq_stop_signal_owner_family"),
        ]

    def __str__(self):
        return f"StopSignalState({self.owner_id}/{self.family}: {self.state} ep{self.episode_seq})"


PATROL_OUTCOMES = [
    ("reminted", "Re-minted announcement"),
    ("flag_realigned", "Stop flag re-aligned"),
    ("sweep_killed", "Task swept into the kill flow"),
    ("repaired", "Live balance repaired upward"),
    ("repaired_micros", "Micros applied by upward repairs"),
    ("repair_lapsed", "Repair candidate lapsed"),
]


class PatrolOutcome(BaseModel):
    """Day-bucketed counters of what the hourly patrol repaired (#44, delivery
    spec §F): re-minted announcements, fast-flag re-alignments, task-sweep
    kills, and the upward live-balance repairs (#45 — count, micros applied,
    and lapsed candidates; the ``repaired_micros`` bucket's ``count`` IS the
    amount). Written by the patrol leg of ``reconcile_live_ledgers``; read by
    the ops/ingest-health surface (``apps.billing.queries.get_patrol_stats``).
    Visibility only — a nonzero count means a crash/blind-window corner was
    actually healed, and a persistent spike means a lane is unhealthy.
    """

    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE,
                               related_name="patrol_outcomes")
    day = models.DateField()
    outcome = models.CharField(max_length=20, choices=PATROL_OUTCOMES)
    count = models.BigIntegerField(default=0)

    class Meta:
        db_table = "ubb_patrol_outcome"
        constraints = [
            models.UniqueConstraint(fields=["tenant", "day", "outcome"],
                                    name="uq_patrol_outcome_tenant_day"),
        ]

    def __str__(self):
        return f"PatrolOutcome({self.tenant_id} {self.day} {self.outcome}: {self.count})"


LIVE_BALANCE_REPAIR_STATUS = [
    ("candidate", "Candidate"),
    ("repaired", "Repaired"),
    ("lapsed", "Lapsed"),
]


class LiveBalanceRepair(BaseModel):
    """Audit trail of the upward live-balance repair (#45, delivery spec §D)
    — one row per grace-gated observation of a prepaid live-counter deficit
    (expected = durable − Σ pending holds; deficit = expected − live).

    Lifecycle: the first patrol pass measuring a past-de-minimis deficit
    writes a ``candidate`` (first measurement + snapshot; nothing applied).
    The immediately-next pass resolves it: still deficient → ``repaired``
    (min of the two measurements applied as a relative increment; the row
    gains the second measurement, the amount, live before/after, and the
    resolving snapshot) — vanished, or too stale to prove hour-stability →
    ``lapsed`` (``second_deficit_micros`` stays null on a stale lapse: the
    in-window second measurement never happened). ``durable_balance_micros``
    and ``pending_hold_micros`` always describe the row's LATEST recorded
    measurement. At most one open candidate per owner (partial unique);
    passes serialize on ``lock_for_billing``, so a repair applies once.
    """

    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE,
                               related_name="live_balance_repairs")
    owner = models.ForeignKey("customers.Customer", on_delete=models.CASCADE,
                              related_name="live_balance_repairs")
    status = models.CharField(max_length=10, choices=LIVE_BALANCE_REPAIR_STATUS,
                              default="candidate")
    first_deficit_micros = models.BigIntegerField()
    second_deficit_micros = models.BigIntegerField(null=True, blank=True)
    applied_micros = models.BigIntegerField(null=True, blank=True)
    live_before_micros = models.BigIntegerField(null=True, blank=True)
    live_after_micros = models.BigIntegerField(null=True, blank=True)
    durable_balance_micros = models.BigIntegerField()
    pending_hold_micros = models.BigIntegerField()
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "ubb_live_balance_repair"
        constraints = [
            models.UniqueConstraint(
                fields=["owner"], condition=models.Q(status="candidate"),
                name="uq_live_balance_repair_open_candidate"),
        ]

    def __str__(self):
        return (f"LiveBalanceRepair({self.owner_id}: {self.status} "
                f"d1={self.first_deficit_micros} applied={self.applied_micros})")


class BudgetConfig(BaseModel):
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE, related_name="budget_configs")
    customer = models.ForeignKey("customers.Customer", on_delete=models.CASCADE,
                                 related_name="budget_configs", null=True, blank=True)
    cap_micros = models.BigIntegerField(default=0)  # <= 0 means "no cap" (overlay inert)
    period = models.CharField(max_length=10, default="month")
    enforce_mode = models.CharField(max_length=10, choices=BUDGET_ENFORCE_MODES, default="advisory")
    hard_stop_pct = models.IntegerField(default=100)
    alert_levels = models.JSONField(default=default_alert_levels)
    fail_closed = models.BooleanField(default=False)

    class Meta:
        db_table = "ubb_budget_config"
        constraints = [
            models.UniqueConstraint(fields=["tenant"], condition=models.Q(customer__isnull=True),
                                    name="uq_budget_config_tenant_default"),
            models.UniqueConstraint(fields=["tenant", "customer"], condition=models.Q(customer__isnull=False),
                                    name="uq_budget_config_tenant_customer"),
        ]

    def __str__(self):
        return f"BudgetConfig({self.tenant_id}/{self.customer_id}: cap={self.cap_micros} {self.enforce_mode})"
