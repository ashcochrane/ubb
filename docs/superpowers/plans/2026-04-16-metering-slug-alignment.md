# Metering Slug Alignment & Explicit-Rate Pricing — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Align backend, SDK, and UI on slug-as-primary-identifier for pricing cards, and replace runtime margin resolution with explicit tenant-facing rates stored directly on each Rate row.

**Architecture:**
- Pricing shifts from `(event_type, provider, dimensions)` + runtime margin cascade → `slug` + explicit `cost_per_unit_micros` on each Rate. Margin becomes a creation-time UX convenience, not runtime logic.
- `UsageEvent` carries immutable snapshots (`card_slug`, `card_name`, `provider`) so historical events survive card renames/archives.
- `TenantMarkup` is deleted. Margin fallback pre-fills in the UI form only: `group.margin_pct → tenant.default_margin_pct`.
- UI `Dimension` becomes the wire-level name for what the backend called `Rate`. UI field names (`slug`, `groupId`, `pricingType`) become canonical.

**Tech Stack:** Django 6.0, django-ninja, PostgreSQL, Pydantic, pytest, React 19, Vite, TanStack Query, TypeScript, openapi-typescript, httpx (SDK).

**Pre-flight:**
- Run from repo root `/Users/ashtoncochrane/Git/localscouta/ubb`.
- Tests use `.venv/bin/python` in `ubb-platform/`.
- UI uses `pnpm` in `ubb-ui/`.
- SDK uses `uv`/`pytest` in `ubb-sdk/`.
- There is no `pytest.ini` — you must set `DJANGO_SETTINGS_MODULE=config.settings` on every invocation.

**Known drift from the CSV decisions (flagged for user confirmation before execution):**
- CSV row "Rate.Metric key" said **"Use 'key' on both"**. This plan uses `metric_name` / `metricName` throughout for three practical reasons: (a) `key` is a reserved React prop name and collides in TSX, (b) SQL standard reserves `KEY`, (c) matches the existing DB column. If the user wants strict adherence to the CSV, add a follow-up task to rename the field (use Django's `db_column` to keep the underlying column name stable, alias Pydantic field to emit `key`, and rename the TS field). Otherwise proceed with `metricName`.

---

## File Map

**Backend — Data layer**
- Modify `ubb-platform/apps/platform/tenants/models.py` — add `default_margin_pct`
- Create `ubb-platform/apps/platform/tenants/migrations/0011_tenant_default_margin_pct.py`
- Modify `ubb-platform/apps/metering/pricing/models.py` — add `Rate.provider_cost_per_unit_micros`; drop `Card.event_type`, `Card.dimensions`, `Card.dimensions_hash`; delete `TenantMarkup`
- Create `ubb-platform/apps/metering/pricing/migrations/0009_rate_provider_cost.py`
- Create `ubb-platform/apps/metering/pricing/migrations/0010_drop_card_legacy_fields.py`
- Create `ubb-platform/apps/metering/pricing/migrations/0011_backfill_rate_provider_cost.py` (data migration)
- Create `ubb-platform/apps/metering/pricing/migrations/0012_delete_tenantmarkup.py`
- Modify `ubb-platform/apps/metering/usage/models.py` — add `card_slug`, `card_name`; drop `event_type`
- Create `ubb-platform/apps/metering/usage/migrations/0018_usageevent_card_snapshot_fields.py`
- Create `ubb-platform/apps/metering/usage/migrations/0019_backfill_card_snapshots.py` (data migration)
- Create `ubb-platform/apps/metering/usage/migrations/0020_drop_usageevent_event_type.py`

**Backend — Services**
- Rewrite `ubb-platform/apps/metering/pricing/services/pricing_service.py`
- Modify `ubb-platform/apps/metering/usage/services/usage_service.py`
- Delete or trim `ubb-platform/apps/metering/pricing/admin.py` (drop TenantMarkup admin)

**Backend — API**
- Modify `ubb-platform/api/v1/schemas.py`
- Modify `ubb-platform/api/v1/metering_endpoints.py` — drop markup CRUD, require pricing_card, update `_card_to_out`
- Modify `ubb-platform/api/v1/platform_endpoints.py` — tenant default margin endpoint; EventOut snapshot fields

**Backend — Tests**
- Modify `ubb-platform/apps/metering/pricing/tests/test_models.py`
- Delete `ubb-platform/apps/metering/pricing/tests/test_pricing_service.py` (legacy; replaced)
- Rewrite `ubb-platform/apps/metering/pricing/tests/test_pricing_service_v2.py`
- Modify `ubb-platform/apps/metering/pricing/tests/test_card_rate.py`
- Modify `ubb-platform/apps/metering/usage/tests/test_models.py`
- Modify `ubb-platform/apps/metering/usage/tests/test_usage_service.py`
- Modify `ubb-platform/api/v1/tests/test_metering_endpoints.py`
- Modify `ubb-platform/api/v1/tests/test_event_endpoints.py`
- Modify `ubb-platform/api/v1/tests/test_dashboard_endpoints.py`

**SDK**
- Modify `ubb-sdk/ubb/metering.py` — `record_usage` signature
- Modify `ubb-sdk/ubb/types.py` — UsageEvent + new CardSummary fields
- Modify `ubb-sdk/tests/test_metering_client.py`

**UI — Feature types & data**
- Rewrite `ubb-ui/src/features/pricing-cards/api/types.ts`
- Rewrite `ubb-ui/src/features/pricing-cards/api/api.ts`
- Modify `ubb-ui/src/features/pricing-cards/api/mock.ts`, `mock-data.ts`
- Modify `ubb-ui/src/features/pricing-cards/lib/schema.ts`
- Modify `ubb-ui/src/features/pricing-cards/components/*.tsx` (wizard, simulators, review)
- Rewrite `ubb-ui/src/features/events/api/types.ts`
- Modify `ubb-ui/src/features/events/api/api.ts`, `mock.ts`, `mock-data.ts`
- Modify `ubb-ui/src/features/events/components/*.tsx`
- Rewrite `ubb-ui/src/features/dashboard/api/types.ts` (split into 3 responses)
- Rewrite `ubb-ui/src/features/dashboard/api/api.ts` (3 parallel calls)
- Modify `ubb-ui/src/features/dashboard/api/mock.ts`, `mock-data.ts`
- Modify `ubb-ui/src/features/dashboard/components/*.tsx`

**UI — Regenerated artifacts**
- Regenerate `ubb-ui/src/api/schemas/*.json` + `ubb-ui/src/api/generated/*.ts`

---

## Dependency Graph

```
Phase 1 (data model)  →  Phase 2 (services)  →  Phase 3 (API contract)
                                                     ↓
Phase 4 (SDK)  ←  Phase 3
                                                     ↓
Phase 5 (UI)  ←  Phase 3 + Phase 4
                                                     ↓
Phase 6 (integration/smoke)
```

Each phase must pass tests before the next begins.

---

## Phase 1 — Data Model

### Task 1: Add `Tenant.default_margin_pct`

**Files:**
- Modify: `ubb-platform/apps/platform/tenants/models.py:13-30`
- Create: `ubb-platform/apps/platform/tenants/migrations/0011_tenant_default_margin_pct.py`
- Test: `ubb-platform/apps/platform/tenants/tests/test_models.py` (create if not present)

- [x] **Step 1: Write failing test**

Add to `ubb-platform/apps/platform/tenants/tests/test_models.py` (create the file if missing, with the standard imports at the top):

```python
from decimal import Decimal

import pytest
from django.db import IntegrityError

from apps.platform.tenants.models import Tenant


@pytest.mark.django_db
class TestTenantDefaultMargin:
    def test_defaults_to_zero(self):
        tenant = Tenant.objects.create(name="Acme", products=["metering"])
        assert tenant.default_margin_pct == Decimal("0.00")

    def test_accepts_percentage(self):
        tenant = Tenant.objects.create(
            name="Acme", products=["metering"], default_margin_pct=Decimal("25.00"),
        )
        tenant.refresh_from_db()
        assert tenant.default_margin_pct == Decimal("25.00")
```

- [x] **Step 2: Run tests to verify they fail**

```
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/platform/tenants/tests/test_models.py::TestTenantDefaultMargin -v
```

Expected: FAIL with `AttributeError: 'Tenant' object has no attribute 'default_margin_pct'`.

- [x] **Step 3: Add field to Tenant model**

Edit `ubb-platform/apps/platform/tenants/models.py`, inside `class Tenant(BaseModel):` — insert before `class Meta:`:

```python
    default_margin_pct = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        help_text="UX default margin % for new cards. 0 = pass-through. Not used at runtime.",
    )
```

- [x] **Step 4: Generate and apply migration**

```
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python manage.py makemigrations tenants --name tenant_default_margin_pct
DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python manage.py migrate tenants
```

Expected: new file `apps/platform/tenants/migrations/0011_tenant_default_margin_pct.py`, applied successfully.

- [x] **Step 5: Run tests to verify they pass**

```
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/platform/tenants/tests/test_models.py::TestTenantDefaultMargin -v
```

Expected: 2 passed.

- [x] **Step 6: Run full tenants test module to check no regressions**

```
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/platform/tenants/ -v
```

Expected: all tests pass.

- [x] **Step 7: Commit**

```
git add ubb-platform/apps/platform/tenants/models.py \
        ubb-platform/apps/platform/tenants/migrations/0011_tenant_default_margin_pct.py \
        ubb-platform/apps/platform/tenants/tests/test_models.py
git commit -m "feat(tenants): add default_margin_pct for UX-default card margin"
```

---

### Task 2: Add `Rate.provider_cost_per_unit_micros`

**Files:**
- Modify: `ubb-platform/apps/metering/pricing/models.py:63-98`
- Create: `ubb-platform/apps/metering/pricing/migrations/0009_rate_provider_cost.py`
- Test: `ubb-platform/apps/metering/pricing/tests/test_models.py`

- [x] **Step 1: Write failing test**

Append to `ubb-platform/apps/metering/pricing/tests/test_models.py`:

```python
class RateProviderCostTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="T", products=["metering"])
        self.card = Card.objects.create(
            tenant=self.tenant, name="C", slug="c",
            provider="openai", event_type="llm_call",
        )

    def test_provider_cost_defaults_to_null(self):
        rate = Rate.objects.create(
            card=self.card, metric_name="input_tokens",
            cost_per_unit_micros=1_000, unit_quantity=1_000_000,
        )
        self.assertIsNone(rate.provider_cost_per_unit_micros)

    def test_provider_cost_can_be_set(self):
        rate = Rate.objects.create(
            card=self.card, metric_name="output_tokens",
            cost_per_unit_micros=1_500, provider_cost_per_unit_micros=1_000,
            unit_quantity=1_000_000,
        )
        rate.refresh_from_db()
        self.assertEqual(rate.provider_cost_per_unit_micros, 1_000)
        self.assertEqual(rate.cost_per_unit_micros, 1_500)
```

If `test_models.py` doesn't already import `Tenant`/`Card`/`Rate`, add the imports at the top.

- [x] **Step 2: Run tests to verify they fail**

```
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/metering/pricing/tests/test_models.py::RateProviderCostTest -v
```

Expected: FAIL with `TypeError: Rate() got unexpected keyword argument 'provider_cost_per_unit_micros'` or `AttributeError`.

- [x] **Step 3: Add field to Rate model**

Edit `ubb-platform/apps/metering/pricing/models.py`, inside `class Rate(BaseModel):` — insert after the `cost_per_unit_micros` field:

```python
    provider_cost_per_unit_micros = models.BigIntegerField(null=True, blank=True)
```

- [x] **Step 4: Generate and apply migration**

```
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python manage.py makemigrations pricing --name rate_provider_cost
DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python manage.py migrate pricing
```

- [x] **Step 5: Run tests**

```
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/metering/pricing/tests/test_models.py::RateProviderCostTest -v
```

Expected: 2 passed.

- [x] **Step 6: Commit**

```
git add ubb-platform/apps/metering/pricing/models.py \
        ubb-platform/apps/metering/pricing/migrations/0009_rate_provider_cost.py \
        ubb-platform/apps/metering/pricing/tests/test_models.py
git commit -m "feat(pricing): add Rate.provider_cost_per_unit_micros for margin analytics"
```

---

### Task 3: Backfill provider cost from historical margin, then freeze tenant-facing prices

**Purpose:** For existing rows, snapshot the current effective price into `cost_per_unit_micros` (applying the currently-resolved margin) and copy the old value into `provider_cost_per_unit_micros`. After this migration, the runtime margin resolver goes away; every Rate carries the final billed price.

**Files:**
- Create: `ubb-platform/apps/metering/pricing/migrations/0010_backfill_rate_provider_cost.py`

- [x] **Step 1: Write the data migration**

Create `ubb-platform/apps/metering/pricing/migrations/0010_backfill_rate_provider_cost.py`:

```python
"""Snapshot resolved margins into explicit Rate.cost_per_unit_micros.

Before this migration: rate.cost_per_unit_micros held provider cost; margin
was applied at runtime via TenantMarkup + Group.margin_pct cascade.

After: rate.provider_cost_per_unit_micros holds provider cost; rate.cost_per_unit_micros
holds the tenant-facing billed price (provider cost after margin).
"""

from decimal import Decimal

from django.db import migrations


def _resolve_margin(Rate, TenantMarkup, Group, rate):
    """Historical resolver, inlined so we don't depend on services code."""
    card = rate.card
    tenant = card.tenant
    base = TenantMarkup.objects.filter(tenant=tenant, valid_to__isnull=True)

    card_markup = base.filter(event_type=card.event_type, provider=card.provider).order_by("-valid_from").first()
    if card_markup:
        return card_markup.margin_pct

    et_markup = base.filter(event_type=card.event_type, provider="").order_by("-valid_from").first()
    if et_markup:
        return et_markup.margin_pct

    global_markup = base.filter(event_type="", provider="").order_by("-valid_from").first()
    if global_markup:
        return global_markup.margin_pct

    if card.group_id:
        current = card.group
        while current is not None:
            if current.margin_pct is not None:
                return current.margin_pct
            current = current.parent

    return Decimal("0")


def _apply_margin(provider_cost, margin_pct):
    if margin_pct <= 0:
        return provider_cost
    divisor = Decimal("1") - (margin_pct / Decimal("100"))
    return int((Decimal(provider_cost) / divisor).quantize(Decimal("1")))


def backfill_forward(apps, schema_editor):
    Rate = apps.get_model("pricing", "Rate")
    TenantMarkup = apps.get_model("pricing", "TenantMarkup")
    Group = apps.get_model("groups", "Group")

    for rate in Rate.objects.select_related("card", "card__tenant", "card__group").iterator():
        if rate.provider_cost_per_unit_micros is not None:
            continue  # already migrated
        provider_cost = rate.cost_per_unit_micros
        margin_pct = _resolve_margin(Rate, TenantMarkup, Group, rate)
        billed = _apply_margin(provider_cost, margin_pct)
        rate.provider_cost_per_unit_micros = provider_cost
        rate.cost_per_unit_micros = billed
        rate.save(update_fields=["provider_cost_per_unit_micros", "cost_per_unit_micros"])


def backfill_reverse(apps, schema_editor):
    Rate = apps.get_model("pricing", "Rate")
    for rate in Rate.objects.iterator():
        if rate.provider_cost_per_unit_micros is not None:
            rate.cost_per_unit_micros = rate.provider_cost_per_unit_micros
            rate.provider_cost_per_unit_micros = None
            rate.save(update_fields=["provider_cost_per_unit_micros", "cost_per_unit_micros"])


class Migration(migrations.Migration):
    dependencies = [
        ("pricing", "0009_rate_provider_cost"),
        ("groups", "0001_initial"),
    ]
    operations = [migrations.RunPython(backfill_forward, backfill_reverse)]
```

- [x] **Step 2: Apply migration**

```
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python manage.py migrate pricing
```

Expected: `Applying pricing.0010_backfill_rate_provider_cost... OK`.

- [x] **Step 3: Run full pricing suite to verify nothing broke**

```
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/metering/pricing/ -q
```

Expected: all pass (existing tests still use old semantics and should still pass; this task only runs the migration).

- [x] **Step 4: Commit**

```
git add ubb-platform/apps/metering/pricing/migrations/0010_backfill_rate_provider_cost.py
git commit -m "feat(pricing): backfill resolved margins into explicit Rate prices"
```

---

### Task 4: Add `UsageEvent.card_slug` + `card_name` snapshot fields

**Files:**
- Modify: `ubb-platform/apps/metering/usage/models.py:28-77`
- Create: `ubb-platform/apps/metering/usage/migrations/0018_usageevent_card_snapshot_fields.py`
- Test: `ubb-platform/apps/metering/usage/tests/test_models.py`

- [x] **Step 1: Write failing test**

Append to `ubb-platform/apps/metering/usage/tests/test_models.py`:

```python
class UsageEventCardSnapshotTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="T", products=["metering"])
        self.customer = Customer.objects.create(tenant=self.tenant, external_id="c1")

    def test_snapshot_fields_default_empty(self):
        event = UsageEvent.objects.create(
            tenant=self.tenant, customer=self.customer,
            request_id="r1", idempotency_key="k1", cost_micros=0,
        )
        self.assertEqual(event.card_slug, "")
        self.assertEqual(event.card_name, "")

    def test_snapshot_fields_persisted(self):
        event = UsageEvent.objects.create(
            tenant=self.tenant, customer=self.customer,
            request_id="r1", idempotency_key="k1", cost_micros=0,
            card_slug="gpt_4o", card_name="GPT-4o",
        )
        event.refresh_from_db()
        self.assertEqual(event.card_slug, "gpt_4o")
        self.assertEqual(event.card_name, "GPT-4o")
```

Ensure the imports at the top of the test file include `Tenant` and `Customer`.

- [x] **Step 2: Run tests to verify they fail**

```
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/metering/usage/tests/test_models.py::UsageEventCardSnapshotTest -v
```

Expected: FAIL — unknown kwarg `card_slug`.

- [x] **Step 3: Add fields to UsageEvent**

Edit `ubb-platform/apps/metering/usage/models.py`, inside `class UsageEvent(BaseModel):` — insert after the existing `card` FK:

```python
    card_slug = models.CharField(max_length=255, blank=True, default="", db_index=True)
    card_name = models.CharField(max_length=255, blank=True, default="")
```

- [x] **Step 4: Generate and apply migration**

```
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python manage.py makemigrations usage --name usageevent_card_snapshot_fields
DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python manage.py migrate usage
```

- [x] **Step 5: Run tests**

```
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/metering/usage/tests/test_models.py::UsageEventCardSnapshotTest -v
```

Expected: 2 passed.

- [x] **Step 6: Commit**

```
git add ubb-platform/apps/metering/usage/models.py \
        ubb-platform/apps/metering/usage/migrations/0018_usageevent_card_snapshot_fields.py \
        ubb-platform/apps/metering/usage/tests/test_models.py
git commit -m "feat(usage): add card_slug/card_name snapshot fields to UsageEvent"
```

---

### Task 5: Backfill `card_slug` + `card_name` for historical events

**Files:**
- Create: `ubb-platform/apps/metering/usage/migrations/0019_backfill_card_snapshots.py`

- [x] **Step 1: Write data migration**

Create `ubb-platform/apps/metering/usage/migrations/0019_backfill_card_snapshots.py`:

```python
"""Populate card_slug/card_name snapshots for events that already have a card FK."""

from django.db import migrations


def backfill_forward(apps, schema_editor):
    UsageEvent = apps.get_model("usage", "UsageEvent")
    qs = UsageEvent.objects.filter(card__isnull=False, card_slug="").select_related("card")
    for event in qs.iterator():
        event.card_slug = event.card.slug or ""
        event.card_name = event.card.name or ""
        event.save(update_fields=["card_slug", "card_name"])


def backfill_reverse(apps, schema_editor):
    UsageEvent = apps.get_model("usage", "UsageEvent")
    UsageEvent.objects.update(card_slug="", card_name="")


class Migration(migrations.Migration):
    dependencies = [
        ("usage", "0018_usageevent_card_snapshot_fields"),
    ]
    operations = [migrations.RunPython(backfill_forward, backfill_reverse)]
```

- [x] **Step 2: Apply migration**

```
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python manage.py migrate usage
```

- [x] **Step 3: Commit**

```
git add ubb-platform/apps/metering/usage/migrations/0019_backfill_card_snapshots.py
git commit -m "feat(usage): backfill card_slug/card_name snapshots from card FK"
```

---

## Phase 2 — Pricing Service Rewrite

### Task 6: Rewrite `PricingService` for explicit-rate pricing

**Files:**
- Rewrite: `ubb-platform/apps/metering/pricing/services/pricing_service.py`
- Create: `ubb-platform/apps/metering/pricing/tests/test_pricing_service_explicit.py`

- [x] **Step 1: Write failing tests**

Create `ubb-platform/apps/metering/pricing/tests/test_pricing_service_explicit.py`:

```python
"""Explicit-rate pricing: no runtime margin resolution."""
from decimal import Decimal

import pytest
from django.test import TestCase

from apps.platform.tenants.models import Tenant
from apps.metering.pricing.models import Card, Rate
from apps.metering.pricing.services.pricing_service import PricingService, PricingError


class PriceEventBySlugTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="T", products=["metering"])
        self.card = Card.objects.create(
            tenant=self.tenant, name="GPT-4o", slug="gpt_4o",
            provider="openai", status="active",
        )
        Rate.objects.create(
            card=self.card, metric_name="input_tokens",
            cost_per_unit_micros=3_000,
            provider_cost_per_unit_micros=2_500,
            unit_quantity=1_000_000,
        )
        Rate.objects.create(
            card=self.card, metric_name="output_tokens",
            cost_per_unit_micros=15_000,
            provider_cost_per_unit_micros=10_000,
            unit_quantity=1_000_000,
        )

    def test_prices_via_stored_costs_no_margin_resolution(self):
        provider_cost, billed_cost, provenance, card = PricingService.price_event_by_slug(
            tenant=self.tenant, card_slug="gpt_4o",
            usage_metrics={"input_tokens": 1_000_000, "output_tokens": 500_000},
        )
        # provider: 1M * 2500/1M + 500k * 10000/1M = 2500 + 5000 = 7500
        self.assertEqual(provider_cost, 7_500)
        # billed: 1M * 3000/1M + 500k * 15000/1M = 3000 + 7500 = 10_500
        self.assertEqual(billed_cost, 10_500)
        self.assertEqual(card, self.card)
        self.assertNotIn("margin", provenance)
        self.assertIn("metrics", provenance)
        self.assertIn("input_tokens", provenance["metrics"])

    def test_null_provider_cost_treated_as_passthrough(self):
        card2 = Card.objects.create(
            tenant=self.tenant, name="Claude", slug="claude_sonnet",
            provider="anthropic", status="active",
        )
        Rate.objects.create(
            card=card2, metric_name="input_tokens",
            cost_per_unit_micros=3_000,
            provider_cost_per_unit_micros=None,  # unknown
            unit_quantity=1_000_000,
        )
        provider_cost, billed_cost, _, _ = PricingService.price_event_by_slug(
            tenant=self.tenant, card_slug="claude_sonnet",
            usage_metrics={"input_tokens": 1_000_000},
        )
        # provider cost falls back to billed cost
        self.assertEqual(provider_cost, 3_000)
        self.assertEqual(billed_cost, 3_000)

    def test_unknown_slug_raises(self):
        with pytest.raises(PricingError):
            PricingService.price_event_by_slug(
                tenant=self.tenant, card_slug="nope",
                usage_metrics={"input_tokens": 1},
            )

    def test_unknown_metric_raises(self):
        with pytest.raises(PricingError):
            PricingService.price_event_by_slug(
                tenant=self.tenant, card_slug="gpt_4o",
                usage_metrics={"bogus_metric": 1},
            )

    def test_empty_metrics_returns_zero(self):
        provider_cost, billed_cost, _, card = PricingService.price_event_by_slug(
            tenant=self.tenant, card_slug="gpt_4o", usage_metrics={},
        )
        self.assertEqual(provider_cost, 0)
        self.assertEqual(billed_cost, 0)
        self.assertIsNone(card)

    def test_draft_card_cannot_be_used_for_live_pricing(self):
        draft = Card.objects.create(
            tenant=self.tenant, name="Draft", slug="draft_card",
            provider="openai", status="draft",
        )
        Rate.objects.create(
            card=draft, metric_name="input_tokens",
            cost_per_unit_micros=1_000, unit_quantity=1_000_000,
        )
        with pytest.raises(PricingError):
            PricingService.price_event_by_slug(
                tenant=self.tenant, card_slug="draft_card",
                usage_metrics={"input_tokens": 1_000_000},
            )
```

- [x] **Step 2: Run tests to verify they fail**

```
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/metering/pricing/tests/test_pricing_service_explicit.py -v
```

Expected: FAIL — the current `PricingService` still does margin resolution.

- [x] **Step 3: Rewrite `PricingService`**

Replace the entire contents of `ubb-platform/apps/metering/pricing/services/pricing_service.py` with:

```python
"""Explicit-rate pricing service. No runtime margin resolution.

Each Rate carries provider_cost_per_unit_micros (what the provider charges) and
cost_per_unit_micros (what the tenant charges its customer). Pricing is a simple
lookup-and-sum; there is no cascade and no TenantMarkup.
"""

import logging
from typing import Dict, Optional, Tuple

from django.db.models import Q
from django.utils import timezone

from apps.metering.pricing.models import Card, Rate

logger = logging.getLogger(__name__)

PRICING_ENGINE_VERSION = "3.0.0"


class PricingError(Exception):
    pass


class PricingService:
    """Calculate dual costs (provider + billed) from stored Rates. No margin math."""

    @staticmethod
    def validate_usage_metrics(usage_metrics: Dict) -> None:
        for key, value in usage_metrics.items():
            if not isinstance(value, int) or isinstance(value, bool):
                raise PricingError(
                    f"Metric '{key}' must be an integer, got {type(value).__name__}"
                )
            if value < 0:
                raise PricingError(f"Metric '{key}' must be >= 0, got {value}")

    @staticmethod
    def price_event_by_slug(
        tenant,
        card_slug: str,
        usage_metrics: Dict[str, int],
        group: str = None,  # accepted but unused; kept for caller compatibility
        as_of=None,
    ) -> Tuple[int, int, Dict, Optional[Card]]:
        """Price an event using direct card slug lookup.

        Returns (provider_cost_micros, billed_cost_micros, provenance, card).
        """
        as_of = as_of or timezone.now()

        if not usage_metrics:
            return 0, 0, {"engine_version": PRICING_ENGINE_VERSION, "metrics": {}}, None

        PricingService.validate_usage_metrics(usage_metrics)

        try:
            card = Card.objects.get(
                tenant=tenant, slug=card_slug, status="active",
            )
        except Card.DoesNotExist:
            raise PricingError(
                f"No active pricing card found with slug '{card_slug}'"
            )

        total_provider_cost = 0
        total_billed_cost = 0
        provenance_metrics = {}

        for metric_name, units in usage_metrics.items():
            rate = PricingService._find_rate(card, metric_name, as_of)
            if rate is None:
                raise PricingError(
                    f"No rate found for metric '{metric_name}' in card '{card.name}'"
                )
            billed_for_metric = rate.calculate_cost_micros(units)
            provider_unit = (
                rate.provider_cost_per_unit_micros
                if rate.provider_cost_per_unit_micros is not None
                else rate.cost_per_unit_micros
            )
            provider_for_metric = PricingService._cost(
                units, provider_unit, rate.unit_quantity, rate.pricing_type,
            )

            total_provider_cost += provider_for_metric
            total_billed_cost += billed_for_metric

            provenance_metrics[metric_name] = {
                "rate_id": str(rate.id),
                "units": units,
                "pricing_type": rate.pricing_type,
                "cost_per_unit_micros": rate.cost_per_unit_micros,
                "provider_cost_per_unit_micros": rate.provider_cost_per_unit_micros,
                "unit_quantity": rate.unit_quantity,
                "billed_cost_micros": billed_for_metric,
                "provider_cost_micros": provider_for_metric,
            }

        provenance = {
            "engine_version": PRICING_ENGINE_VERSION,
            "calculated_at": as_of.isoformat(),
            "card_id": str(card.id),
            "card_slug": card.slug,
            "card_name": card.name,
            "metrics": provenance_metrics,
            "provider_cost_micros": total_provider_cost,
            "billed_cost_micros": total_billed_cost,
        }

        return total_provider_cost, total_billed_cost, provenance, card

    @staticmethod
    def _cost(units: int, per_unit: int, unit_quantity: int, pricing_type: str) -> int:
        if pricing_type == "flat":
            return per_unit
        return (units * per_unit + unit_quantity // 2) // unit_quantity

    @staticmethod
    def _find_rate(card: Card, metric_name: str, as_of) -> Optional[Rate]:
        return card.rates.filter(
            metric_name=metric_name,
            valid_from__lte=as_of,
        ).filter(
            Q(valid_to__isnull=True) | Q(valid_to__gt=as_of)
        ).order_by("-valid_from").first()
```

- [x] **Step 4: Delete legacy pricing tests**

```
rm ubb-platform/apps/metering/pricing/tests/test_pricing_service.py
rm ubb-platform/apps/metering/pricing/tests/test_pricing_service_v2.py
```

These cover `_resolve_margin`, `_find_card`, `_dimensions_match`, and `price_event` — all deleted. The new `test_pricing_service_explicit.py` replaces them.

- [x] **Step 5: Run new pricing tests**

```
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/metering/pricing/tests/test_pricing_service_explicit.py -v
```

Expected: all pass.

- [x] **Step 6: Run full pricing suite** (expect some failures in tests outside this task's scope — usage & endpoint tests still reference `event_type` + `TenantMarkup`. These are fixed in later tasks.)

```
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/metering/pricing/ -q
```

Record which test files still fail. Expected failures will only be fixed downstream.

- [x] **Step 7: Commit**

```
git add ubb-platform/apps/metering/pricing/services/pricing_service.py \
        ubb-platform/apps/metering/pricing/tests/test_pricing_service_explicit.py
git rm ubb-platform/apps/metering/pricing/tests/test_pricing_service.py \
       ubb-platform/apps/metering/pricing/tests/test_pricing_service_v2.py
git commit -m "feat(pricing): rewrite service for explicit-rate pricing (drop margin resolver)"
```

---

### Task 7: Rewrite `UsageService.record_usage` — require pricing_card, write snapshots

**Files:**
- Modify: `ubb-platform/apps/metering/usage/services/usage_service.py`
- Modify: `ubb-platform/apps/metering/usage/tests/test_usage_service.py`

- [x] **Step 1: Write failing tests**

Add to `ubb-platform/apps/metering/usage/tests/test_usage_service.py` (at the end; use existing imports):

```python
class RecordUsageSlugSnapshotTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="T", products=["metering"])
        self.customer = Customer.objects.create(tenant=self.tenant, external_id="c1")
        from apps.metering.pricing.models import Card, Rate
        self.card = Card.objects.create(
            tenant=self.tenant, name="GPT-4o", slug="gpt_4o",
            provider="openai", status="active",
        )
        Rate.objects.create(
            card=self.card, metric_name="input_tokens",
            cost_per_unit_micros=3_000, provider_cost_per_unit_micros=2_500,
            unit_quantity=1_000_000,
        )

    def test_record_with_slug_writes_snapshots(self):
        from apps.metering.usage.models import UsageEvent
        UsageService.record_usage(
            tenant=self.tenant, customer=self.customer,
            request_id="r1", idempotency_key="k1",
            pricing_card="gpt_4o", usage_metrics={"input_tokens": 1_000_000},
        )
        event = UsageEvent.objects.get(idempotency_key="k1")
        self.assertEqual(event.card_slug, "gpt_4o")
        self.assertEqual(event.card_name, "GPT-4o")
        self.assertEqual(event.provider, "openai")
        self.assertEqual(event.card, self.card)
        self.assertEqual(event.provider_cost_micros, 2_500)
        self.assertEqual(event.billed_cost_micros, 3_000)

    def test_record_requires_pricing_card(self):
        from apps.metering.pricing.services.pricing_service import PricingError
        with self.assertRaises((ValueError, PricingError)):
            UsageService.record_usage(
                tenant=self.tenant, customer=self.customer,
                request_id="r2", idempotency_key="k2",
                usage_metrics={"input_tokens": 1},
            )
```

- [x] **Step 2: Run tests to verify they fail**

```
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/metering/usage/tests/test_usage_service.py::RecordUsageSlugSnapshotTest -v
```

Expected: FAIL — `card_slug`/`card_name` snapshots not yet written.

- [x] **Step 3: Update `UsageService.record_usage`**

Replace the full body of `ubb-platform/apps/metering/usage/services/usage_service.py` with:

```python
import logging

from django.db import transaction, IntegrityError

from apps.metering.usage.models import UsageEvent
from apps.platform.events.outbox import write_event
from apps.platform.events.schemas import UsageRecorded

logger = logging.getLogger(__name__)


class UsageService:
    @staticmethod
    @transaction.atomic
    def record_usage(
        tenant,
        customer,
        request_id,
        idempotency_key,
        cost_micros=None,
        metadata=None,
        usage_metrics=None,
        properties=None,
        group=None,
        run_id=None,
        pricing_card=None,
    ):
        # 1. Idempotency fast path
        existing = UsageEvent.objects.filter(
            tenant=tenant, customer=customer, idempotency_key=idempotency_key,
        ).first()
        if existing:
            return {
                "event_id": str(existing.id),
                "new_balance_micros": None,
                "suspended": False,
                "provider_cost_micros": existing.provider_cost_micros,
                "billed_cost_micros": existing.billed_cost_micros,
                "run_id": str(existing.run_id) if existing.run_id else None,
                "run_total_cost_micros": None,
                "hard_stop": False,
            }

        # 2. Price via slug (the only supported path)
        provider_cost_micros = None
        billed_cost_micros = None
        pricing_provenance = {}
        card_obj = None
        card_slug = ""
        card_name = ""
        provider = ""

        if pricing_card is not None and usage_metrics is not None:
            from apps.metering.pricing.services.pricing_service import PricingService
            (
                provider_cost_micros,
                billed_cost_micros,
                pricing_provenance,
                card_obj,
            ) = PricingService.price_event_by_slug(
                tenant=tenant,
                card_slug=pricing_card,
                usage_metrics=usage_metrics,
                group=group,
            )
            cost_micros = billed_cost_micros
            if card_obj is not None:
                card_slug = card_obj.slug
                card_name = card_obj.name
                provider = card_obj.provider
        elif usage_metrics is not None:
            raise ValueError("pricing_card is required when usage_metrics is provided")

        # 3. Run hard-stop accumulation
        run = None
        if run_id is not None:
            from apps.platform.runs.services import RunService

            effective_cost_for_run = (
                billed_cost_micros if billed_cost_micros is not None else cost_micros
            )
            run = RunService.accumulate_cost(run_id, effective_cost_for_run or 0)

        # 4. Create event
        try:
            with transaction.atomic():
                event = UsageEvent.objects.create(
                    tenant=tenant,
                    customer=customer,
                    request_id=request_id,
                    idempotency_key=idempotency_key,
                    cost_micros=cost_micros,
                    balance_after_micros=None,
                    metadata=metadata or {},
                    provider=provider,
                    usage_metrics=usage_metrics or {},
                    properties=properties or {},
                    provider_cost_micros=provider_cost_micros,
                    billed_cost_micros=billed_cost_micros,
                    pricing_provenance=pricing_provenance,
                    group=group,
                    run_id=run_id,
                    card=card_obj,
                    card_slug=card_slug,
                    card_name=card_name,
                )
        except IntegrityError:
            existing = UsageEvent.objects.get(
                tenant=tenant, customer=customer, idempotency_key=idempotency_key,
            )
            return {
                "event_id": str(existing.id),
                "new_balance_micros": None,
                "suspended": False,
                "provider_cost_micros": existing.provider_cost_micros,
                "billed_cost_micros": existing.billed_cost_micros,
                "run_id": str(existing.run_id) if existing.run_id else None,
                "run_total_cost_micros": None,
                "hard_stop": False,
            }

        # 5. Outbox
        effective_cost = billed_cost_micros if billed_cost_micros is not None else cost_micros
        write_event(UsageRecorded(
            tenant_id=str(tenant.id),
            customer_id=str(customer.id),
            event_id=str(event.id),
            cost_micros=effective_cost,
            provider_cost_micros=provider_cost_micros,
            billed_cost_micros=billed_cost_micros,
            event_type="",  # legacy field on UsageRecorded; keep blank
            provider=provider,
            run_id=str(run_id) if run_id else None,
        ))

        return {
            "event_id": str(event.id),
            "new_balance_micros": None,
            "suspended": False,
            "provider_cost_micros": provider_cost_micros,
            "billed_cost_micros": billed_cost_micros,
            "run_id": str(run_id) if run_id else None,
            "run_total_cost_micros": run.total_cost_micros if run else None,
            "hard_stop": False,
        }
```

- [x] **Step 4: Update existing tests in `test_usage_service.py`**

Find any test in `test_usage_service.py` that calls `UsageService.record_usage(... event_type=..., provider=...)`. For each, either:
- Replace with `pricing_card="..."` path and create the card + rate in setUp, OR
- Delete if the test was specifically exercising the dual-mode behavior.

List each fixed test in the commit message.

- [x] **Step 5: Run tests**

```
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/metering/usage/tests/test_usage_service.py -v
```

Expected: all pass (including the new snapshot test).

- [x] **Step 6: Commit**

```
git add ubb-platform/apps/metering/usage/services/usage_service.py \
        ubb-platform/apps/metering/usage/tests/test_usage_service.py
git commit -m "feat(usage): require pricing_card slug; snapshot card_slug/card_name on event"
```

---

## Phase 3 — Drop Legacy Fields

### Task 8: Drop `UsageEvent.event_type`

**Files:**
- Modify: `ubb-platform/apps/metering/usage/models.py`
- Create: `ubb-platform/apps/metering/usage/migrations/0020_drop_usageevent_event_type.py`
- Modify: `ubb-platform/apps/metering/usage/services/usage_service.py` (remove stale write)
- Modify: `ubb-platform/api/v1/metering_endpoints.py` (drop from analytics)
- Modify: `ubb-platform/api/v1/schemas.py` (drop from schemas)

- [x] **Step 1: Remove all references to `event_type` on UsageEvent**

Search for remaining references:

```
cd ubb-platform && .venv/bin/python -c "import pathlib,re; [print(p) for p in pathlib.Path('apps').rglob('*.py') if re.search(r'usageevent.*event_type|event\\.event_type|ue\\.event_type', p.read_text(), re.I)]"
```

Fix each occurrence. Specifically:
- `api/v1/metering_endpoints.py::usage_analytics` — remove the `by_event_type` aggregation block and drop `event_type` from the return dict.
- `api/v1/schemas.py::UsageEventOut` — remove `event_type: str` field.
- `api/v1/schemas.py::UsageAnalyticsResponse` — remove `by_event_type: list[dict]` field.
- Any `_card_to_out` or serializer still returning it.
- `apps/platform/events/schemas.py::UsageRecorded` — remove `event_type` field, AND remove the argument from the `write_event(UsageRecorded(...))` call in `UsageService`.

- [x] **Step 2: Remove the field from the model**

Edit `ubb-platform/apps/metering/usage/models.py`, delete the line:

```python
    event_type = models.CharField(max_length=100, blank=True, default="", db_index=True)
```

- [x] **Step 3: Generate migration**

```
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python manage.py makemigrations usage --name drop_usageevent_event_type
DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python manage.py migrate usage
```

- [x] **Step 4: Run full usage test suite**

```
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/metering/usage/ -q
```

Expected: all pass.

- [x] **Step 5: Commit**

```
git add -u ubb-platform/
git commit -m "feat(usage): drop UsageEvent.event_type (superseded by card_slug snapshot)"
```

---

### Task 9: Drop `Card.event_type`, `Card.dimensions`, `Card.dimensions_hash`, legacy constraint+index

**Files:**
- Modify: `ubb-platform/apps/metering/pricing/models.py`
- Create: `ubb-platform/apps/metering/pricing/migrations/0011_drop_card_legacy_fields.py`

- [x] **Step 1: Update `Card` model**

Edit `ubb-platform/apps/metering/pricing/models.py`. Remove:
- `event_type = models.CharField(...)` line
- `dimensions = models.JSONField(...)` line
- `dimensions_hash = models.CharField(...)` line
- The `indexes = [models.Index(fields=["tenant", "provider", "event_type"], ...)]` entry under `Meta.indexes` (delete the whole `indexes = [...]` block if that was the only one)
- The first `UniqueConstraint` on `(tenant, provider, event_type, dimensions_hash)` under `Meta.constraints` (keep the `uq_card_slug_per_tenant` one)
- The `save()` override that sets `dimensions_hash`

The resulting `Card` body should look like:

```python
class Card(BaseModel):
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="pricing_cards",
    )
    name = models.CharField(max_length=255)
    slug = models.CharField(max_length=255, db_index=True, default="")
    provider = models.CharField(max_length=100, db_index=True)
    description = models.TextField(blank=True, default="")
    pricing_source_url = models.URLField(max_length=500, blank=True, default="")
    group = models.ForeignKey(
        "groups.Group",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pricing_cards",
    )
    status = models.CharField(
        max_length=20,
        choices=[("draft", "Draft"), ("active", "Active"), ("archived", "Archived")],
        default="active",
    )

    class Meta:
        db_table = "ubb_card"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "slug"],
                condition=models.Q(status__in=["active", "draft"]),
                name="uq_card_slug_per_tenant",
            ),
        ]
```

- [x] **Step 2: Generate migration**

```
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python manage.py makemigrations pricing --name drop_card_legacy_fields
```

Inspect the generated file. It should: remove the index, remove the old constraint, remove three fields. If makemigrations complains because data might be lost, confirm (these fields are intentionally being dropped).

- [x] **Step 3: Apply migration**

```
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python manage.py migrate pricing
```

- [x] **Step 4: Find remaining references and fix**

```
cd ubb-platform && .venv/bin/python -c "import pathlib,re; [print(p,':',m.group(0)) for p in pathlib.Path('.').rglob('*.py') if p.suffix=='.py' for m in re.finditer(r'card\\.(event_type|dimensions|dimensions_hash)', p.read_text())]"
```

Fix each. Expected hit sites:
- `api/v1/metering_endpoints.py::_card_to_out` — remove `"event_type"` and `"dimensions"` keys (task 12 will do this formally, but drop now to get tests passing).
- `api/v1/schemas.py::CreateCardRequest`, `CardOut` — drop `event_type` + `dimensions` fields.
- Any test setUp building a Card with `event_type=...`, `dimensions={...}` — remove those kwargs.

- [x] **Step 5: Run full pricing suite**

```
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/metering/pricing/ -q
```

Expected: all pass.

- [x] **Step 6: Commit**

```
git add -u ubb-platform/
git commit -m "feat(pricing): drop Card.event_type, dimensions, dimensions_hash (slug is primary)"
```

---

### Task 10: Delete `TenantMarkup` model + admin

**Files:**
- Modify: `ubb-platform/apps/metering/pricing/models.py` — remove `TenantMarkup` class
- Modify: `ubb-platform/apps/metering/pricing/admin.py` — remove TenantMarkup admin registration
- Create: `ubb-platform/apps/metering/pricing/migrations/0012_delete_tenantmarkup.py`
- Modify: `ubb-platform/api/v1/metering_endpoints.py` — delete the 4 markup endpoints + `_markup_to_out`
- Modify: `ubb-platform/api/v1/schemas.py` — delete `TenantMarkupIn`, `TenantMarkupOut`

- [x] **Step 1: Delete code**

In `ubb-platform/apps/metering/pricing/models.py`: delete the entire `class TenantMarkup(BaseModel):` block.

In `ubb-platform/apps/metering/pricing/admin.py`: remove any `admin.site.register(TenantMarkup, ...)` and `class TenantMarkupAdmin(...)` block.

In `ubb-platform/api/v1/metering_endpoints.py`: delete the block from `# --- Pricing Markups CRUD ---` through `delete_markup`, inclusive of `_markup_to_out`.

In `ubb-platform/api/v1/schemas.py`: delete `class TenantMarkupIn(CamelSchema):` and `class TenantMarkupOut(CamelSchema):`.

Update the import at the top of `metering_endpoints.py` to remove `TenantMarkupIn, TenantMarkupOut`.

- [x] **Step 2: Generate migration**

```
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python manage.py makemigrations pricing --name delete_tenantmarkup
DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python manage.py migrate pricing
```

- [x] **Step 3: Run full suite**

```
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest -q
```

Expected: all pass. If any test imports `TenantMarkup`, delete those tests — they're now covering deleted functionality.

- [x] **Step 4: Commit**

```
git add -u ubb-platform/
git commit -m "feat(pricing): delete TenantMarkup (replaced by explicit rates + UX defaults)"
```

---

## Phase 4 — API Contract

### Task 11: Update `api/v1/schemas.py`

**Files:**
- Modify: `ubb-platform/api/v1/schemas.py`
- Test: `ubb-platform/api/v1/tests/test_metering_endpoints.py` (add a coverage test)

- [x] **Step 1: Write failing test for the new response shape**

Append to `ubb-platform/api/v1/tests/test_metering_endpoints.py`:

```python
class CardOutShapeTest(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="T", products=["metering"])
        self.api_key, self.raw_key = TenantApiKey.create_key(self.tenant, label="test")
        from apps.metering.pricing.models import Card, Rate
        self.card = Card.objects.create(
            tenant=self.tenant, name="GPT-4o", slug="gpt_4o",
            provider="openai", status="active",
        )
        Rate.objects.create(
            card=self.card, metric_name="input_tokens",
            cost_per_unit_micros=3_000,
            provider_cost_per_unit_micros=2_500,
            unit_quantity=1_000_000, label="Input", unit="per 1M tokens",
        )

    def test_card_out_has_dimensions_not_rates(self):
        resp = self.client.get(
            f"/api/v1/metering/pricing/cards/{self.card.id}",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        assert resp.status_code == 200
        body = resp.json()
        # Renamed from rates -> dimensions
        assert "dimensions" in body
        assert "rates" not in body
        # eventType gone
        assert "eventType" not in body
        # Each dimension has providerCostPerUnitMicros
        assert "providerCostPerUnitMicros" in body["dimensions"][0]
```

Ensure imports include `Tenant`, `TenantApiKey`, and `APITestCase` (or equivalent wrapper used in this file).

- [x] **Step 2: Run test to verify it fails**

```
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest api/v1/tests/test_metering_endpoints.py::CardOutShapeTest -v
```

Expected: FAIL — still has `rates`/`eventType`.

- [x] **Step 3: Update schemas**

In `ubb-platform/api/v1/schemas.py`:

**`RateIn`** → rename to `DimensionIn`. Add `provider_cost_per_unit_micros`:

```python
class DimensionIn(CamelSchema):
    metric_name: str = Field(min_length=1, max_length=100)
    pricing_type: str = Field(default="per_unit", pattern=r"^(per_unit|flat)$")
    cost_per_unit_micros: int = Field(ge=0)
    provider_cost_per_unit_micros: Optional[int] = Field(default=None, ge=0)
    unit_quantity: int = Field(gt=0, default=1_000_000)
    currency: str = Field(default="USD", max_length=3)
    label: str = Field(default="", max_length=100)
    unit: str = Field(default="", max_length=50)
```

**`RateOut`** → rename to `DimensionOut`. Add `provider_cost_per_unit_micros`:

```python
class DimensionOut(CamelSchema):
    id: str
    metric_name: str
    pricing_type: str
    cost_per_unit_micros: int
    provider_cost_per_unit_micros: Optional[int] = None
    unit_quantity: int
    currency: str
    label: str
    unit: str
    valid_from: str
    valid_to: Optional[str] = None
```

**`CreateCardRequest`** — remove `event_type` and `dimensions: dict`, rename `rates` → `dimensions`:

```python
class CreateCardRequest(CamelSchema):
    name: str = Field(min_length=1, max_length=255)
    slug: str = Field(min_length=2, max_length=255, pattern=r"^[a-z][a-z0-9_]*$")
    provider: str = Field(min_length=1, max_length=100)
    description: str = ""
    pricing_source_url: str = ""
    group_id: Optional[str] = None
    status: str = Field(default="active", pattern=r"^(draft|active)$")
    dimensions: list[DimensionIn] = Field(default_factory=list)
```

**`CardOut`** — remove `event_type` and `dimensions: dict`, rename `rates` → `dimensions`:

```python
class CardOut(CamelSchema):
    id: str
    slug: str
    name: str
    provider: str
    description: str
    pricing_source_url: str
    group_id: Optional[str] = None
    group_name: Optional[str] = None
    status: str
    dimensions: list[DimensionOut]
    created_at: str
    updated_at: str
```

**`RecordUsageRequest`** — make `pricing_card` required, drop `event_type` and `provider`:

```python
class RecordUsageRequest(CamelSchema):
    customer_id: UUID
    request_id: str = Field(min_length=1, max_length=500)
    idempotency_key: str = Field(min_length=1, max_length=500)
    pricing_card: str = Field(min_length=1, max_length=255)
    usage_metrics: dict[str, int] = Field(default_factory=dict)
    group: Optional[str] = Field(default=None, max_length=255)
    run_id: Optional[UUID] = None

    @field_validator("usage_metrics")
    @classmethod
    def usage_metrics_values_non_negative(cls, v):
        if v is not None:
            for key, val in v.items():
                if not isinstance(val, int) or isinstance(val, bool):
                    raise ValueError(f"Metric '{key}' must be an integer")
                if val < 0:
                    raise ValueError(f"Metric '{key}' must be >= 0")
        return v
```

**`UsageEventOut`** — drop `event_type`, add `card_slug`, `card_name`:

```python
class UsageEventOut(CamelSchema):
    id: UUID
    request_id: str
    cost_micros: int
    provider: str
    card_slug: str
    card_name: str
    provider_cost_micros: Optional[int] = None
    billed_cost_micros: Optional[int] = None
    effective_at: str
```

**`EventOut`** — drop `event_type`:

```python
class EventOut(CamelSchema):
    id: str
    effective_at: str
    customer_id: str
    customer_external_id: str
    group: Optional[str] = None
    card_id: Optional[str] = None
    card_slug: Optional[str] = None
    card_name: Optional[str] = None
    provider: str
    usage_metrics: dict
    provider_cost_micros: Optional[int] = None
    billed_cost_micros: Optional[int] = None
```

**Add a new schema at the bottom of `schemas.py`:**

```python
class TenantDefaultMarginResponse(CamelSchema):
    default_margin_pct: float


class UpdateTenantDefaultMarginRequest(CamelSchema):
    default_margin_pct: float = Field(ge=0, lt=100)
```

- [x] **Step 4: Update `metering_endpoints._card_to_out`**

Replace the function in `ubb-platform/api/v1/metering_endpoints.py` with:

```python
def _card_to_out(card):
    dimensions = card.rates.filter(valid_to__isnull=True).order_by("metric_name")
    return {
        "id": str(card.id),
        "slug": card.slug,
        "name": card.name,
        "provider": card.provider,
        "description": card.description,
        "pricing_source_url": card.pricing_source_url,
        "group_id": str(card.group_id) if card.group_id else None,
        "group_name": card.group.name if card.group_id else None,
        "status": card.status,
        "dimensions": [
            {
                "id": str(r.id),
                "metric_name": r.metric_name,
                "pricing_type": r.pricing_type,
                "cost_per_unit_micros": r.cost_per_unit_micros,
                "provider_cost_per_unit_micros": r.provider_cost_per_unit_micros,
                "unit_quantity": r.unit_quantity,
                "currency": r.currency,
                "label": r.label,
                "unit": r.unit,
                "valid_from": r.valid_from.isoformat(),
                "valid_to": None,
            }
            for r in dimensions
        ],
        "created_at": card.created_at.isoformat(),
        "updated_at": card.updated_at.isoformat(),
    }
```

Also update `create_card`, `add_card_rate`, `update_card_rate` to iterate `payload.dimensions` instead of `payload.rates`, and pass `provider_cost_per_unit_micros=d.provider_cost_per_unit_micros` when constructing each `Rate`.

- [x] **Step 5: Update `record_usage` endpoint**

In `metering_endpoints.py::record_usage`, remove the legacy validation block:

```python
if not payload.pricing_card and not payload.event_type and payload.usage_metrics:
    ...
```

(Pydantic now enforces `pricing_card` is required, and `event_type`/`provider` no longer exist on the request.)

Remove `event_type=payload.event_type or None` and `provider=payload.provider or None` from the `UsageService.record_usage(...)` call.

- [x] **Step 6: Run tests**

```
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest api/v1/tests/test_metering_endpoints.py -q
```

Expected: all pass. Fix any test that hits `rates`, `eventType`, or legacy payload fields.

- [x] **Step 7: Commit**

```
git add -u ubb-platform/
git commit -m "feat(api): rename RateOut->DimensionOut; drop eventType/dimensions dict from CardOut; require pricingCard"
```

---

### Task 12: Add tenant default margin endpoint

**Files:**
- Modify: `ubb-platform/api/v1/platform_endpoints.py`
- Modify: `ubb-platform/api/v1/tests/test_platform_endpoints.py`

- [x] **Step 1: Write failing test**

Append to `ubb-platform/api/v1/tests/test_platform_endpoints.py`:

```python
class TenantDefaultMarginTest(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="T", products=["metering"])
        self.api_key, self.raw_key = TenantApiKey.create_key(self.tenant, label="test")
        self.auth = {"HTTP_AUTHORIZATION": f"Bearer {self.raw_key}"}

    def test_get_default(self):
        resp = self.client.get("/api/v1/platform/tenant/default-margin", **self.auth)
        assert resp.status_code == 200
        assert resp.json() == {"defaultMarginPct": 0.0}

    def test_update_default(self):
        resp = self.client.patch(
            "/api/v1/platform/tenant/default-margin",
            data={"defaultMarginPct": 30.5},
            content_type="application/json",
            **self.auth,
        )
        assert resp.status_code == 200
        assert resp.json() == {"defaultMarginPct": 30.5}
        self.tenant.refresh_from_db()
        assert float(self.tenant.default_margin_pct) == 30.5
```

- [x] **Step 2: Run test to verify it fails**

```
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest api/v1/tests/test_platform_endpoints.py::TenantDefaultMarginTest -v
```

Expected: FAIL — route doesn't exist.

- [x] **Step 3: Add endpoints**

At the bottom of `ubb-platform/api/v1/platform_endpoints.py`, add:

```python
# --- Tenant default margin (UX default for card creation wizard) ---

from api.v1.schemas import TenantDefaultMarginResponse, UpdateTenantDefaultMarginRequest


@platform_api.get("/tenant/default-margin", response=TenantDefaultMarginResponse)
def get_default_margin(request):
    t = request.auth.tenant
    return {"default_margin_pct": float(t.default_margin_pct)}


@platform_api.patch("/tenant/default-margin", response=TenantDefaultMarginResponse)
def update_default_margin(request, payload: UpdateTenantDefaultMarginRequest):
    t = request.auth.tenant
    t.default_margin_pct = payload.default_margin_pct
    t.save(update_fields=["default_margin_pct", "updated_at"])
    return {"default_margin_pct": float(t.default_margin_pct)}
```

- [x] **Step 4: Run tests**

```
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest api/v1/tests/test_platform_endpoints.py::TenantDefaultMarginTest -v
```

Expected: 2 passed.

- [x] **Step 5: Commit**

```
git add -u ubb-platform/
git commit -m "feat(api): tenant default margin GET/PATCH endpoints"
```

---

### Task 13: Update Event endpoints to include `cardSlug`/`cardName` snapshots

**Files:**
- Modify: `ubb-platform/api/v1/platform_endpoints.py::list_events` (and any adjacent helper that builds EventOut)
- Modify: `ubb-platform/api/v1/tests/test_event_endpoints.py`

- [x] **Step 1: Write failing test**

Append to `test_event_endpoints.py`:

```python
class EventOutSnapshotFieldsTest(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="T", products=["metering"])
        self.customer = Customer.objects.create(tenant=self.tenant, external_id="c1")
        self.api_key, self.raw_key = TenantApiKey.create_key(self.tenant, label="test")
        from apps.metering.pricing.models import Card, Rate
        card = Card.objects.create(
            tenant=self.tenant, name="GPT-4o", slug="gpt_4o",
            provider="openai", status="active",
        )
        Rate.objects.create(
            card=card, metric_name="input_tokens",
            cost_per_unit_micros=3_000, provider_cost_per_unit_micros=2_500,
            unit_quantity=1_000_000,
        )
        from apps.metering.usage.services.usage_service import UsageService
        UsageService.record_usage(
            tenant=self.tenant, customer=self.customer,
            request_id="r1", idempotency_key="k1",
            pricing_card="gpt_4o", usage_metrics={"input_tokens": 1_000_000},
        )

    def test_event_list_includes_card_snapshot(self):
        resp = self.client.post(
            "/api/v1/platform/events/list", data={}, content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["events"]) == 1
        event = body["events"][0]
        assert event["cardSlug"] == "gpt_4o"
        assert event["cardName"] == "GPT-4o"
        assert event["provider"] == "openai"
        assert "eventType" not in event
```

- [x] **Step 2: Run test to verify it fails**

```
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest api/v1/tests/test_event_endpoints.py::EventOutSnapshotFieldsTest -v
```

- [x] **Step 3: Update `list_events` to return snapshots**

In `ubb-platform/api/v1/platform_endpoints.py`, find the `list_events` handler (around the `/events/list` route). Replace the per-event dict construction so each `EventOut` item includes:

```python
{
    "id": str(e.id),
    "effective_at": e.effective_at.isoformat(),
    "customer_id": str(e.customer_id),
    "customer_external_id": e.customer.external_id,
    "group": e.group,
    "card_id": str(e.card_id) if e.card_id else None,
    "card_slug": e.card_slug or (e.card.slug if e.card else None),
    "card_name": e.card_name or (e.card.name if e.card else None),
    "provider": e.provider,
    "usage_metrics": e.usage_metrics,
    "provider_cost_micros": e.provider_cost_micros,
    "billed_cost_micros": e.billed_cost_micros,
}
```

Remove any `"event_type": e.event_type` key. Make sure any `select_related("customer", "card")` is in place to avoid N+1.

- [x] **Step 4: Run tests**

```
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest api/v1/tests/test_event_endpoints.py -q
```

Expected: all pass.

- [x] **Step 5: Commit**

```
git add -u ubb-platform/
git commit -m "feat(api): include cardSlug/cardName snapshots on EventOut; drop eventType"
```

---

### Task 14: Update analytics endpoint — drop `by_event_type`

**Files:**
- Modify: `ubb-platform/api/v1/metering_endpoints.py::usage_analytics`
- Modify: `ubb-platform/api/v1/schemas.py::UsageAnalyticsResponse`
- Modify: `ubb-platform/api/v1/tests/` — find and update the analytics test

- [x] **Step 1: Replace `UsageAnalyticsResponse`**

In `ubb-platform/api/v1/schemas.py`:

```python
class UsageAnalyticsResponse(CamelSchema):
    total_events: int
    total_billed_cost_micros: int
    total_provider_cost_micros: int
    by_provider: list[dict]
    by_card: list[dict]
```

- [x] **Step 2: Update the analytics endpoint**

Replace `usage_analytics` in `metering_endpoints.py` with:

```python
@metering_api.get("/analytics/usage", response=UsageAnalyticsResponse)
def usage_analytics(request, start_date: date = None, end_date: date = None):
    _product_check(request)
    tenant = request.auth.tenant
    qs = UsageEvent.objects.filter(tenant=tenant)

    if start_date:
        qs = qs.filter(effective_at__date__gte=start_date)
    if end_date:
        qs = qs.filter(effective_at__date__lte=end_date)

    effective_cost = Coalesce("billed_cost_micros", "cost_micros")

    totals = qs.aggregate(
        total_events=Count("id"),
        total_billed_cost_micros=Sum(effective_cost),
        total_provider_cost_micros=Sum("provider_cost_micros"),
    )

    by_provider = list(
        qs.exclude(provider="").values("provider").annotate(
            event_count=Count("id"),
            total_cost_micros=Sum(effective_cost),
        ).order_by("-total_cost_micros")
    )

    by_card = list(
        qs.exclude(card_slug="").values("card_slug", "card_name").annotate(
            event_count=Count("id"),
            total_cost_micros=Sum(effective_cost),
        ).order_by("-total_cost_micros")
    )

    return {
        "total_events": totals["total_events"] or 0,
        "total_billed_cost_micros": totals["total_billed_cost_micros"] or 0,
        "total_provider_cost_micros": totals["total_provider_cost_micros"] or 0,
        "by_provider": by_provider,
        "by_card": by_card,
    }
```

- [x] **Step 3: Fix existing analytics test**

In whichever test currently asserts on `by_event_type` (search: `grep -r by_event_type ubb-platform/api/v1/tests`), replace with `by_card` assertions using `card_slug`/`card_name` keys.

- [x] **Step 4: Run tests**

```
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest api/v1/tests/ -q
```

Expected: all pass.

- [x] **Step 5: Commit**

```
git add -u ubb-platform/
git commit -m "feat(api): usage analytics groups by_card instead of by_event_type"
```

---

## Phase 5 — Full Backend Regression

### Task 15: Run full platform test suite

- [x] **Step 1: Run all tests**

```
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest -q
```

Expected: all pass. If any fail, fix them in-session before proceeding. Typical fixers:
- Any test setUp creating Card with `event_type=...`/`dimensions=...` → remove those kwargs.
- Any test calling `UsageService.record_usage(event_type=..., provider=...)` → switch to `pricing_card=...`.
- Any test asserting `response.json()["eventType"]` → remove.

- [x] **Step 2: No commit unless fixes were made** — record the "X passed" number in the plan execution log.

---

## Phase 6 — SDK Update

### Task 16: Update SDK `record_usage` to require `pricing_card`

**Files:**
- Modify: `ubb-sdk/ubb/metering.py`
- Modify: `ubb-sdk/ubb/types.py`
- Modify: `ubb-sdk/tests/test_metering_client.py`

- [x] **Step 1: Write failing test**

Append to `ubb-sdk/tests/test_metering_client.py`:

```python
def test_record_usage_sends_pricing_card(httpx_mock):
    from ubb.metering import MeteringClient
    httpx_mock.add_response(
        url="http://api.test/api/v1/metering/usage",
        method="POST",
        json={"eventId": "e1"},
        status_code=200,
    )
    client = MeteringClient(base_url="http://api.test", api_key="test")
    client.record_usage(
        customer_id="c1", request_id="r1", idempotency_key="k1",
        pricing_card="gpt_4o", usage_metrics={"input_tokens": 100},
    )
    request = httpx_mock.get_requests()[0]
    body = request.read().decode()
    assert "pricingCard" in body or "pricing_card" in body
    assert "eventType" not in body
```

(Adjust to match whatever mocking library this test file already uses — `respx`, `httpx_mock`, or manual `monkeypatch`. Follow the idiom already present.)

- [x] **Step 2: Run test to verify it fails**

```
cd ubb-sdk && pytest tests/test_metering_client.py::test_record_usage_sends_pricing_card -v
```

- [x] **Step 3: Update `MeteringClient.record_usage`**

Edit `ubb-sdk/ubb/metering.py` — replace the `record_usage` signature and body:

```python
def record_usage(
    self,
    customer_id: str,
    request_id: str,
    idempotency_key: str,
    pricing_card: str,
    usage_metrics: dict,
    group: str | None = None,
    run_id: str | None = None,
) -> RecordUsageResult:
    """Record a usage event via POST /api/v1/metering/usage.

    Pricing is resolved by the server via the pricing_card slug. The server
    looks up the tenant's Card by slug and applies the stored per-metric rates.
    """
    body: dict = {
        "customerId": customer_id,
        "requestId": request_id,
        "idempotencyKey": idempotency_key,
        "pricingCard": pricing_card,
        "usageMetrics": usage_metrics,
    }
    if group is not None:
        body["group"] = group
    if run_id is not None:
        body["runId"] = run_id
    r = self._request_usage("post", "/api/v1/metering/usage", json=body)
    return RecordUsageResult(**r.json())
```

(Note: the server's CamelCaseRenderer + `populate_by_name=True` accepts both snake and camel in the request body. Camel is preferred because it matches the OpenAPI contract.)

- [x] **Step 4: Update SDK `UsageEvent` type**

Edit `ubb-sdk/ubb/types.py` — find the `UsageEvent` dataclass. Remove `event_type: str` and `provider: str` if they're required fields (replace with `card_slug: str = ""`, `card_name: str = ""`). If the type is used as a loose parser, just add the new fields as optional.

Then update `MeteringClient.get_usage` (around line 170 of `metering.py`) to construct `UsageEvent` with the new fields:

```python
events = [
    UsageEvent(
        id=str(item["id"]),
        request_id=item["requestId"],
        cost_micros=item["costMicros"],
        effective_at=item["effectiveAt"],
        card_slug=item.get("cardSlug", ""),
        card_name=item.get("cardName", ""),
        provider=item.get("provider", ""),
        provider_cost_micros=item.get("providerCostMicros"),
        billed_cost_micros=item.get("billedCostMicros"),
    )
    for item in body["data"]
]
```

Note the switch from snake_case keys to camelCase (the server now returns camelCase exclusively).

- [x] **Step 5: Fix any existing SDK tests that break**

```
cd ubb-sdk && pytest -q
```

Any remaining failures: update call sites from `event_type="..."` to `pricing_card="..."`.

- [x] **Step 6: Commit**

```
git add ubb-sdk/
git commit -m "feat(sdk): require pricing_card slug on record_usage; drop event_type"
```

---

## Phase 7 — UI Alignment

### Task 17: Rewrite `features/pricing-cards/api/types.ts`

**Files:**
- Rewrite: `ubb-ui/src/features/pricing-cards/api/types.ts`

- [x] **Step 1: Replace file contents**

```typescript
export type PricingType = "per_unit" | "flat";
export type CardStatus = "draft" | "active" | "archived";

export interface Dimension {
  id: string;
  metricName: string;
  pricingType: PricingType;
  costPerUnitMicros: number;
  providerCostPerUnitMicros: number | null;
  unitQuantity: number;
  currency: string;
  label: string;
  unit: string;
  validFrom: string;
  validTo: string | null;
}

export interface DimensionInput {
  metricName: string;
  pricingType: PricingType;
  costPerUnitMicros: number;
  providerCostPerUnitMicros: number | null;
  unitQuantity: number;
  currency: string;
  label: string;
  unit: string;
}

export interface PricingCard {
  id: string;
  slug: string;
  name: string;
  provider: string;
  description: string;
  pricingSourceUrl: string;
  groupId: string | null;
  groupName: string | null;
  status: CardStatus;
  dimensions: Dimension[];
  createdAt: string;
  updatedAt: string;
}

export interface CreateCardRequest {
  name: string;
  slug: string;
  provider: string;
  description: string;
  pricingSourceUrl: string;
  groupId: string | null;
  status: CardStatus;
  dimensions: DimensionInput[];
}

export interface CardListResponse {
  data: PricingCard[];
  nextCursor: string | null;
  hasMore: boolean;
}
```

- [x] **Step 2: Commit** (no test yet — UI tests follow in a later task)

```
git add ubb-ui/src/features/pricing-cards/api/types.ts
git commit -m "refactor(ui): rewrite pricing-cards types to match backend slug schema"
```

---

### Task 18: Rewrite `features/pricing-cards/api/api.ts`

**Files:**
- Rewrite: `ubb-ui/src/features/pricing-cards/api/api.ts`

- [x] **Step 1: Replace file contents**

```typescript
import { meteringApi, platformApi } from "@/api/client";
import type { CardListResponse, CreateCardRequest, PricingCard } from "./types";

export async function getCards(): Promise<PricingCard[]> {
  const { data } = await meteringApi.GET("/pricing/cards", {});
  if (!data) return [];
  return (data as CardListResponse).data;
}

export async function getCard(cardId: string): Promise<PricingCard | null> {
  const { data } = await meteringApi.GET("/pricing/cards/{card_id}", {
    params: { path: { card_id: cardId } },
  });
  return (data as PricingCard) ?? null;
}

export async function createCard(req: CreateCardRequest): Promise<PricingCard> {
  const { data } = await meteringApi.POST("/pricing/cards", { body: req });
  return data as PricingCard;
}

// Groups are served by the platform API, not the metering API.
export interface GroupSummary {
  id: string;
  name: string;
  slug: string;
  marginPct: number | null;
}

export async function getGroups(): Promise<GroupSummary[]> {
  const { data } = await platformApi.GET("/groups", {});
  if (!data) return [];
  return (data as { data: GroupSummary[] }).data;
}

// Templates are shipped as a static bundle in the UI (no backend endpoint).
// See features/pricing-cards/api/mock-data.ts::mockTemplates.
```

- [x] **Step 2: Commit**

```
git add ubb-ui/src/features/pricing-cards/api/api.ts
git commit -m "refactor(ui): point pricing-cards api at /pricing/cards and /groups"
```

---

### Task 19: Update `features/pricing-cards` mock + mock-data to match new types

**Files:**
- Modify: `ubb-ui/src/features/pricing-cards/api/mock.ts`
- Modify: `ubb-ui/src/features/pricing-cards/api/mock-data.ts`

- [x] **Step 1: Rewrite `mock-data.ts`**

Rewrite to produce data shaped like the new `PricingCard` + `Dimension` types. Sample card:

```typescript
import type { PricingCard } from "./types";

export const mockPricingCards: PricingCard[] = [
  {
    id: "pc-001",
    slug: "gpt_4o",
    name: "GPT-4o",
    provider: "OpenAI",
    description: "OpenAI GPT-4o for document summarisation",
    pricingSourceUrl: "",
    groupId: "grp-001",
    groupName: "doc_summariser",
    status: "active",
    dimensions: [
      {
        id: "dim-001",
        metricName: "input_tokens",
        pricingType: "per_unit",
        costPerUnitMicros: 3_000,
        providerCostPerUnitMicros: 2_500,
        unitQuantity: 1_000_000,
        currency: "USD",
        label: "Input tokens",
        unit: "per 1M tokens",
        validFrom: "2026-02-15T08:30:00Z",
        validTo: null,
      },
    ],
    createdAt: "2026-02-15T08:30:00Z",
    updatedAt: "2026-02-15T08:30:00Z",
  },
];

// Keep mockTemplates if the wizard uses them — shaped as { slug, name, provider, description, dimensions: DimensionInput[] }
```

- [x] **Step 2: Rewrite `mock.ts` accordingly**

Replace `createCard` etc. to build the new shape from `CreateCardRequest`.

- [x] **Step 3: Commit**

```
git add ubb-ui/src/features/pricing-cards/api/mock.ts ubb-ui/src/features/pricing-cards/api/mock-data.ts
git commit -m "refactor(ui): update pricing-cards mock data to match new types"
```

---

### Task 20: Update pricing-cards components (wizard, schema, simulators)

**Files:**
- Modify: `ubb-ui/src/features/pricing-cards/lib/schema.ts`
- Modify: `ubb-ui/src/features/pricing-cards/components/new-card-wizard.tsx`
- Modify: `ubb-ui/src/features/pricing-cards/components/step-dimensions.tsx`
- Modify: `ubb-ui/src/features/pricing-cards/components/step-review.tsx`
- Modify: `ubb-ui/src/features/pricing-cards/components/dry-run-simulator.tsx`
- Modify: `ubb-ui/src/features/pricing-cards/components/cost-tester.tsx`
- Modify: `ubb-ui/src/features/pricing-cards/components/integration-snippet.tsx`

- [x] **Step 1: Update Zod schema**

Edit `lib/schema.ts` — replace with a schema shaped like `CreateCardRequest`. Drop `pricingPattern`, drop `cardId` (use `slug`), drop `product` (use `groupId`), drop `version`. Dimensions use `metricName`, `pricingType`, `costPerUnitMicros`, `providerCostPerUnitMicros`, `unitQuantity`, `currency`, `label`, `unit`.

- [x] **Step 2: For each component, replace field references**

| Old | New |
|-----|-----|
| `card.cardId` | `card.slug` |
| `card.pricingPattern` | *(derive client-side if needed from `dimensions.every(d => d.pricingType === "per_unit")` → "token" etc.; or drop the visual altogether)* |
| `card.product` | `card.groupName` (display); `card.groupId` (write) |
| `card.version` | *(delete references)* |
| `dimension.key` | `dimension.metricName` |
| `dimension.type` | `dimension.pricingType` |
| `dimension.price` | `dimension.costPerUnitMicros / 1_000_000` (for display) — use `format.ts` util |

- [x] **Step 3: Fix any remaining TypeScript errors**

```
cd ubb-ui && pnpm tsc --noEmit
```

Work through errors file-by-file.

- [x] **Step 4: Commit**

```
git add ubb-ui/src/features/pricing-cards/
git commit -m "refactor(ui): align pricing-cards components with slug schema"
```

---

### Task 21: Rewrite `features/events/api/types.ts`

**Files:**
- Rewrite: `ubb-ui/src/features/events/api/types.ts`

- [x] **Step 1: Replace file contents**

```typescript
export interface UsageEvent {
  id: string;
  effectiveAt: string;
  customerId: string;
  customerExternalId: string;
  group: string | null;
  cardId: string | null;
  cardSlug: string | null;
  cardName: string | null;
  provider: string;
  usageMetrics: Record<string, number>;
  providerCostMicros: number | null;
  billedCostMicros: number | null;
}

export interface StagedEvent {
  effectiveAt: string;
  customerExternalId: string;
  group: string;
  cardSlug: string;
  usageMetrics: Record<string, number>;
  idempotencyKey?: string;
}

export interface ValidationError {
  field: "effectiveAt" | "customerExternalId" | "cardSlug" | "usageMetrics" | "quantity";
  message: string;
  warning?: boolean;
}

export interface EventFilters {
  dateFrom?: string;
  dateTo?: string;
  customerId?: string;
  group?: string;
  cardSlug?: string;
  cursor?: string;
  limit?: number;
}

export interface EventsListResponse {
  events: UsageEvent[];
  totalCount: number;
  totalCostMicros: number;
  nextCursor: string | null;
  hasMore: boolean;
}

export interface FilterOption {
  key: string;
  eventCount: number;
}

export interface EventFilterOptions {
  customers: FilterOption[];
  groups: FilterOption[];
  cards: FilterOption[];
  ungroupedCount: number;
  cardDimensions: Record<string, string[]>; // cardSlug -> [metricName]
  dimensionPrices: Record<string, number>;  // metricName -> costPerUnitMicros
}

export type AuditAction = "added" | "reversed";

export interface AuditEntry {
  id: string;
  action: AuditAction;
  reason: string;
  rowCount: number;
  author: string;
  createdAt: string;
  reversedAt: string | null;
}

export interface PushResult {
  pushedCount: number;
  batchId: string;
}
```

- [x] **Step 2: Commit**

```
git add ubb-ui/src/features/events/api/types.ts
git commit -m "refactor(ui): rewrite events types to match backend EventOut/EventBatchOut"
```

---

### Task 22: Update `features/events/api/api.ts`

**Files:**
- Modify: `ubb-ui/src/features/events/api/api.ts`

- [x] **Step 1: Update the file**

```typescript
import { platformApi } from "@/api/client";
import type {
  AuditEntry, EventFilterOptions, EventFilters,
  EventsListResponse, PushResult, StagedEvent,
} from "./types";

export async function getFilterOptions(): Promise<EventFilterOptions> {
  const { data } = await platformApi.GET("/events/filter-options", {});
  return data as EventFilterOptions;
}

export async function getEvents(filters: EventFilters): Promise<EventsListResponse> {
  const { data } = await platformApi.POST("/events/list", { body: filters });
  return data as EventsListResponse;
}

export async function pushEvents(
  events: StagedEvent[],
  reason: string,
): Promise<PushResult> {
  const { data } = await platformApi.POST("/events/push", { body: { events, reason } });
  return data as PushResult;
}

export async function getAuditTrail(): Promise<AuditEntry[]> {
  const { data } = await platformApi.GET("/events/audit-trail", {});
  return (data as AuditEntry[]) ?? [];
}

export async function reverseAuditEntry(batchId: string): Promise<void> {
  await platformApi.POST("/events/audit-trail/{batch_id}/reverse", {
    params: { path: { batch_id: batchId } },
  });
}

export async function exportCsv(filters: EventFilters): Promise<{ downloadUrl: string }> {
  const { data } = await platformApi.POST("/events/export", { body: filters });
  return data as { downloadUrl: string };
}
```

The only functional change besides types is `{entryId}` → `{batch_id}`.

- [x] **Step 2: Commit**

```
git add ubb-ui/src/features/events/api/api.ts
git commit -m "refactor(ui): align events api with batch_id path + new filter shape"
```

---

### Task 23: Update `features/events` mock + components

**Files:**
- Modify: `ubb-ui/src/features/events/api/mock.ts`
- Modify: `ubb-ui/src/features/events/api/mock-data.ts`
- Modify: `ubb-ui/src/features/events/components/*.tsx`

- [x] **Step 1: Align mock data** to new `UsageEvent` / `AuditEntry` shapes (add `effectiveAt`, `cardSlug`, `cardName`, `usageMetrics`, `providerCostMicros`/`billedCostMicros`; replace `date`→`createdAt`, `reversedDate`→`reversedAt`; drop `title`; drop `edited` from action enum).

- [x] **Step 2: Update components** — the events list, audit trail, and push wizard all read fields that changed. Fix each. Display `cardName` with `cardSlug` in a tooltip for clarity. Show `billedCostMicros` formatted via `lib/format.ts`.

- [x] **Step 3: Typecheck**

```
cd ubb-ui && pnpm tsc --noEmit
```

- [x] **Step 4: Commit**

```
git add ubb-ui/src/features/events/
git commit -m "refactor(ui): align events mock + components with backend snapshots"
```

---

### Task 24: Rewrite `features/dashboard/api/types.ts` — split into three responses

**Files:**
- Rewrite: `ubb-ui/src/features/dashboard/api/types.ts`

- [x] **Step 1: Replace file contents**

```typescript
export type TimeRange = "7d" | "30d" | "90d" | "YTD";

export interface Sparklines {
  revenue: number[];          // micros
  apiCosts: number[];         // micros
  grossMargin: number[];      // micros
  marginPct: number[];
  costPerRev: number[];
}

export interface StatsResponse {
  revenueMicros: number;
  apiCostsMicros: number;
  grossMarginMicros: number;
  marginPercentage: number;
  costPerDollarRevenue: number;
  revenuePrevChange: number;
  costsPrevChange: number;
  marginPrevChange: number;
  marginPctPrevChange: number;
  costPerRevPrevChange: number;
  sparklines: Sparklines;
}

export interface DailyChartPoint {
  date: string;
  revenueMicros: number;
  apiCostsMicros: number;
  marginMicros: number;
}

export interface StackedSeries {
  series: { key: string; label: string }[];
  data: Array<{ date: string; [key: string]: number | string }>;
}

export interface GroupBreakdown {
  key: string;
  label: string;
  valueMicros: number;
  percentage: number;
}

export interface ChartsResponse {
  revenueTimeSeries: DailyChartPoint[];
  costByGroup: StackedSeries;
  costByCard: StackedSeries;
  revenueByGroup: GroupBreakdown[];
  marginByGroup: GroupBreakdown[];
}

export interface DashboardCustomerRow {
  customerId: string;
  externalId: string;
  revenueMicros: number;
  apiCostsMicros: number;
  marginMicros: number;
  marginPercentage: number;
  eventCount: number;
}

export interface CustomersResponse {
  customers: DashboardCustomerRow[];
}
```

- [x] **Step 2: Commit**

```
git add ubb-ui/src/features/dashboard/api/types.ts
git commit -m "refactor(ui): split dashboard types into stats/charts/customers"
```

---

### Task 25: Rewrite `features/dashboard/api/api.ts` + `queries.ts`

**Files:**
- Rewrite: `ubb-ui/src/features/dashboard/api/api.ts`
- Modify: `ubb-ui/src/features/dashboard/api/queries.ts`

- [x] **Step 1: Replace `api.ts`**

```typescript
import { platformApi } from "@/api/client";
import type {
  ChartsResponse, CustomersResponse, StatsResponse, TimeRange,
} from "./types";

export async function getStats(range: TimeRange): Promise<StatsResponse> {
  const { data } = await platformApi.GET("/dashboard/stats", {
    params: { query: { range } },
  });
  return data as StatsResponse;
}

export async function getCharts(range: TimeRange): Promise<ChartsResponse> {
  const { data } = await platformApi.GET("/dashboard/charts", {
    params: { query: { range } },
  });
  return data as ChartsResponse;
}

export async function getCustomers(range: TimeRange): Promise<CustomersResponse> {
  const { data } = await platformApi.GET("/dashboard/customers", {
    params: { query: { range } },
  });
  return data as CustomersResponse;
}
```

- [x] **Step 2: Update `queries.ts`** to expose three hooks instead of one monolithic `useDashboard`:

```typescript
import { useQuery } from "@tanstack/react-query";
import { dashboardApi } from "./provider";
import type { TimeRange } from "./types";

export const useDashboardStats = (range: TimeRange) =>
  useQuery({ queryKey: ["dashboard","stats",range], queryFn: () => dashboardApi.getStats(range) });

export const useDashboardCharts = (range: TimeRange) =>
  useQuery({ queryKey: ["dashboard","charts",range], queryFn: () => dashboardApi.getCharts(range) });

export const useDashboardCustomers = (range: TimeRange) =>
  useQuery({ queryKey: ["dashboard","customers",range], queryFn: () => dashboardApi.getCustomers(range) });
```

Update `provider.ts` to export `getStats`, `getCharts`, `getCustomers` (mapping to the new mock or real api).

- [x] **Step 3: Update dashboard components**

Each sub-section of the dashboard page calls its own hook. The stats card uses `useDashboardStats`, charts use `useDashboardCharts`, customer table uses `useDashboardCustomers`. All three load in parallel.

Replace references to dollar fields with micros equivalents, formatted via `lib/format.ts`.

- [x] **Step 4: Typecheck**

```
cd ubb-ui && pnpm tsc --noEmit
```

- [x] **Step 5: Commit**

```
git add ubb-ui/src/features/dashboard/
git commit -m "refactor(ui): dashboard hooks split across stats/charts/customers"
```

---

### Task 26: Regenerate OpenAPI schemas + TypeScript types

- [x] **Step 1: Bring up the Django dev server in another terminal**

```
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python manage.py runserver 0.0.0.0:8000
```

- [x] **Step 2: Regenerate TS types**

```
cd ubb-ui && bash scripts/generate-api.sh
```

- [x] **Step 3: Save the regenerated OpenAPI JSON**

The `generate-api.sh` script calls `openapi-typescript <url>`. Save the intermediate JSON too:

```
cd ubb-ui
for api in platform metering billing tenant; do
  curl -s "http://localhost:8000/api/v1/$api/openapi.json" > "src/api/schemas/$api.json"
done
```

- [x] **Step 4: Typecheck and fix any type drift**

```
cd ubb-ui && pnpm tsc --noEmit
```

- [x] **Step 5: Commit**

```
git add ubb-ui/src/api/
git commit -m "chore(ui): regenerate OpenAPI schemas + TS types after alignment"
```

---

## Phase 8 — Integration

### Task 27: Run full backend suite

- [x] **Step 1: Run**

```
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest -q
```

Expected: all pass. Record the passing count.

- [x] **Step 2: Run SDK suite**

```
cd ubb-sdk && pytest -q
```

- [x] **Step 3: Run UI typecheck + vitest**

```
cd ubb-ui && pnpm tsc --noEmit && pnpm vitest run
```

Expected: all pass.

If any fail, fix in-session before proceeding.

---

### Task 28: Manual smoke — bring UI up against the real API

- [x] **Step 1: Set UI env**

Edit `ubb-ui/.env.local`:

```
VITE_API_PROVIDER=api
VITE_API_URL=http://localhost:8000
```

- [x] **Step 2: Start servers**

Terminal A:
```
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python manage.py runserver
```

Terminal B:
```
cd ubb-ui && pnpm dev
```

- [x] **Step 3: Verify each page**

Open the UI in a browser. Check:
- **Pricing Cards list** — loads cards from `/api/v1/metering/pricing/cards`. Each card shows its dimensions (previously "rates"), slug, group name. No "pricingPattern" visible.
- **Pricing Card creation wizard** — wizard lets the operator set per-dimension `costPerUnitMicros` and `providerCostPerUnitMicros`. Margin field pre-fills from group → tenant default.
- **Events page** — list shows `cardName` (`cardSlug` in tooltip), `provider`, billed cost, provider cost. Filter dropdowns populate from `/events/filter-options`.
- **Dashboard** — stats, charts, customers all load in parallel. Values display correctly in dollars (formatted from micros).

- [x] **Step 4: Fix any runtime issues**

Common issues: OpenAPI type drift (regenerate), stale mock fallthrough (check provider.ts), formatting errors (check lib/format.ts handles micros).

- [x] **Step 5: Record the outcome** (no commit needed unless fixes were made)

---

### Task 29: Final commit + plan checkbox pass

- [x] **Step 1: Update the plan document**

Mark every checkbox `[x]` in this plan file as you complete each task (or do the whole lot in one edit at the end).

- [x] **Step 2: Commit plan**

```
git add docs/superpowers/plans/2026-04-16-metering-slug-alignment.md
git commit -m "docs: mark metering slug alignment plan complete"
```

---

## Summary

- **Data model:** Card loses `event_type`, `dimensions` dict, `dimensions_hash`; Rate gains `provider_cost_per_unit_micros`; UsageEvent gains `card_slug`/`card_name` snapshots; `TenantMarkup` deleted; `Tenant.default_margin_pct` added.
- **Service:** `PricingService.price_event_by_slug` becomes the only path — no runtime margin resolution. `UsageService.record_usage` requires `pricing_card`.
- **API:** `CardOut` rebranded (rates → dimensions; no eventType); `EventOut` includes snapshots; tenant default margin endpoints; analytics groups by card.
- **SDK:** `record_usage` takes `pricing_card` required.
- **UI:** types/api/components realigned; dashboard split across three hooks; OpenAPI artefacts regenerated.

Ship it.
