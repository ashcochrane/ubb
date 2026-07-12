# Pricing Stage B — Revenue-Source Disambiguation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the margin engine count each revenue stream exactly once on an earned/accrual basis — subscription from the Stripe subscription's recurring amount (not the blended paid invoice), usage from `Σ billed` only when the customer's usage is billed through UBB — so the dashboard reads identically across all subscription/usage timing combos and the two bugs (metering-only invisible COGS; postpaid usage double-count) are fixed.

**Architecture:** A per-customer `revenue_mode` (`billed | metered_only`, default from `billing_mode`) decides whether usage counts as revenue. `RevenueService` gains an accrual subscription figure (`amount_micros × quantity`, pro-rated). `MarginService._compose` becomes mode-aware. All margin call-sites (service + the two inline endpoint formulas) move onto the one composition.

**Tech Stack:** Django 6, django-ninja, pytest-django, Postgres, SDK (httpx).

**Design ref:** `docs/plans/2026-06-08-pricing-stageB-revenue-source-design.md`

---

## ⚠️ Caveats

- **Behavior change (intended):** margin numbers move for meter-only (COGS now subtracted) and postpaid (double-count removed) customers, and subscription revenue becomes accrual (nominal) not cash (paid invoice). **Existing `test_economics.py` / margin-endpoint tests that assert the OLD formula must be updated to the new one** — Task 3/4 call this out. Prepaid totals are unchanged in spirit.
- `_compose` changes signature/return (adds `revenue_mode` arg + `usage_revenue` return) — both callers updated in Task 3.
- Two additive migrations (`customers/0010`, `subscriptions/0004`) via `makemigrations` + `--check`.

## Conventions

- Run from `ubb-platform/`. Venv python: `/c/Users/tom_l/git/ubb/ubb-platform/.venv/Scripts/python.exe`. `$DJ` = `DJANGO_SETTINGS_MODULE=config.settings <python>`.
- Static: `$DJ manage.py check` · `$DJ manage.py makemigrations --check --dry-run`. DB: `$DJ manage.py migrate` · `$DJ -m pytest <paths> -q`.
- Baseline: **674 platform + 142 SDK green.** Branch `tl-changes-05-06-26`. Commit per task; end messages with `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.
- Heads: customers `0009_rename_arrears_to_min_balance`, subscriptions `0003_margin_intelligence`. `Tenant.billing_mode` default `"meter_only"`, choices `meter_only|prepaid|postpaid`.

---

### Task 1: Schema — `Customer.revenue_mode` + `CustomerEconomics.{revenue_mode,total_revenue_micros}`

**Files:** Modify `apps/platform/customers/models.py`, `apps/subscriptions/economics/models.py`; migrations `customers/0010_*`, `subscriptions/0004_*`; Test `apps/subscriptions/tests/test_revenue_mode_fields.py`.

- [ ] **Step 1 — Failing test** `apps/subscriptions/tests/test_revenue_mode_fields.py`:
```python
import pytest
from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer


@pytest.mark.django_db
def test_revenue_mode_columns_exist_with_defaults():
    t = Tenant.objects.create(name="T")
    c = Customer.objects.create(tenant=t, external_id="c1")
    assert c.revenue_mode == ""  # blank = derive from billing_mode
    from apps.subscriptions.economics.models import CustomerEconomics
    import datetime
    e = CustomerEconomics.objects.create(tenant=t, customer=c,
        period_start=datetime.date(2026, 6, 1), period_end=datetime.date(2026, 7, 1))
    assert e.revenue_mode == "" and e.total_revenue_micros == 0
```

- [ ] **Step 2 — Run** → FAIL.

- [ ] **Step 3 — Add columns.** In `apps/platform/customers/models.py` on `Customer` (e.g. after `metadata`):
```python
    revenue_mode = models.CharField(max_length=20, blank=True, default="")  # "" | "billed" | "metered_only"
```
In `apps/subscriptions/economics/models.py` on `CustomerEconomics` (after `subscription_revenue_micros` block):
```python
    total_revenue_micros = models.BigIntegerField(default=0)
    revenue_mode = models.CharField(max_length=20, blank=True, default="")
```

- [ ] **Step 4 — Migrations:** `$DJ manage.py makemigrations customers subscriptions`; `$DJ manage.py makemigrations --check --dry-run` → "No changes detected"; `$DJ manage.py migrate`.

- [ ] **Step 5 — Verify:** `$DJ manage.py check`; `$DJ -m pytest apps/subscriptions/tests/test_revenue_mode_fields.py -q` → green. **Commit:** `feat(economics): revenue_mode + total_revenue_micros columns`.

---

### Task 2: `RevenueService` — `resolve_revenue_mode` + accrual subscription revenue

**Files:** Modify `apps/subscriptions/economics/revenue.py`; Test `apps/subscriptions/tests/test_revenue_service_accrual.py`.

- [ ] **Step 1 — Failing tests** `apps/subscriptions/tests/test_revenue_service_accrual.py`:
```python
import datetime
import pytest
from django.utils import timezone
from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.subscriptions.models import StripeSubscription
from apps.subscriptions.economics.revenue import RevenueService

PS, PE = datetime.date(2026, 6, 1), datetime.date(2026, 7, 1)  # full June


@pytest.mark.django_db
class TestAccrual:
    def test_resolve_revenue_mode_default_and_override(self):
        t = Tenant.objects.create(name="MO", billing_mode="meter_only")
        c = Customer.objects.create(tenant=t, external_id="c1")
        assert RevenueService.resolve_revenue_mode(t, c) == "metered_only"
        tb = Tenant.objects.create(name="PP", products=["metering", "billing"], billing_mode="postpaid")
        cb = Customer.objects.create(tenant=tb, external_id="c1")
        assert RevenueService.resolve_revenue_mode(tb, cb) == "billed"
        cb.revenue_mode = "metered_only"; cb.save(update_fields=["revenue_mode"])
        assert RevenueService.resolve_revenue_mode(tb, cb) == "metered_only"  # override wins

    def test_subscription_nominal_full_month(self):
        t = Tenant.objects.create(name="T")
        c = Customer.objects.create(tenant=t, external_id="c1")
        now = timezone.now()
        StripeSubscription.objects.create(tenant=t, customer=c, stripe_subscription_id="sub_1",
            stripe_product_name="Pro", status="active", amount_micros=10_000_000, quantity=3,
            currency="usd", interval="month", current_period_start=now, current_period_end=now,
            last_synced_at=now)
        # 10/unit * 3 seats = 30/mo; full June -> 30_000_000
        assert RevenueService.subscription_nominal_for_window(t.id, c.id, PS, PE) == 30_000_000

    def test_canceled_subscription_excluded(self):
        t = Tenant.objects.create(name="T")
        c = Customer.objects.create(tenant=t, external_id="c1")
        now = timezone.now()
        StripeSubscription.objects.create(tenant=t, customer=c, stripe_subscription_id="sub_x",
            stripe_product_name="Pro", status="canceled", amount_micros=10_000_000, quantity=3,
            currency="usd", interval="month", current_period_start=now, current_period_end=now,
            last_synced_at=now)
        assert RevenueService.subscription_nominal_for_window(t.id, c.id, PS, PE) == 0
```

- [ ] **Step 2 — Run** → FAIL.

- [ ] **Step 3 — Implement.** Add these three `@staticmethod`s **inside the existing `RevenueService` class body** in `apps/subscriptions/economics/revenue.py` (the file already defines `_month_iter`, `_days_in_month`, and `from django.db.models import Sum` — do NOT create a second `RevenueService` class):
```python
    @staticmethod
    def resolve_revenue_mode(tenant, customer):
        mode = getattr(customer, "revenue_mode", "") or ""
        if mode:
            return mode
        return "metered_only" if tenant.billing_mode == "meter_only" else "billed"

    @staticmethod
    def subscription_nominal_for_window(tenant_id, customer_id, start_date, end_date) -> int:
        from apps.subscriptions.models import StripeSubscription
        subs = StripeSubscription.objects.filter(
            tenant_id=tenant_id, customer_id=customer_id,
            status__in=["active", "trialing", "past_due"])
        total = 0
        for sub in subs:
            per_interval = sub.amount_micros * sub.quantity
            monthly = per_interval // 12 if sub.interval == "year" else per_interval
            for m_start, m_end in _month_iter(start_date, end_date):
                w_start = max(start_date, m_start)
                w_end = min(end_date, m_end)
                overlap_days = (w_end - w_start).days
                if overlap_days <= 0:
                    continue
                total += monthly * overlap_days // _days_in_month(m_start.year, m_start.month)
        return total

    @staticmethod
    def accrued_subscription_revenue(tenant_id, customer_id, start_date, end_date) -> int:
        return (RevenueService.manual_revenue_for_window(tenant_id, customer_id, start_date, end_date)
                + RevenueService.subscription_nominal_for_window(tenant_id, customer_id, start_date, end_date))
```

- [ ] **Step 4 — Verify:** `$DJ -m pytest apps/subscriptions/tests/test_revenue_service_accrual.py -q` → green. **Commit:** `feat(economics): accrual subscription revenue + revenue_mode resolver`.

---

### Task 3: `MarginService` — mode-aware compose (the core fix)

**Files:** Modify `apps/subscriptions/economics/services.py`; Test `apps/subscriptions/tests/test_margin_modes.py` (+ update existing `test_economics.py` assertions that used the old formula).

- [ ] **Step 1 — Failing tests** `apps/subscriptions/tests/test_margin_modes.py`:
```python
import datetime
import pytest
from django.utils import timezone
from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.metering.usage.models import UsageEvent
from apps.subscriptions.models import StripeSubscription, SubscriptionInvoice
from apps.subscriptions.economics.services import MarginService

PS, PE = datetime.date(2026, 6, 1), datetime.date(2026, 7, 1)


def _usage(t, c, provider, billed):
    UsageEvent.objects.create(tenant=t, customer=c, request_id="r", idempotency_key="i",
                              provider_cost_micros=provider, billed_cost_micros=billed)


@pytest.mark.django_db
class TestMarginModes:
    def test_metering_only_subtracts_cogs(self):
        from apps.subscriptions.economics.models import CustomerRevenueProfile
        t = Tenant.objects.create(name="MO", billing_mode="meter_only")
        c = Customer.objects.create(tenant=t, external_id="c1")
        CustomerRevenueProfile.objects.create(tenant=t, customer=c, recurring_amount_micros=100,
                                              effective_from=PS)
        _usage(t, c, provider=30, billed=30)  # passthrough
        d = MarginService.compute_live(t.id, c.id, PS, PE)
        assert d["revenue_mode"] == "metered_only"
        assert d["gross_margin_micros"] == 70   # was 100 — COGS now visible

    def test_billed_uses_nominal_sub_not_paid_invoice(self):
        t = Tenant.objects.create(name="PP", products=["metering", "billing"], billing_mode="postpaid")
        c = Customer.objects.create(tenant=t, external_id="c1")
        now = timezone.now()
        sub = StripeSubscription.objects.create(tenant=t, customer=c, stripe_subscription_id="s1",
            stripe_product_name="Pro", status="active", amount_micros=20_000_000, quantity=1,
            currency="usd", interval="month", current_period_start=now, current_period_end=now,
            last_synced_at=now)  # nominal 20_000_000
        # blended paid invoice INCLUDES usage (the double-count trap): 20M sub + 5M usage = 25M
        SubscriptionInvoice.objects.create(tenant=t, customer=c, stripe_subscription=sub,
            stripe_invoice_id="in_1", amount_paid_micros=25_000_000, currency="usd",
            period_start=now, period_end=now, paid_at=now)
        _usage(t, c, provider=3_000_000, billed=5_000_000)
        d = MarginService.compute_live(t.id, c.id, PS, PE)
        # margin = nominal_sub(20M) + billed(5M) - provider(3M) = 22M  (NOT 25M+5M-3M)
        assert d["gross_margin_micros"] == 22_000_000
        assert d["total_revenue_micros"] == 25_000_000

    def test_metering_only_override_on_billed_tenant(self):
        t = Tenant.objects.create(name="PP", products=["metering", "billing"], billing_mode="postpaid")
        c = Customer.objects.create(tenant=t, external_id="c1", revenue_mode="metered_only")
        _usage(t, c, provider=30, billed=80)  # billed > provider, but metered_only => usage excluded
        d = MarginService.compute_live(t.id, c.id, PS, PE)
        assert d["gross_margin_micros"] == -30 and d["usage_revenue_micros"] == 0
```

- [ ] **Step 2 — Run** → FAIL.

- [ ] **Step 3 — Implement.** Rewrite `_compose` and the two methods in `apps/subscriptions/economics/services.py`:
```python
def _compose(subscription_revenue, usage_billed, provider_cost, revenue_mode):
    usage_revenue = usage_billed if revenue_mode == "billed" else 0
    total_revenue = subscription_revenue + usage_revenue
    margin = total_revenue - provider_cost
    pct = (Decimal(margin) / Decimal(total_revenue) * 100).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP) if total_revenue > 0 else Decimal("0")
    return total_revenue, usage_revenue, margin, pct
```
`compute_live`:
```python
    @staticmethod
    def compute_live(tenant_id, customer_id, start_date, end_date) -> dict:
        from apps.metering.queries import get_customer_cost_totals
        from apps.platform.tenants.models import Tenant
        from apps.platform.customers.models import Customer
        costs = get_customer_cost_totals(tenant_id, customer_id, start_date, end_date)
        tenant = Tenant.objects.get(id=tenant_id)
        customer = Customer.objects.get(id=customer_id)
        mode = RevenueService.resolve_revenue_mode(tenant, customer)
        subscription_revenue = RevenueService.accrued_subscription_revenue(
            tenant_id, customer_id, start_date, end_date)
        total_revenue, usage_revenue, margin, pct = _compose(
            subscription_revenue, costs["billed_cost_micros"], costs["provider_cost_micros"], mode)
        return {
            "customer_id": str(customer_id),
            "revenue_mode": mode,
            "subscription_revenue_micros": subscription_revenue,
            "usage_billed_micros": costs["billed_cost_micros"],
            "usage_revenue_micros": usage_revenue,
            "provider_cost_micros": costs["provider_cost_micros"],
            "total_revenue_micros": total_revenue,
            "gross_margin_micros": margin,
            "margin_percentage": float(pct),
            "event_count": costs["event_count"],
        }
```
`snapshot_customer` (resolve mode + accrual + persist new fields):
```python
    @staticmethod
    def snapshot_customer(tenant_id, customer_id, period_start, period_end) -> CustomerEconomics:
        from apps.platform.tenants.models import Tenant
        from apps.platform.customers.models import Customer
        acc = CustomerCostAccumulator.objects.filter(
            tenant_id=tenant_id, customer_id=customer_id, period_start=period_start).first()
        provider_cost = acc.total_provider_cost_micros if acc else 0
        usage_billed = acc.total_billed_cost_micros if acc else 0
        tenant = Tenant.objects.get(id=tenant_id)
        customer = Customer.objects.get(id=customer_id)
        mode = RevenueService.resolve_revenue_mode(tenant, customer)
        subscription_revenue = RevenueService.accrued_subscription_revenue(
            tenant_id, customer_id, period_start, period_end)
        total_revenue, usage_revenue, margin, pct = _compose(
            subscription_revenue, usage_billed, provider_cost, mode)
        econ, _ = CustomerEconomics.objects.update_or_create(
            tenant_id=tenant_id, customer_id=customer_id, period_start=period_start,
            defaults={
                "period_end": period_end,
                "subscription_revenue_micros": subscription_revenue,
                "usage_billed_micros": usage_billed,
                "provider_cost_micros": provider_cost,
                "total_revenue_micros": total_revenue,
                "revenue_mode": mode,
                "gross_margin_micros": margin,
                "margin_percentage": pct,
            })
        return econ
```

- [ ] **Step 4 — Update existing tests:** run `$DJ -m pytest apps/subscriptions/tests/test_economics.py -q`. Any test asserting the OLD margin (e.g. a meter-only customer's margin including the passthrough, or a postpaid margin from paid invoices) must be updated to the new earned-basis values. Update them to match the corrected formula (do NOT weaken the new tests).

- [ ] **Step 5 — Verify:** `$DJ manage.py check`; `$DJ -m pytest apps/subscriptions -q` → green. **Commit:** `feat(economics): mode-aware accrual margin (fix metering COGS + postpaid double-count)`.

---

### Task 4: Margin endpoints — fix inline formulas + `revenue-mode` CRUD

**Files:** Modify `apps/subscriptions/api/margin_endpoints.py`, `apps/subscriptions/api/margin_schemas.py`; Test `apps/subscriptions/tests/test_revenue_mode_endpoint.py` (+ update `test_margin_endpoints.py` if it asserts old summary/list numbers).

- [ ] **Step 1 — Failing tests** `apps/subscriptions/tests/test_revenue_mode_endpoint.py`: with a `products=["metering","billing"]` tenant + Bearer key (mirror `test_margin_endpoints.py` setup): `PUT .../customers/{id}/revenue-mode {"revenue_mode":"metered_only"}` → 200, `resolved=="metered_only"`; `GET` returns it; an invalid value (`"bogus"`) → 422. (Find the margin API URL prefix from `test_margin_endpoints.py`.)
- [ ] **Step 2 — Run** → FAIL (404).
- [ ] **Step 3a — Schemas** `apps/subscriptions/api/margin_schemas.py` (append):
```python
from ninja import Schema

class RevenueModeIn(Schema):
    revenue_mode: str = ""

class RevenueModeOut(Schema):
    revenue_mode: str
    resolved: str
```
(If `Schema` is already imported there, reuse it.)
- [ ] **Step 3b — Fix the two inline formulas.** In `margin_endpoints.py` `margin_summary` and `list_margin`, replace `RevenueService.revenue_for_window(...)` + `sub + billed` with the accrual + mode composition. For `margin_summary` the loop body becomes:
```python
    from apps.platform.customers.models import Customer
    cust = {c.id: c for c in Customer.objects.filter(
        id__in=[r["customer_id"] for r in rows], tenant=tenant)}
    total_provider = total_billed = total_sub = total_usage_rev = 0
    for r in rows:
        total_provider += r["provider_cost_micros"]
        total_billed += r["billed_cost_micros"]
        total_sub += RevenueService.accrued_subscription_revenue(tenant.id, r["customer_id"], s, e)
        if RevenueService.resolve_revenue_mode(tenant, cust[r["customer_id"]]) == "billed":
            total_usage_rev += r["billed_cost_micros"]
    total_revenue = total_sub + total_usage_rev
    margin = total_revenue - total_provider
```
(add `tenant = request.auth.tenant` near the top; keep the response dict but add `"usage_revenue_micros": total_usage_rev` and set `total_revenue_micros`/`gross_margin_micros` from the above). Apply the same accrual + per-customer-mode fix to `list_margin` (its per-row `sub`/`revenue`/`margin`). `customer_margin` and `margin_trend` already read from `compute_live`/stored fields — no change.
- [ ] **Step 3c — Endpoints** `margin_endpoints.py` (add `RevenueModeIn, RevenueModeOut` to the `from apps.subscriptions.api.margin_schemas import (...)`; append):
```python
_VALID_MODES = {"", "billed", "metered_only"}


@margin_api.get("/customers/{customer_id}/revenue-mode", response=RevenueModeOut)
def get_revenue_mode(request, customer_id: UUID):
    _product_check(request)
    from apps.subscriptions.economics.revenue import RevenueService
    customer = get_object_or_404(Customer, id=customer_id, tenant=request.auth.tenant)
    return {"revenue_mode": customer.revenue_mode,
            "resolved": RevenueService.resolve_revenue_mode(request.auth.tenant, customer)}


@margin_api.put("/customers/{customer_id}/revenue-mode", response=RevenueModeOut)
def put_revenue_mode(request, customer_id: UUID, payload: RevenueModeIn):
    _product_check(request)
    from apps.subscriptions.economics.revenue import RevenueService
    if payload.revenue_mode not in _VALID_MODES:
        return margin_api.create_response(
            request, {"error": "invalid_revenue_mode", "detail": payload.revenue_mode}, status=422)
    customer = get_object_or_404(Customer, id=customer_id, tenant=request.auth.tenant)
    customer.revenue_mode = payload.revenue_mode
    customer.save(update_fields=["revenue_mode", "updated_at"])
    return {"revenue_mode": customer.revenue_mode,
            "resolved": RevenueService.resolve_revenue_mode(request.auth.tenant, customer)}
```
- [ ] **Step 4 — Verify:** `$DJ manage.py check`; `$DJ -m pytest apps/subscriptions -q` → green (update any `test_margin_endpoints.py` summary/list assertions to the accrual numbers). **Commit:** `feat(margin): accrual-correct summary/list + revenue-mode CRUD`.

---

### Task 5: SDK `set_revenue_mode` / `get_revenue_mode`

**Files:** Modify `ubb-sdk/ubb/metering.py`; Test `ubb-sdk/tests/test_revenue_mode_client.py`.

- [ ] **Step 1 — Methods** `ubb-sdk/ubb/metering.py` (mirror the existing `set_customer_revenue`/`get_customer_revenue` margin methods — match their request-helper + the margin URL prefix they use; read those first):
```python
    def set_revenue_mode(self, customer_id, revenue_mode=""):
        r = self._request_margin("put", f"/customers/{customer_id}/revenue-mode",
                                 json={"revenue_mode": revenue_mode})
        return r.json()

    def get_revenue_mode(self, customer_id):
        r = self._request_margin("get", f"/customers/{customer_id}/revenue-mode")
        return r.json()
```
> Use whatever helper + path prefix `set_customer_revenue` uses (it may be `self._request` with a full `/api/v1/margin/...` path rather than `_request_margin`). Match it exactly — do not invent a new helper.
- [ ] **Step 2 — Tests** `ubb-sdk/tests/test_revenue_mode_client.py`: mock the httpx client method; assert the path + that `set_revenue_mode("c1","metered_only")` posts `{"revenue_mode":"metered_only"}` and returns the parsed dict. Mirror `tests/test_rate_card_client.py`.
- [ ] **Step 3 — Verify:** from `ubb-sdk/` (no `DJANGO_SETTINGS_MODULE`): `<venv python> -m pytest -q` → green. **Commit (repo root):** `feat(sdk): revenue-mode methods`.

---

### Task 6: Final verification

- [ ] `$DJ manage.py check`; `$DJ manage.py makemigrations --check --dry-run` → "No changes detected".
- [ ] **Fresh-DB (REQUIRED):** drop/recreate `ubb`; `$DJ manage.py migrate` applies `customers/0010` + `subscriptions/0004` cleanly; `$DJ -m pytest -q` whole platform suite green; `cd ../ubb-sdk && <venv python> -m pytest -q` green.
- [ ] **E2E margin spot-check (the two bug fixes + timing-independence):**
  - meter-only customer (manual 100, billed==provider 30) → `compute_live` margin **70** (not 100).
  - postpaid customer with a nominal-20M Stripe sub + a 25M blended paid invoice + 5M billed / 3M provider → margin **22M** (uses nominal sub, not the inflated invoice).
  - the SAME billed customer yields the SAME margin whether `billing_mode` is prepaid or postpaid (timing-independence — both resolve to `billed` and use the identical accrual formula).

---

## Self-Review

**Spec coverage:** earned/accrual basis (T2/T3) ✓; subscription nominal `amount_micros × quantity` pro-rated (T2) ✓; usage `Σbilled` if billed else 0 (T3 `_compose`) ✓; per-customer `revenue_mode` default-from-`billing_mode` + override (T1 field, T2 resolver) ✓; metering-COGS fix + postpaid double-count fix (T3 tests) ✓; timing-independence (T6) ✓; CustomerEconomics audit fields (T1 + T3 persist) ✓; cash `revenue_for_window` retained-but-unused (left in place; only margin call-sites moved off it) ✓; all margin call-sites updated — service + the two inline endpoint formulas (T3/T4) ✓; API + SDK (T4/T5) ✓.

**Placeholder scan:** T3 Step 4 / T4 Step 4 instruct updating pre-existing tests to the corrected numbers (a real, necessary step given the intended behavior change), not a vague "handle tests". The T2 Step-3 note explicitly warns NOT to write the `class RevenueService(RevenueService)` line and to add methods inside the existing class. SDK helper/path is "match the existing `set_customer_revenue`" with a concrete fallback.

**Type/name consistency:** `_compose(subscription_revenue, usage_billed, provider_cost, revenue_mode) -> (total_revenue, usage_revenue, margin, pct)` defined T3, used by both methods T3. `RevenueService.resolve_revenue_mode` / `accrued_subscription_revenue` / `subscription_nominal_for_window` defined T2, used T3/T4. `revenue_mode` values `""|billed|metered_only` consistent T1/T2/T4. `CustomerEconomics.{total_revenue_micros,revenue_mode}` defined T1, written T3. Endpoint `revenue-mode` path consistent T4/T5.

**Migration risk:** two additive columns (`customers/0010`, `subscriptions/0004`), DB-validated T1 + fresh-DB T6.
