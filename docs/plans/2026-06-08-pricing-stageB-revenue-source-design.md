# Pricing Program — Stage B: Revenue-Source Disambiguation (Detailed Design)

**Date:** 2026-06-08
**Status:** Approved (approach + earned-basis) — pending written-spec review
**Program:** Pricing Cards + Billing Integrity (Stages A–D). **Stage A done.**
**Depends on:** Stage 2 margin engine (`MarginService`, `RevenueService`, `CustomerEconomics`), Stage A rate cards (price cards now make the usage-revenue collision real).

## Objective

Make the margin dashboard **count each revenue stream exactly once** and read **the same regardless of billing timing**, so a tenant can freely combine subscription timing and usage timing (prepaid-sub + postpaid-usage, both-prepaid, both-postpaid, …) and still see consistent, correct margin. This fixes two real bugs in today's `margin = (manual + stripe_paid) + Σbilled − Σprovider`:

1. **Metering-only COGS is invisible.** With no markup `billed == provider`, so `+Σbilled − Σprovider` cancels → `margin = manual_revenue`; the tenant's AI cost is never subtracted (the metering persona's whole value prop).
2. **Postpaid usage is double-counted.** Stage 4 pushes usage as line items onto the customer's Stripe subscription invoice, so the synced `SubscriptionInvoice.amount_paid` already includes usage — which is *also* counted as `Σbilled`.

Both stem from sourcing revenue from Stripe's **blended, timing-sensitive** paid invoice. The fix is to attribute each component from **UBB's own figures** (an *earned/accrual* basis), which is timing-independent by construction.

## The two independent axes (context)

A tenant charges their end-customer two separate things:
- **Subscription** (access + per-seat) = a **Stripe Subscription** the tenant configures. Its charge timing (up-front vs arrears) is a Stripe setting UBB does not execute — UBB reads the mirror. Any subscription timing works for free.
- **Usage** (+ margin) = what UBB executes: `billing_mode=prepaid` draws from credits (Stage 3); `billing_mode=postpaid` invoices at close (Stage 4). So **`billing_mode` is the *usage* timing switch**, independent of the subscription.

All requested combos therefore already execute (Stripe sub of any timing × `billing_mode`). This stage makes the **margin read identically** across them.

## The model (earned / accrual basis)

```
margin = subscription_revenue + usage_revenue − provider_cost

subscription_revenue = manual_revenue (A)
                       + Σ active Stripe subscriptions: (amount_micros × quantity), pro-rated to the window
                       └─ the SUBSCRIPTION's recurring access+seat amount — NOT the blended paid invoice
usage_revenue        = Σ billed_cost_micros (C)   if the customer's usage is billed through UBB
                     = 0                            if metering-only (usage is pure COGS; revenue is manual A)
provider_cost        = Σ provider_cost_micros
```

- **Timing-independent:** subscription comes from the subscription's recurring amount, usage from `Σ billed` (cost + your margin), cost from `Σ provider`. None move with *when* cash is collected, so prepaid-usage and postpaid-usage yield the **same** margin.
- **No double-count:** `subscription_revenue` is access+seats only (the subscription's `amount_micros × quantity`), so postpaid usage riding the Stripe invoice is counted once — as `Σ billed`. Stage 4's one-clean-invoice UX is untouched; only *attribution* changes.
- **COGS visible for metering-only:** `usage_revenue = 0` means usage isn't re-added as passthrough, so `margin = manual_revenue − provider`.

`amount_micros = plan.amount × 10_000` (per-unit micros) and `quantity` = seats (confirmed in `subscriptions/stripe/sync.py:71,77`), so the recurring total is `amount_micros × quantity`, pro-rated over the window by the subscription's `interval` / `current_period`, consistent with how `RevenueService.manual_revenue_for_window` pro-rates by calendar days.

## The discriminator: per-customer `revenue_mode`

A per-customer `revenue_mode` ∈ **`billed` | `metered_only`** decides whether `usage_revenue = Σbilled` or `0`:
- **`metered_only`**: usage is COGS; revenue is the manual `CustomerRevenueProfile` (+ subscription if any). The metering persona.
- **`billed`**: usage billed through UBB (prepaid credits or postpaid invoice) → `usage_revenue = Σ billed`. The integrated persona.

**Default derives from `billing_mode`** (per-tenant), so zero configuration in the common case:
- `meter_only → metered_only`; `prepaid → billed`; `postpaid → billed`.

Stored as a **nullable `Customer.revenue_mode`** override (blank = derive), resolved by `RevenueService.resolve_revenue_mode(tenant, customer)` (`customer.revenue_mode or default_from(tenant.billing_mode)`). The override handles exceptions (e.g. a `postpaid` tenant that hand-invoices one whale customer as `metered_only`).

## Components & changes

- **`RevenueService`** (`apps/subscriptions/economics/revenue.py`):
  - Keep `manual_revenue_for_window` (A).
  - **New** `subscription_nominal_for_window(tenant, customer, start, end)` → Σ over the customer's active `StripeSubscription`s of `(amount_micros × quantity)` pro-rated to the window (mirrors the manual pro-ration). This is the access+seat accrual.
  - **New** `accrued_subscription_revenue(...)` = `manual_revenue_for_window + subscription_nominal_for_window`.
  - `resolve_revenue_mode(tenant, customer)`.
  - Retain `stripe_revenue_for_window` (paid invoices) but it is **no longer used by margin** — it stays available for cash reconciliation (a Stage-D / dashboard concern).
- **`MarginService`** (`economics/services.py`): `_compose` becomes `_compose(subscription_revenue, usage_billed, provider_cost, revenue_mode)`, where `usage_revenue = usage_billed if revenue_mode == "billed" else 0`, `total_revenue = subscription_revenue + usage_revenue`, `margin = total_revenue − provider_cost`. `compute_live` and `snapshot_customer` resolve `revenue_mode`, pull `subscription_revenue` from `accrued_subscription_revenue`, and pass through.
- **`CustomerEconomics`** (`economics/models.py`): add `revenue_mode` (CharField) and `total_revenue_micros` (BigInt) for honest dashboard display (the stored `subscription_revenue_micros` + `usage_billed_micros` + the mode now fully explain the margin). Additive migration.

## API & SDK

- `GET|PUT .../customers/{id}/revenue-mode` (metering-gated, alongside the existing margin/revenue endpoints where `set_customer_revenue` lives) to read/set the override (`billed | metered_only | ""`=derive).
- The margin response (`MarginService.compute_live` output + margin endpoints) surfaces the resolved `revenue_mode` and `total_revenue_micros`.
- SDK: `set_revenue_mode(customer_id, mode)` on the metering client and the fields returned in the margin payload.

## ⚠️ Behavior change to confirm

- Subscription revenue for margin moves from **paid invoices → the subscription's recurring amount (accrual)** — earned, timing-independent (your chosen basis).
- **Existing margin numbers move** (they become correct): metering-only margins drop (COGS now subtracted); postpaid revenue drops (double-count removed). **Prepaid is functionally unchanged** in total, though its subscription component is now accrual not cash. Historical `CustomerEconomics` rows are not auto-rewritten; a tenant can re-run `snapshot_all` to restate a period.

## Decision Log

| # | Decision | Choice | Rationale |
|---|---|---|---|
| 1 | Recognition basis | **Earned / accrual** | Timing-independent; consistent dashboard across combos (user-chosen) |
| 2 | Subscription revenue | **Nominal `amount_micros × quantity` pro-rated** (+ manual) | Excludes usage → no double-count; timing-independent |
| 3 | Usage revenue | **`Σ billed` if `billed` else 0** | Single source of truth; makes metering COGS visible |
| 4 | Discriminator | **Per-customer `revenue_mode`, default from `billing_mode`** | Zero-config common case; override for exceptions |
| 5 | Subscription vs usage | **Independent axes** (`billing_mode` = usage only; sub = Stripe) | Supports all timing combos |
| 6 | Cash/paid invoices | **Retained but unused by margin** (reconciliation only) | Don't lose the data; not the margin basis |

## Risks & mitigations

- **Mis-stating money-adjacent numbers.** The plan leads with golden-value tests per mode (below). The change is confined to revenue composition; cost (`provider`) and usage (`billed`) sourcing are unchanged.
- **Subscription pro-ration edge cases** (annual interval, multiple subs, mid-window period boundaries). Mirror the proven `manual_revenue_for_window` day-based pro-ration; tests cover monthly (full window) + a partial window + multi-subscription.
- **Double-source revenue** (a customer with both manual A and a Stripe subscription for the *same* access fee). Pre-existing assumption (revenue from one access source); documented; the override + `revenue_mode` make intent explicit.

## Acceptance criteria

- **Metering-only** (`meter_only` / `revenue_mode=metered_only`), manual revenue 100, provider 30, billed 30 (passthrough): `margin = 70` (was 100 — bug 1 fixed).
- **Postpaid** integrated with a Stripe sub (nominal S) + usage billed U pushed to the invoice: `margin = S + U − provider`, with the paid invoice (S+U) **not** double-counted (bug 2 fixed).
- **Prepaid** integrated: `margin = (manual + nominal sub) + U − provider`; total unchanged in spirit; subscription now accrual.
- **Same margin** for a customer whether usage is configured prepaid or postpaid, all else equal (timing-independence).
- Default `revenue_mode` derives correctly from `billing_mode`; a per-customer override wins.
- `compute_live` + `snapshot_customer` return/persist `revenue_mode` + `total_revenue_micros`; margin webhooks (unprofitable / spike) still fire off the corrected margin.
- API/SDK round-trip the override; migrations apply on a fresh DB; full platform + SDK suites green.
