from django.db import models
from core.models import BaseModel
from core.vocabulary import (CONTROL_FAMILY_ADMISSION_CONTROL,
                             CONTROL_FAMILY_CEILING,
                             CONTROL_FAMILY_CUSTOMER_SPEND_POOL,
                             CONTROL_FAMILY_WALLET_POLICY,
                             SPEND_POOL_ENFORCE_MODE_ALERT_ONLY,
                             SPEND_POOL_ENFORCE_MODE_BLOCKING)


class RiskConfig(BaseModel):
    tenant = models.OneToOneField("tenants.Tenant", on_delete=models.CASCADE, related_name="risk_config")
    max_requests_per_minute = models.IntegerField(default=60)
    gate_fail_closed = models.BooleanField(default=False)
    # A per-owner cap on work already running sat here until #455 and is
    # DELETED, not moved (#150 §12.5): it bounded a count of outstanding
    # operations, converted to no amount of money, and invited the belief
    # that UBB closes a blind window it cannot see into. Admission control
    # bounds the RATE of new work (the column above) and nothing else.
    # The two tenant-default COGS ceilings that used to sit here (#37, #38)
    # left for the kernel in #453 — `Tenant.default_task_cogs_ceiling_micros`
    # and its contained-work twin — because a ceiling is a kernel concept a
    # tenant without billing still gets (#141 §6.2, slice 6 §1). Their values
    # were carried onto the tenant row by `gating/migrations/0011`.

    class Meta:
        db_table = "ubb_risk_config"

    def __str__(self):
        return f"RiskConfig({self.tenant.name}: {self.max_requests_per_minute}rpm)"


def default_alert_levels():
    return [50, 80, 100, 110]


#: How a customer spend pool is enforced — the registry's closed pair, held by
#: reference (#456 paid `g2-backend-spend_pool_enforce_mode`; both values were
#: already right, so this is a re-source and not a change of value). The
#: wording beside each identity is the admin's, on `TASK_STATUS_CHOICES`'s
#: footing. A blocking pool enforces identically for `prepaid` and `postpaid`:
#: mode decides who invoices, not whether the bound bites (#150 §7.1).
SPEND_POOL_ENFORCE_MODES = [
    (SPEND_POOL_ENFORCE_MODE_ALERT_ONLY, "Alert only"),
    (SPEND_POOL_ENFORCE_MODE_BLOCKING, "Blocking"),
]


#: WHICH OF THE FOUR SPEND CONTROLS A SIGNAL CAME FROM — the registry's
#: `control_family`, held whole by reference (#458 paid
#: `g2-backend-control_family` at the site the registry declares, slice 6
#: §1, §9). The wording beside each identity is the admin's, on
#: `SPEND_POOL_ENFORCE_MODES`' footing. The ledger below keys its lines by
#: this column and today drives two of the four — the pool's stop and the
#: wallet policy's two floors; a ceiling stops a UNIT rather than a customer
#: and admission control refuses a start rather than stopping anything, so
#: neither opens a customer-wide episode. A consumer holds the vocabulary
#: rather than the subset it happens to drive.
CONTROL_FAMILIES = [
    (CONTROL_FAMILY_CEILING, "Ceiling"),
    (CONTROL_FAMILY_CUSTOMER_SPEND_POOL, "Customer spend pool"),
    (CONTROL_FAMILY_WALLET_POLICY, "Wallet policy"),
    (CONTROL_FAMILY_ADMISSION_CONTROL, "Admission control"),
]

STOP_SIGNAL_STATES = [("stopped", "Stopped"), ("cleared", "Cleared")]


class StopSignalState(BaseModel):
    """The durable per-owner-per-line signal ledger (#39, spec §D; slice 6 §9).

    One row per (billing owner, control family, line) holding the current
    stop/clear state and that line's own episode sequence. Every stop/resume
    emission — fast Redis lane, durable drawdown handler, hourly reconcile —
    routes through a winning transition on this row (see
    services/stop_signal_service.py); only the winner emits the outbox event,
    so a crossing observed by several lanes signals exactly once per episode.
    ``episode_seq`` is the stop-episode id the stop-context tagging and the
    past-limit report (#41) key on; it only ever increments (a stop opens
    episode N, the paired clear closes it), so episode ids never collide
    across one line's history.

    THREE LINES, EACH WITH ITS OWN EPISODES (#458): the wallet policy's hard
    floor (``hard_floor``) and the customer spend pool (``customer_spend_pool``)
    are the two STOP lines — each opens the customer-wide stop state, each
    is named by the `reason_code` the stop carries, and a customer stopped
    by its pool and by its floor at once holds two open episodes that clear
    independently, with the stop flag lifting only when both have — and the
    wallet policy's soft floor (``soft_floor``) is the wind-down SIGNAL line,
    never a stop. Until #458 the two stop lines were one row under a local
    family word and the control that opened an episode was told apart by the
    owner's tenant billing mode; the family column now names the control
    and the row records the control's identity beside it.
    """

    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE,
                               related_name="stop_signal_states")
    owner = models.ForeignKey("customers.Customer", on_delete=models.CASCADE,
                              related_name="stop_signal_states")
    control_family = models.CharField(max_length=20, choices=CONTROL_FAMILIES)
    # THE LINE — the ledger's own line name, part of the unique key: the two
    # stop lines coincide with the `reason_code` each stop carries, the
    # wind-down line has a name of its own. Fixed for the life of the row;
    # what CAUSED the last clearing transition is `clear_reason` below.
    reason = models.CharField(max_length=64)
    state = models.CharField(max_length=10, choices=STOP_SIGNAL_STATES)
    episode_seq = models.BigIntegerField(default=0)
    # WHY THE LAST CLEARING TRANSITION HAPPENED — a balance that recovered,
    # the hourly reconcile's bottom line, an upward live-balance repair, or
    # the silent close behind an enforcement-mode flip. "" while stopped.
    # It used to overwrite `reason` on every clear; the line's name is part
    # of the key now, so the cause has its own column.
    clear_reason = models.CharField(max_length=64, blank=True, default="")
    # THE ROW THAT DECLARES THE CONTROL WHOSE LINE THIS IS (§15): the pool row
    # for the pool's line, the billing profile or the tenant's billing
    # configuration that carried the floor for the hard floor's — recorded on
    # the stop transition so the episode's announcement and every re-mint of
    # it name the same control. Null on the wind-down line, which stops
    # nothing and passes nothing to a kill, and on a row that predates #458.
    control_id = models.UUIDField(null=True, blank=True)
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
            # ONE ROW PER LINE, AT THE DATABASE (slice 6 §9, Testing
            # Decisions): the key is the owner, the family and the line, so
            # the pool's and the floor's episodes are two rows that cannot
            # collapse into one whichever lane writes first.
            models.UniqueConstraint(fields=["owner", "control_family", "reason"],
                                    name="uq_stop_signal_owner_family_line"),
        ]

    def __str__(self):
        return (f"StopSignalState({self.owner_id}/{self.control_family}/"
                f"{self.reason}: {self.state} ep{self.episode_seq})")


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
    amount). Written by the patrol leg of ``reconcile_live_ledgers``; read
    through ``apps.billing.queries.get_patrol_stats``.
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
    (expected = the durable balance; deficit = expected − live).

    Lifecycle: the first patrol pass measuring a past-de-minimis deficit
    writes a ``candidate`` (first measurement + snapshot; nothing applied).
    The immediately-next pass resolves it: still deficient → ``repaired``
    (min of the two measurements applied as a relative increment; the row
    gains the second measurement, the amount, live before/after, and the
    resolving snapshot) — vanished, or too stale to prove hour-stability →
    ``lapsed`` (``second_deficit_micros`` stays null on a stale lapse: the
    in-window second measurement never happened). ``durable_balance_micros``
    always describes the row's LATEST recorded measurement. At most one open
    candidate per owner (partial unique); passes serialize on
    ``lock_for_billing``, so a repair applies once.
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
    # The reservation term of the measurement this repair was born with
    # (Ruling A2, #233: the reservation was one cause of the drift, not the
    # cause). The surviving cause reserves nothing, so the repair stopped
    # measuring it and writes 0; historical rows keep what they recorded.
    # Non-null with no default, so the column outlives the term until the
    # reservation's own migration takes it.
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


class CustomerSpendPool(BaseModel):
    """The Customer Spend Pool — a bound on a customer's period charges
    (#150 §7, slice 6 §4). A row on a customer is that customer's pool; a row
    with no customer is the tenant default. The pool's LEVEL needs no column:
    a row on a business is the owner-level pool, a row on a seat the
    seat-level pool, and the tenant default applies to seats only (§4 — the
    two-level behaviour is #459's). Renamed from the retired family word by
    `gating/migrations/0013` (#456), carrying every row."""
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE, related_name="customer_spend_pools")
    customer = models.ForeignKey("customers.Customer", on_delete=models.CASCADE,
                                 related_name="customer_spend_pools", null=True, blank=True)
    cap_micros = models.BigIntegerField(default=0)  # <= 0 means "no pool" (overlay inert)
    period = models.CharField(max_length=10, default="month")
    enforce_mode = models.CharField(max_length=10, choices=SPEND_POOL_ENFORCE_MODES,
                                    default=SPEND_POOL_ENFORCE_MODE_ALERT_ONLY)
    hard_stop_pct = models.IntegerField(default=100)
    alert_levels = models.JSONField(default=default_alert_levels)
    fail_closed = models.BooleanField(default=False)

    class Meta:
        db_table = "ubb_customer_spend_pool"
        constraints = [
            models.UniqueConstraint(fields=["tenant"], condition=models.Q(customer__isnull=True),
                                    name="uq_customer_spend_pool_tenant_default"),
            models.UniqueConstraint(fields=["tenant", "customer"], condition=models.Q(customer__isnull=False),
                                    name="uq_customer_spend_pool_tenant_customer"),
        ]

    def __str__(self):
        return f"CustomerSpendPool({self.tenant_id}/{self.customer_id}: cap={self.cap_micros} {self.enforce_mode})"
