# Stage E — Accounts & Seats (Direction Note, not yet a full design)

**Date:** 2026-06-09
**Status:** Direction approved; full design+plan deferred until **after Stage C**.
**Program:** Pricing Cards + Billing Integrity. Sequencing (user-approved): **Stage C → Stage E** (seats rework is orthogonal to C's exactly-once credit; C consolidates the auto-top-up credit so the seats resolver injects cleanly afterward).

## Requirement

A tenant's end-customer can be an **individual** (flat, as today) **or** a **business with seats** managed by a designated **orchestrator**. The orchestrator chooses auto-top-up granularity: **aggregate** (one pooled business balance; top up when the *pool* dips below a threshold) **or** **per-seat** (each seat has its own balance/threshold/top-up).

## How the best platforms do it (research synthesis)

Convergent pattern across AWS/GCP/Azure, OpenAI/Anthropic, Brex/Ramp/Stripe Issuing, telco pooled plans:
1. **One pooled balance at the business level + per-member *limits* (caps), not per-member balances.** A seat cap is a policy gate at spend time (Stripe Issuing `spending_controls`, Brex "Total", Ramp funds), not money set aside.
2. **Spend control is a separate layer from the balance** (Azure: credit "spending limit" = hard gate vs "budget" = alert).
3. **Both modes are a product choice** (OpenAI Teams = N pools vs Enterprise = 1 pool; Brex "individual limits per user" vs "one shared limit").
4. **Auto-reload lives on the pool** (one config) in aggregate mode; **Stripe cannot pool balances** (per-customer only) → the hierarchy lives in UBB's model; Stripe is the funding rail.
5. **Key ledger insight:** "cap against a shared pool" (aggregate) and "allocated sub-balance" (per-seat) are **two ledger topologies**, not a UI toggle.
6. Industry is drifting from per-member **hard** caps → **soft alerts** (Cursor deprecated per-user hard limits Dec 2025) → caps default soft, hard opt-in.

## Chosen model — **Model A** (self-referential hierarchy on `Customer` + one resolver)

- `Customer` gains: `account_type` (`individual` | `business` | `seat`), `parent` (self-FK, set only on seats), `billing_topology` (`pooled` | `allocated`) on the business. Individual = business-of-one (one code path). Validate: seat⇒has parent & no children; business⇒no parent; individual⇒neither.
- **One resolver** `wallet_owner_id(customer)` = parent for a pooled seat, else self. Inject at **four choke points**: `lock_for_billing`, the drawdown handler, `RiskService.check`, the auto-top-up charge/credit. Below the resolver, all existing wallet/lock/exactly-once machinery is **unchanged**.
- **Pooled mode (default):** seats draw the **one business wallet**; the business holds the single `AutoTopUpConfig` + funding card; per-seat runaway caps **reuse the existing per-customer `BudgetConfig`** (Stage 3) keyed on the seat — "pool funds everyone, seat X can't exceed $Y/period" for ~free.
- **Per-seat mode (opt-in):** each seat = today's flat `Customer + Wallet + AutoTopUpConfig`, replicated.
- Seats stay first-class Customers → metering / `external_id` / Stripe-customer / gating keep working; `UsageEvent.customer = seat` → per-seat margin free, business rollup = sum over `parent`.
- **Backward-compatible:** all existing customers backfill to `account_type='individual'`, zero behaviour change.
- Concurrency: existing `select_for_update` on the wallet already serializes pool access (no TigerBeetle needed now; back-pocket for a hot pool).

*(Model B — separate `Account`/`Organization` entity, Customer-as-seat — rejected: same capability, materially larger migration + dual-owner wallet. Reconsider only if a strong non-customer orchestrator identity is wanted.)*

## Blast radius (to design at Stage E)

- **Gate (Stage 3):** resolve the business wallet/threshold + honour the business status for pooled seats; decide rate-limit scope (per-seat vs pool).
- **Auto-top-up (Stage C):** charge/credit the **billing-account** (business when pooled) — same `auto_topup:{pi_id}` exactly-once constraint, resolved wallet/card. The `AutoTopUpConfig`/`TopUpAttempt`/credit key on the billing-account; the "one pending per customer" partial-unique becomes "per billing-account" (correct).
- **Margin (Stage 2):** per-seat free; add business rollup (sum over parent).
- **Postpaid (Stage 4):** invoice the **business** (consolidated; seats as line items via a new `group_by='seat'`); `CustomerUsageInvoice` keys on the business. Individuals as today.
- **API/SDK:** orchestrator endpoints — create business, add/remove seats, set `billing_topology`, set `AutoTopUpConfig` at business-or-seat level + per-seat caps.

## Open decisions for the Stage E design (resolve at design time)

1. Per-seat cap semantics: soft-alert-by-default + opt-in hard (recommended, reuse `BudgetConfig`); recurring vs absolute.
2. Nesting/over-subscription: must Σ(seat caps) ≤ business pool, or allow over-subscription (first-come against the pool)? (Anthropic enforces child≤parent per-limit, not the sum.)
3. Orchestrator identity: a role flag on a seat vs a distinct concept (Model A uses a flag; Model B would model it).
4. Topology immutability: `pooled`↔`allocated` fixed at business creation / immutable once the wallet has balance (else fund-merge/split migration).
5. Suspension semantics for pooled: pool-dry suspends all seats (gate checks business status); a seat hitting its own cap stops only that seat.
6. Stripe ownership: pooled ⇒ card/`stripe_customer_id`/subscription on the business row; allocated ⇒ per-seat.
7. Postpaid invoicing target (business consolidated vs per-seat) + `group_by='seat'`.
8. Migration/defaults: existing customers ⇒ `individual`; API/SDK default stays `individual`.

## Reference

Research workflow: `wf_5baa4a46-571` (3 agents — cloud/AI/telco patterns, fintech/corporate-card pooled-vs-allocated ledgers, UBB rework map). Output archived in the task transcript.
