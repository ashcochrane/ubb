> ⚠️ PARTIALLY SUPERSEDED: the Pricing Program (Stages A–D, `2026-06-08-pricing-stageA-rate-card-engine-design.md`) REINSTATED a full two-card (cost+price) dimensional rate-card engine (`RateCard` + `PricingService`); the slim-markup-only / "do not rebuild rate-cards" stance here is no longer current. Markup is retained as the zero-config default. The rest of the repositioning (boundary, three tenant modes, prepaid-credit reframe) remains the governing architecture. Master truth: `2026-06-10-program-current-state.md`.

# UBB Repositioning — Usage, Spend-Control & Margin Layer in Front of Stripe

**Date:** 2026-06-05
**Status:** Approved (program-level design)
**Scope:** Full repositioning of UBB. This is the **program-level architecture spec** — the connective tissue. Each stage (0–4) gets its **own** detailed design spec and implementation plan before any code is written for it.

---

## 1. Objective & Positioning

Reposition the existing UBB codebase as a **usage, spend-control, and margin infrastructure layer for AI applications** that sits between an AI application and Stripe.

```
AI app ──► UBB ──► Stripe
           │         │
           │         └── invoicing, payment collection, tax, dunning,
           │             customer portal, refunds, disputes, subscriptions/seats
           │
           ├── real-time spend gate (billing tenants only)
           ├── durable usage-event ledger (provider + billed cost + dimensional tags)
           ├── prepaid credit ledger (mirrors money Stripe collected)
           ├── customer-level + dimensional margin intelligence
           └── period-close Stripe push (postpaid mode only)
```

**The line UBB walks:** UBB **never moves money out** (no payouts, no refunds — Stripe does those) and **never holds cash** (funds sit in the tenant's Stripe connected account). UBB maintains a **credit ledger that mirrors money Stripe has already collected**, meters usage, controls spend, and computes margin. This is the same posture Orb and Metronome operate under.

### Why this diverges from the original consultant brief

The consultant brief mandated pure postpaid billing, "never touch money," and deletion of the wallet/top-up system. Market research (Orb, Metronome, Stripe Billing Credits) and the product owner's requirements show that a **prepaid credit model with auto top-ups is the industry standard for AI billing** and is explicitly required here (a localscouta customer must add funds and use the product immediately, with credits drawn down in real time). The consultant's "delete the wallet" instruction is therefore **rejected**; the narrower, correct interpretation of "never touch money" (no outbound money movement, no cash custody) is **adopted**.

---

## 2. Product Boundary (strict)

| UBB owns (everything up to invoice line items / credit drawdown) | Stripe owns (everything money) |
|---|---|
| Usage metering & durable event ledger | Invoice generation, hosted invoice pages, PDFs |
| Real-time spend gate / budget enforcement | Payment collection & card processing |
| Provider-cost & billed-cost tracking | Tax |
| Prepaid credit ledger (drawdown mirror) | Dunning, retries |
| Customer + dimensional margin analytics | Customer portal |
| Markup application (slim, configurable) | Refunds & disputes |
| Period-close usage aggregation (postpaid) | Subscription & per-seat lifecycle |
| Stripe Customer mapping & line-item / credit-grant creation | Money movement & custody |

UBB does **not** build: wallets-as-custody, stored cash, payment processing, card charging, invoice PDFs, hosted invoice pages, tax, refund/dispute handling, dunning, customer portal, full subscription lifecycle, or money movement.

---

## 3. Tenant Modes

Driven by `Tenant.products` plus a new `billing_mode` field.

| Mode | Example | UBB responsibilities | Money collection |
|---|---|---|---|
| **Meter-only** | heyotis | Record usage (provider + billed cost + tags), analytics, margin. **No gate, no money.** | None |
| **Prepaid** (primary) | localscouta | Meter + credit ledger + **real-time gate** + auto-top-up + per-run hard-stops + margin | Stripe collects at **top-up** / **auto-top-up**; UBB draws down credits in real time |
| **Postpaid** (optional, Stage 4) | future | Meter + **period-close usage line-item push** to Stripe + margin | Stripe invoices monthly |

In all paid modes, the **access fee + per-seat charge are a Stripe Subscription** (base price + seat quantity). Stripe bills, prorates, and charges it. UBB only **reads** that revenue for margin and **never stores seat counts or subscription state**.

"Both prepaid and postpaid" is supported as a per-tenant choice, but **prepaid is built first (Stage 3); postpaid second (Stage 4)** — never as a parallel build.

---

## 4. Target Architecture — Three Layers

### Layer 1 — Sync Gate (real-time, billing tenants only)

Answers "can this customer perform this billable action right now?" **before** the expensive provider call. **No per-call cost estimation** — the gate checks *spend-so-far vs. the customer's available credit/budget*, not the cost of the call about to happen.

- Fast **Redis** counter/balance per `(customer, period)`; authoritative ledger is Postgres.
- Returns `allow` / `BudgetExceeded`.
- **Two distinct controls (do not conflate):**
  - **Credit-balance gate (primary, prepaid):** the customer must have remaining prepaid credits. This is the always-on prepaid drawdown check and is what triggers auto-top-up when the balance dips below a target.
  - **Budget cap + thresholds (optional overlay, Metronome-style):** an *optional* per-period spend ceiling, independent of credit balance, that blocks requests and drives the 50/80/100/110% alerts. A prepaid tenant may run with credits only, with a budget cap only, or both. The exact interaction (precedence, denomination, whether thresholds are relative to the cap or to a top-up target) is a **Stage 3 design decision**.
- **Approximate by design:** the single in-flight call that tips a customer over still completes. Acceptable because the durable ledger is exact and reconciles.
- **Fail-open by default** (UBB unavailable ⇒ tenant app keeps working); **fail-closed opt-in** per tenant/customer.
- Multi-threshold alerts: **50% / 80% / 100% warning, 110% hard stop** (configurable), emitted via the outbox → tenant webhooks.
- Per-run / per-workflow hard-stops ("stop the machine whirring") via the existing `Run` + `RunService.accumulate_cost` mechanism, evolved to consult the Redis gate.

*Detailed Redis↔Postgres consistency mechanism (write-through vs. atomic-decrement-and-reconcile vs. pure-Postgres) is an open design decision deferred to the Stage 3 spec, where 2–3 options will be evaluated.*

### Layer 2 — Async Durable Ledger (exact, all tenants)

The existing `UsageEvent` + transactional outbox + `HandlerCheckpoint` infrastructure. The sync gate does **not** wait on durable writes.

- `record_usage(...)` is called **after** the provider call with the **exact** provider cost.
- Writes the immutable `UsageEvent` and an `OutboxEvent` in the same transaction; `on_commit` dispatches a Celery task; the per-minute `sweep_outbox` is the backstop.
- Handlers (product-gated, idempotent via checkpoints): billing draws down credits; subscriptions/economics accumulates cost for margin; tenant webhooks fire.
- `billed_cost = provider_cost × (1 + markup)` computed by UBB by default, overridable per call (hybrid markup).

### Layer 3 — Period / Revenue & Margin

- **Revenue ingestion (read-only):** sync Stripe subscription + seat + invoice revenue so margin = `(subscription + seats + usage billed) − provider cost`.
- **Margin intelligence:** per-customer and per-dimension (model / feature / provider / agent / workflow) margin, unprofitable-customer flags, provider-cost trend, repricing signals.
- **Period-close (postpaid only):** aggregate `UsageEvent`s by `(tenant, customer)`, create idempotent Stripe invoice line items. Prepaid mode needs **no** period-end usage invoice — usage was already paid at top-up.

---

## 5. Keep / Reframe / Delete

### Keep & harden
- `apps/metering/usage/` — `UsageEvent` becomes the hardened durable source of truth.
- `apps/platform/runs/` — `Run` + `RunService.accumulate_cost` → real-time hard-stop / gate primitive.
- `apps/platform/events/` — outbox, `HandlerCheckpoint`, tenant webhooks. Used heavily.
- `core/auth.py` API-key auth + `ProductAccess`; the SaaS substrate.
- `ubb-sdk/` — the primary integration surface.
- Idempotency machinery everywhere.

### Keep & reframe
- `apps/billing/wallets/` → **prepaid credit ledger** (`Wallet`→credit balance, `WalletTransaction`→credit ledger entries). Funded by Stripe, not custody.
- `apps/billing/topups/` → **Stripe-funded top-up + auto-top-up** (charge saved card / checkout to a target when balance dips below threshold — the Orb pattern).
- `apps/subscriptions/economics/` → **revenue ingestion + margin** engine. Drop the lifecycle-management/sync-CRUD parts; keep read-only revenue sync feeding margin.
- `apps/metering/pricing/` → **slim markup**: replace dimensional `ProviderRate`/`TenantMarkup` rate-cards with a simple per-tenant markup, overridable per-customer, with an optional fixed component. Hybrid: computed default + per-call `billed_cost_micros` override.

### Delete (pre-production ⇒ clean removal, no migration scaffolding)
- `apps/billing/invoicing/` native invoice/receipt **generation** — Stripe issues receipts.
- Subscription **lifecycle / sync CRUD** in `apps/subscriptions/` (keep only revenue read).
- Arbitrary Connect **charge plumbing** not needed for top-ups.
- Dimensional rate-card complexity in `apps/metering/pricing/`.

### Stays — separate concern (untouched by this repositioning)
- `apps/billing/tenant_billing/` — how **UBB bills its own tenants** a platform fee (UBB's monetization). Orthogonal to end-customer billing.
- `apps/billing/connectors/stripe/` & `apps/billing/stripe/` — retained as the Stripe integration surface for top-up collection (connected accounts) and platform-fee invoicing (UBB account), pruned of deleted flows.

---

## 6. Core Data Model Deltas (high-level; detailed per stage)

- **`Tenant.billing_mode`** — new field: `meter_only | prepaid | postpaid`. Validated against `products`.
- **`UsageEvent`** — already stores `provider_cost_micros`, `billed_cost_micros`, `pricing_provenance`, `group_keys`, `run` FK, idempotency. Stage 1 hardens: reconsider the 10-key `group_keys` cap for richer dimensional `tags`, add query indexes, possibly `product_id`.
- **Credit ledger** — `Wallet`/`WalletTransaction` reframed; balance is prepaid credits mirroring Stripe-collected funds. Auto-top-up config retained.
- **Credit-balance config** — auto-top-up target/threshold (the prepaid drawdown gate; reframed from the old wallet "min balance floor").
- **Budget/threshold config (optional overlay)** — new per-customer (and per-tenant default) spend-cap + 50/80/100/110% threshold settings powering the optional budget gate and alerts. Independent of credit balance.
- **Revenue mirror** — read-only Stripe subscription/seat/invoice revenue records feeding margin (reframed from `SubscriptionInvoice`/economics).
- **Markup config** — slim per-tenant/per-customer markup (replaces dimensional rate-cards).

---

## 7. Program Decomposition & Sequencing

Order matches the product owner's directive: **metering → margin → billing**. Each stage ships standalone value and de-risks the next. Each gets its own spec + implementation plan.

| Stage | Goal | Ships | Risk |
|---|---|---|---|
| **0 — Reposition & boundary cleanup** | Clean base on the new positioning | `billing_mode`; deletions/simplifications; slim markup; docs/naming | Low |
| **1 — Metering core (heyotis)** | `UsageEvent` as durable source of truth | Dimensional tags, provider+billed cost, provenance, idempotency, query indexes, analytics query API. No money, no gate. | Low |
| **2 — Margin intelligence** | Meter → margin-control system | Revenue ingestion (read-only), per-customer & per-dimension margin, unprofitable flags, provider-cost trends, margin API + webhooks | Low–Med |
| **3 — Prepaid credit billing (localscouta)** | Real-time prepaid spend control | Credit ledger + Stripe top-up/auto-top-up; **Redis gate** (fail-open default / fail-closed opt-in); 50/80/100/110% alerts; per-run hard-stops; slim markup; Stripe Subscription/seats wiring; reconciliation | **High** |
| **4 — Postpaid option + Stripe push** | Postpaid usage billing | `billing_mode=postpaid`; period-close aggregation; idempotent Stripe invoice line items | Med |

**Stages 1 + 2 together constitute a complete, shippable heyotis product.** Stage 3 is localscouta. The Redis gate in Stage 3 is the single hardest component and will receive dedicated design (2–3 mechanisms with trade-offs) before implementation.

SDK changes thread through every stage. The target developer experience:

```python
# Before the expensive provider call (billing tenants):
gate = ubb.check_budget(customer_id="cus_123")      # allow / BudgetExceeded — no cost estimate
if not gate.allowed:
    raise BudgetExceeded

# ... make the AI provider call ...

# After, with the exact cost:
ubb.record_usage(
    customer_id="cus_123",
    run_id="run_456",
    units=1,
    provider_cost_micros=12000,
    # billed_cost_micros optional override; otherwise UBB applies configured markup
    tags={"model": "gpt-4.1", "feature": "property_search", "agent": "research_agent"},
)
```

---

## 8. Honest Risks & Open Questions

1. **Custody / regulatory (audit item #7).** Prepaid credits are stored value. Engineering is not blocked, but counsel should confirm the "Stripe holds cash, UBB holds a mirror ledger, UBB never pays out" framing. Orb/Metronome operate here.
2. **Two billing modes double the surface area.** Mitigation: build prepaid first (Stage 3), postpaid second (Stage 4); never in parallel.
3. **Redis gate consistency (Stage 3).** Redis↔Postgres under fail-open is the riskiest design. Mechanism deferred to the Stage 3 spec with explicit options.
4. **Markup vs. "no pricing engine."** Resolved: keep a *slim* markup (flat % + optional fixed, per-tenant/per-customer, per-call override); do **not** rebuild tiers/graduated/commit rate-cards (that's Stripe/Metronome territory).
5. **Metering tenants cannot be gated.** Confirmed: for meter-only tenants UBB only tracks; it does not stop the tenant's processes. The gate exists only for prepaid (and optionally postpaid hard-caps) tenants.

---

## 9. Decision Log (resolved forks)

| # | Decision | Choice | Rationale |
|---|---|---|---|
| 1 | Markup ownership | **Hybrid** | UBB applies configured markup by default; caller may override `billed_cost_micros`. |
| 2 | Gate timing | **Pre-call budget check (no estimate) + post-call exact record** | Matches "sufficient balance to make the call"; durable ledger stays exact; slippage = one in-flight call. |
| 3 | Margin revenue scope | **Total customer P&L** | Must include subscription + seat revenue, the largest revenue line; requires read-only Stripe revenue ingestion. |
| 4 | Data posture | **Pre-production / no live data** | Clean hard-deletes; no migration scaffolding. |
| 5 | Budget unit | **Meter-only: none (track only); billing: credit balance (currency) + per-workflow hard limits** | Cannot cap a metering tenant's processes; billing tenants gate on prepaid credit balance. |
| 6 | Funding model | **Prepaid credits + auto-top-up (primary); postpaid optional** | Customer adds funds and uses product immediately; credits drawn in real time. |
| 7 | Build order | **Metering → margin → billing** | Each stage standalone value; billing reuses metering+margin foundation. |
| 8 | Credit ledger fate | **Keep & reframe wallets/topups; support both modes tenant-selectable** | Prepaid is industry standard for AI billing; reverses consultant's "delete." |
| 9 | Usage money timing | **Collected at top-up (pure prepaid)** | Immediate product access; real-time drawdown; no period-end usage invoice in prepaid. |
| 10 | Subs & seats | **Stripe owns (Stripe Subscription, base + seat quantity)** | UBB reads revenue for margin; never stores seat/subscription state. |

---

## 10. Non-Goals

Wallet-as-custody, stored cash, payment processing, card charging, invoice PDFs, hosted invoice pages, tax, refund/dispute handling, dunning, customer portal, full subscription lifecycle, money movement, complex pricing tiers / graduated / packages / minimum commits / enterprise contract logic. For enterprise rate-card edge cases, defer to Stripe Prices or Metronome rather than building in UBB.

---

## 11. Next Step

This program-level design is the connective tissue. The immediate next action is to produce the **Stage 0 + Stage 1 detailed designs**, then their implementation plans. No implementation code is written until each stage's plan is approved.

## References

- Orb — [prepaid credits & ledger](https://docs.withorb.com/tutorials/first-custom-credits), [AI founder's guide to prepaid credits](https://www.withorb.com/blog/an-ai-founders-guide-to-prepaid-credits)
- Metronome — [launch prepaid credits](https://docs.metronome.com/launch-guides/prepaid-credits/), [customer spend controls](https://docs.metronome.com/enhance-customer-experience/customer-controls/)
- Stripe — [billing credits / credit grants](https://docs.stripe.com/billing/subscriptions/usage-based/billing-credits/implementation-guide)
