# Wave 5.5 — Pre-Launch Hardening (Design)

**Date:** 2026-06-10 · **Source:** the 12-agent program-capstone stock-take (workflow `wd0tl9lxd`), which lowered J2 to B−/C+ and found the entire Stripe boundary is mocked with two Critical defects hidden behind green tests. **Goal: make J2 honestly launch-ready** by fixing the four Stripe-boundary blockers, closing the mocked-test blind spots, and shipping the J1 polish + J2 docs. **Owner decisions:** do the full hardening now; J1 cost-coverage stays opt-in but the silent-$0 gets louder (no default-behavior change).

## B1 — 🔴 Postpaid empty-invoice (possibly the NORMAL path) → two-phase pin
**Defect:** `_push_to_stripe` (`postpaid_service.py:~148-162`) creates pending `InvoiceItem`s (no `invoice=`), then `Invoice.create` **without** `pending_invoice_items_behavior` — Stripe's documented default is `exclude`, so the pending items may NOT sweep → an **empty invoice finalizes and usage is never billed.** Every test mocks `Invoice.create` to a bare object with no line assertion → structurally blind.
**Fix (deterministic — chosen over `pending_invoice_items_behavior="include"`, which sweeps *all* of the customer's pending items):** restructure to **two-phase, pinning items to the specific draft**:
1. `inv = Invoice.create(customer=owner, auto_advance=False, stripe_account=connected, idempotency_key="usage-invoice-{rec.id}")` — an empty draft FIRST.
2. for each line: `InvoiceItem.create(customer=owner, invoice=inv.id, amount=cents, currency, description, stripe_account=connected, idempotency_key="usage-item-{rec.id}-{i}")` — **pinned** to the draft.
3. `Invoice.finalize_invoice(inv.id, ...)`.
**Test (closes the blind spot):** assert every `InvoiceItem.create` carries `invoice=<the draft id>` AND the draft id equals `rec.stripe_invoice_id` — so the suite proves items land on the invoice. (Keep the Wave-4.5 cents/residual carry intact.) Idempotency unchanged (same keys).

## B2 — 🔴 Basil subscription routing untested → Basil-shaped mocked tests (+ live extension)
**Defect:** under pinned `api_version=2025-03-31`, Stripe carries the sub link at `invoice.parent.subscription_details.subscription`; `_invoice_subscription_id` (`api/v1/webhooks.py:161-169`) reads it, but **every test uses the legacy top-level `.subscription` + `parent=None`** → the Basil branch has zero coverage. If it misreads, real sub invoices misroute to the usage branch → AR never reconciles (webhook + poller share the helper).
**Fix:** add MOCKED tests that construct a **Basil-shaped** invoice (`subscription=None`; `parent.subscription_details.subscription=<sub_id>`) and assert (a) `_invoice_subscription_id` resolves the sub id, and (b) `_reconcile_customer_invoice` routes to `SubscriptionInvoice` (not the usage branch). This proves the code reads the documented Basil structure. (Full proof remains the live test — extended in B-live.)

## B3 — 🟠 Orphaned-draft revenue leak → bounded retry + `failed` + alert
**Defect:** no `void_invoice` anywhere; `reconcile_postpaid_usage` retries `pending` rows with **no time bound**; Stripe idempotency keys expire after 24h → a worker death + retry >24h strands a draft + creates a duplicate, unmonitored. (`status="failed"` exists but is never set.)
**Fix:** bound the push-retry: if a `CustomerUsageInvoice` has been stuck `pending` past a max age (e.g. 24h, comfortably inside the idem-key window for normal retries but a hard stop after), transition it to `failed` + emit a loud alert (a `billing.usage_push_failed` log/event) so the infinite retry terminates and the stuck push is surfaced for operator action. (A full `void_invoice` cleanup sweep of abandoned drafts is a fast-follow; the bounded-retry + alert is the launch-blocking part — it stops silent unbounded retries + makes the failure visible.)

## B4 — 🟠 payment_intent.* skip the account check → add it
**Defect:** `handle_payment_intent_succeeded`/`payment_failed` (`connectors/stripe/webhooks.py:~390-422`) resolve the `TopUpAttempt` purely from `pi.metadata.topup_attempt_id` with **no `event.account` check** — the only money handlers that skip it.
**Fix:** after resolving the attempt, verify `event.account == attempt.customer.tenant.stripe_connected_account_id` (else `return`); add a test with a mismatched `event.account`.

## J1 polish (blocks a clean A — cheap)
- **README copy-paste bugs:** fix the 3 broken examples — breakdown rows key on `dimension` (not `value`), timeseries buckets key on `bucket` (not `period_start`) + `dimension`, and granularity is `hour`/`day` only (remove `week`/`month`; the API 422s them).
- **Louder uncosted (decision: keep opt-in, raise visibility):** add a prominent README note that `uncosted_metrics` in the `record_usage` response means those metrics priced to $0 and the tenant should either add a cost card or enable `require_cost_card_coverage` for hard rejection. (No default-behavior change.)

## J2 self-serve docs (fails "easy" for J2 today)
- **SDK README J2 section:** document `create_plan`, `subscribe_customer`, `set_seats`, `start_connect_onboarding`/`get_connect_status`, and the `/me` usage/subscription invoice reads — a J2 quickstart.
- **Seed J2:** extend `seed_dev_data.py` so a tenant is set up for J2 (a `billing_mode`, `products` incl. billing, a (placeholder) connected-account note) — enough that a developer can follow the quickstart. (Don't fake a real Stripe connection; document the Connect step.)

## B-live — extend the gated live test (still skip-by-default; ships unrun)
Extend `test_live_stripe_ar.py` to cover the two Critical paths so that when the operator runs it with test-mode creds it actually de-risks them:
1. **Empty-invoice:** create a real postpaid-style usage invoice via the two-phase path and assert the **finalized invoice's `lines` contain the items** (the B1 proof against real Stripe).
2. **Basil subscription:** create a real test-mode subscription + its invoice and assert `_invoice_subscription_id` resolves the sub id via `.parent.subscription_details.subscription` (the B2 proof).

## Build sequence
1. **B1** (two-phase pin + line-content test) — the most dangerous, possibly-normal-path defect.
2. **B4** (PI account check — 2-line + test).
3. **B3** (bounded retry → failed + alert).
4. **B2** (Basil-shaped mocked tests).
5. **J1 README fixes + louder uncosted; J2 quickstart + seed.**
6. **B-live** (extend the gated live test) + final verification (fresh-DB, full suite).

## Explicitly fast-follow (NOT in 5.5)
Full `void_invoice` cleanup sweep; allocated-seat `/me` tests; dunning emails; rename `reconcile_wallet_balances`→detect + add repair; the dead-code `revenue_for_window` removal; 5b consolidated bill. None launch-blocking.
