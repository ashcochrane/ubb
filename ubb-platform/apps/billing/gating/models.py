from django.db import models
from core.models import BaseModel
from core.vocabulary import (AFFORDABILITY_REASON_ACCOUNT_CLOSED,
                             AFFORDABILITY_REASON_CUSTOMER_SPEND_POOL_EXCEEDED,
                             AFFORDABILITY_REASON_CUSTOMER_SPEND_POOL_UNAVAILABLE,
                             AFFORDABILITY_REASON_CUSTOMER_STOPPED,
                             AFFORDABILITY_REASON_INSUFFICIENT_FUNDS,
                             AFFORDABILITY_REASON_PARENT_TASK_NOT_ACTIVE,
                             AFFORDABILITY_REASON_RATE_LIMIT_EXCEEDED,
                             AFFORDABILITY_REASON_SOFT_FLOOR_REACHED,
                             AFFORDABILITY_REASON_SUBTASK_DEPTH_EXCEEDED,
                             CONTROL_FAMILY_ADMISSION_CONTROL,
                             CONTROL_FAMILY_CEILING,
                             CONTROL_FAMILY_CUSTOMER_SPEND_POOL,
                             CONTROL_FAMILY_WALLET_POLICY,
                             SPEND_POOL_ENFORCE_MODE_ALERT_ONLY,
                             SPEND_POOL_ENFORCE_MODE_BLOCKING)


class RiskConfig(BaseModel):
    """The tenant's posture for the customer spend pool's read when its
    store is away — one column, and that is all this row is now (slice 6
    §1; #150 §15).

    Four columns left it, in three tickets, and none of them was billing's
    to hold: the two tenant-default COGS ceilings went to the tenant row in
    #453 (a ceiling is a kernel concept a tenant without billing still gets,
    #141 §6.2; carried by `gating/migrations/0011`); the per-owner cap on
    work already running was DELETED in #455 (#150 §12.5 — a count of
    outstanding operations converts to no amount of money, and its existence
    invited the belief that UBB closes a blind window it cannot see into);
    and the per-minute bound on new work went to the tenant row as
    `max_task_starts_per_minute` in #462 (admission control is a property of
    the work's admission, run by the kernel for every tenant; carried by
    `gating/migrations/0015`). What stays is the one posture #150 §15 keeps
    and #141 §7 keeps in billing. §1 permits folding it onto the pool's
    tenant-default row later, provided a customer row that does not fail
    closed still inherits the tenant's answer; that fold is not taken here.
    """
    tenant = models.OneToOneField("tenants.Tenant", on_delete=models.CASCADE, related_name="risk_config")
    gate_fail_closed = models.BooleanField(default=False)

    class Meta:
        db_table = "ubb_risk_config"

    def __str__(self):
        return f"RiskConfig({self.tenant.name}: fail_closed={self.gate_fail_closed})"


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

#: WHY A START IS REFUSED, OR WOULD BE — the registry's `affordability_reason`,
#: all nine known values held by reference at the site the registry declares
#: (#463 paid `g3-backend-affordability_reason`; slice 6 §1, §13), on
#: `CONTROL_FAMILIES`' footing. The wording beside each identity is the
#: composition layer's, for the prose half of a start's refusal
#: (`api/v1/task_endpoints._refused` puts it in the problem's `detail`); the
#: identity itself travels as data, in `reason`, and is what a caller
#: branches on. Held WHOLE rather than as the subset billing's money verdict
#: answers itself: the kernel's admission check refuses the standing and the
#: rate, its work service refuses the shape of the work (a parent that is not
#: running; a depth work cannot nest to), and the money verdict refuses the
#: floors and the pool and words a suspension — every producer on both sides
#: imports the same constants (§1), and a consumer holds the vocabulary rather
#: than the part it happens to produce. The set is OPEN: a refusal can arise
#: from a control UBB gains later, so nothing may refuse a value it does not
#: list; the wording falls back to the token.
AFFORDABILITY_REASONS = [
    (AFFORDABILITY_REASON_INSUFFICIENT_FUNDS, "insufficient funds"),
    (AFFORDABILITY_REASON_ACCOUNT_CLOSED, "the account is closed"),
    (AFFORDABILITY_REASON_CUSTOMER_STOPPED, "a customer-wide stop is in force"),
    (AFFORDABILITY_REASON_SOFT_FLOOR_REACHED, "the soft floor is reached"),
    (AFFORDABILITY_REASON_RATE_LIMIT_EXCEEDED, "the rate limit is exceeded"),
    (AFFORDABILITY_REASON_CUSTOMER_SPEND_POOL_EXCEEDED,
     "the customer spend pool is exceeded"),
    (AFFORDABILITY_REASON_CUSTOMER_SPEND_POOL_UNAVAILABLE,
     "the customer spend pool's state is unavailable"),
    (AFFORDABILITY_REASON_PARENT_TASK_NOT_ACTIVE, "the parent task is not active"),
    (AFFORDABILITY_REASON_SUBTASK_DEPTH_EXCEEDED, "the subtask depth is exceeded"),
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
    # THE OWNER'S OPEN RESERVATIONS AT THE MOMENT OF THIS ROW'S LATEST
    # RECORDED MEASUREMENT (#461, slice 6 §5) — the prepaid reservations
    # taken at the start of work sold at one agreed price and not yet
    # released (`wallets.WalletReservation`), read under the same billing
    # lock as the durable balance beside it. It is CONTEXT for the audit row
    # and never a term of the arithmetic: a reservation encumbers the
    # affordability read at a start and moves neither the durable balance
    # nor the live counter, so the deficit is durable − live whatever is
    # reserved, and a reader of a repair sees what was encumbering the
    # balance the deficit was measured against. The column was born as a
    # term of the measurement (Ruling A2, #233 — the deleted arrival-time
    # lane's reservation was one cause of the drift, not the cause) and
    # rows written between that lane's deletion and #461 record 0.
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
    seat-level pool, and the tenant default applies to seats only — a
    business with no row of its own has no pool (§4, #459: both levels
    alert, stop and refuse, in every billing mode). Renamed from the retired
    family word by `gating/migrations/0013` (#456), carrying every row."""
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
