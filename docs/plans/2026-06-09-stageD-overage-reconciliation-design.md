# Stage D — Overage Policy + Wallet↔Ledger Reconciliation (Detailed Design)

**Date:** 2026-06-09
**Status:** Approved (with explicit correctness requirements — incorporated below). Final stage of the program.
**Program:** Pricing Cards + Billing Integrity (Stages A–E done). **Closes the last audit gaps.**
**Touches:** Stage 1 metering (`record_usage`/`UsageEvent`), Stage 3 drawdown/gate, Stage E hierarchy resolver, the wallet ledger.

## Objective

1. **Trustworthy balances:** if a usage drawdown ever dead-letters, the durable `UsageEvent` exists but the wallet was never charged — and nothing detects/repairs it (today's `reconcile_wallet_balances` compares the wallet to *its own* transaction log). Add a **wallet↔`UsageEvent` repairing reconcile** that treats the durable ledger as the source of truth and applies missing debits **exactly-once**.
2. **A deliberate, observable overage policy:** the tolerated overspend is bounded by `min_balance` (the existing per-customer → tenant-default floor) but the leakage is silently absorbed. Add an **early, transition-safe `billing.balance_overage` event** so a customer crossing into the red is *visible*, not a silent surprise.

## Cross-cutting invariants (the correctness contract)

These are non-negotiable and each maps to a test:

- **I1 — `UsageEvent.id` is the stable, unique billable-event key.** `record_usage` is idempotent on `(tenant, customer, idempotency_key)` → exactly one `UsageEvent` per billable event; its UUID pk is the stable key. The debit's idempotency key is `usage_deduction:{usage_event_id}`.
- **I2 — Conflict = silent no-op, never an error, never a second debit.** A unique violation on `(wallet, idempotency_key)` is caught and read as *already debited*: the `WalletTransaction` insert and the balance/cached-balance decrement are **one savepoint** — a conflict skips **both** (no decrement) and returns cleanly. The catch is the exactly-once guarantee, not a side effect of it. (This hardens the live drawdown too, which today *raises* on raw replay.)
- **I3 — Wrong-basis reuse errors loudly.** If, under the wallet lock, an existing `usage_deduction:{event_id}` debit is found with a **different** amount / currency / wallet than the event's billed basis, it is **not** silently treated as done — it is logged + alerted as a ledger anomaly.
- **I4 — Owner pinned as-of-event-time.** A usage event must always resolve to the **same** wallet for the live debit and any repair. The resolved billing-owner is **stored on the `UsageEvent` at write time** (`billing_owner_id`); the live drawdown and the reconcile both read that pinned value via **one shared resolver** — never re-resolving (so a future seat re-home / topology change can't split live vs repair across wallets).
- **I5 — Separate namespaces for separate operations.** The repair shares the `usage_deduction:` namespace with the live drawdown (that convergence is the point). Refunds/reversals/corrections/adjustments use their **own** namespaces (`stripe_refund:`, `dispute:`, and a future `usage_correction:`) — never the `usage_deduction:` namespace.
- **I6 — Overage event: once, on transition, winning-insert only, atomic.** The `balance_overage` event is `write_event`'d **inside the same atomic block + savepoint** as the debit, **only** when the insert won **and** the balance crossed `≥0 → <0`. Never on the conflict no-op; never while already negative.
- **I7 — Repair is observable, not the normal path.** Every repair is logged + counted + carries a distinct `wallet.drawdown_repaired` signal; the reconcile **alerts on the repair *rate*** (a spike means the live drawdown is broken), not just the count.

## Piece 1 — Convergent, explicitly-linked usage debit

- **Idempotency key → `usage_deduction:{usage_event_id}`** (the `UsageEvent` id, already in the `UsageRecorded` payload as `event_id`). Live drawdown and reconcile share it → the `(wallet, idempotency_key)` unique constraint guarantees exactly one debit (I1, I2).
- **Add `WalletTransaction.usage_event_id`** (UUIDField, nullable, **db_index**) — the explicit, queryable ledger linkage. The live drawdown + the repair both set it. The reconcile **anti-joins on this column** (not by parsing key strings).
- **Conflict-safe debit:** wrap the `WalletTransaction.create` in a nested `transaction.atomic()` savepoint under `lock_for_billing`; `IntegrityError` → already debited → return without decrementing (I2). Before that, a SELECT-under-lock on `usage_event_id` short-circuits the common case and enforces I3 (amount-mismatch → loud).
- **Cutover (I-cutover):** a data migration backfills `usage_event_id` on **existing** `USAGE_DEDUCTION` rows from their `reference_id` (which is the usage-event id today). Because the reconcile anti-joins on the **column**, already-debited old rows are correctly seen as *present* (not "missing") and are **never** re-debited. (We deliberately do **not** rewrite existing rows' idempotency keys — the column is the anti-join; the new key only governs new events + their repairs.)

## Piece 1b — Pin the billing owner on the `UsageEvent`

- **Add `UsageEvent.billing_owner_id`** (UUIDField, db_index), set at `record_usage` time to `resolve_billing_owner(customer).id` (the business for a pooled seat, else self).
- The **resolver moves to the platform layer** (a `Customer.billing_owner_id` property / `apps/platform/customers` helper) so both metering (`record_usage`) and billing (drawdown, reconcile) share **one** implementation; `apps/billing/accounts.py` re-exports it for the Stage-E call-sites (no behaviour change).
- `UsageRecorded` carries `billing_owner_id`; the drawdown debits `lock_for_billing(payload["billing_owner_id"])` (the **pinned** owner, not a re-resolve); the reconcile reads `usage_event.billing_owner_id`. (I4.)
- **Backfill:** existing `UsageEvent`s → `billing_owner_id = customer_id` (all pre-existing customers are individuals → owner == self).

## Piece 2 — Wallet ↔ `UsageEvent` repairing reconcile

New task `reconcile_usage_drawdowns` (`apps/billing/wallets/tasks.py`), hourly:
- **Scope:** prepaid tenants; `UsageEvent`s with `billed_cost_micros > 0`, **settled** (`effective_at` older than a **grace window**) within a bounded **lookback window** (I11). The grace window **must exceed the live drawdown's max retry / dead-letter horizon** so only genuinely-failed drawdowns are repaired (verified at plan time; default conservative).
- **Anti-join:** an event is "missing" if no `WalletTransaction(usage_event_id == event.id, transaction_type="USAGE_DEDUCTION")` exists on `event.billing_owner_id`'s wallet.
- **Repair** (convergent + conflict-safe): `lock_for_billing(event.billing_owner_id)`; if an existing debit is found → I3 amount-check (loud on mismatch) + no-op; else create `WalletTransaction(idempotency_key=f"usage_deduction:{event.id}", usage_event_id=event.id, amount=-billed, ...)` in a savepoint, decrement the wallet, catch `IntegrityError` → already-debited no-op (I2). Same key as live → a late live drawdown can't double-charge.
- **Already-suspended/closed owner (I12):** apply the debit (the money is owed) + record it, but **do not** re-fire `CustomerSuspended` and **do not** fire `balance_overage` — a back-correction must not re-trip live-path signals.
- **Observability (I7):** log each repair, count per run, and **alert on the rate** (a `wallet.drawdown_repair_spike` log/event when repairs exceed a threshold) — a healthy system repairs ≈ 0.
- **Keep `reconcile_wallet_balances`** (wallet vs its own ledger) as a **secondary** integrity check — it catches a different bug class (balance ↔ txn-log divergence).
- **Known gap, made explicit (I9):** the reconcile catches *missing* debits, not *wrong-amount* ones. If `billed_cost_micros` were ever revised **after** the debit landed, neither reconcile catches the shortfall — by design, billed is immutable on `UsageEvent`; any future revision is a separate `usage_correction:` ledger entry (I5), and we log this boundary rather than leave it implicit.

## Piece 3 — Explicit, observable overage policy

- The overage **limit** is the existing `min_balance` (per-customer `CustomerBillingProfile` → tenant `BillingTenantConfig` → 0) — the deliberate, bounded "how far into the red before hard suspension." The gate already enforces it; `CustomerSuspended` already fires at it. Stage D **documents it as the overage policy** (no new knob — it already exists and is configurable).
- **New `billing.balance_overage` event** (`platform/events/schemas.py` + delivery registration): fired in the drawdown's atomic block, on the **winning insert only**, when `old_balance >= 0 and new_balance < 0` (entering overage) — on the **owner** (business) for a pooled seat. Payload: `customer_id` (owner), `balance_micros`, `overage_limit_micros` (the `min_balance`), `overage_micros` (how far below 0). This is the **early warning** before the hard suspend; the leaked overspend is now a recorded, visible event. A **repair** debit (Piece 2) does **not** fire it (I6/I12 — back-corrections aren't live transitions).

## Decision Log

| # | Decision | Choice | Rationale / requirement |
|---|---|---|---|
| 1 | Debit idempotency key | `usage_deduction:{usage_event_id}` | Convergent live+repair exactly-once (I1) |
| 2 | Ledger linkage | New indexed `WalletTransaction.usage_event_id`; reconcile anti-joins on it | Robust + cutover-safe (I-cutover, I11) |
| 3 | Conflict | Savepoint catch → no-op, no decrement | I2 (the guarantee, not a side effect) |
| 4 | Wrong-basis reuse | Loud alert on amount/currency/wallet mismatch | I3 |
| 5 | Owner | Pinned on `UsageEvent.billing_owner_id` at write time; one shared platform resolver | I4 (live + repair same wallet) |
| 6 | Namespaces | Repair shares `usage_deduction:`; corrections/refunds separate | I5 |
| 7 | Overage event | Once, on `≥0→<0` transition, winning-insert, atomic; not on repair | I6 |
| 8 | Repair visibility | Log + count + **rate** alert; distinct repaired signal | I7 |
| 9 | Suspended/closed owner | Repair + record; do **not** re-fire suspend/overage | I12 |
| 10 | Grace window | ≥ live retry/DLQ horizon; bounded lookback | I13/I11 |
| 11 | Wrong-amount-after-debit | Out of reconcile scope; logged boundary; `usage_correction:` namespace | I9 |
| 12 | Auto-repair | Yes (usage happened; safe via convergence) | user-approved |

## Risks & mitigations

- **Double-charge on cutover** — the column-anti-join + backfill (not key rewrite) makes old debits "present"; tested with a pre-existing old-key debit that must NOT be re-debited.
- **Live/repair split across wallets** — owner pinned on the event; tested by changing a seat's parent after the event and asserting the repair still targets the pinned wallet.
- **Repair racing a late live drawdown** — shared key + savepoint no-op; tested (reconcile then live → one debit).
- **Overage spam / wrong-time firing** — transition-safe winning-insert-only + not-on-repair; tested (already-negative deduction → no event; repair → no event).
- **Grace too short** — set ≥ the live retry/DLQ horizon; the rate-alert surfaces if the live path breaks.

## Acceptance criteria

- A dead-lettered drawdown (committed `UsageEvent`, no debit) past the grace window → the reconcile applies **exactly one** debit on the pinned owner wallet; balance corrected; a repaired signal logged/counted.
- Reconcile then a late live drawdown for the same event → still **one** debit (shared key, savepoint no-op).
- A pre-existing old-key `USAGE_DEDUCTION` (backfilled column) → reconcile treats it as present, **no** second debit.
- An existing debit with a mismatched amount → loud anomaly alert, no silent skip (I3).
- Fresh (within-grace) events are **not** repaired.
- `balance_overage` fires **once** on the `≥0→<0` crossing, atomically with the debit, on the **owner**; not while already negative; not on a repair; not on a conflict no-op.
- Repair on an already-suspended owner → debit applied + recorded; **no** re-fired `CustomerSuspended`/`balance_overage`.
- Individuals + postpaid customers behave exactly as today; full platform + SDK suites green; migrations + backfills apply on a fresh DB.
