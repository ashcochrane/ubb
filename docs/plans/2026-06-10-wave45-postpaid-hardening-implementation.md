# Wave 4.5 — Postpaid J2 Hardening: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the two Critical money bugs (off-by-one usage cycle; sub-cent push crash) + three Important money-correctness gaps the J2 stock-take found, so J2 postpaid is safe for a real-money tenant.

**Architecture:** Usage is always billed on its OWN finalized standalone Stripe invoice (correct-cycle, deterministic — drops the unreliable subscription-pin); usage amounts are floored to whole cents with the sub-cent residual carried forward + audited; plan currency is threaded + asserted; the margin mirror is refreshed on seat change; the accrual status filter matches the push. Tests stay MOCKED.

**Tech Stack:** Django 6, stripe==15.x (mocked in tests), pytest-django.

**Design ref:** `docs/plans/2026-06-10-wave45-postpaid-hardening-design.md`. **Decisions:** C1 standalone-always (true one-bill → Wave 5); C2 floor + carry residual; I1 fail-loud on currency; I2 mirror refresh; I3 +unpaid.

---

## ⚠️ Facts (verified)
- `apps/billing/invoicing/services/postpaid_service.py`: `push_customer_period` (L60-116) claim/push/record; `_push_to_stripe` (L118-182) does the owner-subscription lookup + `subscription=` pin + `_subscription_cycle_closed` guard (L184-213) + per-line `micros_to_cents(amount)` (L158, **raises** `StripeFatalError` on non-cent-aligned) + the standalone branch (L171-181 — `Invoice.create(auto_advance=False)` then `finalize_invoice(auto_advance=True)`). `aggregate_lines` (L14-58) returns `(total, [(label, amount_micros), ...])` sorted desc.
- `CustomerUsageInvoice` (`apps/billing/invoicing/models.py:52-68`): has `total_billed_micros`, `currency`, `status`, `stripe_invoice_id`, `pushed_at`; UniqueConstraint(customer, period_start). NO residual field yet.
- `micros_to_cents` + `stripe_call` + `StripeFatalError` in `apps/billing/stripe/services/stripe_service.py`.
- `apps/subscriptions/orchestration/service.py`: `ensure_plan_provisioned` Price `currency="usd"` (hardcoded); `set_seats` updates only `CustomerSubscriptionItem.quantity`. `StripeSubscription.line_items` is the related_name for `CustomerSubscriptionItem`; `unit_amount_micros`/`quantity` per line.
- `apps/subscriptions/economics/revenue.py:61-77` `subscription_nominal_for_window` status filter `["active","trialing","past_due"]`.
- `UsageInvoicePushed` event schema in `apps/platform/events/schemas.py`.
- invoicing migration head: find via `git ls-files apps/billing/invoicing/migrations | tail`.

## Conventions
- Platform from `ubb-platform/`, `$DJ` = `DJANGO_SETTINGS_MODULE=config.settings <venv python>`. Baseline **812 platform + 180 SDK green**. Stripe MOCKED, never network. Commit per task; `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`. No PR.

---

### Task 1: C1 + C2 — rewrite the postpaid push (always-standalone + floor/carry residual)

**Files:** Modify `apps/billing/invoicing/models.py` (residual field), `apps/billing/invoicing/services/postpaid_service.py`, `apps/platform/events/schemas.py` (`UsageInvoicePushed`); migration `invoicing/00XX_*`; Tests `apps/billing/invoicing/tests/`. Update Wave-4 tests that asserted the pin.

- [ ] **Step 1 — Field + migration:** add to `CustomerUsageInvoice` (models.py): `residual_micros = models.BigIntegerField(default=0)`. `$DJ manage.py makemigrations invoicing`; `makemigrations --check`; `migrate`.
- [ ] **Step 2 — Failing tests** (`apps/billing/invoicing/tests/test_postpaid_hardening.py`; mock `stripe.InvoiceItem.create`/`stripe.Invoice.create`/`stripe.Invoice.finalize_invoice` at `apps.billing.invoicing.services.postpaid_service.stripe.*`; build a charge-ready tenant + a postpaid customer with `stripe_customer_id`):
```python
# C1: a postpaid customer WITH an active StripeSubscription -> usage is billed STANDALONE.
def test_usage_always_standalone_even_with_subscription(...):
    # create a StripeSubscription for the owner (status active)
    # aggregate_lines returns one cent-aligned line (e.g. 500_000 micros = 50c)
    # push -> assert: every InvoiceItem.create call kwargs has NO "subscription" key;
    #   Invoice.create + finalize_invoice called; rec.stripe_invoice_id == inv.id; rec.status=="pushed"

# C2: sub-cent line does not crash; floors to cents; residual carried + audited.
def test_subcent_floors_and_carries_residual(...):
    # one line of 1_234_567 micros, no prior residual
    # push -> no StripeFatalError; InvoiceItem.create got amount=123; rec.residual_micros==4_567; rec.status=="pushed"

def test_residual_carries_into_next_period(...):
    # period 1 leaves residual 4_567 (pushed); period 2 has a new line 8_000 micros
    # push period 2 -> 8_000+4_567=12_567 -> amount=1 (cent), rec2.residual_micros==2_567
```
Run → FAIL.
- [ ] **Step 3 — Rewrite `_push_to_stripe`** (drop the subscription lookup + pin + `_subscription_cycle_closed` guard entirely; always standalone; floor/carry). Signature gains `carry_in`; returns `(standalone_id, items, residual_out)`:
```python
    @staticmethod
    def _push_to_stripe(tenant, customer, rec, lines, period_start, carry_in=0):
        connected = tenant.stripe_connected_account_id
        currency = (tenant.default_currency or "usd").lower()
        owner = customer.resolve_billing_owner()

        items = []
        residual = carry_in
        for i, (label, amount) in enumerate(lines):
            cent_micros = amount + residual           # fold carry into the first/largest line
            cents = cent_micros // 10_000
            residual = cent_micros - cents * 10_000
            if cents <= 0:
                continue
            desc = f"Usage {period_start:%Y-%m}" + (f" — {label}" if label else "")
            item = stripe_call(
                stripe.InvoiceItem.create, retryable=True,
                idempotency_key=f"usage-item-{rec.id}-{i}",
                customer=owner.stripe_customer_id, amount=cents, currency=currency,
                description=desc, stripe_account=connected)
            items.append((label, amount, item.id))

        # C1: usage is ALWAYS its own finalized standalone invoice (correct-cycle,
        # deterministic). True single consolidated bill is a Wave-5 feature.
        inv = stripe_call(
            stripe.Invoice.create, retryable=True, idempotency_key=f"usage-invoice-{rec.id}",
            customer=owner.stripe_customer_id, auto_advance=False, stripe_account=connected)
        stripe_call(
            stripe.Invoice.finalize_invoice, retryable=True,
            idempotency_key=f"usage-finalize-{rec.id}", invoice=inv.id,
            auto_advance=True, stripe_account=connected)
        if residual >= 10_000:
            logger.error("postpaid.residual_overflow", extra={"data": {
                "usage_invoice_id": str(rec.id), "residual_micros": residual}})
        return inv.id, items, residual
```
DELETE `_subscription_cycle_closed` (now dead).
- [ ] **Step 4 — Carry + residual in `push_customer_period`:** before Phase 2, compute the carry; after `_push_to_stripe`, persist the residual + audit. In the claim/Phase-2 area:
```python
        # carry the sub-cent residual from the customer's most recent pushed period
        prior = (CustomerUsageInvoice.objects.filter(
            tenant=tenant, customer=customer, status="pushed",
            period_start__lt=period_start).order_by("-period_start").first())
        carry_in = prior.residual_micros if prior else 0
        try:
            standalone_id, items, residual_out = PostpaidUsageService._push_to_stripe(
                tenant, customer, rec, lines, period_start, carry_in=carry_in)
        except Exception:
            CustomerUsageInvoice.objects.filter(id=rec.id, status="pushing").update(status="pending")
            raise
```
In Phase 3 (record), set `rec.residual_micros = residual_out` (add to `save(update_fields=[...])`), and log + extend the event:
```python
            rec.residual_micros = residual_out
            rec.save(update_fields=["status", "stripe_invoice_id", "residual_micros", "pushed_at", "updated_at"])
            if residual_out or carry_in:
                logger.info("postpaid.residual_carried", extra={"data": {
                    "customer_id": str(customer.id), "period_start": period_start.isoformat(),
                    "carried_in": carry_in, "residual_micros": residual_out}})
            write_event(UsageInvoicePushed(... residual_micros=residual_out ...))
```
Add `residual_micros: int = 0` to the `UsageInvoicePushed` schema.
- [ ] **Step 5 — Update Wave-4 pin tests:** any existing test asserting `InvoiceItem.create(subscription=...)` (e.g. in `test_postpaid_*`/coherence tests from Wave 4 T6) must be updated to the standalone-always reality (no `subscription=` kwarg; standalone `Invoice.create`+`finalize`). Find them: `git grep -n "subscription=" apps/billing/invoicing/tests/`. Update each + note in the report.
- [ ] **Step 6 — Verify:** `$DJ manage.py check`; makemigrations --check; `$DJ -m pytest apps/billing apps/subscriptions -q` → green. **Commit:** `fix(postpaid): usage always standalone (correct-cycle) + floor-to-cents with carried residual`.

---

### Task 2: I3 — align the accrual status filter

**Files:** Modify `apps/subscriptions/economics/revenue.py`; Test `apps/subscriptions/economics/tests/`.

- [ ] **Step 1 — Failing test:** a `StripeSubscription(status="unpaid", amount_micros=130_000_000, interval="month")` → `subscription_nominal_for_window` over a full month returns `130_000_000` (today returns 0 because `unpaid` is filtered out).
- [ ] **Step 2 — Implement:** in `subscription_nominal_for_window`, change `status__in=["active", "trialing", "past_due"]` → `status__in=["active", "trialing", "past_due", "unpaid"]`.
- [ ] **Step 3 — Verify:** `$DJ -m pytest apps/subscriptions/economics -q` → green. **Commit:** `fix(margin): accrue subscription revenue for unpaid subs (match push basis)`.

---

### Task 3: I2 — refresh the margin mirror in `set_seats`

**Files:** Modify `apps/subscriptions/orchestration/service.py`; Test `apps/subscriptions/orchestration/tests/test_service.py`.

- [ ] **Step 1 — Failing test:** a sub with a `1_000_000` access item + a seat item `unit_amount_micros=2_000_000` qty 2; `set_seats(business, plan, 5, change_event_id="e1")` (mock `SubscriptionItem.modify`) → the `StripeSubscription` mirror has `amount_micros == 1_000_000 + 2_000_000*5 == 11_000_000`, `quantity == 5`, `last_synced_at` advanced — WITHOUT a webhook.
- [ ] **Step 2 — Implement:** in `set_seats`, after `item.quantity = new_seats; item.save(...)`, recompute the mirror from the persisted line items:
```python
        mirror = item.stripe_subscription
        mirror.amount_micros = sum(li.unit_amount_micros * li.quantity for li in mirror.line_items.all())
        mirror.quantity = new_seats
        mirror.last_synced_at = timezone.now()
        mirror.save(update_fields=["amount_micros", "quantity", "last_synced_at", "updated_at"])
```
(`timezone` is imported in service.py.)
- [ ] **Step 3 — Verify:** `$DJ -m pytest apps/subscriptions/orchestration -q` → green. **Commit:** `fix(subscriptions): refresh margin mirror in set_seats (no webhook lag)`.

---

### Task 4: I1 — thread plan currency + assert no mismatch

**Files:** Modify `apps/subscriptions/orchestration/service.py`; Tests.

- [ ] **Step 1 — Failing test:** for a tenant `default_currency="eur"`, `ensure_plan_provisioned` calls `stripe.Price.create` with `currency="eur"` (mock + assert kwargs); and `subscribe` for a plan/tenant whose currency is consistent succeeds, while a constructed mismatch (tenant `eur` but … ) raises `StripeFatalError`. (Keep the mismatch test simple — assert the subscribe path validates `(tenant.default_currency or "usd").lower()` against the plan/price currency and raises on mismatch.)
- [ ] **Step 2 — Implement:**
  - In `ensure_plan_provisioned`, the access + seat `Price.create` calls: `currency=(plan.tenant.default_currency or "usd").lower()` (replace the hardcoded `"usd"`).
  - In `subscribe`, after resolving `plan`/`owner`, assert consistency: if the plan was already provisioned under a different currency than the tenant's current `default_currency`, raise `StripeFatalError(f"currency mismatch: tenant={tenant.default_currency} ...")`. (Simplest robust check: compare `(tenant.default_currency or "usd").lower()` to the currency the prices were created under — store/read it consistently. Since prices are created in the tenant currency, the invariant is "tenant currency is stable"; assert it equals what we're about to subscribe in.)
- [ ] **Step 3 — Verify:** `$DJ -m pytest apps/subscriptions -q` → green. **Commit:** `fix(subscriptions): plan Price uses tenant currency + fail loud on mismatch`.

---

### Task 5: Capstone update + final verification

**Files:** Modify `api/v1/tests/test_wave4_orchestration_capstone.py` (the pin assertion → standalone); verification.

- [ ] **Step 1 — Update the Wave-4 capstone:** it asserts the usage `InvoiceItem.create(subscription="sub_1")` (the pin). With C1, usage is standalone — change that assertion to: usage `InvoiceItem.create` has NO `subscription=` kwarg, a standalone `Invoice.create`+`finalize_invoice` is issued, and `compute_business` margin still equals access + seats + usage (the margin math is unchanged — only the invoice routing changed). Run it 2x.
- [ ] **Step 2 — Final verification:**
  - `$DJ manage.py check`; `$DJ manage.py makemigrations --check --dry-run` → "No changes detected".
  - **Fresh-DB:** drop/recreate `ubb`; `$DJ manage.py migrate` applies the new invoicing migration; `$DJ -m pytest -q` whole platform green (report count); `cd ../ubb-sdk && <venv> -m pytest -q` green.
- [ ] **Step 3 — Commit:** `test(wave4.5): capstone usage-standalone + hardening verification`.

---

## Self-Review
**Spec coverage:** C1 standalone-always + drop pin/guard (T1); C2 floor+carry residual + field/migration/audit (T1); I3 status filter (T2); I2 mirror refresh (T3); I1 currency thread + assert (T4); capstone update to standalone reality + fresh-DB verify (T5). Decisions: standalone-always ✓, floor+carry ✓, fail-loud currency ✓.
**Placeholder scan:** T1 gives the full rewritten `_push_to_stripe` + carry logic; T2/T3 one-liners with full code; T4 the currency thread (the mismatch-assert is described concretely against the tenant-currency invariant). No TBD.
**Type consistency:** `_push_to_stripe(..., carry_in=0) -> (standalone_id, items, residual_out)` (T1) consumed by `push_customer_period` (T1); `residual_micros` field (T1) read for carry (T1) + event (T1); `UsageInvoicePushed.residual_micros` (T1); `set_seats` mirror refresh uses `line_items`/`unit_amount_micros` (T3); revenue filter (T2).
**Migration:** one (`invoicing` residual_micros); DB-validated T1 + fresh-DB T5.
**Conservation invariant (C2):** `Σ(billed_cents·10_000) + ending_residual == Σ billed_cost_micros` — the carry chain is linear (each period consumes the immediately-prior pushed period's residual exactly once); idempotent per `rec.id` since carry + lines are deterministic.
