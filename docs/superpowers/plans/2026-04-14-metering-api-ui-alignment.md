# Metering API ↔ UI Alignment — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Align the metering backend models and API endpoints with the UI so the frontend can consume real data with zero adapter layers. Slug-based card lookup replaces attribute-based matching as the primary pricing path.

**Architecture:** Card lookup shifts from `(event_type, provider, dimensions)` to `slug` as primary key. Rate model gains `pricing_type` + display metadata. New `EventBatch` model supports operator-facing audit trail. Three new dashboard endpoints split by component loading pattern. Six new event management endpoints for tenant-wide CRUD. All monetary values stay in micros throughout. A camelCase response middleware ensures the UI consumes API responses without key transformation adapters.

**Tech Stack:** Django 6.0 + django-ninja, PostgreSQL, existing `UsageEvent`/`Card`/`Rate`/`TenantMarkup` models, Clerk JWT auth for dashboard endpoints, API key auth for SDK endpoints.

**Test command:** `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest --tb=short -q`

**Current test count:** 521 platform + 122 SDK tests passing.

---

## File Map

### Modified files

| File | Changes |
|------|---------|
| `apps/metering/pricing/models.py` | Add `slug`, `group` FK, `pricing_source_url`, `draft` status to Card. Add `pricing_type`, `label`, `unit` to Rate. Update `calculate_cost_micros` for flat pricing. |
| `apps/metering/usage/models.py` | Add `card` FK and `batch` FK to UsageEvent. Add `EventBatch` model. |
| `apps/metering/pricing/services/pricing_service.py` | Add `price_event_by_slug()`. Return card object. |
| `apps/metering/usage/services/usage_service.py` | Accept `pricing_card` slug. Store `card` FK on created event. |
| `api/v1/schemas.py` | New/updated schemas for cards, rates, events, dashboard. |
| `api/v1/metering_endpoints.py` | Update card CRUD to include new fields. Add slug-based usage endpoint. |
| `api/v1/platform_endpoints.py` | Add dashboard + events endpoints (including export). |
| `api/v1/middleware.py` | New — camelCase response key transformer for UI consumption. |
| `config/urls.py` | No changes — new endpoints go on existing `platform_api` and `metering_api` routers. |

### New files

| File | Purpose |
|------|---------|
| `api/v1/middleware.py` | CamelCase response middleware for snake_case → camelCase key transformation |
| `apps/metering/pricing/tests/test_slug_lookup.py` | Tests for slug-based card lookup + flat pricing |
| `apps/metering/usage/tests/test_event_batch.py` | Tests for batch push + audit trail |
| `api/v1/tests/test_dashboard_endpoints.py` | Tests for 3 dashboard endpoints |
| `api/v1/tests/test_event_endpoints.py` | Tests for 6 event management endpoints |
| `api/v1/tests/test_camel_case.py` | Tests for camelCase middleware |

### Migrations

| Migration | App | Fields |
|-----------|-----|--------|
| `0008_card_slug_group_pricing.py` | `metering.pricing` | Card: `slug`, `group` FK, `pricing_source_url`, status choice. Rate: `pricing_type`, `label`, `unit`. |
| `0017_usage_event_card_batch.py` | `metering.usage` | UsageEvent: `card` FK, `batch` FK. EventBatch model. |

---

## Task 1: Card Model — Add slug, group FK, pricing_source_url, draft status

**Files:**
- Modify: `apps/metering/pricing/models.py`
- Create: `apps/metering/pricing/migrations/0008_card_slug_group_pricing.py` (auto-generated)
- Test: `apps/metering/pricing/tests/test_card_rate.py`

- [ ] **Step 1: Write failing tests for new Card fields**

Add to `apps/metering/pricing/tests/test_card_rate.py`:

```python
from apps.platform.groups.models import Group


class CardSlugTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Test Tenant")

    def test_create_card_with_slug(self):
        card = Card.objects.create(
            tenant=self.tenant,
            name="Gemini 2 Flash",
            slug="gemini_2_flash",
            provider="google",
            event_type="llm_call",
        )
        card.refresh_from_db()
        self.assertEqual(card.slug, "gemini_2_flash")

    def test_slug_unique_per_tenant_active(self):
        Card.objects.create(
            tenant=self.tenant,
            name="Card A",
            slug="gemini_2_flash",
            provider="google",
            event_type="llm_call",
        )
        with self.assertRaises(IntegrityError):
            Card.objects.create(
                tenant=self.tenant,
                name="Card B",
                slug="gemini_2_flash",
                provider="google",
                event_type="inference",
            )

    def test_slug_unique_allows_archived_duplicate(self):
        Card.objects.create(
            tenant=self.tenant,
            name="Card Old",
            slug="gemini_2_flash",
            provider="google",
            event_type="llm_call",
            status="archived",
        )
        card = Card.objects.create(
            tenant=self.tenant,
            name="Card New",
            slug="gemini_2_flash",
            provider="google",
            event_type="llm_call",
        )
        self.assertEqual(card.status, "active")

    def test_draft_status(self):
        card = Card.objects.create(
            tenant=self.tenant,
            name="Draft Card",
            slug="draft_card",
            provider="openai",
            event_type="embedding",
            status="draft",
        )
        self.assertEqual(card.status, "draft")

    def test_card_with_group(self):
        group = Group.objects.create(
            tenant=self.tenant, name="Research", slug="research"
        )
        card = Card.objects.create(
            tenant=self.tenant,
            name="Card",
            slug="my_card",
            provider="openai",
            event_type="llm_call",
            group=group,
        )
        card.refresh_from_db()
        self.assertEqual(card.group_id, group.id)

    def test_card_group_set_null_on_delete(self):
        group = Group.objects.create(
            tenant=self.tenant, name="Research", slug="research"
        )
        card = Card.objects.create(
            tenant=self.tenant,
            name="Card",
            slug="my_card",
            provider="openai",
            event_type="llm_call",
            group=group,
        )
        group.status = "archived"
        group.save()
        # Soft-delete doesn't cascade, but hard delete does SET_NULL
        Group.objects.filter(id=group.id).delete()
        card.refresh_from_db()
        self.assertIsNone(card.group)

    def test_pricing_source_url(self):
        card = Card.objects.create(
            tenant=self.tenant,
            name="Card",
            slug="my_card",
            provider="openai",
            event_type="llm_call",
            pricing_source_url="https://openai.com/api/pricing",
        )
        card.refresh_from_db()
        self.assertEqual(card.pricing_source_url, "https://openai.com/api/pricing")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/metering/pricing/tests/test_card_rate.py -v -k "Slug" --tb=short`

Expected: FAIL — `slug` field does not exist on Card.

- [ ] **Step 3: Update Card model**

In `apps/metering/pricing/models.py`, update the `Card` class:

```python
class Card(BaseModel):
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="pricing_cards",
    )
    name = models.CharField(max_length=255)
    slug = models.CharField(max_length=255, db_index=True)
    provider = models.CharField(max_length=100, db_index=True)
    event_type = models.CharField(max_length=100, db_index=True)
    dimensions = models.JSONField(default=dict)
    dimensions_hash = models.CharField(max_length=64, db_index=True, blank=True)
    description = models.TextField(blank=True, default="")
    group = models.ForeignKey(
        "groups.Group",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pricing_cards",
    )
    pricing_source_url = models.URLField(max_length=500, blank=True, default="")
    status = models.CharField(
        max_length=20,
        choices=[("draft", "Draft"), ("active", "Active"), ("archived", "Archived")],
        default="active",
    )

    class Meta:
        db_table = "ubb_card"
        indexes = [
            models.Index(
                fields=["tenant", "provider", "event_type"],
                name="idx_card_tenant_lookup",
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "provider", "event_type", "dimensions_hash"],
                condition=models.Q(status="active"),
                name="uq_card_active_per_tenant",
            ),
            models.UniqueConstraint(
                fields=["tenant", "slug"],
                condition=models.Q(status__in=["active", "draft"]),
                name="uq_card_slug_per_tenant",
            ),
        ]

    def save(self, *args, **kwargs):
        import hashlib
        import json
        canonical = json.dumps(self.dimensions, sort_keys=True)
        self.dimensions_hash = hashlib.sha256(canonical.encode()).hexdigest()
        super().save(*args, **kwargs)
```

- [ ] **Step 4: Generate and run migration**

Run:
```bash
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python manage.py makemigrations pricing --name card_slug_group_pricing
```

Then:
```bash
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python manage.py migrate
```

- [ ] **Step 5: Backfill slugs for existing cards**

The migration should include a data migration to backfill `slug` from `name` (slugified). If no existing data in dev, skip this step. If there is data, add a `RunPython` operation:

```python
from django.utils.text import slugify

def backfill_slugs(apps, schema_editor):
    Card = apps.get_model("pricing", "Card")
    for card in Card.objects.filter(slug=""):
        card.slug = slugify(card.name).replace("-", "_")
        card.save(update_fields=["slug"])
```

- [ ] **Step 6: Update existing Card tests to include slug**

In `apps/metering/pricing/tests/test_card_rate.py`, update `setUp` in `CardModelTest` and `RateModelTest` to include `slug` on Card creation:

```python
# CardModelTest.test_create_card
card = Card.objects.create(
    tenant=self.tenant,
    name="GPT-4o Pricing",
    slug="gpt_4o",
    provider="openai",
    event_type="llm_call",
    dimensions={"model": "gpt-4o"},
)

# CardModelTest.test_dimensions_hash_computed_on_save — same, add slug="gpt_4o"
# CardModelTest.test_unique_active_card — first gets slug="gpt_4o", second gets slug="gpt_4o_dup"
# CardModelTest.test_archived_card_does_not_conflict — old gets slug="gpt_4o_old", new gets slug="gpt_4o_new"
# RateModelTest.setUp — add slug="gpt_4o"
```

- [ ] **Step 7: Run all pricing tests**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/metering/pricing/tests/ -v --tb=short`

Expected: ALL PASS

- [ ] **Step 8: Commit**

```
feat(pricing): add slug, group FK, draft status to Card model
```

---

## Task 2: Rate Model — Add pricing_type, label, unit

**Files:**
- Modify: `apps/metering/pricing/models.py`
- Test: `apps/metering/pricing/tests/test_card_rate.py`

- [ ] **Step 1: Write failing tests for new Rate fields and flat pricing**

Add to `apps/metering/pricing/tests/test_card_rate.py`:

```python
class RatePricingTypeTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Test Tenant")
        self.card = Card.objects.create(
            tenant=self.tenant,
            name="Gemini Flash",
            slug="gemini_flash",
            provider="google",
            event_type="llm_call",
        )

    def test_per_unit_rate(self):
        rate = Rate.objects.create(
            card=self.card,
            metric_name="input_tokens",
            pricing_type="per_unit",
            cost_per_unit_micros=75_000,
            unit_quantity=1_000_000,
            label="Input Tokens",
            unit="per 1M tokens",
        )
        rate.refresh_from_db()
        self.assertEqual(rate.pricing_type, "per_unit")
        self.assertEqual(rate.label, "Input Tokens")
        self.assertEqual(rate.unit, "per 1M tokens")

    def test_flat_rate(self):
        rate = Rate.objects.create(
            card=self.card,
            metric_name="grounding_requests",
            pricing_type="flat",
            cost_per_unit_micros=5_000,
            unit_quantity=1,
            label="Grounding",
            unit="per request",
        )
        rate.refresh_from_db()
        self.assertEqual(rate.pricing_type, "flat")

    def test_flat_calculate_cost_ignores_quantity(self):
        rate = Rate.objects.create(
            card=self.card,
            metric_name="grounding_requests",
            pricing_type="flat",
            cost_per_unit_micros=5_000,
            unit_quantity=1,
        )
        # Flat pricing: cost = cost_per_unit_micros regardless of units
        self.assertEqual(rate.calculate_cost_micros(1), 5_000)
        self.assertEqual(rate.calculate_cost_micros(100), 5_000)
        self.assertEqual(rate.calculate_cost_micros(0), 5_000)

    def test_per_unit_calculate_cost_unchanged(self):
        rate = Rate.objects.create(
            card=self.card,
            metric_name="input_tokens",
            pricing_type="per_unit",
            cost_per_unit_micros=75_000,
            unit_quantity=1_000_000,
        )
        self.assertEqual(rate.calculate_cost_micros(1_000_000), 75_000)
        self.assertEqual(rate.calculate_cost_micros(1_000), 75)

    def test_default_pricing_type_is_per_unit(self):
        rate = Rate.objects.create(
            card=self.card,
            metric_name="tokens",
            cost_per_unit_micros=100,
            unit_quantity=1_000_000,
        )
        rate.refresh_from_db()
        self.assertEqual(rate.pricing_type, "per_unit")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/metering/pricing/tests/test_card_rate.py -v -k "PricingType" --tb=short`

Expected: FAIL — `pricing_type` field does not exist.

- [ ] **Step 3: Update Rate model**

In `apps/metering/pricing/models.py`, update the `Rate` class:

```python
class Rate(BaseModel):
    card = models.ForeignKey(
        Card,
        on_delete=models.CASCADE,
        related_name="rates",
    )
    metric_name = models.CharField(max_length=100, db_index=True)
    pricing_type = models.CharField(
        max_length=20,
        choices=[("per_unit", "Per Unit"), ("flat", "Flat")],
        default="per_unit",
    )
    cost_per_unit_micros = models.BigIntegerField()
    unit_quantity = models.BigIntegerField(default=1_000_000)
    currency = models.CharField(max_length=3, default="USD")
    label = models.CharField(max_length=100, blank=True, default="")
    unit = models.CharField(max_length=50, blank=True, default="")
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
        """Calculate cost. Flat rates ignore quantity; per-unit uses round-half-up."""
        if self.pricing_type == "flat":
            return self.cost_per_unit_micros
        return (units * self.cost_per_unit_micros + self.unit_quantity // 2) // self.unit_quantity
```

- [ ] **Step 4: Generate and apply migration**

Run:
```bash
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python manage.py makemigrations pricing --name rate_pricing_type_label_unit
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python manage.py migrate
```

Note: if this merges with the Task 1 migration into one, that's fine. Django may auto-combine.

- [ ] **Step 5: Run all pricing tests**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/metering/pricing/tests/ -v --tb=short`

Expected: ALL PASS (new tests + existing tests unchanged)

- [ ] **Step 6: Commit**

```
feat(pricing): add pricing_type, label, unit to Rate model
```

---

## Task 3: UsageEvent Model — Add card FK + EventBatch model

**Files:**
- Modify: `apps/metering/usage/models.py`
- Create: `apps/metering/usage/migrations/0017_*.py` (auto-generated)
- Test: `apps/metering/usage/tests/test_models.py`

- [ ] **Step 1: Write failing tests for new fields**

Add to `apps/metering/usage/tests/test_models.py`:

```python
from apps.metering.pricing.models import Card
from apps.metering.usage.models import UsageEvent, EventBatch


class UsageEventCardFKTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Test")
        self.customer = Customer.objects.create(tenant=self.tenant, external_id="c1")
        self.card = Card.objects.create(
            tenant=self.tenant,
            name="Gemini Flash",
            slug="gemini_flash",
            provider="google",
            event_type="llm_call",
        )

    def test_event_with_card_fk(self):
        event = UsageEvent.objects.create(
            tenant=self.tenant,
            customer=self.customer,
            request_id="req_1",
            idempotency_key="idem_1",
            cost_micros=1000,
            card=self.card,
        )
        event.refresh_from_db()
        self.assertEqual(event.card_id, self.card.id)

    def test_event_card_nullable(self):
        event = UsageEvent.objects.create(
            tenant=self.tenant,
            customer=self.customer,
            request_id="req_2",
            idempotency_key="idem_2",
            cost_micros=1000,
        )
        self.assertIsNone(event.card)

    def test_event_card_set_null_on_archive(self):
        """Archiving a card doesn't delete events — SET_NULL."""
        event = UsageEvent.objects.create(
            tenant=self.tenant,
            customer=self.customer,
            request_id="req_3",
            idempotency_key="idem_3",
            cost_micros=1000,
            card=self.card,
        )
        # Hard delete card (simulating)
        Card.objects.filter(id=self.card.id).delete()
        event.refresh_from_db()
        self.assertIsNone(event.card)


class EventBatchTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Test")
        self.customer = Customer.objects.create(tenant=self.tenant, external_id="c1")

    def test_create_batch(self):
        batch = EventBatch.objects.create(
            tenant=self.tenant,
            action="added",
            reason="Monthly import",
            row_count=150,
            author="user@example.com",
        )
        batch.refresh_from_db()
        self.assertEqual(batch.action, "added")
        self.assertEqual(batch.row_count, 150)
        self.assertIsNone(batch.reversed_at)

    def test_event_linked_to_batch(self):
        batch = EventBatch.objects.create(
            tenant=self.tenant,
            action="added",
            reason="Import",
            row_count=1,
            author="user@example.com",
        )
        event = UsageEvent.objects.create(
            tenant=self.tenant,
            customer=self.customer,
            request_id="req_batch",
            idempotency_key="idem_batch",
            cost_micros=1000,
            batch=batch,
        )
        self.assertEqual(event.batch_id, batch.id)
        self.assertEqual(batch.events.count(), 1)

    def test_batch_nullable_on_event(self):
        event = UsageEvent.objects.create(
            tenant=self.tenant,
            customer=self.customer,
            request_id="req_no_batch",
            idempotency_key="idem_no_batch",
            cost_micros=1000,
        )
        self.assertIsNone(event.batch)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/metering/usage/tests/test_models.py -v -k "CardFK or EventBatch" --tb=short`

Expected: FAIL — fields/model don't exist.

- [ ] **Step 3: Add EventBatch model and card/batch FKs to UsageEvent**

In `apps/metering/usage/models.py`, add the `EventBatch` class and update `UsageEvent`:

```python
class EventBatch(BaseModel):
    """Tracks operator-initiated batch event pushes for audit trail."""
    tenant = models.ForeignKey(
        "tenants.Tenant", on_delete=models.CASCADE, related_name="event_batches"
    )
    action = models.CharField(
        max_length=20,
        choices=[("added", "Added"), ("reversed", "Reversed")],
    )
    reason = models.TextField(blank=True, default="")
    row_count = models.IntegerField()
    author = models.CharField(max_length=255)
    reversed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "ubb_event_batch"
        ordering = ["-created_at"]

    def __str__(self):
        return f"EventBatch({self.action}: {self.row_count} rows)"


class UsageEvent(BaseModel):
    # ... existing fields ...

    # ADD these two FKs after the existing `run` field:
    card = models.ForeignKey(
        "pricing.Card", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="usage_events",
    )
    batch = models.ForeignKey(
        EventBatch, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="events",
    )
    # ... rest unchanged ...
```

- [ ] **Step 4: Generate and apply migration**

Run:
```bash
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python manage.py makemigrations usage --name usage_event_card_batch
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python manage.py migrate
```

- [ ] **Step 5: Run all usage tests**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/metering/usage/tests/ -v --tb=short`

Expected: ALL PASS

- [ ] **Step 6: Commit**

```
feat(usage): add card FK, EventBatch model, batch FK to UsageEvent
```

---

## Task 4: PricingService — Add slug-based card lookup

**Files:**
- Modify: `apps/metering/pricing/services/pricing_service.py`
- Test: `apps/metering/pricing/tests/test_pricing_service_v2.py`

- [ ] **Step 1: Write failing tests for slug-based pricing**

Add to `apps/metering/pricing/tests/test_pricing_service_v2.py`:

```python
class SlugBasedPricingTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Test", stripe_connected_account_id="acct_test"
        )
        self.card = Card.objects.create(
            tenant=self.tenant,
            name="Gemini Flash",
            slug="gemini_2_flash",
            provider="google",
            event_type="llm_call",
        )
        Rate.objects.create(
            card=self.card,
            metric_name="input_tokens",
            pricing_type="per_unit",
            cost_per_unit_micros=75_000,
            unit_quantity=1_000_000,
            label="Input Tokens",
            unit="per 1M tokens",
        )
        Rate.objects.create(
            card=self.card,
            metric_name="output_tokens",
            pricing_type="per_unit",
            cost_per_unit_micros=300_000,
            unit_quantity=1_000_000,
        )
        Rate.objects.create(
            card=self.card,
            metric_name="grounding_requests",
            pricing_type="flat",
            cost_per_unit_micros=5_000,
            unit_quantity=1,
        )
        TenantMarkup.objects.create(tenant=self.tenant, margin_pct=40)

    def test_price_event_by_slug(self):
        provider_cost, billed_cost, prov, card = PricingService.price_event_by_slug(
            tenant=self.tenant,
            card_slug="gemini_2_flash",
            usage_metrics={"input_tokens": 1_000_000, "output_tokens": 500_000},
        )
        # input: 75_000, output: 150_000 = 225_000
        self.assertEqual(provider_cost, 225_000)
        self.assertEqual(card.slug, "gemini_2_flash")

    def test_price_event_by_slug_with_flat_rate(self):
        provider_cost, billed_cost, prov, card = PricingService.price_event_by_slug(
            tenant=self.tenant,
            card_slug="gemini_2_flash",
            usage_metrics={"grounding_requests": 1},
        )
        self.assertEqual(provider_cost, 5_000)

    def test_price_event_by_slug_mixed_metrics(self):
        provider_cost, billed_cost, prov, card = PricingService.price_event_by_slug(
            tenant=self.tenant,
            card_slug="gemini_2_flash",
            usage_metrics={
                "input_tokens": 1_000_000,
                "output_tokens": 500_000,
                "grounding_requests": 1,
            },
        )
        # input: 75_000 + output: 150_000 + grounding: 5_000 = 230_000
        self.assertEqual(provider_cost, 230_000)

    def test_price_event_by_slug_not_found(self):
        with self.assertRaises(PricingError) as ctx:
            PricingService.price_event_by_slug(
                tenant=self.tenant,
                card_slug="nonexistent_card",
                usage_metrics={"tokens": 100},
            )
        self.assertIn("nonexistent_card", str(ctx.exception))

    def test_price_event_by_slug_returns_card_in_provenance(self):
        _, _, prov, card = PricingService.price_event_by_slug(
            tenant=self.tenant,
            card_slug="gemini_2_flash",
            usage_metrics={"input_tokens": 1000},
        )
        self.assertEqual(prov["card_id"], str(self.card.id))
        self.assertEqual(prov["card_slug"], "gemini_2_flash")

    def test_price_event_by_slug_draft_card_not_found(self):
        self.card.status = "draft"
        self.card.save()
        with self.assertRaises(PricingError):
            PricingService.price_event_by_slug(
                tenant=self.tenant,
                card_slug="gemini_2_flash",
                usage_metrics={"input_tokens": 1000},
            )

    def test_price_event_by_slug_with_group_margin(self):
        Group.objects.create(
            tenant=self.tenant, name="Premium", slug="premium", margin_pct=60,
        )
        _, billed, _, _ = PricingService.price_event_by_slug(
            tenant=self.tenant,
            card_slug="gemini_2_flash",
            usage_metrics={"input_tokens": 1_000_000},
            group="premium",
        )
        # provider_cost = 75_000, margin 60%: 75_000 / 0.40 = 187_500
        self.assertEqual(billed, 187_500)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/metering/pricing/tests/test_pricing_service_v2.py -v -k "SlugBased" --tb=short`

Expected: FAIL — `price_event_by_slug` does not exist.

- [ ] **Step 3: Implement price_event_by_slug**

In `apps/metering/pricing/services/pricing_service.py`, add the new method:

```python
@staticmethod
def price_event_by_slug(
    tenant,
    card_slug: str,
    usage_metrics: Dict[str, int],
    group: str = None,
    as_of=None,
) -> Tuple[int, int, Dict, "Card"]:
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
            "pricing_type": rate.pricing_type,
            "cost_micros": metric_cost,
        }

    # Resolve and apply margin (reuses existing logic)
    margin_pct, margin_source = PricingService._resolve_margin(
        tenant, card.event_type, card.provider, group, as_of,
    )
    billed_cost = PricingService._apply_margin(total_provider_cost, margin_pct)

    provenance = {
        "engine_version": PRICING_ENGINE_VERSION,
        "calculated_at": as_of.isoformat(),
        "card_id": str(card.id),
        "card_slug": card.slug,
        "card_name": card.name,
        "metrics": provenance_metrics,
        "margin": {
            "margin_pct": float(margin_pct),
            "source": margin_source,
        },
        "provider_cost_micros": total_provider_cost,
        "billed_cost_micros": billed_cost,
    }

    return total_provider_cost, billed_cost, provenance, card
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/metering/pricing/tests/test_pricing_service_v2.py -v --tb=short`

Expected: ALL PASS (new slug tests + existing attribute-based tests)

- [ ] **Step 5: Commit**

```
feat(pricing): add slug-based card lookup to PricingService
```

---

## Task 5: UsageService — Accept pricing_card slug, store card FK

**Files:**
- Modify: `apps/metering/usage/services/usage_service.py`
- Test: `apps/metering/usage/tests/test_usage_service.py`

- [ ] **Step 1: Write failing tests for slug-based usage recording**

Add to `apps/metering/usage/tests/test_usage_service.py`:

```python
class UsageServiceSlugTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Test", stripe_connected_account_id="acct_test"
        )
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="c1"
        )
        self.card = Card.objects.create(
            tenant=self.tenant,
            name="Gemini Flash",
            slug="gemini_2_flash",
            provider="google",
            event_type="llm_call",
        )
        Rate.objects.create(
            card=self.card,
            metric_name="input_tokens",
            pricing_type="per_unit",
            cost_per_unit_micros=75_000,
            unit_quantity=1_000_000,
        )

    @patch("apps.platform.events.tasks.process_single_event")
    def test_record_usage_with_pricing_card_slug(self, mock_process):
        result = UsageService.record_usage(
            tenant=self.tenant,
            customer=self.customer,
            request_id="req_slug_1",
            idempotency_key="idem_slug_1",
            pricing_card="gemini_2_flash",
            usage_metrics={"input_tokens": 1_000_000},
        )
        self.assertEqual(result["provider_cost_micros"], 75_000)
        self.assertEqual(result["billed_cost_micros"], 75_000)
        # Verify card FK stored on event
        event = UsageEvent.objects.get(id=result["event_id"])
        self.assertEqual(event.card_id, self.card.id)
        # event_type and provider populated from card
        self.assertEqual(event.event_type, "llm_call")
        self.assertEqual(event.provider, "google")

    @patch("apps.platform.events.tasks.process_single_event")
    def test_record_usage_slug_stores_card_fk(self, mock_process):
        result = UsageService.record_usage(
            tenant=self.tenant,
            customer=self.customer,
            request_id="req_slug_fk",
            idempotency_key="idem_slug_fk",
            pricing_card="gemini_2_flash",
            usage_metrics={"input_tokens": 500},
        )
        event = UsageEvent.objects.get(id=result["event_id"])
        self.assertEqual(event.card_id, self.card.id)

    @patch("apps.platform.events.tasks.process_single_event")
    def test_record_usage_slug_not_found_raises(self, mock_process):
        from apps.metering.pricing.services.pricing_service import PricingError
        with self.assertRaises(PricingError):
            UsageService.record_usage(
                tenant=self.tenant,
                customer=self.customer,
                request_id="req_slug_bad",
                idempotency_key="idem_slug_bad",
                pricing_card="nonexistent",
                usage_metrics={"input_tokens": 100},
            )

    @patch("apps.platform.events.tasks.process_single_event")
    def test_legacy_event_type_provider_still_works(self, mock_process):
        """Existing attribute-based path unchanged."""
        result = UsageService.record_usage(
            tenant=self.tenant,
            customer=self.customer,
            request_id="req_legacy",
            idempotency_key="idem_legacy",
            event_type="llm_call",
            provider="google",
            usage_metrics={"input_tokens": 1_000_000},
            properties={"model": "gemini-2.0-flash"},  # won't match without dimensions on card
        )
        # Falls through to attribute-based lookup; card has no dimensions so it matches
        self.assertEqual(result["provider_cost_micros"], 75_000)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/metering/usage/tests/test_usage_service.py -v -k "Slug" --tb=short`

Expected: FAIL — `pricing_card` is not an accepted parameter.

- [ ] **Step 3: Update UsageService.record_usage**

In `apps/metering/usage/services/usage_service.py`:

```python
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
        event_type=None,
        provider=None,
        usage_metrics=None,
        properties=None,
        group=None,
        run_id=None,
        pricing_card=None,  # NEW: card slug for slug-based lookup
    ):
        # 1. Idempotency check — fast path
        existing = UsageEvent.objects.filter(
            tenant=tenant, customer=customer, idempotency_key=idempotency_key
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

        # 2. Price the event
        provider_cost_micros = None
        billed_cost_micros = None
        pricing_provenance = {}
        card_obj = None

        if pricing_card and usage_metrics is not None:
            # Slug-based lookup (primary path)
            from apps.metering.pricing.services.pricing_service import PricingService
            provider_cost_micros, billed_cost_micros, pricing_provenance, card_obj = (
                PricingService.price_event_by_slug(
                    tenant=tenant,
                    card_slug=pricing_card,
                    usage_metrics=usage_metrics,
                    group=group,
                )
            )
            cost_micros = billed_cost_micros
            # Populate event_type/provider from card for analytics
            event_type = card_obj.event_type
            provider = card_obj.provider
        elif usage_metrics is not None:
            # Attribute-based lookup (legacy/fallback)
            from apps.metering.pricing.services.pricing_service import PricingService
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
            cost_micros = billed_cost_micros

        # 2.5 Run hard-stop check
        run = None
        if run_id is not None:
            from apps.platform.runs.services import RunService
            effective_cost_for_run = (
                billed_cost_micros if billed_cost_micros is not None else cost_micros
            )
            run = RunService.accumulate_cost(run_id, effective_cost_for_run or 0)

        # 3. Create event
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
                    event_type=event_type or "",
                    provider=provider or "",
                    usage_metrics=usage_metrics or {},
                    properties=properties or {},
                    provider_cost_micros=provider_cost_micros,
                    billed_cost_micros=billed_cost_micros,
                    pricing_provenance=pricing_provenance,
                    group=group,
                    run_id=run_id,
                    card=card_obj,
                )
        except IntegrityError:
            existing = UsageEvent.objects.get(
                tenant=tenant, customer=customer, idempotency_key=idempotency_key
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

        # 4-5. Outbox event — unchanged
        effective_cost = billed_cost_micros if billed_cost_micros is not None else cost_micros
        write_event(UsageRecorded(
            tenant_id=str(tenant.id),
            customer_id=str(customer.id),
            event_id=str(event.id),
            cost_micros=effective_cost,
            provider_cost_micros=provider_cost_micros,
            billed_cost_micros=billed_cost_micros,
            event_type=event_type or "",
            provider=provider or "",
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

- [ ] **Step 4: Run all usage service tests**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/metering/usage/tests/test_usage_service.py -v --tb=short`

Expected: ALL PASS (new slug tests + all existing tests unchanged)

- [ ] **Step 5: Run full test suite to verify no regressions**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest --tb=short -q`

Expected: All tests pass (count should be ≥521).

- [ ] **Step 6: Commit**

```
feat(usage): slug-based pricing in UsageService, store card FK on events
```

---

## Task 6: Update API Schemas + Card CRUD Endpoints

**Files:**
- Modify: `api/v1/schemas.py`
- Modify: `api/v1/metering_endpoints.py`

- [ ] **Step 1: Write failing test for updated card API response**

Create `api/v1/tests/__init__.py` (empty) and `api/v1/tests/test_card_api.py`:

```python
from django.test import TestCase, Client
from apps.platform.tenants.models import Tenant, TenantApiKey
from apps.platform.groups.models import Group
from apps.metering.pricing.models import Card, Rate


class CardAPITest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Test", products=["metering"]
        )
        self.api_key = TenantApiKey.objects.create(tenant=self.tenant)
        self.token = self.api_key.raw_key  # or however the key is generated
        self.client = Client()
        self.headers = {"HTTP_AUTHORIZATION": f"Bearer {self.token}"}

    def _create_card_via_api(self, **overrides):
        payload = {
            "name": "Gemini Flash",
            "slug": "gemini_2_flash",
            "provider": "google",
            "event_type": "llm_call",
            "rates": [
                {
                    "metric_name": "input_tokens",
                    "pricing_type": "per_unit",
                    "cost_per_unit_micros": 75000,
                    "unit_quantity": 1000000,
                    "label": "Input Tokens",
                    "unit": "per 1M tokens",
                }
            ],
            **overrides,
        }
        import json
        return self.client.post(
            "/api/v1/metering/pricing/cards",
            data=json.dumps(payload),
            content_type="application/json",
            **self.headers,
        )

    def test_create_card_returns_slug(self):
        resp = self._create_card_via_api()
        self.assertEqual(resp.status_code, 201)
        data = resp.json()
        self.assertEqual(data["slug"], "gemini_2_flash")
        self.assertEqual(data["provider"], "google")
        self.assertEqual(data["event_type"], "llm_call")
        self.assertEqual(len(data["rates"]), 1)
        self.assertEqual(data["rates"][0]["pricing_type"], "per_unit")
        self.assertEqual(data["rates"][0]["label"], "Input Tokens")
        self.assertEqual(data["rates"][0]["unit"], "per 1M tokens")

    def test_create_card_with_group(self):
        group = Group.objects.create(
            tenant=self.tenant, name="Research", slug="research"
        )
        resp = self._create_card_via_api(group_id=str(group.id))
        self.assertEqual(resp.status_code, 201)
        data = resp.json()
        self.assertEqual(data["group_id"], str(group.id))
        self.assertEqual(data["group_name"], "Research")

    def test_create_card_draft_status(self):
        resp = self._create_card_via_api(status="draft")
        self.assertEqual(resp.status_code, 201)
        data = resp.json()
        self.assertEqual(data["status"], "draft")

    def test_list_cards_includes_draft_and_active(self):
        self._create_card_via_api(slug="card_a", name="Card A", status="active")
        self._create_card_via_api(slug="card_b", name="Card B", status="draft",
                                   provider="openai", event_type="embedding")
        resp = self.client.get(
            "/api/v1/metering/pricing/cards",
            **self.headers,
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        slugs = {c["slug"] for c in data["data"]}
        self.assertIn("card_a", slugs)
        self.assertIn("card_b", slugs)
```

Note: the `TenantApiKey` raw_key access depends on your implementation. Check `apps/platform/tenants/models.py` to see how keys are generated — you may need `TenantApiKey.generate_key()` or similar.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest api/v1/tests/test_card_api.py -v --tb=short`

Expected: FAIL — schema doesn't include slug, pricing_type, etc.

- [ ] **Step 3: Update schemas in api/v1/schemas.py**

```python
# Replace the existing card/rate schemas:

class RateIn(Schema):
    metric_name: str = Field(min_length=1, max_length=100)
    pricing_type: str = Field(default="per_unit", pattern=r"^(per_unit|flat)$")
    cost_per_unit_micros: int = Field(ge=0)
    unit_quantity: int = Field(gt=0, default=1_000_000)
    currency: str = Field(default="USD", max_length=3)
    label: str = Field(default="", max_length=100)
    unit: str = Field(default="", max_length=50)


class CreateCardRequest(Schema):
    name: str = Field(min_length=1, max_length=255)
    slug: str = Field(min_length=2, max_length=255, pattern=r"^[a-z][a-z0-9_]*$")
    provider: str = Field(min_length=1, max_length=100)
    event_type: str = Field(min_length=1, max_length=100)
    dimensions: dict = Field(default_factory=dict)
    description: str = ""
    pricing_source_url: str = ""
    group_id: Optional[str] = None
    status: str = Field(default="active", pattern=r"^(draft|active)$")
    rates: list[RateIn] = Field(default_factory=list)


class UpdateCardRequest(Schema):
    name: Optional[str] = None
    description: Optional[str] = None
    pricing_source_url: Optional[str] = None
    group_id: Optional[str] = None
    status: Optional[str] = None


class RateOut(Schema):
    id: str
    metric_name: str
    pricing_type: str
    cost_per_unit_micros: int
    unit_quantity: int
    currency: str
    label: str
    unit: str
    valid_from: str
    valid_to: Optional[str] = None


class CardOut(Schema):
    id: str
    slug: str
    name: str
    provider: str
    event_type: str
    dimensions: dict
    description: str
    pricing_source_url: str
    group_id: Optional[str] = None
    group_name: Optional[str] = None
    status: str
    rates: list[RateOut]
    created_at: str
    updated_at: str
```

- [ ] **Step 4: Update metering_endpoints.py card CRUD**

Update `_card_to_out` to include new fields:

```python
def _card_to_out(card):
    rates = card.rates.filter(valid_to__isnull=True).order_by("metric_name")
    return {
        "id": str(card.id),
        "slug": card.slug,
        "name": card.name,
        "provider": card.provider,
        "event_type": card.event_type,
        "dimensions": card.dimensions,
        "description": card.description,
        "pricing_source_url": card.pricing_source_url,
        "group_id": str(card.group_id) if card.group_id else None,
        "group_name": card.group.name if card.group_id else None,
        "status": card.status,
        "rates": [
            {
                "id": str(r.id),
                "metric_name": r.metric_name,
                "pricing_type": r.pricing_type,
                "cost_per_unit_micros": r.cost_per_unit_micros,
                "unit_quantity": r.unit_quantity,
                "currency": r.currency,
                "label": r.label,
                "unit": r.unit,
                "valid_from": r.valid_from.isoformat(),
                "valid_to": None,
            }
            for r in rates
        ],
        "created_at": card.created_at.isoformat(),
        "updated_at": card.updated_at.isoformat(),
    }
```

Update `create_card` to handle new fields:

```python
@metering_api.post("/pricing/cards", response={201: CardOut})
def create_card(request, payload: CreateCardRequest):
    _product_check(request)
    from apps.metering.pricing.models import Card, Rate
    from apps.platform.groups.models import Group

    group = None
    if payload.group_id:
        group = get_object_or_404(Group, id=payload.group_id, tenant=request.auth.tenant)

    card = Card.objects.create(
        tenant=request.auth.tenant,
        name=payload.name,
        slug=payload.slug,
        provider=payload.provider,
        event_type=payload.event_type,
        dimensions=payload.dimensions,
        description=payload.description,
        pricing_source_url=payload.pricing_source_url,
        group=group,
        status=payload.status,
    )
    for rate_in in payload.rates:
        Rate.objects.create(
            card=card,
            metric_name=rate_in.metric_name,
            pricing_type=rate_in.pricing_type,
            cost_per_unit_micros=rate_in.cost_per_unit_micros,
            unit_quantity=rate_in.unit_quantity,
            currency=rate_in.currency,
            label=rate_in.label,
            unit=rate_in.unit,
        )
    return 201, _card_to_out(card)
```

Update `list_cards` to include draft cards:

```python
@metering_api.get("/pricing/cards", response=CardListResponse)
def list_cards(request, cursor: str = None, limit: int = 50):
    _product_check(request)
    from apps.metering.pricing.models import Card

    limit = min(max(limit, 1), 100)
    qs = Card.objects.filter(
        tenant=request.auth.tenant, status__in=["active", "draft"],
    ).select_related("group").order_by("-created_at", "-id")
    # ... rest unchanged ...
```

Update `update_card` to handle new fields:

```python
@metering_api.patch("/pricing/cards/{card_id}", response=CardOut)
def update_card(request, card_id: UUID, payload: UpdateCardRequest):
    _product_check(request)
    from apps.metering.pricing.models import Card
    from apps.platform.groups.models import Group

    card = get_object_or_404(Card, id=card_id, tenant=request.auth.tenant)
    update_fields = ["updated_at"]
    if payload.name is not None:
        card.name = payload.name
        update_fields.append("name")
    if payload.description is not None:
        card.description = payload.description
        update_fields.append("description")
    if payload.pricing_source_url is not None:
        card.pricing_source_url = payload.pricing_source_url
        update_fields.append("pricing_source_url")
    if payload.group_id is not None:
        if payload.group_id == "":
            card.group = None
        else:
            card.group = get_object_or_404(Group, id=payload.group_id, tenant=request.auth.tenant)
        update_fields.append("group")
    if payload.status is not None:
        card.status = payload.status
        update_fields.append("status")
    card.save(update_fields=update_fields)
    return _card_to_out(card)
```

Also update `add_card_rate` to include new Rate fields:

```python
@metering_api.post("/pricing/cards/{card_id}/rates", response={201: dict})
def add_card_rate(request, card_id: UUID, payload: RateIn):
    _product_check(request)
    from apps.metering.pricing.models import Card, Rate

    card = get_object_or_404(Card, id=card_id, tenant=request.auth.tenant)
    rate = Rate.objects.create(
        card=card,
        metric_name=payload.metric_name,
        pricing_type=payload.pricing_type,
        cost_per_unit_micros=payload.cost_per_unit_micros,
        unit_quantity=payload.unit_quantity,
        currency=payload.currency,
        label=payload.label,
        unit=payload.unit,
    )
    return 201, {
        "id": str(rate.id),
        "metric_name": rate.metric_name,
        "pricing_type": rate.pricing_type,
        "cost_per_unit_micros": rate.cost_per_unit_micros,
        "unit_quantity": rate.unit_quantity,
        "currency": rate.currency,
        "label": rate.label,
        "unit": rate.unit,
        "valid_from": rate.valid_from.isoformat(),
        "valid_to": None,
    }
```

- [ ] **Step 5: Update the `RecordUsageRequest` schema to accept `pricing_card`**

In `api/v1/schemas.py`:

```python
class RecordUsageRequest(Schema):
    customer_id: UUID
    request_id: str = Field(min_length=1, max_length=500)
    idempotency_key: str = Field(min_length=1, max_length=500)
    pricing_card: Optional[str] = Field(default=None, max_length=255)
    event_type: str = Field(default="", max_length=100)
    provider: str = Field(default="", max_length=100)
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

- [ ] **Step 6: Update record_usage endpoint to pass pricing_card**

In `api/v1/metering_endpoints.py`, update `record_usage`:

```python
@metering_api.post("/usage", response={200: RecordUsageResponse})
def record_usage(request, payload: RecordUsageRequest):
    _product_check(request)
    from apps.metering.pricing.services.pricing_service import PricingError
    from apps.platform.runs.services import HardStopExceeded, RunNotActive

    customer = get_object_or_404(Customer, id=payload.customer_id, tenant=request.auth.tenant)

    # Validate: need either pricing_card or (event_type + usage_metrics)
    if not payload.pricing_card and not payload.event_type and payload.usage_metrics:
        from ninja.errors import HttpError
        raise HttpError(422, "Provide either 'pricing_card' or 'event_type' + 'provider'")

    try:
        result = UsageService.record_usage(
            tenant=request.auth.tenant,
            customer=customer,
            request_id=payload.request_id,
            idempotency_key=payload.idempotency_key,
            event_type=payload.event_type or None,
            provider=payload.provider or None,
            usage_metrics=payload.usage_metrics or None,
            group=payload.group,
            run_id=payload.run_id,
            pricing_card=payload.pricing_card,
        )
    except HardStopExceeded as e:
        # ... unchanged ...
    except RunNotActive as e:
        # ... unchanged ...
    except PricingError as e:
        from ninja.errors import HttpError
        raise HttpError(422, str(e))
    except ValueError as e:
        from ninja.errors import HttpError
        raise HttpError(422, str(e))
    return result
```

- [ ] **Step 7: Run all tests**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest --tb=short -q`

Expected: ALL PASS

- [ ] **Step 8: Commit**

```
feat(api): update card/rate schemas and endpoints for slug-based model
```

---

## Task 7: Dashboard Endpoints — Stats, Charts, Customers

**Files:**
- Modify: `api/v1/platform_endpoints.py`
- Modify: `api/v1/schemas.py`
- Create: `api/v1/tests/test_dashboard_endpoints.py`

- [ ] **Step 1: Add dashboard schemas to api/v1/schemas.py**

```python
class DashboardStatsResponse(Schema):
    revenue_micros: int
    api_costs_micros: int
    gross_margin_micros: int
    margin_percentage: float
    cost_per_dollar_revenue: float
    revenue_prev_change: float
    costs_prev_change: float
    margin_prev_change: float
    margin_pct_prev_change: float
    cost_per_rev_prev_change: float
    sparklines: dict  # {revenue: int[], api_costs: int[], gross_margin: int[], margin_pct: float[], cost_per_rev: float[]}


class DailyChartPoint(Schema):
    date: str
    revenue_micros: int
    api_costs_micros: int
    margin_micros: int


class StackedSeriesInfo(Schema):
    key: str
    label: str


class GroupBreakdown(Schema):
    key: str
    label: str
    value_micros: int
    percentage: float


class DashboardChartsResponse(Schema):
    revenue_time_series: list[DailyChartPoint]
    cost_by_group: dict  # {series: [{key, label}], data: [{date, group_a: N, group_b: N, ...}]}
    cost_by_card: dict   # same shape — stacked daily series per card
    revenue_by_group: list[GroupBreakdown]
    margin_by_group: list[GroupBreakdown]


class DashboardCustomerRow(Schema):
    customer_id: str
    external_id: str
    revenue_micros: int
    api_costs_micros: int
    margin_micros: int
    margin_percentage: float
    event_count: int


class DashboardCustomersResponse(Schema):
    customers: list[DashboardCustomerRow]
```

- [ ] **Step 2: Write failing tests**

Create `api/v1/tests/test_dashboard_endpoints.py`:

```python
from datetime import timedelta
from django.test import TestCase, Client
from django.utils import timezone
from apps.platform.tenants.models import Tenant, TenantApiKey
from apps.platform.customers.models import Customer
from apps.platform.groups.models import Group
from apps.metering.pricing.models import Card, Rate
from apps.metering.usage.models import UsageEvent


def _create_event(tenant, customer, card, days_ago=0, billed=1000, provider_cost=800, group=None):
    """Helper to create a usage event with specific effective_at."""
    event = UsageEvent(
        tenant=tenant,
        customer=customer,
        request_id=f"req_{timezone.now().timestamp()}_{days_ago}",
        idempotency_key=f"idem_{timezone.now().timestamp()}_{days_ago}",
        cost_micros=billed,
        event_type=card.event_type if card else "",
        provider=card.provider if card else "",
        provider_cost_micros=provider_cost,
        billed_cost_micros=billed,
        card=card,
        group=group,
    )
    # Bypass auto_now_add to set custom effective_at
    event.save()
    if days_ago > 0:
        target = timezone.now() - timedelta(days=days_ago)
        UsageEvent.objects.filter(id=event.id).update(effective_at=target)
    return event


class DashboardStatsTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Test", products=["metering"])
        self.api_key = TenantApiKey.objects.create(tenant=self.tenant)
        self.client = Client()
        self.headers = {"HTTP_AUTHORIZATION": f"Bearer {self.api_key.raw_key}"}
        self.customer = Customer.objects.create(tenant=self.tenant, external_id="c1")
        self.card = Card.objects.create(
            tenant=self.tenant, name="Test Card", slug="test_card",
            provider="test", event_type="test",
        )

    def test_stats_endpoint_returns_200(self):
        _create_event(self.tenant, self.customer, self.card, days_ago=5, billed=10_000, provider_cost=7_000)
        resp = self.client.get("/api/v1/platform/dashboard/stats?range=30d", **self.headers)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["revenue_micros"], 10_000)
        self.assertEqual(data["api_costs_micros"], 7_000)
        self.assertEqual(data["gross_margin_micros"], 3_000)

    def test_stats_empty_returns_zeros(self):
        resp = self.client.get("/api/v1/platform/dashboard/stats?range=30d", **self.headers)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["revenue_micros"], 0)


class DashboardChartsTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Test", products=["metering"])
        self.api_key = TenantApiKey.objects.create(tenant=self.tenant)
        self.client = Client()
        self.headers = {"HTTP_AUTHORIZATION": f"Bearer {self.api_key.raw_key}"}
        self.customer = Customer.objects.create(tenant=self.tenant, external_id="c1")
        self.card = Card.objects.create(
            tenant=self.tenant, name="Card", slug="card",
            provider="test", event_type="test",
        )

    def test_charts_endpoint_returns_200(self):
        resp = self.client.get("/api/v1/platform/dashboard/charts?range=30d", **self.headers)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("revenue_time_series", data)
        self.assertIn("cost_by_group", data)

    def test_cost_by_group_stacked_series_shape(self):
        """cost_by_group returns {series: [...], data: [{date, group_key: value, ...}]}."""
        _create_event(self.tenant, self.customer, self.card, days_ago=1, billed=5000, provider_cost=3000, group="research")
        _create_event(self.tenant, self.customer, self.card, days_ago=1, billed=3000, provider_cost=2000, group="chat")
        resp = self.client.get("/api/v1/platform/dashboard/charts?range=7d", **self.headers)
        data = resp.json()
        cbg = data["cost_by_group"]
        self.assertIn("series", cbg)
        self.assertIn("data", cbg)
        # series should list each group
        series_keys = {s["key"] for s in cbg["series"]}
        self.assertIn("research", series_keys)
        self.assertIn("chat", series_keys)
        # data rows should have date + dynamic group keys
        self.assertTrue(len(cbg["data"]) > 0)
        row = cbg["data"][0]
        self.assertIn("date", row)


class DashboardCustomersTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Test", products=["metering"])
        self.api_key = TenantApiKey.objects.create(tenant=self.tenant)
        self.client = Client()
        self.headers = {"HTTP_AUTHORIZATION": f"Bearer {self.api_key.raw_key}"}
        self.customer = Customer.objects.create(tenant=self.tenant, external_id="acme")
        self.card = Card.objects.create(
            tenant=self.tenant, name="Card", slug="card",
            provider="test", event_type="test",
        )

    def test_customers_endpoint_returns_data(self):
        _create_event(self.tenant, self.customer, self.card, billed=50_000, provider_cost=30_000)
        resp = self.client.get("/api/v1/platform/dashboard/customers?range=30d", **self.headers)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(len(data["customers"]), 1)
        self.assertEqual(data["customers"][0]["external_id"], "acme")
        self.assertEqual(data["customers"][0]["revenue_micros"], 50_000)
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest api/v1/tests/test_dashboard_endpoints.py -v --tb=short`

Expected: FAIL — endpoints don't exist.

- [ ] **Step 4: Implement dashboard endpoints**

Add to `api/v1/platform_endpoints.py`:

```python
from datetime import date, timedelta
from django.db.models import Sum, Count, F
from django.db.models.functions import Coalesce, TruncDate
from apps.metering.usage.models import UsageEvent


def _parse_range(range_str: str):
    """Return (start_date, end_date, prev_start, prev_end) for the given range."""
    today = date.today()
    if range_str == "7d":
        start = today - timedelta(days=7)
        prev_start = start - timedelta(days=7)
    elif range_str == "90d":
        start = today - timedelta(days=90)
        prev_start = start - timedelta(days=90)
    elif range_str == "YTD":
        start = date(today.year, 1, 1)
        prev_start = date(today.year - 1, 1, 1)
    else:  # default 30d
        start = today - timedelta(days=30)
        prev_start = start - timedelta(days=30)
    return start, today, prev_start, start - timedelta(days=1)


def _pct_change(current, previous):
    if previous == 0:
        return 0.0 if current == 0 else 100.0
    return round((current - previous) / abs(previous) * 100, 1)


@platform_api.get("/dashboard/stats")
def dashboard_stats(request, range: str = "30d"):
    tenant = request.auth.tenant
    start, end, prev_start, prev_end = _parse_range(range)

    effective_billed = Coalesce("billed_cost_micros", "cost_micros")

    def _agg(qs):
        result = qs.aggregate(
            revenue=Coalesce(Sum(effective_billed), 0),
            costs=Coalesce(Sum("provider_cost_micros"), 0),
            count=Count("id"),
        )
        return result

    base_qs = UsageEvent.objects.filter(tenant=tenant)
    current = _agg(base_qs.filter(effective_at__date__gte=start, effective_at__date__lte=end))
    prev = _agg(base_qs.filter(effective_at__date__gte=prev_start, effective_at__date__lte=prev_end))

    revenue = current["revenue"]
    costs = current["costs"]
    margin = revenue - costs
    margin_pct = round(margin / revenue * 100, 1) if revenue else 0.0
    cost_per_rev = round(costs / revenue, 4) if revenue else 0.0

    prev_revenue = prev["revenue"]
    prev_costs = prev["costs"]
    prev_margin = prev_revenue - prev_costs
    prev_margin_pct = round(prev_margin / prev_revenue * 100, 1) if prev_revenue else 0.0
    prev_cost_per_rev = round(prev_costs / prev_revenue, 4) if prev_revenue else 0.0

    # Sparklines: daily values for the current period
    daily_qs = (
        base_qs.filter(effective_at__date__gte=start, effective_at__date__lte=end)
        .annotate(day=TruncDate("effective_at"))
        .values("day")
        .annotate(
            rev=Coalesce(Sum(effective_billed), 0),
            cost=Coalesce(Sum("provider_cost_micros"), 0),
        )
        .order_by("day")
    )
    sparkline_rev = [d["rev"] for d in daily_qs]
    sparkline_cost = [d["cost"] for d in daily_qs]
    sparkline_margin = [d["rev"] - d["cost"] for d in daily_qs]
    sparkline_margin_pct = [
        round((d["rev"] - d["cost"]) / d["rev"] * 100, 1) if d["rev"] else 0.0
        for d in daily_qs
    ]
    sparkline_cost_per_rev = [
        round(d["cost"] / d["rev"], 4) if d["rev"] else 0.0
        for d in daily_qs
    ]

    return {
        "revenue_micros": revenue,
        "api_costs_micros": costs,
        "gross_margin_micros": margin,
        "margin_percentage": margin_pct,
        "cost_per_dollar_revenue": cost_per_rev,
        "revenue_prev_change": _pct_change(revenue, prev_revenue),
        "costs_prev_change": _pct_change(costs, prev_costs),
        "margin_prev_change": _pct_change(margin, prev_margin),
        "margin_pct_prev_change": round(margin_pct - prev_margin_pct, 1),
        "cost_per_rev_prev_change": round(cost_per_rev - prev_cost_per_rev, 4),
        "sparklines": {
            "revenue": sparkline_rev,
            "api_costs": sparkline_cost,
            "gross_margin": sparkline_margin,
            "margin_pct": sparkline_margin_pct,
            "cost_per_rev": sparkline_cost_per_rev,
        },
    }


@platform_api.get("/dashboard/charts")
def dashboard_charts(request, range: str = "30d"):
    tenant = request.auth.tenant
    start, end, _, _ = _parse_range(range)
    effective_billed = Coalesce("billed_cost_micros", "cost_micros")

    base_qs = UsageEvent.objects.filter(
        tenant=tenant, effective_at__date__gte=start, effective_at__date__lte=end,
    )

    # Revenue time series (aggregate daily)
    time_series = list(
        base_qs.annotate(day=TruncDate("effective_at"))
        .values("day")
        .annotate(
            revenue_micros=Coalesce(Sum(effective_billed), 0),
            api_costs_micros=Coalesce(Sum("provider_cost_micros"), 0),
        )
        .order_by("day")
    )
    for row in time_series:
        row["date"] = row.pop("day").isoformat()
        row["margin_micros"] = row["revenue_micros"] - row["api_costs_micros"]

    # --- Stacked daily series builder ---
    def _build_stacked_series(qs, key_field, label_field=None):
        """Build {series: [{key, label}], data: [{date, key_a: N, key_b: N}]}.
        
        This is the shape Recharts needs for stacked area/bar charts.
        """
        label_field = label_field or key_field
        # Get all distinct keys
        daily_rows = list(
            qs.annotate(day=TruncDate("effective_at"))
            .values("day", key_field)
            .annotate(value=Coalesce(Sum(effective_billed), 0))
            .order_by("day")
        )
        # Collect unique keys for series definition
        keys_seen = {}
        for r in daily_rows:
            k = r[key_field] or "ungrouped"
            if k not in keys_seen:
                keys_seen[k] = k  # label defaults to key
        # If we have label_field, look up labels
        if label_field != key_field:
            label_rows = list(
                qs.filter(**{f"{key_field}__isnull": False})
                .values(key_field, label_field).distinct()
            )
            for lr in label_rows:
                k = lr[key_field]
                if k in keys_seen:
                    keys_seen[k] = lr[label_field]
        
        series = [{"key": k, "label": v} for k, v in keys_seen.items()]
        
        # Pivot: group by date, each key becomes a column
        date_map = {}
        for r in daily_rows:
            d = r["day"].isoformat()
            k = r[key_field] or "ungrouped"
            if d not in date_map:
                date_map[d] = {"date": d}
            date_map[d][k] = r["value"]
        
        # Ensure all keys present in every row (default 0)
        data = []
        for d in sorted(date_map.keys()):
            row = date_map[d]
            for s in series:
                row.setdefault(s["key"], 0)
            data.append(row)
        
        return {"series": series, "data": data}

    cost_by_group = _build_stacked_series(base_qs, "group")
    cost_by_card = _build_stacked_series(
        base_qs.filter(card__isnull=False), "card__slug", "card__name"
    )

    # Aggregate breakdowns for pie charts
    total_revenue = base_qs.aggregate(t=Coalesce(Sum(effective_billed), 0))["t"]

    revenue_by_group = list(
        base_qs.values("group")
        .annotate(
            value_micros=Coalesce(Sum(effective_billed), 0),
            cost_micros=Coalesce(Sum("provider_cost_micros"), 0),
        )
        .order_by("-value_micros")
    )

    return {
        "revenue_time_series": time_series,
        "cost_by_group": cost_by_group,
        "cost_by_card": cost_by_card,
        "revenue_by_group": [
            {
                "key": r["group"] or "ungrouped",
                "label": r["group"] or "ungrouped",
                "value_micros": r["value_micros"],
                "percentage": round(r["value_micros"] / total_revenue * 100, 1) if total_revenue else 0.0,
            }
            for r in revenue_by_group
        ],
        "margin_by_group": [
            {
                "key": r["group"] or "ungrouped",
                "label": r["group"] or "ungrouped",
                "value_micros": r["value_micros"] - r["cost_micros"],
                "percentage": round(
                    (r["value_micros"] - r["cost_micros"]) / total_revenue * 100, 1
                ) if total_revenue else 0.0,
            }
            for r in revenue_by_group
        ],
    }


@platform_api.get("/dashboard/customers")
def dashboard_customers(request, range: str = "30d"):
    tenant = request.auth.tenant
    start, end, _, _ = _parse_range(range)
    effective_billed = Coalesce("billed_cost_micros", "cost_micros")

    rows = list(
        UsageEvent.objects.filter(
            tenant=tenant, effective_at__date__gte=start, effective_at__date__lte=end,
        )
        .values("customer_id", "customer__external_id")
        .annotate(
            revenue_micros=Coalesce(Sum(effective_billed), 0),
            api_costs_micros=Coalesce(Sum("provider_cost_micros"), 0),
            event_count=Count("id"),
        )
        .order_by("-revenue_micros")[:50]
    )

    return {
        "customers": [
            {
                "customer_id": str(r["customer_id"]),
                "external_id": r["customer__external_id"],
                "revenue_micros": r["revenue_micros"],
                "api_costs_micros": r["api_costs_micros"],
                "margin_micros": r["revenue_micros"] - r["api_costs_micros"],
                "margin_percentage": (
                    round((r["revenue_micros"] - r["api_costs_micros"]) / r["revenue_micros"] * 100, 1)
                    if r["revenue_micros"] else 0.0
                ),
                "event_count": r["event_count"],
            }
            for r in rows
        ],
    }
```

- [ ] **Step 5: Run dashboard tests**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest api/v1/tests/test_dashboard_endpoints.py -v --tb=short`

Expected: ALL PASS

- [ ] **Step 6: Commit**

```
feat(api): add dashboard stats, charts, customers endpoints
```

---

## Task 8: Events Endpoints — List, Filter Options, Push, Audit Trail

**Files:**
- Modify: `api/v1/platform_endpoints.py`
- Modify: `api/v1/schemas.py`
- Create: `api/v1/tests/test_event_endpoints.py`

- [ ] **Step 1: Add event schemas to api/v1/schemas.py**

```python
class EventFilterOptionsResponse(Schema):
    customers: list[dict]  # [{key, event_count}]
    groups: list[dict]
    cards: list[dict]
    ungrouped_count: int
    card_dimensions: dict  # {card_slug: [metric_name, ...]} — which metrics each card prices
    dimension_prices: dict  # {metric_name: {cost_per_unit_micros, unit_quantity, pricing_type}}


class EventOut(Schema):
    id: str
    effective_at: str
    customer_id: str
    customer_external_id: str
    group: Optional[str] = None
    card_id: Optional[str] = None
    card_slug: Optional[str] = None
    card_name: Optional[str] = None
    event_type: str
    provider: str
    usage_metrics: dict
    provider_cost_micros: Optional[int] = None
    billed_cost_micros: Optional[int] = None


class EventsListRequest(Schema):
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    customer_id: Optional[str] = None
    group: Optional[str] = None
    card_slug: Optional[str] = None
    cursor: Optional[str] = None
    limit: int = 50


class EventsListResponse(Schema):
    events: list[EventOut]
    total_count: int
    total_cost_micros: int  # sum of billed_cost_micros across filtered events
    next_cursor: Optional[str] = None
    has_more: bool


class StagedEventIn(Schema):
    customer_external_id: str = Field(min_length=1)
    pricing_card: str = Field(min_length=1)
    group: str = ""
    usage_metrics: dict[str, int]
    idempotency_key: Optional[str] = None


class PushEventsRequest(Schema):
    events: list[StagedEventIn]
    reason: str = ""


class PushEventsResponse(Schema):
    pushed_count: int
    batch_id: str


class EventBatchOut(Schema):
    id: str
    action: str
    reason: str
    row_count: int
    author: str
    created_at: str
    reversed_at: Optional[str] = None
```

- [ ] **Step 2: Write failing tests**

Create `api/v1/tests/test_event_endpoints.py`:

```python
import json
from django.test import TestCase, Client
from apps.platform.tenants.models import Tenant, TenantApiKey
from apps.platform.customers.models import Customer
from apps.metering.pricing.models import Card, Rate
from apps.metering.usage.models import UsageEvent


class EventFilterOptionsTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Test", products=["metering"])
        self.api_key = TenantApiKey.objects.create(tenant=self.tenant)
        self.client = Client()
        self.headers = {"HTTP_AUTHORIZATION": f"Bearer {self.api_key.raw_key}"}

    def test_filter_options_empty(self):
        resp = self.client.get("/api/v1/platform/events/filter-options", **self.headers)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["customers"], [])
        self.assertEqual(data["ungrouped_count"], 0)


class EventsListTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Test", products=["metering"])
        self.api_key = TenantApiKey.objects.create(tenant=self.tenant)
        self.client = Client()
        self.headers = {"HTTP_AUTHORIZATION": f"Bearer {self.api_key.raw_key}"}
        self.customer = Customer.objects.create(tenant=self.tenant, external_id="acme")
        self.card = Card.objects.create(
            tenant=self.tenant, name="Card", slug="test_card",
            provider="test", event_type="test",
        )

    def test_list_events(self):
        UsageEvent.objects.create(
            tenant=self.tenant, customer=self.customer,
            request_id="r1", idempotency_key="i1", cost_micros=1000,
            card=self.card, usage_metrics={"tokens": 100},
        )
        resp = self.client.post(
            "/api/v1/platform/events/list",
            data=json.dumps({}),
            content_type="application/json",
            **self.headers,
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(len(data["events"]), 1)
        self.assertEqual(data["events"][0]["card_slug"], "test_card")
        self.assertEqual(data["events"][0]["customer_external_id"], "acme")


class EventsPushTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Test", products=["metering"])
        self.api_key = TenantApiKey.objects.create(tenant=self.tenant)
        self.client = Client()
        self.headers = {"HTTP_AUTHORIZATION": f"Bearer {self.api_key.raw_key}"}
        self.customer = Customer.objects.create(tenant=self.tenant, external_id="acme")
        self.card = Card.objects.create(
            tenant=self.tenant, name="Gemini Flash", slug="gemini_flash",
            provider="google", event_type="llm_call",
        )
        Rate.objects.create(
            card=self.card, metric_name="input_tokens",
            pricing_type="per_unit", cost_per_unit_micros=75_000, unit_quantity=1_000_000,
        )

    def test_push_events(self):
        resp = self.client.post(
            "/api/v1/platform/events/push",
            data=json.dumps({
                "events": [
                    {
                        "customer_external_id": "acme",
                        "pricing_card": "gemini_flash",
                        "group": "research",
                        "usage_metrics": {"input_tokens": 1000},
                    }
                ],
                "reason": "Monthly import",
            }),
            content_type="application/json",
            **self.headers,
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["pushed_count"], 1)
        self.assertTrue(data["batch_id"])
        # Verify event created
        self.assertEqual(UsageEvent.objects.filter(tenant=self.tenant).count(), 1)


class AuditTrailTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Test", products=["metering"])
        self.api_key = TenantApiKey.objects.create(tenant=self.tenant)
        self.client = Client()
        self.headers = {"HTTP_AUTHORIZATION": f"Bearer {self.api_key.raw_key}"}

    def test_audit_trail_empty(self):
        resp = self.client.get("/api/v1/platform/events/audit-trail", **self.headers)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), [])
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest api/v1/tests/test_event_endpoints.py -v --tb=short`

Expected: FAIL — endpoints don't exist.

- [ ] **Step 4: Implement event endpoints**

Add to `api/v1/platform_endpoints.py`:

```python
import uuid as _uuid
from apps.metering.usage.models import UsageEvent, EventBatch
from apps.metering.usage.services.usage_service import UsageService


@platform_api.get("/events/filter-options")
def event_filter_options(request):
    tenant = request.auth.tenant
    base_qs = UsageEvent.objects.filter(tenant=tenant)

    customers = list(
        base_qs.values("customer__external_id")
        .annotate(event_count=Count("id"))
        .order_by("-event_count")
    )
    groups = list(
        base_qs.exclude(group__isnull=True).exclude(group="")
        .values("group")
        .annotate(event_count=Count("id"))
        .order_by("-event_count")
    )
    cards = list(
        base_qs.filter(card__isnull=False)
        .values("card__slug")
        .annotate(event_count=Count("id"))
        .order_by("-event_count")
    )
    ungrouped = base_qs.filter(models.Q(group__isnull=True) | models.Q(group="")).count()

    # Card dimensions: which metric_names each active card has
    from apps.metering.pricing.models import Card, Rate
    active_cards = Card.objects.filter(
        tenant=tenant, status__in=["active", "draft"],
    ).prefetch_related("rates")

    card_dimensions = {}
    dimension_prices = {}
    for card in active_cards:
        active_rates = card.rates.filter(valid_to__isnull=True)
        card_dimensions[card.slug] = [r.metric_name for r in active_rates]
        for r in active_rates:
            dimension_prices[r.metric_name] = {
                "cost_per_unit_micros": r.cost_per_unit_micros,
                "unit_quantity": r.unit_quantity,
                "pricing_type": r.pricing_type,
            }

    return {
        "customers": [{"key": c["customer__external_id"], "event_count": c["event_count"]} for c in customers],
        "groups": [{"key": g["group"], "event_count": g["event_count"]} for g in groups],
        "cards": [{"key": c["card__slug"], "event_count": c["event_count"]} for c in cards],
        "ungrouped_count": ungrouped,
        "card_dimensions": card_dimensions,
        "dimension_prices": dimension_prices,
    }


@platform_api.post("/events/list")
def list_events(request, payload: EventsListRequest):
    tenant = request.auth.tenant
    limit = min(max(payload.limit, 1), 100)

    qs = UsageEvent.objects.filter(tenant=tenant).select_related("customer", "card").order_by("-effective_at", "-id")

    if payload.date_from:
        qs = qs.filter(effective_at__date__gte=payload.date_from)
    if payload.date_to:
        qs = qs.filter(effective_at__date__lte=payload.date_to)
    if payload.customer_id:
        qs = qs.filter(customer_id=payload.customer_id)
    if payload.group:
        qs = qs.filter(group=payload.group)
    if payload.card_slug:
        qs = qs.filter(card__slug=payload.card_slug)

    if payload.cursor:
        try:
            qs = apply_cursor_filter(qs, payload.cursor)
        except ValueError:
            from ninja.errors import HttpError
            raise HttpError(400, "Invalid cursor")

    # Aggregate total cost across the full filtered set (before pagination)
    from django.db.models.functions import Coalesce
    agg = qs.aggregate(
        total_count=Count("id"),
        total_cost_micros=Coalesce(Sum(Coalesce("billed_cost_micros", "cost_micros")), 0),
    )
    total_count = agg["total_count"]
    total_cost_micros = agg["total_cost_micros"]

    events = list(qs[:limit + 1])
    has_more = len(events) > limit
    events = events[:limit]

    next_cursor = None
    if has_more and events:
        last = events[-1]
        next_cursor = encode_cursor(last.effective_at, last.id)

    return {
        "events": [
            {
                "id": str(e.id),
                "effective_at": e.effective_at.isoformat(),
                "customer_id": str(e.customer_id),
                "customer_external_id": e.customer.external_id,
                "group": e.group,
                "card_id": str(e.card_id) if e.card_id else None,
                "card_slug": e.card.slug if e.card_id else None,
                "card_name": e.card.name if e.card_id else None,
                "event_type": e.event_type,
                "provider": e.provider,
                "usage_metrics": e.usage_metrics,
                "provider_cost_micros": e.provider_cost_micros,
                "billed_cost_micros": e.billed_cost_micros,
            }
            for e in events
        ],
        "total_count": total_count,
        "total_cost_micros": total_cost_micros,
        "next_cursor": next_cursor,
        "has_more": has_more,
    }


@platform_api.post("/events/push")
def push_events(request, payload: PushEventsRequest):
    tenant = request.auth.tenant
    author = getattr(request, "tenant_user", None)
    author_str = str(author) if author else "api_key"

    batch = EventBatch.objects.create(
        tenant=tenant,
        action="added",
        reason=payload.reason,
        row_count=len(payload.events),
        author=author_str,
    )

    pushed = 0
    for i, staged in enumerate(payload.events):
        customer = Customer.objects.filter(
            tenant=tenant, external_id=staged.customer_external_id,
        ).first()
        if customer is None:
            continue  # skip unknown customers

        idem_key = staged.idempotency_key or f"batch_{batch.id}_{i}"

        try:
            result = UsageService.record_usage(
                tenant=tenant,
                customer=customer,
                request_id=f"batch_{batch.id}_{i}",
                idempotency_key=idem_key,
                pricing_card=staged.pricing_card,
                usage_metrics=staged.usage_metrics,
                group=staged.group or None,
            )
            # Link event to batch
            UsageEvent.objects.filter(id=result["event_id"]).update(batch=batch)
            pushed += 1
        except Exception:
            continue  # skip failed events, could enhance with error collection

    batch.row_count = pushed
    batch.save(update_fields=["row_count", "updated_at"])

    return {"pushed_count": pushed, "batch_id": str(batch.id)}


@platform_api.get("/events/audit-trail")
def event_audit_trail(request):
    tenant = request.auth.tenant
    batches = EventBatch.objects.filter(tenant=tenant).order_by("-created_at")[:50]
    return [
        {
            "id": str(b.id),
            "action": b.action,
            "reason": b.reason,
            "row_count": b.row_count,
            "author": b.author,
            "created_at": b.created_at.isoformat(),
            "reversed_at": b.reversed_at.isoformat() if b.reversed_at else None,
        }
        for b in batches
    ]


@platform_api.post("/events/audit-trail/{batch_id}/reverse")
def reverse_audit_entry(request, batch_id: str):
    from apps.metering.usage.models import Refund

    tenant = request.auth.tenant
    batch = get_object_or_404(EventBatch, id=batch_id, tenant=tenant)

    if batch.reversed_at:
        from ninja.errors import HttpError
        raise HttpError(400, "Batch already reversed")

    events = UsageEvent.objects.filter(batch=batch)
    for event in events:
        if not hasattr(event, "refund"):
            Refund.objects.create(
                tenant=tenant,
                customer=event.customer,
                usage_event=event,
                amount_micros=event.billed_cost_micros or event.cost_micros,
                reason=f"Batch reversal: {batch.reason}",
            )

    batch.reversed_at = timezone.now()
    batch.save(update_fields=["reversed_at", "updated_at"])
    return {"status": "reversed", "batch_id": str(batch.id)}
```

Add the necessary imports at the top of the file: `from django.db import models`, `from django.db.models import Sum, Count`, and `from django.utils import timezone`.

- [ ] **Step 5: Add export endpoint**

Add to `api/v1/platform_endpoints.py`:

```python
import csv
import io
from django.http import HttpResponse


@platform_api.post("/events/export")
def export_events(request, payload: EventsListRequest):
    """Export filtered events as CSV. Synchronous for now; async via Celery for large sets later."""
    tenant = request.auth.tenant

    qs = UsageEvent.objects.filter(tenant=tenant).select_related("customer", "card").order_by("-effective_at")

    if payload.date_from:
        qs = qs.filter(effective_at__date__gte=payload.date_from)
    if payload.date_to:
        qs = qs.filter(effective_at__date__lte=payload.date_to)
    if payload.customer_id:
        qs = qs.filter(customer_id=payload.customer_id)
    if payload.group:
        qs = qs.filter(group=payload.group)
    if payload.card_slug:
        qs = qs.filter(card__slug=payload.card_slug)

    # Cap at 50k rows for sync export
    events = qs[:50_000]

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "id", "effective_at", "customer_external_id", "group",
        "card_slug", "event_type", "provider", "usage_metrics",
        "provider_cost_micros", "billed_cost_micros",
    ])
    for e in events:
        writer.writerow([
            str(e.id),
            e.effective_at.isoformat(),
            e.customer.external_id,
            e.group or "",
            e.card.slug if e.card_id else "",
            e.event_type,
            e.provider,
            str(e.usage_metrics),
            e.provider_cost_micros,
            e.billed_cost_micros,
        ])

    response = HttpResponse(output.getvalue(), content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="events_export.csv"'
    return response
```

- [ ] **Step 6: Run event endpoint tests**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest api/v1/tests/test_event_endpoints.py -v --tb=short`

Expected: ALL PASS

- [ ] **Step 7: Run full test suite**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest --tb=short -q`

Expected: ALL PASS — no regressions.

- [ ] **Step 8: Commit**

```
feat(api): add events list, filter-options, push, audit-trail, export endpoints
```

---

## Task 9: CamelCase Response Middleware

The UI expects camelCase keys (`revenueMicros`, `eventType`, `cardSlug`). The API returns snake_case (`revenue_micros`, `event_type`, `card_slug`). Rather than maintaining separate naming in every endpoint or transforming in the UI, we add a response middleware that converts all JSON response keys from snake_case to camelCase. The same middleware converts incoming camelCase request keys to snake_case.

This is the standard approach used by django-ninja and DRF projects that serve JavaScript frontends.

**Files:**
- Create: `api/v1/middleware.py`
- Modify: `api/v1/metering_endpoints.py` (apply middleware)
- Modify: `api/v1/platform_endpoints.py` (apply middleware)
- Create: `api/v1/tests/test_camel_case.py`

- [ ] **Step 1: Write failing test for camelCase transformation**

Create `api/v1/tests/test_camel_case.py`:

```python
from api.v1.middleware import to_camel_case, transform_keys


class CamelCaseTest:
    def test_simple_key(self):
        assert to_camel_case("revenue_micros") == "revenueMicros"

    def test_single_word(self):
        assert to_camel_case("id") == "id"

    def test_nested_dict(self):
        data = {
            "revenue_micros": 100,
            "nested_object": {
                "inner_key": "value",
            },
            "list_field": [
                {"item_key": 1},
            ],
        }
        result = transform_keys(data, to_camel_case)
        assert result == {
            "revenueMicros": 100,
            "nestedObject": {
                "innerKey": "value",
            },
            "listField": [
                {"itemKey": 1},
            ],
        }

    def test_preserves_non_dict_values(self):
        data = {"cost_per_unit_micros": 75000, "name": "test"}
        result = transform_keys(data, to_camel_case)
        assert result["costPerUnitMicros"] == 75000
        assert result["name"] == "test"
```

- [ ] **Step 2: Implement middleware**

Create `api/v1/middleware.py`:

```python
"""Snake-case ↔ camelCase key transformation for API responses.

Applied as django-ninja middleware on the platform and metering API instances.
Converts all JSON response keys from snake_case to camelCase so the UI
consumes data without transformation adapters.
"""

import json
import re


def to_camel_case(snake_str: str) -> str:
    """Convert snake_case to camelCase."""
    parts = snake_str.split("_")
    return parts[0] + "".join(p.capitalize() for p in parts[1:])


def to_snake_case(camel_str: str) -> str:
    """Convert camelCase to snake_case."""
    return re.sub(r"(?<=[a-z0-9])([A-Z])", r"_\1", camel_str).lower()


def transform_keys(obj, fn):
    """Recursively transform all dict keys using fn."""
    if isinstance(obj, dict):
        return {fn(k): transform_keys(v, fn) for k, v in obj.items()}
    if isinstance(obj, list):
        return [transform_keys(item, fn) for item in obj]
    return obj


class CamelCaseResponseMiddleware:
    """django-ninja middleware that converts response keys to camelCase
    and request keys to snake_case."""

    def resolve(self, next_call, **kwargs):
        # Transform incoming request body keys to snake_case
        # (handled by ninja's Schema parsing, but this catches raw dict access)
        result = next_call(**kwargs)
        return result

    def process_response(self, request, response):
        if hasattr(response, "content") and response.get("Content-Type", "").startswith("application/json"):
            try:
                data = json.loads(response.content)
                transformed = transform_keys(data, to_camel_case)
                response.content = json.dumps(transformed)
            except (json.JSONDecodeError, ValueError):
                pass
        return response
```

Note: The exact middleware integration depends on django-ninja's version. An alternative approach is to use a custom renderer or override the `NinjaAPI.create_response` method. The implementer should check which pattern works best with the project's ninja version. A simpler approach that always works:

```python
# In each NinjaAPI instance, add a custom renderer:
import orjson  # or json

class CamelCaseRenderer:
    media_type = "application/json"
    
    def render(self, request, data, *, response_status):
        transformed = transform_keys(data, to_camel_case)
        return json.dumps(transformed)

# Then: metering_api = NinjaAPI(..., renderer=CamelCaseRenderer())
```

- [ ] **Step 3: Apply to API instances**

In `api/v1/metering_endpoints.py`:

```python
from api.v1.middleware import CamelCaseRenderer

metering_api = NinjaAPI(auth=ApiKeyAuth(), urls_namespace="ubb_metering_v1", renderer=CamelCaseRenderer())
```

In `api/v1/platform_endpoints.py`:

```python
from api.v1.middleware import CamelCaseRenderer

platform_api = NinjaAPI(auth=[ApiKeyAuth(), ClerkJWTAuth()], urls_namespace="ubb_platform_v1", renderer=CamelCaseRenderer())
```

- [ ] **Step 4: Run tests — verify camelCase in responses**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest api/v1/tests/ -v --tb=short`

Expected: ALL PASS. Note that test assertions for response keys will now need to use camelCase (e.g., `data["revenueMicros"]` instead of `data["revenue_micros"]`). Update test assertions in Tasks 7 and 8 accordingly during implementation.

**Important:** If the CamelCaseRenderer approach causes issues with django-ninja's built-in Schema validation, an alternative is to apply the transform at the endpoint level using a decorator. The implementer should pick the approach that integrates cleanly.

- [ ] **Step 5: Commit**

```
feat(api): add camelCase response middleware for UI consumption
```

---

## Task 10: Final Integration — Full Test Run + Verify Existing Tests

**Files:** None — verification only.

- [ ] **Step 1: Run full platform test suite**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest --tb=short -q`

Expected: ≥521 tests passing, 0 failures.

- [ ] **Step 2: Verify existing pricing service tests still pass**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/metering/pricing/tests/ -v --tb=short`

Expected: ALL PASS — attribute-based tests unchanged, slug-based tests added.

- [ ] **Step 3: Verify existing usage service tests still pass**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/metering/usage/tests/ -v --tb=short`

Expected: ALL PASS — legacy `cost_micros` path and `event_type+provider` path both work.

- [ ] **Step 4: Verify camelCase in API responses**

Run a quick manual check:
```bash
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -c "
from api.v1.middleware import to_camel_case, transform_keys
data = {'revenue_micros': 100, 'cost_by_group': {'series': [{'key': 'a'}]}}
print(transform_keys(data, to_camel_case))
"
```

Expected: `{'revenueMicros': 100, 'costByGroup': {'series': [{'key': 'a'}]}}`

- [ ] **Step 5: Commit all work**

```
feat(metering): complete API-UI alignment — models, endpoints, slug-based pricing, camelCase
```

---

## Summary

| Task | What | Endpoints | Tests |
|------|------|-----------|-------|
| 1 | Card model: slug, group FK, draft | — | ~7 |
| 2 | Rate model: pricing_type, label, unit | — | ~6 |
| 3 | UsageEvent: card FK + EventBatch model | — | ~6 |
| 4 | PricingService: slug-based lookup | — | ~7 |
| 5 | UsageService: accept pricing_card slug | — | ~4 |
| 6 | API schemas + card CRUD + slug usage | Updated card CRUD + usage | ~4 |
| 7 | Dashboard endpoints (stacked daily series) | 3 new (stats, charts, customers) | ~5 |
| 8 | Events endpoints (with export + enriched filters) | 6 new (filter-options, list, push, audit-trail, reverse, export) | ~5 |
| 9 | CamelCase response middleware | — (cross-cutting) | ~4 |
| 10 | Full integration verification | — | Full suite |

**Total: 10 tasks, ~10 new endpoints, ~48 new tests, 4 model migrations**

### What the UI can now consume directly (no adapters)

| UI Feature | API Endpoint | Key alignment |
|---|---|---|
| Dashboard stat cards + sparklines | `GET /platform/dashboard/stats?range=30d` | camelCase, micros |
| Dashboard time series chart | `GET /platform/dashboard/charts?range=30d` → `revenueTimeSeries` | Daily points |
| Dashboard stacked area (by group) | Same → `costByGroup.series` + `costByGroup.data` | Recharts-ready shape |
| Dashboard stacked area (by card) | Same → `costByCard.series` + `costByCard.data` | Recharts-ready shape |
| Dashboard pie charts | Same → `revenueByGroup`, `marginByGroup` | Breakdown arrays |
| Dashboard customer table | `GET /platform/dashboard/customers?range=30d` | Per-customer rollups |
| Events filter bar | `GET /platform/events/filter-options` | Faceted counts + cardDimensions + dimensionPrices |
| Events table | `POST /platform/events/list` | Paginated, filtered, totalCostMicros |
| Events push | `POST /platform/events/push` | Bulk via card slug |
| Events audit trail | `GET /platform/events/audit-trail` | Batch history |
| Events undo | `POST /platform/events/audit-trail/{id}/reverse` | Refund-based |
| Events CSV export | `POST /platform/events/export` | Direct CSV download |
| Pricing card list | `GET /metering/pricing/cards` | slug, rates, group, draft |
| Pricing card create | `POST /metering/pricing/cards` | Full create with rates |
| Pricing card CRUD | PATCH/DELETE existing | slug, group_id, pricing_source_url |
| SDK usage recording | `POST /metering/usage` | `pricingCard` slug lookup |
