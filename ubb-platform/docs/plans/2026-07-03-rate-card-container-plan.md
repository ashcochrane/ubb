# RateCard Container (Rate + RateCard two-level pricing) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Introduce a `RateCard` container that groups per-metric `Rate`s (today's misnamed `RateCard`), enabling atomic multi-metric repricing and per-customer book assignment.

**Architecture:** Rename today's per-metric `RateCard` model to `Rate` (Python-only, table unchanged). Add a `RateCard` container model + `RateCardAssignment`, and `rate_card` / `book_version_*` columns on `Rate`. Rewrite `PricingService._resolve_card` to resolve within a customer's assigned book, falling back to the tenant's per-provider default book. Add a transactional `publish()` that reprices a book's rates atomically. Backfill every existing rate into per-provider default books.

**Tech Stack:** Django 6.0, django-ninja, PostgreSQL, pytest. Run tests with `DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest --tb=short -q` from `ubb-platform/`.

## Global Constraints

- Python: `ubb-platform/.venv/bin/python`; always set `DJANGO_SETTINGS_MODULE=config.settings`.
- `Rate` keeps physical table `ubb_rate_card` (no destructive rename); the `RateCard` container uses a NEW table `ubb_rate_card_container`. (Naming wart: legacy table name is preserved to avoid a physical rename; the Python names are the ones that matter.)
- `Rate.lineage_id` is load-bearing for tiered marginal continuity (`PricingPeriodCounter` keys on it). NEVER change a rate's `lineage_id` on version bump.
- All money is integer micros. Currency is per-tenant single-currency (CUR-1); a card's currency must equal the tenant's `default_currency`.
- Resolution specificity is unchanged: within a candidate set, sort by `(len(dimensions), valid_from)` descending; temporal filter is `valid_from <= as_of AND (valid_to IS NULL OR valid_to > as_of)`.
- Follow existing patterns: models inherit `core.models.BaseModel` (UUID pk + timestamps); services are `@staticmethod` classes; outbox events via `apps.platform.events.outbox.write_event`.
- Commit after each task. Branch: work on the current `feat/ubb-capability-notes` branch unless told otherwise.

---

### Task 1: Rename `RateCard` → `Rate` (Python-only, behavior-preserving)

Pure mechanical rename. Table name unchanged, so the only migration is a state-only `RenameModel`. The existing test suite is the gate — no behavior changes.

**Files:**
- Modify: `apps/metering/pricing/models.py` (class `RateCard` → `Rate`; pin `db_table`)
- Create: `apps/metering/pricing/migrations/0010_rename_ratecard_to_rate.py`
- Modify (rename references): `apps/metering/pricing/services/pricing_service.py`, `apps/metering/pricing/services/tier_counter_service.py`, `apps/metering/pricing/tasks.py`, `api/v1/metering_endpoints.py`, `apps/platform/tenants/tasks.py`, `apps/platform/tenants/management/commands/seed_dev_data.py`
- Modify (test references): all files listed by the grep in Step 1 under `apps/…/tests/` and `api/v1/tests/`

**Interfaces:**
- Produces: model `Rate` (was `RateCard`) importable from `apps.metering.pricing.models`; all methods (`compute`, `compute_cumulative`, `compute_marginal`, `save`) unchanged. Module constants `CARD_TYPE_CHOICES`, `PRICING_MODEL_CHOICES`, `TIERED_PRICING_MODELS`, `validate_tiers` unchanged.

- [ ] **Step 1: Inventory every reference**

Run:
```bash
cd ubb-platform && grep -rln "RateCard" --include="*.py" apps/ api/
```
Expected: the ~28 files from the blast-radius scan. Keep this list.

**CRITICAL — rename the whole-word token `RateCard` only (`\bRateCard\b`).** This deliberately does NOT touch:
- Schema classes `RateCardIn`, `RateCardOut`, `RateCardUpdateIn`, `RateCardBatchIn` (the `In`/`Out`/… suffix means no trailing word boundary — they stay until Task 6).
- snake_case helpers/functions `_rate_card_to_out`, `create_rate_card`, `list_rate_cards`, `update_rate_card`, `bulk_create_rate_cards`, `rate_card_history` (no `RateCard` token).
- The URL string `"/pricing/rate-cards"` (hyphenated, not matched).
- **Existing migration files** `migrations/0007_ratecard.py`, `0008_ratecard_lineage_id.py`, `0009_*` — historical migrations are immutable; the new `0010` handles the state rename. Exclude them from the sweep.

- [ ] **Step 2: Rename the model class and pin the table**

In `apps/metering/pricing/models.py`, rename `class RateCard(BaseModel):` → `class Rate(BaseModel):`. Its `Meta` already sets `db_table = "ubb_rate_card"` — leave that exactly as is (this is what keeps the table stable through the rename).

- [ ] **Step 3: Word-boundary-rename references in non-test code**

In each non-test file from Step 1 (EXCLUDING migration files), rename the whole-word token `\bRateCard\b` → `Rate`. A safe sweep per file:
```bash
# preview first:
grep -nE "\bRateCard\b" <file>
# apply (macOS/BSD sed):
sed -i '' -E 's/\bRateCard\b/Rate/g' <file>
```
Key sites:
- `pricing_service.py:4` → `from apps.metering.pricing.models import Rate, TIERED_PRICING_MODELS`
- `pricing_service.py` bodies: `RateCard.objects` → `Rate.objects` (in `_resolve_card`).
- `metering_endpoints.py`: the models import and all `RateCard.objects`/`get_object_or_404(RateCard, …)` → `Rate`. The `from api.v1.schemas import RateCardIn, RateCardOut, …` line is UNCHANGED (schema names survive). Endpoint URLs and schema class names stay `rate-cards`/`RateCardOut` until Task 6.
- `tenants/tasks.py`, `tenant_endpoints.py`, `seed_dev_data.py`, `pricing/tasks.py`: same whole-word swap.

- [ ] **Step 4: Word-boundary-rename references in tests**

In each test file from Step 1, rename `\bRateCard\b` → `Rate` (imports + usages) with the same `sed` command. Do not change assertions or logic. Watch for tests that import `RateCardOut`-style schemas — those tokens are left intact by the word boundary.

- [ ] **Step 5: Create the state-only rename migration**

Create `apps/metering/pricing/migrations/0010_rename_ratecard_to_rate.py`:
```python
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("pricing", "0009_alter_ratecard_pricing_model_pricingperiodcounter"),
    ]

    # State-only: the table stays `ubb_rate_card`, so Django's model state must
    # rename WITHOUT touching the database. RenameModel would otherwise attempt a
    # table rename; db_table is pinned, but we wrap in SeparateDatabaseAndState to
    # be explicit and future-proof.
    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.RenameModel(old_name="RateCard", new_name="Rate"),
            ],
            database_operations=[],
        ),
    ]
```

- [ ] **Step 6: Verify migration state matches models**

Run:
```bash
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python manage.py makemigrations --check --dry-run
```
Expected: `No changes detected`. If Django wants a new migration, the model/migration state diverged — reconcile before continuing.

- [ ] **Step 7: Run the full suite (the rename gate)**

Run:
```bash
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/metering/ api/v1/tests/ apps/billing/tests/test_tiered_drawdown.py apps/platform/tenants/tests/ --tb=short -q
```
Expected: PASS (same count as before the rename; zero failures). A rename that keeps all tests green is correct by construction.

- [ ] **Step 8: Commit**

```bash
git add apps/metering/pricing api/v1 apps/platform/tenants apps/metering/usage/tests apps/billing/tests/test_tiered_drawdown.py
git commit -m "refactor(pricing): rename RateCard model to Rate (no behavior change)

Frees the RateCard name for the container introduced next. State-only
migration; table ubb_rate_card unchanged.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: Add `RateCard` container + `RateCardAssignment` + `Rate` membership columns

Introduce the container model, the assignment model, and the new columns on `Rate`. No resolution wiring yet — models + constraints + a schema migration only.

**Files:**
- Modify: `apps/metering/pricing/models.py` (add `RateCard`, `RateCardAssignment`; add fields to `Rate`)
- Create: `apps/metering/pricing/migrations/0011_ratecard_container.py`
- Create/Modify test: `apps/metering/pricing/tests/test_rate_card_container_model.py`

**Interfaces:**
- Produces:
  - `RateCard(BaseModel)` with fields `tenant (FK)`, `card_type (str)`, `currency (str)`, `key (str)`, `name (str)`, `version (int, default 1)`, `is_default (bool, default False)`; table `ubb_rate_card_container`.
  - `RateCardAssignment(BaseModel)` with `tenant (FK)`, `customer (FK)`, `rate_card (FK→RateCard)`, `currency (str)`.
  - `Rate` gains `rate_card (FK→RateCard, null=True)`, `book_version_from (int, default 1)`, `book_version_to (int, null=True)`.

- [ ] **Step 1: Write failing model-constraint tests**

Create `apps/metering/pricing/tests/test_rate_card_container_model.py`:
```python
import pytest
from django.db import IntegrityError
from apps.metering.pricing.models import RateCard, RateCardAssignment
from apps.platform.tenants.models import Tenant

pytestmark = pytest.mark.django_db


def _tenant():
    return Tenant.objects.create(name="T", default_currency="usd")


def test_one_default_book_per_tenant_cardtype_provider_currency():
    t = _tenant()
    RateCard.objects.create(tenant=t, card_type="price", currency="usd",
                            key="gemini", name="Gemini", is_default=True)
    # A second default book for the SAME (tenant, card_type, provider, currency)
    # must be rejected. Provider is carried by the book key convention here; the
    # DB guard is the partial unique constraint on is_default.
    with pytest.raises(IntegrityError):
        RateCard.objects.create(tenant=t, card_type="price", currency="usd",
                                key="gemini-2", name="Gemini 2", is_default=True)


def test_assignment_unique_per_customer_currency():
    from apps.platform.customers.models import Customer
    t = _tenant()
    c = Customer.objects.create(tenant=t, external_id="c1")
    book = RateCard.objects.create(tenant=t, card_type="price", currency="usd",
                                   key="ent", name="Enterprise")
    RateCardAssignment.objects.create(tenant=t, customer=c, rate_card=book, currency="usd")
    with pytest.raises(IntegrityError):
        RateCardAssignment.objects.create(tenant=t, customer=c, rate_card=book, currency="usd")
```

> NOTE on the default-book constraint: the §3 invariant is per `(tenant, card_type, provider, currency)`, but `provider` lives on the `Rate`, not the book. We encode "provider" as a required non-empty `RateCard.provider_key` column (added below) so the DB can enforce one default per provider. Update the model in Step 3 accordingly and the test's second insert uses the SAME `provider_key`.

- [ ] **Step 2: Run tests to verify they fail**

Run:
```bash
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/metering/pricing/tests/test_rate_card_container_model.py -v
```
Expected: FAIL with `ImportError: cannot import name 'RateCard'` (container not defined yet).

- [ ] **Step 3: Add the models**

In `apps/metering/pricing/models.py`, after the `Rate` class add:
```python
class RateCard(BaseModel):
    """Container grouping many Rates, versioned and assigned as a unit.

    Naming wart: the physical table is `ubb_rate_card_container` because the
    legacy `ubb_rate_card` table now backs the `Rate` model (the old, misnamed
    RateCard). The Python names are correct: RateCard = the sheet, Rate = a line.
    """
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE,
                               related_name="rate_card_containers")
    card_type = models.CharField(max_length=10, choices=CARD_TYPE_CHOICES, db_index=True)
    # provider_key pins the book to one provider so the per-provider default
    # invariant is DB-enforceable ("" is the no-provider bucket).
    provider_key = models.CharField(max_length=100, blank=True, default="")
    currency = models.CharField(max_length=3, default="usd")
    key = models.SlugField(max_length=64)
    name = models.CharField(max_length=255, blank=True, default="")
    version = models.PositiveIntegerField(default=1)
    is_default = models.BooleanField(default=False)

    class Meta:
        db_table = "ubb_rate_card_container"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "card_type", "key"], name="uq_ratecard_tenant_key"),
            models.UniqueConstraint(
                fields=["tenant", "card_type", "provider_key", "currency"],
                condition=models.Q(is_default=True),
                name="uq_ratecard_one_default_per_provider"),
        ]

    def __str__(self):
        return f"RateCard({self.key} v{self.version})"


class RateCardAssignment(BaseModel):
    """A customer's assigned PRICE book (one per customer per currency)."""
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE,
                               related_name="rate_card_assignments")
    customer = models.ForeignKey("customers.Customer", on_delete=models.CASCADE,
                                 related_name="rate_card_assignments")
    rate_card = models.ForeignKey(RateCard, on_delete=models.CASCADE,
                                  related_name="assignments")
    currency = models.CharField(max_length=3, default="usd")

    class Meta:
        db_table = "ubb_rate_card_assignment"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "customer", "currency"],
                name="uq_assignment_customer_currency"),
        ]
```
Then add the membership fields to `Rate` (inside `class Rate`, after `product_id`):
```python
    rate_card = models.ForeignKey("pricing.RateCard", on_delete=models.PROTECT,
                                  related_name="rates", null=True, blank=True)
    book_version_from = models.PositiveIntegerField(default=1)
    book_version_to = models.PositiveIntegerField(null=True, blank=True)
```
Update the Step-1 test so both default-book inserts use `provider_key="gemini"` (that is the field the constraint keys on).

- [ ] **Step 4: Generate the schema migration**

Run:
```bash
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python manage.py makemigrations pricing --name ratecard_container
```
Expected: creates `0011_ratecard_container.py` with `CreateModel` (RateCard, RateCardAssignment) + `AddField` (rate_card, book_version_from, book_version_to on Rate). Open it and confirm no unexpected operations.

- [ ] **Step 5: Run tests to verify they pass**

Run:
```bash
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/metering/pricing/tests/test_rate_card_container_model.py -v
```
Expected: PASS (both constraints enforced).

- [ ] **Step 6: Commit**

```bash
git add apps/metering/pricing/models.py apps/metering/pricing/migrations/0011_ratecard_container.py apps/metering/pricing/tests/test_rate_card_container_model.py
git commit -m "feat(pricing): add RateCard container + RateCardAssignment + Rate membership

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: Data migration — backfill Rates into per-provider default books

Group every active `Rate` into books and stamp membership. Asserts price-parity is preserved.

**Files:**
- Create: `apps/metering/pricing/migrations/0012_backfill_books.py`
- Create test: `apps/metering/pricing/tests/test_book_backfill_migration.py`

**Interfaces:**
- Consumes: models from Task 2.
- Produces: every active `Rate` has a non-null `rate_card`; one `is_default` book per `(tenant, card_type, provider, currency)`; per-customer books + `RateCardAssignment` for customer-scoped price rates.

- [ ] **Step 1: Write the failing backfill test**

Create `apps/metering/pricing/tests/test_book_backfill_migration.py`:
```python
import pytest
from django.core.management import call_command
from django.utils import timezone
from apps.metering.pricing.models import Rate, RateCard, RateCardAssignment
from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer

pytestmark = pytest.mark.django_db


def _backfill():
    # The migration's data function, callable directly for the test.
    from apps.metering.pricing.migrations import _book_backfill
    from django.apps import apps as django_apps
    _book_backfill.forwards(django_apps, None)


def test_default_rates_grouped_into_per_provider_default_book():
    t = Tenant.objects.create(name="T", default_currency="usd")
    r1 = Rate.objects.create(tenant=t, card_type="price", provider="gemini",
                             metric_name="input_tokens", currency="usd",
                             rate_per_unit_micros=10)
    r2 = Rate.objects.create(tenant=t, card_type="price", provider="gemini",
                             metric_name="output_tokens", currency="usd",
                             rate_per_unit_micros=30)
    _backfill()
    r1.refresh_from_db(); r2.refresh_from_db()
    assert r1.rate_card_id is not None
    assert r1.rate_card_id == r2.rate_card_id  # same provider -> same book
    assert r1.rate_card.is_default is True
    assert r1.rate_card.provider_key == "gemini"
    assert r1.book_version_from == 1 and r1.book_version_to is None


def test_customer_scoped_price_rate_gets_book_and_assignment():
    t = Tenant.objects.create(name="T", default_currency="usd")
    c = Customer.objects.create(tenant=t, external_id="c1")
    r = Rate.objects.create(tenant=t, card_type="price", provider="gemini",
                            metric_name="input_tokens", currency="usd",
                            customer=c, rate_per_unit_micros=5)
    _backfill()
    r.refresh_from_db()
    assert r.rate_card.is_default is False
    a = RateCardAssignment.objects.get(tenant=t, customer=c, currency="usd")
    assert a.rate_card_id == r.rate_card_id
```

- [ ] **Step 2: Run to verify it fails**

Run:
```bash
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/metering/pricing/tests/test_book_backfill_migration.py -v
```
Expected: FAIL with `ModuleNotFoundError: … _book_backfill`.

- [ ] **Step 3: Write the backfill logic module**

Create `apps/metering/pricing/migrations/_book_backfill.py` (a plain module so it is unit-testable; the migration calls `forwards`):
```python
"""Backfill logic for 0012. Groups active Rates into books.

Default (customer IS NULL) rates -> one is_default book per
(tenant, card_type, provider, currency), named after the provider.
Customer-scoped rates -> a per-(customer, card_type) book + a price-book
assignment. Only ACTIVE rates (valid_to IS NULL) are grouped; historical
versions inherit their lineage sibling's book in a second pass.
"""


def _book_for(RateCard, tenant_id, card_type, provider, currency, customer_id):
    is_default = customer_id is None
    key = (provider or "default") if is_default else f"cust-{customer_id}-{provider or 'default'}"
    book, _ = RateCard.objects.get_or_create(
        tenant_id=tenant_id, card_type=card_type, key=key[:64],
        defaults={"provider_key": provider or "", "currency": currency,
                  "name": provider or "default", "version": 1,
                  "is_default": is_default},
    )
    return book


def forwards(apps, schema_editor):
    Rate = apps.get_model("pricing", "Rate")
    RateCard = apps.get_model("pricing", "RateCard")
    RateCardAssignment = apps.get_model("pricing", "RateCardAssignment")

    # Pass 1: active rates -> books.
    for r in Rate.objects.filter(valid_to__isnull=True, rate_card__isnull=True):
        customer_id = r.customer_id
        book = _book_for(RateCard, r.tenant_id, r.card_type, r.provider,
                         r.currency, customer_id)
        r.rate_card = book
        r.book_version_from = 1
        r.book_version_to = None
        r.save(update_fields=["rate_card", "book_version_from", "book_version_to"])
        if customer_id is not None and r.card_type == "price":
            RateCardAssignment.objects.get_or_create(
                tenant_id=r.tenant_id, customer_id=customer_id, currency=r.currency,
                defaults={"rate_card": book})

    # Pass 2: historical rate versions -> same book as their active lineage sibling.
    active_by_lineage = {
        r.lineage_id: r.rate_card_id
        for r in Rate.objects.filter(valid_to__isnull=True)
    }
    for r in Rate.objects.filter(rate_card__isnull=True):
        book_id = active_by_lineage.get(r.lineage_id)
        if book_id is None:
            # No active sibling (fully superseded lineage): give it its own book.
            book = _book_for(RateCard, r.tenant_id, r.card_type, r.provider,
                             r.currency, r.customer_id)
            book_id = book.id
        r.rate_card_id = book_id
        r.save(update_fields=["rate_card"])


def backwards(apps, schema_editor):
    Rate = apps.get_model("pricing", "Rate")
    RateCard = apps.get_model("pricing", "RateCard")
    RateCardAssignment = apps.get_model("pricing", "RateCardAssignment")
    Rate.objects.update(rate_card=None)
    RateCardAssignment.objects.all().delete()
    RateCard.objects.all().delete()
```

- [ ] **Step 4: Write the migration that calls it**

Create `apps/metering/pricing/migrations/0012_backfill_books.py`:
```python
from django.db import migrations
from apps.metering.pricing.migrations import _book_backfill


class Migration(migrations.Migration):
    dependencies = [("pricing", "0011_ratecard_container")]
    operations = [
        migrations.RunPython(_book_backfill.forwards, _book_backfill.backwards),
    ]
```

- [ ] **Step 5: Run tests to verify they pass**

Run:
```bash
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/metering/pricing/tests/test_book_backfill_migration.py -v
```
Expected: PASS.

- [ ] **Step 6: Add an ops note for prod parity**

Append to the design doc's §10 (or a new `docs/plans/2026-07-03-rate-card-container-plan.md` ops appendix): before applying `0012` to staging/prod, run the parity probe:
```bash
DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python manage.py shell -c "
from apps.metering.pricing.models import Rate
print('cost customer-scoped:', Rate.objects.filter(card_type='cost', customer__isnull=False).count())
print('active rates:', Rate.objects.filter(valid_to__isnull=True).count())
"
```
Confirm the count of orphaned (`rate_card IS NULL`) active rates is zero AFTER migrate.

- [ ] **Step 7: Commit**

```bash
git add apps/metering/pricing/migrations/_book_backfill.py apps/metering/pricing/migrations/0012_backfill_books.py apps/metering/pricing/tests/test_book_backfill_migration.py
git commit -m "feat(pricing): backfill Rates into per-provider default books

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: Book-scoped resolution in `PricingService._resolve_card`

Rewrite resolution to use the customer's assigned book, falling back to the tenant's per-provider default book. Preserves the specificity + temporal logic exactly, scoped to a book.

**Files:**
- Modify: `apps/metering/pricing/services/pricing_service.py` (`_resolve_card`, add `_assigned_book`, `_default_book`, `_resolve_rate_within`)
- Modify test: `apps/metering/pricing/tests/test_pricing_service.py` (add resolution cases)

**Interfaces:**
- Consumes: `RateCard`, `RateCardAssignment`, `Rate` from Tasks 2–3.
- Produces: `_resolve_card(tenant, customer, card_type, provider, event_type, metric_name, tags, currency, as_of)` → a `Rate` or `None`, now book-scoped. Signature unchanged, so the two call sites in `price()` are untouched.

- [ ] **Step 1: Write failing resolution tests**

Add to `apps/metering/pricing/tests/test_pricing_service.py`:
```python
def test_unassigned_customer_uses_provider_default_book(db):
    from apps.metering.pricing.models import Rate, RateCard
    from apps.metering.pricing.services.pricing_service import PricingService
    from apps.platform.tenants.models import Tenant
    from apps.platform.customers.models import Customer
    from django.utils import timezone
    t = Tenant.objects.create(name="T", default_currency="usd")
    c = Customer.objects.create(tenant=t, external_id="c1")
    book = RateCard.objects.create(tenant=t, card_type="price", provider_key="gemini",
                                   currency="usd", key="gemini", is_default=True)
    r = Rate.objects.create(tenant=t, card_type="price", provider="gemini",
                            metric_name="input_tokens", currency="usd",
                            rate_per_unit_micros=10, rate_card=book)
    got = PricingService._resolve_card(t, c, "price", "gemini", "",
                                       "input_tokens", {}, "usd", timezone.now())
    assert got is not None and got.id == r.id


def test_assigned_book_wins_then_falls_back_to_default(db):
    from apps.metering.pricing.models import Rate, RateCard, RateCardAssignment
    from apps.metering.pricing.services.pricing_service import PricingService
    from apps.platform.tenants.models import Tenant
    from apps.platform.customers.models import Customer
    from django.utils import timezone
    t = Tenant.objects.create(name="T", default_currency="usd")
    c = Customer.objects.create(tenant=t, external_id="c1")
    default = RateCard.objects.create(tenant=t, card_type="price", provider_key="gemini",
                                      currency="usd", key="gemini", is_default=True)
    ent = RateCard.objects.create(tenant=t, card_type="price", provider_key="gemini",
                                  currency="usd", key="ent")
    RateCardAssignment.objects.create(tenant=t, customer=c, rate_card=ent, currency="usd")
    # Enterprise overrides input_tokens; output_tokens only exists in default.
    ent_in = Rate.objects.create(tenant=t, card_type="price", provider="gemini",
                                 metric_name="input_tokens", currency="usd",
                                 rate_per_unit_micros=5, rate_card=ent)
    def_out = Rate.objects.create(tenant=t, card_type="price", provider="gemini",
                                  metric_name="output_tokens", currency="usd",
                                  rate_per_unit_micros=30, rate_card=default)
    now = timezone.now()
    assert PricingService._resolve_card(t, c, "price", "gemini", "", "input_tokens", {}, "usd", now).id == ent_in.id
    assert PricingService._resolve_card(t, c, "price", "gemini", "", "output_tokens", {}, "usd", now).id == def_out.id


def test_no_default_book_for_provider_returns_none(db):
    from apps.metering.pricing.services.pricing_service import PricingService
    from apps.platform.tenants.models import Tenant
    from apps.platform.customers.models import Customer
    from django.utils import timezone
    t = Tenant.objects.create(name="T", default_currency="usd")
    c = Customer.objects.create(tenant=t, external_id="c1")
    assert PricingService._resolve_card(t, c, "price", "openai", "", "input_tokens", {}, "usd", timezone.now()) is None
```

- [ ] **Step 2: Run to verify they fail**

Run:
```bash
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/metering/pricing/tests/test_pricing_service.py -k "book or default or assigned" -v
```
Expected: FAIL (old `_resolve_card` ignores books; `RateCard` here is the container, so `.customer_id` filtering breaks).

- [ ] **Step 3: Rewrite `_resolve_card` and add helpers**

In `apps/metering/pricing/services/pricing_service.py`, replace the `_resolve_card` staticmethod (currently lines ~67–80) with:
```python
    @staticmethod
    def _resolve_rate_within(book, provider, event_type, metric_name, tags, currency, as_of):
        if book is None:
            return None
        cands = [c for c in Rate.objects.filter(
            rate_card=book, provider=provider or "", event_type=event_type or "",
            metric_name=metric_name, currency=currency, valid_from__lte=as_of,
        ).filter(Q(valid_to__isnull=True) | Q(valid_to__gt=as_of))
            if PricingService._dimensions_match(c.dimensions, tags)]
        if not cands:
            return None
        cands.sort(key=lambda c: (len(c.dimensions or {}), c.valid_from), reverse=True)
        return cands[0]

    @staticmethod
    def _assigned_book(tenant, customer, card_type, currency):
        if customer is None or card_type != "price":
            return None
        a = RateCardAssignment.objects.filter(
            tenant=tenant, customer=customer, currency=currency,
            rate_card__card_type="price").select_related("rate_card").first()
        return a.rate_card if a else None

    @staticmethod
    def _default_book(tenant, card_type, provider, currency):
        return RateCard.objects.filter(
            tenant=tenant, card_type=card_type, provider_key=provider or "",
            currency=currency, is_default=True).first()

    @staticmethod
    def _resolve_card(tenant, customer, card_type, provider, event_type, metric_name, tags, currency, as_of):
        book = PricingService._assigned_book(tenant, customer, card_type, currency)
        if book is not None:
            rate = PricingService._resolve_rate_within(
                book, provider, event_type, metric_name, tags, currency, as_of)
            if rate is not None:
                return rate
        default_book = PricingService._default_book(tenant, card_type, provider, currency)
        return PricingService._resolve_rate_within(
            default_book, provider, event_type, metric_name, tags, currency, as_of)
```
Update the import at the top: `from apps.metering.pricing.models import Rate, RateCard, RateCardAssignment, TIERED_PRICING_MODELS`.

- [ ] **Step 4: Add a shared test helper for book-attached rates**

Resolution now requires every priced rate to live in a book. **Every end-to-end test that creates a bare `Rate` and then prices through `PricingService.price()` or `record_usage` will break** (unit tests that call `card.compute*()` directly on a `Rate` instance are unaffected — they never resolve). Add a helper so the sweep is one-line-per-site.

Create `apps/metering/pricing/tests/_helpers.py`:
```python
from apps.metering.pricing.models import Rate, RateCard


def rate_in_default_book(tenant, *, card_type="price", provider="", customer=None, **fields):
    """Create a Rate attached to the tenant's is_default book for its
    (card_type, provider, currency). If customer is given, attach to a
    customer book + assignment instead. Mirrors the backfill's grouping so
    tests exercise the real resolution path."""
    from apps.metering.pricing.models import RateCardAssignment
    currency = fields.get("currency", tenant.default_currency or "usd")
    if customer is None:
        book, _ = RateCard.objects.get_or_create(
            tenant=tenant, card_type=card_type, provider_key=provider, currency=currency,
            is_default=True, defaults={"key": (provider or "default")[:64]})
    else:
        book, _ = RateCard.objects.get_or_create(
            tenant=tenant, card_type=card_type, key=f"cust-{customer.id}"[:64],
            defaults={"provider_key": provider, "currency": currency})
        if card_type == "price":
            RateCardAssignment.objects.get_or_create(
                tenant=tenant, customer=customer, currency=currency,
                defaults={"rate_card": book})
    return Rate.objects.create(tenant=tenant, card_type=card_type, provider=provider,
                               rate_card=book, book_version_from=book.version, **fields)
```

- [ ] **Step 5: Sweep end-to-end tests onto the helper**

In each of these files, replace `Rate.objects.create(...)` calls that are subsequently priced through `price()`/`record_usage` with `rate_in_default_book(...)` (same field kwargs; drop the now-implicit `rate_card`). Keep every asserted price identical:
- `apps/metering/pricing/tests/test_pricing_service.py`
- `apps/metering/usage/tests/test_record_usage_pricing.py`
- `apps/metering/usage/tests/test_tiered_record_usage.py`
- `apps/billing/tests/test_tiered_drawdown.py`
- `api/v1/tests/test_record_usage_provenance.py`, `api/v1/tests/test_journey1_best_in_class.py`, `api/v1/tests/test_journey1_sdk_integration.py`

Leave `test_tiered_pricing_math.py`, `test_tier_ladder_concurrency.py`, `test_verify_tier_rerate.py`, `test_tier_counter_service.py` alone IF they call `card.compute*()` / `TierCounterService` directly (verify each — convert only the ones that route through `price()`).

- [ ] **Step 6: Run resolution tests + full pricing/usage/billing suites**

Run:
```bash
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/metering/ apps/billing/tests/test_tiered_drawdown.py api/v1/tests/test_record_usage_provenance.py api/v1/tests/test_journey1_best_in_class.py api/v1/tests/test_journey1_sdk_integration.py --tb=short -q
```
Expected: PASS, including the three new resolution tests. Any residual failure is a test still creating a bare rate — route it through the helper.

- [ ] **Step 7: Commit**

```bash
git add apps/metering/pricing/services/pricing_service.py apps/metering/pricing/tests apps/metering/usage/tests apps/billing/tests/test_tiered_drawdown.py api/v1/tests
git commit -m "feat(pricing): book-scoped rate resolution with per-provider default fallback

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 5: `RateCard.publish()` — atomic multi-metric reprice

Add a service that supersedes a set of a book's rates and mints new versions in one transaction, bumping the book version and stamping `book_version_*`.

**Files:**
- Create: `apps/metering/pricing/services/book_service.py`
- Create test: `apps/metering/pricing/tests/test_book_publish.py`

**Interfaces:**
- Consumes: `RateCard`, `Rate`.
- Produces: `BookService.publish(book, changes, as_of=None) -> RateCard` where `changes` is a list of `{"metric_name","provider","event_type","dimensions", <pricing fields>}`. Each change supersedes the matching active rate (`valid_to=T`, `book_version_to=old book version`) and inserts a new active rate (same `lineage_id`, `valid_from>=T`, `book_version_from=new version`). Book `version` increments once. All in one `transaction.atomic()`.

- [ ] **Step 1: Write failing publish tests**

Create `apps/metering/pricing/tests/test_book_publish.py`:
```python
import pytest
from django.utils import timezone
from apps.metering.pricing.models import Rate, RateCard
from apps.metering.pricing.services.book_service import BookService
from apps.platform.tenants.models import Tenant

pytestmark = pytest.mark.django_db


def _book_with_two_rates():
    t = Tenant.objects.create(name="T", default_currency="usd")
    book = RateCard.objects.create(tenant=t, card_type="price", provider_key="gemini",
                                   currency="usd", key="gemini", is_default=True, version=1)
    ri = Rate.objects.create(tenant=t, card_type="price", provider="gemini",
                             metric_name="input_tokens", currency="usd",
                             rate_per_unit_micros=10, rate_card=book, book_version_from=1)
    ro = Rate.objects.create(tenant=t, card_type="price", provider="gemini",
                             metric_name="output_tokens", currency="usd",
                             rate_per_unit_micros=30, rate_card=book, book_version_from=1)
    return t, book, ri, ro


def test_publish_supersedes_and_bumps_version_atomically():
    t, book, ri, ro = _book_with_two_rates()
    BookService.publish(book, changes=[
        {"metric_name": "input_tokens", "provider": "gemini", "event_type": "",
         "dimensions": {}, "rate_per_unit_micros": 12},
        {"metric_name": "output_tokens", "provider": "gemini", "event_type": "",
         "dimensions": {}, "rate_per_unit_micros": 33},
    ])
    book.refresh_from_db(); ri.refresh_from_db(); ro.refresh_from_db()
    assert book.version == 2
    # Old rows closed at v1, new active rows opened at v2.
    assert ri.valid_to is not None and ri.book_version_to == 1
    assert ro.valid_to is not None and ro.book_version_to == 1
    active = list(Rate.objects.filter(rate_card=book, valid_to__isnull=True).order_by("metric_name"))
    assert [a.rate_per_unit_micros for a in active] == [12, 33]
    assert all(a.book_version_from == 2 for a in active)
    # lineage preserved (tiered continuity guarantee).
    assert {a.lineage_id for a in active} == {ri.lineage_id, ro.lineage_id}


def test_publish_is_all_or_nothing_on_error():
    t, book, ri, ro = _book_with_two_rates()
    with pytest.raises(Exception):
        BookService.publish(book, changes=[
            {"metric_name": "input_tokens", "provider": "gemini", "event_type": "",
             "dimensions": {}, "rate_per_unit_micros": 12},
            {"metric_name": "MISSING", "provider": "gemini", "event_type": "",
             "dimensions": {}, "rate_per_unit_micros": 1},  # no active rate -> error
        ])
    book.refresh_from_db()
    assert book.version == 1  # rolled back
    assert Rate.objects.filter(rate_card=book, valid_to__isnull=True).count() == 2
```

- [ ] **Step 2: Run to verify they fail**

Run:
```bash
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/metering/pricing/tests/test_book_publish.py -v
```
Expected: FAIL with `ModuleNotFoundError: … book_service`.

- [ ] **Step 3: Implement `BookService.publish`**

Create `apps/metering/pricing/services/book_service.py`:
```python
from django.db import transaction
from django.db.models import Q, F
from django.utils import timezone

from apps.metering.pricing.models import Rate, RateCard

_RATE_COPY_FIELDS = (
    "tenant_id", "customer_id", "card_type", "provider", "event_type",
    "metric_name", "dimensions", "pricing_model", "rate_per_unit_micros",
    "unit_quantity", "fixed_micros", "tiers", "currency", "product_id",
    "lineage_id", "rate_card_id",
)


class BookService:
    @staticmethod
    def publish(book, changes, as_of=None):
        """Atomically reprice a set of the book's rates. Each change must match
        exactly one ACTIVE rate in the book by (metric_name, provider,
        event_type, dimensions). Supersedes it (valid_to=T, book_version_to=old
        version) and inserts a new active rate (same lineage_id, valid_from>=T,
        book_version_from=new version). Bumps book.version once. All-or-nothing.
        """
        as_of = as_of or timezone.now()
        with transaction.atomic():
            locked = RateCard.objects.select_for_update().get(id=book.id)
            new_version = locked.version + 1
            for ch in changes:
                old = Rate.objects.select_for_update().filter(
                    rate_card=locked, valid_to__isnull=True,
                    metric_name=ch["metric_name"],
                    provider=ch.get("provider", ""),
                    event_type=ch.get("event_type", ""),
                ).filter(Q(dimensions=ch.get("dimensions", {}))).first()
                if old is None:
                    raise ValueError(
                        f"publish: no active rate for {ch['metric_name']!r} in book {locked.key}")
                data = {f: getattr(old, f) for f in _RATE_COPY_FIELDS}
                for k in ("pricing_model", "rate_per_unit_micros", "unit_quantity",
                          "fixed_micros", "tiers"):
                    if k in ch:
                        data[k] = ch[k]
                data["book_version_from"] = new_version
                data["book_version_to"] = None
                # Close the old row, then open the new (valid_from auto_now_add > T).
                old.valid_to = as_of
                old.book_version_to = locked.version
                old.save(update_fields=["valid_to", "book_version_to", "updated_at"])
                Rate.objects.create(**data)
            locked.version = new_version
            locked.save(update_fields=["version", "updated_at"])
            book.version = new_version
            return book
```
> `Rate.save()` computes `dimensions_hash`; `Rate.objects.create(**data)` runs it, so the new row's hash is correct. `valid_from` is `auto_now_add`, set at insert (after the `old.save`), so windows never overlap.

- [ ] **Step 4: Run to verify they pass**

Run:
```bash
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/metering/pricing/tests/test_book_publish.py -v
```
Expected: PASS (both).

- [ ] **Step 5: Add a tiered-continuity regression test**

Append to `test_book_publish.py`:
```python
def test_publish_preserves_lineage_for_tiered_marginal_continuity():
    t = Tenant.objects.create(name="T", default_currency="usd")
    book = RateCard.objects.create(tenant=t, card_type="price", provider_key="gemini",
                                   currency="usd", key="gemini", is_default=True, version=1)
    r = Rate.objects.create(tenant=t, card_type="price", provider="gemini",
                            metric_name="input_tokens", currency="usd",
                            pricing_model="graduated",
                            tiers=[{"up_to": 1000, "rate_per_unit_micros": 10},
                                   {"up_to": None, "rate_per_unit_micros": 5}],
                            rate_card=book, book_version_from=1)
    old_lineage = r.lineage_id
    BookService.publish(book, changes=[{
        "metric_name": "input_tokens", "provider": "gemini", "event_type": "",
        "dimensions": {}, "pricing_model": "graduated",
        "tiers": [{"up_to": 1000, "rate_per_unit_micros": 12},
                  {"up_to": None, "rate_per_unit_micros": 6}]}])
    new = Rate.objects.get(rate_card=book, valid_to__isnull=True)
    assert new.lineage_id == old_lineage  # PricingPeriodCounter continuity intact
```
Run the same pytest command; expect PASS.

- [ ] **Step 6: Commit**

```bash
git add apps/metering/pricing/services/book_service.py apps/metering/pricing/tests/test_book_publish.py
git commit -m "feat(pricing): BookService.publish for atomic multi-metric reprice

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 6: API reshape — book CRUD, rates sub-resource, publish, assign

Reshape the pricing API so `/pricing/rate-cards` manages books, rates live under a book, and add publish + assignment endpoints. Breaking change (no shim), per spec §2.4.

**Files:**
- Modify: `api/v1/metering_endpoints.py` (replace the rate-card endpoint block, ~lines 529–780)
- Modify: `api/v1/schemas.py` (add book/assignment schemas; repurpose `RateCardOut` → `RateOut`)
- Modify test: `api/v1/tests/test_rate_card_crud.py`, `api/v1/tests/test_tiered_rate_card_api.py` (rewrite to the new surface)
- Create test: `api/v1/tests/test_book_api.py`

**Interfaces:**
- Consumes: `RateCard`, `RateCardAssignment`, `Rate`, `BookService`.
- Produces endpoints:
  - `GET/POST /pricing/rate-cards` — list/create **books** (`BookIn`/`BookOut`).
  - `GET/POST /pricing/rate-cards/{book_id}/rates` — list/add **rates** in a book (`RateIn`/`RateOut`); create-with-many reuses batch semantics.
  - `POST /pricing/rate-cards/{book_id}/publish` — `PublishIn` (list of changes) → `BookOut`.
  - `GET /pricing/rate-cards/{book_id}/rates?include_history=true` — version history via `valid_to`.
  - `POST /pricing/customers/{customer_id}/rate-card` — assign a price book (`AssignIn`).

- [ ] **Step 1: Write failing API tests**

Create `api/v1/tests/test_book_api.py` (uses the project's existing auth/test-client helpers — mirror the setup in `api/v1/tests/test_rate_card_crud.py`):
```python
import pytest
pytestmark = pytest.mark.django_db


def test_create_book_then_add_rate_then_publish(auth_client, tenant):
    # 1. create a price book
    r = auth_client.post("/api/v1/metering/pricing/rate-cards", json={
        "card_type": "price", "provider_key": "gemini", "key": "gemini",
        "name": "Gemini", "is_default": True})
    assert r.status_code == 200, r.content
    book_id = r.json()["id"]
    # 2. add a rate to it
    r = auth_client.post(f"/api/v1/metering/pricing/rate-cards/{book_id}/rates", json={
        "metric_name": "input_tokens", "provider": "gemini",
        "pricing_model": "per_unit", "rate_per_unit_micros": 10})
    assert r.status_code == 200, r.content
    # 3. publish a reprice -> version bumps
    r = auth_client.post(f"/api/v1/metering/pricing/rate-cards/{book_id}/publish", json={
        "changes": [{"metric_name": "input_tokens", "provider": "gemini",
                     "rate_per_unit_micros": 12}]})
    assert r.status_code == 200, r.content
    assert r.json()["version"] == 2


def test_assign_book_to_customer(auth_client, tenant, customer):
    r = auth_client.post("/api/v1/metering/pricing/rate-cards", json={
        "card_type": "price", "provider_key": "gemini", "key": "ent", "name": "Ent"})
    book_id = r.json()["id"]
    r = auth_client.post(f"/api/v1/metering/pricing/customers/{customer.id}/rate-card",
                         json={"rate_card_id": book_id})
    assert r.status_code == 200, r.content
```
> If the test suite lacks `auth_client`/`tenant`/`customer` fixtures, copy the exact setup pattern from the top of `test_rate_card_crud.py` (it already constructs an authenticated client + tenant). Do not invent a new fixture style.

- [ ] **Step 2: Run to verify they fail**

Run:
```bash
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest api/v1/tests/test_book_api.py -v
```
Expected: FAIL (routes 404 / schema mismatch).

- [ ] **Step 3: Add schemas**

In `api/v1/schemas.py`, add the following. `RateIn` is the old `RateCardIn` minus `card_type` and `customer_id` (both now come from the book):
```python
class RateIn(Schema):
    metric_name: str = Field(min_length=1, max_length=100)
    provider: str = Field(default="", max_length=100)
    event_type: str = Field(default="", max_length=100)
    dimensions: dict = Field(default_factory=dict)
    pricing_model: str = "per_unit"
    rate_per_unit_micros: int = Field(default=0, ge=0)
    unit_quantity: int = Field(default=1_000_000, gt=0)
    fixed_micros: int = Field(default=0, ge=0)
    tiers: list = Field(default_factory=list)
    product_id: str = Field(default="", max_length=100)


class BookIn(Schema):
    card_type: str
    provider_key: str = Field(default="", max_length=100)
    key: str = Field(min_length=1, max_length=64)
    name: str = Field(default="", max_length=255)
    currency: Optional[str] = Field(default=None, max_length=3)
    is_default: bool = False


class BookOut(Schema):
    id: str
    card_type: str
    provider_key: str
    key: str
    name: str
    currency: str
    version: int
    is_default: bool


class RateChangeIn(Schema):
    metric_name: str
    provider: str = ""
    event_type: str = ""
    dimensions: dict = Field(default_factory=dict)
    pricing_model: Optional[str] = None
    rate_per_unit_micros: Optional[int] = Field(default=None, ge=0)
    unit_quantity: Optional[int] = Field(default=None, gt=0)
    fixed_micros: Optional[int] = Field(default=None, ge=0)
    tiers: Optional[list] = None


class PublishIn(Schema):
    changes: list[RateChangeIn]


class AssignIn(Schema):
    rate_card_id: UUID
```
Rename `RateCardOut` → `RateOut` (same fields; drop `customer_id`, add `rate_card_id: str`). Then **delete** the now-unused `RateCardIn`, `RateCardUpdateIn`, and `RateCardBatchIn` schemas — the flat create/update/batch endpoints they served are removed in Step 4, so leaving them is dead code (the `usage_mode` lesson). Grep to confirm no remaining references before deleting.

- [ ] **Step 4: Replace the endpoint block**

In `api/v1/metering_endpoints.py`, replace the block from `list_rate_cards` through `rate_card_history` with book + rate endpoints. Core additions:
```python
@metering_api.post("/pricing/rate-cards", response={200: BookOut, 422: dict})
def create_book(request, payload: BookIn):
    _gate_card_type(request, payload.card_type)
    try:
        currency = _resolve_card_currency(request.auth.tenant, payload.currency)
    except ValueError as e:
        return 422, {"error": str(e)}
    book = RateCard.objects.create(
        tenant=request.auth.tenant, card_type=payload.card_type,
        provider_key=payload.provider_key, key=payload.key, name=payload.name,
        currency=currency, is_default=payload.is_default)
    return 200, _book_to_out(book)


@metering_api.post("/pricing/rate-cards/{book_id}/rates", response={200: RateOut, 422: dict})
def add_rate(request, book_id: UUID, payload: RateIn):
    book = get_object_or_404(RateCard, id=book_id, tenant=request.auth.tenant)
    _gate_card_type(request, book.card_type)
    try:
        validate_tiers(book.card_type, payload.pricing_model, payload.tiers)
    except ValueError as e:
        return 422, {"error": str(e)}
    rate = Rate.objects.create(
        tenant=request.auth.tenant, rate_card=book, card_type=book.card_type,
        metric_name=payload.metric_name, provider=payload.provider,
        event_type=payload.event_type, dimensions=payload.dimensions,
        pricing_model=payload.pricing_model,
        rate_per_unit_micros=payload.rate_per_unit_micros,
        unit_quantity=payload.unit_quantity, fixed_micros=payload.fixed_micros,
        tiers=payload.tiers, currency=book.currency, product_id=payload.product_id,
        book_version_from=book.version)
    return 200, _rate_to_out(rate)


@metering_api.post("/pricing/rate-cards/{book_id}/publish", response={200: BookOut, 422: dict})
def publish_book(request, book_id: UUID, payload: PublishIn):
    from apps.metering.pricing.services.book_service import BookService
    book = get_object_or_404(RateCard, id=book_id, tenant=request.auth.tenant)
    _gate_card_type(request, book.card_type)
    try:
        BookService.publish(book, [c.dict(exclude_none=True) for c in payload.changes])
    except ValueError as e:
        return 422, {"error": str(e)}
    book.refresh_from_db()
    return 200, _book_to_out(book)


@metering_api.post("/pricing/customers/{customer_id}/rate-card", response={200: dict, 422: dict})
def assign_book(request, customer_id: UUID, payload: AssignIn):
    _billing_check(request)
    customer = get_object_or_404(Customer, id=customer_id, tenant=request.auth.tenant)
    book = get_object_or_404(RateCard, id=payload.rate_card_id,
                             tenant=request.auth.tenant, card_type="price")
    RateCardAssignment.objects.update_or_create(
        tenant=request.auth.tenant, customer=customer, currency=book.currency,
        defaults={"rate_card": book})
    return 200, {"assigned": str(book.id)}
```
Add `_book_to_out`, `_rate_to_out` helpers (mirror `_rate_card_to_out`), and a `list_book_rates` GET with `include_history`. Import `RateCard`, `RateCardAssignment` from the models and the new schemas.

- [ ] **Step 5: Rewrite the old CRUD tests to the new surface**

`api/v1/tests/test_rate_card_crud.py` and `test_tiered_rate_card_api.py` currently POST flat rate cards. Rewrite each to first create a book, then add rates under it, keeping the asserted prices/behaviors identical. Delete assertions on removed fields (`customer_id` on the flat card).

- [ ] **Step 6: Run the API + full pricing/usage suites**

Run:
```bash
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest api/v1/tests/test_book_api.py api/v1/tests/test_rate_card_crud.py api/v1/tests/test_tiered_rate_card_api.py apps/metering/ --tb=short -q
```
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add api/v1/metering_endpoints.py api/v1/schemas.py api/v1/tests/
git commit -m "feat(pricing): reshape pricing API around RateCard books (breaking)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 7: Full-suite verification + changelog

**Files:**
- Modify: whatever `docs/` changelog the repo uses (search for `CHANGELOG`/`docs/api`); if none, add a note to the design doc.

- [ ] **Step 1: Run the entire test suite**

Run:
```bash
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest --tb=short -q
```
Expected: PASS, zero failures. Investigate any failure before proceeding — do not mark complete with red tests.

- [ ] **Step 2: Confirm migration state is clean**

Run:
```bash
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python manage.py makemigrations --check --dry-run
```
Expected: `No changes detected`.

- [ ] **Step 3: Write the API changelog note**

Document the breaking change: `/pricing/rate-cards` now manages books; rates moved under `/pricing/rate-cards/{id}/rates`; new `publish` and customer-assignment endpoints; `RateCardOut` → `RateOut`. Note the migration (`0010`–`0012`) and the prod parity probe from Task 3 Step 6.

- [ ] **Step 4: Commit**

```bash
git add docs/
git commit -m "docs(pricing): changelog for RateCard container API reshape

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Deferred (NOT in this plan — the contracts phase)

- Per-rate customer overrides *within* a shared book.
- Effective-dating / contract terms.
- Version-pinned grandfathering (resolution pinning `as_of`→`book_version` via the assignment). The `book_version_from/to` columns and `RateCard.version` are the seam; no code here consumes them for resolution yet.
