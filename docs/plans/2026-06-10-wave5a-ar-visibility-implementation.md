# Wave 5a — J2 AR-Visibility Loop: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** UBB learns the payment outcome of every invoice it pushes (paid/open/void/uncollectible), stores the hosted invoice link + PDF, and surfaces usage + subscription invoices to the billing-owner end-customer — closing the AR-visibility gap below every competitor's norm.

**Architecture:** All `invoice.*` reconcile lives on ONE endpoint (the api/v1 billing webhook, which already has `StripeWebhookEvent` dedup + connected-account filtering), routing by presence of `invoice.subscription`: subscription → `SubscriptionInvoice`, no-subscription standalone → `CustomerUsageInvoice`, top-up → `Invoice` (existing). New `payment_status`/`status` + `hosted_invoice_url`/`invoice_pdf` columns; an hourly Stripe-driven polling backstop; billing-owner-gated `/me` endpoints. Tests mocked + ONE gated live test.

**Tech Stack:** Django 6, django-ninja, stripe==15.x (mocked except the gated live test), pytest-django.

**Design ref:** `docs/plans/2026-06-10-wave5a-ar-visibility-design.md`. **5b (owned-finalize one-bill) DEFERRED.** Decisions: gated live test (opt-in); `/me` billing-owner-only; dunning status-only; SubscriptionInvoice open-row on finalized.

---

## ⚠️ Facts (verified)
- `api/v1/webhooks.py`: `stripe_webhook` dispatch loop (dedup via `StripeWebhookEvent` + error classification, L34-143); `handle_invoice_paid` (L146-198) matches `Invoice`/`TenantInvoice` by `stripe_invoice_id` + `event.account`, locks + monotonic flip; `WEBHOOK_HANDLERS` registry (L227-238) has `invoice.paid` + `invoice.payment_failed`.
- `apps/subscriptions/api/webhooks.py` `handle_invoice_paid` (L95-129): writes `SubscriptionInvoice` via `get_or_create` on PAID only; **NO `event.account` check (Critical 2)**. Registered in the subscriptions endpoint's handler map (`apps/subscriptions/api/endpoints.py`). **This must be REMOVED + its logic moved to api/v1 (Critical 1 — dedup collision).**
- `apps/billing/connectors/stripe/webhooks.py` `handle_invoice_payment_failed` (L145-170): suspends the customer + `sync_seat_quantity_on_commit`. Registered on api/v1. **Extend it (don't break the suspend).**
- `SubscriptionInvoice` (`apps/subscriptions/models.py`): `tenant`, `customer`, `stripe_subscription` FK, `stripe_invoice_id` (unique), `amount_paid_micros`, `currency`, `period_start/end`, `paid_at`. NO `status`/`hosted_invoice_url`/`invoice_pdf`.
- `CustomerUsageInvoice` (`apps/billing/invoicing/models.py:52-68`): `status` (push lifecycle), `stripe_invoice_id` (NOT indexed), `residual_micros` (Wave 4.5). NO `payment_status`/url/pdf.
- `/me/invoices` (`api/v1/me_endpoints.py:178-216`): `Invoice` (top-up) only, `request.widget_customer`, `InvoiceOut` schema, `apply_cursor_filter`. `Customer.resolve_billing_owner()` (`apps/platform/customers/models.py:45-51`).
- migration heads: `git ls-files apps/billing/invoicing/migrations | tail` (`0003`) ; `apps/subscriptions/migrations | tail` (`0005`).

## Conventions
- Platform from `ubb-platform/`, `$DJ` = `DJANGO_SETTINGS_MODULE=config.settings <venv python>`. Baseline **817 platform + 180 SDK green**. Stripe MOCKED (except the gated live test, skipped by default). Commit per task; `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`. No PR.

---

### Task 1: Schema — AR-status + hosted-link columns (+ the index)

**Files:** Modify `apps/billing/invoicing/models.py`, `apps/subscriptions/models.py`; migrations `invoicing/0004_*`, `subscriptions/0006_*`; Tests (model round-trip).

- [ ] **Step 1 — `CustomerUsageInvoice`** add:
```python
    payment_status = models.CharField(max_length=20, null=True, blank=True)  # open|paid|void|uncollectible (NULL=not yet collectible)
    paid_at = models.DateTimeField(null=True, blank=True)
    payment_failed_at = models.DateTimeField(null=True, blank=True)
    hosted_invoice_url = models.CharField(max_length=1000, blank=True, default="")
    invoice_pdf = models.CharField(max_length=1000, blank=True, default="")
```
and change `stripe_invoice_id` to `models.CharField(max_length=255, blank=True, default="", db_index=True)` (add `db_index=True`).
- [ ] **Step 2 — `SubscriptionInvoice`** add:
```python
    status = models.CharField(max_length=20, default="open")  # open|paid|void|uncollectible
    hosted_invoice_url = models.CharField(max_length=1000, blank=True, default="")
    invoice_pdf = models.CharField(max_length=1000, blank=True, default="")
```
- [ ] **Step 3 — Failing test** (round-trip both new field sets) → FAIL.
- [ ] **Step 4 — Migrations:** `$DJ manage.py makemigrations invoicing subscriptions`; `makemigrations --check`; `migrate`.
- [ ] **Step 5 — Verify + commit:** `$DJ -m pytest apps/billing/invoicing apps/subscriptions -q`. `feat(ar): payment_status + hosted invoice link/pdf columns (+ stripe_invoice_id index)`.

---

### Task 2: Consolidate `invoice.*` reconcile onto api/v1

**Files:** Modify `api/v1/webhooks.py` (handlers + registry), `apps/billing/connectors/stripe/webhooks.py` (payment_failed extension), `apps/subscriptions/api/endpoints.py` (REMOVE `invoice.paid` from its handler map); Tests `api/v1/tests/test_webhooks*.py`.

- [ ] **Step 1 — Failing tests** (`api/v1/tests/`; construct synthetic Stripe events; POST to `/api/v1/webhooks/stripe` or call the handler — match the existing webhook-test pattern; mock signature verification): 
  - `invoice.finalized` for a usage standalone invoice (no `subscription`) whose `stripe_invoice_id` matches a `CustomerUsageInvoice` on the tenant's connected account → `payment_status="open"`, `hosted_invoice_url`/`invoice_pdf` stored.
  - `invoice.paid` (usage) → `payment_status="paid"`, `paid_at` set.
  - `invoice.finalized` for a SUBSCRIPTION invoice (`subscription` present) → a `SubscriptionInvoice` open-row is created (`status="open"` + url/pdf); a subsequent `invoice.paid` → the SAME row flips to `paid` + `paid_at` (NOT a second row).
  - `invoice.voided` → `void`; `invoice.marked_uncollectible` → `uncollectible`.
  - `event.account` mismatch (invoice id matches but a different connected account) → NO write.
  - `invoice.payment_failed` → customer still suspended (unchanged) AND the usage/subscription invoice gets `payment_failed_at` + url refreshed.
  - **Dual-endpoint dedup:** the same `event.id` POSTed to both endpoints → second is a deduped no-op (one handler ran).
  Run → FAIL.
- [ ] **Step 2 — Helpers** in `api/v1/webhooks.py`:
```python
def _refresh_urls(local, inv):
    """Re-store hosted_invoice_url/invoice_pdf whenever Stripe sends a non-null value
    (the token rotates on payment_failed). Caller saves."""
    if getattr(inv, "hosted_invoice_url", None):
        local.hosted_invoice_url = inv.hosted_invoice_url
    if getattr(inv, "invoice_pdf", None):
        local.invoice_pdf = inv.invoice_pdf

def _invoice_subscription_id(inv):
    """Basil-safe read of the subscription linkage (may be a string id or nested)."""
    sub = getattr(inv, "subscription", None)
    if sub:
        return sub if isinstance(sub, str) else getattr(sub, "id", None)
    parent = getattr(inv, "parent", None)
    details = getattr(parent, "subscription_details", None) if parent else None
    s = getattr(details, "subscription", None) if details else None
    return s if isinstance(s, str) else getattr(s, "id", None)
```
- [ ] **Step 3 — `_reconcile_customer_invoice(event, *, payment_status=None, paid=False, failed=False)`** (new, in api/v1/webhooks.py): the shared status-flip for the *customer* invoices (usage + subscription), all under `event.account` + `select_for_update` + monotonic:
```python
def _reconcile_customer_invoice(event, *, new_status):
    from apps.billing.invoicing.models import CustomerUsageInvoice
    from apps.subscriptions.models import SubscriptionInvoice, StripeSubscription
    from apps.platform.tenants.models import Tenant
    inv = event.data.object
    acct = event.account
    if not acct:
        return  # customer invoices are always on a connected account
    sub_id = _invoice_subscription_id(inv)
    if sub_id:
        sub = StripeSubscription.objects.filter(
            stripe_subscription_id=sub_id, tenant__stripe_connected_account_id=acct).first()
        if not sub:
            return
        with transaction.atomic():
            row, _ = SubscriptionInvoice.objects.select_for_update().get_or_create(
                stripe_invoice_id=inv.id,
                defaults={"tenant": sub.tenant, "customer": sub.customer, "stripe_subscription": sub,
                          "amount_paid_micros": (getattr(inv, "amount_paid", 0) or 0) * 10_000,
                          "currency": inv.currency, "status": new_status,
                          "period_start": _unix(inv.period_start), "period_end": _unix(inv.period_end)})
            if row.status not in ("paid", "void", "uncollectible"):  # monotonic
                row.status = new_status
            if new_status == "paid" and not row.paid_at:
                row.paid_at = _unix(getattr(inv.status_transitions, "paid_at", None))
                row.amount_paid_micros = (getattr(inv, "amount_paid", 0) or 0) * 10_000
            _refresh_urls(row, inv)
            row.save()
    else:
        row = CustomerUsageInvoice.objects.filter(
            stripe_invoice_id=inv.id, tenant__stripe_connected_account_id=acct).first()
        if not row:
            return
        with transaction.atomic():
            row = CustomerUsageInvoice.objects.select_for_update().get(id=row.id)
            if row.payment_status not in ("paid", "void", "uncollectible"):
                row.payment_status = new_status
            if new_status == "paid" and not row.paid_at:
                row.paid_at = timezone.now()
            _refresh_urls(row, inv)
            row.save()
```
(`_unix` = the unix→datetime helper; reuse the subscriptions one or add a small local. VERIFY `inv.status_transitions.paid_at` access shape.)
- [ ] **Step 4 — Event handlers + registry** in api/v1/webhooks.py:
```python
def handle_invoice_finalized(event):
    _reconcile_customer_invoice(event, new_status="open")

def handle_invoice_voided(event):
    _reconcile_customer_invoice(event, new_status="void")

def handle_invoice_uncollectible(event):
    _reconcile_customer_invoice(event, new_status="uncollectible")
```
Extend the EXISTING `handle_invoice_paid`: after its top-up/TenantInvoice logic, ALSO call `_reconcile_customer_invoice(event, new_status="paid")` (so a connected-account subscription/usage invoice.paid reconciles the customer invoice too — the top-up branch returns early when no `Invoice` matches, so add the customer-invoice reconcile as a parallel call, not gated on the top-up match). Register: `"invoice.finalized": handle_invoice_finalized, "invoice.voided": handle_invoice_voided, "invoice.marked_uncollectible": handle_invoice_uncollectible`.
- [ ] **Step 5 — Extend `handle_invoice_payment_failed`** (`connectors/stripe/webhooks.py`): keep the suspend; ADD a call to set the customer-invoice `payment_failed_at` + refresh url (import + call `_reconcile_customer_invoice`-style logic, or a focused `payment_failed` branch — set `payment_failed_at=now()`, `_refresh_urls`, do NOT change a terminal status). Keep it idempotent + atomic with the suspend.
- [ ] **Step 6 — Remove the collision (Critical 1):** delete `invoice.paid` from the subscriptions endpoint's handler map (`apps/subscriptions/api/endpoints.py`) and remove/retire `apps/subscriptions/api/webhooks.py::handle_invoice_paid` (its logic now lives in api/v1's `_reconcile_customer_invoice`). Update any subscriptions webhook test that asserted the old handler. Add a code comment: "all invoice.* reconcile lives on api/v1; the subscriptions endpoint handles customer.subscription.* only — no invoice.* type on both (shared StripeWebhookEvent dedup)."
- [ ] **Step 7 — Verify + commit:** `$DJ -m pytest api/v1 apps/billing apps/subscriptions -q` → green. `feat(ar): consolidate invoice.* payment reconcile on api/v1 (status + url/pdf, account-checked, monotonic)`.

---

### Task 3: Polling backstop (hourly Stripe-driven reconcile)

**Files:** Create a beat task in `apps/billing/invoicing/tasks.py` (or the AR tasks home); register the beat in `config/settings.py`; Test.

- [ ] **Step 1 — Failing test:** a `CustomerUsageInvoice(status="pushed", stripe_invoice_id="in_x", payment_status=None)` + a mocked `stripe.Invoice.list` returning `in_x` with `status="paid"`, `hosted_invoice_url`/`invoice_pdf` → the reconcile task sets `payment_status="paid"` + stores url/pdf. (And a `SubscriptionInvoice` analog.)
- [ ] **Step 2 — Implement `reconcile_invoice_payment_status`** (mirror Stage C's `reconcile_topups_with_stripe`): per charge-ready tenant, `stripe.Invoice.list(stripe_account=connected, created={"gte": now-4d})` `auto_paging_iter` (+ small sleep); for each Stripe invoice, match `CustomerUsageInvoice` (filter `status="pushed"` AND `stripe_invoice_id != ""`) or `SubscriptionInvoice` by `stripe_invoice_id`; repair `payment_status`/`status` + url/pdf monotonically to Stripe's truth; loud-log unexpected regressions. **4-day lookback** (matches Stage C); requires the Task-1 index.
- [ ] **Step 3 — Beat** in `config/settings.py`: `"reconcile-invoice-payment-status": {"task": "...reconcile_invoice_payment_status", "schedule": crontab(minute=15)}` (hourly).
- [ ] **Step 4 — Verify + commit:** `$DJ -m pytest apps/billing -q`. `feat(ar): hourly Stripe-driven invoice-payment-status reconcile backstop`.

---

### Task 4: `/me` surface — billing-owner-gated usage + subscription invoices

**Files:** Modify `api/v1/me_endpoints.py` (+ schemas); Test.

- [ ] **Step 1 — Failing tests:** a business widget customer with a `CustomerUsageInvoice` + a `SubscriptionInvoice` → `GET /me/usage-invoices` and `GET /me/subscription-invoices` return them (with `payment_status`/`status`, `hosted_invoice_url`, `invoice_pdf`, totals, period); a POOLED SEAT widget customer → both return **empty** (no sibling-spend leak); a non-billing-owner gets empty even though the business has invoices.
- [ ] **Step 2 — Implement** two endpoints (reuse the existing widget auth + `apply_cursor_filter` per endpoint). Gate:
```python
    owner = request.widget_customer.resolve_billing_owner()
    if owner.id != request.widget_customer.id:
        return {"invoices": [], "next_cursor": None}   # pooled seat: not the billing owner
    qs = CustomerUsageInvoice.objects.filter(customer=owner).order_by("-created_at")
```
Serialize the new fields (a `UsageInvoiceOut`/`SubscriptionInvoiceOut` schema with `hosted_invoice_url`, `invoice_pdf`, `payment_status`/`status`, `total_billed_micros`/`amount_paid_micros`, `period_start/end`). Keep `/me/invoices` (top-up) unchanged.
- [ ] **Step 3 — Verify + commit:** `$DJ -m pytest api/v1 -q`. `feat(me): billing-owner-gated usage + subscription invoice endpoints with hosted link`.

---

### Task 5: Mocked capstone + gated live test + verification

**Files:** Create `api/v1/tests/test_wave5a_ar_capstone.py`; create `apps/billing/invoicing/tests/test_live_stripe_ar.py` (gated, skipped by default).

- [ ] **Step 1 — Mocked capstone:** a synthetic event sequence against the api/v1 endpoint proving the full loop: `invoice.finalized → paid` (usage AND subscription); `finalized → payment_failed → voided`; out-of-order + duplicate `event.id` redelivery; `event.account` mismatch rejected; url/pdf stored + REFRESHED (a payment_failed event carrying a rotated url updates the stored value); then assert `/me` returns the right set for the billing owner and EMPTY for a pooled seat. Run 2x.
- [ ] **Step 2 — Gated live test** (`test_live_stripe_ar.py`): `pytestmark = pytest.mark.skipif(not os.environ.get("UBB_STRIPE_LIVE_TEST"), reason="opt-in live Stripe test")`. Using real Stripe test-mode (`STRIPE_TEST_SECRET_KEY` + `STRIPE_TEST_CONNECTED_ACCOUNT` env): create + finalize + pay a real invoice on the connected account, retrieve the real Invoice object + a real event, and ASSERT the field paths our handlers read exist + are shaped as expected (`status`, `hosted_invoice_url`, `invoice_pdf`, the subscription linkage via `_invoice_subscription_id`). **This test is SKIPPED by default + ships unrun here (no Stripe creds in this env).** Add a short `# HOW TO RUN` docstring (set the env vars + a test connected account).
- [ ] **Step 3 — Final verification:** `$DJ manage.py check`; `$DJ manage.py makemigrations --check --dry-run`; fresh-DB drop/recreate + `migrate` (applies `invoicing/0004` + `subscriptions/0006`); FULL platform `$DJ -m pytest -q` (report count; the live test SKIPPED); SDK green; clean tree.
- [ ] **Step 4 — Commit:** `test(wave5a): AR-visibility mocked capstone + gated live Stripe test`.

---

## Self-Review
**Spec coverage:** schema + index (T1); consolidated `invoice.*` reconcile on api/v1 routing by subscription presence + `event.account` (C-2) + monotonic + `_refresh_urls` + open-row + remove subscriptions `invoice.paid` (C-1) + payment_failed extension (T2); polling backstop 4-day (T3); `/me` billing-owner-gated (T4); mocked capstone + gated live test (T5). Decisions: gated live test ✓; billing-owner-only ✓; dunning status-only (no emails) ✓; SubscriptionInvoice open-row on finalized ✓. 5b deferred ✓.
**Critique must-fixes:** C-1 (one endpoint owns invoice.* + remove subscriptions handler + dedup test) → T2.6 + T5.1; C-2 (event.account in every handler) → T2.3; on_commit-not-for-writes (status flips synchronous under select_for_update) → T2.3; open-row coordination (get_or_create then update) → T2.3; payment_status NULL default + only when stripe_invoice_id set → T1/T2; index prerequisite → T1; _refresh_urls unconditional + non-null guard + token rotation → T2.2/T2.5; /me predicate resolve_billing_owner → T4; Basil subscription field-path → `_invoice_subscription_id` (T2.2) + the live test (T5).
**Placeholder scan:** T2 gives the full `_reconcile_customer_invoice` + helpers; "VERIFY status_transitions.paid_at shape" is a real verification. No TBD.
**Type consistency:** `_reconcile_customer_invoice(event, *, new_status)` (T2) used by all handlers; `_refresh_urls`/`_invoice_subscription_id` (T2) reused by the poller (T3); `payment_status`/`status`/url/pdf fields (T1) read by reconcile (T2), poller (T3), /me (T4), capstone (T5).
**Migrations:** two additive (invoicing/0004 + subscriptions/0006); DB-validated T1 + fresh-DB T5.
