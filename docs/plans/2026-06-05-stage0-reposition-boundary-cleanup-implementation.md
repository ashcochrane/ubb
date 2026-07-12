> ⚠️ SUPERSEDED (pricing-engine removal only): the rate-card pricing engine this plan removed was later REINSTATED (redesigned two-card cost+price engine) — see `2026-06-08-pricing-stageA-rate-card-engine-implementation.md`. The `billing_mode` + boundary-cleanup work remains current. Master truth: `2026-06-10-program-current-state.md`.

# Stage 0 — Reposition & Boundary Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Establish the new UBB positioning on a clean base — add `Tenant.billing_mode`, decommission the dimensional rate-card pricing engine (`ProviderRate` + `PricingService` + the `usage_metrics` intake + `/pricing/rates` CRUD), and reposition docs — leaving the test suite green at every commit.

**Architecture:** Pure positioning + subtraction. No new runtime behaviour beyond the `billing_mode` field (advisory until Stage 3). Removals are ordered so each commit keeps the suite importable and green: (1) drop the `usage_metrics` intake path, (2) drop the `/pricing/rates` API, (3) delete the `ProviderRate` model + service last. The slim markup (`TenantMarkup` + `/pricing/markups`) is left untouched here and reworked in Stage 1.

**Tech Stack:** Django 6, django-ninja, pytest-django (+ Django `TestCase`), Postgres, Redis, Celery.

**Design ref:** `docs/plans/2026-06-05-stage0-reposition-boundary-cleanup-design.md`

---

## Conventions used in every task

- All commands run from `ubb-platform/` with the project venv active.
- **Test command** (`$TEST`): `DJANGO_SETTINGS_MODULE=config.settings python -m pytest --tb=short -q`
  - On Windows git-bash the venv python is `.venv/Scripts/python.exe`; on POSIX it's `.venv/bin/python`. Use whichever exists, or activate the venv so `python` resolves to it.
- **Migration check** (`$MIGCHECK`): `DJANGO_SETTINGS_MODULE=config.settings python manage.py makemigrations --check --dry-run`
- Commit after each task. Branch is `tl-changes-05-06-26` (already a feature branch — do not branch again).

---

### Task 0: Environment prerequisites & green baseline

**Files:** none (environment only).

- [ ] **Step 1: Ensure Postgres and Redis are running**

The test settings read `DATABASE_URL` (Postgres — required because migrations include a GIN index and JSON `contains` queries) and `REDIS_URL` (cache + Celery). Start both locally, e.g. Postgres on `localhost:5432` and Redis on `localhost:6379`.

- [ ] **Step 2: Create the venv and install dependencies**

```bash
python -m venv .venv
# POSIX: source .venv/bin/activate     |  Windows git-bash: source .venv/Scripts/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

- [ ] **Step 3: Create `.env` from the example**

Create `ubb-platform/.env` with at least:
```
SECRET_KEY=dev-not-secret
DEBUG=True
DATABASE_URL=postgres://user:pass@localhost:5432/ubb_platform
REDIS_URL=redis://localhost:6379/1
```
(`SECRET_KEY` is required at import; `DEBUG=True` avoids the `ALLOWED_HOSTS` requirement. Match `DATABASE_URL`/`REDIS_URL` to your local services. `.env` is gitignored.)

- [ ] **Step 4: Apply migrations and run the full suite to capture a green baseline**

Run: `DJANGO_SETTINGS_MODULE=config.settings python manage.py migrate`
Run: `$TEST`
Expected: all tests pass (this is the baseline; if anything fails here it is pre-existing and must be understood before proceeding).

- [ ] **Step 5: Confirm migration state is clean**

Run: `$MIGCHECK`
Expected: "No changes detected".

---

### Task 1: Add `Tenant.billing_mode`

**Files:**
- Modify: `apps/platform/tenants/models.py`
- Create: `apps/platform/tenants/migrations/0008_add_billing_mode.py`
- Test: `apps/platform/tenants/tests/test_billing_mode.py`

- [ ] **Step 1: Write the failing tests**

Create `apps/platform/tenants/tests/test_billing_mode.py`:
```python
import pytest
from django.core.exceptions import ValidationError

from apps.platform.tenants.models import Tenant


@pytest.mark.django_db
class TestTenantBillingMode:
    def test_default_is_meter_only(self):
        t = Tenant.objects.create(name="T", products=["metering"])
        assert t.billing_mode == "meter_only"

    def test_prepaid_requires_billing_product(self):
        t = Tenant(name="T", products=["metering"], billing_mode="prepaid")
        with pytest.raises(ValidationError, match="billing"):
            t.full_clean(exclude=["branding_config", "metadata"])

    def test_postpaid_requires_billing_product(self):
        t = Tenant(name="T", products=["metering"], billing_mode="postpaid")
        with pytest.raises(ValidationError, match="billing"):
            t.full_clean(exclude=["branding_config", "metadata"])

    def test_prepaid_with_billing_product_valid(self):
        t = Tenant(name="T", products=["metering", "billing"], billing_mode="prepaid")
        t.full_clean(exclude=["branding_config", "metadata"])  # no raise

    def test_meter_only_with_billing_product_allowed(self):
        # meter_only does not constrain products (advisory until Stage 3); must not
        # break the existing metering+billing tenant fixtures.
        t = Tenant(name="T", products=["metering", "billing"], billing_mode="meter_only")
        t.full_clean(exclude=["branding_config", "metadata"])  # no raise
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `$TEST apps/platform/tenants/tests/test_billing_mode.py`
Expected: FAIL — `billing_mode` is not a field yet (`TypeError`/`FieldError`).

- [ ] **Step 3: Add the field, choices, and validation**

In `apps/platform/tenants/models.py`, add the choices constant near the top (after `VALID_PRODUCTS`):
```python
BILLING_MODE_CHOICES = [
    ("meter_only", "Meter only"),
    ("prepaid", "Prepaid credits"),
    ("postpaid", "Postpaid"),
]
```
Add the field on `Tenant` (immediately after the `products` field, line ~29):
```python
    billing_mode = models.CharField(
        max_length=20, choices=BILLING_MODE_CHOICES, default="meter_only", db_index=True
    )
```
Extend `Tenant.clean()` (after the existing `unknown` products check):
```python
        if self.billing_mode in ("prepaid", "postpaid") and "billing" not in (self.products or []):
            raise ValidationError(
                {"billing_mode": f"billing_mode '{self.billing_mode}' requires 'billing' in products."}
            )
```

- [ ] **Step 4: Create the migration (field + backfill)**

Create `apps/platform/tenants/migrations/0008_add_billing_mode.py`:
```python
from django.db import migrations, models


def backfill_billing_mode(apps, schema_editor):
    Tenant = apps.get_model("tenants", "Tenant")
    for tenant in Tenant.objects.all():
        tenant.billing_mode = "prepaid" if "billing" in (tenant.products or []) else "meter_only"
        tenant.save(update_fields=["billing_mode"])


class Migration(migrations.Migration):
    dependencies = [("tenants", "0007_rename_arrears_to_min_balance")]

    operations = [
        migrations.AddField(
            model_name="tenant",
            name="billing_mode",
            field=models.CharField(
                choices=[
                    ("meter_only", "Meter only"),
                    ("prepaid", "Prepaid credits"),
                    ("postpaid", "Postpaid"),
                ],
                db_index=True,
                default="meter_only",
                max_length=20,
            ),
        ),
        migrations.RunPython(backfill_billing_mode, migrations.RunPython.noop),
    ]
```

- [ ] **Step 5: Run the tests to verify they pass + migration check**

Run: `$TEST apps/platform/tenants/tests/test_billing_mode.py`
Expected: PASS (5 tests).
Run: `$MIGCHECK`
Expected: "No changes detected".
Run: `$TEST apps/platform/tenants/`
Expected: PASS (existing `test_products_validation.py` still green — `test_valid_products` unaffected because `meter_only` does not constrain products).

- [ ] **Step 6: Commit**

```bash
git add apps/platform/tenants/models.py apps/platform/tenants/migrations/0008_add_billing_mode.py apps/platform/tenants/tests/test_billing_mode.py
git commit -m "feat(tenants): add billing_mode (meter_only/prepaid/postpaid)"
```

---

### Task 2: Remove the `usage_metrics` (rate-card) intake path

Removes the "platform prices it" mode from the request schema, the service, and the endpoint, plus the tests that exercised it. `PricingService`/`ProviderRate` still exist after this task (deleted in Task 4), so `test_pricing_service.py` stays green.

**Files:**
- Modify: `api/v1/schemas.py` (`RecordUsageRequest`)
- Modify: `apps/metering/usage/services/usage_service.py`
- Modify: `api/v1/metering_endpoints.py` (`record_usage`)
- Modify: `apps/metering/usage/tests/test_usage_service.py`

- [ ] **Step 1: Rewrite `RecordUsageRequest`**

In `api/v1/schemas.py`, replace the `RecordUsageRequest` class (lines 24–73) with:
```python
class RecordUsageRequest(Schema):
    customer_id: UUID
    request_id: str = Field(min_length=1, max_length=500)
    idempotency_key: str = Field(min_length=1, max_length=500)
    metadata: dict = Field(default_factory=dict)
    cost_micros: int = Field(gt=0, le=999_999_999_999)
    group_keys: Optional[dict[str, str]] = None
    run_id: Optional[UUID] = None
    # Descriptive dimensions (not pricing inputs)
    event_type: Optional[str] = Field(default=None, max_length=100)
    provider: Optional[str] = Field(default=None, max_length=100)
```
(Removes `usage_metrics`, `properties`, the `usage_metrics` validator, `cost_micros_positive` no-op validator, and `validate_intake_mode`. `cost_micros` is now required.)

- [ ] **Step 2: Strip the pricing branch from the service**

In `apps/metering/usage/services/usage_service.py`:
- Remove `usage_metrics=None` and `properties=None` from the `record_usage` signature (lines 47–48).
- Delete the pricing block (lines 72–88: the `provider_cost_micros = None ... cost_micros = billed_cost_micros` section including the `from apps.metering.pricing.services.pricing_service import PricingService` import and the `PricingService.price_event(...)` call). Replace with:
```python
        provider_cost_micros = None
        billed_cost_micros = None
        pricing_provenance = {}
```
- In the `UsageEvent.objects.create(...)` call, remove the `usage_metrics=usage_metrics or {}` and `properties=properties or {}` keyword arguments (the model fields default to `{}`).

- [ ] **Step 3: Update the endpoint**

In `api/v1/metering_endpoints.py`, in `record_usage`:
- Remove the `from apps.metering.pricing.services.pricing_service import PricingError` import (line 33).
- Remove `usage_metrics=payload.usage_metrics,` and `properties=payload.properties,` from the `UsageService.record_usage(...)` call (lines 47–48).
- Remove the `except PricingError as e:` arm (lines 69–71). Keep the `except ValueError` arm (it still catches `validate_group_keys` errors).

- [ ] **Step 4: Remove the metric-pricing tests**

In `apps/metering/usage/tests/test_usage_service.py`:
- Delete the entire `UsageServicePricingTest` class (lines 151–268).
- In `UsageServiceEventEmissionTest`, delete the method `test_record_usage_writes_billed_cost_for_priced_events` (lines 298–324).
- Change the import on line 7 from `from apps.metering.pricing.models import ProviderRate, TenantMarkup` to remove it entirely (neither is used after the deletions above).

- [ ] **Step 5: Run the affected tests + full suite**

Run: `$TEST apps/metering/usage/ api/v1/tests/test_metering_endpoints.py`
Expected: PASS (the surviving cost_micros / run / emission tests).
Run: `$TEST`
Expected: PASS (whole suite; `test_pricing_service.py` still green since the service still exists).

- [ ] **Step 6: Commit**

```bash
git add api/v1/schemas.py apps/metering/usage/services/usage_service.py api/v1/metering_endpoints.py apps/metering/usage/tests/test_usage_service.py
git commit -m "refactor(metering): remove usage_metrics rate-card intake; caller provides cost"
```

---

### Task 3: Remove the `/pricing/rates` CRUD API

**Files:**
- Modify: `api/v1/metering_endpoints.py`
- Modify: `api/v1/schemas.py`
- Modify: `api/v1/tests/test_metering_endpoints.py`

- [ ] **Step 1: Delete the rates endpoints**

In `api/v1/metering_endpoints.py`:
- Delete `_rate_to_out` (lines 149–161) and the four rate endpoints `list_rates`, `create_rate`, `update_rate`, `delete_rate` (lines 164–229), including the `# --- Pricing Rates CRUD ---` header.
- In the top imports (lines 11–18), remove `ProviderRateIn, ProviderRateOut,` from the `api.v1.schemas` import. Keep `TenantMarkupIn, TenantMarkupOut` (markup endpoints remain).

- [ ] **Step 2: Delete the rate schemas**

In `api/v1/schemas.py`, delete `ProviderRateIn` (lines 175–183) and `ProviderRateOut` (lines 185–196). Keep `TenantMarkupIn`/`TenantMarkupOut`.

- [ ] **Step 3: Delete the rates endpoint tests**

In `api/v1/tests/test_metering_endpoints.py`:
- Delete the entire `PricingRatesCRUDTest` class (lines 75–162).
- Change the import on line 12 from `from apps.metering.pricing.models import ProviderRate, TenantMarkup` to `from apps.metering.pricing.models import TenantMarkup` (`TenantMarkup` is still used by `PricingMarkupsCRUDTest`).

- [ ] **Step 4: Run tests**

Run: `$TEST api/v1/tests/test_metering_endpoints.py`
Expected: PASS (markup CRUD, run, analytics, gating tests survive).
Run: `$TEST`
Expected: PASS (whole suite).

- [ ] **Step 5: Commit**

```bash
git add api/v1/metering_endpoints.py api/v1/schemas.py api/v1/tests/test_metering_endpoints.py
git commit -m "refactor(metering): remove /pricing/rates CRUD endpoints"
```

---

### Task 4: Delete the `ProviderRate` model, the pricing service, and drop the table

**Files:**
- Delete: `apps/metering/pricing/services/pricing_service.py`
- Delete: `apps/metering/pricing/tests/test_pricing_service.py`
- Modify: `apps/metering/pricing/models.py`
- Modify: `apps/metering/pricing/admin.py`
- Modify: `apps/metering/pricing/tests/test_models.py`
- Create: `apps/metering/pricing/migrations/0005_delete_providerrate.py`

- [ ] **Step 1: Delete the pricing service and its tests**

```bash
git rm apps/metering/pricing/services/pricing_service.py apps/metering/pricing/tests/test_pricing_service.py
```
(`apps/metering/pricing/services/__init__.py` remains — Stage 1 adds `MarkupService` here.)

- [ ] **Step 2: Remove `ProviderRate` from the model module**

In `apps/metering/pricing/models.py`:
- Delete the `ProviderRate` class (lines 9–49).
- Remove the now-unused imports `import hashlib` and `import json` (they were only used by `ProviderRate.save`). Keep `from django.db import models` and `from core.models import BaseModel`.
- Keep `TenantMarkup` unchanged.

- [ ] **Step 3: Remove `ProviderRate` from admin**

In `apps/metering/pricing/admin.py`:
- Remove `ProviderRate` from the import (line 3 → `from apps.metering.pricing.models import TenantMarkup`).
- Delete the `ProviderRateAdmin` registration (lines 6–19). Keep `TenantMarkupAdmin`.

- [ ] **Step 4: Remove `ProviderRate` model tests**

In `apps/metering/pricing/tests/test_models.py`:
- Delete the `ProviderRateTests` class (lines 10–63).
- Remove the unused imports `import hashlib`, `import json`, and change line 6 to `from apps.metering.pricing.models import TenantMarkup`. Keep `TenantMarkupTests`.

- [ ] **Step 5: Create the drop-table migration**

Create `apps/metering/pricing/migrations/0005_delete_providerrate.py`:
```python
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("pricing", "0004_add_markup_composite_index")]

    operations = [
        migrations.DeleteModel(name="ProviderRate"),
    ]
```

- [ ] **Step 6: Verify no dangling references remain**

Run: `git grep -nE "ProviderRate|PricingService|price_event|PricingError|usage_metrics" -- 'apps' 'api' 'config' 'core'`
Expected: **no matches** in non-migration source (historical migrations `0001`–`0004` under `pricing/migrations/` legitimately still mention `ProviderRate` and are NOT edited).

- [ ] **Step 7: Run migration check and full suite**

Run: `$MIGCHECK`
Expected: "No changes detected".
Run: `DJANGO_SETTINGS_MODULE=config.settings python manage.py migrate`
Expected: applies `pricing.0005` cleanly (drops `ubb_provider_rate`).
Run: `$TEST`
Expected: PASS (whole suite).

- [ ] **Step 8: Commit**

```bash
git add apps/metering/pricing/models.py apps/metering/pricing/admin.py apps/metering/pricing/tests/test_models.py apps/metering/pricing/migrations/0005_delete_providerrate.py
git commit -m "refactor(metering): delete ProviderRate model and pricing engine"
```

---

### Task 5: Reposition docs & add deprecation markers

**Files:**
- Modify: `README.md` (repo root)
- Create: `docs/architecture/positioning.md`
- Modify: `apps/billing/wallets/__init__.py`, `apps/billing/topups/__init__.py`, `apps/billing/invoicing/__init__.py`
- Modify: `apps/subscriptions/__init__.py`

- [ ] **Step 1: Rewrite the README**

Replace `README.md` contents with:
```markdown
# UBB

Usage, spend-control, and margin infrastructure for AI applications — the layer
between an AI app and Stripe.

- **UBB owns:** usage metering, real-time spend control, provider-cost &
  billed-cost tracking, customer margin analytics, and (for billing tenants)
  prepaid credit drawdown / period-close Stripe line-item push.
- **Stripe owns:** invoicing, payment collection, tax, dunning, customer portal,
  refunds, disputes, and subscription/seat lifecycle.

See `docs/architecture/positioning.md` and `docs/plans/2026-06-05-ubb-repositioning-design.md`.
```

- [ ] **Step 2: Add the positioning doc**

Create `docs/architecture/positioning.md` summarising the UBB/Stripe boundary and the three tenant modes (`meter_only`, `prepaid`, `postpaid`), referencing the program design. Content (verbatim):
```markdown
# UBB Positioning & Tenant Modes

UBB is the usage, spend-control, and margin layer in front of Stripe. It never
moves money out and never holds cash; it maintains a credit ledger that mirrors
money Stripe has already collected.

## Tenant modes (`Tenant.billing_mode`)
- **meter_only** — track usage + provider/billed cost + dimensional tags + margin. No money, no gate.
- **prepaid** — meter + prepaid credit ledger + real-time spend gate + auto-top-up. Requires the `billing` product.
- **postpaid** — meter + period-close Stripe invoice line-item push. Requires the `billing` product.

## Boundary
UBB owns everything up to invoice line items / credit drawdown. Stripe owns
invoicing, payments, tax, dunning, portal, refunds, disputes, and subscription/
seat lifecycle. Full detail: docs/plans/2026-06-05-ubb-repositioning-design.md.
```

- [ ] **Step 3: Add deprecation/repositioning docstrings**

Prepend a module docstring to each of these `__init__.py` files (create the docstring at the top; preserve any existing content below):

`apps/billing/wallets/__init__.py`:
```python
"""Wallets — to be REFRAMED in Stage 3 as the prepaid credit ledger.

Do not extend the prepaid-balance-as-custody model. See
docs/plans/2026-06-05-ubb-repositioning-design.md.
"""
```
`apps/billing/topups/__init__.py`:
```python
"""Top-ups — to be REFRAMED in Stage 3 as Stripe-funded top-up + auto-top-up.

See docs/plans/2026-06-05-ubb-repositioning-design.md.
"""
```
`apps/billing/invoicing/__init__.py`:
```python
"""Native invoice/receipt generation — to be DELETED in Stage 3 (Stripe issues
receipts). Do not extend. See docs/plans/2026-06-05-ubb-repositioning-design.md.
"""
```
`apps/subscriptions/__init__.py`:
```python
"""Subscriptions — RETAINED as the read-only Stripe revenue mirror feeding
margin (Stage 2). Do not add subscription lifecycle management here; Stripe owns
the lifecycle. See docs/plans/2026-06-05-ubb-repositioning-design.md.
"""
```

- [ ] **Step 4: Verify nothing imports broke and suite is green**

Run: `$TEST`
Expected: PASS (docstrings are inert).

- [ ] **Step 5: Commit**

```bash
git add README.md docs/architecture/positioning.md apps/billing/wallets/__init__.py apps/billing/topups/__init__.py apps/billing/invoicing/__init__.py apps/subscriptions/__init__.py
git commit -m "docs: reposition UBB and mark billing-overlap apps for their stage"
```

---

### Task 6: Final verification

**Files:** none (verification only).

- [ ] **Step 1: Migration state clean**

Run: `$MIGCHECK`
Expected: "No changes detected".

- [ ] **Step 2: Fresh-DB migrate + full suite**

Run: `DJANGO_SETTINGS_MODULE=config.settings python manage.py migrate`
Run: `$TEST`
Expected: all tests pass.

- [ ] **Step 3: Confirm removed symbols are gone from source**

Run: `git grep -nE "ProviderRate|PricingService|price_event|PricingError|usage_metrics|properties=payload" -- 'apps' 'api' 'core' 'config'`
Expected: no matches outside `apps/metering/pricing/migrations/0001`–`0004` (historical migrations are intentionally untouched).

- [ ] **Step 4: Confirm `billing_mode` is present and validated**

Run: `$TEST apps/platform/tenants/tests/test_billing_mode.py apps/platform/tenants/tests/test_products_validation.py`
Expected: PASS.

---

## Self-Review

**Spec coverage (vs. Stage 0 design):**
- `Tenant.billing_mode` + validation + migration + backfill → Task 1. ✓
- Remove `ProviderRate` (model, migrations, admin) → Task 4. ✓
- Remove `PricingService.price_event`/service module → Task 4. ✓
- Remove `usage_metrics` intake (schema, service, endpoint) → Task 2. ✓
- Remove `/pricing/rates` CRUD + `ProviderRateIn/Out` → Task 3. ✓
- Keep `TenantMarkup` + `/pricing/markups` (reworked in Stage 1) → untouched across all tasks. ✓
- Docs/README reposition + deprecation markers; subscriptions retained note → Task 5. ✓
- Suite green at every commit → ordering Task 2→3→4 keeps `PricingService` importable until its last consumer is removed. ✓

**Placeholder scan:** No TBD/TODO; every code/edit step shows exact content and line ranges; every run step states expected output. ✓

**Type/name consistency:** `billing_mode` choices identical in model and migration; `BILLING_MODE_CHOICES` values (`meter_only`/`prepaid`/`postpaid`) match the validation rule and tests; `TenantMarkup` import retained exactly where still used (`test_metering_endpoints.py`, `test_models.py`). ✓

**Known external dependency:** Tasks require a provisioned environment (venv + deps + Postgres + Redis + `.env`) — Task 0. If the environment cannot be stood up, the edits are still correct but the per-step test runs cannot be executed; surface that rather than claiming green.
