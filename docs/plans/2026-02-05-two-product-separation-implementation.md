# Two-Product Separation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Split UBB into two independent products — Usage Metering and Billing & Payments — that can be sold separately or together, with a shared Platform layer and an Event Bus for async side effects.

**Architecture:** Single Django deployment with three code domains (`platform/`, `metering/`, `billing/`) under `apps/`. Products never import from each other. Both import from `platform/` (shared tenants/customers). An `EventBus` singleton handles async side effects. The SDK orchestrates multi-product flows client-side. A `products` ArrayField on Tenant controls API access via `ProductAccess` auth.

**Tech Stack:** Django 6.0, django-ninja, Celery, Redis, Stripe, PostgreSQL (via dj-database-url), pytest, factory-boy

**Design doc:** `docs/plans/2026-02-05-two-product-separation-design.md`

---

## Phase 1: Restructure Directories (no logic changes)

> Move files into `platform/`, `metering/`, `billing/` structure. Update all imports. Zero behaviour change — just file moves and import rewrites.

### Task 1: Create the new app directories and `__init__.py` files

**Files:**
- Create: `apps/platform/__init__.py`
- Create: `apps/platform/tenants/__init__.py`
- Create: `apps/platform/customers/__init__.py`
- Create: `apps/metering/__init__.py`
- Create: `apps/metering/usage/__init__.py`
- Create: `apps/metering/pricing/__init__.py`
- Create: `apps/billing/__init__.py`
- Create: `apps/billing/wallets/__init__.py`
- Create: `apps/billing/topups/__init__.py`
- Create: `apps/billing/stripe/__init__.py`
- Create: `apps/billing/invoicing/__init__.py`
- Create: `apps/billing/tenant_billing/__init__.py`
- Create: `apps/billing/gating/__init__.py`

**Step 1: Create all directories with `__init__.py`**

```bash
mkdir -p apps/platform/tenants apps/platform/customers
mkdir -p apps/metering/usage apps/metering/pricing
mkdir -p apps/billing/wallets apps/billing/topups apps/billing/stripe apps/billing/invoicing apps/billing/tenant_billing apps/billing/gating

touch apps/platform/__init__.py apps/platform/tenants/__init__.py apps/platform/customers/__init__.py
touch apps/metering/__init__.py apps/metering/usage/__init__.py apps/metering/pricing/__init__.py
touch apps/billing/__init__.py apps/billing/wallets/__init__.py apps/billing/topups/__init__.py apps/billing/stripe/__init__.py apps/billing/invoicing/__init__.py apps/billing/tenant_billing/__init__.py apps/billing/gating/__init__.py
```

**Step 2: Commit**

```bash
git add apps/platform apps/metering apps/billing
git commit -m "chore: create product directory skeleton (platform, metering, billing)"
```

---

### Task 2: Move Platform — Tenants

Move `apps/tenants/` → `apps/platform/tenants/`. This is the Tenant and TenantApiKey models plus the apps.py config.

**Files:**
- Move: `apps/tenants/models.py` → `apps/platform/tenants/models.py`
- Move: `apps/tenants/apps.py` → `apps/platform/tenants/apps.py`
- Move: `apps/tenants/admin.py` → `apps/platform/tenants/admin.py` (if exists)
- Move: `apps/tenants/migrations/` → `apps/platform/tenants/migrations/`
- Modify: `apps/platform/tenants/apps.py` — update `name` to `"apps.platform.tenants"`
- Modify: `config/settings.py` — update `INSTALLED_APPS` entry
- Modify: Every file that imports from `apps.tenants` — update to `apps.platform.tenants`

**Step 1: Move the files**

```bash
cp -r apps/tenants/models.py apps/platform/tenants/models.py
cp -r apps/tenants/apps.py apps/platform/tenants/apps.py
cp -r apps/tenants/migrations apps/platform/tenants/migrations
# Copy admin.py if it exists
cp apps/tenants/admin.py apps/platform/tenants/admin.py 2>/dev/null || true
```

**Step 2: Update `apps/platform/tenants/apps.py`**

Change `name` from `"apps.tenants"` to `"apps.platform.tenants"`:

```python
from django.apps import AppConfig

class TenantsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.platform.tenants"
    label = "tenants"  # Keep same DB table prefix — avoids migration
```

> **CRITICAL:** Set `label = "tenants"` so Django keeps the existing DB table names (`tenants_tenant`, `tenants_tenantapikey`). Without this, Django will try to create new tables.

**Step 3: Update all migrations**

In every migration file under `apps/platform/tenants/migrations/`, update the `dependencies` list if any reference `("tenants", ...)` — these stay as `("tenants", ...)` because we kept `label = "tenants"`.

No changes needed to migration `dependencies` since the label is preserved.

**Step 4: Update `config/settings.py`**

Replace `"apps.tenants"` with `"apps.platform.tenants"` in `INSTALLED_APPS`.

**Step 5: Find and update all imports**

Search the entire codebase for `apps.tenants` and replace with `apps.platform.tenants`. Key files:
- `core/auth.py` — imports `TenantApiKey`
- `core/widget_auth.py` — imports `Tenant`
- `apps/customers/models.py` — FK to `Tenant`
- `apps/usage/models.py` — FK to `Tenant`
- `apps/pricing/models.py` — FK to `Tenant`
- `apps/tenant_billing/models.py` — FK to `Tenant`
- `apps/gating/models.py` — FK to `Tenant`
- `api/v1/endpoints.py`
- `api/v1/tenant_endpoints.py`
- Test files

**Step 6: Remove old `apps/tenants/` directory**

```bash
rm -rf apps/tenants
```

**Step 7: Run tests to verify zero behaviour change**

```bash
cd ubb-platform && python -m pytest --tb=short -q
```
Expected: All tests pass. No migration changes detected.

**Step 8: Verify no new migrations needed**

```bash
python manage.py makemigrations --check --dry-run
```
Expected: "No changes detected"

**Step 9: Commit**

```bash
git add -A
git commit -m "refactor: move tenants app to apps/platform/tenants"
```

---

### Task 3: Move Platform — Customers (identity only)

Move `apps/customers/` → `apps/platform/customers/`. For now, move the **entire** customers app (Customer, Wallet, WalletTransaction, AutoTopUpConfig, TopUpAttempt) to platform. In Phase 1, we only move files. The wallet/topup models will be extracted to `billing/` in a later task.

**Why move everything first?** Moving the whole app preserves all FK relationships and migration history. Splitting models across apps requires careful migration surgery — that's a separate task.

**Files:**
- Move: All files from `apps/customers/` → `apps/platform/customers/`
- Modify: `apps/platform/customers/apps.py` — update `name`, keep `label = "customers"`
- Modify: `config/settings.py` — update `INSTALLED_APPS`
- Modify: All files importing from `apps.customers`

**Step 1: Move the files**

```bash
cp -r apps/customers/* apps/platform/customers/
# Ensure migrations directory is copied
cp -r apps/customers/migrations apps/platform/customers/migrations
```

**Step 2: Update `apps/platform/customers/apps.py`**

```python
from django.apps import AppConfig

class CustomersConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.platform.customers"
    label = "customers"  # Keep same DB table prefix
```

**Step 3: Update `config/settings.py`**

Replace `"apps.customers"` with `"apps.platform.customers"`.

**Step 4: Find and update all imports**

Search for `apps.customers` → `apps.platform.customers`. Key files:
- `apps/usage/services/usage_service.py`
- `apps/usage/services/auto_topup_service.py`
- `apps/usage/models.py`
- `apps/stripe_integration/services/stripe_service.py`
- `apps/invoicing/services.py`
- `apps/gating/services/risk_service.py`
- `api/v1/endpoints.py`
- `api/v1/me_endpoints.py`
- `api/v1/webhooks.py`
- `core/locking.py`
- All test files referencing customers

**Step 5: Remove old directory**

```bash
rm -rf apps/customers
```

**Step 6: Run tests**

```bash
cd ubb-platform && python -m pytest --tb=short -q
```
Expected: All tests pass.

**Step 7: Verify no new migrations**

```bash
python manage.py makemigrations --check --dry-run
```

**Step 8: Commit**

```bash
git add -A
git commit -m "refactor: move customers app to apps/platform/customers"
```

---

### Task 4: Move Metering — Usage

Move `apps/usage/` → `apps/metering/usage/`.

**Files:**
- Move: All files from `apps/usage/` → `apps/metering/usage/`
- Modify: `apps/metering/usage/apps.py` — update `name`, keep `label = "usage"`
- Modify: `config/settings.py`
- Modify: All files importing from `apps.usage`

**Step 1: Move the files**

```bash
cp -r apps/usage/* apps/metering/usage/
cp -r apps/usage/migrations apps/metering/usage/migrations
```

**Step 2: Update `apps/metering/usage/apps.py`**

```python
from django.apps import AppConfig

class UsageConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.metering.usage"
    label = "usage"
```

**Step 3: Update `config/settings.py`**

Replace `"apps.usage"` with `"apps.metering.usage"`.

**Step 4: Find and update all imports**

Search for `apps.usage` → `apps.metering.usage`. Key files:
- `api/v1/endpoints.py`
- `api/v1/webhooks.py`
- `apps/tenant_billing/services.py` (queries UsageEvent)
- `apps/invoicing/services.py`
- Test files

**Step 5: Remove old directory**

```bash
rm -rf apps/usage
```

**Step 6: Run tests**

```bash
cd ubb-platform && python -m pytest --tb=short -q
```

**Step 7: Verify no new migrations**

```bash
python manage.py makemigrations --check --dry-run
```

**Step 8: Commit**

```bash
git add -A
git commit -m "refactor: move usage app to apps/metering/usage"
```

---

### Task 5: Move Metering — Pricing

Move `apps/pricing/` → `apps/metering/pricing/`.

**Files:**
- Move: All files from `apps/pricing/` → `apps/metering/pricing/`
- Modify: `apps/metering/pricing/apps.py` — update `name`, keep `label = "pricing"`
- Modify: `config/settings.py`
- Modify: All files importing from `apps.pricing`

**Step 1: Move the files**

```bash
cp -r apps/pricing/* apps/metering/pricing/
cp -r apps/pricing/migrations apps/metering/pricing/migrations
```

**Step 2: Update `apps/metering/pricing/apps.py`**

```python
from django.apps import AppConfig

class PricingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.metering.pricing"
    label = "pricing"
```

**Step 3: Update `config/settings.py`**

Replace `"apps.pricing"` with `"apps.metering.pricing"`.

**Step 4: Find and update all imports**

Search for `apps.pricing` → `apps.metering.pricing`. Key files:
- `apps/metering/usage/services/usage_service.py` (calls PricingService)
- Test files

**Step 5: Remove old directory**

```bash
rm -rf apps/pricing
```

**Step 6: Run tests**

```bash
cd ubb-platform && python -m pytest --tb=short -q
```

**Step 7: Verify no new migrations**

```bash
python manage.py makemigrations --check --dry-run
```

**Step 8: Commit**

```bash
git add -A
git commit -m "refactor: move pricing app to apps/metering/pricing"
```

---

### Task 6: Move Billing — Stripe Integration

Move `apps/stripe_integration/` → `apps/billing/stripe/`.

**Files:**
- Move: All files from `apps/stripe_integration/` → `apps/billing/stripe/`
- Modify: `apps/billing/stripe/apps.py` — update `name`, keep `label = "stripe_integration"`
- Modify: `config/settings.py`
- Modify: All files importing from `apps.stripe_integration`

**Step 1: Move the files**

```bash
cp -r apps/stripe_integration/* apps/billing/stripe/
cp -r apps/stripe_integration/migrations apps/billing/stripe/migrations
```

**Step 2: Update `apps/billing/stripe/apps.py`**

```python
from django.apps import AppConfig

class StripeIntegrationConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.billing.stripe"
    label = "stripe_integration"  # Keep DB table prefix
```

**Step 3: Update `config/settings.py`**

Replace `"apps.stripe_integration"` with `"apps.billing.stripe"`.

**Step 4: Find and update all imports**

Search for `apps.stripe_integration` → `apps.billing.stripe`. Key files:
- `api/v1/endpoints.py`
- `api/v1/webhooks.py`
- Test files

**Step 5: Remove old directory**

```bash
rm -rf apps/stripe_integration
```

**Step 6: Run tests**

```bash
cd ubb-platform && python -m pytest --tb=short -q
```

**Step 7: Verify no new migrations**

```bash
python manage.py makemigrations --check --dry-run
```

**Step 8: Commit**

```bash
git add -A
git commit -m "refactor: move stripe_integration app to apps/billing/stripe"
```

---

### Task 7: Move Billing — Gating

Move `apps/gating/` → `apps/billing/gating/`.

**Files:**
- Move: All files from `apps/gating/` → `apps/billing/gating/`
- Modify: `apps/billing/gating/apps.py` — update `name`, keep `label = "gating"`
- Modify: `config/settings.py`
- Modify: All files importing from `apps.gating`

**Step 1: Move the files**

```bash
cp -r apps/gating/* apps/billing/gating/
cp -r apps/gating/migrations apps/billing/gating/migrations
```

**Step 2: Update `apps/billing/gating/apps.py`**

```python
from django.apps import AppConfig

class GatingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.billing.gating"
    label = "gating"
```

**Step 3: Update `config/settings.py`**

Replace `"apps.gating"` with `"apps.billing.gating"`.

**Step 4: Find and update all imports**

Search for `apps.gating` → `apps.billing.gating`. Key files:
- `api/v1/endpoints.py` (RiskService.check)
- Test files

**Step 5: Remove old directory**

```bash
rm -rf apps/gating
```

**Step 6: Run tests**

```bash
cd ubb-platform && python -m pytest --tb=short -q
```

**Step 7: Verify no new migrations**

```bash
python manage.py makemigrations --check --dry-run
```

**Step 8: Commit**

```bash
git add -A
git commit -m "refactor: move gating app to apps/billing/gating"
```

---

### Task 8: Move Billing — Invoicing

Move `apps/invoicing/` → `apps/billing/invoicing/`.

**Files:**
- Move: All files from `apps/invoicing/` → `apps/billing/invoicing/`
- Modify: `apps/billing/invoicing/apps.py` — update `name`, keep `label = "invoicing"`
- Modify: `config/settings.py`
- Modify: All files importing from `apps.invoicing`

**Step 1: Move the files**

```bash
cp -r apps/invoicing/* apps/billing/invoicing/
cp -r apps/invoicing/migrations apps/billing/invoicing/migrations
```

**Step 2: Update `apps/billing/invoicing/apps.py`**

```python
from django.apps import AppConfig

class InvoicingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.billing.invoicing"
    label = "invoicing"
```

**Step 3: Update `config/settings.py`**

Replace `"apps.invoicing"` with `"apps.billing.invoicing"`.

**Step 4: Find and update all imports**

Search for `apps.invoicing` → `apps.billing.invoicing`. Key files:
- `api/v1/webhooks.py`
- Test files

**Step 5: Remove old directory**

```bash
rm -rf apps/invoicing
```

**Step 6: Run tests**

```bash
cd ubb-platform && python -m pytest --tb=short -q
```

**Step 7: Verify no new migrations**

```bash
python manage.py makemigrations --check --dry-run
```

**Step 8: Commit**

```bash
git add -A
git commit -m "refactor: move invoicing app to apps/billing/invoicing"
```

---

### Task 9: Move Billing — Tenant Billing

Move `apps/tenant_billing/` → `apps/billing/tenant_billing/`.

**Files:**
- Move: All files from `apps/tenant_billing/` → `apps/billing/tenant_billing/`
- Modify: `apps/billing/tenant_billing/apps.py` — update `name`, keep `label = "tenant_billing"`
- Modify: `config/settings.py`
- Modify: All files importing from `apps.tenant_billing`

**Step 1: Move the files**

```bash
cp -r apps/tenant_billing/* apps/billing/tenant_billing/
cp -r apps/tenant_billing/migrations apps/billing/tenant_billing/migrations
```

**Step 2: Update `apps/billing/tenant_billing/apps.py`**

```python
from django.apps import AppConfig

class TenantBillingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.billing.tenant_billing"
    label = "tenant_billing"
```

**Step 3: Update `config/settings.py`**

Replace `"apps.tenant_billing"` with `"apps.billing.tenant_billing"`.

**Step 4: Find and update all imports**

Search for `apps.tenant_billing` → `apps.billing.tenant_billing`. Key files:
- `apps/metering/usage/services/usage_service.py` (accumulate_usage call — this cross-product import will be removed in Phase 2)
- `api/v1/tenant_endpoints.py`
- Test files

**Step 5: Remove old directory**

```bash
rm -rf apps/tenant_billing
```

**Step 6: Run tests**

```bash
cd ubb-platform && python -m pytest --tb=short -q
```

**Step 7: Verify no new migrations**

```bash
python manage.py makemigrations --check --dry-run
```

**Step 8: Commit**

```bash
git add -A
git commit -m "refactor: move tenant_billing app to apps/billing/tenant_billing"
```

---

### Task 10: Update `INSTALLED_APPS` final verification and clean up empty directories

**Files:**
- Modify: `config/settings.py` — verify final `INSTALLED_APPS` list

**Step 1: Verify `config/settings.py` INSTALLED_APPS looks like this**

```python
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "corsheaders",
    # Platform (always installed, shared)
    "apps.platform.tenants",
    "apps.platform.customers",
    # Metering
    "apps.metering.usage",
    "apps.metering.pricing",
    # Billing
    "apps.billing.stripe",
    "apps.billing.gating",
    "apps.billing.invoicing",
    "apps.billing.tenant_billing",
]
```

**Step 2: Clean up any remaining empty old directories**

```bash
# Remove any leftover empty directories from old app structure
rmdir apps/tenants apps/customers apps/usage apps/pricing apps/stripe_integration apps/gating apps/invoicing apps/tenant_billing 2>/dev/null || true
```

**Step 3: Run full test suite**

```bash
cd ubb-platform && python -m pytest --tb=short -q
```
Expected: All tests pass.

**Step 4: Run Django check**

```bash
python manage.py check
python manage.py makemigrations --check --dry-run
```
Expected: "System check identified no issues." and "No changes detected."

**Step 5: Commit**

```bash
git add -A
git commit -m "refactor: finalize Phase 1 directory restructure — verify all apps relocated"
```

---

## Phase 2: Introduce the Event Bus

> Add `core/event_bus.py`. Add `usage.recorded` event emission. Move tenant billing accumulation from direct call to event handler. Critical path (wallet debit) stays as direct calls.

### Task 11: Write failing test for EventBus

**Files:**
- Create: `core/tests/test_event_bus.py`

**Step 1: Write the failing test**

```python
# core/tests/test_event_bus.py
import pytest
from unittest.mock import MagicMock, patch
from core.event_bus import EventBus


class TestEventBus:
    def test_subscribe_and_emit(self):
        bus = EventBus()
        handler = MagicMock()
        bus.subscribe("test.event", handler)
        bus.emit("test.event", {"key": "value"})
        handler.assert_called_once_with({"key": "value"})

    def test_emit_unknown_event_does_nothing(self):
        bus = EventBus()
        bus.emit("unknown.event", {"key": "value"})  # No error

    def test_multiple_handlers(self):
        bus = EventBus()
        handler1 = MagicMock()
        handler2 = MagicMock()
        bus.subscribe("test.event", handler1)
        bus.subscribe("test.event", handler2)
        bus.emit("test.event", {"key": "value"})
        handler1.assert_called_once_with({"key": "value"})
        handler2.assert_called_once_with({"key": "value"})

    def test_handler_error_is_swallowed(self):
        bus = EventBus()
        bad_handler = MagicMock(side_effect=RuntimeError("boom"))
        good_handler = MagicMock()
        bus.subscribe("test.event", bad_handler)
        bus.subscribe("test.event", good_handler)
        bus.emit("test.event", {"key": "value"})
        bad_handler.assert_called_once()
        good_handler.assert_called_once()  # Still called despite bad_handler failure

    @pytest.mark.django_db
    def test_product_access_skips_handler_when_tenant_lacks_product(self):
        from apps.platform.tenants.models import Tenant

        tenant = Tenant.objects.create(name="metering-only")
        # Tenant has no products set (empty list)
        bus = EventBus()
        handler = MagicMock()
        bus.subscribe("test.event", handler, requires_product="billing")
        bus.emit("test.event", {"tenant_id": str(tenant.id)})
        handler.assert_not_called()

    @pytest.mark.django_db
    def test_product_access_calls_handler_when_tenant_has_product(self):
        from apps.platform.tenants.models import Tenant

        tenant = Tenant.objects.create(name="both", products=["metering", "billing"])
        bus = EventBus()
        handler = MagicMock()
        bus.subscribe("test.event", handler, requires_product="billing")
        bus.emit("test.event", {"tenant_id": str(tenant.id)})
        handler.assert_called_once()

    def test_handler_without_product_requirement_always_runs(self):
        bus = EventBus()
        handler = MagicMock()
        bus.subscribe("test.event", handler)  # No requires_product
        bus.emit("test.event", {"tenant_id": "some-id"})
        handler.assert_called_once()
```

**Step 2: Run test to verify it fails**

```bash
cd ubb-platform && python -m pytest core/tests/test_event_bus.py -v
```
Expected: FAIL with `ModuleNotFoundError: No module named 'core.event_bus'`

**Step 3: Commit**

```bash
git add core/tests/test_event_bus.py
git commit -m "test: add failing tests for EventBus"
```

---

### Task 12: Add `products` field to Tenant model

The EventBus needs to check tenant products. Add the field first.

**Files:**
- Modify: `apps/platform/tenants/models.py`
- Create: migration via `makemigrations`

**Step 1: Write the failing test**

```python
# Add to existing tenant model tests or create apps/platform/tenants/tests/test_models.py
import pytest
from apps.platform.tenants.models import Tenant


@pytest.mark.django_db
class TestTenantProducts:
    def test_default_products_is_empty_list(self):
        tenant = Tenant.objects.create(name="test")
        assert tenant.products == []

    def test_can_set_metering_only(self):
        tenant = Tenant.objects.create(name="test", products=["metering"])
        tenant.refresh_from_db()
        assert tenant.products == ["metering"]

    def test_can_set_both_products(self):
        tenant = Tenant.objects.create(name="test", products=["metering", "billing"])
        tenant.refresh_from_db()
        assert "metering" in tenant.products
        assert "billing" in tenant.products
```

**Step 2: Run test to verify it fails**

```bash
cd ubb-platform && python -m pytest apps/platform/tenants/tests/test_models.py -v -k "TestTenantProducts"
```
Expected: FAIL — `products` field doesn't exist yet.

**Step 3: Add the `products` field to Tenant model**

In `apps/platform/tenants/models.py`, add:

```python
from django.contrib.postgres.fields import ArrayField

class Tenant(BaseModel):
    # ... existing fields ...
    products = ArrayField(
        models.CharField(max_length=20),
        default=list,
        blank=True,
        help_text='Product access: "metering", "billing"',
    )
```

> **NOTE:** If using SQLite for tests, `ArrayField` requires PostgreSQL. If the project uses SQLite for testing, use a JSONField instead:
> ```python
> products = models.JSONField(default=list, blank=True)
> ```
> Check `config/settings.py` — if `DATABASE_URL` defaults to SQLite, use JSONField.

**Step 4: Generate migration**

```bash
cd ubb-platform && python manage.py makemigrations tenants -n add_products_field
```

**Step 5: Run migration**

```bash
python manage.py migrate
```

**Step 6: Run tests to verify they pass**

```bash
cd ubb-platform && python -m pytest apps/platform/tenants/tests/test_models.py -v -k "TestTenantProducts"
```
Expected: PASS

**Step 7: Commit**

```bash
git add apps/platform/tenants/models.py apps/platform/tenants/migrations/ apps/platform/tenants/tests/
git commit -m "feat: add products field to Tenant model"
```

---

### Task 13: Implement EventBus

**Files:**
- Create: `core/event_bus.py`

**Step 1: Implement EventBus**

```python
# core/event_bus.py
import logging

logger = logging.getLogger("ubb.events")


class EventBus:
    def __init__(self):
        self._handlers = {}

    def subscribe(self, event_name, handler, requires_product=None):
        self._handlers.setdefault(event_name, []).append({
            "handler": handler,
            "requires_product": requires_product,
        })

    def _tenant_has_product(self, tenant_id, product):
        from django.core.cache import cache

        cache_key = f"tenant_products:{tenant_id}"
        products = cache.get(cache_key)
        if products is None:
            from apps.platform.tenants.models import Tenant

            tenant = Tenant.objects.get(id=tenant_id)
            products = tenant.products
            cache.set(cache_key, products, timeout=300)  # 5 min
        return product in products

    def emit(self, event_name, data):
        logger.info("event.emitted", extra={"data": {"event": event_name, **data}})
        for entry in self._handlers.get(event_name, []):
            try:
                if entry["requires_product"] and data.get("tenant_id"):
                    if not self._tenant_has_product(
                        data["tenant_id"], entry["requires_product"]
                    ):
                        continue
                entry["handler"](data)
            except Exception:
                logger.exception(
                    "event.handler_failed",
                    extra={
                        "data": {
                            "event": event_name,
                            "handler": entry["handler"].__name__,
                        }
                    },
                )


event_bus = EventBus()
```

**Step 2: Run tests to verify they pass**

```bash
cd ubb-platform && python -m pytest core/tests/test_event_bus.py -v
```
Expected: All 7 tests PASS.

**Step 3: Commit**

```bash
git add core/event_bus.py
git commit -m "feat: implement EventBus with product access checks"
```

---

### Task 14: Emit `usage.recorded` event from UsageService

**Files:**
- Modify: `apps/metering/usage/services/usage_service.py`
- Create: `apps/metering/usage/tests/test_usage_event_emission.py`

**Step 1: Write the failing test**

```python
# apps/metering/usage/tests/test_usage_event_emission.py
import pytest
from unittest.mock import patch, MagicMock
from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer


@pytest.mark.django_db
class TestUsageRecordedEventEmission:
    def test_emits_usage_recorded_event(self):
        tenant = Tenant.objects.create(name="test", products=["metering"])
        customer = Customer.objects.create(tenant=tenant, external_id="cust-1")
        customer.wallet.balance_micros = 100_000_000  # $100
        customer.wallet.save()

        with patch("apps.metering.usage.services.usage_service.event_bus") as mock_bus:
            from apps.metering.usage.services.usage_service import UsageService

            result = UsageService.record_usage(
                tenant=tenant,
                customer=customer,
                request_id="req-1",
                idempotency_key="idem-1",
                cost_micros=1_000_000,
            )

            mock_bus.emit.assert_called_once()
            call_args = mock_bus.emit.call_args
            assert call_args[0][0] == "usage.recorded"
            data = call_args[0][1]
            assert data["tenant_id"] == str(tenant.id)
            assert data["customer_id"] == str(customer.id)
            assert data["cost_micros"] == 1_000_000
            assert "event_id" in data
```

**Step 2: Run test to verify it fails**

```bash
cd ubb-platform && python -m pytest apps/metering/usage/tests/test_usage_event_emission.py -v
```
Expected: FAIL — `event_bus` not imported in usage_service, or `emit` not called.

**Step 3: Add event emission to UsageService.record_usage()**

At the end of `record_usage()`, after the UsageEvent is created and wallet is debited, add:

```python
from core.event_bus import event_bus

# ... at end of record_usage(), before return ...
event_bus.emit("usage.recorded", {
    "tenant_id": str(tenant.id),
    "customer_id": str(customer.id),
    "cost_micros": cost_micros,
    "event_type": event_type,
    "event_id": str(event.id),
})
```

> **IMPORTANT:** This must be INSIDE the `@transaction.atomic` block so the event is only emitted if the transaction succeeds. However, per the design doc, handler errors are swallowed — so this is safe.

**Step 4: Run tests**

```bash
cd ubb-platform && python -m pytest apps/metering/usage/tests/test_usage_event_emission.py -v
```
Expected: PASS

**Step 5: Run full test suite to verify no regressions**

```bash
cd ubb-platform && python -m pytest --tb=short -q
```

**Step 6: Commit**

```bash
git add apps/metering/usage/services/usage_service.py apps/metering/usage/tests/
git commit -m "feat: emit usage.recorded event from UsageService"
```

---

### Task 15: Move tenant billing accumulation from direct call to event handler

Currently `UsageService.record_usage()` directly calls `TenantBillingService.accumulate_usage()`. This is a cross-product import (metering → billing). Replace it with an event handler.

**Files:**
- Modify: `apps/metering/usage/services/usage_service.py` — remove direct `accumulate_usage` call
- Create: `apps/billing/handlers.py` — event handler for `usage.recorded`
- Modify: `apps/billing/tenant_billing/apps.py` — register handler in `ready()`

**Step 1: Write the failing test**

```python
# apps/billing/tests/test_handlers.py
import pytest
from unittest.mock import patch
from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer


@pytest.mark.django_db
class TestUsageRecordedHandler:
    def test_accumulates_usage_on_event(self):
        tenant = Tenant.objects.create(name="test", products=["metering", "billing"])

        with patch(
            "apps.billing.handlers.TenantBillingService.accumulate_usage"
        ) as mock_accumulate:
            from apps.billing.handlers import handle_usage_recorded

            handle_usage_recorded({
                "tenant_id": str(tenant.id),
                "customer_id": "some-customer",
                "cost_micros": 1_500_000,
                "event_type": "api_call",
                "event_id": "some-event-id",
            })

            mock_accumulate.assert_called_once_with(tenant, 1_500_000)
```

**Step 2: Run test to verify it fails**

```bash
cd ubb-platform && python -m pytest apps/billing/tests/test_handlers.py -v
```
Expected: FAIL — `apps.billing.handlers` doesn't exist.

**Step 3: Create the handler**

```python
# apps/billing/handlers.py
import logging
from apps.platform.tenants.models import Tenant
from apps.billing.tenant_billing.services import TenantBillingService

logger = logging.getLogger("ubb.events")


def handle_usage_recorded(data):
    """Accumulate usage cost into the tenant's current billing period."""
    tenant = Tenant.objects.get(id=data["tenant_id"])
    billed_cost_micros = data.get("cost_micros", 0)
    if billed_cost_micros > 0:
        TenantBillingService.accumulate_usage(tenant, billed_cost_micros)
    logger.info(
        "billing.usage_accumulated",
        extra={"data": {"tenant_id": data["tenant_id"], "cost_micros": billed_cost_micros}},
    )
```

**Step 4: Run handler test**

```bash
cd ubb-platform && python -m pytest apps/billing/tests/test_handlers.py -v
```
Expected: PASS

**Step 5: Register the handler in BillingConfig.ready()**

Update `apps/billing/tenant_billing/apps.py` (or create a top-level `apps/billing/apps.py` — use whichever is the app that gets loaded):

> **NOTE:** Since `apps.billing.tenant_billing` is in INSTALLED_APPS, its `ready()` hook runs. Add the subscription there.

```python
# apps/billing/tenant_billing/apps.py
from django.apps import AppConfig


class TenantBillingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.billing.tenant_billing"
    label = "tenant_billing"

    def ready(self):
        from core.event_bus import event_bus
        from apps.billing.handlers import handle_usage_recorded

        event_bus.subscribe(
            "usage.recorded",
            handle_usage_recorded,
            requires_product="billing",
        )
```

**Step 6: Remove the direct `accumulate_usage` call from UsageService**

In `apps/metering/usage/services/usage_service.py`, find and remove the line:
```python
TenantBillingService.accumulate_usage(tenant, billed_cost_micros)
```
And remove the import:
```python
from apps.billing.tenant_billing.services import TenantBillingService
```

> **CRITICAL:** This removes the cross-product import from metering → billing. The accumulation now happens via the event bus.

**Step 7: Run full test suite**

```bash
cd ubb-platform && python -m pytest --tb=short -q
```
Expected: All tests pass. The tenant billing accumulation still happens, but now through the event bus handler instead of a direct call.

**Step 8: Commit**

```bash
git add apps/billing/handlers.py apps/billing/tenant_billing/apps.py apps/metering/usage/services/usage_service.py apps/billing/tests/
git commit -m "feat: move tenant billing accumulation to event bus handler, remove cross-product import"
```

---

### Task 16: Add cache invalidation helper for tenant products

**Files:**
- Modify: `apps/platform/tenants/models.py` (or create `apps/platform/tenants/services.py`)

**Step 1: Write the failing test**

```python
# apps/platform/tenants/tests/test_cache_invalidation.py
import pytest
from django.core.cache import cache
from apps.platform.tenants.models import Tenant


@pytest.mark.django_db
class TestTenantProductsCacheInvalidation:
    def test_updating_products_invalidates_cache(self):
        tenant = Tenant.objects.create(name="test", products=["metering"])
        cache_key = f"tenant_products:{tenant.id}"

        # Simulate cached value
        cache.set(cache_key, ["metering"], timeout=300)
        assert cache.get(cache_key) == ["metering"]

        # Update products
        tenant.products = ["metering", "billing"]
        tenant.save()

        # Cache should be invalidated
        assert cache.get(cache_key) is None
```

**Step 2: Run test to verify it fails**

```bash
cd ubb-platform && python -m pytest apps/platform/tenants/tests/test_cache_invalidation.py -v
```
Expected: FAIL — cache is not invalidated on save.

**Step 3: Add cache invalidation to Tenant.save()**

In `apps/platform/tenants/models.py`, override `save()`:

```python
from django.core.cache import cache

class Tenant(BaseModel):
    # ... existing fields ...

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        cache.delete(f"tenant_products:{self.id}")
```

**Step 4: Run test**

```bash
cd ubb-platform && python -m pytest apps/platform/tenants/tests/test_cache_invalidation.py -v
```
Expected: PASS

**Step 5: Run full test suite**

```bash
cd ubb-platform && python -m pytest --tb=short -q
```

**Step 6: Commit**

```bash
git add apps/platform/tenants/models.py apps/platform/tenants/tests/
git commit -m "feat: invalidate tenant products cache on save"
```

---

## Phase 3: Extract Product APIs

> Create namespaced `/metering/` and `/billing/` API paths. Add `ProductAccess` auth. Move existing endpoints into product-specific API modules.

### Task 17: Implement ProductAccess auth class

**Files:**
- Modify: `core/auth.py`
- Create: `core/tests/test_product_access.py`

**Step 1: Write the failing test**

```python
# core/tests/test_product_access.py
import pytest
from unittest.mock import MagicMock
from django.http import HttpRequest
from core.auth import ProductAccess


class TestProductAccess:
    def test_raises_403_when_tenant_lacks_product(self):
        auth = ProductAccess("billing")
        request = MagicMock()
        request.tenant = MagicMock()
        request.tenant.products = ["metering"]

        with pytest.raises(Exception) as exc_info:
            auth(request)
        # Should be a 403 HttpError from django-ninja
        assert "403" in str(exc_info.value) or "does not have access" in str(exc_info.value)

    def test_passes_when_tenant_has_product(self):
        auth = ProductAccess("billing")
        request = MagicMock()
        request.tenant = MagicMock()
        request.tenant.products = ["metering", "billing"]

        # Should not raise
        auth(request)

    def test_passes_when_tenant_has_only_required_product(self):
        auth = ProductAccess("metering")
        request = MagicMock()
        request.tenant = MagicMock()
        request.tenant.products = ["metering"]

        auth(request)
```

**Step 2: Run test to verify it fails**

```bash
cd ubb-platform && python -m pytest core/tests/test_product_access.py -v
```
Expected: FAIL — `ProductAccess` doesn't exist.

**Step 3: Implement ProductAccess**

Add to `core/auth.py`:

```python
from ninja.errors import HttpError


class ProductAccess:
    """Dependency that checks tenant has access to a specific product."""

    def __init__(self, required_product):
        self.required_product = required_product

    def __call__(self, request):
        if self.required_product not in request.tenant.products:
            raise HttpError(
                403,
                f"Tenant does not have access to {self.required_product}",
            )
```

**Step 4: Run tests**

```bash
cd ubb-platform && python -m pytest core/tests/test_product_access.py -v
```
Expected: PASS

**Step 5: Commit**

```bash
git add core/auth.py core/tests/test_product_access.py
git commit -m "feat: add ProductAccess auth dependency"
```

---

### Task 18: Create Metering API module (`/api/v1/metering/`)

Extract metering-related endpoints (usage recording, usage history, analytics) from the flat `api/v1/endpoints.py` into `api/v1/metering_endpoints.py` with the `/metering/` prefix and `ProductAccess("metering")` check.

**Files:**
- Create: `api/v1/metering_endpoints.py`
- Modify: `config/urls.py` — add metering API route
- Create: `api/v1/tests/test_metering_endpoints.py`

**Step 1: Write the failing test**

```python
# api/v1/tests/test_metering_endpoints.py
import pytest
from django.test import override_settings


@pytest.mark.django_db
class TestMeteringProductAccess:
    def test_metering_endpoint_requires_metering_product(self, client):
        """Tenant without 'metering' product gets 403 on metering endpoints."""
        # Create tenant with only billing product
        from apps.platform.tenants.models import Tenant, TenantApiKey

        tenant = Tenant.objects.create(name="billing-only", products=["billing"])
        key_obj, raw_key = TenantApiKey.create_key(tenant=tenant, label="test")

        response = client.post(
            "/api/v1/metering/usage",
            content_type="application/json",
            data={},
            HTTP_AUTHORIZATION=f"Bearer {raw_key}",
        )
        assert response.status_code == 403

    def test_metering_endpoint_allows_metering_tenant(self, client):
        """Tenant with 'metering' product can hit metering endpoints."""
        from apps.platform.tenants.models import Tenant, TenantApiKey
        from apps.platform.customers.models import Customer

        tenant = Tenant.objects.create(name="metering-tenant", products=["metering"])
        key_obj, raw_key = TenantApiKey.create_key(tenant=tenant, label="test")
        customer = Customer.objects.create(tenant=tenant, external_id="cust-1")
        customer.wallet.balance_micros = 100_000_000
        customer.wallet.save()

        response = client.post(
            "/api/v1/metering/usage",
            content_type="application/json",
            data={
                "customer_id": customer.external_id,
                "request_id": "req-1",
                "idempotency_key": "idem-1",
                "cost_micros": 1_000_000,
            },
            HTTP_AUTHORIZATION=f"Bearer {raw_key}",
        )
        assert response.status_code == 200
```

**Step 2: Run test to verify it fails**

```bash
cd ubb-platform && python -m pytest api/v1/tests/test_metering_endpoints.py -v
```
Expected: FAIL — 404, route doesn't exist.

**Step 3: Create metering API module**

Create `api/v1/metering_endpoints.py` — copy the usage-related endpoints from `api/v1/endpoints.py` (record_usage, get_usage, and any analytics endpoints). Add `ProductAccess("metering")` as a dependency.

```python
# api/v1/metering_endpoints.py
from ninja import Router
from core.auth import ApiKeyAuth, ProductAccess

metering_api = Router(auth=[ApiKeyAuth()], tags=["metering"])
metering_product = ProductAccess("metering")


@metering_api.post("/usage", response=RecordUsageResponse)
def record_usage(request, payload: RecordUsageRequest):
    metering_product(request)
    # ... same implementation as current record_usage ...


@metering_api.get("/customers/{customer_id}/usage", response=PaginatedUsageResponse)
def get_usage(request, customer_id: str, cursor: str = None, limit: int = 20):
    metering_product(request)
    # ... same implementation ...
```

> **NOTE:** The exact endpoints to move depend on reading the current `api/v1/endpoints.py`. The key pattern is: metering endpoints go here, billing endpoints go to a separate module.

**Step 4: Wire up in `config/urls.py`**

```python
from api.v1.metering_endpoints import metering_api

urlpatterns = [
    # ... existing ...
    path("api/v1/metering/", metering_api.urls),
]
```

**Step 5: Run tests**

```bash
cd ubb-platform && python -m pytest api/v1/tests/test_metering_endpoints.py -v
```
Expected: PASS

**Step 6: Run full test suite**

```bash
cd ubb-platform && python -m pytest --tb=short -q
```

**Step 7: Commit**

```bash
git add api/v1/metering_endpoints.py config/urls.py api/v1/tests/test_metering_endpoints.py
git commit -m "feat: create metering API with ProductAccess enforcement"
```

---

### Task 19: Create Billing API module (`/api/v1/billing/`)

Extract billing-related endpoints (balance, transactions, top-up, auto-top-up, withdraw, pre-check, tenant billing) into `api/v1/billing_endpoints.py` with `/billing/` prefix and `ProductAccess("billing")`.

**Files:**
- Create: `api/v1/billing_endpoints.py`
- Modify: `config/urls.py`
- Create: `api/v1/tests/test_billing_endpoints.py`

**Step 1: Write the failing test**

```python
# api/v1/tests/test_billing_endpoints.py
import pytest


@pytest.mark.django_db
class TestBillingProductAccess:
    def test_billing_endpoint_requires_billing_product(self, client):
        from apps.platform.tenants.models import Tenant, TenantApiKey
        from apps.platform.customers.models import Customer

        tenant = Tenant.objects.create(name="metering-only", products=["metering"])
        key_obj, raw_key = TenantApiKey.create_key(tenant=tenant, label="test")
        customer = Customer.objects.create(tenant=tenant, external_id="cust-1")

        response = client.get(
            f"/api/v1/billing/customers/{customer.external_id}/balance",
            HTTP_AUTHORIZATION=f"Bearer {raw_key}",
        )
        assert response.status_code == 403

    def test_billing_endpoint_allows_billing_tenant(self, client):
        from apps.platform.tenants.models import Tenant, TenantApiKey
        from apps.platform.customers.models import Customer

        tenant = Tenant.objects.create(name="billing-tenant", products=["billing"])
        key_obj, raw_key = TenantApiKey.create_key(tenant=tenant, label="test")
        customer = Customer.objects.create(tenant=tenant, external_id="cust-1")

        response = client.get(
            f"/api/v1/billing/customers/{customer.external_id}/balance",
            HTTP_AUTHORIZATION=f"Bearer {raw_key}",
        )
        assert response.status_code == 200
```

**Step 2: Run test to verify it fails**

```bash
cd ubb-platform && python -m pytest api/v1/tests/test_billing_endpoints.py -v
```
Expected: FAIL — 404.

**Step 3: Create billing API module**

Create `api/v1/billing_endpoints.py` — move billing endpoints (balance, transactions, top-up, auto-top-up, withdraw, pre-check, debit, credit, tenant billing periods, tenant invoices) from `api/v1/endpoints.py` and `api/v1/tenant_endpoints.py`.

```python
# api/v1/billing_endpoints.py
from ninja import Router
from core.auth import ApiKeyAuth, ProductAccess

billing_api = Router(auth=[ApiKeyAuth()], tags=["billing"])
billing_product = ProductAccess("billing")


@billing_api.get("/customers/{customer_id}/balance", response=BalanceResponse)
def get_balance(request, customer_id: str):
    billing_product(request)
    # ... same implementation ...


@billing_api.post("/debit", response=DebitResponse)
def debit_wallet(request, payload: DebitRequest):
    billing_product(request)
    # ... implementation ...


@billing_api.post("/credit", response=CreditResponse)
def credit_wallet(request, payload: CreditRequest):
    billing_product(request)
    # ... implementation ...


# ... remaining billing endpoints ...
```

**Step 4: Wire up in `config/urls.py`**

```python
from api.v1.billing_endpoints import billing_api

urlpatterns = [
    # ... existing ...
    path("api/v1/billing/", billing_api.urls),
]
```

**Step 5: Run tests**

```bash
cd ubb-platform && python -m pytest api/v1/tests/test_billing_endpoints.py -v
```
Expected: PASS

**Step 6: Run full test suite**

```bash
cd ubb-platform && python -m pytest --tb=short -q
```

**Step 7: Commit**

```bash
git add api/v1/billing_endpoints.py config/urls.py api/v1/tests/test_billing_endpoints.py
git commit -m "feat: create billing API with ProductAccess enforcement"
```

---

### Task 20: Keep old flat endpoints working (backward compatibility)

The old endpoints (`POST /api/v1/usage`, `GET /api/v1/customers/{id}/balance`, etc.) should continue to work for existing integrations. They should NOT enforce product access — they work as before.

**Step 1: Verify existing tests still pass**

```bash
cd ubb-platform && python -m pytest api/v1/tests/test_endpoints.py -v
```
Expected: All existing API tests still pass (old routes still work).

> **NOTE:** Do NOT remove the old endpoints yet. They will be deprecated in a future release. The new `/metering/` and `/billing/` endpoints are the canonical routes going forward.

**Step 2: Commit (if any changes needed)**

```bash
git add -A
git commit -m "chore: verify backward compatibility of flat API endpoints"
```

---

### Task 21: Update Widget API to require billing product

The widget endpoints (`/api/v1/me/`) are billing-related (balance, transactions, top-up, invoices). Add `ProductAccess("billing")` check.

**Files:**
- Modify: `api/v1/me_endpoints.py`
- Modify: `api/v1/tests/test_me_endpoints.py`

**Step 1: Write the failing test**

```python
# Add to api/v1/tests/test_me_endpoints.py
@pytest.mark.django_db
class TestWidgetProductAccess:
    def test_widget_balance_requires_billing_product(self, client):
        from apps.platform.tenants.models import Tenant
        from apps.platform.customers.models import Customer
        from core.widget_auth import create_widget_token

        tenant = Tenant.objects.create(
            name="metering-only",
            products=["metering"],
            widget_secret="a" * 64,
        )
        customer = Customer.objects.create(tenant=tenant, external_id="cust-1")
        token = create_widget_token(customer)

        response = client.get(
            "/api/v1/me/balance",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        assert response.status_code == 403
```

**Step 2: Run test to verify it fails**

```bash
cd ubb-platform && python -m pytest api/v1/tests/test_me_endpoints.py -v -k "test_widget_balance_requires_billing"
```
Expected: FAIL — currently returns 200.

**Step 3: Add ProductAccess check to widget endpoints**

In `api/v1/me_endpoints.py`, add the billing product check at the start of each endpoint. Since widget endpoints use `WidgetJWTAuth` (not `ApiKeyAuth`), we need to check `request.widget_tenant.products`:

```python
from core.auth import ProductAccess

billing_product = ProductAccess("billing")


@me_api.get("/balance", response=BalanceResponse)
def get_balance(request):
    # Widget tenant is set by WidgetJWTAuth
    request.tenant = request.widget_tenant  # ProductAccess reads request.tenant
    billing_product(request)
    # ... rest of implementation ...
```

**Step 4: Run tests**

```bash
cd ubb-platform && python -m pytest api/v1/tests/test_me_endpoints.py -v
```
Expected: All pass.

**Step 5: Commit**

```bash
git add api/v1/me_endpoints.py api/v1/tests/test_me_endpoints.py
git commit -m "feat: enforce billing product access on widget endpoints"
```

---

## Phase 4: Update SDK + Clean Up

> Update the SDK to support product-specific clients. SDK orchestrates multi-product flows (record usage + debit wallet). Remove remaining cross-product imports.

### Task 22: Create MeteringClient in SDK

**Files:**
- Create: `ubb-sdk/ubb/metering.py`
- Create: `ubb-sdk/tests/test_metering_client.py`

**Step 1: Write the failing test**

```python
# ubb-sdk/tests/test_metering_client.py
import pytest
import httpx
from unittest.mock import AsyncMock, patch
from ubb.metering import MeteringClient


class TestMeteringClient:
    def test_record_usage_calls_metering_endpoint(self):
        client = MeteringClient(api_key="ubb_live_test", base_url="http://localhost:8001")

        with patch.object(client._client, "post") as mock_post:
            mock_post.return_value = httpx.Response(
                200,
                json={
                    "event_id": "evt-1",
                    "new_balance_micros": 99_000_000,
                    "suspended": False,
                    "provider_cost_micros": 800_000,
                    "billed_cost_micros": 1_000_000,
                },
            )

            result = client.record_usage(
                customer_id="cust-1",
                request_id="req-1",
                idempotency_key="idem-1",
                cost_micros=1_000_000,
            )

            mock_post.assert_called_once()
            call_url = mock_post.call_args[0][0]
            assert "/metering/usage" in call_url
            assert result.event_id == "evt-1"

    def test_estimate_cost_calls_metering_endpoint(self):
        client = MeteringClient(api_key="ubb_live_test", base_url="http://localhost:8001")

        with patch.object(client._client, "get") as mock_get:
            mock_get.return_value = httpx.Response(
                200,
                json={"estimated_cost_micros": 1_500_000},
            )

            cost = client.estimate_cost(
                event_type="api_call",
                provider="openai",
                usage_metrics={"input_tokens": 1000},
            )

            assert cost == 1_500_000
```

**Step 2: Run test to verify it fails**

```bash
cd ubb-sdk && python -m pytest tests/test_metering_client.py -v
```
Expected: FAIL — `MeteringClient` doesn't exist.

**Step 3: Implement MeteringClient**

```python
# ubb-sdk/ubb/metering.py
import httpx
from ubb.types import RecordUsageResult, PaginatedResponse, UsageEvent
from ubb.exceptions import UBBAuthError, UBBAPIError, UBBConnectionError, UBBValidationError


class MeteringClient:
    def __init__(self, api_key: str, base_url: str = "http://localhost:8001", timeout: float = 10.0):
        self._client = httpx.Client(
            base_url=base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout,
        )

    def record_usage(
        self,
        customer_id: str,
        request_id: str,
        idempotency_key: str,
        cost_micros: int | None = None,
        metadata: dict | None = None,
        event_type: str | None = None,
        provider: str | None = None,
        usage_metrics: dict | None = None,
        properties: dict | None = None,
        group_keys: dict | None = None,
    ) -> RecordUsageResult:
        payload = {
            "customer_id": customer_id,
            "request_id": request_id,
            "idempotency_key": idempotency_key,
        }
        if cost_micros is not None:
            payload["cost_micros"] = cost_micros
        if metadata:
            payload["metadata"] = metadata
        if event_type:
            payload["event_type"] = event_type
        if provider:
            payload["provider"] = provider
        if usage_metrics:
            payload["usage_metrics"] = usage_metrics
        if properties:
            payload["properties"] = properties
        if group_keys:
            payload["group_keys"] = group_keys

        resp = self._request("POST", "/api/v1/metering/usage", json=payload)
        return RecordUsageResult(**resp)

    def estimate_cost(
        self,
        event_type: str,
        provider: str,
        usage_metrics: dict,
        properties: dict | None = None,
    ) -> int:
        params = {
            "event_type": event_type,
            "provider": provider,
            "usage_metrics": usage_metrics,
        }
        if properties:
            params["properties"] = properties
        resp = self._request("GET", "/api/v1/metering/estimate", params=params)
        return resp["estimated_cost_micros"]

    def get_usage(
        self,
        customer_id: str,
        cursor: str | None = None,
        limit: int = 20,
        group_key: str | None = None,
        group_value: str | None = None,
    ) -> PaginatedResponse[UsageEvent]:
        params = {"limit": limit}
        if cursor:
            params["cursor"] = cursor
        if group_key:
            params["group_key"] = group_key
        if group_value:
            params["group_value"] = group_value
        resp = self._request("GET", f"/api/v1/metering/customers/{customer_id}/usage", params=params)
        return PaginatedResponse(
            data=[UsageEvent(**e) for e in resp["data"]],
            next_cursor=resp.get("next_cursor"),
            has_more=resp.get("has_more", False),
        )

    def _request(self, method, url, **kwargs):
        try:
            resp = self._client.request(method, url, **kwargs)
        except (httpx.ConnectError, httpx.TimeoutException) as e:
            raise UBBConnectionError(e) from e

        if resp.status_code == 401:
            raise UBBAuthError("Invalid API key")
        if resp.status_code == 422:
            raise UBBValidationError(resp.json().get("detail", "Validation error"))
        if resp.status_code >= 400:
            raise UBBAPIError(resp.status_code, resp.text)
        return resp.json()

    def close(self):
        self._client.close()
```

**Step 4: Run tests**

```bash
cd ubb-sdk && python -m pytest tests/test_metering_client.py -v
```
Expected: PASS

**Step 5: Commit**

```bash
git add ubb-sdk/ubb/metering.py ubb-sdk/tests/test_metering_client.py
git commit -m "feat: add MeteringClient to SDK"
```

---

### Task 23: Create BillingClient in SDK

**Files:**
- Create: `ubb-sdk/ubb/billing.py`
- Create: `ubb-sdk/tests/test_billing_client.py`

**Step 1: Write the failing test**

```python
# ubb-sdk/tests/test_billing_client.py
import pytest
import httpx
from unittest.mock import patch
from ubb.billing import BillingClient


class TestBillingClient:
    def test_debit_calls_billing_endpoint(self):
        client = BillingClient(api_key="ubb_live_test", base_url="http://localhost:8001")

        with patch.object(client._client, "post") as mock_post:
            mock_post.return_value = httpx.Response(
                200,
                json={"new_balance_micros": 98_000_000, "transaction_id": "txn-1"},
            )

            result = client.debit(
                customer_id="cust-1",
                amount_micros=2_000_000,
                reference="evt-123",
            )

            call_url = mock_post.call_args[0][0]
            assert "/billing/debit" in call_url
            assert result["new_balance_micros"] == 98_000_000

    def test_get_balance_calls_billing_endpoint(self):
        client = BillingClient(api_key="ubb_live_test", base_url="http://localhost:8001")

        with patch.object(client._client, "get") as mock_get:
            mock_get.return_value = httpx.Response(
                200,
                json={"balance_micros": 50_000_000, "currency": "USD"},
            )

            result = client.get_balance(customer_id="cust-1")
            call_url = mock_get.call_args[0][0]
            assert "/billing/customers/cust-1/balance" in call_url
            assert result.balance_micros == 50_000_000

    def test_pre_check_calls_billing_endpoint(self):
        client = BillingClient(api_key="ubb_live_test", base_url="http://localhost:8001")

        with patch.object(client._client, "post") as mock_post:
            mock_post.return_value = httpx.Response(
                200,
                json={"can_proceed": True, "balance_micros": 50_000_000},
            )

            result = client.pre_check(
                customer_id="cust-1",
                estimated_cost=2_000_000,
            )

            call_url = mock_post.call_args[0][0]
            assert "/billing/pre-check" in call_url
            assert result["can_proceed"] is True
```

**Step 2: Run test to verify it fails**

```bash
cd ubb-sdk && python -m pytest tests/test_billing_client.py -v
```
Expected: FAIL

**Step 3: Implement BillingClient**

```python
# ubb-sdk/ubb/billing.py
import httpx
from ubb.types import BalanceResult, TopUpResult
from ubb.exceptions import UBBAuthError, UBBAPIError, UBBConnectionError, UBBValidationError


class BillingClient:
    def __init__(self, api_key: str, base_url: str = "http://localhost:8001", timeout: float = 10.0):
        self._client = httpx.Client(
            base_url=base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout,
        )

    def debit(self, customer_id: str, amount_micros: int, reference: str) -> dict:
        return self._request("POST", "/api/v1/billing/debit", json={
            "customer_id": customer_id,
            "amount_micros": amount_micros,
            "reference": reference,
        })

    def credit(self, customer_id: str, amount_micros: int, source: str, reference: str) -> dict:
        return self._request("POST", "/api/v1/billing/credit", json={
            "customer_id": customer_id,
            "amount_micros": amount_micros,
            "source": source,
            "reference": reference,
        })

    def get_balance(self, customer_id: str) -> BalanceResult:
        resp = self._request("GET", f"/api/v1/billing/customers/{customer_id}/balance")
        return BalanceResult(**resp)

    def pre_check(self, customer_id: str, estimated_cost: int) -> dict:
        return self._request("POST", "/api/v1/billing/pre-check", json={
            "customer_id": customer_id,
            "estimated_cost": estimated_cost,
        })

    def create_top_up(
        self, customer_id: str, amount_micros: int, success_url: str, cancel_url: str
    ) -> TopUpResult:
        resp = self._request("POST", f"/api/v1/billing/customers/{customer_id}/top-up", json={
            "amount_micros": amount_micros,
            "success_url": success_url,
            "cancel_url": cancel_url,
        })
        return TopUpResult(**resp)

    def configure_auto_topup(
        self, customer_id: str, is_enabled: bool,
        trigger_threshold_micros: int | None = None,
        top_up_amount_micros: int | None = None,
    ) -> dict:
        payload = {"is_enabled": is_enabled}
        if trigger_threshold_micros is not None:
            payload["trigger_threshold_micros"] = trigger_threshold_micros
        if top_up_amount_micros is not None:
            payload["top_up_amount_micros"] = top_up_amount_micros
        return self._request(
            "PUT",
            f"/api/v1/billing/customers/{customer_id}/auto-top-up",
            json=payload,
        )

    def get_transactions(self, customer_id: str, cursor: str | None = None, limit: int = 20) -> dict:
        params = {"limit": limit}
        if cursor:
            params["cursor"] = cursor
        return self._request("GET", f"/api/v1/billing/customers/{customer_id}/transactions", params=params)

    def _request(self, method, url, **kwargs):
        try:
            resp = self._client.request(method, url, **kwargs)
        except (httpx.ConnectError, httpx.TimeoutException) as e:
            raise UBBConnectionError(e) from e

        if resp.status_code == 401:
            raise UBBAuthError("Invalid API key")
        if resp.status_code == 422:
            raise UBBValidationError(resp.json().get("detail", "Validation error"))
        if resp.status_code >= 400:
            raise UBBAPIError(resp.status_code, resp.text)
        return resp.json()

    def close(self):
        self._client.close()
```

**Step 4: Run tests**

```bash
cd ubb-sdk && python -m pytest tests/test_billing_client.py -v
```
Expected: PASS

**Step 5: Commit**

```bash
git add ubb-sdk/ubb/billing.py ubb-sdk/tests/test_billing_client.py
git commit -m "feat: add BillingClient to SDK"
```

---

### Task 24: Update UBBClient to support product-specific clients with orchestration

**Files:**
- Modify: `ubb-sdk/ubb/client.py`
- Modify: `ubb-sdk/tests/test_client.py` (or create new test file)

**Step 1: Write the failing test**

```python
# ubb-sdk/tests/test_orchestration.py
import pytest
import httpx
from unittest.mock import patch, MagicMock
from ubb.client import UBBClient


class TestUBBClientOrchestration:
    def test_record_usage_metering_only(self):
        """Metering-only client records usage, no wallet debit."""
        client = UBBClient(
            api_key="ubb_live_test",
            base_url="http://localhost:8001",
            metering=True,
            billing=False,
        )

        with patch.object(client.metering, "record_usage") as mock_record:
            from ubb.types import RecordUsageResult
            mock_record.return_value = RecordUsageResult(
                event_id="evt-1",
                new_balance_micros=99_000_000,
                suspended=False,
                provider_cost_micros=800_000,
                billed_cost_micros=1_000_000,
            )

            result = client.record_usage(
                customer_id="cust-1",
                request_id="req-1",
                idempotency_key="idem-1",
                cost_micros=1_000_000,
            )

            mock_record.assert_called_once()
            assert result.event_id == "evt-1"
            assert not hasattr(result, "balance_after_micros") or result.balance_after_micros is None

    def test_record_usage_with_billing_debits_wallet(self):
        """Both-products client records usage AND debits wallet."""
        client = UBBClient(
            api_key="ubb_live_test",
            base_url="http://localhost:8001",
            metering=True,
            billing=True,
        )

        with patch.object(client.metering, "record_usage") as mock_record, \
             patch.object(client.billing, "debit") as mock_debit:
            from ubb.types import RecordUsageResult
            mock_record.return_value = RecordUsageResult(
                event_id="evt-1",
                new_balance_micros=99_000_000,
                suspended=False,
                provider_cost_micros=800_000,
                billed_cost_micros=1_000_000,
            )
            mock_debit.return_value = {
                "new_balance_micros": 98_000_000,
                "transaction_id": "txn-1",
            }

            result = client.record_usage(
                customer_id="cust-1",
                request_id="req-1",
                idempotency_key="idem-1",
                cost_micros=1_000_000,
            )

            mock_record.assert_called_once()
            mock_debit.assert_called_once_with(
                customer_id="cust-1",
                amount_micros=1_000_000,
                reference="evt-1",
            )
            assert result.balance_after_micros == 98_000_000

    def test_record_usage_without_metering_raises(self):
        """Can't record usage without metering product."""
        client = UBBClient(
            api_key="ubb_live_test",
            base_url="http://localhost:8001",
            metering=False,
            billing=True,
        )
        from ubb.exceptions import UBBError
        with pytest.raises(UBBError, match="Metering not configured"):
            client.record_usage(
                customer_id="cust-1",
                request_id="req-1",
                idempotency_key="idem-1",
                cost_micros=1_000_000,
            )

    def test_pre_check_with_both_products(self):
        """Pre-check estimates cost via metering, checks balance via billing."""
        client = UBBClient(
            api_key="ubb_live_test",
            base_url="http://localhost:8001",
            metering=True,
            billing=True,
        )

        with patch.object(client.metering, "estimate_cost") as mock_estimate, \
             patch.object(client.billing, "pre_check") as mock_precheck:
            mock_estimate.return_value = 1_500_000
            mock_precheck.return_value = {
                "can_proceed": True,
                "balance_micros": 50_000_000,
            }

            result = client.pre_check(
                customer_id="cust-1",
                event_type="api_call",
                provider="openai",
                usage_metrics={"input_tokens": 1000},
            )

            mock_estimate.assert_called_once()
            mock_precheck.assert_called_once()
            assert result.can_proceed is True
            assert result.estimated_cost_micros == 1_500_000
```

**Step 2: Run test to verify it fails**

```bash
cd ubb-sdk && python -m pytest tests/test_orchestration.py -v
```
Expected: FAIL

**Step 3: Update UBBClient**

Modify `ubb-sdk/ubb/client.py` to add product-specific client support:

```python
# ubb-sdk/ubb/client.py
from ubb.metering import MeteringClient
from ubb.billing import BillingClient
from ubb.exceptions import UBBError
from ubb.types import RecordUsageResult
from dataclasses import dataclass


@dataclass(frozen=True)
class PreCheckResult:
    can_proceed: bool
    estimated_cost_micros: int
    balance_micros: int | None = None


class UBBClient:
    def __init__(
        self,
        api_key: str,
        base_url: str = "http://localhost:8001",
        timeout: float = 10.0,
        metering: bool = True,
        billing: bool = False,
        # Legacy params (kept for backward compat)
        widget_secret: str | None = None,
        tenant_id: str | None = None,
    ):
        self.metering = MeteringClient(api_key, base_url, timeout) if metering else None
        self.billing = BillingClient(api_key, base_url, timeout) if billing else None
        self._widget_secret = widget_secret
        self._tenant_id = tenant_id

    def record_usage(
        self,
        customer_id: str,
        request_id: str,
        idempotency_key: str,
        cost_micros: int | None = None,
        metadata: dict | None = None,
        event_type: str | None = None,
        provider: str | None = None,
        usage_metrics: dict | None = None,
        properties: dict | None = None,
        group_keys: dict | None = None,
    ) -> RecordUsageResult:
        if not self.metering:
            raise UBBError("Metering not configured")

        result = self.metering.record_usage(
            customer_id=customer_id,
            request_id=request_id,
            idempotency_key=idempotency_key,
            cost_micros=cost_micros,
            metadata=metadata,
            event_type=event_type,
            provider=provider,
            usage_metrics=usage_metrics,
            properties=properties,
            group_keys=group_keys,
        )

        if self.billing and result.billed_cost_micros:
            debit = self.billing.debit(
                customer_id=customer_id,
                amount_micros=result.billed_cost_micros,
                reference=result.event_id,
            )
            result = RecordUsageResult(
                event_id=result.event_id,
                new_balance_micros=result.new_balance_micros,
                suspended=result.suspended,
                provider_cost_micros=result.provider_cost_micros,
                billed_cost_micros=result.billed_cost_micros,
                balance_after_micros=debit["new_balance_micros"],
            )

        return result

    def pre_check(
        self,
        customer_id: str,
        event_type: str,
        provider: str,
        usage_metrics: dict,
    ) -> PreCheckResult:
        if not self.metering:
            raise UBBError("Metering not configured")

        cost = self.metering.estimate_cost(event_type, provider, usage_metrics)

        if self.billing:
            check = self.billing.pre_check(customer_id, estimated_cost=cost)
            return PreCheckResult(
                can_proceed=check["can_proceed"],
                estimated_cost_micros=cost,
                balance_micros=check.get("balance_micros"),
            )

        return PreCheckResult(
            can_proceed=True,
            estimated_cost_micros=cost,
        )

    def close(self):
        if self.metering:
            self.metering.close()
        if self.billing:
            self.billing.close()
```

> **NOTE:** The `RecordUsageResult` dataclass may need a `balance_after_micros` field added. Update `ubb/types.py` accordingly.

**Step 4: Update types if needed**

Add `balance_after_micros` to `RecordUsageResult` in `ubb-sdk/ubb/types.py`:

```python
@dataclass(frozen=True)
class RecordUsageResult:
    event_id: str
    new_balance_micros: int
    suspended: bool
    provider_cost_micros: int | None = None
    billed_cost_micros: int | None = None
    balance_after_micros: int | None = None  # Set when billing is enabled
```

**Step 5: Run tests**

```bash
cd ubb-sdk && python -m pytest tests/test_orchestration.py -v
```
Expected: PASS

**Step 6: Run full SDK tests**

```bash
cd ubb-sdk && python -m pytest --tb=short -q
```

**Step 7: Commit**

```bash
git add ubb-sdk/ubb/client.py ubb-sdk/ubb/types.py ubb-sdk/tests/test_orchestration.py
git commit -m "feat: update UBBClient with product-specific clients and SDK orchestration"
```

---

### Task 25: Audit and remove cross-product imports

Verify that metering code never imports from billing code, and vice versa. Both can import from platform.

**Files:**
- No new files — this is an audit and cleanup task

**Step 1: Search for cross-product imports**

```bash
# Metering importing from billing (should find ZERO results)
cd ubb-platform && grep -rn "from apps.billing" apps/metering/ || echo "CLEAN: No metering→billing imports"

# Billing importing from metering (should find ZERO results)
grep -rn "from apps.metering" apps/billing/ || echo "CLEAN: No billing→metering imports"

# Both importing from platform is OK
grep -rn "from apps.platform" apps/metering/ apps/billing/
```

Expected: Zero cross-product imports. If any are found, refactor them out (use event bus or move to platform).

**Step 2: If cross-product imports exist, fix them**

Common fix patterns:
- If billing imports from metering to query UsageEvent: Move the query to the event bus handler (it receives the data it needs via events).
- If metering imports from billing for wallet operations: This should already be removed (wallet debit is handled by SDK orchestration or event bus).

**Step 3: Run full test suite**

```bash
cd ubb-platform && python -m pytest --tb=short -q
```

**Step 4: Commit**

```bash
git add -A
git commit -m "refactor: remove all cross-product imports between metering and billing"
```

---

### Task 26: End-to-end verification — metering-only tenant

**Files:**
- Create: `api/v1/tests/test_product_isolation.py`

**Step 1: Write integration tests**

```python
# api/v1/tests/test_product_isolation.py
import pytest


@pytest.mark.django_db
class TestMeteringOnlyTenant:
    """Verify a tenant with products=["metering"] can use metering but not billing."""

    def test_can_record_usage(self, client):
        from apps.platform.tenants.models import Tenant, TenantApiKey
        from apps.platform.customers.models import Customer

        tenant = Tenant.objects.create(name="metering-only", products=["metering"])
        key_obj, raw_key = TenantApiKey.create_key(tenant=tenant, label="test")
        customer = Customer.objects.create(tenant=tenant, external_id="cust-1")
        customer.wallet.balance_micros = 100_000_000
        customer.wallet.save()

        response = client.post(
            "/api/v1/metering/usage",
            content_type="application/json",
            data={
                "customer_id": "cust-1",
                "request_id": "req-1",
                "idempotency_key": "idem-1",
                "cost_micros": 1_000_000,
            },
            HTTP_AUTHORIZATION=f"Bearer {raw_key}",
        )
        assert response.status_code == 200

    def test_cannot_access_billing(self, client):
        from apps.platform.tenants.models import Tenant, TenantApiKey
        from apps.platform.customers.models import Customer

        tenant = Tenant.objects.create(name="metering-only", products=["metering"])
        key_obj, raw_key = TenantApiKey.create_key(tenant=tenant, label="test")
        customer = Customer.objects.create(tenant=tenant, external_id="cust-1")

        response = client.get(
            f"/api/v1/billing/customers/cust-1/balance",
            HTTP_AUTHORIZATION=f"Bearer {raw_key}",
        )
        assert response.status_code == 403


@pytest.mark.django_db
class TestBillingOnlyTenant:
    """Verify a tenant with products=["billing"] can use billing but not metering."""

    def test_can_access_balance(self, client):
        from apps.platform.tenants.models import Tenant, TenantApiKey
        from apps.platform.customers.models import Customer

        tenant = Tenant.objects.create(name="billing-only", products=["billing"])
        key_obj, raw_key = TenantApiKey.create_key(tenant=tenant, label="test")
        customer = Customer.objects.create(tenant=tenant, external_id="cust-1")

        response = client.get(
            f"/api/v1/billing/customers/cust-1/balance",
            HTTP_AUTHORIZATION=f"Bearer {raw_key}",
        )
        assert response.status_code == 200

    def test_cannot_access_metering(self, client):
        from apps.platform.tenants.models import Tenant, TenantApiKey

        tenant = Tenant.objects.create(name="billing-only", products=["billing"])
        key_obj, raw_key = TenantApiKey.create_key(tenant=tenant, label="test")

        response = client.post(
            "/api/v1/metering/usage",
            content_type="application/json",
            data={},
            HTTP_AUTHORIZATION=f"Bearer {raw_key}",
        )
        assert response.status_code == 403


@pytest.mark.django_db
class TestBothProductsTenant:
    """Verify a tenant with both products can use everything."""

    def test_can_access_metering_and_billing(self, client):
        from apps.platform.tenants.models import Tenant, TenantApiKey
        from apps.platform.customers.models import Customer

        tenant = Tenant.objects.create(
            name="full-platform", products=["metering", "billing"]
        )
        key_obj, raw_key = TenantApiKey.create_key(tenant=tenant, label="test")
        customer = Customer.objects.create(tenant=tenant, external_id="cust-1")
        customer.wallet.balance_micros = 100_000_000
        customer.wallet.save()

        # Metering works
        response = client.post(
            "/api/v1/metering/usage",
            content_type="application/json",
            data={
                "customer_id": "cust-1",
                "request_id": "req-1",
                "idempotency_key": "idem-1",
                "cost_micros": 1_000_000,
            },
            HTTP_AUTHORIZATION=f"Bearer {raw_key}",
        )
        assert response.status_code == 200

        # Billing works
        response = client.get(
            f"/api/v1/billing/customers/cust-1/balance",
            HTTP_AUTHORIZATION=f"Bearer {raw_key}",
        )
        assert response.status_code == 200
```

**Step 2: Run tests**

```bash
cd ubb-platform && python -m pytest api/v1/tests/test_product_isolation.py -v
```
Expected: All pass.

**Step 3: Commit**

```bash
git add api/v1/tests/test_product_isolation.py
git commit -m "test: add end-to-end product isolation tests"
```

---

### Task 27: Final cleanup and documentation

**Step 1: Run full test suite one final time**

```bash
cd ubb-platform && python -m pytest --tb=short -q
cd ubb-sdk && python -m pytest --tb=short -q
```
Expected: All tests pass.

**Step 2: Verify Django checks pass**

```bash
cd ubb-platform && python manage.py check
python manage.py makemigrations --check --dry-run
```

**Step 3: Verify import boundaries**

```bash
cd ubb-platform
grep -rn "from apps.billing" apps/metering/ && echo "FAIL: cross-product import found" || echo "PASS: metering clean"
grep -rn "from apps.metering" apps/billing/ && echo "FAIL: cross-product import found" || echo "PASS: billing clean"
```

**Step 4: Commit**

```bash
git add -A
git commit -m "chore: finalize two-product separation — all phases complete"
```

---

## Summary

| Phase | Tasks | Description |
|-------|-------|-------------|
| **Phase 1** | Tasks 1–10 | Directory restructure (file moves, import rewrites, zero logic changes) |
| **Phase 2** | Tasks 11–16 | Event bus, `products` field, `usage.recorded` event, tenant billing handler |
| **Phase 3** | Tasks 17–21 | Product APIs (`/metering/`, `/billing/`), `ProductAccess` auth, widget updates |
| **Phase 4** | Tasks 22–27 | SDK product clients, orchestration, cross-product import cleanup, E2E tests |

**Total tasks:** 27
**Each phase is independently deployable and verifiable.**
