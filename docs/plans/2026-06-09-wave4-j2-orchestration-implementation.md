# Wave 4 — J2 Multi-Axis Subscription Orchestration: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** UBB orchestrates the whole J2 bill — access fee + per-seat (licensed SubscriptionItems) + UBB-rated usage (subscription-pinned InvoiceItem) — as ONE coherent Stripe invoice per business on the tenant's connected account, and fixes the margin-corrupting subscription sync along the way.

**Architecture:** One Stripe Subscription per business; access/seat = licensed `SubscriptionItem`s read via `items.data[]` (current Basil API, never `.plan`); usage = a `subscription=`-pinned pending `InvoiceItem` carrying UBB's `billed_cost_micros`. Two thin models (`TenantBillingPlan`, `CustomerSubscriptionItem`) + a `SubscriptionOrchestrator`. Stripe mocked in tests.

**Tech Stack:** Django 6, django-ninja, stripe==15.2.0 (Basil, API `2025-03-31`), pytest-django, the `ubb` SDK.

**Design ref:** `docs/plans/2026-06-09-wave4-j2-orchestration-design.md`. **Decisions:** usage = pinned InvoiceItem; proration = `create_prorations`; ship plan API now.

---

## ⚠️ Facts (verified)
- `revenue.py:61-77` `subscription_nominal_for_window`: filters `StripeSubscription` by tenant+customer+`status__in=["active","trialing","past_due"]`; `per_interval = sub.amount_micros * sub.quantity` (L68). `accrued_subscription_revenue` = manual + nominal.
- `sync.py:36-79`: the BUG — `expand=["data.plan.product"]`, reads `stripe_sub.plan.product.name/.amount/.currency/.interval` + top-level `current_period_start/end` + `getattr(stripe_sub,"quantity",1)`. Basil removed top-level `current_period_*` (now item-level) and `.plan` is wrong for multi-item subs.
- `economics/services.py:44-55` `compute_business`: sums `compute_live` per seat; **never adds the business's own subscription revenue** → business subscription revenue always 0 (the subscription lives on the business, seats return 0). `compute_live` (L18-42) composes per-customer; `_compose` (L7-13): `margin = total_revenue - provider_cost`.
- `requirements.txt:10` = `stripe>=8.0` (stale → bump). `stripe_call(fn, *, retryable=False, idempotency_key=None, max_retries=3, **kwargs)` at `apps/billing/stripe/services/stripe_service.py:33`; `stripe.api_key` set there + in `apps/billing/connectors/stripe/stripe_api.py:17`.
- Subscriptions webhook: `apps/subscriptions/api/webhooks.py` + `endpoints.py` (NO `StripeWebhookEvent` dedup). The robust dedup pattern is in `api/v1/webhooks.py`.
- `StripeSubscription` (`apps/subscriptions/models.py`): mirror with `amount_micros`, `quantity`, `interval`, `current_period_start/end`, `status`, `stripe_subscription_id`, `customer`, `tenant`, `stripe_product_name`.
- `Customer.resolve_billing_owner()` (pooled seat → business, else self); business→seats via the FK (`business.seats` per `compute_business`). `get_tenant_stripe_account(tenant_id)`, `micros_to_cents()` (raises on non-cent-aligned).

## Conventions
- Platform from `ubb-platform/`, `$DJ` = `DJANGO_SETTINGS_MODULE=config.settings <venv python>`. Baseline **784 platform green**. SDK from `ubb-sdk/`, **177 green**. Stripe MOCKED in tests, never network. Commit per task; `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`. No PR.

---

### Task 1: Connector hardening — SDK pin, startup assertion, subscriptions-webhook dedup

**Files:** Modify `requirements.txt`, `apps/billing/stripe/services/stripe_service.py`, `apps/subscriptions/api/webhooks.py` (+/or `endpoints.py`); Test `apps/subscriptions/api/tests/`.

- [ ] **Step 1 — SDK pin:** `requirements.txt` L10 `stripe>=8.0` → `stripe>=15.0,<16.0`.
- [ ] **Step 2 — Startup assertion** in `apps/billing/stripe/services/stripe_service.py` (after `import stripe`): `assert tuple(int(p) for p in stripe.VERSION.split(".")[:1]) >= (15,), f"Stripe SDK must be >=15 for Basil API; got {stripe.VERSION}"`.
- [ ] **Step 3 — API version: decide globally vs per-call.** First run the FULL suite with the Basil version pinned globally (temporarily add `stripe.api_version = "2025-03-31"` in stripe_service.py) → `$DJ -m pytest -q`. If GREEN (784), keep the global pin (commit it). If ANY existing path regresses, REMOVE the global pin and instead pass `stripe_version="2025-03-31"` per orchestration `stripe_call` (Task 4) only. Report which path you took + the suite result.
- [ ] **Step 4 — Subscriptions-webhook dedup (Critical 4).** READ `api/v1/webhooks.py` for the `StripeWebhookEvent` get_or_create dedup + error-classification pattern, and `apps/subscriptions/api/webhooks.py`/`endpoints.py` for the current bare handler. Add the SAME dedup (a `StripeWebhookEvent` row keyed on the Stripe event id, skip if already processed) + replace bare-500 with classified handling, so a duplicate/retried `customer.subscription.updated` can't double-apply.
  - **Failing test:** post the same `customer.subscription.updated` event twice → the handler processes it once (second is a deduped no-op, 200).
- [ ] **Step 5 — Verify:** `$DJ -m pytest apps/subscriptions api/v1/tests/test_webhooks*.py -q`; full suite for the api_version decision. **Commit:** `feat(subscriptions): pin stripe>=15 + Basil version + webhook dedup`.

---

### Task 2: Margin-correctness bundle (atomic) — sync fix + `_sum_items` + revenue + compute_business

**Files:** Create `apps/subscriptions/stripe/items.py`; Modify `apps/subscriptions/stripe/sync.py`, `apps/subscriptions/api/webhooks.py`, `apps/subscriptions/economics/revenue.py`, `apps/subscriptions/economics/services.py`; Tests in `apps/subscriptions/...`.

> These changes are ONE atomic commit (Critical 2): `_sum_items` makes `amount_micros = Σ(access + seat×qty)`, and revenue.py must drop `* sub.quantity` in the SAME commit, or revenue is overstated by the seat multiple.

- [ ] **Step 1 — Failing test** (`apps/subscriptions/economics/tests/`): build a `StripeSubscription` with `amount_micros=130_000_000`, `quantity=10`, `interval="month"`; assert `subscription_nominal_for_window` over a full month returns `130_000_000` (NOT `1_300_000_000`). And a `compute_business` test: a business with a `StripeSubscription` (amount 130M) + 2 seats each with usage → assert `totals["subscription_revenue_micros"] == 130_000_000` (today it's 0).
- [ ] **Step 2 — `_sum_items` helper** `apps/subscriptions/stripe/items.py`:
```python
from datetime import datetime, timezone as dt_timezone


def _sum_items(stripe_sub):
    """(amount_micros, seat_qty, interval). amount = Σ licensed unit_amount×qty (access+seat);
    metered items contribute 0 (their revenue arrives as InvoiceItems)."""
    total, seat_qty, interval = 0, 1, "month"
    for it in stripe_sub["items"]["data"]:
        price = it["price"]; rec = price.get("recurring") or {}
        interval = rec.get("interval", interval)
        if rec.get("usage_type") == "metered":
            continue
        qty = it.get("quantity", 1) or 1
        total += (price["unit_amount"] or 0) * 10_000 * qty
        if qty > 1:
            seat_qty = qty
    return total, seat_qty, interval


def _period_end(stripe_sub):
    items = stripe_sub["items"]["data"]
    ends = [i.get("current_period_end") for i in items if i.get("current_period_end")]
    if len(set(ends)) > 1:
        import logging; logging.getLogger(__name__).warning("subscription has mixed item periods")
    return _u(ends[0]) if ends else None


def _period_start(stripe_sub):
    items = stripe_sub["items"]["data"]
    starts = [i.get("current_period_start") for i in items if i.get("current_period_start")]
    return _u(starts[0]) if starts else None


def _product_name(stripe_sub):
    for it in stripe_sub["items"]["data"]:
        prod = (it["price"] or {}).get("product")
        if isinstance(prod, dict) and prod.get("name"):
            return prod["name"]
    return ""


def _u(ts):
    return datetime.fromtimestamp(ts, tz=dt_timezone.utc) if ts else None
```
- [ ] **Step 3 — sync.py:** change `expand=["data.plan.product"]` → `expand=["data.items.data.price.product"]`; replace the `defaults={...}` block to use `_sum_items`/`_period_*`/`_product_name`:
```python
from apps.subscriptions.stripe.items import _sum_items, _period_start, _period_end, _product_name
...
amount_micros, seat_qty, interval = _sum_items(stripe_sub)
StripeSubscription.objects.update_or_create(stripe_subscription_id=stripe_sub.id, defaults={
    "tenant": tenant, "customer_id": customer_id,
    "stripe_product_name": _product_name(stripe_sub), "status": stripe_sub.status,
    "amount_micros": amount_micros, "currency": stripe_sub.get("currency", "usd"),
    "interval": interval, "current_period_start": _period_start(stripe_sub),
    "current_period_end": _period_end(stripe_sub), "last_synced_at": timezone.now(),
    "quantity": seat_qty})
```
- [ ] **Step 4 — webhooks.py:** in `handle_subscription_created`/`updated`, replace `stripe_sub.plan.*`/`getattr(...,"quantity",1)`/top-level periods with `_sum_items`/`_period_*`/`_product_name` (same as sync). (Verify the handler reads the event's subscription object; expand if needed via a retrieve, or use the event payload's `items.data`.)
- [ ] **Step 5 — revenue.py L68 (atomic):** `per_interval = sub.amount_micros * sub.quantity` → `per_interval = sub.amount_micros`.
- [ ] **Step 6 — compute_business (Critical 1)** in `economics/services.py`: after summing per-seat, add the business's OWN subscription revenue ONCE:
```python
    business_sub = RevenueService.accrued_subscription_revenue(
        tenant_id, business.id, start_date, end_date)
    totals["subscription_revenue_micros"] += business_sub
    totals["total_revenue_micros"] += business_sub
    totals["gross_margin_micros"] += business_sub
```
(per-seat subscription revenue is 0 since the sub is on the business, so this adds it exactly once.)
- [ ] **Step 7 — Verify:** `$DJ -m pytest apps/subscriptions -q` → green (the 130M-not-1.3B + business-130M tests). **Commit (single atomic):** `fix(subscriptions): read items.data[] (Basil) + correct multi-item margin + business subscription rollup`.

---

### Task 3: Plan models — `TenantBillingPlan` + `CustomerSubscriptionItem`

**Files:** Create `apps/subscriptions/plans/__init__.py`, `apps/subscriptions/plans/models.py`; register the app module if needed (models under the existing `subscriptions` app — put them in a `plans` submodule imported by the app, OR directly in `apps/subscriptions/models.py` if the app discovers models there). migration `subscriptions/00XX_*`.

- [ ] **Step 1 — Failing test:** create a `TenantBillingPlan(tenant, key="pro", name="Pro", access_fee_micros=50_000_000, per_seat_micros=8_000_000, interval="month")` and assert it round-trips + `unique_together(tenant,key)` rejects a duplicate key.
- [ ] **Step 2 — Models** (`apps/subscriptions/plans/models.py`; import them from `apps/subscriptions/models.py` so Django discovers them, OR define in `models.py` directly — verify how the app loads models):
```python
from django.db import models
from core.models import BaseModel


class TenantBillingPlan(BaseModel):
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE, related_name="billing_plans")
    key = models.CharField(max_length=64)
    name = models.CharField(max_length=255)
    access_fee_micros = models.BigIntegerField(default=0)
    per_seat_micros = models.BigIntegerField(default=0)
    interval = models.CharField(max_length=5, default="month")  # month|year
    usage_mode = models.CharField(max_length=12, default="invoice_item")  # invoice_item|none
    stripe_access_product_id = models.CharField(max_length=255, blank=True, default="")
    stripe_access_price_id = models.CharField(max_length=255, blank=True, default="")
    stripe_seat_product_id = models.CharField(max_length=255, blank=True, default="")
    stripe_seat_price_id = models.CharField(max_length=255, blank=True, default="")
    provisioned_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "ubb_billing_plan"
        constraints = [models.UniqueConstraint(fields=["tenant", "key"], name="uq_billing_plan_tenant_key")]


class CustomerSubscriptionItem(BaseModel):
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE, related_name="sub_items")
    customer = models.ForeignKey("customers.Customer", on_delete=models.CASCADE, related_name="sub_items")
    stripe_subscription = models.ForeignKey("subscriptions.StripeSubscription", on_delete=models.CASCADE,
                                            related_name="line_items")
    stripe_subscription_item_id = models.CharField(max_length=255, unique=True)
    axis = models.CharField(max_length=8)  # access|seat
    stripe_price_id = models.CharField(max_length=255)
    unit_amount_micros = models.BigIntegerField(default=0)
    quantity = models.IntegerField(default=1)
    plan = models.ForeignKey(TenantBillingPlan, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        db_table = "ubb_customer_sub_item"
```
- [ ] **Step 3 — Migration:** `$DJ manage.py makemigrations subscriptions`; `makemigrations --check`; `migrate`.
- [ ] **Step 4 — Verify:** `$DJ -m pytest apps/subscriptions -q`. **Commit:** `feat(subscriptions): TenantBillingPlan + CustomerSubscriptionItem models`.

---

### Task 4: `SubscriptionOrchestrator` — provision, subscribe, set_seats

**Files:** Create `apps/subscriptions/orchestration/__init__.py`, `apps/subscriptions/orchestration/service.py`; Test `apps/subscriptions/orchestration/tests/test_service.py` (Stripe mocked).

- [ ] **Step 1 — Failing tests** (mock `stripe.Product.create`, `stripe.Price.create`, `stripe.Subscription.create`, `stripe.SubscriptionItem.modify` at `apps...service.stripe.*` or via `stripe_call`): `ensure_plan_provisioned` creates 1 Product+1 Price per non-zero axis and saves the ids + `provisioned_at`; a second call is a no-op (no new Stripe calls). `subscribe(business, plan, seats=10)` calls `Subscription.create` with `items=[access×1, seat×10]` + `billing_cycle_anchor` set + persists 2 `CustomerSubscriptionItem` rows + a `StripeSubscription` mirror with `amount_micros=130_000_000`. `set_seats(business, plan, 12)` calls `SubscriptionItem.modify(quantity=12, proration_behavior="create_prorations")`.
- [ ] **Step 2 — Implement** `apps/subscriptions/orchestration/service.py` (use `stripe_call` with `stripe_account=connected` + deterministic keys; gate with charge-ready; partial-save each id):
```python
import stripe
from django.utils import timezone
from apps.billing.stripe.services.stripe_service import stripe_call
from apps.platform.queries import get_tenant_stripe_account
from apps.billing.stripe.services.stripe_service import micros_to_cents  # verify location
from apps.subscriptions.plans.models import TenantBillingPlan, CustomerSubscriptionItem
from apps.subscriptions.models import StripeSubscription


class OrchestrationError(Exception):
    pass


def _require_charge_ready(tenant):
    if not (tenant.stripe_connected_account_id and tenant.charges_enabled):
        raise OrchestrationError("tenant Stripe account is not charge-ready")


def _next_month_anchor():
    import datetime
    today = timezone.now()
    y, m = (today.year + 1, 1) if today.month == 12 else (today.year, today.month + 1)
    return int(datetime.datetime(y, m, 1, tzinfo=datetime.timezone.utc).timestamp())


class SubscriptionOrchestrator:
    @staticmethod
    def ensure_plan_provisioned(plan):
        if plan.provisioned_at:
            return plan
        tenant = plan.tenant
        _require_charge_ready(tenant)
        connected = get_tenant_stripe_account(tenant.id)
        if plan.access_fee_micros and not plan.stripe_access_price_id:
            prod = stripe_call(stripe.Product.create, retryable=True,
                idempotency_key=f"plan-prod-access-{plan.id}", name=f"{plan.name} Access",
                stripe_account=connected)
            price = stripe_call(stripe.Price.create, retryable=True,
                idempotency_key=f"plan-price-access-{plan.id}", product=prod.id, currency="usd",
                unit_amount=micros_to_cents(plan.access_fee_micros),
                recurring={"interval": plan.interval, "usage_type": "licensed"},
                stripe_account=connected)
            plan.stripe_access_product_id, plan.stripe_access_price_id = prod.id, price.id
            plan.save(update_fields=["stripe_access_product_id", "stripe_access_price_id", "updated_at"])
        if plan.per_seat_micros and not plan.stripe_seat_price_id:
            prod = stripe_call(stripe.Product.create, retryable=True,
                idempotency_key=f"plan-prod-seat-{plan.id}", name=f"{plan.name} Seats",
                stripe_account=connected)
            price = stripe_call(stripe.Price.create, retryable=True,
                idempotency_key=f"plan-price-seat-{plan.id}", product=prod.id, currency="usd",
                unit_amount=micros_to_cents(plan.per_seat_micros),
                recurring={"interval": plan.interval, "usage_type": "licensed"},
                stripe_account=connected)
            plan.stripe_seat_product_id, plan.stripe_seat_price_id = prod.id, price.id
            plan.save(update_fields=["stripe_seat_product_id", "stripe_seat_price_id", "updated_at"])
        plan.provisioned_at = timezone.now()
        plan.save(update_fields=["provisioned_at", "updated_at"])
        return plan

    @staticmethod
    def subscribe(customer, plan, seats):
        owner = customer.resolve_billing_owner()
        tenant = plan.tenant
        _require_charge_ready(tenant)
        connected = get_tenant_stripe_account(tenant.id)
        SubscriptionOrchestrator.ensure_plan_provisioned(plan)
        items = []
        if plan.access_fee_micros:
            items.append({"price": plan.stripe_access_price_id, "quantity": 1})
        if plan.per_seat_micros:
            items.append({"price": plan.stripe_seat_price_id, "quantity": seats})
        sub = stripe_call(stripe.Subscription.create, retryable=True,
            idempotency_key=f"sub-create-{owner.id}-{plan.id}",
            customer=owner.stripe_customer_id, items=items,
            collection_method="charge_automatically",
            billing_cycle_anchor=_next_month_anchor(), proration_behavior="create_prorations",
            stripe_account=connected)
        from apps.subscriptions.stripe.items import _sum_items, _period_start, _period_end, _product_name
        amount_micros, seat_qty, interval = _sum_items(sub)
        mirror, _ = StripeSubscription.objects.update_or_create(
            stripe_subscription_id=sub["id"], defaults={
                "tenant": tenant, "customer_id": owner.id, "status": sub["status"],
                "amount_micros": amount_micros, "quantity": seat_qty, "interval": interval,
                "currency": sub.get("currency", "usd"), "stripe_product_name": _product_name(sub),
                "current_period_start": _period_start(sub), "current_period_end": _period_end(sub),
                "last_synced_at": timezone.now()})
        for it in sub["items"]["data"]:
            axis = "access" if it["price"]["id"] == plan.stripe_access_price_id else "seat"
            CustomerSubscriptionItem.objects.update_or_create(
                stripe_subscription_item_id=it["id"], defaults={
                    "tenant": tenant, "customer_id": owner.id, "stripe_subscription": mirror,
                    "axis": axis, "stripe_price_id": it["price"]["id"],
                    "unit_amount_micros": (it["price"]["unit_amount"] or 0) * 10_000,
                    "quantity": it.get("quantity", 1), "plan": plan})
        return mirror

    @staticmethod
    def set_seats(business, plan, new_seats, *, change_event_id):
        tenant = plan.tenant
        _require_charge_ready(tenant)
        connected = get_tenant_stripe_account(tenant.id)
        item = CustomerSubscriptionItem.objects.get(customer=business, plan=plan, axis="seat")
        stripe_call(stripe.SubscriptionItem.modify, retryable=True,
            idempotency_key=f"seat-qty-{item.stripe_subscription_item_id}-{change_event_id}",
            id=item.stripe_subscription_item_id, quantity=new_seats,
            proration_behavior="create_prorations", stripe_account=connected)
        item.quantity = new_seats
        item.save(update_fields=["quantity", "updated_at"])
```
(VERIFY `micros_to_cents` import path; `stripe_call`'s kwargs passthrough; `owner.stripe_customer_id` exists — if a business lacks a Stripe customer, the orchestrator must create one first via the existing customer-provisioning path. Confirm + add that step if needed.)
- [ ] **Step 3 — Verify:** `$DJ -m pytest apps/subscriptions/orchestration -q`. **Commit:** `feat(subscriptions): SubscriptionOrchestrator (provision/subscribe/set_seats)`.

---

### Task 5: Plan + subscribe + seats API + SDK

**Files:** Modify `api/v1/platform_endpoints.py`, `api/v1/schemas.py`; SDK `ubb-sdk/ubb/...` (a subscriptions/plans client + `UBBClient` delegates); Tests.

- [ ] **Step 1 — Failing tests** (platform): `POST /api/v1/platform/plans` `{key,name,access_fee_micros,per_seat_micros,interval}` → 201 + plan exists; `POST /api/v1/platform/customers/{external_id}/subscribe` `{plan_key, seats}` → 200 (Stripe mocked) + a `StripeSubscription` mirror exists for the owner; `POST /api/v1/platform/customers/{external_id}/seats` `{seats}` → 200 + the seat item quantity updated.
- [ ] **Step 2 — Endpoints** on `platform_api` (ApiKeyAuth, scoped to `request.auth.tenant`): create plan; resolve the customer by external_id; call `SubscriptionOrchestrator.subscribe`/`set_seats` (for set_seats generate a `change_event_id` = a uuid4 or the request's idempotency context). Schemas `PlanIn`/`PlanOut`/`SubscribeIn`/`SeatsIn`.
- [ ] **Step 3 — SDK:** `create_plan(key, name, *, access_fee_micros, per_seat_micros, interval="month", usage_mode="invoice_item")`, `subscribe_customer(external_id, plan_key, seats)`, `set_seats(external_id, seats)`, `get_subscription(external_id)` (if a read endpoint exists; else skip). SDK tests.
- [ ] **Step 4 — Verify:** `$DJ -m pytest api/v1 apps/subscriptions -q`; SDK green. **Commit:** `feat(subscriptions): plan + subscribe + seats API (+SDK)`.

---

### Task 6: Usage↔subscription coherence + seat-count hooks

**Files:** Modify `apps/billing/invoicing/services/postpaid_service.py` (the push branch ~L135-148 + the status filter ~L137); the seat add/remove/suspend/close path (`api/v1/platform_endpoints.py` create + the `Customer` status-change/soft_delete handler); Tests.

- [ ] **Step 1 — Failing tests:** (a) a postpaid business WITH an active subscription → `_push_to_stripe` calls `InvoiceItem.create` with `subscription=<sub_id>` (the pin), NOT a standalone invoice. (b) a business with NO subscription → standalone invoice (unchanged). (c) status filter includes `unpaid`: a business whose sub is `unpaid` → still pins to the subscription (no standalone). (d) seat add → the business's seat item quantity is pushed to `new_count`; seat soft-delete/suspend → quantity decremented.
- [ ] **Step 2 — Coherence:** in `_push_to_stripe`, look up the owner's subscription `StripeSubscription.objects.filter(tenant=tenant, customer=owner, status__in=["active","trialing","past_due","unpaid"]).order_by("-created_at").first()`; if present pass `subscription=sub.stripe_subscription_id` to `stripe.InvoiceItem.create` (key `usage-item-{rec.id}-{i}`); else the standalone path. **Late-push guard:** after create, if the sub's `latest_invoice` status is `paid`/`void`, route the item to a standalone invoice for that period + emit a loud log/alert (don't leave it pending). (Verify the `_push_to_stripe` signature + how `owner`/`tenant`/`connected` are in scope.)
- [ ] **Step 3 — Seat hooks:** add a helper `seat_count(business)` = active seats under the business; call `SubscriptionOrchestrator.set_seats(business, plan, seat_count(business), change_event_id=<uuid4 or audit id>)` `on_commit` in the SAME transaction as: the seat-create path (`POST /platform/customers` when account_type=seat with a parent business that has a plan/subscription), and the seat suspend/close/soft_delete path. Only fire when the business has an active subscription + a seat-axis item (else no-op). (VERIFY where seat create + status transitions happen; wire the hook so a removed seat can't bill as a ghost.)
- [ ] **Step 4 — Verify:** `$DJ -m pytest apps/billing apps/subscriptions api/v1 -q`. **Commit:** `feat(subscriptions): deterministic usage↔subscription coherence + seat-count push`.

---

### Task 7: Capstone — one coherent multi-axis bill via the SDK

**Files:** Create `api/v1/tests/test_wave4_orchestration_capstone.py` (live_server + SDK; Stripe mocked process-wide).

- [ ] **Step 1 — Write** (`@pytest.mark.django_db(transaction=True)` + `live_server` + the `_no_outbox_dispatch` pattern; patch `stripe.Product.create`/`Price.create`/`Subscription.create`/`SubscriptionItem.modify`/`InvoiceItem.create` to return realistic objects with `items.data[]`). The mocked `Subscription.create` returns 2 items (access price, seat price ×10). Via the SDK: tenant (charges_enabled) `create_plan("pro", access_fee_micros=50_000_000, per_seat_micros=8_000_000)`; subscribe a business with 10 seats → assert 2 `CustomerSubscriptionItem` rows + mirror `amount_micros == 130_000_000`; `set_seats(biz, 12)` → assert `SubscriptionItem.modify(quantity=12, proration_behavior="create_prorations")` called + item quantity 12; record usage for seats (rate-card→billed) + run the postpaid close → assert one `InvoiceItem.create(subscription=<sub_id>)` (the pin), no standalone; `MarginService.compute_business` → `subscription_revenue_micros` reflects $50 + 12×$8 = 146M (the regression proof the sync fix + compute_business fix worked). Mock realistically; the goal is the wiring + the math, not real Stripe.
- [ ] **Step 2 — Run** 2-3x; full platform suite `$DJ -m pytest -q | tail -2`. **Commit:** `test(wave4): multi-axis orchestration capstone (one coherent bill + correct margin)`.

---

### Task 8: Final verification
- [ ] `$DJ manage.py check`; `$DJ manage.py makemigrations --check --dry-run` → "No changes detected".
- [ ] **Fresh-DB:** drop/recreate `ubb`; `$DJ manage.py migrate` applies the new `subscriptions` migration; `$DJ -m pytest -q` whole platform green (report count); `cd ../ubb-sdk && <venv> -m pytest -q` green.
- [ ] Capstone passes; clean tree.

---

## Self-Review
**Spec coverage:** connector pin + webhook dedup + api_version decision (T1, Critical 4 + pin); sync fix + `_sum_items` + revenue one-liner + compute_business (T2, Criticals 1+2, the live bug); plan models (T3); orchestrator provision/subscribe(billing_cycle_anchor)/set_seats(event-id key) (T4); plan+subscribe+seats API+SDK — decision 3 (T5); pinned InvoiceItem (decision 1) + unpaid status + late-push guard + seat hooks (T6); capstone proving one invoice + correct margin (T7); verification (T8). Proration `create_prorations` (decision 2) in T4/T6.
**Placeholder scan:** T2 gives the full `_sum_items`/revenue/compute_business code; T4 the full orchestrator; T1/T5/T6 cite read-and-follow patterns with concrete code where net-new. "VERIFY" notes are real verifications, not placeholders.
**Type consistency:** `_sum_items`→`(amount_micros, seat_qty, interval)` used by sync (T2) + orchestrator (T4); `TenantBillingPlan`/`CustomerSubscriptionItem` (T3) used by orchestrator (T4) + coherence (T6); `SubscriptionOrchestrator.subscribe/set_seats` (T4) used by API (T5) + hooks (T6) + capstone (T7); `change_event_id` param on set_seats (T4) supplied by T5/T6.
**Migration:** one `subscriptions` migration (T3 models); DB-validated T3 + fresh-DB T8.
**Critique must-fixes mapped:** Critical1→T2.6; Critical2→T2 atomic commit; Critical3→T4 billing_cycle_anchor; Critical4→T1.4 (first); unpaid→T6.2; event-id idempotency→T4 set_seats; seat hooks→T6.3; late-push guard→T6.2; stripe pin→T1.1-2; api_version caution→T1.3; partial-save→T4 ensure_plan_provisioned; mixed-interval warn→T2 `_period_end`.
