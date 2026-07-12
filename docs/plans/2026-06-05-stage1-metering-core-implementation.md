# Stage 1 — Metering Core (heyotis) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `UsageEvent` the hardened durable source of truth with a caller-provided-cost contract, dimensional `tags`, a slim per-tenant/per-customer markup, and a dimensional analytics API. No money, no gate (that is Stage 3).

**Architecture:** The caller passes the exact `provider_cost_micros`; UBB derives `billed_cost_micros` via `MarkupService` unless overridden. Cost model collapses to two authoritative non-null fields (`provider_cost_micros`, `billed_cost_micros`); `cost_micros`/`usage_metrics`/`properties` are removed; `group_keys`→`tags` (cap 10→50). Tasks are ordered **additive-before-destructive** so each commit keeps the suite importable.

**Tech Stack:** Django 6, django-ninja, pytest-django, Postgres (GIN), Celery. SDK: httpx.

**Design ref:** `docs/plans/2026-06-05-stage1-metering-core-design.md`

---

## ⚠️ Migration-validation caveat

Tasks 1–6 include real schema migrations (column rename + **GIN index swap**, **non-null backfills**, column drops). The static harness (`manage.py check`, `makemigrations --check`, `pytest --collect-only`) validates model/migration *consistency* and import health, but does **NOT** prove the migrations *apply* on Postgres or that backfills are correct. **Every migration task MUST be validated with `manage.py migrate` + the relevant `pytest` run against a real Postgres before it is trusted.** If no DB is available, implement and static-check, but mark migrate/test steps UNVERIFIED — do not claim green.

## Conventions

- Run from `ubb-platform/`, venv active. Venv python: `.venv/Scripts/python.exe` (Windows) or `.venv/bin/python` (POSIX).
- `$DJ` = `DJANGO_SETTINGS_MODULE=config.settings <python>`
- Static checks: `$DJ manage.py check` · `$DJ manage.py makemigrations --check --dry-run` · `$DJ -m pytest --collect-only -q`
- DB checks (when available): `$DJ manage.py migrate` · `$DJ -m pytest <paths> -q`
- Branch `tl-changes-05-06-26`. Commit per task. Migration head at start: `usage/0015`, `pricing/0005`, `tenants/0008`.

---

### Task 1: `Tenant.default_currency` (additive)

**Files:** Modify `apps/platform/tenants/models.py`; Create `apps/platform/tenants/migrations/0009_tenant_default_currency.py`; Test `apps/platform/tenants/tests/test_billing_mode.py` (append).

- [ ] **Step 1 — Failing test** (append to `TestTenantBillingMode`):
```python
    def test_default_currency_defaults_to_usd(self):
        t = Tenant.objects.create(name="T", products=["metering"])
        assert t.default_currency == "usd"
```
- [ ] **Step 2 — Run** `$DJ -m pytest apps/platform/tenants/tests/test_billing_mode.py::TestTenantBillingMode::test_default_currency_defaults_to_usd -q` → FAIL (no attribute). (If no DB: `--collect-only` only.)
- [ ] **Step 3 — Add field** on `Tenant` (after `billing_mode`):
```python
    default_currency = models.CharField(max_length=3, default="usd")
```
- [ ] **Step 4 — Migration** `0009_tenant_default_currency.py`:
```python
from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [("tenants", "0008_add_billing_mode")]
    operations = [
        migrations.AddField(
            model_name="tenant",
            name="default_currency",
            field=models.CharField(default="usd", max_length=3),
        ),
    ]
```
- [ ] **Step 5 — Verify**: `$DJ manage.py check` → ok; `$DJ manage.py makemigrations --check` → "No changes detected"; `--collect-only` → +1 test.
- [ ] **Step 6 — Commit**: `git commit -am "feat(tenants): add default_currency"`

---

### Task 2: Slim markup model + `MarkupService` + endpoints

Rework `TenantMarkup` to a per-tenant default + per-customer override (drop dimensional `event_type`/`provider`). `MarkupService` is created but not yet wired into `record_usage` (Task 5 wires it).

**Files:**
- Modify: `apps/metering/pricing/models.py`, `apps/metering/pricing/admin.py`
- Create: `apps/metering/pricing/services/markup_service.py`, `apps/metering/pricing/migrations/0006_slim_tenant_markup.py`
- Modify: `api/v1/metering_endpoints.py`, `api/v1/schemas.py`
- Modify: `apps/metering/pricing/tests/test_models.py`; Create `apps/metering/pricing/tests/test_markup_service.py`; Modify `api/v1/tests/test_metering_endpoints.py` (`PricingMarkupsCRUDTest`)

- [ ] **Step 1 — Failing tests** `apps/metering/pricing/tests/test_markup_service.py`:
```python
import pytest
from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.metering.pricing.models import TenantMarkup
from apps.metering.pricing.services.markup_service import MarkupService


@pytest.mark.django_db
class TestMarkupService:
    def setup_method(self):
        pass

    def test_no_markup_returns_provider_cost(self):
        t = Tenant.objects.create(name="T", products=["metering"])
        c = Customer.objects.create(tenant=t, external_id="c1")
        assert MarkupService.apply(100_000, tenant=t, customer=c) == 100_000

    def test_tenant_default_markup_applied(self):
        t = Tenant.objects.create(name="T", products=["metering"])
        c = Customer.objects.create(tenant=t, external_id="c1")
        TenantMarkup.objects.create(tenant=t, customer=None, markup_percentage_micros=20_000_000)  # 20%
        assert MarkupService.apply(100_000, tenant=t, customer=c) == 120_000

    def test_customer_override_beats_tenant_default(self):
        t = Tenant.objects.create(name="T", products=["metering"])
        c = Customer.objects.create(tenant=t, external_id="c1")
        TenantMarkup.objects.create(tenant=t, customer=None, markup_percentage_micros=20_000_000)
        TenantMarkup.objects.create(tenant=t, customer=c, markup_percentage_micros=50_000_000)
        assert MarkupService.apply(100_000, tenant=t, customer=c) == 150_000

    def test_fixed_uplift_added(self):
        t = Tenant.objects.create(name="T", products=["metering"])
        c = Customer.objects.create(tenant=t, external_id="c1")
        TenantMarkup.objects.create(tenant=t, customer=None, markup_percentage_micros=0, fixed_uplift_micros=500)
        assert MarkupService.apply(100_000, tenant=t, customer=c) == 100_500
```
- [ ] **Step 2 — Run** → FAIL (no `markup_service`, `customer` field). (No DB: `--collect-only` will error until Step 3–4 exist.)
- [ ] **Step 3 — Rework `TenantMarkup`** in `apps/metering/pricing/models.py` (replace the class body):
```python
class TenantMarkup(BaseModel):
    tenant = models.ForeignKey(
        "tenants.Tenant", on_delete=models.CASCADE, related_name="markups",
    )
    customer = models.ForeignKey(
        "customers.Customer", on_delete=models.CASCADE, related_name="markups",
        null=True, blank=True,
    )
    markup_percentage_micros = models.BigIntegerField(default=0)  # 1_000_000 == 1%
    fixed_uplift_micros = models.BigIntegerField(default=0)

    class Meta:
        db_table = "ubb_tenant_markup"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant"], condition=models.Q(customer__isnull=True),
                name="uq_markup_tenant_default",
            ),
            models.UniqueConstraint(
                fields=["tenant", "customer"], condition=models.Q(customer__isnull=False),
                name="uq_markup_tenant_customer",
            ),
        ]

    def calculate_markup_micros(self, provider_cost_micros: int) -> int:
        percent = (provider_cost_micros * self.markup_percentage_micros + 50_000_000) // 100_000_000
        return percent + self.fixed_uplift_micros
```
- [ ] **Step 4 — `MarkupService`** `apps/metering/pricing/services/markup_service.py`:
```python
from apps.metering.pricing.models import TenantMarkup


class MarkupService:
    @staticmethod
    def resolve(tenant, customer):
        """Return the applicable TenantMarkup (customer override → tenant default → None)."""
        if customer is not None:
            m = TenantMarkup.objects.filter(tenant=tenant, customer=customer).first()
            if m:
                return m
        return TenantMarkup.objects.filter(tenant=tenant, customer__isnull=True).first()

    @staticmethod
    def apply(provider_cost_micros, tenant, customer):
        """billed = provider + markup(provider); no markup configured → billed == provider."""
        markup = MarkupService.resolve(tenant, customer)
        if markup is None:
            return provider_cost_micros
        return provider_cost_micros + markup.calculate_markup_micros(provider_cost_micros)
```
- [ ] **Step 5 — Migration** `0006_slim_tenant_markup.py` (drops `event_type`/`provider`/`valid_from`/`valid_to` and the old index, adds `customer` FK + new constraints). Author by hand:
```python
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("pricing", "0005_delete_providerrate"),
        ("customers", "0009_rename_arrears_to_min_balance"),
    ]
    operations = [
        migrations.RemoveIndex(model_name="tenantmarkup", name="idx_markup_tenant_lookup"),
        migrations.RemoveField(model_name="tenantmarkup", name="event_type"),
        migrations.RemoveField(model_name="tenantmarkup", name="provider"),
        migrations.RemoveField(model_name="tenantmarkup", name="valid_from"),
        migrations.RemoveField(model_name="tenantmarkup", name="valid_to"),
        migrations.AddField(
            model_name="tenantmarkup", name="customer",
            field=models.ForeignKey(
                null=True, blank=True, on_delete=django.db.models.deletion.CASCADE,
                related_name="markups", to="customers.customer",
            ),
        ),
        migrations.AddConstraint(
            model_name="tenantmarkup",
            constraint=models.UniqueConstraint(
                fields=["tenant"], condition=models.Q(customer__isnull=True),
                name="uq_markup_tenant_default"),
        ),
        migrations.AddConstraint(
            model_name="tenantmarkup",
            constraint=models.UniqueConstraint(
                fields=["tenant", "customer"], condition=models.Q(customer__isnull=False),
                name="uq_markup_tenant_customer"),
        ),
    ]
```
> Verify the `customers` migration dependency name with `git ls-files apps/platform/customers/migrations` and use the actual head. `RemoveIndex`/`RemoveField` names must match `pricing/migrations/0001`+`0004`; confirm before writing.

- [ ] **Step 6 — Admin** `apps/metering/pricing/admin.py`: update `TenantMarkupAdmin.list_display`/`list_filter`/`search_fields` to drop `event_type`/`provider`/`valid_from`/`valid_to`, e.g. `list_display = ("tenant", "customer", "markup_percentage_micros", "fixed_uplift_micros")`, `list_filter = ()`, `search_fields = ("tenant__name",)`.
- [ ] **Step 7 — Endpoints** `api/v1/metering_endpoints.py`: replace the five markup endpoints + `_markup_to_out` with:
  - `GET /pricing/markup` → return the tenant default markup (or `{percentage_micros:0, fixed_uplift_micros:0}` if none).
  - `PUT /pricing/markup` → upsert the tenant default (`customer=None`).
  - `GET /pricing/customers/{customer_id}/markup` → the customer override (fall back to tenant default).
  - `PUT /pricing/customers/{customer_id}/markup` → upsert the override.
  Use `update_or_create(tenant=..., customer=...)`. Response shape `TenantMarkupOut` (Step 8). (No more version-on-PUT; this is a simple upsert.)
- [ ] **Step 8 — Schemas** `api/v1/schemas.py`: replace `TenantMarkupIn`/`TenantMarkupOut`:
```python
class TenantMarkupIn(Schema):
    markup_percentage_micros: int = Field(default=0, ge=0)
    fixed_uplift_micros: int = Field(default=0, ge=0)

class TenantMarkupOut(Schema):
    markup_percentage_micros: int
    fixed_uplift_micros: int
```
- [ ] **Step 9 — Tests**: in `apps/metering/pricing/tests/test_models.py` update `TenantMarkupTests` to drop `event_type=` kwargs (they're gone). In `api/v1/tests/test_metering_endpoints.py` rewrite `PricingMarkupsCRUDTest` to hit `GET/PUT /pricing/markup` (no `event_type`/`provider`, no versioning, no `valid_to`).
- [ ] **Step 10 — Verify**: `check` ok; `makemigrations --check` → "No changes detected"; `--collect-only` clean. **With DB:** `$DJ -m pytest apps/metering/pricing api/v1/tests/test_metering_endpoints.py -q` → green.
- [ ] **Step 11 — Commit**: `git add -A && git commit -m "refactor(pricing): slim TenantMarkup to per-tenant/customer markup + MarkupService"`

---

### Task 3: `UsageEvent` additive fields (`currency`, `units`, `product_id`)

Additive only — keeps `cost_micros`/`group_keys` for now.

**Files:** Modify `apps/metering/usage/models.py`; Create `apps/metering/usage/migrations/0016_usageevent_currency_units_product.py`; Test `apps/metering/usage/tests/test_models.py`.

- [ ] **Step 1 — Failing test** (add to usage `test_models.py`): create a `UsageEvent` and assert `currency == "usd"`, `units is None`, `product_id == ""` defaults.
- [ ] **Step 2 — Add fields** on `UsageEvent` (after `provider`):
```python
    units = models.BigIntegerField(null=True, blank=True)
    currency = models.CharField(max_length=3, default="usd")
    product_id = models.CharField(max_length=100, blank=True, default="", db_index=True)
```
- [ ] **Step 3 — Migration** `0016_...` `AddField` × 3 (`units` nullable; `currency` default "usd"; `product_id` default "" + db_index). Dependency `("usage", "0015_add_tenant_effective_index")`.
- [ ] **Step 4 — Verify** static + (DB) migrate. **Commit**: `feat(metering): add currency/units/product_id to UsageEvent`.

---

### Task 4: Rename `group_keys` → `tags` (incl. GIN index)

**Files:** Modify `apps/metering/usage/models.py`, `apps/metering/usage/services/usage_service.py`, `api/v1/metering_endpoints.py`, `api/v1/schemas.py`; Create `apps/metering/usage/migrations/0017_rename_group_keys_to_tags.py`; Rename test file `test_group_keys.py`→`test_tags.py`; Modify SDK `ubb-sdk/ubb/metering.py`.

- [ ] **Step 1 — Model**: rename the field `group_keys` → `tags` (same `JSONField(null=True, blank=True)`).
- [ ] **Step 2 — Service** `usage_service.py`: rename `validate_group_keys`→`validate_tags`, parameter `group_keys`→`tags`, error messages "group_keys"→"tags", **raise the cap `> 10` to `> 50`**, and the `create(... tags=tags)`. Keep the key regex and value rules.
- [ ] **Step 3 — Endpoint** `metering_endpoints.py`: `record_usage` passes `tags=payload.tags`; `get_usage` query params `group_key`/`group_value` → `tag_key`/`tag_value`, filter `tags__contains={tag_key: tag_value}`.
- [ ] **Step 4 — Schema** `schemas.py`: `RecordUsageRequest.group_keys` → `tags: Optional[dict[str, str]] = None`.
- [ ] **Step 5 — Migration** `0017_rename_group_keys_to_tags.py`:
```python
from django.db import connection, migrations


def swap_gin_index(apps, schema_editor):
    if connection.vendor == "postgresql":
        schema_editor.execute("DROP INDEX IF EXISTS idx_usage_event_group_keys;")
        schema_editor.execute(
            "CREATE INDEX IF NOT EXISTS idx_usage_event_tags "
            "ON ubb_usage_event USING GIN (tags jsonb_path_ops);"
        )


def unswap_gin_index(apps, schema_editor):
    if connection.vendor == "postgresql":
        schema_editor.execute("DROP INDEX IF EXISTS idx_usage_event_tags;")
        schema_editor.execute(
            "CREATE INDEX IF NOT EXISTS idx_usage_event_group_keys "
            "ON ubb_usage_event USING GIN (group_keys jsonb_path_ops);"
        )


class Migration(migrations.Migration):
    dependencies = [("usage", "0016_usageevent_currency_units_product")]
    operations = [
        migrations.RenameField(model_name="usageevent", old_name="group_keys", new_name="tags"),
        migrations.RunPython(swap_gin_index, unswap_gin_index),
    ]
```
- [ ] **Step 6 — Tests**: `git mv apps/metering/usage/tests/test_group_keys.py apps/metering/usage/tests/test_tags.py`; replace `group_keys`→`tags` throughout; rename the `test_group_keys_max_10_keys` test to assert the 50-key cap (build a 51-key dict, expect `ValueError`); endpoint test query param `group_key`→`tag_key`, `group_value`→`tag_value`.
- [ ] **Step 7 — SDK** `ubb-sdk/ubb/metering.py`: `record_usage` param `group_keys`→`tags` (body key `tags`); `get_usage` params `group_key`/`group_value`→`tag_key`/`tag_value`.
- [ ] **Step 8 — Verify**: `check`; `makemigrations --check` → "No changes detected"; `--collect-only` clean; `git grep -n group_keys -- apps api ':!*/migrations/*'` → none. **With DB:** run `apps/metering/usage` tests green (incl. the GIN-filtered `test_usage_filter_by_tag`). **Commit**: `refactor(metering): rename group_keys to tags (cap 50, GIN index swap)`.

---

### Task 5: New `record_usage` contract + collapse the cost model

The coordinated destructive change. **DB validation required.**

**Files:** Modify `apps/metering/usage/models.py`, `apps/metering/usage/services/usage_service.py`, `api/v1/schemas.py`, `api/v1/metering_endpoints.py`, `apps/metering/queries.py`, `apps/referrals/rewards/reconciliation.py`; Create `apps/metering/usage/migrations/0018_collapse_cost_model.py`; Modify the usage/endpoint test files (bulk cost_micros→provider/billed).

- [ ] **Step 1 — Model**: make `provider_cost_micros = models.BigIntegerField(default=0)` and `billed_cost_micros = models.BigIntegerField(default=0)` (both non-null). Remove `cost_micros`, `usage_metrics`, `properties`.
- [ ] **Step 2 — Migration** `0018_collapse_cost_model.py`: backfill then drop. Author by hand:
```python
from django.db import migrations, models


def backfill(apps, schema_editor):
    UsageEvent = apps.get_model("usage", "UsageEvent")
    UsageEvent.objects.filter(provider_cost_micros__isnull=True).update(provider_cost_micros=0)
    # billed: prefer existing billed, else the legacy cost_micros
    from django.db.models import F
    UsageEvent.objects.filter(billed_cost_micros__isnull=True).update(billed_cost_micros=F("cost_micros"))


class Migration(migrations.Migration):
    dependencies = [("usage", "0017_rename_group_keys_to_tags")]
    operations = [
        migrations.RunPython(backfill, migrations.RunPython.noop),
        migrations.AlterField(model_name="usageevent", name="provider_cost_micros",
                              field=models.BigIntegerField(default=0)),
        migrations.AlterField(model_name="usageevent", name="billed_cost_micros",
                              field=models.BigIntegerField(default=0)),
        migrations.RemoveField(model_name="usageevent", name="cost_micros"),
        migrations.RemoveField(model_name="usageevent", name="usage_metrics"),
        migrations.RemoveField(model_name="usageevent", name="properties"),
    ]
```
- [ ] **Step 3 — Service** `usage_service.py` new signature + body:
```python
@staticmethod
@transaction.atomic
def record_usage(tenant, customer, request_id, idempotency_key, *,
                 provider_cost_micros, billed_cost_micros=None, units=None,
                 provider="", event_type="", currency=None, tags=None,
                 product_id="", metadata=None, run_id=None):
    validate_tags(tags)
    existing = UsageEvent.objects.filter(
        tenant=tenant, customer=customer, idempotency_key=idempotency_key).first()
    if existing:
        return _result(existing, run_total=None)
    from apps.metering.pricing.services.markup_service import MarkupService
    if billed_cost_micros is None:
        billed_cost_micros = MarkupService.apply(provider_cost_micros, tenant=tenant, customer=customer)
    run = None
    if run_id is not None:
        from apps.platform.runs.services import RunService
        run = RunService.accumulate_cost(run_id, billed_cost_micros)
    try:
        with transaction.atomic():
            event = UsageEvent.objects.create(
                tenant=tenant, customer=customer, request_id=request_id,
                idempotency_key=idempotency_key, metadata=metadata or {},
                event_type=event_type or "", provider=provider or "",
                provider_cost_micros=provider_cost_micros,
                billed_cost_micros=billed_cost_micros,
                units=units, currency=currency or tenant.default_currency,
                product_id=product_id or "", tags=tags, run_id=run_id)
    except IntegrityError:
        existing = UsageEvent.objects.get(
            tenant=tenant, customer=customer, idempotency_key=idempotency_key)
        return _result(existing, run_total=None)
    write_event(UsageRecorded(
        tenant_id=str(tenant.id), customer_id=str(customer.id), event_id=str(event.id),
        cost_micros=billed_cost_micros, provider_cost_micros=provider_cost_micros,
        billed_cost_micros=billed_cost_micros, event_type=event_type or "",
        provider=provider or "", run_id=str(run_id) if run_id else None))
    return _result(event, run_total=run.total_cost_micros if run else None)
```
  Add a module-level helper:
```python
def _result(event, run_total):
    return {
        "event_id": str(event.id),
        "provider_cost_micros": event.provider_cost_micros,
        "billed_cost_micros": event.billed_cost_micros,
        "units": event.units,
        "new_balance_micros": None, "suspended": False,
        "run_id": str(event.run_id) if event.run_id else None,
        "run_total_cost_micros": run_total, "hard_stop": False,
    }
```
- [ ] **Step 3b — Validation** rename in service is already done in Task 4 (`validate_tags`). Keep `pricing_provenance` off the model (it stays a column — NOT removed this stage; leave as-is). *(Note: `pricing_provenance` column remains; it is simply written as `{}`/unset. Do not pass it.)*
- [ ] **Step 4 — Schema** `schemas.py`:
```python
class RecordUsageRequest(Schema):
    customer_id: UUID
    request_id: str = Field(min_length=1, max_length=500)
    idempotency_key: str = Field(min_length=1, max_length=500)
    metadata: dict = Field(default_factory=dict)
    provider_cost_micros: int = Field(ge=0, le=999_999_999_999)
    billed_cost_micros: Optional[int] = Field(default=None, ge=0, le=999_999_999_999)
    units: Optional[int] = Field(default=None, ge=0)
    currency: Optional[str] = Field(default=None, max_length=3)
    tags: Optional[dict[str, str]] = None
    run_id: Optional[UUID] = None
    event_type: Optional[str] = Field(default=None, max_length=100)
    provider: Optional[str] = Field(default=None, max_length=100)
    product_id: Optional[str] = Field(default=None, max_length=100)
```
  `RecordUsageResponse`: add `units: Optional[int] = None`. `UsageEventOut`: replace `cost_micros: int` with `provider_cost_micros: Optional[int] = None` + `billed_cost_micros: Optional[int] = None` + `units: Optional[int] = None`.
- [ ] **Step 5 — Endpoint** `record_usage`: pass the new params (`provider_cost_micros=payload.provider_cost_micros`, `billed_cost_micros=payload.billed_cost_micros`, `units=payload.units`, `currency=payload.currency`, `tags=payload.tags`, `product_id=payload.product_id`, plus existing). `get_usage` serializer: emit `provider_cost_micros`/`billed_cost_micros`/`units` instead of `cost_micros`.
- [ ] **Step 6 — `queries.py`**: in all three functions replace `Coalesce("billed_cost_micros", "cost_micros")` with `"billed_cost_micros"`; in `get_customer_usage_for_period` drop `"cost_micros"` from `.values(...)` and fix the filter `created_at` → `effective_at`.
- [ ] **Step 7 — referrals** `apps/referrals/rewards/reconciliation.py:35`: change `cost = event.get("billed_cost_micros") or event.get("cost_micros") or 0` → `cost = event.get("billed_cost_micros") or 0`.
- [ ] **Step 8 — Tests (bulk transform)**: across `apps/metering/usage/tests/*.py` and `api/v1/tests/test_metering_endpoints.py` and `apps/metering/usage/tests/test_tags.py`: replace each `cost_micros=N` kwarg in `record_usage(...)` calls and each `"cost_micros": N` JSON body key with `provider_cost_micros=N` / `"provider_cost_micros": N`. Replace assertions on `event.cost_micros` with `event.billed_cost_micros`, and response `body["total_billed_cost_micros"]` expectations remain valid. Update `test_decoupled_usage.py`, `test_outbox_integration.py`, usage `test_models.py` similarly. Run `--collect-only` and `git grep -n "cost_micros" -- apps/metering api ':!*/migrations/*'` to confirm only `provider_cost_micros`/`billed_cost_micros` remain.
- [ ] **Step 9 — Verify**: `check`; `makemigrations --check` → "No changes detected"; `--collect-only` clean. **With DB (required):** `$DJ manage.py migrate`; `$DJ -m pytest apps/metering api/v1 apps/referrals -q` → green.
- [ ] **Step 10 — Commit**: `git add -A && git commit -m "feat(metering): caller-provided provider_cost + markup-derived billed cost; collapse cost model"`

---

### Task 6: Dimensional analytics API

**Files:** Modify `api/v1/metering_endpoints.py` (`usage_analytics`), `api/v1/schemas.py` (`UsageAnalyticsResponse`); Test `api/v1/tests/test_metering_endpoints.py` (`MeteringUsageAnalyticsEndpointTest`).

- [ ] **Step 1 — Failing test**: record 3 events with `tags={"model": ...}`/`product_id`/distinct customers; assert the analytics response contains `usage_markup_margin_micros` and non-empty `by_customer`, `by_product`, and `by_tag` (when `?tag_key=model`).
- [ ] **Step 2 — Schema** `UsageAnalyticsResponse`: add `usage_markup_margin_micros: int`, `by_customer: list[dict]`, `by_product: list[dict]`, `by_tag: list[dict]`.
- [ ] **Step 3 — Endpoint**: extend `usage_analytics(request, start_date=None, end_date=None, customer_id=None, tag_key=None)`. Totals add `usage_markup_margin_micros = total_billed - total_provider`. Add `by_customer` (`values("customer__external_id")`), `by_product` (`exclude(product_id="").values("product_id")`), and when `tag_key` given, `by_tag` via `annotate(tag_val=...)`—group by the JSON key using `tags__<key>`? Postgres JSON key lookups: filter rows with `tags__has_key=tag_key`, then aggregate in Python by `e.tags.get(tag_key)` over an iterator, OR use `.annotate(tag_val=RawSQL("tags ->> %s", (tag_key,)))` then `.values("tag_val")`. Use the `RawSQL` approach; cost columns are `provider_cost_micros`/`billed_cost_micros`.
- [ ] **Step 4 — Verify** static + (DB) the new test green. **Commit**: `feat(metering): dimensional usage analytics (customer/product/tag + markup margin)`.

---

### Task 7: SDK metering client + types

**Files:** Modify `ubb-sdk/ubb/metering.py`, `ubb-sdk/ubb/types.py`, `ubb-sdk/ubb/client.py`; Tests `ubb-sdk/tests/test_metering_client.py`, `ubb-sdk/tests/test_client.py`, `ubb-sdk/tests/test_orchestration.py`.

- [ ] **Step 1 — `types.py`**: `RecordUsageResult` — add `units: int | None = None`; keep `provider_cost_micros`/`billed_cost_micros`; `new_balance_micros` becomes `int | None = None`. `UsageEvent` — replace `cost_micros: int` with `provider_cost_micros: int | None = None`, `billed_cost_micros: int | None = None`, `units: int | None = None`.
- [ ] **Step 2 — `metering.py` `record_usage`**: new signature `record_usage(customer_id, request_id, idempotency_key, *, provider_cost_micros, billed_cost_micros=None, units=None, provider="", event_type="", currency=None, tags=None, product_id="", metadata=None, run_id=None)`. Build body with `provider_cost_micros` always; include `billed_cost_micros`/`units`/`currency`/`tags`/`product_id`/`event_type`/`provider`/`run_id` when set. Remove the `usage_metrics`/`properties` branch. `get_usage` params `tag_key`/`tag_value` (done in Task 4 Step 7 — confirm).
- [ ] **Step 3 — `client.py`**: update `UBBClient.record_usage(...)` to thread the new params to `self.metering.record_usage(...)` (read the current method and mirror the new signature; drop `usage_metrics`).
- [ ] **Step 4 — SDK tests**: update mocked request bodies/results to the new contract. The SDK suite runs without a DB: `cd ubb-sdk && python -m pytest -q`.
- [ ] **Step 5 — Commit**: `feat(sdk): metering record_usage caller-cost contract + tags`.

---

### Task 8: Final verification

- [ ] `$DJ manage.py check` → no issues.
- [ ] `$DJ manage.py makemigrations --check` → "No changes detected".
- [ ] `$DJ -m pytest --collect-only -q` → clean (no import errors).
- [ ] `git grep -nE "cost_micros[^_a-z]|group_keys|usage_metrics|properties=" -- apps/metering api ':!*/migrations/*'` → only `provider_cost_micros`/`billed_cost_micros`/`tags`; no bare `cost_micros`, no `group_keys`.
- [ ] **With DB (REQUIRED before trusting this stage):** `$DJ manage.py migrate` from a fresh DB applies `usage/0016..0018`, `pricing/0006`, `tenants/0009` cleanly; `$DJ -m pytest -q` whole suite green; `cd ubb-sdk && python -m pytest -q` green.

---

## Self-Review

**Spec coverage (vs. Stage 1 design):** collapse cost model (T5) ✓; `currency`/`units`/`product_id` (T3) ✓; `group_keys`→`tags` + cap 50 + GIN (T4) ✓; caller `provider_cost` + markup-derived billed + override (T5) ✓; slim per-tenant/customer markup + service (T2) ✓; queries/analytics on new model (T5/T6) ✓; dimensional analytics customer/product/tag + markup margin (T6) ✓; SDK (T7) ✓; idempotency preserved (T5 fast-path + IntegrityError) ✓; `Tenant.default_currency` (T1) ✓; run hard-stop now on billed (T5) ✓.

**Placeholder scan:** Migration dependency names for `customers` (T2) and confirmation of `pricing` index/field names are called out as "verify before writing" — these are verification instructions, not placeholders. The Task-5 bulk test transform is specified as an exact rule + file list (a deterministic mechanical edit), not a vague "update tests".

**Type/name consistency:** `MarkupService.apply(provider_cost_micros, tenant, customer)` signature identical in T2 def and T5 call. `tags` field/param/SDK consistent across T4/T5/T7. `_result(event, run_total)` helper defined and used consistently in T5. Response/`UsageEventOut` fields (`provider_cost_micros`/`billed_cost_micros`/`units`) consistent across schema, endpoint serializer, and SDK types.

**Migration risk:** flagged at top and per destructive task; T5/T4/T2 require `migrate` + `pytest` on Postgres before trust.
