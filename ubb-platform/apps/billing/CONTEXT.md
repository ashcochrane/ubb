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
A wallet op the module declined (the hard floor, insufficient withdrawable, …) — returned as a
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

**Wallet policy**:
The family of controls that are POLICY on a customer's wallet rather than a bound on any one
unit of work (`control_family: wallet_policy`; #150 §2.2, slice 6 §5): the two floors, and the
reservation a prepaid start takes. Each lives where it always did — per customer on the billing
profile, tenant-wide on the billing configuration, resolved in billing's read contract — and gained
its family's word in slice 6: their episodes are `wallet_policy` lines on the signal ledger, the
soft floor's pair sits under the `wallet_policy` namespace while the hard floor's stop announces
as the customer's own pair (`customer.stopped` / `customer.stop_cleared`, ADR-0006 §5), and a
hard-floor stop's reason is `hard_floor`.

- **The hard floor (min balance)** — the predetermined line on a wallet's negative balance whose
  crossing fires the customer-wide stop (`customer.stopped`, `reason_code: hard_floor`, the
  control being the billing profile or the tenant configuration that carried the floor) and whose
  re-crossing fires the paired resume (`customer.stop_cleared`) the moment the balance recovers,
  from any clearing path. A signal point, not a wall — events past it still land and bill, and the
  balance keeps showing reality. (`apps/billing/queries.py:get_customer_min_balance`,
  `get_customer_floor_control_id`)
- **The soft floor** — the second, higher line of the pair: a tenant-chosen wind-down line per end
  customer (customer override → tenant default; null = no soft floor; always resolving at or above
  the hard floor). Past it, NEW top-level starts are refused (`soft_floor_reached`) while running
  work — and contained starts under a still-active parent — complete. Crossing and re-crossing
  fire the `wallet_policy.soft_floor_crossed` / `wallet_policy.soft_floor_cleared` pair through the
  ledger's `soft_floor` line (durable lane only — no Redis threshold; signal latency is outbox
  latency). Never a stop and never an ack change: acks never change on a soft-floor crossing,
  events are never tagged, and work slipping past the gate lands and bills.
  (`apps/billing/queries.py:get_customer_soft_min_balance`)
- **The reservation** (#461, the half of the affordability test #139 §4.1 decided and nothing
  had built) — at a prepaid customer's start of a kind of work sold at one agreed price, a durable
  `WalletReservation` row keyed on the unit is written for the pinned price, under the owner's
  billing lock and in the start's own transaction, after the unit's row exists. **Affordability is
  `balance − open reservations`**, tested against the same two floors and never a new threshold,
  so a start that would leave the available amount past a floor is refused with
  `insufficient_funds` (or `soft_floor_reached`, at the altitude the soft floor reads). Event-priced
  work and a postpaid tenant reserve nothing. Every terminal transition — a close, a kill, an expiry
  and each of the three cascades — releases it through the kernel's terminal-transition listener
  registry (`apps/platform/work/hooks.py`; billing registers
  `release_on_terminal_transition` in `WalletsConfig.ready()`), a notification the kernel makes
  inside the transition and that can never veto it; an hourly sweep releases whatever a failed
  listener left behind (why the brief window between the delivered close's release and the
  Charge's drawdown is tolerated is ADR-0014 §4). The customer's Billing tab shows the reserved
  and available amounts beside the balance (#468).
  (`apps/billing/wallets/reservations.py`;
  `apps/billing/gating/services/risk_service.py:RiskService.reserve_agreed_price`)

_Avoid_: "credit limit" and "suspension threshold" for the hard floor — suspension is a reaction to
the crossing, not the floor's meaning; treating the soft floor as a stop signal — `stop=true` keeps
meaning a stop line was reached, never the wind-down line; a new threshold for the reservation —
it is judged against the floors that already exist; and the retired per-task floor snapshot (see
below), which was a third floor and is not coming back.

**Floor snapshot (removed)**:
A per-task snapshot (`Task.floor_snapshot_micros`, fed by
`BillingTenantConfig.default_task_floor_snapshot_micros`) that used to kill an individual task when
the balance FROZEN AT TASK START fell past it — deleted on `feat/billing-surface-correctness` in
favor of the existing **customer-wide stop flag**. Two problems, not one: it compared against a
tenant-wide CONSTANT, never the customer's real `CustomerBillingProfile.min_balance_micros`, and it
compared against a balance snapshot that never moved — so it was blind to a mid-task top-up and
could kill a task for a customer who had just paid. The durable drawdown lane already detects the
real floor crossing and fires the customer-wide stop (`reason_code: hard_floor`), the correct
wallet-wide scope for what is a wallet-wide fact; there is no per-task floor line to reintroduce.
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
guard does not (and must not) touch them: **`CustomerSpendPool`** — a pool declared on a seat
bounds the seat's own charges, on purpose (see **Customer spend pool**) — and **audit records**, where the seat stays the named subject of the
action even when the money moved on the owner's wallet. Anything else that legitimately needs a
seat id would need a deliberate, named allowlist entry, not a silent pass.
_Avoid_: adding a new exception to the guard without recording it here and in the guard's own
docstring — the guard's whole value is that its exception set is small, named, and closed.

## Spend control

Two of the four spend-control families live here — the **Customer spend pool** and
**Wallet policy**; the Ceiling and Admission control are the kernel's (`apps/platform/CONTEXT.md`),
and the four families, their homes and the one channel a billing-side control uses to reach a kill
are ADR-0014.

**Start-gate (spend gate)**:
What runs before a unit of work is registered, in the order the composition layer runs it
(`api/v1/task_endpoints.py`; ADR-0011 §1 — registering work is its own route at the root, and the
money-shaped checks run INSIDE it, conditioned on the tenant having a wallet regime rather than on
a product flag at the door):

1. **The claim.** A repeated `idempotency_key` answers the unit it already started and consumes
   nothing below.
2. **Admission control — the kernel's, for every tenant** (#462, slice 6 §6;
   `apps/platform/work/admission.py`): the per-seat bound on new top-level starts
   (`Tenant.max_task_starts_per_minute`, `rate_limit_exceeded` with retry information), then the
   customer's standing — suspended (`customer_stopped`) or closed (`account_closed`). The rate
   first, so a customer both stopped and over the rate is told the answer that changes on its own
   within a minute. A tenant that does not bill through UBB gets both; until #462 neither ran for
   it, because both sat inside the money verdict below.
3. **The money-shaped verdict**, for a tenant with a wallet regime only (`RiskService.check`,
   `apps/billing/gating/services/risk_service.py`): the standing again, worded by the line
   holding the customer (the advisory read's first answer); the stop flag in force (enforcing
   tenants); then the hard floor and the soft floor (top-level starts only) on `balance − open
   reservations`; then the seat-level **Customer spend pool**. Asking it consumes nothing — the
   advisory `GET /billing/customers/{id}/affordability` read (#463) answers from the same code.
4. **The shape of the work** — a parent that is not running, a depth work cannot nest to — refused
   by the kernel under the parent's own lock, in the registry's words (`parent_task_not_active`,
   `subtask_depth_exceeded`), sourced from `core.vocabulary` on both sides of the boundary.
5. **The reservation**, last, after the row is written and the price pinned
   (`RiskService.reserve_agreed_price`; see **Wallet policy**) — the one money question that
   needs the price, and a refusal here rolls the whole start back.

Every refusal is one vocabulary — the registry's `affordability_reason`, nine known values held
whole in `apps/billing/gating/models.py:AFFORDABILITY_REASONS` and produced by constant on
both sides (#463). Refusing a start is legitimate under the one-rule model: it refuses work that
hasn't happened, never a usage report.
A per-owner cap on work already running sat beside `check` until #455 and is DELETED, not narrowed
(#150 §12.5; the reasoning is ADR-0014 §1). Admission control bounds the rate of new work and
nothing else; `check` is now the whole money-shaped answer.
A cost-coverage condition sat in this list until #321 and is gone with nothing in its place: it
refused a COGS-limited start unless the tenant had promised full cost coverage, and #320 made that
promise unkeepable by recording an uncostable event with its cost unresolved rather than counting
it as zero. The ceiling now races a floor, and saying so is a downstream job (#328), not a
start-gate one.
_Avoid_: the retired name for the advisory call — it described a moment in a sequence rather than
the question asked, and #141 retired it outright.

**Live counter**:
THE one module owning every piece of Tier-2 Redis state (#111): the billing-owner-keyed live
balance/spend counters maintained synchronously at record time (so the API response carries a real
stop verdict), the cooperative stop flag, the seat-keyed pool counter
(`ubb:spend_pool:{customer_id}:{YYYY-MM}`, #456), and every key format, Lua script, and TTL
behind them. Interface: `debit · credit · read · reconcile · repair_incr · resume · cleanup ·
spend_pool_incr/read/reconcile`, plus a deliberate TEST-ONLY door (`Door`) for fabricating
counter/flag state. Key formats are frozen once in the module's own pin test; a perimeter walker
(ADR-001 style) keeps the keyspace, the Lua, and the test door private everywhere else. The counter
writes hang off the live-counter-maintenance switch — unmaintained at record time when it is off;
the verdict reads never switch off. Since #459 the debit's owner-level pool leg runs in every
billing mode.
(`apps/billing/gating/services/live_counter.py`;
pins: `apps/billing/tests/test_live_counter_perimeter.py`)
_Avoid_: "live ledger" — "ledger" now means the signal ledger (`StopSignalState`); one word, one
thing.

**Live counter maintenance**:
The per-tenant posture (`Tenant.live_counter_maintenance_enabled`, default ON, read only through
`flags.live_counter_maintenance_on`) governing **real-time counter maintenance** — the synchronous
live-counter write on the recording path, the counter legs of both reconciles, and the upward
repair. It selects WHEN the counters are maintained, never which route an event takes in; that
narrowing is slice 1's (#149 §6.5), which deleted the arrival-time lane the switch once turned off
as one unit, and #246 took the name off the deleted lane and put it on the surviving mechanism.
Two honest latency profiles: ON detects crossings as the event is recorded (stop
latency bounded, independent of drawdown-queue depth — the ≤5s p99 presumes ON); OFF is the
competitor-normal degraded posture — recording does no live-counter Redis work and detection waits
for the durable drawdown, so latency degrades exactly when a runaway spender floods the queue. The
durable lane (signal ledger, patrol, webhook delivery, ack verdicts) never switches off and
maintains the ack-verdict flag in both postures, so flipping never changes the tenant-facing
contract. Flipping either way enqueues an immediate per-tenant reconcile: OFF→ON re-seeds honest
counters, and ON→OFF has nothing to drain, because nothing on the recording path was ever deferred.
_Avoid_: a `products` entry — products gate ACCESS (403s); this is a behavior posture, meaningful
only when enforcing; reading the column anywhere but the flags module; "arrival signals" and "fast
lane" — both name an ingest lane deleted in slice 1, and this switch never was that lane's switch
(#246 retired both words, registry-enforced).
(`apps/platform/tenants/flags.py:live_counter_maintenance_on`)

**Customer-wide stop flag**:
The cooperative, owner-keyed Redis flag set when a live counter reaches a stop line — the wallet's
hard floor, or the pool's stop line at either level; it blocks new task starts until recovery —
usage reports keep landing and billing.
Paired with resume: the moment every open stop line has cleared, the flag lifts and
`customer.stop_cleared` fires, closing the last episode (a customer held by its pool and by its
floor at once stays flagged until both clear, #458). The flag is the fast READ surface (ack
verdicts) only — emission dedup lives on the signal ledger. Durable truth owns it: the hourly
patrol re-aligns an orphaned or missing flag to the ledger's stop lines' durable state within one
interval.

**Signal ledger (`StopSignalState`)**:
The durable per-owner-per-line state row every stop/resume emission routes through — keyed by
`(owner, control_family, reason)` since #458, the third column being the line's own name: the wallet policy's `hard_floor` and the customer
spend pool's `customer_spend_pool` are the two STOP lines (each named by the `reason_code` its
stop carries; each opens the customer-wide stop state; two open episodes clear independently), and
the wallet policy's `soft_floor` is the wind-down SIGNAL line, never a stop. Only the winning
transition emits (atomically with the row), so a crossing observed by the fast Redis lane, the
durable drawdown handler, and reconcile signals exactly once. Its `episode_seq` is the STOP
EPISODE id — a stop opens episode N, the paired clear closes it — which stop-context tagging and
Stops and breaches key on; `control_id` records the row that declares the control whose line it
is (the pool row; the billing profile or tenant configuration that carried the floor), so the
episode's announcement and every re-mint of it name the same control; `clear_reason` is why the
last clearing transition happened. Suspension rides the same winning stop transition, so a stop
line and suspension can never disagree or double-fire. Each winning transition also stamps
`announce_outbox_id` (the row's last announcement) inside the same atomic unit — see Announcement.
Until #458 the two stop lines were one row under a local family word, told apart by the owner's
tenant billing mode.
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
of the reconcile beat (no scheduled task of its own; since #452 the beat visits every tenant, and
only the ceiling's two legs — the sweep of work at or past its ceiling and the re-mint of a
stopped unit's dead-lettered announcement — run for a tenant whose enforcement switch is `off`,
because declaring a ceiling is itself the opt-in; the signal legs and the repair stay enforcing
tenants only). Per pass: drives
missed signal transitions in both directions for the ledger's three lines, re-aligns the fast
stop flag to durable truth, re-mints unannounced signal rows and killed tasks as fresh
current-state events (`re_announcement: true`, bottom line only), sweeps active work at or past
its COGS ceiling — and active work under an open pool line (#459) — into the idempotent kill flow,
and runs the upward live-balance repair.
Outcomes land as day-bucketed counters, read through `apps.billing.queries.get_patrol_stats`.
Worst-case emission latency after a crash: one patrol interval plus the delivery retry schedule.
_Avoid_: a separate patrol schedule — the reconcile pass IS the patrol; touching the shared
outbox retry/dead-letter policy — the patrol re-mints around a dead-lettered row, never mutates it.
(`apps/billing/gating/patrol.py`)

**Enforcement mode**:
Two positions — `off` / `enforcing` — and since #452 it governs the CUSTOMER-WIDE family only:
the live counters and their crossing checks, the hard floor's signal, the signal ledger and its
re-mint, the stop flag and the suspension fold, the start-gate's stop-flag and soft-floor refusals,
the customer-scope entries of a stop context, and the ANNOUNCEMENT of an expiry. When `off`, all of
that is byte-for-byte a no-op. The Ceiling is NOT governed — declaring a ceiling is itself the
opt-in (#150 §11.2): the COGS compare and kill, the ack's stop verdict, the unit-scope stop
context and the patrol's ceiling legs run for every tenant; both expiry ladders are climbed for
every tenant too, but the announcing reaper is enforcing-only, so under `off` an expiry lands
later and silently, through the one-hour safety net.
(`apps/platform/tenants/flags.py:enforcing`)
_Avoid_: a second enable flag — this is the single switch (it IS the tenant's `enforcement_mode`);
a middle "compute but never act" mode — the one honest question is whether the signal suite is on;
reading `off` as "no spend control" — a declared ceiling still stops work.

**Customer spend pool**:
A bound on one customer's charges over a period — the family's name on every surface since #456
(`control_family: customer_spend_pool`; `apps/billing/gating/models.py:CustomerSpendPool`,
routes `/billing/customer-spend-pool` for the tenant default and
`/billing/customers/{id}/customer-spend-pool` + `/status` for a customer's own, audit action
`customer_spend_pool.set`, event `customer_spend_pool.threshold_reached`). A row on a customer is
that customer's pool; a row with no customer is the tenant default, and it applies to **seats
only** — every customer that is not a business, with its own row (even an inert zero one)
shadowing it (`CustomerSpendPoolService.resolve_config_for`): a business with no row of its own
has no pool, so one configured number never becomes two lines at two altitudes. The level needs no
column: a row on a business is the owner-level pool, a row on a seat the seat-level pool, and for
a standalone customer the two coincide.

**Two levels, two counters** (#150 §7.3; #459). A unit's charges count toward its SEAT's pool and
its BILLING OWNER's pool where each exists:

- `ubb:spend_pool:{customer_id}:{YYYY-MM}` — SEAT-keyed, fed by the drawdown handler once per
  posting and MAX-merged toward the seat's own durable charges. Drives the start-gate
  (`CustomerSpendPoolService.check`), the threshold alerts, and the seat-level stop, detected on
  the drawdown and settled by the seat-level beat.
- `ubb:livespend:{owner}:{YYYY-MM}` — OWNER-keyed, fed by the recording lane and MAX-merged toward
  the owner-aggregated durable charges. Drives the owner-level crossing on the live counter's pool
  leg, settled by the owner-level pass of the hourly reconcile.

They were not collapsed when owner == seat because conditional key identity is a footgun — a seat
adopted into a business mid-month would silently change which key its spend lives under — and
because they are different aggregates with different merge semantics.

**Enforcement is payment-mode independent** (#150 §7.1; slice 6 §4 — a RULING, built by #459).
`enforce_mode` is the registry's closed pair (`spend_pool_enforce_mode`: `alert_only` announces
the levels and never stops; `blocking` announces AND stops), and a blocking pool stops a prepaid
customer exactly as it stops a postpaid one — payment mode decides who invoices, nothing else. On
the pool line's winning stop transition every active unit of the stopped customer is killed
through the kernel's `TaskService.kill_and_announce` (`reason_code: customer_spend_pool`,
`trigger_source: pool_crossing`, `control_id` = the pool row) — billing imports the kernel, never
the reverse — and the next start is refused (`customer_spend_pool_exceeded`;
`customer_spend_pool_unavailable` when the store is away and the read fails closed, the pool
row's own `fail_closed` first, else `RiskConfig.gate_fail_closed`, the one column that row keeps).
**Known-over fires on a pair** (#150 §4.2): the pool's durable basis is the resolved period
charges beside the count of postings whose customer price UBB could not resolve
(`period_basis`; the status route publishes the same pair) — known at or over the line blocks,
known below with unknowns present alerts and never blocks, and nothing sums an unknown as zero.
**Each Charge counts once**: ADR-0013 makes a delivered fixed-price unit's Charge → posting →
`usage.recorded` chain 1:1, and a replayed close writes no second Charge. The compare is
`core/crossing.py`'s (`spend_pool_stop_line`, `spend_pool_stop_threshold`,
`spend_pool_assessment`), shared with the console's mirror. The customer's Billing tab renders the
pool under its name, the level in words and the mode as the catalogue word (#468).
(`apps/billing/gating/services/customer_spend_pool_service.py`; the Charge-counted-once and
every-mode pins are `apps/billing/gating/tests/test_a_blocking_pool_stops_prepaid_work_as_it_stops_postpaid.py`)
_Avoid_: the retired family word — a word for money set aside, which this is not; assuming a
blocking pool only refuses starts on prepaid — since #459 it stops running work in every mode;
"fixing" the seat/owner divergence by pointing both counters at one key — that reintroduces the
mid-month-adoption footgun; a compensating Charge decrementing nothing — the day one has a path to
the rails (#472) the period it compensates must have its pool decremented on both counters and in
the durable basis, stated at the service until then.

**Crossing**:
The instant a debit pushes an owner's live counter past its threshold (the hard floor, or a pool's
stop line), setting the stop flag. Cooperative: the crossing event itself still lands and bills.
The compare itself — both sign orientations (wallet balance FALLS below the line, pool spend
RISES over it), the transition/level/recovery forms, the pool stop line's `enforce_mode`
semantics (an `alert_only` pool alerts but can never cross, in every lane; a `blocking` pool both
alerts and can cross), and the month label/bounds the crossing is scoped by — has ONE owner:
`core/crossing.py` (#110; moved from this product into the kernel's shared package by #452, so
the kernel's own ceiling compare could import it rather than keep an inline copy that disagreed).
Every lane (fast, durable, start-gate, reconcile, repair, pool gate, dispute clawback) imports
those predicates rather than re-deriving the comparison, and since #452 so does the unit of
work's COGS ceiling — the recording lane's live compare, the patrol's sweep and the Utilisation
and headroom report — at or above the line, everywhere.
_Avoid_: writing `balance < -floor` / `spend >= cap * pct // 100` inline anywhere — that is the
exact re-sprawl #110 retired.

**Upward repair**:
The patrol's honesty repair of the prepaid live counter (#45): a deficit against the expected
balance (the durable balance, one locked snapshot) past the $1 de-minimis writes a
candidate on one hourly pass and, if the immediately-next pass still measures one, applies
min(first, second) — the amount proven stable across the hour — as a relative increment. A repair
that lifts a wedged stop drives the clearing transition (`customer.stop_cleared`, reason
`balance_repaired`); candidate/repaired/lapsed live on the `LiveBalanceRepair` audit trail, and a
repair-rate spike per tenant per 24h alerts CRITICAL — an epidemic is a bug, never silent
self-healing. The cause it measures (Ruling A2, #233) is a crashed **synchronous** recording
request: the debit is issued after the event row's savepoint but inside the still-open recording
transaction, so a failure before the commit rolls the row back and leaves the debit standing.
Hangs off the live-counter-maintenance switch — the same switch that arms that debit, so the
repair is inert exactly where its cause cannot occur.
_Avoid_: an absolute SET on the counter — unsafe under concurrent traffic; touching the postpaid
spend counter — its drift lane is the MAX-merge + pool reconcile.
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

**Invoice-line grouping**:
The one axis a tenant's usage invoice is broken into lines by — a word of the SAME grouping
vocabulary every analytics surface uses (`field:<declared field>` or `rollup:<axis>`), or empty for
one line per period. It is chosen from the tenant's own discovery contract, reached through
metering's `queries.py` read contract, which is the only channel ADR-001 allows here. A tenant
sends and reads it as `group_by` on the postpaid configuration — ONE axis, where the economic
query's `group_by` is a list, because an invoice line is grouped by exactly one.
(`apps/billing/invoicing/models.py:PostpaidUsageConfig.invoice_line_grouping`)
_Avoid_: the retired free-text key, which named a `Metadata` bag key and otherwise fell through to
the first declared slot — the third of ADR-0005's ad-hoc label reads, and the only one a paying
customer read. **Rollups are actively preferred**: fewer, more meaningful lines.

**Money-only lines**:
The rule that an invoice line exists where a customer owes something. A **waived** charge and every
metered call under a **fixed-price Task** carry no liability, so they produce no line at all — a
fixed-price Task is ONE line, labelled by that Task, and its constituent calls are none. A tenant
still sees the waived money on the exposure report, which is where a decision with a real loss
behind it belongs.
_Avoid_: reading it as "drop the zero rows". It is decided by revenue STATE, never by amount, and
**cost state never delays, blocks or alters a customer-facing line** — an unresolved supplier cost
is read nowhere in building one.

**Invoice-line cardinality warning**:
What UBB tells a tenant, at the moment they choose an axis, when that axis has already recorded more
distinct values than the maximum they declared for it (ADR-0005 D4). A warning and never a refusal —
the cap is a keyspace guard, not an invariant — recorded on the audit feed beside the change that
provoked it.
_Avoid_: deferring it to invoice time, which is the failure it exists to prevent: the first anyone
hears of a 5,000-line invoice should not be the customer receiving one.

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
`customer_suspended`, `credit_grant_expired`, `customer_spend_pool.threshold_reached`,
`wallet_policy.soft_floor_crossed` / `wallet_policy.soft_floor_cleared`, `customer.stopped` /
`customer.stop_cleared` (each carrying `control_family` and `control_id`, #458). (The platform kernel emits `task.killed` from the verdict-driven kill flow, and `task.expired` from
either sweeper — the name carries the state entered, so a subscriber alerting on spend incidents
takes the first without the second.)
