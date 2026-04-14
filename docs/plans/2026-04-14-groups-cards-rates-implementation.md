# Groups, Cards & Rates Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Introduce Group, Card, and Rate models; standardise markup to margin; replace group_keys with a simple group field; update the pricing pipeline and API.

**Architecture:** Group in `apps/platform/groups/` (hierarchy + margin), Card + Rate in `apps/metering/pricing/` (pure pricing). UsageEvent.group is a simple CharField. PricingService resolves Card for cost and Group for margin independently.

**Tech Stack:** Django 6.0, django-ninja, PostgreSQL, pytest, existing BaseModel pattern.

**Spec:** `docs/plans/2026-04-14-groups-cards-rates-design.md`

**Run tests:** `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest --tb=short -q`

**Run single test:** `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest <path>::<class>::<method> -v`

---

## File Map

### New files

| File | Responsibility |
|------|---------------|
| `apps/platform/groups/__init__.py` | Package init |
| `apps/platform/groups/apps.py` | Django app config |
| `apps/platform/groups/models.py` | Group model |
| `apps/platform/groups/admin.py` | GroupAdmin |
| `apps/platform/groups/tests/__init__.py` | Test package |
| `apps/platform/groups/tests/test_models.py` | Group model tests |
| `apps/platform/groups/tests/test_api.py` | Group CRUD endpoint tests |
| `api/v1/group_endpoints.py` | Group CRUD API endpoints |

### Modified files

| File | Change |
|------|--------|
| `config/settings.py` | Add `apps.platform.groups` to INSTALLED_APPS |
| `config/urls.py` | Add group API url pattern |
| `apps/metering/pricing/models.py` | Add Card model, rename ProviderRate → Rate, change TenantMarkup to margin_pct |
| `apps/metering/pricing/admin.py` | Update for Card + Rate + TenantMarkup changes |
| `apps/metering/pricing/services/pricing_service.py` | Card lookup, margin resolution with Group |
| `apps/metering/pricing/tests/test_models.py` | Update for Card + Rate + margin |
| `apps/metering/pricing/tests/test_pricing_service.py` | Update for Card lookup + margin resolution |
| `apps/metering/usage/models.py` | Replace `group_keys` with `group` CharField |
| `apps/metering/usage/services/usage_service.py` | Replace `group_keys` param with `group`, pass to PricingService |
| `apps/metering/usage/tests/test_group_keys.py` | Rewrite as test_group.py for new field |
| `apps/platform/tenants/models.py` | Add `group_label` field |
| `api/v1/schemas.py` | Update RecordUsageRequest (group replaces group_keys), add Group/Card/Rate schemas |
| `api/v1/metering_endpoints.py` | Update usage endpoint, replace rate/markup CRUD with card-based |
| `ubb-sdk/ubb/metering.py` | Replace `group_keys` with `group` parameter |

---

## Task 1: Group Model + Admin

**Files:**
- Create: `apps/platform/groups/__init__.py`, `apps/platform/groups/apps.py`, `apps/platform/groups/models.py`, `apps/platform/groups/admin.py`
- Create: `apps/platform/groups/tests/__init__.py`, `apps/platform/groups/tests/test_models.py`
- Modify: `config/settings.py`

- [ ] **Step 1: Scaffold the groups app**

Create `apps/platform/groups/__init__.py` (empty).

Create `apps/platform/groups/apps.py`:
```python
from django.apps import AppConfig


class GroupsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.platform.groups"
    label = "groups"
```

Create `apps/platform/groups/tests/__init__.py` (empty).

- [ ] **Step 2: Write failing Group model test**

Create `apps/platform/groups/tests/test_models.py`:
```python
from django.test import TestCase
from django.db import IntegrityError
from apps.platform.tenants.models import Tenant
from apps.platform.groups.models import Group


class GroupModelTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Test", stripe_connected_account_id="acct_test"
        )

    def test_create_group(self):
        group = Group.objects.create(
            tenant=self.tenant,
            name="Property Search",
            slug="property_search",
        )
        self.assertEqual(group.name, "Property Search")
        self.assertEqual(group.slug, "property_search")
        self.assertEqual(group.status, "active")
        self.assertIsNone(group.margin_pct)
        self.assertIsNone(group.parent)

    def test_group_with_margin(self):
        group = Group.objects.create(
            tenant=self.tenant,
            name="Property Search",
            slug="property_search",
            margin_pct=65.00,
        )
        self.assertEqual(group.margin_pct, 65.00)

    def test_unique_active_slug_per_tenant(self):
        Group.objects.create(
            tenant=self.tenant, name="Group A", slug="same_slug"
        )
        with self.assertRaises(IntegrityError):
            Group.objects.create(
                tenant=self.tenant, name="Group B", slug="same_slug"
            )

    def test_archived_slug_does_not_conflict(self):
        Group.objects.create(
            tenant=self.tenant, name="Old", slug="reuse_me", status="archived"
        )
        new = Group.objects.create(
            tenant=self.tenant, name="New", slug="reuse_me", status="active"
        )
        self.assertEqual(new.status, "active")

    def test_parent_relationship(self):
        parent = Group.objects.create(
            tenant=self.tenant, name="Parent", slug="parent"
        )
        child = Group.objects.create(
            tenant=self.tenant, name="Child", slug="child", parent=parent
        )
        self.assertEqual(child.parent, parent)
        self.assertIn(child, parent.children.all())

    def test_parent_set_null_on_delete(self):
        parent = Group.objects.create(
            tenant=self.tenant, name="Parent", slug="parent"
        )
        child = Group.objects.create(
            tenant=self.tenant, name="Child", slug="child", parent=parent
        )
        parent.delete()
        child.refresh_from_db()
        self.assertIsNone(child.parent)

    def test_different_tenants_same_slug(self):
        tenant2 = Tenant.objects.create(
            name="Other", stripe_connected_account_id="acct_other"
        )
        Group.objects.create(
            tenant=self.tenant, name="G1", slug="shared_slug"
        )
        g2 = Group.objects.create(
            tenant=tenant2, name="G2", slug="shared_slug"
        )
        self.assertEqual(g2.slug, "shared_slug")
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/platform/groups/tests/test_models.py -v`

Expected: ImportError — `apps.platform.groups.models` does not exist yet.

- [ ] **Step 4: Implement Group model**

Create `apps/platform/groups/models.py`:
```python
from django.db import models
from core.models import BaseModel


GROUP_STATUS_CHOICES = [
    ("active", "Active"),
    ("archived", "Archived"),
]


class Group(BaseModel):
    """Tenant-defined billing group for organising pricing and margins."""

    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="groups",
    )
    parent = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="children",
    )
    name = models.CharField(max_length=255)
    slug = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    margin_pct = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Target margin %. Null = inherit from parent or default.",
    )
    status = models.CharField(
        max_length=20,
        choices=GROUP_STATUS_CHOICES,
        default="active",
    )

    class Meta:
        db_table = "ubb_group"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "slug"],
                condition=models.Q(status="active"),
                name="uq_group_active_tenant_slug",
            ),
        ]
        indexes = [
            models.Index(
                fields=["tenant", "status"],
                name="idx_group_tenant_status",
            ),
        ]

    def __str__(self):
        return f"{self.name} ({self.slug})"
```

- [ ] **Step 5: Register app and run migration**

Add `"apps.platform.groups"` to `INSTALLED_APPS` in `config/settings.py`, after `"apps.platform.runs"`.

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python manage.py makemigrations groups`
Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python manage.py migrate`

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/platform/groups/tests/test_models.py -v`

Expected: All 7 tests PASS.

- [ ] **Step 7: Add GroupAdmin**

Create `apps/platform/groups/admin.py`:
```python
from django.contrib import admin
from apps.platform.groups.models import Group


@admin.register(Group)
class GroupAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "tenant", "margin_pct", "status", "parent", "created_at")
    list_filter = ("status", "tenant")
    search_fields = ("name", "slug")
    readonly_fields = ("id", "created_at", "updated_at")
```

- [ ] **Step 8: Commit**

```bash
git add apps/platform/groups/ config/settings.py
git commit -m "feat: add Group model in apps/platform/groups"
```

---

## Task 2: Card + Rate Models

**Files:**
- Modify: `apps/metering/pricing/models.py`
- Modify: `apps/metering/pricing/admin.py`
- Create: `apps/metering/pricing/tests/test_card_rate.py`

- [ ] **Step 1: Write failing Card + Rate model tests**

Create `apps/metering/pricing/tests/test_card_rate.py`:
```python
import hashlib
import json
from django.test import TestCase
from django.db import IntegrityError
from apps.platform.tenants.models import Tenant
from apps.metering.pricing.models import Card, Rate


class CardModelTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Test", stripe_connected_account_id="acct_test"
        )

    def test_create_card(self):
        card = Card.objects.create(
            tenant=self.tenant,
            name="Gemini 2.0 Flash",
            provider="google_gemini",
            event_type="llm_call",
            dimensions={"model": "gemini-2.0-flash"},
        )
        self.assertEqual(card.name, "Gemini 2.0 Flash")
        self.assertEqual(card.status, "active")
        self.assertNotEqual(card.dimensions_hash, "")

    def test_dimensions_hash_computed_on_save(self):
        card = Card.objects.create(
            tenant=self.tenant,
            name="Test Card",
            provider="test",
            event_type="test",
            dimensions={"model": "gpt-4o", "region": "us"},
        )
        expected = hashlib.sha256(
            json.dumps({"model": "gpt-4o", "region": "us"}, sort_keys=True).encode()
        ).hexdigest()
        self.assertEqual(card.dimensions_hash, expected)

    def test_unique_active_card(self):
        Card.objects.create(
            tenant=self.tenant,
            name="Card A",
            provider="p",
            event_type="e",
            dimensions={"model": "x"},
        )
        with self.assertRaises(IntegrityError):
            Card.objects.create(
                tenant=self.tenant,
                name="Card B",
                provider="p",
                event_type="e",
                dimensions={"model": "x"},
            )

    def test_archived_card_does_not_conflict(self):
        Card.objects.create(
            tenant=self.tenant,
            name="Old",
            provider="p",
            event_type="e",
            dimensions={},
            status="archived",
        )
        new = Card.objects.create(
            tenant=self.tenant,
            name="New",
            provider="p",
            event_type="e",
            dimensions={},
        )
        self.assertEqual(new.status, "active")


class RateModelTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Test", stripe_connected_account_id="acct_test"
        )
        self.card = Card.objects.create(
            tenant=self.tenant,
            name="Test Card",
            provider="openai",
            event_type="llm_call",
            dimensions={"model": "gpt-4o"},
        )

    def test_create_rate(self):
        rate = Rate.objects.create(
            card=self.card,
            metric_name="input_tokens",
            cost_per_unit_micros=5_000,
            unit_quantity=1_000_000,
        )
        self.assertEqual(rate.metric_name, "input_tokens")
        self.assertIsNone(rate.valid_to)

    def test_calculate_cost_micros(self):
        rate = Rate.objects.create(
            card=self.card,
            metric_name="input_tokens",
            cost_per_unit_micros=75_000,
            unit_quantity=1_000_000,
        )
        # 1M tokens at 75000 micros / 1M = 75000 micros = $0.075
        self.assertEqual(rate.calculate_cost_micros(1_000_000), 75_000)
        # 1000 tokens: (1000 * 75000 + 500000) // 1000000 = 75
        self.assertEqual(rate.calculate_cost_micros(1_000), 75)

    def test_unique_active_rate_per_card_metric(self):
        Rate.objects.create(
            card=self.card,
            metric_name="input_tokens",
            cost_per_unit_micros=5_000,
        )
        with self.assertRaises(IntegrityError):
            Rate.objects.create(
                card=self.card,
                metric_name="input_tokens",
                cost_per_unit_micros=10_000,
            )

    def test_rates_via_card_relationship(self):
        Rate.objects.create(
            card=self.card, metric_name="input_tokens", cost_per_unit_micros=5_000,
        )
        Rate.objects.create(
            card=self.card, metric_name="output_tokens", cost_per_unit_micros=15_000,
        )
        self.assertEqual(self.card.rates.count(), 2)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/metering/pricing/tests/test_card_rate.py -v`

Expected: ImportError — `Card` and `Rate` not defined.

- [ ] **Step 3: Implement Card + Rate models**

In `apps/metering/pricing/models.py`, add Card and Rate classes (keep ProviderRate for now — it will be removed in Task 13). Add these **above** the existing ProviderRate class:

```python
class Card(BaseModel):
    """A pricing card grouping related Rates for a provider + model combination."""

    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="pricing_cards",
    )
    name = models.CharField(max_length=255)
    provider = models.CharField(max_length=100, db_index=True)
    event_type = models.CharField(max_length=100, db_index=True)
    dimensions = models.JSONField(default=dict)
    dimensions_hash = models.CharField(max_length=64, db_index=True, blank=True)
    description = models.TextField(blank=True, default="")
    status = models.CharField(
        max_length=20,
        choices=[("active", "Active"), ("archived", "Archived")],
        default="active",
    )

    class Meta:
        db_table = "ubb_card"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "provider", "event_type", "dimensions_hash"],
                condition=models.Q(status="active"),
                name="uq_card_active_per_tenant_provider_event_dims",
            ),
        ]
        indexes = [
            models.Index(
                fields=["tenant", "provider", "event_type"],
                name="idx_card_tenant_lookup",
            ),
        ]

    def save(self, *args, **kwargs):
        canonical = json.dumps(self.dimensions, sort_keys=True)
        self.dimensions_hash = hashlib.sha256(canonical.encode()).hexdigest()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.provider}/{self.event_type})"


class Rate(BaseModel):
    """A single metric price line within a Card."""

    card = models.ForeignKey(Card, on_delete=models.CASCADE, related_name="rates")
    metric_name = models.CharField(max_length=100, db_index=True)
    cost_per_unit_micros = models.BigIntegerField()
    unit_quantity = models.BigIntegerField(default=1_000_000)
    currency = models.CharField(max_length=3, default="USD")
    valid_from = models.DateTimeField(auto_now_add=True, db_index=True)
    valid_to = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        db_table = "ubb_rate"
        constraints = [
            models.UniqueConstraint(
                fields=["card", "metric_name"],
                condition=models.Q(valid_to__isnull=True),
                name="uq_rate_active_per_card_metric",
            ),
        ]

    def calculate_cost_micros(self, units: int) -> int:
        """Round-half-up cost calculation."""
        return (
            units * self.cost_per_unit_micros + self.unit_quantity // 2
        ) // self.unit_quantity

    def __str__(self):
        return f"{self.metric_name} @ {self.cost_per_unit_micros}/{self.unit_quantity}"
```

Ensure `hashlib` and `json` are imported at the top of the file (they already are for ProviderRate).

- [ ] **Step 4: Run migration**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python manage.py makemigrations pricing`
Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python manage.py migrate`

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/metering/pricing/tests/test_card_rate.py -v`

Expected: All 9 tests PASS.

- [ ] **Step 6: Update admin for Card + Rate**

In `apps/metering/pricing/admin.py`, add Card and Rate admin registrations:

```python
from apps.metering.pricing.models import Card, Rate

@admin.register(Card)
class CardAdmin(admin.ModelAdmin):
    list_display = ("name", "provider", "event_type", "tenant", "status", "created_at")
    list_filter = ("provider", "event_type", "status")
    search_fields = ("name", "provider", "event_type")
    readonly_fields = ("id", "dimensions_hash", "created_at", "updated_at")

@admin.register(Rate)
class RateAdmin(admin.ModelAdmin):
    list_display = ("card", "metric_name", "cost_per_unit_micros", "unit_quantity", "currency", "valid_from", "valid_to")
    list_filter = ("currency",)
    search_fields = ("metric_name", "card__name")
    readonly_fields = ("id", "created_at", "updated_at")
```

- [ ] **Step 7: Commit**

```bash
git add apps/metering/pricing/
git commit -m "feat: add Card and Rate models"
```

---

## Task 3: TenantMarkup → margin_pct

**Files:**
- Modify: `apps/metering/pricing/models.py`
- Modify: `apps/metering/pricing/tests/test_models.py`

- [ ] **Step 1: Write failing margin test**

Add to `apps/metering/pricing/tests/test_models.py`:
```python
class TenantMarkupMarginTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Test", stripe_connected_account_id="acct_test"
        )

    def test_margin_pct_default_zero(self):
        markup = TenantMarkup.objects.create(tenant=self.tenant)
        self.assertEqual(markup.margin_pct, 0)

    def test_apply_margin_zero_passthrough(self):
        markup = TenantMarkup.objects.create(tenant=self.tenant, margin_pct=0)
        self.assertEqual(markup.apply_margin(1_000_000), 1_000_000)

    def test_apply_margin_fifty_percent(self):
        markup = TenantMarkup.objects.create(tenant=self.tenant, margin_pct=50)
        # $1.00 provider cost / (1 - 0.50) = $2.00 billed
        self.assertEqual(markup.apply_margin(1_000_000), 2_000_000)

    def test_apply_margin_sixty_percent(self):
        markup = TenantMarkup.objects.create(tenant=self.tenant, margin_pct=60)
        # $1.00 / 0.40 = $2.50
        self.assertEqual(markup.apply_margin(1_000_000), 2_500_000)

    def test_apply_margin_eighty_percent(self):
        markup = TenantMarkup.objects.create(tenant=self.tenant, margin_pct=80)
        # $1.00 / 0.20 = $5.00
        self.assertEqual(markup.apply_margin(1_000_000), 5_000_000)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/metering/pricing/tests/test_models.py::TenantMarkupMarginTest -v`

Expected: FAIL — `margin_pct` field and `apply_margin` method do not exist.

- [ ] **Step 3: Update TenantMarkup model**

In `apps/metering/pricing/models.py`, replace the TenantMarkup fields and method:

Remove `markup_percentage_micros` and `fixed_uplift_micros` fields. Remove `calculate_markup_micros` method.

Replace with:
```python
class TenantMarkup(BaseModel):
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="markups",
    )
    event_type = models.CharField(max_length=100, blank=True, default="", db_index=True)
    provider = models.CharField(max_length=100, blank=True, default="", db_index=True)
    margin_pct = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        help_text="Target margin %. 0 = pass-through.",
    )
    valid_from = models.DateTimeField(auto_now_add=True, db_index=True)
    valid_to = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "ubb_tenant_markup"
        indexes = [
            models.Index(
                fields=["tenant", "event_type", "provider"],
                name="idx_markup_tenant_lookup",
            ),
        ]

    def apply_margin(self, provider_cost_micros: int) -> int:
        """Calculate billed cost from provider cost and target margin.

        billed = provider_cost / (1 - margin_pct/100)
        """
        if self.margin_pct <= 0:
            return provider_cost_micros
        from decimal import Decimal
        divisor = Decimal("1") - (self.margin_pct / Decimal("100"))
        # Use integer arithmetic with rounding for micros precision
        return int(
            (Decimal(provider_cost_micros) / divisor).quantize(Decimal("1"))
        )

    def __str__(self):
        scope = f"{self.event_type}/{self.provider}" if self.event_type else "global"
        return f"Markup {self.margin_pct}% ({scope})"
```

- [ ] **Step 4: Run migration**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python manage.py makemigrations pricing`
Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python manage.py migrate`

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/metering/pricing/tests/test_models.py::TenantMarkupMarginTest -v`

Expected: All 5 tests PASS.

- [ ] **Step 6: Update existing TenantMarkup tests**

Update any existing tests in `apps/metering/pricing/tests/test_models.py` that reference `markup_percentage_micros` or `fixed_uplift_micros` — replace with `margin_pct` and use `apply_margin()` instead of `calculate_markup_micros()`.

- [ ] **Step 7: Run full pricing test suite**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/metering/pricing/tests/ -v`

Expected: All tests PASS.

- [ ] **Step 8: Commit**

```bash
git add apps/metering/pricing/
git commit -m "feat: replace TenantMarkup markup with margin_pct"
```

---

## Task 4: UsageEvent.group + Tenant.group_label

**Files:**
- Modify: `apps/metering/usage/models.py`
- Modify: `apps/platform/tenants/models.py`

- [ ] **Step 1: Replace group_keys with group on UsageEvent**

In `apps/metering/usage/models.py`:

Remove: `group_keys = models.JSONField(null=True, blank=True)`

Add: `group = models.CharField(max_length=255, null=True, blank=True, db_index=True)`

Also remove the GIN index migration for group_keys if referenced in Meta (check the indexes list).

- [ ] **Step 2: Add group_label to Tenant**

In `apps/platform/tenants/models.py`, add to the Tenant model:

```python
group_label = models.CharField(
    max_length=100,
    default="Products",
    help_text="Display label for groups in the UI.",
)
```

- [ ] **Step 3: Run migrations**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python manage.py makemigrations usage tenants`
Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python manage.py migrate`

- [ ] **Step 4: Commit**

```bash
git add apps/metering/usage/ apps/platform/tenants/
git commit -m "feat: replace group_keys with group CharField, add Tenant.group_label"
```

---

## Task 5: Update UsageService for group parameter

**Files:**
- Modify: `apps/metering/usage/services/usage_service.py`
- Rewrite: `apps/metering/usage/tests/test_group_keys.py` → `apps/metering/usage/tests/test_group.py`

- [ ] **Step 1: Write failing group tests**

Delete `apps/metering/usage/tests/test_group_keys.py`.

Create `apps/metering/usage/tests/test_group.py`:
```python
from unittest.mock import patch
from django.test import TestCase
from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.metering.usage.models import UsageEvent
from apps.metering.usage.services.usage_service import UsageService


class GroupFieldTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Test", stripe_connected_account_id="acct_test"
        )
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="c1"
        )

    @patch("apps.platform.events.tasks.process_single_event")
    def test_group_stored_on_event(self, mock_process):
        result = UsageService.record_usage(
            tenant=self.tenant,
            customer=self.customer,
            request_id="req_g1",
            idempotency_key="idem_g1",
            cost_micros=1_000_000,
            group="property_search",
        )
        event = UsageEvent.objects.get(id=result["event_id"])
        self.assertEqual(event.group, "property_search")

    @patch("apps.platform.events.tasks.process_single_event")
    def test_group_null_by_default(self, mock_process):
        result = UsageService.record_usage(
            tenant=self.tenant,
            customer=self.customer,
            request_id="req_g2",
            idempotency_key="idem_g2",
            cost_micros=1_000_000,
        )
        event = UsageEvent.objects.get(id=result["event_id"])
        self.assertIsNone(event.group)

    @patch("apps.platform.events.tasks.process_single_event")
    def test_group_max_length_255(self, mock_process):
        long_group = "a" * 255
        result = UsageService.record_usage(
            tenant=self.tenant,
            customer=self.customer,
            request_id="req_g3",
            idempotency_key="idem_g3",
            cost_micros=1_000_000,
            group=long_group,
        )
        event = UsageEvent.objects.get(id=result["event_id"])
        self.assertEqual(event.group, long_group)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/metering/usage/tests/test_group.py -v`

Expected: FAIL — `record_usage` still expects `group_keys`, not `group`.

- [ ] **Step 3: Update UsageService**

In `apps/metering/usage/services/usage_service.py`:

1. Remove the `validate_group_keys` function and `GROUP_KEY_PATTERN` constant.
2. Replace `group_keys=None` parameter with `group=None` in `record_usage()`.
3. Remove the `validate_group_keys(group_keys)` call.
4. In the `UsageEvent.objects.create(...)` call, replace `group_keys=group_keys` with `group=group`.

The updated `record_usage` signature:
```python
@staticmethod
@transaction.atomic
def record_usage(
    tenant,
    customer,
    request_id,
    idempotency_key,
    cost_micros=None,
    metadata=None,
    event_type=None,
    provider=None,
    usage_metrics=None,
    properties=None,
    group=None,
    run_id=None,
):
```

And in the create call:
```python
event = UsageEvent.objects.create(
    ...
    group=group,
    ...
)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/metering/usage/tests/test_group.py -v`

Expected: All 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/metering/usage/
git commit -m "feat: replace group_keys with group in UsageService"
```

---

## Task 6: PricingService — Card/Rate Lookup + Margin Resolution

**Files:**
- Modify: `apps/metering/pricing/services/pricing_service.py`
- Create: `apps/metering/pricing/tests/test_pricing_service_v2.py`

- [ ] **Step 1: Write failing pricing tests for Card + Rate + Group margin**

Create `apps/metering/pricing/tests/test_pricing_service_v2.py`:
```python
from decimal import Decimal
from django.test import TestCase
from apps.platform.tenants.models import Tenant
from apps.platform.groups.models import Group
from apps.metering.pricing.models import Card, Rate, TenantMarkup
from apps.metering.pricing.services.pricing_service import PricingService, PricingError


class PricingServiceCardTest(TestCase):
    """Test PricingService with Card + Rate models."""

    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Test", stripe_connected_account_id="acct_test"
        )
        self.card = Card.objects.create(
            tenant=self.tenant,
            name="Gemini Flash",
            provider="google_gemini",
            event_type="llm_call",
            dimensions={"model": "gemini-2.0-flash"},
        )
        Rate.objects.create(
            card=self.card,
            metric_name="input_tokens",
            cost_per_unit_micros=75_000,
            unit_quantity=1_000_000,
        )
        Rate.objects.create(
            card=self.card,
            metric_name="output_tokens",
            cost_per_unit_micros=300_000,
            unit_quantity=1_000_000,
        )
        # Global default margin
        TenantMarkup.objects.create(
            tenant=self.tenant, margin_pct=40,
        )

    def test_price_event_with_card(self):
        provider_cost, billed_cost, prov = PricingService.price_event(
            tenant=self.tenant,
            event_type="llm_call",
            provider="google_gemini",
            usage_metrics={"input_tokens": 1_000_000, "output_tokens": 500_000},
            properties={"model": "gemini-2.0-flash"},
        )
        # input: 75000, output: (500000 * 300000 + 500000) // 1000000 = 150000
        self.assertEqual(provider_cost, 75_000 + 150_000)
        # 40% margin: 225000 / (1 - 0.40) = 375000
        self.assertEqual(billed_cost, 375_000)

    def test_no_card_raises_pricing_error(self):
        with self.assertRaises(PricingError):
            PricingService.price_event(
                tenant=self.tenant,
                event_type="unknown",
                provider="unknown",
                usage_metrics={"tokens": 100},
            )


class MarginResolutionTest(TestCase):
    """Test margin resolution with Group overrides."""

    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Test", stripe_connected_account_id="acct_test"
        )
        self.card = Card.objects.create(
            tenant=self.tenant,
            name="Test Card",
            provider="test_provider",
            event_type="test_event",
            dimensions={},
        )
        Rate.objects.create(
            card=self.card,
            metric_name="requests",
            cost_per_unit_micros=1_000_000,
            unit_quantity=1,
        )
        # Global default: 30% margin
        TenantMarkup.objects.create(
            tenant=self.tenant, margin_pct=30,
        )

    def test_default_margin_when_no_group(self):
        _, billed, _ = PricingService.price_event(
            tenant=self.tenant,
            event_type="test_event",
            provider="test_provider",
            usage_metrics={"requests": 1},
        )
        # $1.00 / (1 - 0.30) = $1.428571... rounds to 1_428_571
        expected = int(Decimal("1000000") / Decimal("0.70"))
        self.assertEqual(billed, expected)

    def test_group_margin_overrides_default(self):
        Group.objects.create(
            tenant=self.tenant,
            name="Premium",
            slug="premium",
            margin_pct=60,
        )
        _, billed, _ = PricingService.price_event(
            tenant=self.tenant,
            event_type="test_event",
            provider="test_provider",
            usage_metrics={"requests": 1},
            group="premium",
        )
        # $1.00 / (1 - 0.60) = $2.50
        self.assertEqual(billed, 2_500_000)

    def test_group_null_margin_inherits_default(self):
        Group.objects.create(
            tenant=self.tenant,
            name="Basic",
            slug="basic",
            margin_pct=None,
        )
        _, billed, _ = PricingService.price_event(
            tenant=self.tenant,
            event_type="test_event",
            provider="test_provider",
            usage_metrics={"requests": 1},
            group="basic",
        )
        # Falls back to default 30%
        expected = int(Decimal("1000000") / Decimal("0.70"))
        self.assertEqual(billed, expected)

    def test_card_level_markup_takes_precedence_over_group(self):
        Group.objects.create(
            tenant=self.tenant,
            name="Premium",
            slug="premium",
            margin_pct=60,
        )
        # Card-level TenantMarkup (event_type + provider match)
        TenantMarkup.objects.create(
            tenant=self.tenant,
            event_type="test_event",
            provider="test_provider",
            margin_pct=80,
        )
        _, billed, _ = PricingService.price_event(
            tenant=self.tenant,
            event_type="test_event",
            provider="test_provider",
            usage_metrics={"requests": 1},
            group="premium",
        )
        # Card-level 80% takes precedence: $1.00 / 0.20 = $5.00
        self.assertEqual(billed, 5_000_000)

    def test_unmatched_group_slug_uses_default(self):
        _, billed, _ = PricingService.price_event(
            tenant=self.tenant,
            event_type="test_event",
            provider="test_provider",
            usage_metrics={"requests": 1},
            group="nonexistent_group",
        )
        # No matching group, falls back to default 30%
        expected = int(Decimal("1000000") / Decimal("0.70"))
        self.assertEqual(billed, expected)

    def test_zero_margin_passthrough(self):
        TenantMarkup.objects.all().delete()
        TenantMarkup.objects.create(
            tenant=self.tenant, margin_pct=0,
        )
        _, billed, _ = PricingService.price_event(
            tenant=self.tenant,
            event_type="test_event",
            provider="test_provider",
            usage_metrics={"requests": 1},
        )
        # 0% margin = pass-through: billed = provider cost
        self.assertEqual(billed, 1_000_000)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/metering/pricing/tests/test_pricing_service_v2.py -v`

Expected: FAIL — PricingService still uses ProviderRate and old markup logic.

- [ ] **Step 3: Update PricingService**

Rewrite `apps/metering/pricing/services/pricing_service.py`:

```python
"""Pricing service: Card/Rate lookup, dimension matching, margin resolution."""

import logging
from decimal import Decimal
from typing import Dict, Optional, Tuple

from django.db.models import Q
from django.utils import timezone

from apps.metering.pricing.models import Card, Rate, TenantMarkup

logger = logging.getLogger(__name__)

PRICING_ENGINE_VERSION = "2.0.0"


class PricingError(Exception):
    pass


class PricingService:
    """
    Calculates dual costs (provider COGS + billed revenue) from raw usage metrics.

    Pipeline:
      1. Find matching Card (dimension match, most-specific wins)
      2. For each metric: find Rate in Card, calculate cost
      3. Resolve margin: card-level TenantMarkup → Group → parent chain → default TenantMarkup
      4. Apply margin → billed_cost_micros
    """

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
    def price_event(
        tenant,
        event_type: str,
        provider: str,
        usage_metrics: Dict[str, int],
        properties: Dict = None,
        group: str = None,
        as_of=None,
    ) -> Tuple[int, int, Dict]:
        """
        Price a usage event.

        Args:
            tenant: Tenant instance
            event_type: e.g. "llm_call"
            provider: e.g. "google_gemini"
            usage_metrics: e.g. {"input_tokens": 1500}
            properties: dimension values for Card matching
            group: billing group slug for margin resolution
            as_of: pricing effective timestamp (default: now)

        Returns:
            (provider_cost_micros, billed_cost_micros, provenance)
        """
        as_of = as_of or timezone.now()
        properties = properties or {}

        if not usage_metrics:
            return 0, 0, {"engine_version": PRICING_ENGINE_VERSION, "metrics": {}}

        PricingService.validate_usage_metrics(usage_metrics)

        # Find the matching Card
        card = PricingService._find_card(tenant, provider, event_type, properties, as_of)
        if card is None:
            raise PricingError(
                f"No pricing card found: {provider}/{event_type} "
                f"properties={properties}"
            )

        # Calculate provider cost from Card's Rates
        total_provider_cost = 0
        provenance_metrics = {}

        for metric_name, units in usage_metrics.items():
            rate = PricingService._find_rate(card, metric_name, as_of)
            if rate is None:
                raise PricingError(
                    f"No rate found for metric '{metric_name}' in card '{card.name}'"
                )
            metric_cost = rate.calculate_cost_micros(units)
            total_provider_cost += metric_cost

            provenance_metrics[metric_name] = {
                "rate_id": str(rate.id),
                "card_id": str(card.id),
                "units": units,
                "cost_per_unit_micros": rate.cost_per_unit_micros,
                "unit_quantity": rate.unit_quantity,
                "cost_micros": metric_cost,
            }

        # Resolve and apply margin
        margin_pct, margin_source = PricingService._resolve_margin(
            tenant, event_type, provider, group, as_of,
        )
        billed_cost = PricingService._apply_margin(total_provider_cost, margin_pct)

        provenance = {
            "engine_version": PRICING_ENGINE_VERSION,
            "calculated_at": as_of.isoformat(),
            "card_id": str(card.id),
            "card_name": card.name,
            "metrics": provenance_metrics,
            "margin": {
                "margin_pct": float(margin_pct),
                "source": margin_source,
            },
            "provider_cost_micros": total_provider_cost,
            "billed_cost_micros": billed_cost,
        }

        return total_provider_cost, billed_cost, provenance

    @staticmethod
    def _find_card(
        tenant, provider: str, event_type: str, properties: Dict, as_of,
    ) -> Optional[Card]:
        """Find best matching Card using dimension matching."""
        cards = Card.objects.filter(
            tenant=tenant,
            provider=provider,
            event_type=event_type,
            status="active",
        )

        matched = []
        for card in cards:
            if PricingService._dimensions_match(card.dimensions, properties):
                matched.append(card)

        if not matched:
            return None

        # Most specific (most dimension keys) wins
        matched.sort(
            key=lambda c: len(c.dimensions) if c.dimensions else 0,
            reverse=True,
        )
        return matched[0]

    @staticmethod
    def _find_rate(card: Card, metric_name: str, as_of) -> Optional[Rate]:
        """Find active Rate within a Card for a metric."""
        return card.rates.filter(
            metric_name=metric_name,
            valid_from__lte=as_of,
        ).filter(
            Q(valid_to__isnull=True) | Q(valid_to__gt=as_of)
        ).order_by("-valid_from").first()

    @staticmethod
    def _dimensions_match(card_dimensions: Dict, event_properties: Dict) -> bool:
        """All card dimension key-values must exist in event properties."""
        if not card_dimensions:
            return True
        return all(
            event_properties.get(k) == v for k, v in card_dimensions.items()
        )

    @staticmethod
    def _resolve_margin(
        tenant, event_type: str, provider: str, group: str = None, as_of=None,
    ) -> Tuple[Decimal, str]:
        """
        Resolve margin with precedence:
          1. TenantMarkup (event_type + provider) — card-level
          2. Group.margin_pct — group-level override
          3. Walk Group.parent chain
          4. TenantMarkup (event_type only)
          5. TenantMarkup (global)
          6. Default: 0 (pass-through)
        """
        as_of = as_of or timezone.now()
        base = TenantMarkup.objects.filter(
            tenant=tenant,
            valid_from__lte=as_of,
        ).filter(Q(valid_to__isnull=True) | Q(valid_to__gt=as_of))

        # 1. Card-level TenantMarkup
        card_markup = base.filter(
            event_type=event_type, provider=provider,
        ).order_by("-valid_from").first()
        if card_markup:
            return card_markup.margin_pct, f"tenant_markup:{card_markup.id}"

        # 2-3. Group margin (walk parent chain)
        if group:
            from apps.platform.groups.models import Group as GroupModel
            try:
                grp = GroupModel.objects.get(
                    tenant=tenant, slug=group, status="active",
                )
                # Walk up the parent chain
                current = grp
                while current is not None:
                    if current.margin_pct is not None:
                        return current.margin_pct, f"group:{current.id}"
                    current = current.parent
            except GroupModel.DoesNotExist:
                pass  # Unmatched group slug, fall through

        # 4. Event-type TenantMarkup
        et_markup = base.filter(
            event_type=event_type, provider="",
        ).order_by("-valid_from").first()
        if et_markup:
            return et_markup.margin_pct, f"tenant_markup:{et_markup.id}"

        # 5. Global TenantMarkup
        global_markup = base.filter(
            event_type="", provider="",
        ).order_by("-valid_from").first()
        if global_markup:
            return global_markup.margin_pct, f"tenant_markup:{global_markup.id}"

        # 6. No margin configured
        return Decimal("0"), "default:passthrough"

    @staticmethod
    def _apply_margin(provider_cost_micros: int, margin_pct: Decimal) -> int:
        """Apply margin: billed = provider_cost / (1 - margin_pct/100)."""
        if margin_pct <= 0:
            return provider_cost_micros
        divisor = Decimal("1") - (margin_pct / Decimal("100"))
        return int(
            (Decimal(provider_cost_micros) / divisor).quantize(Decimal("1"))
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/metering/pricing/tests/test_pricing_service_v2.py -v`

Expected: All 8 tests PASS.

- [ ] **Step 5: Update old pricing service tests**

Update `apps/metering/pricing/tests/test_pricing_service.py` to use Card + Rate instead of ProviderRate, and margin instead of markup. Key changes:
- Create Card + Rate instead of ProviderRate in setUp
- Update expected values for margin math instead of markup math
- Update provenance assertions

- [ ] **Step 6: Run full test suite**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/metering/pricing/tests/ -v`

Expected: All tests PASS.

- [ ] **Step 7: Commit**

```bash
git add apps/metering/pricing/
git commit -m "feat: update PricingService for Card/Rate lookup and Group margin resolution"
```

---

## Task 7: Wire group Through UsageService → PricingService

**Files:**
- Modify: `apps/metering/usage/services/usage_service.py`

- [ ] **Step 1: Write test for group passed to PricingService**

Add to `apps/metering/usage/tests/test_group.py`:
```python
class GroupPricingIntegrationTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Test", stripe_connected_account_id="acct_test",
            products=["metering", "billing"],
        )
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="c1"
        )
        from apps.metering.pricing.models import Card, Rate, TenantMarkup
        card = Card.objects.create(
            tenant=self.tenant,
            name="Test Card",
            provider="test_provider",
            event_type="test_event",
            dimensions={},
        )
        Rate.objects.create(
            card=card,
            metric_name="requests",
            cost_per_unit_micros=1_000_000,
            unit_quantity=1,
        )
        TenantMarkup.objects.create(tenant=self.tenant, margin_pct=30)
        from apps.platform.groups.models import Group
        Group.objects.create(
            tenant=self.tenant, name="Premium", slug="premium", margin_pct=60,
        )

    @patch("apps.platform.events.tasks.process_single_event")
    def test_group_affects_billed_cost(self, mock_process):
        result = UsageService.record_usage(
            tenant=self.tenant,
            customer=self.customer,
            request_id="req_gp1",
            idempotency_key="idem_gp1",
            event_type="test_event",
            provider="test_provider",
            usage_metrics={"requests": 1},
            group="premium",
        )
        # 60% margin: $1.00 / 0.40 = $2.50
        self.assertEqual(result["billed_cost_micros"], 2_500_000)
        self.assertEqual(result["provider_cost_micros"], 1_000_000)

    @patch("apps.platform.events.tasks.process_single_event")
    def test_no_group_uses_default_margin(self, mock_process):
        result = UsageService.record_usage(
            tenant=self.tenant,
            customer=self.customer,
            request_id="req_gp2",
            idempotency_key="idem_gp2",
            event_type="test_event",
            provider="test_provider",
            usage_metrics={"requests": 1},
        )
        # 30% default: $1.00 / 0.70 = ~$1.428571
        from decimal import Decimal
        expected = int(Decimal("1000000") / Decimal("0.70"))
        self.assertEqual(result["billed_cost_micros"], expected)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/metering/usage/tests/test_group.py::GroupPricingIntegrationTest -v`

Expected: FAIL — UsageService doesn't pass `group` to PricingService.

- [ ] **Step 3: Update UsageService to pass group to PricingService**

In `apps/metering/usage/services/usage_service.py`, update the PricingService call (around line 79):

```python
provider_cost_micros, billed_cost_micros, pricing_provenance = (
    PricingService.price_event(
        tenant=tenant,
        event_type=event_type,
        provider=provider,
        usage_metrics=usage_metrics,
        properties=properties,
        group=group,
    )
)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/metering/usage/tests/test_group.py -v`

Expected: All 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/metering/usage/
git commit -m "feat: wire group through UsageService to PricingService"
```

---

## Task 8: Group CRUD API Endpoints

**Files:**
- Create: `api/v1/group_endpoints.py`
- Create: `apps/platform/groups/tests/test_api.py`
- Modify: `api/v1/schemas.py`
- Modify: `config/urls.py`

- [ ] **Step 1: Add Group schemas**

In `api/v1/schemas.py`, add:
```python
class CreateGroupRequest(Schema):
    name: str = Field(min_length=1, max_length=255)
    slug: str = Field(min_length=2, max_length=255, pattern=r"^[a-z][a-z0-9_]*$")
    description: str = ""
    margin_pct: Optional[float] = None
    parent_id: Optional[str] = None

class UpdateGroupRequest(Schema):
    name: Optional[str] = None
    description: Optional[str] = None
    margin_pct: Optional[float] = Field(default=None, ge=0, lt=100)
    status: Optional[str] = None

class GroupResponse(Schema):
    id: str
    name: str
    slug: str
    description: str
    margin_pct: Optional[float]
    status: str
    parent_id: Optional[str]
    created_at: str
    updated_at: str

class GroupListResponse(Schema):
    data: list[GroupResponse]
    next_cursor: Optional[str] = None
    has_more: bool
```

- [ ] **Step 2: Write failing endpoint tests**

Create `apps/platform/groups/tests/test_api.py`:
```python
import json
from django.test import TestCase, Client
from apps.platform.tenants.models import Tenant, TenantApiKey
from apps.platform.groups.models import Group


class GroupEndpointTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.tenant = Tenant.objects.create(
            name="Test", products=["metering", "billing"]
        )
        self.key_obj, self.raw_key = TenantApiKey.create_key(self.tenant, label="test")

    def test_create_group(self):
        response = self.client.post(
            "/api/v1/platform/groups",
            data=json.dumps({
                "name": "Property Search",
                "slug": "property_search",
                "margin_pct": 65.0,
            }),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["name"], "Property Search")
        self.assertEqual(body["slug"], "property_search")
        self.assertEqual(body["margin_pct"], 65.0)

    def test_list_groups(self):
        Group.objects.create(tenant=self.tenant, name="G1", slug="g1")
        Group.objects.create(tenant=self.tenant, name="G2", slug="g2")
        response = self.client.get(
            "/api/v1/platform/groups",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["data"]), 2)

    def test_get_group(self):
        g = Group.objects.create(tenant=self.tenant, name="G1", slug="g1", margin_pct=50)
        response = self.client.get(
            f"/api/v1/platform/groups/{g.id}",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["slug"], "g1")

    def test_update_group(self):
        g = Group.objects.create(tenant=self.tenant, name="G1", slug="g1", margin_pct=50)
        response = self.client.patch(
            f"/api/v1/platform/groups/{g.id}",
            data=json.dumps({"margin_pct": 70.0}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["margin_pct"], 70.0)

    def test_delete_group_archives(self):
        g = Group.objects.create(tenant=self.tenant, name="G1", slug="g1")
        response = self.client.delete(
            f"/api/v1/platform/groups/{g.id}",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        self.assertEqual(response.status_code, 200)
        g.refresh_from_db()
        self.assertEqual(g.status, "archived")
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/platform/groups/tests/test_api.py -v`

Expected: 404 errors — endpoints not registered yet.

- [ ] **Step 4: Implement Group endpoints**

Create `api/v1/group_endpoints.py`:
```python
from uuid import UUID
from django.shortcuts import get_object_or_404
from ninja import NinjaAPI

from core.auth import ApiKeyAuth
from api.v1.schemas import (
    CreateGroupRequest, UpdateGroupRequest,
    GroupResponse, GroupListResponse,
)
from api.v1.pagination import encode_cursor, apply_cursor_filter
from apps.platform.groups.models import Group

group_api = NinjaAPI(auth=ApiKeyAuth(), urls_namespace="ubb_groups_v1")


def _group_to_response(g):
    return {
        "id": str(g.id),
        "name": g.name,
        "slug": g.slug,
        "description": g.description,
        "margin_pct": float(g.margin_pct) if g.margin_pct is not None else None,
        "status": g.status,
        "parent_id": str(g.parent_id) if g.parent_id else None,
        "created_at": g.created_at.isoformat(),
        "updated_at": g.updated_at.isoformat(),
    }


@group_api.post("/groups", response={201: GroupResponse})
def create_group(request, payload: CreateGroupRequest):
    tenant = request.auth.tenant
    parent = None
    if payload.parent_id:
        parent = get_object_or_404(Group, id=payload.parent_id, tenant=tenant)

    from decimal import Decimal
    group = Group.objects.create(
        tenant=tenant,
        name=payload.name,
        slug=payload.slug,
        description=payload.description,
        margin_pct=Decimal(str(payload.margin_pct)) if payload.margin_pct is not None else None,
        parent=parent,
    )
    return 201, _group_to_response(group)


@group_api.get("/groups", response=GroupListResponse)
def list_groups(request, status: str = None, cursor: str = None, limit: int = 50):
    tenant = request.auth.tenant
    limit = min(max(limit, 1), 100)

    qs = Group.objects.filter(tenant=tenant).order_by("-created_at", "-id")
    if status:
        qs = qs.filter(status=status)

    if cursor:
        try:
            qs = apply_cursor_filter(qs, cursor)
        except ValueError:
            from ninja.errors import HttpError
            raise HttpError(400, "Invalid cursor")

    groups = list(qs[:limit + 1])
    has_more = len(groups) > limit
    groups = groups[:limit]

    next_cursor = None
    if has_more and groups:
        last = groups[-1]
        next_cursor = encode_cursor(last.created_at, last.id)

    return {
        "data": [_group_to_response(g) for g in groups],
        "next_cursor": next_cursor,
        "has_more": has_more,
    }


@group_api.get("/groups/{group_id}", response=GroupResponse)
def get_group(request, group_id: UUID):
    group = get_object_or_404(Group, id=group_id, tenant=request.auth.tenant)
    return _group_to_response(group)


@group_api.patch("/groups/{group_id}", response=GroupResponse)
def update_group(request, group_id: UUID, payload: UpdateGroupRequest):
    group = get_object_or_404(Group, id=group_id, tenant=request.auth.tenant)
    update_fields = ["updated_at"]

    if payload.name is not None:
        group.name = payload.name
        update_fields.append("name")
    if payload.description is not None:
        group.description = payload.description
        update_fields.append("description")
    if payload.margin_pct is not None:
        from decimal import Decimal
        group.margin_pct = Decimal(str(payload.margin_pct))
        update_fields.append("margin_pct")
    if payload.status is not None:
        group.status = payload.status
        update_fields.append("status")

    group.save(update_fields=update_fields)
    return _group_to_response(group)


@group_api.delete("/groups/{group_id}")
def delete_group(request, group_id: UUID):
    group = get_object_or_404(Group, id=group_id, tenant=request.auth.tenant)
    group.status = "archived"
    group.save(update_fields=["status", "updated_at"])
    return {"status": "archived"}
```

- [ ] **Step 5: Register URL pattern**

In `config/urls.py`, add import and URL pattern:

```python
from api.v1.group_endpoints import group_api
```

Add to urlpatterns (before the generic `api/v1/` catch-all):
```python
path("api/v1/platform/", group_api.urls),
```

Note: since `platform_api` already handles `/api/v1/platform/`, merge the group endpoints into `platform_api` in `api/v1/platform_endpoints.py` instead if there's a conflict. Alternatively, mount at a non-conflicting subpath. Check how `platform_api` is mounted and either add group endpoints to it, or mount group_api at a different prefix like `path("api/v1/groups/", group_api.urls)`.

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/platform/groups/tests/test_api.py -v`

Expected: All 5 tests PASS.

- [ ] **Step 7: Commit**

```bash
git add api/v1/group_endpoints.py api/v1/schemas.py config/urls.py apps/platform/groups/tests/
git commit -m "feat: add Group CRUD API endpoints"
```

---

## Task 9: Card + Rate CRUD API Endpoints

**Files:**
- Modify: `api/v1/metering_endpoints.py`
- Modify: `api/v1/schemas.py`

- [ ] **Step 1: Add Card + Rate schemas**

In `api/v1/schemas.py`, add:
```python
class RateIn(Schema):
    metric_name: str = Field(min_length=1, max_length=100)
    cost_per_unit_micros: int = Field(ge=0)
    unit_quantity: int = Field(gt=0, default=1_000_000)
    currency: str = Field(default="USD", max_length=3)

class CreateCardRequest(Schema):
    name: str = Field(min_length=1, max_length=255)
    provider: str = Field(min_length=1, max_length=100)
    event_type: str = Field(min_length=1, max_length=100)
    dimensions: dict = Field(default_factory=dict)
    description: str = ""
    rates: list[RateIn] = Field(default_factory=list)

class RateOut(Schema):
    id: str
    metric_name: str
    cost_per_unit_micros: int
    unit_quantity: int
    currency: str
    valid_from: str
    valid_to: Optional[str] = None

class CardOut(Schema):
    id: str
    name: str
    provider: str
    event_type: str
    dimensions: dict
    description: str
    status: str
    rates: list[RateOut]
    created_at: str

class CardListResponse(Schema):
    data: list[CardOut]
    next_cursor: Optional[str] = None
    has_more: bool
```

- [ ] **Step 2: Implement Card CRUD endpoints**

In `api/v1/metering_endpoints.py`, add card endpoints (after the existing run endpoints, replacing the old standalone rate endpoints):

```python
from apps.metering.pricing.models import Card, Rate


def _card_to_out(card):
    rates = card.rates.filter(valid_to__isnull=True).order_by("metric_name")
    return {
        "id": str(card.id),
        "name": card.name,
        "provider": card.provider,
        "event_type": card.event_type,
        "dimensions": card.dimensions,
        "description": card.description,
        "status": card.status,
        "rates": [
            {
                "id": str(r.id),
                "metric_name": r.metric_name,
                "cost_per_unit_micros": r.cost_per_unit_micros,
                "unit_quantity": r.unit_quantity,
                "currency": r.currency,
                "valid_from": r.valid_from.isoformat(),
                "valid_to": r.valid_to.isoformat() if r.valid_to else None,
            }
            for r in rates
        ],
        "created_at": card.created_at.isoformat(),
    }


@metering_api.post("/pricing/cards", response={201: CardOut})
def create_card(request, payload: CreateCardRequest):
    _product_check(request)
    card = Card.objects.create(
        tenant=request.auth.tenant,
        name=payload.name,
        provider=payload.provider,
        event_type=payload.event_type,
        dimensions=payload.dimensions,
        description=payload.description,
    )
    for rate_in in payload.rates:
        Rate.objects.create(
            card=card,
            metric_name=rate_in.metric_name,
            cost_per_unit_micros=rate_in.cost_per_unit_micros,
            unit_quantity=rate_in.unit_quantity,
            currency=rate_in.currency,
        )
    return 201, _card_to_out(card)


@metering_api.get("/pricing/cards", response=CardListResponse)
def list_cards(request, cursor: str = None, limit: int = 50):
    _product_check(request)
    limit = min(max(limit, 1), 100)
    qs = Card.objects.filter(
        tenant=request.auth.tenant, status="active",
    ).order_by("-created_at", "-id")

    if cursor:
        try:
            qs = apply_cursor_filter(qs, cursor)
        except ValueError:
            from ninja.errors import HttpError
            raise HttpError(400, "Invalid cursor")

    cards = list(qs[:limit + 1])
    has_more = len(cards) > limit
    cards = cards[:limit]
    next_cursor = None
    if has_more and cards:
        last = cards[-1]
        next_cursor = encode_cursor(last.created_at, last.id)

    return {
        "data": [_card_to_out(c) for c in cards],
        "next_cursor": next_cursor,
        "has_more": has_more,
    }


@metering_api.get("/pricing/cards/{card_id}", response=CardOut)
def get_card(request, card_id: UUID):
    _product_check(request)
    card = get_object_or_404(Card, id=card_id, tenant=request.auth.tenant)
    return _card_to_out(card)


@metering_api.patch("/pricing/cards/{card_id}", response=CardOut)
def update_card(request, card_id: UUID, payload: dict):
    _product_check(request)
    card = get_object_or_404(Card, id=card_id, tenant=request.auth.tenant)
    update_fields = ["updated_at"]
    for field in ("name", "description"):
        if field in payload:
            setattr(card, field, payload[field])
            update_fields.append(field)
    if "status" in payload:
        card.status = payload["status"]
        update_fields.append("status")
    card.save(update_fields=update_fields)
    return _card_to_out(card)


@metering_api.delete("/pricing/cards/{card_id}")
def delete_card(request, card_id: UUID):
    _product_check(request)
    card = get_object_or_404(Card, id=card_id, tenant=request.auth.tenant)
    card.status = "archived"
    card.save(update_fields=["status", "updated_at"])
    return {"status": "archived"}


@metering_api.post("/pricing/cards/{card_id}/rates", response={201: RateOut})
def add_rate(request, card_id: UUID, payload: RateIn):
    _product_check(request)
    card = get_object_or_404(Card, id=card_id, tenant=request.auth.tenant)
    rate = Rate.objects.create(
        card=card,
        metric_name=payload.metric_name,
        cost_per_unit_micros=payload.cost_per_unit_micros,
        unit_quantity=payload.unit_quantity,
        currency=payload.currency,
    )
    return 201, {
        "id": str(rate.id),
        "metric_name": rate.metric_name,
        "cost_per_unit_micros": rate.cost_per_unit_micros,
        "unit_quantity": rate.unit_quantity,
        "currency": rate.currency,
        "valid_from": rate.valid_from.isoformat(),
        "valid_to": None,
    }


@metering_api.put("/pricing/cards/{card_id}/rates/{rate_id}", response=RateOut)
def update_rate_in_card(request, card_id: UUID, rate_id: UUID, payload: RateIn):
    """Soft-expire old rate and create new version."""
    _product_check(request)
    card = get_object_or_404(Card, id=card_id, tenant=request.auth.tenant)
    old_rate = get_object_or_404(Rate, id=rate_id, card=card, valid_to__isnull=True)

    now = timezone.now()
    old_rate.valid_to = now
    old_rate.save(update_fields=["valid_to", "updated_at"])

    new_rate = Rate.objects.create(
        card=card,
        metric_name=payload.metric_name,
        cost_per_unit_micros=payload.cost_per_unit_micros,
        unit_quantity=payload.unit_quantity,
        currency=payload.currency,
    )
    return {
        "id": str(new_rate.id),
        "metric_name": new_rate.metric_name,
        "cost_per_unit_micros": new_rate.cost_per_unit_micros,
        "unit_quantity": new_rate.unit_quantity,
        "currency": new_rate.currency,
        "valid_from": new_rate.valid_from.isoformat(),
        "valid_to": None,
    }


@metering_api.delete("/pricing/cards/{card_id}/rates/{rate_id}")
def delete_rate_in_card(request, card_id: UUID, rate_id: UUID):
    _product_check(request)
    card = get_object_or_404(Card, id=card_id, tenant=request.auth.tenant)
    rate = get_object_or_404(Rate, id=rate_id, card=card, valid_to__isnull=True)
    rate.valid_to = timezone.now()
    rate.save(update_fields=["valid_to", "updated_at"])
    return {"status": "deleted"}
```

- [ ] **Step 3: Run full test suite**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest --tb=short -q`

Expected: All tests PASS.

- [ ] **Step 4: Commit**

```bash
git add api/v1/metering_endpoints.py api/v1/schemas.py
git commit -m "feat: add Card + Rate CRUD API endpoints"
```

---

## Task 10: Update Usage Recording Endpoint

**Files:**
- Modify: `api/v1/schemas.py`
- Modify: `api/v1/metering_endpoints.py`

- [ ] **Step 1: Update RecordUsageRequest schema**

In `api/v1/schemas.py`, update `RecordUsageRequest`:

Remove: `group_keys: Optional[dict[str, str]] = None`
Add: `group: Optional[str] = Field(default=None, max_length=255)`

- [ ] **Step 2: Update record_usage endpoint**

In `api/v1/metering_endpoints.py`, update the `record_usage` function to pass `group` instead of `group_keys`:

```python
result = UsageService.record_usage(
    tenant=request.auth.tenant,
    customer=customer,
    request_id=payload.request_id,
    idempotency_key=payload.idempotency_key,
    event_type=payload.event_type,
    provider=payload.provider,
    usage_metrics=payload.usage_metrics,
    group=payload.group,
    run_id=payload.run_id,
)
```

- [ ] **Step 3: Update get_usage endpoint**

In `api/v1/metering_endpoints.py`, update the `get_usage` function. Replace group_key/group_value filtering:

Change parameters from `group_key: str = None, group_value: str = None` to `group: str = None`.

Change filter from:
```python
if group_key and group_value:
    qs = qs.filter(group_keys__contains={group_key: group_value})
```

To:
```python
if group:
    qs = qs.filter(group=group)
```

- [ ] **Step 4: Update markup endpoints to use margin_pct**

In `api/v1/metering_endpoints.py`, update `_markup_to_out`:
```python
def _markup_to_out(markup):
    return {
        "id": markup.id,
        "event_type": markup.event_type,
        "provider": markup.provider,
        "margin_pct": float(markup.margin_pct),
        "valid_from": markup.valid_from.isoformat(),
        "valid_to": markup.valid_to.isoformat() if markup.valid_to else None,
    }
```

Update `TenantMarkupIn` and `TenantMarkupOut` in `api/v1/schemas.py`:
- Remove `markup_percentage_micros` and `fixed_uplift_micros`
- Add `margin_pct: float = Field(ge=0, lt=100, default=0)`

Update `create_markup` and `update_markup` endpoints to use `margin_pct` instead of `markup_percentage_micros` and `fixed_uplift_micros`.

- [ ] **Step 5: Run full test suite to check for breakage**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest --tb=short -q`

Fix any failing tests that reference old field names (`group_keys`, `markup_percentage_micros`, `fixed_uplift_micros`).

- [ ] **Step 6: Commit**

```bash
git add api/v1/schemas.py api/v1/metering_endpoints.py
git commit -m "feat: update usage and markup endpoints for group + margin_pct"
```

---

## Task 11: SDK Updates

**Files:**
- Modify: `ubb-sdk/ubb/metering.py`

- [ ] **Step 1: Update MeteringClient.record_usage**

In `ubb-sdk/ubb/metering.py`, update `record_usage` method:

Replace `group_keys: dict | None = None` parameter with `group: str | None = None`.

Update body construction:
```python
if group is not None:
    body["group"] = group
```

Remove the old `group_keys` body line.

- [ ] **Step 2: Update get_usage if it uses group_key/group_value**

Check if `get_usage` in the SDK passes `group_key` and `group_value` query params. Update to pass `group` instead.

- [ ] **Step 3: Run SDK tests**

Run: `cd ubb-sdk && python -m pytest --tb=short -q`

Fix any tests that reference `group_keys`. Update to `group`.

- [ ] **Step 4: Commit**

```bash
git add ubb-sdk/
git commit -m "feat: update SDK for group parameter (replaces group_keys)"
```

---

## Task 12: Data Migration + Cleanup

**Files:**
- Modify: `apps/metering/pricing/models.py` (remove ProviderRate)
- Modify: Various test files

- [ ] **Step 1: Write data migration to convert ProviderRates → Cards + Rates**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python manage.py makemigrations pricing --empty -n migrate_providerrate_to_card_rate`

Edit the generated migration:
```python
from django.db import migrations


def forward(apps, schema_editor):
    ProviderRate = apps.get_model("pricing", "ProviderRate")
    Card = apps.get_model("pricing", "Card")
    Rate = apps.get_model("pricing", "Rate")

    # Group existing rates by (tenant, provider, event_type, dimensions_hash)
    seen_cards = {}  # (tenant_id, provider, event_type, dimensions_hash) → Card

    for pr in ProviderRate.objects.all():
        key = (str(pr.tenant_id), pr.provider, pr.event_type, pr.dimensions_hash)
        if key not in seen_cards:
            # Derive card name from provider + first dimension value
            dim_label = ""
            if pr.dimensions:
                first_val = next(iter(pr.dimensions.values()), "")
                dim_label = f" ({first_val})" if first_val else ""
            card_name = f"{pr.provider}{dim_label}"

            card = Card.objects.create(
                id=None,  # auto-generate UUID
                tenant_id=pr.tenant_id,
                name=card_name,
                provider=pr.provider,
                event_type=pr.event_type,
                dimensions=pr.dimensions,
                dimensions_hash=pr.dimensions_hash,
                status="active" if pr.valid_to is None else "archived",
            )
            seen_cards[key] = card

        card = seen_cards[key]
        Rate.objects.create(
            card=card,
            metric_name=pr.metric_name,
            cost_per_unit_micros=pr.cost_per_unit_micros,
            unit_quantity=pr.unit_quantity,
            currency=pr.currency,
            valid_from=pr.valid_from,
            valid_to=pr.valid_to,
        )


def reverse(apps, schema_editor):
    # Reverse is lossy but safe for pre-production
    apps.get_model("pricing", "Rate").objects.all().delete()
    apps.get_model("pricing", "Card").objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [
        ("pricing", "NNNN_previous"),  # Replace with the actual previous migration name from ls apps/metering/pricing/migrations/
    ]
    operations = [
        migrations.RunPython(forward, reverse),
    ]
```

- [ ] **Step 2: Run migration**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python manage.py migrate`

- [ ] **Step 3: Remove ProviderRate model**

In `apps/metering/pricing/models.py`, delete the `ProviderRate` class entirely.

Create a migration to remove the table:
Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python manage.py makemigrations pricing`

- [ ] **Step 4: Remove ProviderRate admin**

In `apps/metering/pricing/admin.py`, remove the `ProviderRateAdmin` registration. Keep `CardAdmin`, `RateAdmin`, and `TenantMarkupAdmin`.

- [ ] **Step 5: Clean up old rate endpoints**

In `api/v1/metering_endpoints.py`:
- Remove `_rate_to_out`, `list_rates`, `create_rate`, `update_rate`, `delete_rate` functions (the standalone rate endpoints)
- Remove ProviderRate imports
- Keep markup endpoints (updated for margin_pct)

In `api/v1/schemas.py`:
- Remove `ProviderRateIn`, `ProviderRateOut`

- [ ] **Step 6: Remove group_keys GIN index migration**

Check `apps/metering/usage/migrations/` for the GIN index migration (`0011_usage_event_group_keys_gin_index.py`). If the `group_keys` column was removed in Task 4, Django should handle this. If not, create a migration to drop the index and column.

- [ ] **Step 7: Clean up remaining references**

Search the codebase for any remaining references to:
- `group_keys` (should be `group`)
- `ProviderRate` (should be `Card` + `Rate`)
- `markup_percentage_micros` (should be `margin_pct`)
- `fixed_uplift_micros` (removed)
- `calculate_markup_micros` (should be `apply_margin`)

Update or remove each reference.

- [ ] **Step 8: Run full test suite**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest --tb=short -q`

Fix any remaining failures.

- [ ] **Step 9: Run SDK tests**

Run: `cd ubb-sdk && python -m pytest --tb=short -q`

Expected: All tests PASS.

- [ ] **Step 10: Run migrations check**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python manage.py migrate`

Expected: No pending migrations.

- [ ] **Step 11: Final commit**

```bash
git add -A
git commit -m "feat: remove ProviderRate, clean up group_keys and markup references"
```

---

## Verification Checklist

After all tasks are complete, verify:

- [ ] `Group` model exists in `apps/platform/groups/` with parent FK, margin_pct, slug
- [ ] `Card` model exists in `apps/metering/pricing/` with no Group FK, no margin fields
- [ ] `Rate` model exists in `apps/metering/pricing/` as child of Card
- [ ] `ProviderRate` model is fully removed
- [ ] `TenantMarkup` uses `margin_pct` (not markup_percentage_micros)
- [ ] `UsageEvent` has `group` CharField (not group_keys JSONField)
- [ ] `Tenant` has `group_label` field
- [ ] `PricingService.price_event()` accepts `group` parameter
- [ ] Margin resolution follows the chain: Card TenantMarkup → Group → parent chain → default TenantMarkup
- [ ] Group CRUD API endpoints work at `/api/v1/platform/groups`
- [ ] SDK `record_usage()` accepts `group` string parameter
- [ ] All platform tests pass
- [ ] All SDK tests pass
