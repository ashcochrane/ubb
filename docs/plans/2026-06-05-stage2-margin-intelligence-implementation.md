> ⚠️ SUPERSEDED (revenue wiring only): the cash-basis `RevenueService.revenue_for_window`/`stripe_revenue_for_window` built in Task 3 and wired into `MarginService.compute_live`/`snapshot_customer` + the margin API below were REPLACED by accrual `accrued_subscription_revenue` (manual + subscription nominal pro-rated) in `2026-06-08-pricing-stageB-revenue-source-implementation.md`, and the cash-basis methods were DELETED. Do NOT re-create them. Cost accumulator, snapshots, thresholds, margin webhooks remain current. Master truth: `2026-06-10-program-current-state.md`.

# Stage 2 — Margin Intelligence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Compute per-customer and per-dimension **gross margin = (manual/Stripe subscription revenue + usage billed) − provider cost** in real time, flag unprofitable customers, surface provider-cost spikes, and expose it via a `metering`-gated margin API + webhooks. No money movement, no gate (Stage 3).

**Architecture:** Cost is read from `UsageEvent` (live, any window) and from a per-month `CustomerCostAccumulator` (snapshots). Revenue is a per-customer **manual** `CustomerRevenueProfile` (primary) plus optional synced Stripe invoices. A reframed `MarginService` composes them; a periodic task writes monthly `CustomerEconomics` snapshots and emits margin webhooks via the existing transactional outbox.

**Tech Stack:** Django 6, django-ninja, pytest-django, Postgres, Celery, transactional outbox + `HandlerCheckpoint`. SDK: httpx.

**Design ref:** `docs/plans/2026-06-05-stage2-margin-intelligence-design.md`

---

## ⚠️ Migration-validation caveat

Task 3 carries a real schema migration (`subscriptions/0003`): accumulator field split, `CustomerEconomics` reframe, two new models, `StripeSubscription.quantity`. The static harness validates model/migration *consistency*; it does **NOT** prove the migration applies on Postgres. **Every migration task MUST be validated with `manage.py migrate` + the relevant `pytest` on real Postgres before it is trusted** (Docker Postgres is up per the Stage 1 setup).

## Conventions

- Run from `ubb-platform/`, venv active. Venv python: `/c/Users/tom_l/git/ubb/ubb-platform/.venv/Scripts/python.exe`.
- `$DJ` = `DJANGO_SETTINGS_MODULE=config.settings <python>`.
- Static checks: `$DJ manage.py check` · `$DJ manage.py makemigrations --check --dry-run` · `$DJ -m pytest --collect-only -q`.
- DB checks: `$DJ manage.py migrate` · `$DJ -m pytest <paths> -q`. Baseline at start: **601 platform tests green** (Stage 1 complete).
- Branch `tl-changes-05-06-26`. Commit per task; end commit messages with the `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>` trailer. Migration head at start: `subscriptions/0002_create_cost_accumulator_and_economics`.
- **P&L vocabulary (use exactly):** `subscription_revenue_micros` = manual + Stripe; `usage_billed_micros` = Σ `billed_cost_micros`; `provider_cost_micros` = Σ `provider_cost_micros`; `total_revenue = subscription_revenue + usage_billed`; `gross_margin = total_revenue − provider_cost`; `margin_pct = gross_margin / total_revenue` (`0` when `total_revenue == 0`).

---

### Task 1: Metering cost-totals read queries (additive, no migration)

The margin engine reads usage cost through the metering cross-product contract. Add three functions to `apps/metering/queries.py`.

**Files:** Modify `apps/metering/queries.py`; Test `apps/metering/tests/test_queries.py` (append).

- [ ] **Step 1 — Failing tests** (append to `apps/metering/tests/test_queries.py`):
```python
class GetCostTotalsTest(TestCase):
    def setUp(self):
        from django.utils import timezone
        self.tenant = Tenant.objects.create(name="T")
        self.customer = Customer.objects.create(tenant=self.tenant, external_id="c1")
        self.start = timezone.now().date().replace(day=1)
        self.end = (self.start.replace(month=self.start.month % 12 + 1, day=1)
                    if self.start.month < 12 else self.start.replace(year=self.start.year + 1, month=1, day=1))
        UsageEvent.objects.create(
            tenant=self.tenant, customer=self.customer, request_id="r1", idempotency_key="i1",
            provider_cost_micros=800_000, billed_cost_micros=1_000_000, provider="openai",
            product_id="chat", tags={"model": "gpt-4"})
        UsageEvent.objects.create(
            tenant=self.tenant, customer=self.customer, request_id="r2", idempotency_key="i2",
            provider_cost_micros=200_000, billed_cost_micros=300_000, provider="openai",
            product_id="chat", tags={"model": "gpt-4"})

    def test_customer_cost_totals(self):
        from apps.metering.queries import get_customer_cost_totals
        t = get_customer_cost_totals(self.tenant.id, self.customer.id, self.start, self.end)
        assert t["provider_cost_micros"] == 1_000_000
        assert t["billed_cost_micros"] == 1_300_000
        assert t["event_count"] == 2

    def test_per_customer_cost_totals(self):
        from apps.metering.queries import get_per_customer_cost_totals
        rows = get_per_customer_cost_totals(self.tenant.id, self.start, self.end)
        assert len(rows) == 1
        assert rows[0]["billed_cost_micros"] == 1_300_000

    def test_dimensional_margin_by_provider(self):
        from apps.metering.queries import get_dimensional_margin
        rows = get_dimensional_margin(self.tenant.id, group_by="provider",
                                      start_date=self.start, end_date=self.end)
        assert rows[0]["dimension"] == "openai"
        assert rows[0]["margin_micros"] == 300_000  # 1_300_000 - 1_000_000

    def test_dimensional_margin_by_tag(self):
        from apps.metering.queries import get_dimensional_margin
        rows = get_dimensional_margin(self.tenant.id, tag_key="model",
                                      start_date=self.start, end_date=self.end)
        assert rows[0]["dimension"] == "gpt-4"
        assert rows[0]["margin_micros"] == 300_000
```

- [ ] **Step 2 — Run** `$DJ -m pytest apps/metering/tests/test_queries.py::GetCostTotalsTest -q` → FAIL (functions not defined). (No DB: `--collect-only`.)

- [ ] **Step 3 — Implement** in `apps/metering/queries.py` (append; reuse the existing `Sum`/`Count` imports):
```python
def get_customer_cost_totals(tenant_id, customer_id, start_date, end_date) -> dict:
    """Provider + billed cost totals for one customer over [start, end)."""
    from apps.metering.usage.models import UsageEvent
    agg = UsageEvent.objects.filter(
        tenant_id=tenant_id, customer_id=customer_id,
        effective_at__date__gte=start_date, effective_at__date__lt=end_date,
    ).aggregate(
        provider=Sum("provider_cost_micros"), billed=Sum("billed_cost_micros"),
        count=Count("id"),
    )
    return {
        "provider_cost_micros": agg["provider"] or 0,
        "billed_cost_micros": agg["billed"] or 0,
        "event_count": agg["count"] or 0,
    }


def get_per_customer_cost_totals(tenant_id, start_date, end_date) -> list[dict]:
    """Per-customer provider + billed totals over [start, end)."""
    from apps.metering.usage.models import UsageEvent
    rows = (UsageEvent.objects.filter(
        tenant_id=tenant_id,
        effective_at__date__gte=start_date, effective_at__date__lt=end_date,
    ).values("customer_id").annotate(
        provider_cost_micros=Sum("provider_cost_micros"),
        billed_cost_micros=Sum("billed_cost_micros"),
        event_count=Count("id"),
    ).order_by("-billed_cost_micros"))
    return [dict(r) for r in rows]


def get_dimensional_margin(tenant_id, *, group_by=None, tag_key=None,
                           start_date=None, end_date=None) -> list[dict]:
    """Usage-only margin (billed - provider) grouped by a column or a tag key.

    group_by in {"provider", "event_type", "product_id"}; OR tag_key for tags->>key.
    Each row: {dimension, provider_cost_micros, billed_cost_micros, margin_micros, event_count}.
    """
    from apps.metering.usage.models import UsageEvent
    qs = UsageEvent.objects.filter(tenant_id=tenant_id)
    if start_date:
        qs = qs.filter(effective_at__date__gte=start_date)
    if end_date:
        qs = qs.filter(effective_at__date__lt=end_date)

    def _row(dim, provider, billed, count):
        return {"dimension": dim, "provider_cost_micros": provider or 0,
                "billed_cost_micros": billed or 0,
                "margin_micros": (billed or 0) - (provider or 0), "event_count": count}

    if tag_key:
        from collections import defaultdict
        agg = defaultdict(lambda: {"p": 0, "b": 0, "n": 0})
        for tags, p, b in qs.filter(tags__has_key=tag_key).values_list(
                "tags", "provider_cost_micros", "billed_cost_micros"):
            k = (tags or {}).get(tag_key)
            agg[k]["p"] += p or 0
            agg[k]["b"] += b or 0
            agg[k]["n"] += 1
        rows = [_row(k, v["p"], v["b"], v["n"]) for k, v in agg.items()]
        return sorted(rows, key=lambda r: -r["margin_micros"])

    if group_by not in ("provider", "event_type", "product_id"):
        raise ValueError("group_by must be provider, event_type, or product_id")
    grouped = (qs.exclude(**{group_by: ""}).values(group_by).annotate(
        provider=Sum("provider_cost_micros"), billed=Sum("billed_cost_micros"),
        count=Count("id")).order_by())
    rows = [_row(g[group_by], g["provider"], g["billed"], g["count"]) for g in grouped]
    return sorted(rows, key=lambda r: -r["margin_micros"])
```

- [ ] **Step 4 — Verify**: `$DJ manage.py check`; `$DJ -m pytest apps/metering/tests/test_queries.py -q` → green. **Commit**: `feat(metering): cost-totals + dimensional-margin read queries`.

---

### Task 2: Margin webhook event contracts + delivery registration (additive)

Add the two outbound event schemas and register webhook delivery for them. No migration.

**Files:** Modify `apps/platform/events/schemas.py`, `apps/platform/events/apps.py`; Test `apps/platform/events/tests/test_schemas.py` (append).

- [ ] **Step 1 — Failing test** (append to `apps/platform/events/tests/test_schemas.py`):
```python
def test_margin_event_contracts():
    from dataclasses import asdict
    from apps.platform.events.schemas import MarginCustomerUnprofitable, MarginProviderCostSpike
    e1 = MarginCustomerUnprofitable(
        tenant_id="t", customer_id="c", period_start="2026-06-01",
        gross_margin_micros=-500, margin_pct=-5.0, threshold_pct=0.0)
    assert e1.EVENT_TYPE == "margin.customer_unprofitable"
    assert asdict(e1)["customer_id"] == "c"
    e2 = MarginProviderCostSpike(
        tenant_id="t", customer_id="c", period_start="2026-06-01",
        prev_provider_cost_micros=100, current_provider_cost_micros=200,
        prev_margin_pct=20.0, current_margin_pct=5.0)
    assert e2.EVENT_TYPE == "margin.provider_cost_spike"
```

- [ ] **Step 2 — Run** → FAIL (import error). (No DB: this test needs no DB.)

- [ ] **Step 3 — Add schemas** to `apps/platform/events/schemas.py` (append; all fields have defaults except identifiers, per the additive rule):
```python
@dataclass(frozen=True)
class MarginCustomerUnprofitable:
    EVENT_TYPE = "margin.customer_unprofitable"
    tenant_id: str
    customer_id: str
    period_start: str
    gross_margin_micros: int = 0
    margin_pct: float = 0.0
    threshold_pct: float = 0.0


@dataclass(frozen=True)
class MarginProviderCostSpike:
    EVENT_TYPE = "margin.provider_cost_spike"
    tenant_id: str
    customer_id: str
    period_start: str
    prev_provider_cost_micros: int = 0
    current_provider_cost_micros: int = 0
    prev_margin_pct: float = 0.0
    current_margin_pct: float = 0.0
```

- [ ] **Step 4 — Register webhook delivery** in `apps/platform/events/apps.py`: add `"margin.customer_unprofitable"` and `"margin.provider_cost_spike"` to the `event_types` list (so `handle_webhook_delivery` is registered for them).

- [ ] **Step 5 — Verify**: `$DJ manage.py check`; `$DJ -m pytest apps/platform/events/tests/test_schemas.py -q` → green. **Commit**: `feat(events): margin webhook event contracts + delivery registration`.

---

### Task 3: Data model — accumulator split, economics reframe, new models, seats (migration)

**Files:** Modify `apps/subscriptions/economics/models.py`, `apps/subscriptions/models.py`; Create `apps/subscriptions/migrations/0003_margin_intelligence.py`; Test `apps/subscriptions/tests/test_models.py` (append).

- [ ] **Step 1 — Failing tests** (append to `apps/subscriptions/tests/test_models.py`):
```python
def test_revenue_profile_and_threshold_and_accumulator_fields(self):
    from apps.subscriptions.economics.models import (
        CustomerCostAccumulator, CustomerEconomics, CustomerRevenueProfile, MarginThresholdConfig)
    from apps.platform.tenants.models import Tenant
    from apps.platform.customers.models import Customer
    import datetime
    t = Tenant.objects.create(name="T")
    c = Customer.objects.create(tenant=t, external_id="c1")
    acc = CustomerCostAccumulator.objects.create(
        tenant=t, customer=c, period_start=datetime.date(2026, 6, 1),
        period_end=datetime.date(2026, 7, 1),
        total_provider_cost_micros=800_000, total_billed_cost_micros=1_000_000, event_count=2)
    assert acc.total_provider_cost_micros == 800_000
    rp = CustomerRevenueProfile.objects.create(
        tenant=t, customer=c, recurring_amount_micros=500_000_000,
        effective_from=datetime.date(2026, 6, 1))
    assert rp.interval == "month"
    cfg = MarginThresholdConfig.objects.create(tenant=t)
    assert cfg.min_margin_pct == 0
    assert cfg.provider_cost_spike_pct == 25
    econ = CustomerEconomics.objects.create(
        tenant=t, customer=c, period_start=datetime.date(2026, 6, 1),
        period_end=datetime.date(2026, 7, 1), subscription_revenue_micros=500_000_000,
        usage_billed_micros=1_000_000, provider_cost_micros=800_000,
        gross_margin_micros=500_200_000)
    assert econ.is_unprofitable is False
```

- [ ] **Step 2 — Run** → FAIL (no attribute / no model). (No DB: `--collect-only` after Step 3.)

- [ ] **Step 3 — Reframe** `apps/subscriptions/economics/models.py` (replace the file body):
```python
from django.db import models
from core.models import BaseModel


class CustomerCostAccumulator(BaseModel):
    """Per-customer, per-month provider + billed cost totals (event-driven)."""
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE, related_name="cost_accumulators")
    customer = models.ForeignKey("customers.Customer", on_delete=models.CASCADE, related_name="cost_accumulators")
    period_start = models.DateField()
    period_end = models.DateField()
    total_provider_cost_micros = models.BigIntegerField(default=0)
    total_billed_cost_micros = models.BigIntegerField(default=0)
    event_count = models.IntegerField(default=0)

    class Meta:
        app_label = "subscriptions"
        db_table = "ubb_customer_cost_accumulator"
        constraints = [models.UniqueConstraint(
            fields=["tenant", "customer", "period_start"],
            name="uq_cost_accumulator_tenant_customer_period")]

    def __str__(self):
        return f"CostAccumulator({self.customer_id}: {self.period_start})"


class CustomerEconomics(BaseModel):
    """Per-customer, per-month margin snapshot. revenue = subscription + usage_billed; cost = provider."""
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE, related_name="customer_economics")
    customer = models.ForeignKey("customers.Customer", on_delete=models.CASCADE, related_name="economics")
    period_start = models.DateField()
    period_end = models.DateField()
    subscription_revenue_micros = models.BigIntegerField(default=0)  # manual + stripe
    usage_billed_micros = models.BigIntegerField(default=0)
    provider_cost_micros = models.BigIntegerField(default=0)
    gross_margin_micros = models.BigIntegerField(default=0)
    margin_percentage = models.DecimalField(max_digits=7, decimal_places=2, default=0)
    is_unprofitable = models.BooleanField(default=False)

    class Meta:
        app_label = "subscriptions"
        db_table = "ubb_customer_economics"
        constraints = [models.UniqueConstraint(
            fields=["tenant", "customer", "period_start"],
            name="uq_economics_tenant_customer_period")]

    def __str__(self):
        return f"Economics({self.customer_id}: {self.margin_percentage}%)"


class CustomerRevenueProfile(BaseModel):
    """Manual per-customer recurring revenue the tenant collects externally."""
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE, related_name="revenue_profiles")
    customer = models.ForeignKey("customers.Customer", on_delete=models.CASCADE, related_name="revenue_profiles")
    recurring_amount_micros = models.BigIntegerField(default=0)
    interval = models.CharField(max_length=10, default="month")
    currency = models.CharField(max_length=3, default="usd")
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)

    class Meta:
        app_label = "subscriptions"
        db_table = "ubb_customer_revenue_profile"
        constraints = [models.UniqueConstraint(
            fields=["tenant", "customer"], name="uq_revenue_profile_tenant_customer")]


class MarginThresholdConfig(BaseModel):
    """Per-tenant default (+ optional per-customer override) for unprofitable + spike detection."""
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE, related_name="margin_thresholds")
    customer = models.ForeignKey("customers.Customer", on_delete=models.CASCADE,
                                 related_name="margin_thresholds", null=True, blank=True)
    min_margin_pct = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    consecutive_periods = models.IntegerField(default=1)
    provider_cost_spike_pct = models.DecimalField(max_digits=6, decimal_places=2, default=25)

    class Meta:
        app_label = "subscriptions"
        db_table = "ubb_margin_threshold_config"
        constraints = [
            models.UniqueConstraint(fields=["tenant"], condition=models.Q(customer__isnull=True),
                                    name="uq_margin_threshold_tenant_default"),
            models.UniqueConstraint(fields=["tenant", "customer"], condition=models.Q(customer__isnull=False),
                                    name="uq_margin_threshold_tenant_customer"),
        ]
```
Keep the bottom-of-file re-export line in `apps/subscriptions/models.py` (`from apps.subscriptions.economics.models import CustomerCostAccumulator, CustomerEconomics`) and **extend** it to also import `CustomerRevenueProfile, MarginThresholdConfig` so migrations discover them.

- [ ] **Step 4 — Seats** in `apps/subscriptions/models.py`: add to `StripeSubscription` after `interval`:
```python
    quantity = models.IntegerField(default=1)
```

- [ ] **Step 5 — Migration** `apps/subscriptions/migrations/0003_margin_intelligence.py` (author by hand; pre-production ⇒ direct alters):
```python
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("subscriptions", "0002_create_cost_accumulator_and_economics"),
        ("customers", "0009_rename_arrears_to_min_balance"),
    ]
    operations = [
        # Accumulator split
        migrations.RemoveField(model_name="customercostaccumulator", name="total_cost_micros"),
        migrations.AddField(model_name="customercostaccumulator", name="total_provider_cost_micros",
                            field=models.BigIntegerField(default=0)),
        migrations.AddField(model_name="customercostaccumulator", name="total_billed_cost_micros",
                            field=models.BigIntegerField(default=0)),
        # Economics reframe
        migrations.RemoveField(model_name="customereconomics", name="usage_cost_micros"),
        migrations.AddField(model_name="customereconomics", name="usage_billed_micros",
                            field=models.BigIntegerField(default=0)),
        migrations.AddField(model_name="customereconomics", name="provider_cost_micros",
                            field=models.BigIntegerField(default=0)),
        migrations.AddField(model_name="customereconomics", name="is_unprofitable",
                            field=models.BooleanField(default=False)),
        # Seats
        migrations.AddField(model_name="stripesubscription", name="quantity",
                            field=models.IntegerField(default=1)),
        # New models
        migrations.CreateModel(
            name="CustomerRevenueProfile",
            fields=[
                ("id", models.UUIDField(primary_key=True, serialize=False, editable=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("recurring_amount_micros", models.BigIntegerField(default=0)),
                ("interval", models.CharField(default="month", max_length=10)),
                ("currency", models.CharField(default="usd", max_length=3)),
                ("effective_from", models.DateField()),
                ("effective_to", models.DateField(blank=True, null=True)),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                    related_name="revenue_profiles", to="tenants.tenant")),
                ("customer", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                    related_name="revenue_profiles", to="customers.customer")),
            ],
            options={"db_table": "ubb_customer_revenue_profile"},
        ),
        migrations.AddConstraint(model_name="customerrevenueprofile",
            constraint=models.UniqueConstraint(fields=["tenant", "customer"],
                name="uq_revenue_profile_tenant_customer")),
        migrations.CreateModel(
            name="MarginThresholdConfig",
            fields=[
                ("id", models.UUIDField(primary_key=True, serialize=False, editable=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("min_margin_pct", models.DecimalField(decimal_places=2, default=0, max_digits=6)),
                ("consecutive_periods", models.IntegerField(default=1)),
                ("provider_cost_spike_pct", models.DecimalField(decimal_places=2, default=25, max_digits=6)),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                    related_name="margin_thresholds", to="tenants.tenant")),
                ("customer", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE,
                    related_name="margin_thresholds", to="customers.customer")),
            ],
            options={"db_table": "ubb_margin_threshold_config"},
        ),
        migrations.AddConstraint(model_name="marginthresholdconfig",
            constraint=models.UniqueConstraint(fields=["tenant"], condition=models.Q(customer__isnull=True),
                name="uq_margin_threshold_tenant_default")),
        migrations.AddConstraint(model_name="marginthresholdconfig",
            constraint=models.UniqueConstraint(fields=["tenant", "customer"], condition=models.Q(customer__isnull=False),
                name="uq_margin_threshold_tenant_customer")),
    ]
```
> Confirm the `id`/`created_at`/`updated_at` field definitions match `core.models.BaseModel` (UUID pk + auto timestamps) — copy the exact field defs from `subscriptions/migrations/0002`'s `CreateModel` blocks if they differ.

- [ ] **Step 6 — Verify**: `$DJ manage.py check`; `$DJ manage.py makemigrations --check --dry-run` → "No changes detected"; **DB:** `$DJ manage.py migrate`; `$DJ -m pytest apps/subscriptions/tests/test_models.py -q` → green. **Commit**: `feat(subscriptions): margin data model (accumulator split, economics reframe, revenue+threshold, seats)`.

---

### Task 4: Handler accumulates both costs + re-gate to metering

**Files:** Modify `apps/subscriptions/handlers.py`, `apps/subscriptions/apps.py`; Test `apps/subscriptions/tests/test_handlers.py`.

- [ ] **Step 1 — Failing test** (modify the existing handler test, or add): a `usage.recorded` payload with `provider_cost_micros` + `billed_cost_micros` produces an accumulator row with both totals:
```python
def test_handler_accumulates_provider_and_billed(self):
    from apps.subscriptions.handlers import handle_usage_recorded_subscriptions
    from apps.subscriptions.economics.models import CustomerCostAccumulator
    handle_usage_recorded_subscriptions("evt1", {
        "tenant_id": str(self.tenant.id), "customer_id": str(self.customer.id),
        "cost_micros": 1_000_000, "provider_cost_micros": 800_000, "billed_cost_micros": 1_000_000})
    acc = CustomerCostAccumulator.objects.get(tenant=self.tenant, customer=self.customer)
    assert acc.total_provider_cost_micros == 800_000
    assert acc.total_billed_cost_micros == 1_000_000
    assert acc.event_count == 1
```
(Reuse/adjust the existing `setUp` that creates `self.tenant`/`self.customer`.)

- [ ] **Step 2 — Run** → FAIL (handler still writes `total_cost_micros`).

- [ ] **Step 3 — Rewrite** `handle_usage_recorded_subscriptions` in `apps/subscriptions/handlers.py`: read `provider = payload.get("provider_cost_micros", 0) or 0` and `billed = payload.get("billed_cost_micros", payload.get("cost_micros", 0)) or 0`; skip only if `billed <= 0 and provider <= 0`; the atomic `update(...)` and the `create(...)` set `total_provider_cost_micros=F(...)+provider` (or `=provider`), `total_billed_cost_micros=F(...)+billed` (or `=billed`), `event_count` unchanged. (Mirror the existing fast-path/create/IntegrityError structure exactly, just with the two fields.)

- [ ] **Step 4 — Re-gate** in `apps/subscriptions/apps.py`: change `requires_product="subscriptions"` → `requires_product="metering"` (so meter-only heyotis accumulates; every tenant has `metering`).

- [ ] **Step 5 — Verify**: `$DJ manage.py check`; **DB:** `$DJ -m pytest apps/subscriptions/tests/test_handlers.py -q` → green. **Commit**: `feat(subscriptions): accumulate provider+billed cost; gate accumulator on metering`.

---

### Task 5: RevenueService + MarginService (reframe `EconomicsService`)

**Files:** Create `apps/subscriptions/economics/revenue.py`; Modify `apps/subscriptions/economics/services.py`; Test `apps/subscriptions/tests/test_economics.py` (rewrite to the new P&L).

- [ ] **Step 1 — Failing tests** (rewrite `apps/subscriptions/tests/test_economics.py`):
```python
import datetime
from django.test import TestCase
from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.subscriptions.economics.models import CustomerCostAccumulator, CustomerRevenueProfile
from apps.subscriptions.economics.revenue import RevenueService
from apps.subscriptions.economics.services import MarginService


class MarginServiceTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="T")
        self.customer = Customer.objects.create(tenant=self.tenant, external_id="c1")
        self.ps = datetime.date(2026, 6, 1)
        self.pe = datetime.date(2026, 7, 1)

    def test_meter_only_margin_is_billed_minus_provider(self):
        CustomerCostAccumulator.objects.create(
            tenant=self.tenant, customer=self.customer, period_start=self.ps, period_end=self.pe,
            total_provider_cost_micros=800_000, total_billed_cost_micros=1_000_000, event_count=2)
        econ = MarginService.snapshot_customer(self.tenant.id, self.customer.id, self.ps, self.pe)
        assert econ.subscription_revenue_micros == 0
        assert econ.usage_billed_micros == 1_000_000
        assert econ.provider_cost_micros == 800_000
        assert econ.gross_margin_micros == 200_000
        assert float(econ.margin_percentage) == 20.0  # 200k / 1_000k

    def test_manual_revenue_full_month(self):
        amt = RevenueService.manual_revenue_for_window(
            self.tenant.id, self.customer.id, self.ps, self.pe)
        assert amt == 0
        CustomerRevenueProfile.objects.create(
            tenant=self.tenant, customer=self.customer,
            recurring_amount_micros=500_000_000, effective_from=datetime.date(2026, 1, 1))
        amt = RevenueService.manual_revenue_for_window(
            self.tenant.id, self.customer.id, self.ps, self.pe)
        assert amt == 500_000_000  # full June

    def test_margin_includes_manual_revenue(self):
        CustomerRevenueProfile.objects.create(
            tenant=self.tenant, customer=self.customer,
            recurring_amount_micros=500_000_000, effective_from=datetime.date(2026, 1, 1))
        CustomerCostAccumulator.objects.create(
            tenant=self.tenant, customer=self.customer, period_start=self.ps, period_end=self.pe,
            total_provider_cost_micros=800_000, total_billed_cost_micros=1_000_000, event_count=2)
        econ = MarginService.snapshot_customer(self.tenant.id, self.customer.id, self.ps, self.pe)
        # revenue = 500_000_000 + 1_000_000 ; margin = revenue - 800_000
        assert econ.subscription_revenue_micros == 500_000_000
        assert econ.gross_margin_micros == 500_200_000
```

- [ ] **Step 2 — Run** → FAIL. (No DB: `--collect-only` after Steps 3-4 exist.)

- [ ] **Step 3 — RevenueService** `apps/subscriptions/economics/revenue.py`:
```python
import calendar
import datetime
from django.db.models import Sum


def _days_in_month(year, month):
    return calendar.monthrange(year, month)[1]


def _month_iter(start, end):
    """Yield (month_start, month_end) calendar months overlapping [start, end)."""
    cur = start.replace(day=1)
    while cur < end:
        nxt = (cur.replace(year=cur.year + 1, month=1, day=1)
               if cur.month == 12 else cur.replace(month=cur.month + 1, day=1))
        yield cur, nxt
        cur = nxt


class RevenueService:
    @staticmethod
    def manual_revenue_for_window(tenant_id, customer_id, start_date, end_date) -> int:
        from apps.subscriptions.economics.models import CustomerRevenueProfile
        p = CustomerRevenueProfile.objects.filter(
            tenant_id=tenant_id, customer_id=customer_id).first()
        if not p or not p.recurring_amount_micros:
            return 0
        eff_start = max(start_date, p.effective_from)
        eff_end = end_date if p.effective_to is None else min(end_date, p.effective_to)
        if eff_end <= eff_start:
            return 0
        total = 0
        for m_start, m_end in _month_iter(eff_start, eff_end):
            w_start = max(eff_start, m_start)
            w_end = min(eff_end, m_end)
            overlap_days = (w_end - w_start).days
            month_days = _days_in_month(m_start.year, m_start.month)
            total += p.recurring_amount_micros * overlap_days // month_days
        return total

    @staticmethod
    def stripe_revenue_for_window(tenant_id, customer_id, start_date, end_date) -> int:
        from apps.subscriptions.models import SubscriptionInvoice
        return SubscriptionInvoice.objects.filter(
            tenant_id=tenant_id, customer_id=customer_id,
            paid_at__date__gte=start_date, paid_at__date__lt=end_date,
        ).aggregate(t=Sum("amount_paid_micros"))["t"] or 0

    @staticmethod
    def revenue_for_window(tenant_id, customer_id, start_date, end_date) -> int:
        return (RevenueService.manual_revenue_for_window(tenant_id, customer_id, start_date, end_date)
                + RevenueService.stripe_revenue_for_window(tenant_id, customer_id, start_date, end_date))
```
> Note: a full calendar month gives `amount * days_in_month // days_in_month == amount` (exact). Month-to-date prorates.

- [ ] **Step 4 — MarginService** replace `apps/subscriptions/economics/services.py` body:
```python
from decimal import Decimal, ROUND_HALF_UP

from apps.subscriptions.economics.models import CustomerCostAccumulator, CustomerEconomics
from apps.subscriptions.economics.revenue import RevenueService


def _compose(subscription_revenue, usage_billed, provider_cost):
    total_revenue = subscription_revenue + usage_billed
    margin = total_revenue - provider_cost
    pct = (Decimal(margin) / Decimal(total_revenue) * 100).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP) if total_revenue > 0 else Decimal("0")
    return total_revenue, margin, pct


class MarginService:
    @staticmethod
    def compute_live(tenant_id, customer_id, start_date, end_date) -> dict:
        """Live margin for any window from UsageEvent + revenue. No persistence."""
        from apps.metering.queries import get_customer_cost_totals
        costs = get_customer_cost_totals(tenant_id, customer_id, start_date, end_date)
        subscription_revenue = RevenueService.revenue_for_window(
            tenant_id, customer_id, start_date, end_date)
        _, margin, pct = _compose(subscription_revenue, costs["billed_cost_micros"], costs["provider_cost_micros"])
        return {
            "customer_id": str(customer_id),
            "subscription_revenue_micros": subscription_revenue,
            "usage_billed_micros": costs["billed_cost_micros"],
            "provider_cost_micros": costs["provider_cost_micros"],
            "gross_margin_micros": margin,
            "margin_percentage": float(pct),
            "event_count": costs["event_count"],
        }

    @staticmethod
    def snapshot_customer(tenant_id, customer_id, period_start, period_end) -> CustomerEconomics:
        """Monthly snapshot from the accumulator + full-month revenue. Persists CustomerEconomics."""
        acc = CustomerCostAccumulator.objects.filter(
            tenant_id=tenant_id, customer_id=customer_id, period_start=period_start).first()
        provider_cost = acc.total_provider_cost_micros if acc else 0
        usage_billed = acc.total_billed_cost_micros if acc else 0
        subscription_revenue = RevenueService.revenue_for_window(
            tenant_id, customer_id, period_start, period_end)
        _, margin, pct = _compose(subscription_revenue, usage_billed, provider_cost)
        econ, _ = CustomerEconomics.objects.update_or_create(
            tenant_id=tenant_id, customer_id=customer_id, period_start=period_start,
            defaults={
                "period_end": period_end,
                "subscription_revenue_micros": subscription_revenue,
                "usage_billed_micros": usage_billed,
                "provider_cost_micros": provider_cost,
                "gross_margin_micros": margin,
                "margin_percentage": pct,
            })
        return econ
```

- [ ] **Step 5 — Verify**: `$DJ manage.py check`; **DB:** `$DJ -m pytest apps/subscriptions/tests/test_economics.py -q` → green. **Commit**: `feat(subscriptions): RevenueService + MarginService (new P&L)`.

---

### Task 6: Snapshot task — flagging + provider-cost-spike webhooks

**Files:** Modify `apps/subscriptions/economics/services.py` (add flag/emit helpers), `apps/subscriptions/tasks.py`; Test `apps/subscriptions/tests/test_tasks.py`.

- [ ] **Step 1 — Failing tests** (add to `apps/subscriptions/tests/test_tasks.py`): seed a customer whose margin% is below a `MarginThresholdConfig.min_margin_pct`, run the task, assert `CustomerEconomics.is_unprofitable` is set and a `margin.customer_unprofitable` `OutboxEvent` exists; seed a prior-month snapshot with low provider cost and a current month with a >25% provider-cost rise, assert a `margin.provider_cost_spike` `OutboxEvent` exists. (Use `OutboxEvent.objects.filter(event_type=...)`.)

- [ ] **Step 2 — Run** → FAIL.

- [ ] **Step 3 — Flagging + emission** add to `MarginService` in `services.py`:
```python
    @staticmethod
    def _threshold(tenant_id, customer_id):
        from apps.subscriptions.economics.models import MarginThresholdConfig
        cfg = MarginThresholdConfig.objects.filter(tenant_id=tenant_id, customer_id=customer_id).first()
        if cfg:
            return cfg
        return MarginThresholdConfig.objects.filter(tenant_id=tenant_id, customer__isnull=True).first()

    @staticmethod
    def evaluate_and_emit(econ):
        """Set is_unprofitable + emit webhooks on transition. Call inside a transaction."""
        from decimal import Decimal
        from django.db import transaction
        from apps.platform.events.outbox import write_event
        from apps.platform.events.schemas import MarginCustomerUnprofitable, MarginProviderCostSpike
        from apps.subscriptions.economics.models import CustomerEconomics

        cfg = MarginService._threshold(econ.tenant_id, econ.customer_id)
        min_pct = Decimal(cfg.min_margin_pct) if cfg else Decimal("0")
        spike_pct = Decimal(cfg.provider_cost_spike_pct) if cfg else Decimal("25")
        consecutive = cfg.consecutive_periods if cfg else 1

        # consecutive-period check: this snapshot + the previous (consecutive-1) all below
        recent = list(CustomerEconomics.objects.filter(
            tenant_id=econ.tenant_id, customer_id=econ.customer_id,
            period_start__lte=econ.period_start,
        ).order_by("-period_start")[:consecutive])
        below = len(recent) >= consecutive and all(e.margin_percentage < min_pct for e in recent)
        was_unprofitable = recent[1].is_unprofitable if len(recent) > 1 else False

        if below != econ.is_unprofitable:
            econ.is_unprofitable = below
            econ.save(update_fields=["is_unprofitable", "updated_at"])
        if below and not was_unprofitable:
            with transaction.atomic():
                write_event(MarginCustomerUnprofitable(
                    tenant_id=str(econ.tenant_id), customer_id=str(econ.customer_id),
                    period_start=econ.period_start.isoformat(),
                    gross_margin_micros=econ.gross_margin_micros,
                    margin_pct=float(econ.margin_percentage), threshold_pct=float(min_pct)))

        # provider-cost spike vs previous period
        prev = (CustomerEconomics.objects.filter(
            tenant_id=econ.tenant_id, customer_id=econ.customer_id,
            period_start__lt=econ.period_start).order_by("-period_start").first())
        if prev and prev.provider_cost_micros > 0:
            rise = (Decimal(econ.provider_cost_micros - prev.provider_cost_micros)
                    / Decimal(prev.provider_cost_micros) * 100)
            if rise >= spike_pct:
                with transaction.atomic():
                    write_event(MarginProviderCostSpike(
                        tenant_id=str(econ.tenant_id), customer_id=str(econ.customer_id),
                        period_start=econ.period_start.isoformat(),
                        prev_provider_cost_micros=prev.provider_cost_micros,
                        current_provider_cost_micros=econ.provider_cost_micros,
                        prev_margin_pct=float(prev.margin_percentage),
                        current_margin_pct=float(econ.margin_percentage)))

    @staticmethod
    def snapshot_all(tenant_id, period_start, period_end):
        """Snapshot every customer with cost or revenue activity this period; evaluate flags."""
        from apps.subscriptions.economics.models import (
            CustomerCostAccumulator, CustomerRevenueProfile)
        ids = set(CustomerCostAccumulator.objects.filter(
            tenant_id=tenant_id, period_start=period_start).values_list("customer_id", flat=True))
        ids |= set(CustomerRevenueProfile.objects.filter(
            tenant_id=tenant_id).values_list("customer_id", flat=True))
        results = []
        for cid in ids:
            econ = MarginService.snapshot_customer(tenant_id, cid, period_start, period_end)
            MarginService.evaluate_and_emit(econ)
            results.append(econ)
        return results
```

- [ ] **Step 4 — Task** rewrite `calculate_all_economics_task` in `apps/subscriptions/tasks.py`: filter `Tenant.objects.filter(products__contains=["metering"], is_active=True)`; call `MarginService.snapshot_all(tenant.id, period_start, period_end)` (import `MarginService` from `apps.subscriptions.economics.services`). Keep `sync_tenant_subscriptions_task` unchanged.

- [ ] **Step 5 — Verify**: `$DJ manage.py check`; **DB:** `$DJ -m pytest apps/subscriptions/tests/test_tasks.py -q` → green. **Commit**: `feat(subscriptions): margin snapshots + unprofitable/spike webhooks`.

---

### Task 7: Margin API (metering-gated) + remove old economics endpoints

**Files:** Create `apps/subscriptions/api/margin_endpoints.py`, `apps/subscriptions/api/margin_schemas.py`; Modify `apps/subscriptions/api/endpoints.py` (remove `/economics*`), `config/urls.py`, `apps/subscriptions/queries.py`; Test `apps/subscriptions/tests/test_margin_endpoints.py` (new).

- [ ] **Step 1 — Failing tests** `apps/subscriptions/tests/test_margin_endpoints.py`: a `metering`-only tenant (no `subscriptions` product) can `PUT /api/v1/margin/customers/{id}/revenue` then `GET /api/v1/margin/{id}` and see margin reflecting the revenue + usage; `GET /api/v1/margin/by-dimension?provider=1` returns rows; `GET /api/v1/margin/unprofitable` and `GET /api/v1/margin/threshold` work; `PUT /api/v1/margin/threshold` upserts. (Build a tenant with `products=["metering"]`, an API key, a customer, and a couple of `UsageEvent`s via `UsageService.record_usage(provider_cost_micros=...)`.)

- [ ] **Step 2 — Run** → FAIL (404 / no router).

- [ ] **Step 3 — Schemas** `apps/subscriptions/api/margin_schemas.py`:
```python
from uuid import UUID
from typing import Optional
from ninja import Schema, Field


class RevenueProfileIn(Schema):
    recurring_amount_micros: int = Field(ge=0)
    interval: str = "month"
    currency: str = "usd"
    effective_from: Optional[str] = None  # ISO date; defaults to today
    effective_to: Optional[str] = None


class RevenueProfileOut(Schema):
    recurring_amount_micros: int
    interval: str
    currency: str
    effective_from: str
    effective_to: Optional[str] = None


class MarginThresholdIn(Schema):
    min_margin_pct: float = 0.0
    consecutive_periods: int = Field(default=1, ge=1)
    provider_cost_spike_pct: float = 25.0


class MarginThresholdOut(Schema):
    min_margin_pct: float
    consecutive_periods: int
    provider_cost_spike_pct: float
```

- [ ] **Step 4 — Router** `apps/subscriptions/api/margin_endpoints.py` (complete; all `metering`-gated):
```python
from datetime import date, timedelta
from uuid import UUID

from django.shortcuts import get_object_or_404
from django.utils import timezone
from ninja import NinjaAPI

from core.auth import ApiKeyAuth, ProductAccess
from apps.platform.customers.models import Customer
from apps.subscriptions.economics.models import (
    CustomerEconomics, CustomerRevenueProfile, MarginThresholdConfig)
from apps.subscriptions.economics.services import MarginService
from apps.subscriptions.api.margin_schemas import (
    RevenueProfileIn, RevenueProfileOut, MarginThresholdIn, MarginThresholdOut)

margin_api = NinjaAPI(auth=ApiKeyAuth(), urls_namespace="ubb_margin_v1")
_product_check = ProductAccess("metering")


def _current_month():
    today = timezone.now().date()
    start = today.replace(day=1)
    end = (start.replace(year=start.year + 1, month=1, day=1)
           if start.month == 12 else start.replace(month=start.month + 1, day=1))
    return start, end


def _window(start_date, end_date):
    if start_date and end_date:
        return start_date, end_date
    s, _ = _current_month()
    today = timezone.now().date()
    return s, today + timedelta(days=1)  # month-to-date (inclusive of today)


@margin_api.get("/summary")
def margin_summary(request, start_date: date = None, end_date: date = None):
    _product_check(request)
    s, e = _window(start_date, end_date)
    from apps.metering.queries import get_per_customer_cost_totals
    from apps.subscriptions.economics.revenue import RevenueService
    rows = get_per_customer_cost_totals(request.auth.tenant.id, s, e)
    total_provider = total_billed = total_sub = 0
    for r in rows:
        total_provider += r["provider_cost_micros"]
        total_billed += r["billed_cost_micros"]
        total_sub += RevenueService.revenue_for_window(
            request.auth.tenant.id, r["customer_id"], s, e)
    total_revenue = total_sub + total_billed
    margin = total_revenue - total_provider
    return {
        "period": {"start": s.isoformat(), "end": e.isoformat()},
        "subscription_revenue_micros": total_sub,
        "usage_billed_micros": total_billed,
        "provider_cost_micros": total_provider,
        "total_revenue_micros": total_revenue,
        "gross_margin_micros": margin,
        "margin_percentage": round(margin / total_revenue * 100, 2) if total_revenue else 0.0,
        "customer_count": len(rows),
    }


@margin_api.get("/by-dimension")
def margin_by_dimension(request, provider: int = None, product: int = None,
                        tag_key: str = None, start_date: date = None, end_date: date = None):
    _product_check(request)
    s, e = _window(start_date, end_date)
    from apps.metering.queries import get_dimensional_margin
    if tag_key:
        rows = get_dimensional_margin(request.auth.tenant.id, tag_key=tag_key, start_date=s, end_date=e)
    elif product:
        rows = get_dimensional_margin(request.auth.tenant.id, group_by="product_id", start_date=s, end_date=e)
    else:
        rows = get_dimensional_margin(request.auth.tenant.id, group_by="provider", start_date=s, end_date=e)
    return {"period": {"start": s.isoformat(), "end": e.isoformat()}, "rows": rows}


@margin_api.get("/unprofitable")
def margin_unprofitable(request, period_start: date = None):
    _product_check(request)
    ps = period_start or _current_month()[0]
    rows = CustomerEconomics.objects.filter(
        tenant=request.auth.tenant, period_start=ps, is_unprofitable=True
    ).select_related("customer")
    return {"period_start": ps.isoformat(), "customers": [{
        "customer_id": str(r.customer_id), "external_id": r.customer.external_id,
        "gross_margin_micros": r.gross_margin_micros,
        "margin_percentage": float(r.margin_percentage),
    } for r in rows]}


@margin_api.get("/threshold", response=MarginThresholdOut)
def get_threshold(request):
    _product_check(request)
    cfg = MarginThresholdConfig.objects.filter(tenant=request.auth.tenant, customer__isnull=True).first()
    if not cfg:
        return {"min_margin_pct": 0.0, "consecutive_periods": 1, "provider_cost_spike_pct": 25.0}
    return {"min_margin_pct": float(cfg.min_margin_pct), "consecutive_periods": cfg.consecutive_periods,
            "provider_cost_spike_pct": float(cfg.provider_cost_spike_pct)}


@margin_api.put("/threshold", response=MarginThresholdOut)
def put_threshold(request, payload: MarginThresholdIn):
    _product_check(request)
    cfg, _ = MarginThresholdConfig.objects.update_or_create(
        tenant=request.auth.tenant, customer=None,
        defaults={"min_margin_pct": payload.min_margin_pct,
                  "consecutive_periods": payload.consecutive_periods,
                  "provider_cost_spike_pct": payload.provider_cost_spike_pct})
    return {"min_margin_pct": float(cfg.min_margin_pct), "consecutive_periods": cfg.consecutive_periods,
            "provider_cost_spike_pct": float(cfg.provider_cost_spike_pct)}


@margin_api.get("/customers/{customer_id}/revenue", response=RevenueProfileOut)
def get_revenue(request, customer_id: UUID):
    _product_check(request)
    customer = get_object_or_404(Customer, id=customer_id, tenant=request.auth.tenant)
    p = CustomerRevenueProfile.objects.filter(tenant=request.auth.tenant, customer=customer).first()
    if not p:
        return {"recurring_amount_micros": 0, "interval": "month", "currency": "usd",
                "effective_from": timezone.now().date().isoformat(), "effective_to": None}
    return {"recurring_amount_micros": p.recurring_amount_micros, "interval": p.interval,
            "currency": p.currency, "effective_from": p.effective_from.isoformat(),
            "effective_to": p.effective_to.isoformat() if p.effective_to else None}


@margin_api.put("/customers/{customer_id}/revenue", response=RevenueProfileOut)
def put_revenue(request, customer_id: UUID, payload: RevenueProfileIn):
    _product_check(request)
    customer = get_object_or_404(Customer, id=customer_id, tenant=request.auth.tenant)
    eff_from = date.fromisoformat(payload.effective_from) if payload.effective_from else timezone.now().date()
    eff_to = date.fromisoformat(payload.effective_to) if payload.effective_to else None
    p, _ = CustomerRevenueProfile.objects.update_or_create(
        tenant=request.auth.tenant, customer=customer,
        defaults={"recurring_amount_micros": payload.recurring_amount_micros,
                  "interval": payload.interval, "currency": payload.currency,
                  "effective_from": eff_from, "effective_to": eff_to})
    return {"recurring_amount_micros": p.recurring_amount_micros, "interval": p.interval,
            "currency": p.currency, "effective_from": p.effective_from.isoformat(),
            "effective_to": p.effective_to.isoformat() if p.effective_to else None}


@margin_api.get("/{customer_id}/trend")
def margin_trend(request, customer_id: UUID, periods: int = 6):
    _product_check(request)
    customer = get_object_or_404(Customer, id=customer_id, tenant=request.auth.tenant)
    rows = CustomerEconomics.objects.filter(
        tenant=request.auth.tenant, customer=customer).order_by("-period_start")[:max(1, min(periods, 36))]
    return {"customer_id": str(customer.id), "points": [{
        "period_start": r.period_start.isoformat(),
        "provider_cost_micros": r.provider_cost_micros,
        "usage_billed_micros": r.usage_billed_micros,
        "subscription_revenue_micros": r.subscription_revenue_micros,
        "gross_margin_micros": r.gross_margin_micros,
        "margin_percentage": float(r.margin_percentage),
    } for r in reversed(list(rows))]}


@margin_api.get("/{customer_id}")
def customer_margin(request, customer_id: UUID, start_date: date = None, end_date: date = None):
    _product_check(request)
    customer = get_object_or_404(Customer, id=customer_id, tenant=request.auth.tenant)
    s, e = _window(start_date, end_date)
    data = MarginService.compute_live(request.auth.tenant.id, customer.id, s, e)
    data["external_id"] = customer.external_id
    data["period"] = {"start": s.isoformat(), "end": e.isoformat()}
    return data


@margin_api.get("")
def list_margin(request, start_date: date = None, end_date: date = None):
    _product_check(request)
    s, e = _window(start_date, end_date)
    from apps.metering.queries import get_per_customer_cost_totals
    from apps.subscriptions.economics.revenue import RevenueService
    out = []
    for r in get_per_customer_cost_totals(request.auth.tenant.id, s, e):
        sub = RevenueService.revenue_for_window(request.auth.tenant.id, r["customer_id"], s, e)
        revenue = sub + r["billed_cost_micros"]
        margin = revenue - r["provider_cost_micros"]
        out.append({"customer_id": str(r["customer_id"]),
                    "subscription_revenue_micros": sub,
                    "usage_billed_micros": r["billed_cost_micros"],
                    "provider_cost_micros": r["provider_cost_micros"],
                    "gross_margin_micros": margin,
                    "margin_percentage": round(margin / revenue * 100, 2) if revenue else 0.0})
    return {"period": {"start": s.isoformat(), "end": e.isoformat()}, "customers": out}
```
> Route order: register `/summary`, `/by-dimension`, `/unprofitable`, `/threshold`, `/customers/...` BEFORE the `/{customer_id}` and `/{customer_id}/trend` catch-alls (django-ninja matches in definition order) — the layout above already does this.

- [ ] **Step 5 — Mount + prune**: in `config/urls.py` add `from apps.subscriptions.api.margin_endpoints import margin_api` and `path("api/v1/margin/", margin_api.urls)` (before the generic `api/v1/`). In `apps/subscriptions/api/endpoints.py` DELETE `_current_period`, `get_economics_summary`, `list_economics`, `get_customer_economics` (the `/economics*` endpoints) and their now-unused imports (`EconomicsService`, `Decimal`, `CustomerEconomicsOut`, etc.). Keep `/sync`, `/customers/{id}/subscription`, `/customers/{id}/invoices`, and the Stripe webhook (still `subscriptions`-gated).

- [ ] **Step 6 — `queries.py`** reframe `apps/subscriptions/queries.py` `get_economics_summary` to aggregate the new fields: `Sum("subscription_revenue_micros")`, `Sum("usage_billed_micros")`, `Sum("provider_cost_micros")`, `Sum("gross_margin_micros")`; return those keys. Leave `get_customer_economics`/`get_customer_subscription` (signatures unchanged).

- [ ] **Step 7 — Verify**: `$DJ manage.py check`; `$DJ manage.py makemigrations --check --dry-run` → "No changes detected"; **DB:** `$DJ -m pytest apps/subscriptions api/v1/tests -q` → green; `git grep -n "/economics" -- apps ':!*/tests/*'` → none. **Commit**: `feat(margin): metering-gated margin API; remove old economics endpoints`.

---

### Task 8: Seat-aware Stripe sync

**Files:** Modify `apps/subscriptions/stripe/sync.py`, `apps/subscriptions/api/webhooks.py`; Test `apps/subscriptions/tests/test_sync.py`.

- [ ] **Step 1 — Failing test**: a mocked Stripe subscription with `quantity=3` and `plan.amount=1000` syncs a `StripeSubscription` with `quantity == 3` (and `amount_micros == 1000 * 10_000`, the per-seat unit price). (Mirror the existing `test_sync.py` mocking style.)

- [ ] **Step 2 — Run** → FAIL.

- [ ] **Step 3 — Sync** in `sync.py` `update_or_create(... defaults=...)`: add `"quantity": getattr(stripe_sub, "quantity", 1) or 1`. (Keep `amount_micros` as the per-seat unit price; the seat-inclusive total = `amount_micros * quantity`, used by future live MRR estimation. Closed-period revenue still comes from invoices.)

- [ ] **Step 4 — Webhooks** in `apps/subscriptions/api/webhooks.py`: where `handle_subscription_created`/`handle_subscription_updated` build the `StripeSubscription` defaults, add `"quantity"` from the event's subscription object (default 1). (Read the file first; mirror the existing field-mapping.)

- [ ] **Step 5 — Verify**: `$DJ manage.py check`; **DB:** `$DJ -m pytest apps/subscriptions/tests/test_sync.py apps/subscriptions/tests/test_webhooks.py -q` → green. **Commit**: `feat(subscriptions): capture subscription quantity (seats)`.

---

### Task 9: SDK margin client + types

**Files:** Modify `ubb-sdk/ubb/metering.py` (or a new `ubb-sdk/ubb/margin.py`), `ubb-sdk/ubb/client.py`, `ubb-sdk/ubb/types.py`; Tests `ubb-sdk/tests/test_metering_client.py` (or `test_margin_client.py`).

- [ ] **Step 1 — Types** `ubb-sdk/ubb/types.py`: add frozen dataclasses `CustomerMargin` (`customer_id, subscription_revenue_micros, usage_billed_micros, provider_cost_micros, gross_margin_micros, margin_percentage`), `DimensionMargin` (`dimension, provider_cost_micros, billed_cost_micros, margin_micros, event_count`), `MarginTrendPoint` (`period_start, provider_cost_micros, usage_billed_micros, subscription_revenue_micros, gross_margin_micros, margin_percentage`), `CustomerRevenue` (`recurring_amount_micros, interval, currency, effective_from, effective_to`). All non-id fields default-able (`int | None = None` etc.) so `**dict` parsing tolerates partial payloads.

- [ ] **Step 2 — Client methods** add to `MeteringClient` (margin is metering-gated, so it belongs on the metering client; base path `/api/v1/margin`):
```python
    def get_customer_margin(self, customer_id, start_date=None, end_date=None):
        params = {k: v for k, v in {"start_date": start_date, "end_date": end_date}.items() if v}
        r = self._request("get", f"/api/v1/margin/{customer_id}", params=params)
        return CustomerMargin(**{k: v for k, v in r.json().items()
                                 if k in CustomerMargin.__dataclass_fields__})

    def get_margin_by_dimension(self, *, provider=False, product=False, tag_key=None,
                                start_date=None, end_date=None):
        params = {}
        if provider: params["provider"] = 1
        if product: params["product"] = 1
        if tag_key: params["tag_key"] = tag_key
        if start_date: params["start_date"] = start_date
        if end_date: params["end_date"] = end_date
        r = self._request("get", "/api/v1/margin/by-dimension", params=params)
        return [DimensionMargin(**row) for row in r.json()["rows"]]

    def get_unprofitable_customers(self, period_start=None):
        params = {"period_start": period_start} if period_start else {}
        r = self._request("get", "/api/v1/margin/unprofitable", params=params)
        return r.json()["customers"]

    def get_margin_trend(self, customer_id, periods=6):
        r = self._request("get", f"/api/v1/margin/{customer_id}/trend", params={"periods": periods})
        return [MarginTrendPoint(**p) for p in r.json()["points"]]

    def set_customer_revenue(self, customer_id, recurring_amount_micros, interval="month",
                             currency="usd", effective_from=None, effective_to=None):
        body = {"recurring_amount_micros": recurring_amount_micros, "interval": interval,
                "currency": currency}
        if effective_from: body["effective_from"] = effective_from
        if effective_to: body["effective_to"] = effective_to
        r = self._request("put", f"/api/v1/margin/customers/{customer_id}/revenue", json=body)
        return CustomerRevenue(**r.json())

    def get_customer_revenue(self, customer_id):
        r = self._request("get", f"/api/v1/margin/customers/{customer_id}/revenue")
        return CustomerRevenue(**r.json())
```
Import the new types at the top of `metering.py`.

- [ ] **Step 3 — UBBClient** thread the same methods through `ubb-sdk/ubb/client.py` (delegate to `self._require_metering().<method>(...)`), mirroring the existing `get_usage` delegation.

- [ ] **Step 4 — SDK tests** add `test_margin_client.py` (or extend `test_metering_client.py`): mock `httpx.Client.get/put` returns for each method; assert the right path/params and that results parse into the dataclasses. Run from `ubb-sdk/`: `/c/Users/tom_l/git/ubb/ubb-platform/.venv/Scripts/python.exe -m pytest -q` → green.

- [ ] **Step 5 — Commit**: `feat(sdk): margin read + revenue-input methods`.

---

### Task 10: Final verification

- [ ] `$DJ manage.py check` → no issues.
- [ ] `$DJ manage.py makemigrations --check --dry-run` → "No changes detected".
- [ ] `$DJ -m pytest --collect-only -q` → clean.
- [ ] `git grep -nE "usage_cost_micros|/economics|requires_product=\"subscriptions\".*cost" -- apps ':!*/migrations/*'` → no `usage_cost_micros`, no `/economics` route, accumulator handler gated on `metering`.
- [ ] **With DB (REQUIRED):** drop/recreate the `ubb` DB, `$DJ manage.py migrate` applies `subscriptions/0003` cleanly from zero; `$DJ -m pytest -q` whole suite green; `cd ../ubb-sdk && <venv python> -m pytest -q` green.
- [ ] Spot-check end to end: a `metering`-only tenant records usage (`provider_cost_micros`, `billed_cost_micros`), sets a revenue profile, and `GET /api/v1/margin/{customer_id}` returns `gross_margin = (revenue + billed) − provider` with correct `margin_percentage`.

---

## Self-Review

**Spec coverage (vs. Stage 2 design):** P&L reframe (T3/T5) ✓; manual revenue primary + Stripe optional (`RevenueService`, T5) ✓; metering-gating of margin/revenue + accumulator (T4/T7) ✓; hybrid live (`compute_live`, T5/T7) + monthly snapshots (T6) ✓; usage-only per-dimension margin (T1 query + T7 endpoint) ✓; configurable threshold + unprofitable flag (T3 model, T6 evaluate) ✓; provider-cost-spike + unprofitable webhooks via outbox (T2 contracts/registration, T6 emit) ✓; seat capture (T8) ✓; margin API surface (T7) ✓; SDK (T9) ✓; keep/reframe/delete (T4–T8; nothing material deleted) ✓.

**Placeholder scan:** Webhook field mapping in T8 Step 4 says "read the file first; mirror the existing mapping" — a verification instruction (the exact current `webhooks.py` defaults must be matched), not a placeholder. `BaseModel` field defs in the T3 migration are flagged "confirm vs. 0002" for exactness.

**Type/name consistency:** `MarginService.compute_live`/`snapshot_customer`/`snapshot_all`/`evaluate_and_emit` consistent across T5/T6/T7. Metering queries `get_customer_cost_totals`/`get_per_customer_cost_totals`/`get_dimensional_margin` consistent across T1/T5/T7. Event contracts `MarginCustomerUnprofitable`/`MarginProviderCostSpike` consistent across T2/T6 and the `events/apps.py` registration. P&L field names (`subscription_revenue_micros`/`usage_billed_micros`/`provider_cost_micros`/`gross_margin_micros`/`margin_percentage`/`is_unprofitable`) identical across model (T3), service (T5/T6), endpoints (T7), SDK types (T9).

**Migration risk:** flagged at top; T3 is the only migration and is DB-validated + re-validated from a fresh DB in T10.
