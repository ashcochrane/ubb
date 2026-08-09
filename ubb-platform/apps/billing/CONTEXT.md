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

**Wallet operation (wallet op)**:
A named, exactly-once money movement on a wallet — debit, credit, withdraw, usage refund,
drawdown, grant mint/void, top-up credit — applied through the single wallet-operations seam,
answered with an outcome: applied, replayed, refused, or noop.
(`apps/billing/wallets/operations.py` — decided in #109, lands with the Wallet module)
_Avoid_: hand-rolling lock/expiry/idempotency at a call site — the seam owns that skeleton.

**Refusal (refused outcome)**:
A wallet op the module declined (overdraft floor, insufficient withdrawable, …) — returned as a
result value carrying a refusal code, never raised, because a refusal still commits the lazy-expiry
side effects it triggered.
_Avoid_: "error" — infrastructure faults raise; refusals return.

**Mirror invariant**:
The rule that every credit-raising wallet mutation schedules a matching live-counter credit on
commit — enforced structurally at the wallet-operations seam, since the MIN-merge reconcile can
never re-raise a missed credit. There is no sanctioned non-ledger credit site: the one that
existed was the reservation lane's settle, removed with it in slice 1 (#239).
_Avoid_: wiring `LiveCounter.credit` by hand at call sites.

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

**Floor snapshot (removed)**:
A per-task snapshot (`Task.floor_snapshot_micros`, fed by
`BillingTenantConfig.default_task_floor_snapshot_micros`) that used to kill an individual task when
the balance FROZEN AT TASK START fell past it — deleted on `feat/billing-surface-correctness` in
favor of the existing **customer-wide stop flag**. Two problems, not one: it compared against a
tenant-wide CONSTANT, never the customer's real `CustomerBillingProfile.min_balance_micros`, and it
compared against a balance snapshot that never moved — so it was blind to a mid-task top-up and
could kill a task for a customer who had just paid. The durable drawdown lane already detects the
real floor crossing and fires `customer_wide_stop`, the correct wallet-wide scope for what is a
wallet-wide fact; there is no per-task floor line to reintroduce.
_Avoid_: re-deriving a task-scoped floor check anywhere — one floor, one crossing, one scope (see
**Customer-wide stop flag**).

**Negative since (aged negatives)**:
`Wallet.negative_since` — when the balance last crossed ≥0 → <0; null whenever the balance is ≥ 0.
Maintained as a sign-consistency invariant by the wallet's own save (every mutation path keeps it
true), surfaced on the balance API and, as an aged-negatives count + max age, on the
`get_negative_balance_stats` read contract (the ops route that used to serve it went with the
ingest pipeline it watched). Purely observational: no reminder events, no auto-close — collections
stay between the tenant, their customer, and Stripe. (`apps/billing/wallets/models.py:Wallet`)
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

## Pooled billing (seats & owners)

**Billing owner**:
The Customer whose Wallet/card/auto-top-up actually funds a given customer's spend — itself,
unless the customer is a pooled SEAT (`account_type="seat"` with a `parent` business whose
`billing_topology` is `"pooled"`), in which case it is the parent business.
(`apps/platform/customers/models.py:Customer.resolve_billing_owner`) A pooled seat has no wallet of
its own; every wallet-mutating path (debit, credit, withdraw, auto-top-up, grants, dispute/refund
clawback) resolves the owner first and moves money there, while the seat stays the named subject of
the request/audit trail.
_Avoid_: passing a seat's id into anything that locks or mutates a Wallet — resolve the owner first.

**NotBillingOwnerError (the seat/owner guard)**:
`lock_for_billing(customer_id)` — the Wallet → Customer lock every money-moving wallet op takes —
refuses any id that is not itself a billing owner, raising `core.exceptions.NotBillingOwnerError`
before taking any lock or lazily minting a wallet.
(`apps/billing/locking.py:lock_for_billing`) Added after the same defect shape turned up seven times
across earlier fixes on this branch: a caller reached the lock with a pooled seat's id, and the
lazy `Wallet.objects.create` silently minted a second, unread phantom wallet on the seat instead of
failing loudly. The guard makes the whole class of bug a hard failure at the first test run instead
of a wallet nothing ever reads.

Two things deliberately still key off the SEAT and never call `lock_for_billing` at all, so the
guard does not (and must not) touch them: **`BudgetConfig`** — budgets cap the seat's own spend, on
purpose (see **Budget**) — and **audit records**, where the seat stays the named subject of the
action even when the money moved on the owner's wallet. Anything else that legitimately needs a
seat id would need a deliberate, named allowlist entry, not a silent pass.
_Avoid_: adding a new exception to the guard without recording it here and in the guard's own
docstring — the guard's whole value is that its exception set is small, named, and closed.

## Spend control

**Start-gate (spend gate)**:
The durable pre-start check — suspension, stop flag, rate/concurrency limits, affordability, the
soft floor (top-level starts only), budget, cost-card coverage — run before a Task is created.
Refusing a start is legitimate under the one-rule model: it refuses work that hasn't happened,
never a usage report.
(`apps/billing/gating/services/risk_service.py`)

**Live counter**:
THE one module owning every piece of Tier-2 Redis state (#111): the billing-owner-keyed live
balance/spend counters maintained synchronously at record time (so the API response carries a real
stop verdict), the cooperative stop flag, the seat-keyed budget counter, and every key format, Lua
script, and TTL behind them. Interface: `debit · credit · read · reconcile · repair_incr ·
resume · cleanup · budget_incr/read/reconcile`, plus a deliberate TEST-ONLY door (`Door`) for
fabricating counter/flag state. Key formats are frozen once in the module's own pin test; a
perimeter walker (ADR-001 style) keeps the keyspace, the Lua, and the test door private everywhere
else. The counter writes hang off the arrival-signals switch — unmaintained at record time when it
is off; the verdict reads never switch off.
(`apps/billing/gating/services/live_counter.py`;
pins: `apps/billing/tests/test_live_counter_perimeter.py`)
_Avoid_: "live ledger" — "ledger" now means the signal ledger (`StopSignalState`); one word, one
thing.

**Arrival signals**:
The per-tenant posture (`Tenant.arrival_signals_enabled`, default ON, read only through
`flags.arrival_signals_on`) governing **real-time counter maintenance** — the synchronous
live-counter write on the recording path, the counter legs of both reconciles, and the upward
repair. It selects WHEN the counters are maintained, never which route an event takes in; that
narrowing is slice 1's (#149 §6.5), which deleted the arrival-time lane the switch once turned off
as one unit. Two honest latency profiles: ON detects crossings as the event is recorded (stop
latency bounded, independent of drawdown-queue depth — the ≤5s p99 presumes ON); OFF is the
competitor-normal degraded posture — recording does no live-counter Redis work and detection waits
for the durable drawdown, so latency degrades exactly when a runaway spender floods the queue. The
durable lane (signal ledger, patrol, webhook delivery, ack verdicts) never switches off and
maintains the ack-verdict flag in both postures, so flipping never changes the tenant-facing
contract. Flipping either way enqueues an immediate per-tenant reconcile: OFF→ON re-seeds honest
counters, and ON→OFF has nothing to drain, because nothing on the recording path was ever deferred.
_Avoid_: a `products` entry — products gate ACCESS (403s); this is a behavior posture, meaningful
only when enforcing; reading the column anywhere but the flags module; "fast lane" as its scope —
the arrival-time lane it once named is gone, and #246 owns the rename that follows.
(`apps/platform/tenants/flags.py:arrival_signals_on`)

**Customer-wide stop flag**:
The cooperative, owner-keyed Redis flag set when the live counter crosses the wallet floor or
budget cap; it blocks new task starts until recovery — usage reports keep landing and billing.
Paired with resume: the moment the balance re-crosses the floor, the flag lifts and `stop.cleared`
fires, closing the stop episode. The flag is the fast READ surface (ack verdicts) only — emission
dedup lives on the signal ledger. Durable truth owns it: the hourly patrol re-aligns an orphaned
or missing flag to the `floor_stop` family's durable state within one interval.

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
`announce_outbox_id`. ANNOUNCED = the stamped event reached terminal success (`processed` — for a
tenant with no webhook config that is vacuous success: no push channel chosen, never re-minted).
UNANNOUNCED = no stamp while signal-bearing, or the stamped row dead-lettered — the
patrol re-mints a fresh current-state event carrying `re_announcement: true` and the current
episode. IN-FLIGHT (`pending`/`processing`) is left alone: at most one live announcement per row.
_Avoid_: replaying the original failed event — a re-mint announces the CURRENT state, bottom-line
only; a `skipped` outbox status (documented for years, produced never) was deleted by #114.
(`apps/platform/events/announcements.py`)

**Patrol**:
The hourly traffic-independent backstop that makes every signal "late, never lost" — the #44 leg
of the reconcile beat (no scheduled task of its own; enforcing tenants only). Per pass: drives
missed signal transitions in both directions for both families, re-aligns the fast stop flag to
durable truth, re-mints unannounced signal rows and killed tasks as fresh current-state events
(`re_announcement: true`, bottom line only), sweeps active tasks at-or-past their
provider-cost limit into the idempotent kill flow, and runs the upward live-balance repair.
Outcomes land as day-bucketed counters, read through `apps.billing.queries.get_patrol_stats`.
Worst-case emission latency after a crash: one patrol interval plus the delivery retry schedule.
_Avoid_: a separate patrol schedule — the reconcile pass IS the patrol; touching the shared
outbox retry/dead-letter policy — the patrol re-mints around a dead-lettered row, never mutates it.
(`apps/billing/gating/patrol.py`)

**Enforcement mode**:
Two positions — `off` / `enforcing`. When `off`, spend control is byte-for-byte a no-op (no
counters, no signals, no tagging); `enforcing` runs the full signal suite + state changes.
_Avoid_: a second enable flag — this is the single switch (mirrors the tenant's `enforcement_mode`);
a middle "compute but never act" mode — the one honest question is whether the signal suite is on.

**Budget**:
A per-tenant (optionally per-customer) monthly spend cap with alert levels.
(`apps/billing/gating/models.py:BudgetConfig`) Two DIFFERENT month-to-date counters read a
`BudgetConfig`, resolved two different ways, and they are deliberately not merged:

- `ubb:budget:{seat}:{YYYY-MM}` — SEAT-keyed. Drives the start-gate (`BudgetService.check`) and the
  threshold alerts. Its config is resolved SEAT-first, tenant-default second
  (`BudgetService.resolve_config_for`) — a seat's own cap always governs the seat's own start-gate,
  never its business's.
- `ubb:livespend:{owner}:{YYYY-MM}` — OWNER-keyed. Drives the postpaid LIVE crossing (the
  customer-wide stop flag). Its config is resolved for the OWNER (`LiveCounter._threshold`) — a
  pooled business's own `BudgetConfig` row, falling back to the tenant default when the business has
  none, but NEVER a seat's row: a business customer's own budget row is what governs the aggregate.

For a standalone customer (owner == seat) these compute the same number twice. For a pooled
business they diverge on purpose: per-seat start caps plus one owner-aggregate stop line. They were
not collapsed when owner == seat because conditional key identity is a footgun — a seat adopted into
a business mid-month would silently change which key its spend lives under, splitting the counter
with no migration path — and because they are different aggregates with different merge semantics:
`livespend` MAX-merges toward the owner-aggregated durable billed total; `budget` MAX-merges toward
the seat's own ledger. They coincide only in the degenerate case.

**Mode split** — why a budget crossing is a wall on postpaid but not on prepaid/meter_only (the
reasoning is who carries the credit risk, which is what makes the asymmetry legible rather than an
inconsistency):

- **postpaid** — the tenant is extending credit, so the budget IS the live stop line: crossing it
  fires the stop flag, the `stop.fired` webhook, and suspension
  (`crossing.budget_stop_threshold`, wired into `LiveCounter._crossed`/`_threshold`).
- **prepaid / meter_only** — the money is already collected and the tenant carries no credit risk,
  so the budget is start-gate only: it refuses NEW task starts and never interrupts running work
  (the live counter's `_threshold` for these modes uses the wallet floor, never the budget, so a
  budget cap cannot enter the live crossing at all in these modes). The wallet floor is the real
  wall here, and it is self-correcting: top up and continue.
_Avoid_: assuming a budget crossing stops anything on prepaid/meter_only — it never does; only the
wallet floor does. "Fixing" the seat/owner divergence by pointing both counters at the same key —
that reintroduces the mid-month-adoption footgun this design deliberately avoided.

**Crossing**:
The instant a debit pushes an owner's live counter past its threshold (wallet floor or
budget cap), setting the stop flag. Cooperative: the crossing event itself still lands and bills.
The compare itself — both sign orientations (wallet balance FALLS below the line, budget spend
RISES over it), the transition/level/recovery forms, the budget stop line's `enforce_mode`
semantics (an `alert_only` budget alerts but can never cross, in every lane; a `blocking`
budget both alerts and can cross), and the month
label/bounds the postpaid crossing is scoped by — has ONE owner:
`apps/billing/gating/crossing.py` (#110). Every lane (fast, durable, start-gate, reconcile,
repair, budget gate, dispute clawback) imports those predicates rather than re-deriving the
comparison.
_Avoid_: writing `balance < -floor` / `spend >= cap * pct // 100` inline anywhere — that is the
exact re-sprawl #110 retired.

**Upward repair**:
The patrol's honesty repair of the prepaid live counter (#45): a deficit against the expected
balance (the durable balance, one locked snapshot) past the $1 de-minimis writes a
candidate on one hourly pass and, if the immediately-next pass still measures one, applies
min(first, second) — the amount proven stable across the hour — as a relative increment. A repair
that lifts a wedged stop drives the clearing transition (`stop.cleared`, reason
`balance_repaired`); candidate/repaired/lapsed live on the `LiveBalanceRepair` audit trail, and a
repair-rate spike per tenant per 24h alerts CRITICAL — an epidemic is a bug, never silent
self-healing. The cause it measures (Ruling A2, #233) is a crashed **synchronous** recording
request: the debit is issued after the event row's savepoint but inside the still-open recording
transaction, so a failure before the commit rolls the row back and leaves the debit standing.
Hangs off the arrival-signals switch — the same switch that arms that debit, so the repair is
inert exactly where its cause cannot occur.
_Avoid_: an absolute SET on the counter — unsafe under concurrent traffic; touching the postpaid
spend counter — its drift lane is the MAX-merge + budget reconcile.
(`apps/billing/gating/repair.py`)

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
A usage invoice parked after exhausting its retries; emits `usage_invoice.push_failed_permanent`.

**Platform fee**:
UBB's own charge to the tenant, computed per-product at the tenant's own period close. The
per-product amounts are summed in exact micros and reach the currency's minor unit exactly once,
at close (R3). (`apps/billing/tenant_billing/`)

**Platform fee carry**:
The sub-minor-unit remainder a period's fee could not bill, banked against the tenant and applied
to the next period's fee — one row per (tenant, period), written at close so a period that never
pushes cannot strand it. Sandbox tenants get no row, since they accrue no fee.
(`apps/billing/tenant_billing/models.py:PlatformFeeCarry`)
_Avoid_: reading it as the postpaid **residual ledger**, which does the same job for usage-invoice
lines but is keyed per customer and reserved/deposited across a push.
(`apps/billing/invoicing/models.py:PostpaidResidualLedger`)

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
