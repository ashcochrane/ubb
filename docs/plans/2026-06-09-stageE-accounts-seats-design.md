# Stage E — Accounts & Seats (Detailed Design)

**Date:** 2026-06-09
**Status:** Approved — proceeding to plan + build.
**Program:** Pricing Cards + Billing Integrity (Stages A–E). **A, B, C done.** (Stage D — overage/reconciliation — follows.)
**Direction note:** `docs/plans/2026-06-09-stageE-accounts-seats-direction.md` (enterprise research + Model A choice).
**Touches:** Stage 1 metering, Stage 2 margin, Stage 3 gate/drawdown, Stage C auto-top-up, Stage 4 postpaid, platform API/SDK.

## Objective

Let a tenant's end-customer be an **individual** (flat, as today) or a **business with seats** managed by an orchestrator, where the orchestrator chooses auto-top-up granularity: **aggregate** (one pooled business balance) or **per-seat**. Built as a low-risk hierarchy + resolver over the existing flat model (Model A), serving the convergent enterprise pattern (pooled balance + per-seat caps; auto-reload on the pool; control separate from balance). The user opted to include the **postpaid consolidated business invoice** in this stage.

## 1. Data model — hierarchy on `Customer`

`apps/platform/customers/models.py` `Customer` gains three additive fields:
- `account_type` — CharField(choices `individual` | `business` | `seat`, default `individual`, db_index).
- `parent` — `ForeignKey("self", null=True, blank=True, on_delete=PROTECT, related_name="seats")` — set only on seats, points at a `business`.
- `billing_topology` — CharField(choices `pooled` | `allocated`, blank default `""`) — set on a `business` (blank on individual/seat).

**Validation** (`Customer.clean()` / service-level):
- `seat` ⇒ `parent` set, `parent.account_type == "business"`, no children, no `billing_topology`.
- `business` ⇒ no `parent`, `billing_topology` in {pooled, allocated}.
- `individual` ⇒ no `parent`, no `billing_topology`, no children.
- `billing_topology` is **immutable once the business wallet has any `WalletTransaction`** (changing it would require a fund migration).

Every existing `Customer` backfills to `account_type="individual"` (migration `default`) → **zero behaviour change**. `external_id` stays tenant-unique for all rows (seats are addressable customers).

## 2. The core principle — *pooled money, per-seat control*

One resolver in `apps/billing` (e.g. `apps/billing/accounts.py`):
```
resolve_billing_owner_id(customer) -> uuid
    = customer.parent_id   if customer.account_type == "seat" and customer.parent.billing_topology == "pooled"
    = customer.id          otherwise   (individual, allocated seat, or business)
```
It governs **money only**: the wallet that is debited/credited, the suspension flag, the `AutoTopUpConfig`, and the Stripe card. **Control + attribution stay per-seat**: the `BudgetConfig` cap, the budget spend counter, the `UsageEvent.customer`, the rate-limit key, and margin attribution all remain keyed on the *seat*. This split is the whole reason the change stays small — below the resolver the money machinery is unchanged; the control machinery never moves.

## 3. Pooled mode (business default)

- **One business `Wallet`** (lazily created on the business row). Seats have no wallet; their drawdown resolves to the business wallet.
- The **business** holds the `AutoTopUpConfig` (threshold + amount), the Stripe `stripe_customer_id` + saved card, and (for postpaid) the `StripeSubscription`.
- **Per-seat runaway caps** = `BudgetConfig` keyed on the *seat* (already per-customer): **advisory by default**, enforcing opt-in. Over-subscription allowed (caps are independent ceilings; the pool is the hard money floor).
- **Suspension:** business pool below `-min_balance` suspends the **business**; the gate gates a seat if the business *or* the seat is suspended. A seat hitting its **enforcing** cap gates only that seat; the pool keeps funding others.

## 4. Allocated (per-seat) mode (opt-in)

Each seat is exactly today's flat `Customer + Wallet + AutoTopUpConfig + card`. `resolve_billing_owner_id` returns self. The business "balance" is a derived sum of its seats (a query, not a spendable pool).

## 5. The four money choke points (resolver injected)

| Site | Money (→ business for pooled seat) | Control/attribution (stays per-seat) |
|---|---|---|
| **Drawdown handler** (`apps/billing/handlers.py`) | `lock_for_billing(resolve_billing_owner_id(seat))` → deduct the business wallet; suspend the business; `BalanceLow` on the business `AutoTopUpConfig` | `TenantBillingService.accumulate_usage` (tenant-level, unchanged); `BudgetService.record_usage_spend(seat, billed)`; `UsageEvent.customer = seat` |
| **Gate** (`RiskService.check`) | affordability reads the **business** wallet + min-balance; status gate honours the **business** status (suspended business gates all seats) | rate-limit key per-seat; `BudgetService.check(seat)` (per-seat cap) |
| **Auto-top-up** (Stage C) | charge the **business** card, credit the **business** wallet; `AutoTopUpConfig`/`TopUpAttempt`/`apply_topup_credit` key on the business; the "one pending per customer" partial-unique becomes "per billing-owner" | — |

The Stage-C `auto_topup:{pi_id}` exactly-once constraint is **unchanged** — only the resolved wallet/card differs. The drawdown handler keeps both ids in scope: the original **seat** `customer_id` (for spend/attribution) and the resolved **business** id (for money).

## 6. Margin (Stage 2) — per-seat free + business rollup

`UsageEvent.customer = seat`, so `get_customer_cost_totals`/`get_per_customer_cost_totals` give per-seat margin unchanged. Add a **business rollup**: a query summing seats (`Customer.objects.filter(parent_id=business)`) + an endpoint `GET /margin/business/{id}` returning the business total + per-seat breakdown. `MarginService.compute_live` is unchanged at the seat level; a thin `compute_business(...)` aggregates. Per-seat `revenue_mode` (Stage B) still applies per seat; the business rollup sums the seats' margins.

## 7. Postpaid (Stage 4) — hierarchy-aware consolidated invoice

The period-close (`close_postpaid_usage_periods` + `PostpaidUsageService`) becomes hierarchy-aware:
- For a **business** (postpaid tenant): aggregate usage across **all its seats** for the period into **one `CustomerUsageInvoice` keyed on the business**, pushed to the **business's** Stripe customer/subscription, with **a line item per seat** (new `group_by` value `"seat"` → groups by the seat's `external_id`, reusing the Stage-4 per-dimension aggregation with the seat as the dimension).
- **Individuals / standalone seats** invoice exactly as today (per-customer).
- The close iterates **businesses** (not their seats) for postpaid usage; a seat is never invoiced directly under a pooled/consolidated business. `CustomerUsageInvoice`'s unique `(customer, period_start)` keys on the business — one consolidated bill per business per period.
- The `Σ line_item == total_billed` invariant holds across the seats of the business.

## 8. API & SDK (the orchestrator)

- `create_customer` (`api/v1/platform_endpoints.py`) gains optional `account_type` + `parent_external_id` (resolved to a `business` parent); default `individual` so existing callers are unchanged.
- New (metering/billing-gated, tenant-authenticated — the tenant *is* the orchestrator acting on the business): `POST /accounts/business` (create business + topology), `POST /accounts/business/{id}/seats` (add seat), `DELETE .../seats/{id}`, `GET /accounts/business/{id}` (business + seats + balances), set business-or-seat `AutoTopUpConfig`, set per-seat `BudgetConfig` cap.
- SDK: `create_business`, `add_seat`, `get_business`, `set_auto_topup`, `set_seat_cap`, + types.

## 9. Migration & backward compatibility

One additive migration (`customers/0011`: `account_type`/`parent`/`billing_topology`). Existing customers → `individual`. The resolver returns self for non-pooled-seats, so **every existing flow (individuals) behaves byte-for-byte as today**; the new behaviour only engages for `business`/`seat` rows.

## Decision Log

| # | Decision | Choice | Rationale |
|---|---|---|---|
| 1 | Model | **Model A: hierarchy on `Customer` + `resolve_billing_owner_id`** | Least disruption; reuses all wallet/lock/exactly-once primitives |
| 2 | Money vs control | **Resolver governs money; control + attribution stay per-seat** | Enterprise principle; keeps the change confined |
| 3 | Topologies | **Pooled (default) + allocated (opt-in), per-business** | User-chosen; both selectable by the orchestrator |
| 4 | Per-seat caps | **`BudgetConfig` on the seat, advisory default, enforcing opt-in** | Reuses Stage 3; matches industry drift to soft-by-default |
| 5 | Over-subscription | **Allowed** (caps independent; pool is the hard floor) | Anthropic-style child≤parent per-limit, not Σ |
| 6 | Suspension | **Pool-dry suspends the business (gates all seats); seat cap gates only the seat** | Pooled money, per-seat control |
| 7 | Stripe ownership | **Pooled ⇒ on the business; allocated/individual ⇒ on self** | Stripe can't pool; the business is the funding/billing entity |
| 8 | Postpaid | **Consolidated invoice on the business; `group_by="seat"` line items** | One enterprise bill, itemised by seat (user-chosen in scope) |
| 9 | Topology mutability | **Immutable once the business wallet has transactions** | Avoids fund-migration |
| 10 | Orchestrator | **The tenant acting on the business via API; no separate identity** | YAGNI |
| 11 | Rate limit | **Per-seat** | Each seat is a Customer; simplest |

## Risks & mitigations

- **Money mis-routing** (a seat's usage hits the wrong wallet, or its spend is counted on the business). Mitigated by the explicit money-vs-control split + tests asserting: pooled seat usage debits the **business** wallet but records spend/`UsageEvent` on the **seat**.
- **Backward-compat regression** for individuals. Mitigated by a backward-compat suite (individuals unchanged) + the resolver returning self for non-pooled-seats.
- **Concurrency on a hot pool** (many seats draining one business wallet). The existing `select_for_update` on the wallet serializes pool access correctly; TigerBeetle remains the back-pocket if a hot pool ever needs it.
- **Topology change after funding.** Blocked by the immutability validation.
- **Postpaid double-invoicing** (a seat invoiced separately *and* in the business roll-up). Mitigated by the close iterating businesses (never their seats) + the `(customer, period)` unique on the business.

## Acceptance criteria

- A pooled business with 2 seats: each seat's usage **debits the business wallet**; `record_usage_spend` + `UsageEvent` are on the **seat**; the business pool funds both.
- The pool dipping below the business threshold fires **one** `BalanceLow` on the business and (Stage C) tops up the **business** card/wallet exactly once.
- The business pool going below `-min_balance` suspends the **business** → the gate denies **all** its seats; a seat's **enforcing** `BudgetConfig` cap denies only that seat while the pool funds the others.
- An **allocated** business: each seat behaves as a flat customer (own wallet + auto-top-up).
- **Individuals** behave byte-for-byte as today (backward-compat suite green).
- Business **margin rollup** = sum of its seats; per-seat margin still correct.
- Postpaid close for a business → **one** `CustomerUsageInvoice` keyed on the business, pushed to the business subscription, with a **per-seat line item**; `Σ line_item == total_billed`; seats are not invoiced separately.
- Orchestrator API/SDK round-trip (create business, add seats, set topology/auto-top-up/caps); migration applies on a fresh DB; full platform + SDK suites green.

## Plan shape (for writing-plans)

Two sequenced implementation plans (each shippable + green):
- **E1 — Hierarchy foundation + money paths + orchestrator API:** the model + migration + `resolve_billing_owner_id` + the four choke-point injections (drawdown, gate, auto-top-up) + per-seat caps + the accounts API/SDK. Backward-compat suite.
- **E2 — Margin rollup + postpaid consolidated invoicing:** the business margin rollup + endpoint, and the hierarchy-aware Stage-4 close (`group_by="seat"`, business-keyed `CustomerUsageInvoice`).
