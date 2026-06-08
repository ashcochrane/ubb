# Stage 3 — Prepaid Spend Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a per-(customer, calendar-month) **budget overlay** — a soft spend cap with 50/80/100/110% alerts — backed by a reconstructable Redis counter, wired into the existing `billing` gate (pre-call) and drawdown (post-call). Postgres stays the sole money authority; the cap ships **advisory** and flips to **enforcing** per-customer via config.

**Architecture:** A new `BudgetConfig` (per-customer + tenant default) and a `BudgetService` that keeps a Redis counter `budget:{customer}:{YYYY-MM}` = Σ billed_cost this month. The counter is incremented on the existing drawdown handler and read by the existing `RiskService.check`; it is **fail-open** and always recomputable from the durable `UsageEvent` ledger (hourly reconciliation). Threshold alerts ride the existing outbox→webhook path with outbox-existence dedup.

**Tech Stack:** Django 6, django-ninja, pytest-django, Postgres, **Redis** (Django `RedisCache`), Celery. SDK: httpx.

**Design ref:** `docs/plans/2026-06-05-stage3-prepaid-spend-gate-design.md`

---

## ⚠️ Test-fidelity caveat

`BudgetService` uses real Redis semantics (`cache.incr` raises `ValueError` on a missing key; TTL; atomic INCRBY). Tests for Tasks 3–8 MUST run against the **real Dockerized Redis** (already configured as the default cache via `REDIS_URL`), not a dummy/locmem cache. Do not add `@override_settings(CACHES=locmem)`. Task 1 carries the only schema migration — DB-validate it (`migrate` + `pytest`) on Postgres.

## Conventions

- Run from `ubb-platform/`, venv active. Venv python: `/c/Users/tom_l/git/ubb/ubb-platform/.venv/Scripts/python.exe`.
- `$DJ` = `DJANGO_SETTINGS_MODULE=config.settings <python>`.
- Static: `$DJ manage.py check` · `$DJ manage.py makemigrations --check --dry-run` · `$DJ -m pytest --collect-only -q`.
- DB+Redis: `$DJ manage.py migrate` · `$DJ -m pytest <paths> -q`. Baseline at start: **613 platform + 127 SDK tests green** (Stages 0–2). To clear a stray counter in a test: `from django.core.cache import cache; cache.clear()` in `setUp`.
- Branch `tl-changes-05-06-26`. Commit per task; end commit messages with `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`. Gating migration head at start: `gating/0001_initial`.

---

### Task 1: `BudgetConfig` model + `RiskConfig.gate_fail_closed` + migration

**Files:** Modify `apps/billing/gating/models.py`; Create `apps/billing/gating/migrations/0002_budget_config.py`; Test `apps/billing/gating/tests/test_models.py` (create if absent).

- [ ] **Step 1 — Failing test** `apps/billing/gating/tests/test_models.py`:
```python
import pytest
from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer


@pytest.mark.django_db
class TestBudgetConfig:
    def test_defaults(self):
        from apps.billing.gating.models import BudgetConfig
        t = Tenant.objects.create(name="T")
        cfg = BudgetConfig.objects.create(tenant=t, cap_micros=1_000_000_000)
        assert cfg.customer is None  # tenant default
        assert cfg.enforce_mode == "advisory"
        assert cfg.hard_stop_pct == 100
        assert cfg.alert_levels == [50, 80, 100, 110]
        assert cfg.fail_closed is False

    def test_tenant_default_and_customer_override_coexist(self):
        from apps.billing.gating.models import BudgetConfig
        t = Tenant.objects.create(name="T")
        c = Customer.objects.create(tenant=t, external_id="c1")
        BudgetConfig.objects.create(tenant=t, customer=None, cap_micros=1_000)
        BudgetConfig.objects.create(tenant=t, customer=c, cap_micros=2_000)
        assert BudgetConfig.objects.filter(tenant=t).count() == 2

    def test_risk_config_fail_closed_default(self):
        from apps.billing.gating.models import RiskConfig
        t = Tenant.objects.create(name="T")
        rc = RiskConfig.objects.create(tenant=t)
        assert rc.gate_fail_closed is False
```

- [ ] **Step 2 — Run** → FAIL (no `BudgetConfig` / no `gate_fail_closed`). (No DB: `--collect-only` after Step 3.)

- [ ] **Step 3 — Models** in `apps/billing/gating/models.py` (append `BudgetConfig` + the module-level default fn; add the field to `RiskConfig`):
```python
def default_alert_levels():
    return [50, 80, 100, 110]


BUDGET_ENFORCE_MODES = [("advisory", "Advisory"), ("enforcing", "Enforcing")]


class BudgetConfig(BaseModel):
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE, related_name="budget_configs")
    customer = models.ForeignKey("customers.Customer", on_delete=models.CASCADE,
                                 related_name="budget_configs", null=True, blank=True)
    cap_micros = models.BigIntegerField(default=0)  # <= 0 means "no cap" (overlay inert)
    period = models.CharField(max_length=10, default="month")
    enforce_mode = models.CharField(max_length=10, choices=BUDGET_ENFORCE_MODES, default="advisory")
    hard_stop_pct = models.IntegerField(default=100)
    alert_levels = models.JSONField(default=default_alert_levels)
    fail_closed = models.BooleanField(default=False)

    class Meta:
        db_table = "ubb_budget_config"
        constraints = [
            models.UniqueConstraint(fields=["tenant"], condition=models.Q(customer__isnull=True),
                                    name="uq_budget_config_tenant_default"),
            models.UniqueConstraint(fields=["tenant", "customer"], condition=models.Q(customer__isnull=False),
                                    name="uq_budget_config_tenant_customer"),
        ]

    def __str__(self):
        return f"BudgetConfig({self.tenant_id}/{self.customer_id}: cap={self.cap_micros} {self.enforce_mode})"
```
Add to `RiskConfig` (after `max_concurrent_requests`):
```python
    gate_fail_closed = models.BooleanField(default=False)
```

- [ ] **Step 4 — Migration** `apps/billing/gating/migrations/0002_budget_config.py`:
```python
import uuid

import django.db.models.deletion
from django.db import migrations, models

import apps.billing.gating.models


class Migration(migrations.Migration):
    dependencies = [
        ("gating", "0001_initial"),
        ("customers", "0009_rename_arrears_to_min_balance"),
        ("tenants", "0009_tenant_default_currency"),
    ]
    operations = [
        migrations.AddField(model_name="riskconfig", name="gate_fail_closed",
                            field=models.BooleanField(default=False)),
        migrations.CreateModel(
            name="BudgetConfig",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("cap_micros", models.BigIntegerField(default=0)),
                ("period", models.CharField(default="month", max_length=10)),
                ("enforce_mode", models.CharField(
                    choices=[("advisory", "Advisory"), ("enforcing", "Enforcing")],
                    default="advisory", max_length=10)),
                ("hard_stop_pct", models.IntegerField(default=100)),
                ("alert_levels", models.JSONField(default=apps.billing.gating.models.default_alert_levels)),
                ("fail_closed", models.BooleanField(default=False)),
                ("customer", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE,
                    related_name="budget_configs", to="customers.customer")),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                    related_name="budget_configs", to="tenants.tenant")),
            ],
            options={"db_table": "ubb_budget_config"},
        ),
        migrations.AddConstraint(model_name="budgetconfig",
            constraint=models.UniqueConstraint(fields=("tenant",), condition=models.Q(customer__isnull=True),
                name="uq_budget_config_tenant_default")),
        migrations.AddConstraint(model_name="budgetconfig",
            constraint=models.UniqueConstraint(fields=("tenant", "customer"), condition=models.Q(customer__isnull=False),
                name="uq_budget_config_tenant_customer")),
    ]
```
> Verify the `tenants`/`customers` dep names against `git ls-files apps/platform/{tenants,customers}/migrations | tail -1` and use the actual heads.

- [ ] **Step 5 — Verify**: `$DJ manage.py check`; `$DJ manage.py makemigrations --check --dry-run` → "No changes detected"; `$DJ manage.py migrate`; `$DJ -m pytest apps/billing/gating/tests/test_models.py -q` → green. **Commit**: `feat(gating): BudgetConfig + RiskConfig.gate_fail_closed`.

---

### Task 2: `budget.threshold_reached` event contract + delivery registration (additive)

**Files:** Modify `apps/platform/events/schemas.py`, `apps/platform/events/apps.py`; Test `apps/platform/events/tests/test_schemas.py`.

- [ ] **Step 1 — Failing test** (append to `test_schemas.py`):
```python
def test_budget_threshold_event_contract():
    from dataclasses import asdict
    from apps.platform.events.schemas import BudgetThresholdReached
    e = BudgetThresholdReached(tenant_id="t", customer_id="c", period="2026-06",
                               level=80, spend_micros=800, cap_micros=1000, enforce_mode="advisory")
    assert e.EVENT_TYPE == "budget.threshold_reached"
    assert asdict(e)["level"] == 80
```

- [ ] **Step 2 — Run** → FAIL (ImportError).

- [ ] **Step 3 — Schema** (append to `apps/platform/events/schemas.py`):
```python
@dataclass(frozen=True)
class BudgetThresholdReached:
    EVENT_TYPE = "budget.threshold_reached"
    tenant_id: str
    customer_id: str
    period: str
    level: int = 0
    spend_micros: int = 0
    cap_micros: int = 0
    enforce_mode: str = "advisory"
```

- [ ] **Step 4 — Register delivery**: add `"budget.threshold_reached"` to the `event_types` list in `apps/platform/events/apps.py` `ready()`.

- [ ] **Step 5 — Verify**: `$DJ manage.py check`; `$DJ -m pytest apps/platform/events/tests/test_schemas.py -q` → green. **Commit**: `feat(events): budget.threshold_reached contract + delivery registration`.

---

### Task 3: `BudgetService` — counter, reconstruct, check (real Redis)

**Files:** Create `apps/billing/gating/services/budget_service.py`; Test `apps/billing/gating/tests/test_budget_service.py`.

- [ ] **Step 1 — Failing tests** `apps/billing/gating/tests/test_budget_service.py`:
```python
import pytest
from django.core.cache import cache
from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.billing.gating.models import BudgetConfig
from apps.billing.gating.services.budget_service import BudgetService


@pytest.mark.django_db
class TestBudgetService:
    def setup_method(self):
        cache.clear()

    def _cust(self, **cfg):
        t = Tenant.objects.create(name="T")
        c = Customer.objects.create(tenant=t, external_id="c1")
        if cfg:
            BudgetConfig.objects.create(tenant=t, customer=c, **cfg)
        return c

    def test_record_and_current_spend(self):
        c = self._cust(cap_micros=1_000_000)
        old, new, label = BudgetService.record_spend(c.tenant_id, c.id, 300_000)
        assert (old, new) == (0, 300_000)
        old, new, label = BudgetService.record_spend(c.tenant_id, c.id, 200_000)
        assert (old, new) == (300_000, 500_000)
        assert BudgetService.current_spend(c.tenant_id, c.id) == 500_000

    def test_current_spend_rebuilds_from_postgres_on_miss(self):
        from unittest.mock import patch
        c = self._cust(cap_micros=1_000_000)
        with patch("apps.billing.gating.services.budget_service.get_customer_cost_totals",
                   return_value={"provider_cost_micros": 0, "billed_cost_micros": 750_000, "event_count": 1}):
            cache.clear()
            assert BudgetService.current_spend(c.tenant_id, c.id) == 750_000

    def test_check_no_config_allows(self):
        c = self._cust()  # no BudgetConfig
        assert BudgetService.check(c)["allowed"] is True

    def test_check_zero_cap_inert(self):
        c = self._cust(cap_micros=0, enforce_mode="enforcing")
        BudgetService.record_spend(c.tenant_id, c.id, 999_999_999)
        assert BudgetService.check(c)["allowed"] is True

    def test_advisory_never_denies(self):
        c = self._cust(cap_micros=1_000, enforce_mode="advisory")
        BudgetService.record_spend(c.tenant_id, c.id, 5_000)  # way over
        assert BudgetService.check(c)["allowed"] is True

    def test_enforcing_denies_at_cap(self):
        c = self._cust(cap_micros=1_000, enforce_mode="enforcing", hard_stop_pct=100)
        BudgetService.record_spend(c.tenant_id, c.id, 999)
        assert BudgetService.check(c)["allowed"] is True
        BudgetService.record_spend(c.tenant_id, c.id, 1)  # now at 1000 == cap
        res = BudgetService.check(c)
        assert res["allowed"] is False and res["reason"] == "budget_exceeded"
```

- [ ] **Step 2 — Run** → FAIL (no module).

- [ ] **Step 3 — Implement** `apps/billing/gating/services/budget_service.py`:
```python
import logging

from django.core.cache import cache
from django.utils import timezone

from apps.metering.queries import get_customer_cost_totals

logger = logging.getLogger("ubb.billing")

_TTL_SECONDS = 62 * 24 * 3600  # current month + buffer for late reconciliation


def _period():
    """(label 'YYYY-MM', period_start date, period_end date exclusive) for the current calendar month."""
    today = timezone.now().date()
    start = today.replace(day=1)
    if today.month == 12:
        end = start.replace(year=start.year + 1, month=1, day=1)
    else:
        end = start.replace(month=start.month + 1, day=1)
    return f"{start.year:04d}-{start.month:02d}", start, end


def _key(customer_id, label):
    return f"budget:{customer_id}:{label}"


class BudgetService:
    @staticmethod
    def resolve_config(customer):
        from apps.billing.gating.models import BudgetConfig
        cfg = BudgetConfig.objects.filter(tenant_id=customer.tenant_id, customer_id=customer.id).first()
        if cfg:
            return cfg
        return BudgetConfig.objects.filter(tenant_id=customer.tenant_id, customer__isnull=True).first()

    @staticmethod
    def current_spend(tenant_id, customer_id):
        label, start, end = _period()
        key = _key(customer_id, label)
        val = cache.get(key)
        if val is not None:
            return int(val)
        total = get_customer_cost_totals(tenant_id, customer_id, start, end)["billed_cost_micros"]
        cache.set(key, total, timeout=_TTL_SECONDS)
        return total

    @staticmethod
    def record_spend(tenant_id, customer_id, amount_micros):
        """INCRBY the period counter. Returns (old, new, label). Rebuilds from Postgres on a missing key."""
        label, start, end = _period()
        key = _key(customer_id, label)
        try:
            new = cache.incr(key, amount_micros)
            return new - amount_micros, new, label
        except ValueError:
            # Missing key — rebuild from the durable ledger (already includes this event).
            new = get_customer_cost_totals(tenant_id, customer_id, start, end)["billed_cost_micros"]
            cache.set(key, new, timeout=_TTL_SECONDS)
            return max(0, new - amount_micros), new, label

    @staticmethod
    def check(customer):
        cfg = BudgetService.resolve_config(customer)
        if cfg is None or cfg.cap_micros <= 0:
            return {"allowed": True, "reason": None, "spend_micros": None, "cap_micros": None}
        try:
            spend = BudgetService.current_spend(customer.tenant_id, customer.id)
        except Exception:
            from apps.billing.gating.models import RiskConfig
            fail_closed = cfg.fail_closed
            if not fail_closed:
                rc = RiskConfig.objects.filter(tenant_id=customer.tenant_id).first()
                fail_closed = bool(rc and rc.gate_fail_closed)
            if fail_closed:
                return {"allowed": False, "reason": "budget_unavailable",
                        "spend_micros": None, "cap_micros": cfg.cap_micros}
            return {"allowed": True, "reason": None, "spend_micros": None, "cap_micros": cfg.cap_micros}
        limit = cfg.cap_micros * cfg.hard_stop_pct // 100
        if cfg.enforce_mode == "enforcing" and spend >= limit:
            return {"allowed": False, "reason": "budget_exceeded",
                    "spend_micros": spend, "cap_micros": cfg.cap_micros}
        return {"allowed": True, "reason": None, "spend_micros": spend, "cap_micros": cfg.cap_micros}
```

- [ ] **Step 4 — Verify**: `$DJ manage.py check`; `$DJ -m pytest apps/billing/gating/tests/test_budget_service.py -q` → green (runs against real Redis). **Commit**: `feat(gating): BudgetService Redis spend counter + cap check`.

---

### Task 4: Threshold-crossing alerts (transition-safe) + `record_usage_spend`

**Files:** Modify `apps/billing/gating/services/budget_service.py`; Test `apps/billing/gating/tests/test_budget_service.py` (append).

- [ ] **Step 1 — Failing tests** (append):
```python
    def test_threshold_alert_emitted_once_on_crossing(self):
        from apps.platform.events.models import OutboxEvent
        c = self._cust(cap_micros=1_000, enforce_mode="advisory")
        BudgetService.record_usage_spend(c, 850)  # crosses 50% (500) and 80% (800)
        assert OutboxEvent.objects.filter(event_type="budget.threshold_reached").count() == 2
        BudgetService.record_usage_spend(c, 10)   # 860 — no new level
        assert OutboxEvent.objects.filter(event_type="budget.threshold_reached").count() == 2

    def test_threshold_alert_dedup_on_repeated_emit(self):
        from apps.platform.events.models import OutboxEvent
        c = self._cust(cap_micros=1_000)
        cfg = BudgetService.resolve_config(c)
        BudgetService.emit_threshold_alerts(c, cfg, 0, 600, "2026-06")  # crosses 50%
        BudgetService.emit_threshold_alerts(c, cfg, 0, 600, "2026-06")  # replay (e.g. reconciliation) — no dup
        assert OutboxEvent.objects.filter(
            event_type="budget.threshold_reached", payload__level=50).count() == 1
```

- [ ] **Step 2 — Run** → FAIL (no `record_usage_spend` / `emit_threshold_alerts`).

- [ ] **Step 3 — Implement** (append to `BudgetService`):
```python
    @staticmethod
    def emit_threshold_alerts(customer, cfg, old, new, label):
        if cfg is None or cfg.cap_micros <= 0:
            return
        from django.db import transaction
        from apps.platform.events.models import OutboxEvent
        from apps.platform.events.outbox import write_event
        from apps.platform.events.schemas import BudgetThresholdReached
        for level in cfg.alert_levels:
            threshold = cfg.cap_micros * level // 100
            if old < threshold <= new:
                already = OutboxEvent.objects.filter(
                    event_type="budget.threshold_reached", tenant_id=customer.tenant_id,
                    payload__customer_id=str(customer.id), payload__period=label,
                    payload__level=level).exists()
                if already:
                    continue
                with transaction.atomic():
                    write_event(BudgetThresholdReached(
                        tenant_id=str(customer.tenant_id), customer_id=str(customer.id),
                        period=label, level=level, spend_micros=new, cap_micros=cfg.cap_micros,
                        enforce_mode=cfg.enforce_mode))

    @staticmethod
    def record_usage_spend(customer, amount_micros):
        """Post-drawdown hook: increment the counter + emit threshold alerts. Fail-open."""
        if amount_micros <= 0:
            return
        cfg = BudgetService.resolve_config(customer)
        if cfg is None or cfg.cap_micros <= 0:
            return
        try:
            old, new, label = BudgetService.record_spend(customer.tenant_id, customer.id, amount_micros)
        except Exception:
            logger.warning("budget.record_spend_failed", extra={"data": {"customer_id": str(customer.id)}})
            return  # fail-open: reconciliation repairs the counter
        BudgetService.emit_threshold_alerts(customer, cfg, old, new, label)
```

- [ ] **Step 4 — Verify**: `$DJ -m pytest apps/billing/gating/tests/test_budget_service.py -q` → green. **Commit**: `feat(gating): transition-safe budget threshold alerts`.

---

### Task 5: Wire `record_usage_spend` into the drawdown handler

**Files:** Modify `apps/billing/handlers.py`; Test `apps/billing/tests/test_outbox_handlers.py` (append).

- [ ] **Step 1 — Failing test** (append a test that records usage through the billing handler and asserts the counter moved). Use the file's existing `handle_usage_recorded_billing` invocation style (event payload dict with `tenant_id`/`customer_id`/`cost_micros`); after a wallet+budget setup with a `BudgetConfig(cap_micros>0)`, assert `BudgetService.current_spend(...)` equals the billed amount and (for a crossing) a `budget.threshold_reached` OutboxEvent exists.

- [ ] **Step 2 — Run** → FAIL (counter unchanged).

- [ ] **Step 3 — Wire**: in `handle_usage_recorded_billing`, immediately AFTER the `with transaction.atomic():` wallet block (i.e. after the deduction/suspend/BalanceLow logic commits, alongside the existing `TenantBillingService.accumulate_usage(...)` call), add:
```python
        from apps.billing.gating.services.budget_service import BudgetService
        BudgetService.record_usage_spend(customer, billed_cost_micros)
```
`customer` and `billed_cost_micros` are already in scope. Keep this OUTSIDE the wallet lock (it touches Redis + the outbox, not the wallet).

- [ ] **Step 4 — Verify**: `$DJ -m pytest apps/billing/tests/test_outbox_handlers.py -q` → green. **Commit**: `feat(billing): increment budget counter on usage drawdown`.

---

### Task 6: Wire `BudgetService.check` into the gate

**Files:** Modify `apps/billing/gating/services/risk_service.py`; Test `apps/billing/gating/tests/test_risk_service.py` (create/append).

- [ ] **Step 1 — Failing tests**: a customer with an `enforcing` `BudgetConfig(cap_micros=1000)` and a Redis spend ≥ 1000 → `RiskService.check(customer)["allowed"] is False` and `reason == "budget_exceeded"`; an `advisory` config over cap → still allowed; no config → allowed (existing affordability behavior). (Give the customer enough wallet balance so the credit-balance check passes, isolating the budget gate. Build via `Wallet.objects.create(customer=..., balance_micros=10_000_000)` and `BudgetService.record_spend(...)`.)

- [ ] **Step 2 — Run** → FAIL.

- [ ] **Step 3 — Wire**: in `RiskService.check`, after the affordability check passes (right after the `if balance < -threshold: return insufficient_funds` block, BEFORE building the `result`/optional run), add:
```python
        from apps.billing.gating.services.budget_service import BudgetService
        budget = BudgetService.check(customer)
        if not budget["allowed"]:
            return {"allowed": False, "reason": budget["reason"],
                    "balance_micros": balance, "run_id": None}
```

- [ ] **Step 4 — Verify**: `$DJ manage.py check`; `$DJ -m pytest apps/billing/gating -q` → green. **Commit**: `feat(gating): enforce budget cap in the pre-call gate`.

---

### Task 7: Budget config + status API

**Files:** Modify `api/v1/billing_endpoints.py`, `api/v1/schemas.py`; Test `api/v1/tests/test_billing_endpoints.py` (append) or a new `test_budget_endpoints.py`.

- [ ] **Step 1 — Failing tests**: a `billing`-product tenant can `PUT /api/v1/billing/customers/{id}/budget` then `GET` it back; `PUT /api/v1/billing/budget` upserts the tenant default; `GET /api/v1/billing/customers/{id}/budget/status` returns `{spend_micros, cap_micros, pct, enforce_mode, period}`. (Mirror the existing billing endpoint test style — `Client`, `Bearer` key, `products=["metering","billing"]`.)

- [ ] **Step 2 — Run** → FAIL (404).

- [ ] **Step 3 — Schemas** `api/v1/schemas.py` (append):
```python
class BudgetConfigIn(Schema):
    cap_micros: int = Field(ge=0)
    enforce_mode: str = "advisory"
    hard_stop_pct: int = Field(default=100, ge=1, le=1000)
    alert_levels: Optional[list[int]] = None
    fail_closed: bool = False

class BudgetConfigOut(Schema):
    cap_micros: int
    enforce_mode: str
    hard_stop_pct: int
    alert_levels: list[int]
    fail_closed: bool

class BudgetStatusOut(Schema):
    period: str
    spend_micros: int
    cap_micros: int
    pct: float
    enforce_mode: str
```

- [ ] **Step 4 — Endpoints** `api/v1/billing_endpoints.py` (add; import `BudgetConfigIn, BudgetConfigOut, BudgetStatusOut`, `BudgetConfig`, `BudgetService`, `default_alert_levels`):
```python
def _budget_out(cfg):
    return {"cap_micros": cfg.cap_micros, "enforce_mode": cfg.enforce_mode,
            "hard_stop_pct": cfg.hard_stop_pct, "alert_levels": cfg.alert_levels,
            "fail_closed": cfg.fail_closed}


def _upsert_budget(tenant, customer, payload):
    from apps.billing.gating.models import BudgetConfig, default_alert_levels
    cfg, _ = BudgetConfig.objects.update_or_create(
        tenant=tenant, customer=customer,
        defaults={"cap_micros": payload.cap_micros, "enforce_mode": payload.enforce_mode,
                  "hard_stop_pct": payload.hard_stop_pct,
                  "alert_levels": payload.alert_levels or default_alert_levels(),
                  "fail_closed": payload.fail_closed})
    return cfg


@billing_api.get("/budget", response=BudgetConfigOut)
def get_tenant_budget(request):
    _product_check(request)
    from apps.billing.gating.models import BudgetConfig
    cfg = BudgetConfig.objects.filter(tenant=request.auth.tenant, customer__isnull=True).first()
    if not cfg:
        return {"cap_micros": 0, "enforce_mode": "advisory", "hard_stop_pct": 100,
                "alert_levels": [50, 80, 100, 110], "fail_closed": False}
    return _budget_out(cfg)


@billing_api.put("/budget", response=BudgetConfigOut)
def put_tenant_budget(request, payload: BudgetConfigIn):
    _product_check(request)
    return _budget_out(_upsert_budget(request.auth.tenant, None, payload))


@billing_api.get("/customers/{customer_id}/budget", response=BudgetConfigOut)
def get_customer_budget(request, customer_id: UUID):
    _product_check(request)
    from apps.billing.gating.models import BudgetConfig
    customer = get_object_or_404(Customer, id=customer_id, tenant=request.auth.tenant)
    cfg = BudgetConfig.objects.filter(tenant=request.auth.tenant, customer=customer).first()
    if not cfg:
        return {"cap_micros": 0, "enforce_mode": "advisory", "hard_stop_pct": 100,
                "alert_levels": [50, 80, 100, 110], "fail_closed": False}
    return _budget_out(cfg)


@billing_api.put("/customers/{customer_id}/budget", response=BudgetConfigOut)
def put_customer_budget(request, customer_id: UUID, payload: BudgetConfigIn):
    _product_check(request)
    customer = get_object_or_404(Customer, id=customer_id, tenant=request.auth.tenant)
    return _budget_out(_upsert_budget(request.auth.tenant, customer, payload))


@billing_api.get("/customers/{customer_id}/budget/status", response=BudgetStatusOut)
def get_customer_budget_status(request, customer_id: UUID):
    _product_check(request)
    from apps.billing.gating.services.budget_service import BudgetService, _period
    from apps.billing.gating.models import BudgetConfig
    customer = get_object_or_404(Customer, id=customer_id, tenant=request.auth.tenant)
    label, _s, _e = _period()
    cfg = BudgetService.resolve_config(customer)
    cap = cfg.cap_micros if cfg else 0
    try:
        spend = BudgetService.current_spend(customer.tenant_id, customer.id)
    except Exception:
        spend = 0
    pct = round(spend / cap * 100, 2) if cap > 0 else 0.0
    return {"period": label, "spend_micros": spend, "cap_micros": cap, "pct": pct,
            "enforce_mode": cfg.enforce_mode if cfg else "advisory"}
```
Confirm `UUID`, `get_object_or_404`, `Customer`, `_product_check` are already imported in `billing_endpoints.py` (they are — used by other endpoints).

- [ ] **Step 5 — Verify**: `$DJ manage.py check`; `$DJ -m pytest api/v1 apps/billing -q` → green. **Commit**: `feat(billing): budget config + status API`.

---

### Task 8: Reconciliation task + beat schedule

**Files:** Create `apps/billing/gating/tasks.py`; Modify `config/settings.py` (CELERY_BEAT_SCHEDULE); add `BudgetService.reconcile_customer`; Test `apps/billing/gating/tests/test_tasks.py`.

- [ ] **Step 1 — Failing test**: set a `BudgetConfig(cap>0)`, record real `UsageEvent`s for the customer this month (via `UsageService.record_usage(provider_cost_micros=..., billed_cost_micros=...)` with `process_single_event` patched), corrupt the Redis counter (`cache.set(key, 0)`), run `reconcile_budget_counters()`, assert `BudgetService.current_spend(...)` equals the summed billed cost.

- [ ] **Step 2 — Run** → FAIL.

- [ ] **Step 3 — `reconcile_customer`** (append to `BudgetService`):
```python
    @staticmethod
    def reconcile_customer(customer):
        cfg = BudgetService.resolve_config(customer)
        if cfg is None or cfg.cap_micros <= 0:
            return
        label, start, end = _period()
        total = get_customer_cost_totals(customer.tenant_id, customer.id, start, end)["billed_cost_micros"]
        try:
            cache.set(_key(customer.id, label), total, timeout=_TTL_SECONDS)
        except Exception:
            return
        BudgetService.emit_threshold_alerts(customer, cfg, 0, total, label)  # fires only not-yet-sent levels
```

- [ ] **Step 4 — Task** `apps/billing/gating/tasks.py`:
```python
import logging

from celery import shared_task

logger = logging.getLogger("ubb.billing")


@shared_task(queue="ubb_billing")
def reconcile_budget_counters():
    """Rebuild per-customer budget counters from the durable ledger (drift correction)."""
    from apps.platform.customers.models import Customer
    from apps.billing.gating.models import BudgetConfig
    from apps.billing.gating.services.budget_service import BudgetService, _period
    from apps.metering.usage.models import UsageEvent

    _label, start, end = _period()
    ids = set(BudgetConfig.objects.filter(customer__isnull=False, cap_micros__gt=0)
              .values_list("customer_id", flat=True))
    default_tenants = list(BudgetConfig.objects.filter(customer__isnull=True, cap_micros__gt=0)
                           .values_list("tenant_id", flat=True))
    if default_tenants:
        ids |= set(UsageEvent.objects.filter(
            tenant_id__in=default_tenants, effective_at__date__gte=start, effective_at__date__lt=end
        ).values_list("customer_id", flat=True).distinct())
    for customer in Customer.objects.filter(id__in=ids):
        try:
            BudgetService.reconcile_customer(customer)
        except Exception:
            logger.exception("budget.reconcile_failed", extra={"data": {"customer_id": str(customer.id)}})
```

- [ ] **Step 5 — Beat schedule** in `config/settings.py` `CELERY_BEAT_SCHEDULE`, add (the file already imports `crontab`):
```python
    "reconcile-budget-counters": {
        "task": "apps.billing.gating.tasks.reconcile_budget_counters",
        "schedule": crontab(minute=15),  # hourly at :15
    },
```

- [ ] **Step 6 — Verify**: `$DJ manage.py check`; `$DJ -m pytest apps/billing/gating/tests/test_tasks.py -q` → green. **Commit**: `feat(billing): hourly budget-counter reconciliation`.

---

### Task 9: SDK budget methods + types

**Files:** Modify `ubb-sdk/ubb/billing.py`, `ubb-sdk/ubb/client.py`, `ubb-sdk/ubb/types.py`; Test `ubb-sdk/tests/test_budget_client.py` (new).

- [ ] **Step 1 — Types** `ubb-sdk/ubb/types.py` (append):
```python
@dataclass(frozen=True)
class BudgetConfig:
    cap_micros: int | None = None
    enforce_mode: str | None = None
    hard_stop_pct: int | None = None
    alert_levels: list | None = None
    fail_closed: bool | None = None

@dataclass(frozen=True)
class BudgetStatus:
    period: str | None = None
    spend_micros: int | None = None
    cap_micros: int | None = None
    pct: float | None = None
    enforce_mode: str | None = None
```

- [ ] **Step 2 — `BillingClient` methods** `ubb-sdk/ubb/billing.py` (add the `BudgetConfig, BudgetStatus` import to the existing `from ubb.types import ...`; mirror the existing `_request` usage in that client):
```python
    def set_budget(self, customer_id, cap_micros, enforce_mode="advisory",
                   hard_stop_pct=100, alert_levels=None, fail_closed=False):
        body = {"cap_micros": cap_micros, "enforce_mode": enforce_mode,
                "hard_stop_pct": hard_stop_pct, "fail_closed": fail_closed}
        if alert_levels is not None:
            body["alert_levels"] = alert_levels
        r = self._request("put", f"/api/v1/billing/customers/{customer_id}/budget", json=body)
        return BudgetConfig(**r.json())

    def get_budget(self, customer_id):
        r = self._request("get", f"/api/v1/billing/customers/{customer_id}/budget")
        return BudgetConfig(**r.json())

    def get_budget_status(self, customer_id):
        r = self._request("get", f"/api/v1/billing/customers/{customer_id}/budget/status")
        return BudgetStatus(**r.json())
```

- [ ] **Step 3 — `UBBClient` delegation** `ubb-sdk/ubb/client.py` (mirror the existing billing delegations like `get_balance` that call `self._require_billing().<method>`):
```python
    def set_budget(self, customer_id, cap_micros, enforce_mode="advisory",
                   hard_stop_pct=100, alert_levels=None, fail_closed=False):
        return self._require_billing().set_budget(
            customer_id, cap_micros, enforce_mode, hard_stop_pct, alert_levels, fail_closed)

    def get_budget(self, customer_id):
        return self._require_billing().get_budget(customer_id)

    def get_budget_status(self, customer_id):
        return self._require_billing().get_budget_status(customer_id)
```
> Confirm the billing client accessor name by reading `client.py` (it uses `_require_billing()` / `self.billing`); match whatever the existing `get_balance` delegation uses.

- [ ] **Step 4 — Tests** `ubb-sdk/tests/test_budget_client.py`: mock `httpx.Client.put`/`get` on the billing client; assert path + that results parse into `BudgetConfig`/`BudgetStatus`. (Mirror `tests/test_margin_client.py` patch style, but patch `ubb.billing.httpx.Client...`.) Run from `ubb-sdk/`: `/c/Users/tom_l/git/ubb/ubb-platform/.venv/Scripts/python.exe -m pytest -q` → green.

- [ ] **Step 5 — Commit**: `feat(sdk): budget config + status methods`.

---

### Task 10: Final verification

- [ ] `$DJ manage.py check` → no issues.
- [ ] `$DJ manage.py makemigrations --check --dry-run` → "No changes detected".
- [ ] `$DJ -m pytest --collect-only -q` → clean.
- [ ] **Fresh-DB (REQUIRED):** drop/recreate `ubb`, `$DJ manage.py migrate` applies `gating/0002` cleanly; `$DJ -m pytest -q` whole suite green; `cd ../ubb-sdk && <venv python> -m pytest -q` green.
- [ ] **E2E spot-check (advisory→enforcing):** create a `billing` tenant + customer with a funded wallet; `PUT .../budget` `{cap_micros: 1000, enforce_mode: "advisory"}`; record usage totalling ≥600 → a `budget.threshold_reached` (level 50) OutboxEvent exists and `/pre-check` still allows; `PUT .../budget` `{enforce_mode: "enforcing"}`; record usage to ≥1000 → `/pre-check` returns `allowed=false, reason="budget_exceeded"`.
- [ ] **Fail-open spot-check:** with Redis made to raise (monkeypatch `cache.get` to raise in a unit test), `BudgetService.check` returns `allowed=True` for a default config and `allowed=False, reason="budget_unavailable"` when `fail_closed=True`.

---

## Self-Review

**Spec coverage (vs. Stage 3 design):** `BudgetConfig` + fail-mode (T1) ✓; `budget.threshold_reached` contract+registration (T2) ✓; Redis counter + reconstruct + check + fail-open (T3) ✓; transition-safe alerts w/ outbox dedup (T4) ✓; drawdown increment (T5) ✓; gate enforcement + `budget_exceeded` (T6) ✓; budget API incl. status (T7) ✓; reconciliation + beat (T8) ✓; SDK (T9) ✓; advisory→enforcing config-only flip (T1 default + T6 honoring `enforce_mode`) ✓; period = calendar month aligned (`_period`, T3) ✓; Redis-only/Postgres-authoritative + reconstructable (T3 rebuild, T8 reconcile) ✓.

**Placeholder scan:** T5/T7/T9 reference "mirror the existing test/import style" with the exact endpoint/payload shapes given — verification instructions against concrete current code, not vague stubs. Migration dep names flagged "verify the actual heads."

**Type/name consistency:** `BudgetService.resolve_config/current_spend/record_spend/check/emit_threshold_alerts/record_usage_spend/reconcile_customer` consistent across T3/T4/T6/T8 and the API (T7). `_period()`/`_key()`/`_TTL_SECONDS` consistent. Event `BudgetThresholdReached` (fields `level/spend_micros/cap_micros/period/enforce_mode`) consistent across T2/T4/T8 and the `events/apps.py` registration string `budget.threshold_reached`. Config fields (`cap_micros/enforce_mode/hard_stop_pct/alert_levels/fail_closed`) identical across model (T1), service (T3/T4), API (T7), SDK (T9). Gate reason strings `budget_exceeded`/`budget_unavailable` consistent across T3/T6 and the E2E check.

**Migration risk:** one migration (`gating/0002`), DB-validated in T1 and re-validated fresh in T10. The `alert_levels` JSONField default is a named module function (`default_alert_levels`) so `makemigrations --check` stays clean.
