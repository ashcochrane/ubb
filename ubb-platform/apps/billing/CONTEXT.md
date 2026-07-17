# Billing

The money layer for prepaid and postpaid tenants — the prepaid credit ledger, real-time spend
control, auto-top-up, and the period-close Stripe line-item push. Billing owns everything up to
invoice line items / credit drawdown; Stripe owns collection, tax, dunning, refunds, and disputes.
Code anchors are relative to `ubb-platform/`.

## Prepaid wallet & credit ledger

**Wallet**:
A customer's single prepaid credit account holding a spendable balance in one currency; one per
customer. (`apps/billing/wallets/models.py:Wallet`)

**Ledger entry**:
An append-only row recording one balance movement (its signed amount and resulting balance), made
exactly-once per idempotency key. (`apps/billing/wallets/models.py:WalletTransaction`)
_Avoid_: mutating a balance without writing a ledger entry.

**Drawdown**:
The wallet debit applied when a `usage.recorded` event is processed.
_Avoid_: "charge" — a charge is a Stripe collection; a drawdown is a ledger debit.

**Credit grant (lot)**:
A layer of (often expiring or promo) credit stacked on the wallet with its own remaining balance;
base money is the non-grant remainder, derived not stored.
(`apps/billing/wallets/models.py:CreditGrant`)

**Grant kind**:
Whether a lot is `paid` (from a top-up, withdrawable) or `promo` (never withdrawable); promo is
consumed before paid.

**Consumption order**:
The deterministic order lots are drawn down — soonest expiry first, promo before paid — with the
remainder charged to base money.

**Clawback**:
Restoring the credit invariant after a dispute loss or Stripe refund by voiding/consuming lot
remainders.

**Min balance (wallet floor)**:
The predetermined line on a wallet's negative balance whose crossing fires the customer-wide stop
signal (`stop.fired`) — and whose re-crossing fires the paired resume (`stop.cleared`), the moment
the balance recovers, from any clearing path. The HARD floor of the two-floor pair (see **Soft
floor**). A signal point, not a wall — events past it still land and bill, and the balance keeps
showing reality.
_Avoid_: "credit limit", and "suspension threshold" — suspension is a reaction to the crossing,
not the floor's meaning.

**Negative since (aged negatives)**:
`Wallet.negative_since` — when the balance last crossed ≥0 → <0; null whenever the balance is ≥ 0.
Maintained as a sign-consistency invariant by the wallet's own save (every mutation path keeps it
true), surfaced on the balance API and as the ops aged-negatives metric (count + max age on
ingest-health). Purely observational: no reminder events, no auto-close — collections stay between
the tenant, their customer, and Stripe. (`apps/billing/wallets/models.py:Wallet`)
_Avoid_: wiring any automatic reaction to it.

**Soft floor**:
The second, higher line of the two-floor pair — a tenant-chosen wind-down line per end customer
(customer override → tenant default; null = no soft floor; always resolving at or above the hard
floor): past it, NEW top-level task starts are refused at the start-gate (`soft_floor_reached`)
while running tasks — and subtask starts under a still-active parent — complete. Crossing and
re-crossing fire the `soft_floor.crossed`/`soft_floor.cleared` webhook pair through the signal
ledger's `soft_floor` family (durable lane only — no Redis threshold; signal latency is outbox
latency). Never a billing wall and never an ack change: acks never change on a soft-floor
crossing, events are never tagged, and work slipping past the gate lands and bills.
(`apps/billing/queries.py:get_customer_soft_min_balance`)
_Avoid_: treating it as a stop signal — `stop=true` keeps meaning exactly one thing (hard-floor
family only).

## Spend control

**Start-gate (spend gate)**:
The durable pre-start check — suspension, stop flag, rate/concurrency limits, affordability, the
soft floor (top-level starts only), budget, cost-card coverage — run before a Task is created.
Refusing a start is legitimate under the one-rule model: it refuses work that hasn't happened,
never a usage report.
(`apps/billing/gating/services/risk_service.py`)

**Live ledger (Tier-2 counter)**:
The billing-owner-keyed Redis counter decremented synchronously at record time so the API response
can carry a real stop verdict; reconciled against the durable ledger.
(`apps/billing/gating/services/live_ledger_service.py`)

**Customer-wide stop flag**:
The cooperative, owner-keyed Redis flag set when the live counter crosses the wallet floor or
budget cap; it blocks new task starts until recovery — usage reports keep landing and billing.
Paired with resume: the moment the balance re-crosses the floor, the flag lifts and `stop.cleared`
fires, closing the stop episode. The flag is the fast READ surface (ack verdicts) only — emission
dedup lives on the signal ledger.

**Signal ledger (`StopSignalState`)**:
The durable per-owner-per-family state row every stop/resume emission routes through; only the
winning transition emits (atomically with the row), so a crossing observed by the fast Redis lane,
the durable drawdown handler, and reconcile signals exactly once. Its `episode_seq` is the STOP
EPISODE id — a stop opens episode N, the paired clear closes it — which stop-context tagging and
the past-limit report key on. Suspension rides the same winning stop transition, so floor-stop and
suspension can never disagree or double-fire. Each winning transition also stamps
`announce_outbox_id` (the row's last announcement) inside the same atomic unit — see Announcement.
_Avoid_: treating the Redis stop flag as the emission dedup — the flag is fast-lane visibility;
the ledger is the truth.
(`apps/billing/gating/services/stop_signal_service.py`)

**Announcement**:
What a signal-bearing row (a ledger row, a killed task) last told the world: the stamped
`announce_outbox_id`. ANNOUNCED = the stamped event reached terminal success (`processed`, or
`skipped` — a tenant with no webhook config chose no push channel: vacuous success, never
re-minted). UNANNOUNCED = no stamp while signal-bearing, or the stamped row dead-lettered — the
patrol re-mints a fresh current-state event carrying `re_announcement: true` and the current
episode. IN-FLIGHT (`pending`/`processing`) is left alone: at most one live announcement per row.
_Avoid_: replaying the original failed event — a re-mint announces the CURRENT state, bottom-line
only. (`apps/platform/events/announcements.py`)

**Enforcement mode**:
Two positions — `off` / `enforcing`. When `off`, spend control is byte-for-byte a no-op (no
counters, no signals, no tagging); `enforcing` runs the full signal suite + state changes.
_Avoid_: a second enable flag — this is the single switch (mirrors the tenant's `enforcement_mode`);
a middle "compute but never act" mode — the one honest question is whether the signal suite is on.

**Budget**:
A per-tenant (optionally per-customer) monthly spend cap with alert levels.
(`apps/billing/gating/models.py:BudgetConfig`)

**Hold**:
The arrival-time reservation of one async event's estimated price on the live ledger, taken
*before* the event is durably appended; trued up at settle. Always holds, against the wallet only
— task limits are detected at settle with exact costs.
(`apps/billing/gating/services/hold_service.py`)
_Avoid_: "pre-auth" — a hold reserves an amount; it never blocks the event from landing.

**Crossing**:
The instant a debit or hold pushes an owner's live counter past its threshold (wallet floor or
budget cap), setting the stop flag. Cooperative: the crossing event itself still lands and bills.

**Orphan hold**:
A hold whose event never durably landed (crash between the hold and the append); the live balance
reads *lower* than reality — the safe direction — until credited, repaired, or expired. The
MIN-merge reconcile cannot heal it (it only ever lowers).

**Safe direction (over-restrictive)**:
The invariant that every accidental fast-lane failure makes the live view stingier — balance lower,
spend higher — never looser. The first-use seed window is the single deliberate exception.
_Avoid_: "fail-open means unprotected" — the durable lane keeps recording and billing throughout.

## Auto top-up

**Auto top-up**:
Automatically charging the saved payment method to refill the wallet when the balance falls below a
trigger threshold. (`apps/billing/topups/models.py:AutoTopUpConfig`)

**Top-up attempt**:
A persisted charge attempt created *before* calling Stripe (to supply deterministic idempotency
keys); status walks `pending → succeeded/failed/requires_action/superseded`.
(`apps/billing/topups/models.py:TopUpAttempt`)

**requires_action**:
A top-up that needs SCA (Strong Customer Authentication) before it can complete.

## Period close / usage invoicing (postpaid)

**Period close**:
The monthly job pushing each postpaid customer's prior-month usage to Stripe as invoice line items.
(`apps/billing/invoicing/tasks.py`)

**Usage invoice**:
A postpaid customer's usage for one calendar month, pushed to Stripe as line items; one per
(customer, month). (`apps/billing/invoicing/models.py:CustomerUsageInvoice`)
_Avoid_: confusing it with a Stripe invoice — UBB pushes the lines; Stripe owns the invoice.

**Line-item push**:
The claim → Stripe → record flow that aggregates usage into lines and finalizes the Stripe invoice.

**Consolidation**:
Pinning usage lines onto the owner's subscription-renewal invoice instead of minting a standalone
one.

**failed_permanent**:
A usage invoice parked after exhausting its retries; emits `usage.invoice_push_failed_permanent`.

**Platform fee**:
UBB's own charge to the tenant, computed per-product at the tenant's own period close.
(`apps/billing/tenant_billing/`)

## Stripe connector kit (the ADR-001 §5 exception)

**stripe_call**:
The mandatory Stripe API wrapper — maps Stripe errors to domain exceptions, retries idempotently,
and requires an explicit `api_key` so a sandbox flow can never use the live key.
(`apps/billing/stripe/services/stripe_service.py`)

**StripeWebhookEvent**:
The single dedup table shared across both webhook endpoints, so a replayed Stripe event is
deduplicated no matter which endpoint receives it. (`apps/billing/stripe/models.py`)

**AR transition table**:
Stripe's legal invoice-status graph, shared by the webhook fast path and the hourly poller so they
can never diverge. (`apps/billing/connectors/stripe/invoice_routing.py`)

## Read contract & events

**queries.py**:
Billing's plain-data read contract — notably `is_usage_period_closed` (metering consults it before
accepting a backdated `effective_at`) and the live-spend ports.
_Avoid_: importing billing models from another product; go through `queries.py`/`ports`.

**Key events**:
Consumes `usage.recorded` (drawdown); emits `balance_low` (→ auto-top-up), `balance_overage`,
`customer_suspended`, `credit_grant_expired`, `budget.threshold_reached`, `stop.fired`. (The
platform kernel emits `task.limit_exceeded` from the verdict-driven kill flow.)
