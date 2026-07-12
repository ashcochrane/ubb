# Wave 5.5 — Pre-Launch Hardening: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make J2 honestly launch-ready by fixing the four Stripe-boundary launch-blockers the program stock-take found (all hidden behind mocked tests), closing the mocked-test blind spots, and shipping the J1 polish + J2 docs.

**Architecture:** Surgical fixes on the postpaid push (deterministic two-phase invoice), the reconcile retry bound, the payment_intent account check, plus Basil-shaped tests, docs, and an extended (still-gated) live test.

**Tech Stack:** Django 6, stripe==15.x (mocked except the gated live test), pytest-django.

**Design ref:** `docs/plans/2026-06-10-wave55-prelaunch-hardening-design.md`. **Decisions:** full hardening now; J1 cost-coverage stays opt-in (louder visibility, no default change).

---

## ⚠️ Facts (verified)
- `apps/billing/invoicing/services/postpaid_service.py` `_push_to_stripe` (L129-166): creates pending `InvoiceItem`s (no `invoice=`, L148-153) THEN `Invoice.create` (auto_advance=False, L156-158) THEN `finalize_invoice` — the B1 ordering defect. Cents/residual carry (Wave 4.5) at L140-153.
- `apps/billing/connectors/stripe/webhooks.py` `handle_payment_intent_succeeded` (L390-401) + `handle_payment_intent_payment_failed` (L404-422): resolve `TopUpAttempt` from `pi.metadata.topup_attempt_id`, NO `event.account` check (B4). `TopUpAttempt` has `.customer` FK; `customer.tenant.stripe_connected_account_id`.
- `_invoice_subscription_id` (`api/v1/webhooks.py:161-169`): reads `inv.subscription` then `inv.parent.subscription_details.subscription` (Basil). `_reconcile_customer_invoice` routes by it.
- `reconcile_postpaid_usage` (`apps/billing/invoicing/tasks.py`): retries `pending` `CustomerUsageInvoice` rows; `status` choices include `failed` (never set today). READ it for the exact retry loop.
- `ubb-sdk/README.md` (J1-only; broken at L88/98/102). `ubb-platform/seed_dev_data.py` (J1-only). `test_live_stripe_ar.py` (gated, skip-by-default).

## Conventions
- Platform from `ubb-platform/`, `$DJ` = `DJANGO_SETTINGS_MODULE=config.settings <venv python>`. Baseline **851 platform (1 skipped) + 180 SDK green**. Stripe MOCKED (except the gated live test). Commit per task; `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`. No PR.

---

### Task 1: B1 — postpaid two-phase invoice (usage actually lands on the bill)

**Files:** Modify `apps/billing/invoicing/services/postpaid_service.py`; Test `apps/billing/invoicing/tests/test_postpaid_hardening.py`.

- [ ] **Step 1 — Failing test:** push a postpaid usage period (mock `stripe.Invoice.create`→`MagicMock(id="in_1")`, `stripe.InvoiceItem.create`→`MagicMock(id="ii")`, `stripe.Invoice.finalize_invoice`). Assert: (a) `stripe.Invoice.create` is called BEFORE any `stripe.InvoiceItem.create` (order — use a parent `MagicMock` with `.method_calls`, or assert each `InvoiceItem.create` call kwargs has `invoice="in_1"`); (b) EVERY `InvoiceItem.create` carries `invoice="in_1"`; (c) the returned `rec.stripe_invoice_id == "in_1"`. (This is the assertion the old suite lacked — it proves items land on the invoice.) Run → FAIL (today items are created with no `invoice=` and before the invoice exists).
- [ ] **Step 2 — Reorder `_push_to_stripe`** to create the draft FIRST, pin each item to it:
```python
    @staticmethod
    def _push_to_stripe(tenant, customer, rec, lines, period_start, carry_in=0):
        connected = tenant.stripe_connected_account_id
        currency = (tenant.default_currency or "usd").lower()
        owner = customer.resolve_billing_owner()

        # Compute the cent lines first (carry the sub-cent residual forward, Wave 4.5).
        cent_lines, residual = [], carry_in
        for i, (label, amount) in enumerate(lines):
            cent_micros = amount + residual
            cents = cent_micros // 10_000
            residual = cent_micros - cents * 10_000
            if cents <= 0:
                continue
            cent_lines.append((i, label, cents))
        if residual >= 10_000:
            logger.error("postpaid.residual_overflow", extra={"data": {
                "usage_invoice_id": str(rec.id), "residual_micros": residual}})

        # Sub-cent total: nothing to bill this period; carry the residual, no empty invoice.
        if not cent_lines:
            return None, [], residual

        # B1: create the draft invoice FIRST, then PIN each usage line to it via invoice=<id>.
        # Stripe's default pending_invoice_items_behavior is 'exclude' — un-pinned pending items
        # would NOT sweep, finalizing an EMPTY invoice. Two-phase guarantees the items land.
        inv = stripe_call(
            stripe.Invoice.create, retryable=True, idempotency_key=f"usage-invoice-{rec.id}",
            customer=owner.stripe_customer_id, auto_advance=False, stripe_account=connected)
        items = []
        for i, label, cents in cent_lines:
            desc = f"Usage {period_start:%Y-%m}" + (f" — {label}" if label else "")
            item = stripe_call(
                stripe.InvoiceItem.create, retryable=True,
                idempotency_key=f"usage-item-{rec.id}-{i}",
                customer=owner.stripe_customer_id, invoice=inv.id, amount=cents, currency=currency,
                description=desc, stripe_account=connected)
            # original micro amount for the local line record:
            orig = next(a for (lbl, a) in [(l, a) for (l, a) in lines] if lbl == label)
            items.append((label, orig, item.id))
        stripe_call(
            stripe.Invoice.finalize_invoice, retryable=True,
            idempotency_key=f"usage-finalize-{rec.id}", invoice=inv.id,
            auto_advance=True, stripe_account=connected)
        return inv.id, items, residual
```
(Keep the local `items` recording the ORIGINAL micro amount per line — simplify the `orig` lookup if labels can collide: track `(i,label,cents,orig)` in `cent_lines` instead. The point: `InvoiceItem.create` carries `invoice=inv.id`. VERIFY `push_customer_period` handles the `(None, [], residual)` no-items return — if `standalone_id` is None it should record the residual + a `skipped`/`pushed`-no-invoice status without crashing; adjust `push_customer_period` minimally if needed and note it.)
- [ ] **Step 3 — Verify + commit:** `$DJ -m pytest apps/billing/invoicing -q` → green. `fix(postpaid): two-phase invoice — pin usage items to the draft so they actually bill (B1)`.

---

### Task 2: B4 — payment_intent webhook account check

**Files:** Modify `apps/billing/connectors/stripe/webhooks.py`; Test `apps/billing/connectors/stripe/tests/test_pi_webhooks.py`.

- [ ] **Step 1 — Failing test:** a `payment_intent.succeeded` event whose `event.account` does NOT match the attempt's tenant connected account → `AutoTopUpService.apply_topup_credit` is NOT called (patch/spy it); a matching `event.account` → it IS called. Run → FAIL (no check today).
- [ ] **Step 2 — Add the guard** to BOTH handlers, after resolving `attempt`:
```python
    acct = getattr(event, "account", None)
    if acct and acct != attempt.customer.tenant.stripe_connected_account_id:
        return  # cross-account guard — only act on the attempt's own connected account
```
(`handle_payment_intent_succeeded` before `apply_topup_credit`; `handle_payment_intent_payment_failed` before the `with transaction.atomic()`. VERIFY `attempt.customer.tenant.stripe_connected_account_id` is the correct path.)
- [ ] **Step 3 — Verify + commit:** `$DJ -m pytest apps/billing/connectors -q`. `fix(webhooks): account-check the payment_intent handlers (B4)`.

---

### Task 3: B3 — bound the postpaid push retry (no silent infinite retry)

**Files:** Modify `apps/billing/invoicing/tasks.py` (`reconcile_postpaid_usage`); Test.

- [ ] **Step 1 — Read** `reconcile_postpaid_usage` for the exact retry loop (which rows it re-pushes + the status set on failure).
- [ ] **Step 2 — Failing test:** a `CustomerUsageInvoice` stuck `pending` (or `pushing`) with `updated_at` older than 24h → after `reconcile_postpaid_usage`, its status is `failed` and a loud alert was logged (assert via `caplog` `billing.usage_push_stuck` or similar); a row younger than 24h → still retried (not failed).
- [ ] **Step 3 — Implement:** in the reconcile loop, before re-pushing a `pending`/`pushing` row, if `timezone.now() - rec.updated_at > timedelta(hours=24)`: set `status="failed"`, `logger.error("billing.usage_push_stuck", extra={"data": {"usage_invoice_id": str(rec.id), "age_hours": ...}})`, and SKIP the retry (so the loop terminates + the stuck push is surfaced for an operator). Otherwise retry as today.
- [ ] **Step 4 — Verify + commit:** `$DJ -m pytest apps/billing/invoicing -q`. `fix(postpaid): bound the push retry — stuck rows go failed + alert (B3)`.

---

### Task 4: B2 — Basil-shaped subscription routing tests

**Files:** Test `api/v1/tests/test_ar_reconcile.py` (or a new `test_ar_basil_shape.py`).

- [ ] **Step 1 — Failing/again-passing tests:** construct a **Basil-shaped** invoice object: `subscription=None`, `parent` = an object whose `subscription_details.subscription = "sub_x"` (use `MagicMock` or a namespace matching the getattr chain in `_invoice_subscription_id`). Assert: (a) `api.v1.webhooks._invoice_subscription_id(inv)` returns `"sub_x"`; (b) an `invoice.finalized` event with this Basil-shaped invoice (for a `StripeSubscription("sub_x")` on the tenant's connected account) creates/updates a `SubscriptionInvoice` (NOT a `CustomerUsageInvoice`) — i.e. it routes to the subscription branch. Run → these should PASS if the Basil branch is correct (they EXERCISE the previously-untested branch; if they fail, the Basil read is wrong → fix `_invoice_subscription_id`).
- [ ] **Step 2 — If a test fails, fix** `_invoice_subscription_id` to read the Basil chain correctly; else the tests stand as the coverage that was missing.
- [ ] **Step 3 — Verify + commit:** `$DJ -m pytest api/v1 -q`. `test(ar): exercise the Basil subscription-link routing (parent.subscription_details) (B2)`.

---

### Task 5: J1 README fixes + louder uncosted + J2 quickstart + seed

**Files:** Modify `ubb-sdk/README.md`, `ubb-platform/seed_dev_data.py`.

- [ ] **Step 1 — Fix the 3 README copy-paste bugs:** breakdown rows → key on `dimension` (not `value`); timeseries buckets → key on `bucket` (not `period_start`) and `dimension`; granularity examples → `hour`/`day` only (remove `week`/`month` — the API 422s them). VERIFY each against `metering_endpoints.py`/`queries.py` field names.
- [ ] **Step 2 — Louder uncosted note** (decision: opt-in kept): add a prominent README callout — "If `record_usage` returns a non-empty `uncosted_metrics`, those metrics priced to **$0** (no matching cost card). Add a cost card, or enable `require_cost_card_coverage` on the tenant to hard-reject (422) instead of silently $0."
- [ ] **Step 3 — J2 quickstart** in the README: a section documenting `create_plan(...)`, `subscribe_customer(external_id, plan_key, seats)`, `set_seats(...)`, `start_connect_onboarding(return_url)`/`get_connect_status()`, and the `/me/usage-invoices` + `/me/subscription-invoices` reads — a copy-pasteable J2 path. (VERIFY the exact SDK signatures in `ubb-sdk/ubb/client.py`.)
- [ ] **Step 4 — Seed J2:** extend `seed_dev_data.py` so the dev tenant has `billing_mode`, `products` incl. `billing`, and a printed note on the Connect step (don't fake a real `stripe_connected_account_id`); print the J2 quickstart URLs. Run `$DJ manage.py seed_dev_data` (or however it's invoked) to confirm it doesn't crash.
- [ ] **Step 5 — Verify + commit:** SDK `<venv> -m pytest -q` (docs-only; confirm nothing broke). `docs(sdk): fix J1 README examples + louder uncosted + add J2 quickstart + seed`.

---

### Task 6: B-live — extend the gated live test + final verification

**Files:** Modify `apps/billing/invoicing/tests/test_live_stripe_ar.py`; verification.

- [ ] **Step 1 — Extend the gated live test** (still `skipif(not UBB_STRIPE_LIVE_TEST)`, ships unrun): add two cases against the real test-mode connected account — (a) **empty-invoice/B1:** create a draft invoice, pin an InvoiceItem via `invoice=<id>`, finalize, RETRIEVE it, and assert `inv.lines.data` contains the item (proves usage lands); (b) **Basil/B2:** create a real test-mode subscription + retrieve its invoice and assert `api.v1.webhooks._invoice_subscription_id(inv)` resolves the sub id via `.parent.subscription_details.subscription`. Add a `# HOW TO RUN` note. (Ships UNRUN here — confirm it's collected + skipped.)
- [ ] **Step 2 — Final verification:** `$DJ manage.py check`; `$DJ manage.py makemigrations --check --dry-run` → "No changes detected" (this wave adds NO migration); confirm the live test SKIPPED; FULL platform `$DJ -m pytest -q` (report count + skipped); SDK green; clean tree.
- [ ] **Step 3 — Commit:** `test(wave5.5): extend gated live test to cover B1 empty-invoice + B2 Basil subscription`.

---

## Self-Review
**Spec coverage:** B1 two-phase pin + line-content test (T1); B4 PI account check (T2); B3 bounded retry → failed + alert (T3); B2 Basil-shaped routing tests (T4); J1 README fixes + louder uncosted + J2 quickstart + seed (T5); B-live extension + verify (T6). Decisions: opt-in cost-coverage kept (T5.2 visibility only); no default-behavior change.
**Placeholder scan:** T1/T2 give full code; T3/T4/T6 give concrete test+fix shapes against cited lines; "VERIFY" notes are real verifications. No TBD.
**Type consistency:** `_push_to_stripe` still returns `(standalone_id, items, residual)` (T1) — `push_customer_period` unchanged except the None-standalone_id guard; `_invoice_subscription_id` (T4) is the same helper the poller + reconcile use.
**No migration** this wave (all behavior/test/doc changes) — T6 asserts makemigrations clean.
**Honest boundary:** the live test (T6) still ships UNRUN — the mocked tests (T1 line-content, T4 Basil-shape) close the *code* blind spots; the live test is the operator's real-Stripe proof. State this in the wrap-up.
