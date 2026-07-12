# Wave 5a — J2 AR-Visibility Loop (Design)

**Date:** 2026-06-10 · **Method:** 7-agent research+critique workflow with explicit guardrails against the three prior planning errors (norm drift, Stripe over-optimism, mocked-test dishonesty). **Scope: 5a only** (payment reconcile + hosted invoice link/PDF + `/me` visibility). **5b (owned-finalize one-coherent-bill) DEFERRED** — XL, silent-revenue-stall liability (no Stripe 72h rescue under `auto_advance=false`), and owned-finalize-as-default would be Express-class norm drift (Metronome pushes standalone + listens for status; UBB's current two-invoice state already matches that). 5b, if ever: opt-in per-tenant + hardened watchdog + a live test.

**Why 5a:** today UBB pushes an invoice and **never learns if it was paid** — a correctness/trust gap below every leader (Metronome/Orb/Lago/Chargebee/m3ter all reconcile paid/failed/void + surface a hosted link). 5a is additive, low-risk, and a prerequisite for 5b being worth anything.

**Decisions:** ship 5a / defer 5b; one **gated live Stripe-test-mode test** (opt-in, skipped by default); `/me` = **billing-owner-only**; dunning = **status-only** (badge now, emails deferred); `SubscriptionInvoice` open-row on `finalized`.

---

## ⚠️ Critique must-fixes (baked in — resolve in the plan before any handler code)
- **🔴 C-1 Shared-dedup-table collision.** Both webhook endpoints write the SAME `StripeWebhookEvent` table (unique on `stripe_event_id`), and `STRIPE_SUBSCRIPTIONS_WEBHOOK_SECRET` is **undefined** in settings — the subscriptions endpoint falls back to `STRIPE_WEBHOOK_SECRET` (`endpoints.py:167-168`), so both may consume the SAME Stripe registration. If the same `invoice.*` event is handled on both endpoints, the first wins the dedup row and the second **silently skips**. **FIX (chosen): ONE endpoint owns ALL `invoice.*` reconcile** — the api/v1 billing endpoint (`api/v1/webhooks.py`), which already has the robust `StripeWebhookEvent` dedup + connected-account filtering + handles `invoice.paid` for top-ups. Route inside it by **presence of `invoice.subscription`**: subscription → `SubscriptionInvoice`; no subscription (usage standalone) → `CustomerUsageInvoice`; top-up → `Invoice` (existing). **Remove the subscriptions endpoint's `invoice.paid` handler** (move its `SubscriptionInvoice` logic to api/v1). Document the constraint: "no `invoice.*` type is registered on both endpoints."
- **🔴 C-2 Missing `event.account`→tenant check.** Every `invoice.*` reconcile handler MUST verify the matched local row's tenant `stripe_connected_account_id == event.account` (the api/v1 top-up handler already does; the subscriptions `handle_invoice_paid` does NOT). A coincidental subscription-id/invoice-id match from another connected account must not write a wrong row.
- **Important:** status flips are written **synchronously under `transaction.atomic()` + `select_for_update`** (mirror `lock_invoice`), NOT via `on_commit`; `on_commit` only for dispatching follow-on tasks. Open-row coordination: `invoice.finalized` creates the row (status `open`); `invoice.paid` must **`get_or_create` then UPDATE** if not already `paid` (the existing `get_or_create`-with-`paid`-defaults would GET the open row and never write `paid_at`). `_refresh_urls(local, stripe_invoice)` called **unconditionally at the top of every handler** (re-store `hosted_invoice_url`/`invoice_pdf` whenever non-null — the token rotates on `payment_failed`); guard non-null (void/uncollectible may lack it). `payment_status` defaults **NULL** (not `open`) and is only set when `stripe_invoice_id` is non-empty.
- **Minor:** `/me` gating predicate = `customer == customer.resolve_billing_owner()` (handles individual/business/allocated-seat correctly; pooled seat → empty). Note the pre-existing standalone-finalize orphaned-draft gap (not a 5a regression). Add a mocked test that fires the SAME `event.id` at both endpoints to prove the dedup behavior.

---

## 1. Schema (additive migrations — FIRST, prerequisite)
- **`CustomerUsageInvoice`** (`apps/billing/invoicing/models.py`): add `payment_status` (CharField, null=True, choices `open/paid/void/uncollectible`), `paid_at` (DateTime null), `payment_failed_at` (DateTime null), `hosted_invoice_url` (CharField/URLField blank), `invoice_pdf` (CharField blank); **add `db_index=True` (or a UniqueConstraint) on `stripe_invoice_id`** — a money-state webhook lookup on an unindexed column is unsafe + the polling backstop's prerequisite.
- **`SubscriptionInvoice`** (`apps/subscriptions/models.py`): add `status` (CharField, choices `open/paid/void/uncollectible`, default `open`), `hosted_invoice_url`, `invoice_pdf`. (`stripe_invoice_id` already unique+indexed.) Change the create path so a row is written on `invoice.finalized` (status `open`) — today rows exist only for PAID invoices, so unpaid/open/failed sub invoices are invisible.

## 2. Reconcile handlers (B + C) — on the api/v1 billing endpoint
Register on the api/v1 endpoint's `WEBHOOK_HANDLERS`. Each event's `data.object` is the full invoice (carries `status`, `hosted_invoice_url`, `invoice_pdf`, `lines.data[]`, `amount_paid/due`, `billing_reason`, and the subscription linkage). **Verify under the pinned Basil API (2025-03-31) the exact field path for the subscription** — it may be `invoice.subscription` (string) or `invoice.parent.subscription_details.subscription`; read defensively with a fallback, and the gated live test (§5) confirms it.

| event | action |
|---|---|
| `invoice.finalized` | route by subscription presence; create/locate the row; set status `open`; `_refresh_urls`; (SubscriptionInvoice: create the open-row) |
| `invoice.paid` | set `paid`/`paid_at` (`get_or_create`→update if not paid); `_refresh_urls`; amount_paid |
| `invoice.payment_failed` | set `payment_failed_at`, payment_status stays `open`; `_refresh_urls` (token rotated). **Coordinate with the existing `handle_invoice_payment_failed` suspend logic** (`connectors/stripe/webhooks.py`) — one handler does both effects atomically, or keep independent + idempotent; do NOT break suspension. |
| `invoice.voided` | status `void` |
| `invoice.marked_uncollectible` | status `uncollectible` |

All handlers: `event.account`→tenant check (C-2); monotonic flip under `select_for_update` (`if status terminal: return`); synchronous write; `StripeWebhookEvent` dedup (existing). Per-axis: do the **honest minimum** — store Stripe `status` + url/pdf; reconstruct any access/seat/usage breakdown from UBB's own DB (the system of record), NOT from Stripe's blended payload.

## 3. Polling backstop (required — webhooks retry only ~3 days then drop)
Hourly beat `reconcile_invoice_payment_status` (mirror Stage C's `reconcile_topups_with_stripe`): per connected account, `Invoice.list(stripe_account=connected)` with a **4-day lookback**, `auto_paging_iter` + small sleep; for each, match `CustomerUsageInvoice`/`SubscriptionInvoice` by `stripe_invoice_id` (filter `status='pushed' AND stripe_invoice_id != ''` for usage) and repair `payment_status`/`status` + url/pdf to Stripe's truth (monotonic; loud on unexpected regressions). Webhooks = fast path; poller = truth-repair.

## 4. `/me` surface (D) — billing-owner-only
Separate endpoints (avoids brittle multi-queryset cursor): `GET /me/usage-invoices`, `GET /me/subscription-invoices` (keep `/me/invoices` = top-up receipts for everyone). **Gating:** compute `owner = request.widget_customer.resolve_billing_owner()`; only when `owner.id == request.widget_customer.id` query `CustomerUsageInvoice`/`SubscriptionInvoice` filtered `customer=owner` (else empty — a pooled seat must NOT see the consolidated business bill = sibling-spend leak). Serialize `payment_status`/`status`, `hosted_invoice_url`, `invoice_pdf`, totals, period. Reuse the existing cursor pagination per endpoint. (URL expiry 30–120d: serve the stored URL; the poller keeps recent ones fresh; on-demand re-fetch for aged invoices is a noted refinement, not v1.)

## 5. Test strategy (mostly mocked + ONE gated live)
- **Mocked capstone (proves intent):** synthetic event sequences against the api/v1 endpoint — `finalized→paid`; `finalized→payment_failed→voided`; out-of-order + duplicate `event.id` redelivery — assert correct terminal status, idempotency/dedup, monotonic flips, url/pdf stored + refreshed (incl. token rotation on payment_failed), the `event.account` guard rejects a foreign account, and `/me` returns the right set for a billing-owner vs empty for a pooled seat. Plus the **dual-endpoint dedup test** (same `event.id` at both endpoints → second is a deduped no-op).
- **Gated live Stripe-test-mode test (proves Stripe outcome; OPT-IN):** behind `UBB_STRIPE_LIVE_TEST=1` + `STRIPE_TEST_CONNECTED_ACCOUNT` env (skipped by default via `pytest.mark.skipif`). Against one real test-mode connected account: create + finalize + pay a real invoice, retrieve the real event/object, and ASSERT the field paths our handlers read (`status`, `hosted_invoice_url`, `invoice_pdf`, the subscription linkage under Basil) match. **Honesty: this ships UNRUN in this environment (no Stripe credentials here); the operator runs it against a test account.** It is the only honest verification of payload shape + that the connected-account `invoice.*` lands on the api/v1 endpoint — the exact gap that hid the Wave-4 bug.

## 6. Build sequence
1. **Schema migrations** (payment_status/url/pdf + the `stripe_invoice_id` index on CustomerUsageInvoice; status/url/pdf on SubscriptionInvoice) — prerequisite.
2. **Consolidate `invoice.*` reconcile onto api/v1** (handlers + routing by subscription presence + `event.account` check + monotonic + `_refresh_urls` + open-row; REMOVE the subscriptions endpoint's `invoice.paid` handler; coordinate the payment_failed suspend). + the dual-endpoint dedup test.
3. **Polling backstop** (hourly List-Invoices reconcile, 4-day lookback).
4. **`/me` surface** (two endpoints, billing-owner gating, url/pdf).
5. **Mocked capstone + the gated live test (skip-by-default) + final verification.**

## Explicitly deferred
5b owned-finalize one-coherent-bill (opt-in + watchdog + `invoice.finalization_failed` handler + two-clock double-bill guard + live test — XL); dunning notification emails; on-demand `/me` URL refresh for aged invoices; allocated/non-pooled business subs; mixed-interval. The standalone usage invoice stays the default — norm-aligned with Metronome, zero silent-stall liability.
