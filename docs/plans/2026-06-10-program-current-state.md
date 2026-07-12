# UBB — Program Current State (READ THIS FIRST)

**Date:** 2026-06-12 (covers the **F-program**, F0–F6) · **Status:** AUTHORITATIVE — single source of truth for the shipped architecture.

This document describes **what is TRUE today**, on branch `tl-changes-05-06-26`, after the
competitiveness program (`2026-06-11-competitiveness-program-plan.md`) shipped F0–F6 on top of the
pre-F0 state this doc previously described. Where older design/implementation docs in `docs/plans/`
contradict this, **this wins** and those docs carry a `⚠️ SUPERSEDED` banner pointing here or to the
wave/stage that superseded them. No aspirational language below — only shipped behaviour, verified
against code with `file:line` anchors.

> Test/mock caveat stated up front (see §7): the **entire Stripe boundary is MOCKED** in the test
> suite, except one gated live test that ships **unrun**. Green tests prove the **ledger math**, not
> Stripe behaviour. J2's launch gate (run the live test) still stands.

---

## 1. What UBB is + the two journeys

UBB is a **usage-based-billing platform** tenants run on top of **their own Stripe account**. UBB owns
the *rating* (cost attribution, margin, the rate-card pricing engine — now including graduated/package
**tiers**); Stripe owns the *document* (invoices, PaymentIntents). Two customer journeys:

- **J1 — Cost attribution / margin visibility.** A tenant records usage events (optionally backdated
  via `effective_at`, optionally in batches of up to 100); UBB prices each event through the rate-card
  engine (provider cost + billed price), attributes it to the customer (or the billing-owner business),
  and reports per-customer **margin** on an accrual basis. No Stripe required.
- **J2 — Self-serve subscription billing.** A tenant connects their own Stripe (Standard OAuth) and
  UBB orchestrates flat access fee + per-seat + usage. Subscription (access + seats) bills as **one
  Stripe Subscription with multiple items**; usage bills by default on its **own standalone Stripe
  invoice** (an **opt-in** consolidation mode can ride usage on the renewal draft — §3c).

Money is integer micros (`1_000_000 = 1 major unit`; cents = micros / 10_000) in the tenant's
`default_currency` — **2-decimal currencies only** (CUR-1, §4f). Exactly-once is enforced by **DB
unique constraints + `select_for_update` + `StripeWebhookEvent` dedup**, never by trusting Stripe to
de-dupe. Every tenant can run a **sandbox** (a sibling tenant addressed by `ubb_test_` keys, §4d).

---

## 2. J1 — Cost attribution (current)

- **Choke point:** `UsageService.record_usage` calls `PricingService.price(...)` for every event —
  `apps/metering/usage/services/usage_service.py:162-167`. The caller MAY pass
  `caller_provider_cost` / `caller_billed` to override; otherwise the rate-card engine computes them.
  Pricing resolves card versions `as_of` the event's `effective_at` (`usage_service.py:160-167`).
- **The rate-card pricing engine is ALIVE and central** (see §5 Reversal B). Two cards per match —
  a **cost** card and a **price** card — dimensional (matched on provider / event_type / metric /
  tags), versioned with lineage + `as_of` resolution. `apps/metering/pricing/models.py` (`RateCard`),
  `apps/metering/pricing/services/pricing_service.py` (`PricingService.price`). Per-tenant **markup**
  is retained as the zero-config default.
- **Tiered pricing (F4.1): graduated + package, PRICE cards only.** `pricing_model` ∈
  per_unit | flat | graduated | package (`pricing/models.py:43-49`; field at `:135`; shape validation
  `validate_tiers` at `:59`). Rating is **marginal over the period's cumulative quantity**:
  `T(q) − T(q − units)` via `RateCard.compute_cumulative` (`pricing/models.py:182`), with the
  per-period cumulative position kept in `PricingPeriodCounter` (`pricing/models.py:230`). Cost cards
  stay per_unit/flat — a hand-crafted tiered cost card fails loudly
  (`pricing_service.py:120-124`). A monthly **re-rate tripwire** `verify_tier_rerate`
  (`apps/metering/pricing/tasks.py:20`, beat: `config/settings.py:249-253`) recomputes the ladder and
  alerts on drift — alert-only, never mutates.
- **Strict coverage rejects units-only events.** With `require_cost_card_coverage=True`, an event with
  `units > 0` and no `usage_metrics` is REJECTED — no metric name means no cost card can match and
  COGS would silently be $0 (`pricing_service.py:110-113`).
- **Caller timestamps + bounded backfill (F4.2).** `record_usage` accepts `effective_at`
  (`usage_service.py:116-120`); validation at the choke point (`usage_service.py:31-69`) rejects
  naive/future timestamps and anything older than `tenant.backfill_window_days` (default 34, max 60 —
  `apps/platform/tenants/models.py:60-64`). A backdate into an already-billed period is refused by the
  closed-period guard `is_usage_period_closed` (`apps/billing/queries.py:54`) — and the postpaid push
  itself carries a frozen-snapshot tripwire for the residual race
  (`postpaid_service.py:142-160`). Accepted backfills write a `BackfillDirtyPeriod` marker
  (`apps/metering/usage/models.py:75`) consumed by `resnapshot_dirty_periods`
  (`apps/subscriptions/tasks.py:116`, beat `settings.py:239-244`) so frozen margin snapshots are
  recomputed. **Batch ingestion:** `POST /usage/batch`, 1..100 independent items, >100 or 0 → 422
  (`api/v1/metering_endpoints.py:184-201`).
- **Billing owner pinned at record time.** Each `UsageEvent` stores `billing_owner_id` resolved via
  `Customer.resolve_billing_owner()` so live drawdown and repair hit the **same** wallet
  (`usage_service.py:131-132,185`). Pooled seats draw down the parent business's wallet;
  control/attribution (budget cap, spend counter, margin) stay per-seat.
- **Margin is ACCRUAL / EARNED basis** (see §5 Reversal E). `MarginService.compute_live /
  compute_business / snapshot_customer` use `RevenueService.accrued_subscription_revenue` =
  `manual_revenue_for_window + subscription_nominal_for_window` (the subscription's nominal amount
  pro-rated to the window, NOT the blended paid invoice) —
  `apps/subscriptions/economics/services.py:27,54,74`, `apps/subscriptions/economics/revenue.py:66-68`.
- **Deleted cash-basis methods:** `RevenueService.revenue_for_window` / `stripe_revenue_for_window`
  were **cash-basis** (sum PAID invoices) and remain **DELETED** from `revenue.py` (0 grep hits).
  Do NOT re-create them — wiring cash-basis revenue into margin silently switches revenue recognition
  and double-counts subscriptions against `subscription_nominal_for_window`.
- **Analytics are index-served (F2).** Day filters use sargable half-open UTC windows
  (`core/time_windows.py:12,16`) instead of `__date` casts; the `tags` GIN index uses `jsonb_ops` so
  `has_key` tag analytics are index-served
  (`apps/metering/usage/migrations/0022_swap_tags_gin_to_jsonb_ops.py`); tag aggregation is pushed
  into SQL via `KeyTextTransform` group-by (`apps/metering/queries.py:29`,
  `api/v1/metering_endpoints.py:8`).

---

## 3. J2 — Subscription billing (current)

### 3a. Stripe Connect = Standard OAuth
The tenant connects **their own** Stripe account via Standard OAuth (`scope=read_write` —
`apps/billing/connectors/stripe/connect.py:54`; `stripe.OAuth.token` — `connect.py:71`). UBB stores
the `stripe_connected_account_id` and acts on it with `stripe_account=<acct>`. **Express /
`Account.create` / platform-of-record was REJECTED** (see §5 Reversal A). The decision record is
`2026-06-09-wave3-stripe-connect-research.md`.

### 3b. One Subscription, multiple items, Basil API
Subscription = **one Stripe Subscription** carrying licensed items: access fee (qty 1) + per-seat
(qty = seats). The Stripe API is pinned to the **canonical Basil form `"2025-03-31.basil"`** —
`apps/billing/stripe/services/stripe_service.py:16-17` (bare `2025-03-31` is not a valid version;
the gated live test asserts the pin — `test_live_stripe_ar.py:27`). Sync/webhook code reads the
**Basil** shape:
- subscription amounts come from iterating `subscription.items.data[]` + `price` (NOT `.plan`);
- a webhook's invoice→subscription link reads `invoice.parent.subscription_details.subscription`,
  with a legacy `.subscription` fallback — `_invoice_subscription_id`,
  `apps/billing/connectors/stripe/invoice_routing.py:80-88`.

`TenantBillingPlan.usage_mode` is `invoice_item | none` only (`apps/subscriptions/models.py:91`); it
does **not** route usage onto the subscription invoice (see §5 Reversal C).

**Lifecycle verbs + plan-price versioning (F5.4).** `POST
/customers/{ext}/subscription/cancel|pause|resume` (`api/v1/platform_endpoints.py:210-244`) map to
`SubscriptionOrchestrationService.cancel/pause/resume`
(`apps/subscriptions/orchestration/service.py:255,300,326`). Editing a provisioned plan fee bumps
`pricing_version` and creates a **new Stripe Price on the same Product**
(`service.py:362-442`; `stripe.Price.create` at `:416`) — new subscribes pick it up, existing
subscriptions are **grandfathered** on their old Price (`apps/subscriptions/models.py:99`) unless
explicitly migrated (`service.py:442`).

**Stripe Tax passthrough (F5.3).** Opt-in `tenant.automatic_tax_enabled`
(`apps/platform/tenants/models.py:52-59`): `automatic_tax={"enabled": True}` is sent at **exactly two
charge sites** — `Subscription.create` and the postpaid usage `Invoice.create`
(`postpaid_service.py:357-359`, and its split-remainder twin `:624-626`). UBB never computes tax;
top-ups/receipts never carry it (wallet credit must equal the charged amount exactly).

### 3c. Usage = its OWN standalone, two-phase invoice — with a bounded, resumable push (F0/F1)
At period close (beat: 1st 00:05 UTC — `config/settings.py:220-226`), postpaid usage is billed on a
**standalone finalized invoice**, created **two-phase** (`apps/billing/invoicing/services/postpaid_service.py`):
1. `stripe.Invoice.create(auto_advance=False)` → a **draft** on the billing owner's customer (`:366-372`);
2. `stripe.InvoiceItem.create(invoice=<draft_id>, ...)` for each cent-floored line (`:438-444`);
3. `stripe.Invoice.finalize_invoice(invoice=<draft_id>, auto_advance=True)` (`:447-450`).

Un-pinned pending items would NOT sweep (Stripe default `pending_invoice_items_behavior=exclude`),
which is why the items are **pinned to the draft**. Usage is **never** pinned to the subscription
(`subscription=<id>`). **A postpaid customer therefore receives TWO Stripe invoices per period** —
unless the tenant opts into consolidation (below). A business's usage aggregates one line per seat
onto the **business's** single invoice (`postpaid_service.py:22-40`); seats are never invoiced
directly, and a row keyed on a seat is superseded by the owner-first re-key
(`postpaid_service.py:109-123`).

**The push is a bounded, resumable state machine (F0.1):**
- State on `CustomerUsageInvoice`: `push_attempts` / `first_attempted_at` / `push_phase` /
  `invoice_kind` / `rebill_generation` / `carry_in_micros`
  (`apps/billing/invoicing/models.py:72-96`).
- **Resume-not-recreate:** the Stripe invoice id is persisted the moment the target is known
  (Phase 2a, `postpaid_service.py:384-391` — an `updated == 0` claim-loss aborts before any item
  create); retries are retrieve-first (`:316-339`), falling back to a deterministic metadata lookup
  (`_find_existing_invoice`, `:672-688`) before ever creating.
- **Bounded:** retries stop at `UBB_POSTPAID_PUSH_MAX_ATTEMPTS` (8) or
  `UBB_POSTPAID_PUSH_MAX_AGE_HOURS` (20) — both inside Stripe's 24h idempotency-key window
  (`settings.py:264-267`; cap check `postpaid_service.py:128-136`) — then park terminally as
  **`failed_permanent`** with an outbox alert (`_park_failed_permanent`, `:61-99`). A
  `StripeFatalError` (void/deleted invoice, auth/config, idempotency mismatch) parks **immediately**
  (`:208-218`).
- **Frozen lines:** the first claim pins the line snapshot; every retry consumes it, with an
  alert-only divergence tripwire (`:142-160`).
- **Rebill generations:** a deliberate void-rebill (`repush_usage_invoice --rebill-void`) rotates
  every idempotency-key family via `-g{rebill_generation}` (`:279-285`) so legacy keys can never
  replay a voided corpse.
- **Owner-first keying:** the row, its unique `(customer, period_start)` constraint and the
  `stripe_customer_id` check all key on the **billing owner** (`:106-110`).

**Sub-cent residuals ride a per-owner ledger (F1.1).** `PostpaidResidualLedger`
(`apps/billing/invoicing/models.py:123`): Phase 1 **reserves** the carry exactly once — take-and-zero
the ledger and PIN it on the row as `carry_in_micros` (`postpaid_service.py:187-198`); Phase 3
deposits the push's residual back (`:253-259`). Order-free across periods; a `failed_permanent` row
keeps its pin PARKED (the cent it funded may sit on a finalized invoice — `:69-72`); an all-sub-cent
period banks the residual and creates **no** invoice (`:302-309`).

**Opt-in consolidated billing (F5.5).** `PostpaidUsageConfig.consolidate_with_subscription`
(`apps/billing/invoicing/models.py:146,153`). When ON, the close (which runs at 00:05, inside the
renewal-draft window Stripe auto-finalizes ~1h after the 00:00 anchor) targets the owner's
subscription **renewal draft** via `apps/subscriptions/ports.get_active_subscription_for_consolidation`
(`postpaid_service.py:455-491`); a draft older than 45 min (`:15-17`) or non-auto-advancing falls back
to standalone. Riding a **foreign** invoice that finalizes on Stripe's clock gets its own safety path
(`_push_consolidated`, `:493-609`): never call finalize on the renewal; if it auto-finalizes mid-push,
**split** — bill only the missing lines on a fresh standalone remainder invoice we control
(`_bill_remainder`, `:611-670`, keys namespaced `-r{target_id}`), so every line lands on exactly one
finalized invoice. **The standalone default did NOT revert** — consolidation sits on top, opt-in.

### 3d. AR reconcile consolidated on `api/v1`, on a shared Stripe-legal transition table (F1.2)
ALL `invoice.*` events (`paid` / `finalized` / `payment_failed` / `voided` / `marked_uncollectible`)
reconcile on the **api/v1 webhook endpoint**, routed by subscription presence (handler map
`api/v1/webhooks.py:419-428`; routing comment `:182-187`). The subscriptions endpoint handles
`customer.subscription.*` only — its `invoice.paid` handler was **REMOVED** to avoid
double-registration on the shared `StripeWebhookEvent` dedup table
(`apps/subscriptions/api/webhooks.py:104-107`). Status writes go through **one** transition table,
`AR_ALLOWED` (`apps/billing/connectors/stripe/invoice_routing.py:59-65`): paid/void are final, but
**`uncollectible` → `paid` is legal** (`:62`) — a late `invoice.paid` applies. Both the webhook
handlers (`api/v1/webhooks.py:238,286`) and the hourly poller backstop
`reconcile_invoice_payment_status` (`apps/billing/invoicing/tasks.py:147`, beat `settings.py:245-248`)
use the same table; the backstop also refreshes rotated hosted URLs on equal-status no-ops
(`invoice_routing.py:72-77`). `/me` invoice visibility is **billing-owner-gated** (a pooled seat sees
the consolidated **business** bill).

### 3e. Prepaid wallets: expiring credit grants (F4.3)
Paid and promo **credit lots** (`CreditGrant`, `apps/billing/wallets/models.py:104`; `kind` at
`:123`) sit under the wallet lock with a lot ledger (`GrantAllocation`, `:167`). Invariants are
**named and fuzzed**: G1 (Σ remaining of active grants ≤ max(balance, 0)) and G2 (per-grant
conservation) — `apps/billing/wallets/grants.py:16-25`, fuzz suite
`apps/billing/wallets/tests/test_grant_invariant_fuzz.py`. Expiry is **lazy + beat**
(`GrantLedger.expire_due`, `grants.py:54`; `expire_credit_grants` task `wallets/tasks.py:178`, beat
`settings.py:156-159`). Dispute/refund clawbacks cascade across lots until G1 holds again
(`grants.py:223-262`); usage refunds are **lot-aware** (restore to the source lot — `grants.py:265`).

---

## 4. Cross-cutting platform capabilities

- **a. Product boundaries are AST-enforced (F3).** The dependency matrix lives in
  **ADR-001** (`docs/architecture/2026-06-12-adr-001-product-boundaries.md`) and is enforced by
  `apps/platform/tests/test_product_boundaries.py` (AST walker over every non-test module under
  `apps/` and `core/`, lazy function-body imports included; failures cite the ADR — `:31`). Products
  talk only via outbox events, the `queries.py` read contracts (`apps/metering/queries.py`,
  `apps/billing/queries.py`), the platform lifecycle hook registry
  (`apps/platform/customers/hooks.py:15`), and per-pair ports (`apps/subscriptions/ports.py`).
  `apps/`/`core/` never import `api.*`. The metering read contract carries all cross-product
  UsageEvent reads (e.g. `get_billed_totals_by_customer` `queries.py:379`,
  `get_customer_billed_breakdown` `:398`, `get_customer_usage_summary` `:177`).
- **b. /me usage summary (F5.1).** `GET /api/v1/me/usage-summary` — month-to-date rollup for end
  customers (`api/v1/me_endpoints.py:382`).
- **c. Self-serve API keys (F5.2).** `GET/POST /tenant/api-keys`, `POST .../{id}/rotate`,
  `DELETE .../{id}` (`api/v1/tenant_endpoints.py:171,183,214,250`) with a last-active-key lockout
  guard (revoking the only active key → 409, `:273-274`).
- **d. Sandbox mode (F4.4).** A sandbox is a **sibling Tenant row** (`is_sandbox` +
  `parent_tenant`, one per parent — `apps/platform/tenants/models.py:65-91`), so tenant-scoped
  isolation/idempotency/rate-limits/beat jobs apply for free. `ubb_test_` keys are **minted on** the
  sandbox tenant (routing at mint time — `TenantApiKey.create_key`, `models.py:149-175`; auth simply
  trusts the key's tenant — `core/auth.py:15-17` — with a mode/prefix cross-check in `verify_key`,
  `models.py:187-193`). `stripe_call` **requires** `api_key` (no default; a forgotten call site fails
  loudly — `apps/billing/stripe/services/stripe_service.py:58-69`), keys are mode-mapped per tenant
  (`api_key_for_tenant`, `:40`), and live webhook endpoints reject `livemode=False` events when a
  test webhook secret is configured (`invoice_routing.py:22-55`; `settings.py:302-308`). Sandbox
  **reset** wipes tenant-scoped rows generically via the app registry — no product imports
  (`apps/platform/tenants/tasks.py:63,114,148`; ADR-001 rule 7).
- **e. Webhook v2 signatures (F5.6).** Outbound tenant webhooks carry
  `X-UBB-Signature-V2: t=<ts>,v1=<hmac over "t.body">` (`compute_signature_v2`,
  `apps/platform/events/webhooks.py:87-92`; headers `:158-159`); the legacy body-only
  `X-UBB-Signature` is still sent during the deprecation window (`:154-156`). The SDK verifies with
  `ubb.webhooks.verify_webhook` (tolerance default 300s — `ubb-sdk/ubb/webhooks.py:30,39-40`;
  `verify_webhook_legacy` kept at `:97`).
- **f. CUR-1 currency integrity.** `tenant.default_currency` is writable
  (`apps/platform/tenants/models.py:49`) but constrained to an **18-currency, 2-decimal allowlist**
  (`SUPPORTED_CURRENCIES`, `models.py:12-20` — every micros↔Stripe conversion assumes a 1/100 minor
  unit; zero-decimal currencies are rejected until CUR-2). Once ANY money exists the currency is
  **locked forever** by the 5-condition check `_currency_locked_reason`
  (`api/v1/tenant_endpoints.py:339-371`): wallet transactions, provisioned plan Prices, pushed usage
  invoices, mirrored Stripe subscriptions, or ACTIVE rate cards (cards are currency-pinned) → 409.
- **g. SDK hardening (F0.5).** All product clients retry idempotent failures:
  `request_with_retry(max_retries=3)` (`ubb-sdk/ubb/retry.py:52`; client defaults
  `ubb/client.py:38`, `ubb/metering.py:39`) with exponential backoff and a server-supplied
  `Retry-After` **capped at 30s** (`retry.py:38-46`) so a hostile header cannot stall the client.
- **h. Reproducible env + CI (F6).** `ubb-platform/requirements.lock.txt` +
  `ubb-sdk/requirements.lock.txt` pin the working set (Python 3.13);
  `.github/workflows/ci.yml` runs `manage.py check`, `makemigrations --check`, the full platform
  suite against postgres:16 + redis:7 services, then the SDK suite. The
  `feat/ubb-ui-dashboard` branch is a READ-ONLY fork — never merge it (decision record appended to
  ADR-001).

---

## 5. Key decisions + the REVERSALS a coder must not re-trip

Each reversal below is a place where an earlier doc says the **opposite** of the shipped code. Know
them cold. **The F-program introduced NO new reversals** — it hardened the existing decisions. In
particular, the standalone-usage-invoice default (Reversal C) **stands**: F5.5 consolidation is
opt-in ON TOP of it, never a return to subscription-pinned pending items.

| # | Reversal | OLD (stale) | NEW (shipped) | WHY |
|---|----------|-------------|---------------|-----|
| A | Connect model | Express / `Account.create` / platform-of-record | **Standard OAuth**, tenant's own Stripe | Tenant owns the customer relationship + funds; UBB is not money-custodian. `connect.py:54,71`. |
| B | Pricing engine | "delete ProviderRate / pricing engine; caller provides cost only" (Stage 0) | **Rate-card engine REINSTATED** (two-card cost+price, dimensional, versioned, now tiered) | The engine is the product's rating core; only the old `ProviderRate` model stayed deleted. `pricing/models.py`, `services/pricing_service.py`. |
| C | Usage invoice routing | usage = `subscription=`-pinned pending InvoiceItem → "one coherent bill" | **standalone two-phase invoice** (draft → pin items → finalize); consolidation only as explicit opt-in via the renewal **draft** (F5.5) | Pinning landed usage on the wrong cycle (Wave 4.5) and un-pinned items don't sweep → empty-invoice bug (Wave 5.5). `postpaid_service.py:360-372,438-450`. |
| D | Stripe field reads | `subscription.plan.*`, top-level `current_period_*`, `expand=["data.plan.product"]` | **Basil** `subscription.items.data[]` + `invoice.parent.subscription_details` | `.plan` collapses multi-item subs; Basil removed the top-level fields. `stripe_service.py:16`, `invoice_routing.py:80-88`. |
| E | Revenue basis | cash basis: manual + Σ(Stripe **paid** invoices) | **accrual/earned**: manual + subscription **nominal** pro-rated | Cash basis hid metering COGS + double-counted postpaid usage. `revenue.py:66-68`. `revenue_for_window` / `stripe_revenue_for_window` were DELETED. |

---

## 6. What is DEFERRED (not missing-by-accident)

These are **intentionally unshipped**; do not "fix" them as bugs:

- **~~Wave 5b — consolidated bill~~ → SHIPPED as opt-in (F5.5).** True consolidation now exists
  behind `PostpaidUsageConfig.consolidate_with_subscription` (§3c). The **default** remains two
  invoices per postpaid period — that is **correct**, not a bug. What remains deferred is making
  consolidation the default.
- **Dunning / payment-failed emails.** Still out — **Stripe owns dunning** (Smart Retries +
  customer emails on the tenant's own account). UBB records AR status (§3d); it does not send
  collection email.
- **Volume pricing.** Graduated (marginal bands) + package shipped (F4.1); **volume** tiers (the
  whole period quantity re-priced at the highest band reached) are deferred — crossing a threshold
  re-rates *already-recorded* events, which is incompatible with per-event marginal rating
  (`T(q) − T(q−units)`) and needs period-end re-rate/credit semantics first.
- **CUR-2 — zero-decimal currencies.** jpy/krw etc. stay rejected
  (`apps/platform/tenants/models.py:12-20`) until a minor-unit helper replaces the pervasive
  `// 10_000` cent conversions.
- **Legacy webhook signature removal.** `X-UBB-Signature` (body-only, replayable forever) is still
  sent alongside v2 during the deprecation window (`events/webhooks.py:154-159`); removal needs a
  receiver-migration window, not code.
- **Allocated seats.** Stage E ships **pooled** money (per-seat control) as default; per-seat
  *allocated* wallets are an opt-in design point, not implemented.
- **`void_invoice` sweep / cleanup.** Stranded-draft voiding beyond the per-push residual logic is
  not implemented (the F0.1 resume machinery makes strands rare: the pointer persists before item
  creates).

---

## 7. Honest test / mock boundary + the one launch gate

- **The entire Stripe boundary is MOCKED.** Every passing test constructs synthetic Stripe objects.
  Green suites prove the **ledger math, idempotency keys, and reconcile routing** — they do **NOT**
  prove real Stripe behaviour or that the Basil payload shape matches our field reads.
- **A missed mock now fails loudly (F0.2).** An autouse fixture forces a sentinel Stripe key and
  blocks Stripe network I/O for every test except the gated live module
  (`ubb-platform/conftest.py:45-70`) — a real key exported in the shell can no longer leak into a
  test run.
- **The one live test ships UNRUN.** `apps/billing/invoicing/tests/test_live_stripe_ar.py` is gated
  behind `UBB_STRIPE_LIVE_TEST` + Stripe test-mode creds and is **skipped by default**
  (`test_live_stripe_ar.py:14-17`). It is the only check against real Basil payload drift — and it
  now **also asserts the canonical API-version pin** (`:27`) plus the B1 empty-invoice and B2
  subscription shapes.
- **Remaining J2 launch gate (unchanged):** run `test_live_stripe_ar.py` against a real Stripe
  **test-mode** Connect platform to confirm the live Basil `2025-03-31.basil` payloads expose the
  exact field paths the reconcile handlers read (`invoice.parent.subscription_details.subscription`,
  `subscription.items.data[]`). Until that passes against live Stripe, J2 is **ledger-proven, not
  Stripe-proven**.

---

## 8. Where to look (map by concern)

| Concern | File(s) |
|---|---|
| Usage record + pricing choke point | `apps/metering/usage/services/usage_service.py:116-185` |
| effective_at validation / backfill window | `usage_service.py:31-69`, `apps/platform/tenants/models.py:60-64` |
| Batch ingestion (≤100) | `api/v1/metering_endpoints.py:184-201` |
| Rate-card engine + tiers | `apps/metering/pricing/models.py` (tiers `:43-49,59,135`; `compute_cumulative:182`; `PricingPeriodCounter:230`), `services/pricing_service.py` |
| Tier re-rate tripwire | `apps/metering/pricing/tasks.py:20` (`verify_tier_rerate`) |
| Margin (accrual) | `apps/subscriptions/economics/services.py`, `apps/subscriptions/economics/revenue.py:66-68` |
| Revenue dead methods (DELETED) | `RevenueService.revenue_for_window` / `stripe_revenue_for_window` — removed from `revenue.py`; do not re-create |
| Sargable day windows | `core/time_windows.py` |
| Stripe Connect (Standard OAuth) | `apps/billing/connectors/stripe/connect.py:50-71` |
| Stripe API pin (Basil) + `stripe_call` | `apps/billing/stripe/services/stripe_service.py:16-17,58` |
| Subscription lifecycle + price versioning | `api/v1/platform_endpoints.py:210-244`, `apps/subscriptions/orchestration/service.py:255-442` |
| Postpaid push state machine (two-phase, bounded, resumable) | `apps/billing/invoicing/services/postpaid_service.py`, `apps/billing/invoicing/models.py:61-120` |
| Residual carry ledger | `apps/billing/invoicing/models.py:123` (`PostpaidResidualLedger`), `postpaid_service.py:187-198,253-259` |
| Consolidated billing (opt-in) | `postpaid_service.py:455-670`, `apps/billing/invoicing/models.py:146-153` |
| AR reconcile + transition table | `api/v1/webhooks.py:419-428`, `apps/billing/connectors/stripe/invoice_routing.py:59-88`, `apps/billing/invoicing/tasks.py:147` |
| Credit grants (lots, expiry, clawback) | `apps/billing/wallets/models.py:104-204`, `apps/billing/wallets/grants.py` |
| Sandbox (sibling tenants, reset) | `apps/platform/tenants/models.py:65-91,149-194`, `apps/platform/tenants/tasks.py:63-148`, `core/auth.py:15-17` |
| Currency integrity (CUR-1) | `apps/platform/tenants/models.py:12-20,49`, `api/v1/tenant_endpoints.py:339-371` |
| /me usage summary | `api/v1/me_endpoints.py:382` |
| Self-serve API keys | `api/v1/tenant_endpoints.py:171-275` |
| Webhook v2 signatures | `apps/platform/events/webhooks.py:87-92,150-159`; SDK `ubb-sdk/ubb/webhooks.py:39` |
| SDK retry | `ubb-sdk/ubb/retry.py:38-52` |
| Product boundaries (AST-enforced) | `apps/platform/tests/test_product_boundaries.py`, `docs/architecture/2026-06-12-adr-001-product-boundaries.md` |
| Billing-owner resolution / hierarchy | `apps/platform/customers/models.py` (`Customer.resolve_billing_owner`), `apps/billing/accounts.py` |
| Live Stripe gate (unrun) | `apps/billing/invoicing/tests/test_live_stripe_ar.py` |
| CI + locked requirements | `.github/workflows/ci.yml`, `ubb-platform/requirements.lock.txt`, `ubb-sdk/requirements.lock.txt` |

**Authoritative wave/stage docs** (trust these; older docs carry `⚠️ SUPERSEDED` banners pointing at
them): `2026-06-11-competitiveness-program-plan.md` (the F-program itself),
`2026-06-09-wave3-stripe-connect-research.md` (Standard OAuth), `2026-06-08-pricing-stageA-…`
(rate-card engine), `2026-06-08-pricing-stageB-…` (accrual revenue),
`2026-06-10-wave45-postpaid-hardening-…` (standalone usage invoice),
`2026-06-10-wave55-prelaunch-hardening-…` (two-phase pin + Basil routing),
`2026-06-10-wave5a-ar-visibility-…` (AR consolidation), `2026-06-12-tiered-pricing-design.md` (F4.1),
`2026-06-12-backfill-batch-design.md` (F4.2), and ADR-001 (boundaries + the
`feat/ubb-ui-dashboard` branch decision).
