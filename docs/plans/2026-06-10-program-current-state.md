# UBB — Program Current State (READ THIS FIRST)

**Date:** 2026-06-10 · **Status:** AUTHORITATIVE — single source of truth for the shipped architecture.

This document describes **what is TRUE today**, on branch `tl-changes-05-06-26`. Where older
design/implementation docs in `docs/plans/` contradict this, **this wins** and those docs carry a
`⚠️ SUPERSEDED` banner pointing here or to the wave/stage that superseded them. No aspirational
language below — only shipped behaviour, verified against code with `file:line` anchors.

> Test/mock caveat stated up front (see §6): the **entire Stripe boundary is MOCKED** in the test
> suite. Green tests prove the **ledger math**, not Stripe behaviour. The one live test ships **unrun**.

---

## 1. What UBB is + the two journeys

UBB is a **usage-based-billing platform** tenants run on top of **their own Stripe account**. UBB owns
the *rating* (cost attribution, margin, the rate-card pricing engine); Stripe owns the *document*
(invoices, PaymentIntents). Two customer journeys:

- **J1 — Cost attribution / margin visibility.** A tenant records usage events; UBB prices each event
  through the rate-card engine (provider cost + billed price), attributes it to the customer (or the
  billing-owner business), and reports per-customer **margin** on an accrual basis. No Stripe required.
- **J2 — Self-serve subscription billing.** A tenant connects their own Stripe (Standard OAuth) and
  UBB orchestrates flat access fee + per-seat + usage. Subscription (access + seats) bills as **one
  Stripe Subscription with multiple items**; usage bills on its **own standalone Stripe invoice**.

Money is **USD micros** (`1_000_000 = $1`; cents = micros / 10_000). Exactly-once is enforced by **DB
unique constraints + `select_for_update` + `StripeWebhookEvent` dedup**, never by trusting Stripe to
de-dupe.

---

## 2. J1 — Cost attribution (current)

- **Choke point:** `UsageService.record_usage` calls `PricingService.price(...)` for every
  event — `apps/metering/usage/services/usage_service.py:65-69`. The caller MAY pass
  `caller_provider_cost` / `caller_billed` to override; otherwise the rate-card engine computes them.
- **The rate-card pricing engine is ALIVE and central** (see §4 Reversal B). Two cards per match —
  a **cost** card and a **price** card — dimensional (matched on provider / event_type / metric /
  tags), versioned with lineage + `as_of` resolution. `apps/metering/pricing/models.py` (`RateCard`),
  `apps/metering/pricing/services/pricing_service.py` (`PricingService.price`, engine version `2.0.0`).
  Per-tenant **markup** is retained as the zero-config default.
- **Billing owner pinned at record time.** Each `UsageEvent` stores `billing_owner_id` resolved via
  `Customer.resolve_billing_owner()` so live drawdown and repair hit the **same** wallet
  (`usage_service.py:76`). Pooled seats draw down the parent business's wallet; control/attribution
  (budget cap, spend counter, margin) stay per-seat.
- **Margin is ACCRUAL / EARNED basis** (see §4 Reversal E). `MarginService.compute_live /
  compute_business / snapshot_customer` use `RevenueService.accrued_subscription_revenue` =
  `manual_revenue_for_window + subscription_nominal_for_window` (the subscription's nominal amount
  pro-rated to the window, NOT the blended paid invoice) — `apps/subscriptions/economics/services.py:27,54,74`,
  `apps/subscriptions/economics/revenue.py:65-68`.
- **Deleted cash-basis methods:** `RevenueService.revenue_for_window` / `stripe_revenue_for_window`
  were **cash-basis** (sum PAID invoices) and have been **DELETED** from `revenue.py` in this branch.
  Do NOT re-create them — wiring cash-basis revenue into margin silently switches revenue recognition
  and double-counts subscriptions against `subscription_nominal_for_window`.

---

## 3. J2 — Subscription billing (current)

### 3a. Stripe Connect = Standard OAuth
The tenant connects **their own** Stripe account via Standard OAuth (`scope=read_write`,
`stripe.OAuth.token`) — `apps/billing/connectors/stripe/connect.py:25-27,37`. UBB stores the
`stripe_connected_account_id` and acts on it with `stripe_account=<acct>`. **Express / `Account.create`
/ platform-of-record was REJECTED** (see §4 Reversal A). The decision record is
`2026-06-09-wave3-stripe-connect-research.md`.

### 3b. One Subscription, multiple items, Basil API
Subscription = **one Stripe Subscription** carrying licensed items: access fee (qty 1) + per-seat
(qty = seats). The Stripe API is pinned to **Basil, `api_version = "2025-03-31.basil"`** —
`apps/billing/stripe/services/stripe_service.py:16`. Sync/webhook code reads the **Basil** shape:
- subscription amounts come from iterating `subscription.items.data[]` + `price` (NOT `.plan`);
- a webhook's invoice→subscription link reads `invoice.parent.subscription_details.subscription`,
  with a legacy `.subscription` fallback — `api/v1/webhooks.py:161-169`.

`TenantBillingPlan.usage_mode` is `invoice_item | none` only (`apps/subscriptions/models.py:84`); it does
**not** route usage onto the subscription invoice (see §4 Reversal C).

### 3c. Usage = its OWN standalone, two-phase invoice
At period close, postpaid usage is billed on a **standalone finalized invoice**, created **two-phase**
— `apps/billing/invoicing/services/postpaid_service.py:158-178`:
1. `stripe.Invoice.create(auto_advance=False)` → a **draft** on the billing owner's customer;
2. `stripe.InvoiceItem.create(invoice=<draft_id>, ...)` for each cent-floored line (sub-cent residual
   carried forward across periods);
3. `stripe.Invoice.finalize_invoice(invoice=<draft_id>, auto_advance=True)`.

Un-pinned pending items would NOT sweep (Stripe default `pending_invoice_items_behavior=exclude`),
which is why the items are **pinned to the draft**. Usage is **never** pinned to the subscription
(`subscription=<id>`). **A postpaid customer therefore receives TWO Stripe invoices per period:** the
subscription renewal (access + seats) and the standalone usage invoice. A business's usage aggregates
one line per seat onto the **business's** single invoice (`postpaid_service.py:15-32`); seats are never
invoiced directly.

### 3d. AR reconcile consolidated on `api/v1`
ALL `invoice.*` events (`paid` / `finalized` / `payment_failed` / `voided` / `marked_uncollectible`)
reconcile on the **api/v1 webhook endpoint**, routed by subscription presence
(`api/v1/webhooks.py:146-150`). The subscriptions endpoint handles `customer.subscription.*` only — its
`invoice.paid` handler was **REMOVED** to avoid double-registration on the shared `StripeWebhookEvent`
dedup table (`apps/subscriptions/api/webhooks.py:87-91`). `/me` invoice visibility is
**billing-owner-gated** (a pooled seat sees the consolidated **business** bill).

---

## 4. Key decisions + the REVERSALS a coder must not re-trip

Each reversal below is a place where an earlier doc says the **opposite** of the shipped code. Know
them cold.

| # | Reversal | OLD (stale) | NEW (shipped) | WHY |
|---|----------|-------------|---------------|-----|
| A | Connect model | Express / `Account.create` / platform-of-record | **Standard OAuth**, tenant's own Stripe | Tenant owns the customer relationship + funds; UBB is not money-custodian. `connect.py:25-27`. |
| B | Pricing engine | "delete ProviderRate / pricing engine; caller provides cost only" (Stage 0) | **Rate-card engine REINSTATED** (two-card cost+price, dimensional, versioned) | The engine is the product's rating core; only the old `ProviderRate` model stayed deleted. `pricing/models.py`, `services/pricing_service.py`. |
| C | Usage invoice routing | usage = `subscription=`-pinned pending InvoiceItem → "one coherent bill" | **standalone two-phase invoice** (draft → pin items → finalize) | Pinning landed usage on the wrong cycle (Wave 4.5) and un-pinned items don't sweep → empty-invoice bug (Wave 5.5). `postpaid_service.py:158-178`. |
| D | Stripe field reads | `subscription.plan.*`, top-level `current_period_*`, `expand=["data.plan.product"]` | **Basil** `subscription.items.data[]` + `invoice.parent.subscription_details` | `.plan` collapses multi-item subs; Basil removed the top-level fields. `stripe_service.py:16`, `webhooks.py:161-169`. |
| E | Revenue basis | cash basis: manual + Σ(Stripe **paid** invoices) | **accrual/earned**: manual + subscription **nominal** pro-rated | Cash basis hid metering COGS + double-counted postpaid usage. `revenue.py:65-68`. `revenue_for_window` / `stripe_revenue_for_window` were DELETED. |

---

## 5. What is DEFERRED (not missing-by-accident)

These are **intentionally unshipped**; do not "fix" them as bugs:

- **Wave 5b — consolidated bill.** True single-invoice consolidation (subscription + usage on ONE
  owned/finalized Stripe invoice) is deferred. Until then, two invoices per postpaid period is
  **correct**. Ref: `2026-06-10-wave5a-ar-visibility-design.md`.
- **Dunning / payment-failed emails.** AR records payment status; customer-facing dunning email flows
  are not built.
- **Allocated seats.** Stage E ships **pooled** money (per-seat control) as default; per-seat
  *allocated* wallets are an opt-in design point, not implemented.
- **`void_invoice` sweep / cleanup.** Stranded-draft voiding beyond the per-push residual logic is not
  implemented.

---

## 6. Honest test / mock boundary + the one launch gate

- **The entire Stripe boundary is MOCKED.** Every passing test constructs synthetic Stripe objects.
  Green suites prove the **ledger math, idempotency keys, and reconcile routing** — they do **NOT**
  prove real Stripe behaviour or that the Basil payload shape matches our field reads.
- **The one live test ships UNRUN.** `apps/billing/invoicing/tests/test_live_stripe_ar.py` is gated
  behind `UBB_STRIPE_LIVE_TEST` + Stripe test-mode creds and is **skipped by default**
  (`test_live_stripe_ar.py:14-17`). It is the only check against real Basil payload drift.
- **Remaining J2 launch gate:** run `test_live_stripe_ar.py` against a real Stripe **test-mode**
  Connect platform to confirm the live Basil `2025-03-31.basil` invoice payload exposes the exact field
  paths the reconcile handlers read (`invoice.parent.subscription_details.subscription`,
  `subscription.items.data[]`). Until that passes against live Stripe, J2 is **ledger-proven, not
  Stripe-proven**.

---

## 7. Where to look (map by concern)

| Concern | File(s) |
|---|---|
| Usage record + pricing choke point | `apps/metering/usage/services/usage_service.py:55-76` |
| Rate-card engine | `apps/metering/pricing/models.py`, `apps/metering/pricing/services/pricing_service.py` |
| Margin (accrual) | `apps/subscriptions/economics/services.py`, `apps/subscriptions/economics/revenue.py` |
| Revenue dead methods (DELETED) | `RevenueService.revenue_for_window` / `stripe_revenue_for_window` — removed from `revenue.py`; do not re-create |
| Stripe Connect (Standard OAuth) | `apps/billing/connectors/stripe/connect.py` |
| Stripe API pin (Basil) | `apps/billing/stripe/services/stripe_service.py:16` |
| Subscription sync (items.data[]) | `apps/subscriptions/` sync + `api/v1/webhooks.py:161-169` |
| Postpaid usage invoice (standalone two-phase) | `apps/billing/invoicing/services/postpaid_service.py:60-178` |
| AR reconcile (consolidated) | `api/v1/webhooks.py:146-...`; retirement note `apps/subscriptions/api/webhooks.py:87-91` |
| Billing-owner resolution / hierarchy | `apps/platform/customers/models.py` (`Customer.resolve_billing_owner`), `apps/billing/accounts.py` |
| Live Stripe gate (unrun) | `apps/billing/invoicing/tests/test_live_stripe_ar.py` |

**Authoritative wave/stage docs** (trust these; older docs carry `⚠️ SUPERSEDED` banners pointing at
them): `2026-06-09-wave3-stripe-connect-research.md` (Standard OAuth), `2026-06-08-pricing-stageA-…`
(rate-card engine), `2026-06-08-pricing-stageB-…` (accrual revenue), `2026-06-10-wave45-postpaid-hardening-…`
(standalone usage invoice), `2026-06-10-wave55-prelaunch-hardening-…` (two-phase pin + Basil routing),
`2026-06-10-wave5a-ar-visibility-…` (AR consolidation + 5b deferral).
