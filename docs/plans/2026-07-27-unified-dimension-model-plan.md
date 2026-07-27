# Unified Dimension Model Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace UBB's three competing attribution mechanisms (named columns, `tags` JSONB,
`Rate.dimensions` JSONB) with one declared per-tenant dimension vocabulary that governs both
analytics grouping and rate selection, and add the `task_type` registry that makes per-run
unit economics answerable.

**Architecture:** A `DimensionDef` registry (platform) binds tenant-chosen keys to ten
indexed selector columns present on both `UsageEvent` and `Rate`. `""` means wildcard in a
rate selector; the match with the most non-empty selectors wins. A `DimensionValue` ledger
caps cardinality on write, which is what makes the rate cache safely dimension-keyed. Values
declared at `task`/`subtask` scope are inherited onto events at the single normalization seam
both recording lanes already share.

**Tech Stack:** Django 6.0, django-ninja, PostgreSQL, Celery/Redis, pytest.

**Design doc:** `docs/plans/2026-07-27-unified-dimension-model-design.md` — read it first;
decisions are referenced below as D1–D9.

## Global Constraints

- Run tests from `ubb-platform/`: `DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest`
- Python interpreter is always `.venv/bin/python` — never bare `python`
- **Local environment (verified 2026-07-27, applies to every command you run):**
  `.env`'s `DATABASE_URL` points at a docker Postgres on :5433 whose password auth
  fails. The working database is the native one on :5432. Export this in every shell —
  do NOT edit `.env`:
  ```bash
  export DATABASE_URL="postgresql://heyotis:heyotis@localhost:5432/ubb"
  export DJANGO_SETTINGS_MODULE=config.settings
  ```
- **Never run `manage.py migrate`.** The dev `ubb` database has a pre-existing,
  unrelated `InconsistentMigrationHistory` (`usage.0014_add_run_fk` is recorded as
  applied before its dependency `tasks.0001_initial`). It predates this branch, is dev-DB
  row state rather than a code defect, and is out of scope here. It does not affect
  `makemigrations`, and it does not affect pytest — pytest-django builds a fresh test
  database and applies every migration in dependency order, which is the real check that
  a new migration is sound. So: run `makemigrations`, then run the tests. If `pytest`
  passes, your migration is good.
  **`makemigrations` itself works fine — the inconsistency is a `migrate`-time check.** It
  emits a `RuntimeWarning` about the DB connection and generates normally. **Never
  hand-write a migration file.** A hand-written one drifts from the model (e.g. recording
  `id` as `UUIDField(default=None)` instead of `BaseModel`'s `default=uuid.uuid4`), which
  is invisible in your own tests but injects a spurious `AlterField` into every later
  task's `makemigrations` run. Verify with
  `.venv/bin/python manage.py makemigrations <app> --check --dry-run` — it must report no
  changes once you are done.
- Every model inherits `core.models.BaseModel` (UUID pk, `created_at`, `updated_at`)
- Every table name is prefixed `ubb_`
- **ADR-001 product boundaries:** products (`apps/metering`, `apps/billing`,
  `apps/subscriptions`, `apps/referrals`) never import each other. Cross-product reads go
  through `queries.py` module-level functions returning plain data, never ORM objects.
  `apps/platform` may be imported by anyone; `api/*` may import anything; products never
  import `api.*`. Gate: `.venv/bin/python -m pytest apps/platform/tests/test_product_boundaries.py`
- **ADR-002 spec is truth:** after ANY change to the API surface run
  `.venv/bin/python scripts/export_openapi.py` and commit the refreshed `openapi/v1.json`
- Micro-denominated integers throughout: `1_000_000` micros == 1 unit. Never floats for money
- `UsageEvent` is immutable — `save()` on an existing row and `delete()` both raise
  `ValueError` (`apps/metering/usage/models.py:91-97`)
- Dimension slot count is **six** (`dim1`..`dim6`) plus four reserved (`provider`,
  `event_type`, `task_type`, `subtask_type`) = ten selector columns
- **Known-failing baseline (measured 2026-07-27 on this branch — supersedes the earlier,
  stale "27 failures" figure).** A full run is `6 failed, 2188 passed, 3 skipped`. Judge by
  CAUSE, not by count — if you see a failure that is not one of these two causes, it is
  yours:
  - **`attrs` is not installed** in `.venv` at all → 4 `ubb-sdk` test failures plus 1
    excluded collection error
  - **`psycopg2` 2.9.11 is installed where the lock pins `psycopg==3.3.4`** (psycopg 3 is
    absent) → 2 NUL-byte tests fail
  Both are venv/lock drift, both predate this work, and neither is in scope here. Do NOT
  try to fix them — installing psycopg 3 mid-plan would swap the database driver under
  2188 passing tests.
- **Registry-mutating routes are ADMIN floor, audited, and atomic (ruled 2026-07-27 —
  overrides the `@role_floor(WRITE)` written in Tasks 3 and 7).** `PUT /metering/dimensions`
  and `PUT /metering/task-types` reshape the rules used to price usage — the dimension
  vocabulary feeds rate selection (D1) and task types carry per-job COGS ceilings (D7) — so
  they sit with `markup.set` and `rate_card.*` at Admin, per the carve table's own rule in
  `api/v1/tests/test_role_floors.py`: *every write floors at Admin (changes the rules or
  moves money) except the enumerated Write routes (day-to-day data ops)*. Each such route
  must ALSO carry `@records_audit(...)`, and must wrap its whole mutation loop plus its
  `audit_record(...)` call in ONE `transaction.atomic()` — `ledger.record()`'s docstring
  requires being inside the mutation's atomic block, and without it a partially-applied
  multi-item PUT commits rows, returns 422, and writes no audit trail. `POST
  /billing/pre-check` stays at Write: starting a job is a day-to-day data op, not a rule
  change.
- **`.venv` must match `requirements.lock.txt` for anything that generates committed
  artifacts.** A pydantic drift (2.12.5 installed vs 2.13.4 locked) silently stripped 9
  webhook `description` fields from every regenerated `openapi/v1.json`; that is now
  corrected to 2.13.4. If a spec regeneration produces changes you did not expect, suspect
  the toolchain before suspecting your own diff.
- **API test convention (corrected 2026-07-27 — overrides the test signatures written in
  every task below).** There is no `conftest.py` under `api/v1/tests/` and there are no
  `client` / `tenant` / `api_headers` / `customer` / `funded_wallet` pytest fixtures. Any
  task below whose test reads `def test_x(self, client, tenant, api_headers)` must be
  written instead in the repo's established pytest-class style, modelled on
  `api/v1/tests/test_accounts_api.py:1-30`:

  ```python
  import pytest
  from django.test import Client

  from apps.platform.tenants.models import Tenant, TenantApiKey


  @pytest.mark.django_db
  class TestSomething:
      def setup_method(self):
          # products=[...] is REQUIRED: every route below is gated by
          # _product_check, so a tenant without the product gets 403, not 422.
          self.tenant = Tenant.objects.create(
              name="T", products=["metering", "billing"])
          _, self.raw_key = TenantApiKey.create_key(self.tenant)
          self.client = Client()

      def _auth(self):
          return {"HTTP_AUTHORIZATION": f"Bearer {self.raw_key}"}

      def _get(self, path):
          return self.client.get(path, **self._auth())

      def _put(self, path, data):
          return self.client.put(path, data=data,
                                 content_type="application/json", **self._auth())

      def _post(self, path, data):
          return self.client.post(path, data=data,
                                  content_type="application/json", **self._auth())
  ```

  Conversion is mechanical: drop the fixture parameters, use `self.tenant` where the test
  used `tenant`, and call `self._get/_put/_post` where it used `client.<verb>(...,
  **api_headers)`. Create customers and wallets in `setup_method` where a task's tests need
  them (`Customer.objects.create(tenant=self.tenant, external_id="c1")`;
  `Wallet.objects.create(customer=...)` then set `balance_micros` and
  `save(update_fields=["balance_micros"])`, as `test_metering_endpoints.py:26-29` does).
  Every assertion, status code, and expected value in the task bodies stands unchanged —
  only the scaffolding differs. `TenantApiKey.create_key` returns `(key_obj, raw_key)` and
  keys default to the `admin` role, which satisfies every `@role_floor` on these routes.
- This is pre-launch: no live data. Renames and destructive migrations are acceptable and
  preferred over compatibility shims

---

## File Structure

**New app — `apps/platform/dimensions/`** (platform, so both products may read it)

| File | Responsibility |
|---|---|
| `models.py` | `DimensionDef`, `DimensionValue` |
| `services.py` | `DimensionService` — admit/validate values, resolve key→slot map |
| `queries.py` | Read contract for products: `declared_dimensions()`, `slot_map()` |
| `apps.py` | `AppConfig` with `label = "dimensions"` |
| `admin.py` | Django admin registration |
| `tests/` | `test_models.py`, `test_services.py`, `test_queries.py` |

**Modified**

| File | Change |
|---|---|
| `apps/platform/tasks/models.py` | `TaskType` model; `Task.task_type`, `Task.subtask_type` |
| `apps/platform/tasks/services.py` | Ceiling resolution from `TaskType`; type immutability |
| `apps/platform/tasks/queries.py` | **Create** — task read contract for the API/analytics |
| `apps/metering/usage/models.py` | Rename `product_id`/`service_id`/`agent_id` → `dim1`/`dim2`/`dim3`; add `dim4..dim6`, `task_type`, `subtask_type`; index `provider`; drop `RESERVED_DIM_KEYS` |
| `apps/metering/usage/services/usage_service.py` | Inheritance in `RecordingInput.gather`; slot names at the create site |
| `apps/metering/pricing/models.py` | `Rate`: ten selector columns; delete `dimensions`, `dimensions_hash`, hash `save()` hook |
| `apps/metering/pricing/services/pricing_service.py` | Wildcard + specificity resolution; delete `_dimensions_match` |
| `apps/metering/pricing/services/card_cache.py` | Dimension-keyed L1; delete the `if tags:` bypass |
| `apps/metering/queries.py` | `get_dimensional_margin` accepts any declared key |
| `api/v1/schemas.py` | `dimensions` dict on write schemas; `TaskOut`, `TaskTypeIn/Out`, `DimensionDefIn/Out`, `TaskAnalyticsOut` |
| `api/v1/metering_endpoints.py` | Dimension + task-type registry routes; task reads; `task_id` filter; `/analytics/tasks` |
| `api/v1/billing_endpoints.py` | `task_type`/`subtask_type`/`dimensions` on pre-check |
| `apps/subscriptions/api/margin_endpoints.py` | Real `group_by` string replacing `provider: int`/`product: int` |
| `docs/adr/0005-declared-dimensions.md` | **Create** — D8 mutability rules |

---

## Task 1: DimensionDef and DimensionValue models

**Files:**
- Create: `apps/platform/dimensions/__init__.py`, `apps.py`, `models.py`, `admin.py`
- Create: `apps/platform/dimensions/tests/__init__.py`, `tests/test_models.py`
- Modify: `config/settings.py` (add to `INSTALLED_APPS`)

**Interfaces:**
- Produces: `DimensionDef(tenant, key, slot, scope, max_cardinality, retired_at)` with
  `SLOT_CHOICES = ["dim1".."dim6"]`, `SCOPE_CHOICES = ["task", "subtask", "event"]`;
  `DimensionValue(tenant, key, value)`

- [ ] **Step 1: Write the failing test**

```python
# apps/platform/dimensions/tests/test_models.py
import pytest
from django.db import IntegrityError
from apps.platform.tenants.models import Tenant
from apps.platform.dimensions.models import DimensionDef, DimensionValue


@pytest.mark.django_db
class TestDimensionDef:
    def _t(self):
        return Tenant.objects.create(name="T")

    def test_key_unique_per_tenant(self):
        t = self._t()
        DimensionDef.objects.create(tenant=t, key="region", slot="dim1", scope="task")
        with pytest.raises(IntegrityError):
            DimensionDef.objects.create(tenant=t, key="region", slot="dim2", scope="task")

    def test_slot_unique_per_tenant(self):
        t = self._t()
        DimensionDef.objects.create(tenant=t, key="region", slot="dim1", scope="task")
        with pytest.raises(IntegrityError):
            DimensionDef.objects.create(tenant=t, key="model", slot="dim1", scope="event")

    def test_same_key_allowed_across_tenants(self):
        a, b = self._t(), self._t()
        DimensionDef.objects.create(tenant=a, key="region", slot="dim1", scope="task")
        DimensionDef.objects.create(tenant=b, key="region", slot="dim1", scope="task")
        assert DimensionDef.objects.count() == 2

    def test_value_unique_per_tenant_key(self):
        t = self._t()
        DimensionValue.objects.create(tenant=t, key="region", value="eu-west-1")
        with pytest.raises(IntegrityError):
            DimensionValue.objects.create(tenant=t, key="region", value="eu-west-1")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/platform/dimensions/tests/test_models.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'apps.platform.dimensions'`

- [ ] **Step 3: Create the app package**

```python
# apps/platform/dimensions/__init__.py
```
(empty file)

```python
# apps/platform/dimensions/apps.py
from django.apps import AppConfig


class DimensionsConfig(AppConfig):
    name = "apps.platform.dimensions"
    label = "dimensions"
```

```python
# apps/platform/dimensions/models.py
from django.db import models

from core.models import BaseModel

# Six tenant-owned slots (D2). A seventh axis requires a migration, so six is
# deliberately generous — adding columns later is the expensive move.
SLOT_CHOICES = [(f"dim{i}", f"dim{i}") for i in range(1, 7)]

# The level at which a dimension's value is CONSTANT (D6). Task- and
# subtask-scoped values are set once on the unit and inherited by its events;
# event-scoped values are sent per call.
SCOPE_CHOICES = [("task", "Task"), ("subtask", "Subtask"), ("event", "Event")]

# Always-present axes that are never declared and never retired (D1). A tenant
# may not bind one of these words to a dim slot.
RESERVED_KEYS = ("provider", "event_type", "task_type", "subtask_type")

# Correlation identifiers (D9): unbounded by construction, so they are filter
# parameters and may never be declared as dimensions.
FORBIDDEN_KEYS = ("task_id", "subtask_id", "request_id", "idempotency_key",
                  "customer_id", "event_id")


class DimensionDef(BaseModel):
    """One declared slicing axis, binding a tenant's own key to a physical slot.

    The registry is the SINGLE vocabulary for analytics grouping and rate
    selection (D1) — nothing may be grouped by or priced on that is not
    declared here.

    Immutability (D8): `slot` and `scope` never change. Re-slotting would
    silently change the meaning of every historical row in that column;
    re-scoping would make old and new rows disagree about where a value came
    from. `key` is a display label and may be renamed; the slot is identity.
    """
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE,
                               related_name="dimension_defs")
    key = models.CharField(max_length=64)
    slot = models.CharField(max_length=8, choices=SLOT_CHOICES)
    scope = models.CharField(max_length=8, choices=SCOPE_CHOICES, default="event")
    # Keyspace guard, not an invariant (D4): bounding distinct values is what
    # makes the rate cache safely dimension-keyed. Raise only, never lower.
    max_cardinality = models.IntegerField(default=100)
    # Retire, never delete (D8): stops accepting new values while historical
    # rows keep their meaning and stay groupable.
    retired_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "ubb_dimension_def"
        constraints = [
            models.UniqueConstraint(fields=["tenant", "key"],
                                    name="uq_dimension_def_key"),
            models.UniqueConstraint(fields=["tenant", "slot"],
                                    name="uq_dimension_def_slot"),
        ]

    def __str__(self):
        return f"DimensionDef({self.key} -> {self.slot}, {self.scope})"


class DimensionValue(BaseModel):
    """The distinct-value ledger backing the cardinality cap (D4).

    One row per (tenant, key, value) ever admitted. Also the read model for
    `GET /dimensions/{key}/values`, which is what a tenant dashboard needs to
    build a filter dropdown.
    """
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE,
                               related_name="dimension_values")
    key = models.CharField(max_length=64)
    value = models.CharField(max_length=100)

    class Meta:
        db_table = "ubb_dimension_value"
        constraints = [
            models.UniqueConstraint(fields=["tenant", "key", "value"],
                                    name="uq_dimension_value"),
        ]
        indexes = [
            models.Index(fields=["tenant", "key"], name="idx_dimvalue_tenant_key"),
        ]

    def __str__(self):
        return f"DimensionValue({self.key}={self.value})"
```

```python
# apps/platform/dimensions/admin.py
from django.contrib import admin

from apps.platform.dimensions.models import DimensionDef, DimensionValue


@admin.register(DimensionDef)
class DimensionDefAdmin(admin.ModelAdmin):
    list_display = ("tenant", "key", "slot", "scope", "max_cardinality", "retired_at")
    list_filter = ("scope", "slot")
    search_fields = ("key",)


@admin.register(DimensionValue)
class DimensionValueAdmin(admin.ModelAdmin):
    list_display = ("tenant", "key", "value", "created_at")
    list_filter = ("key",)
    search_fields = ("value",)
```

```python
# apps/platform/dimensions/tests/__init__.py
```
(empty file)

- [ ] **Step 4: Register the app**

In `config/settings.py`, add `"apps.platform.dimensions"` to `INSTALLED_APPS`
immediately after the existing `"apps.platform.tasks"` entry.

- [ ] **Step 5: Make and run the migration**

```bash
DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python manage.py makemigrations dimensions
# NOTE: do NOT run `manage.py migrate` — see Global Constraints. pytest builds a
# fresh test DB and applies migrations in dependency order, which is the check.
```

- [ ] **Step 6: Run test to verify it passes**

Run: `DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/platform/dimensions/tests/test_models.py -v`
Expected: 4 passed

- [ ] **Step 7: Commit**

```bash
git add apps/platform/dimensions config/settings.py
git commit -m "feat(dimensions): DimensionDef registry and DimensionValue ledger"
```

---

## Task 2: DimensionService — admit values, resolve slots

**Files:**
- Create: `apps/platform/dimensions/services.py`, `apps/platform/dimensions/queries.py`
- Create: `apps/platform/dimensions/tests/test_services.py`

**Interfaces:**
- Consumes: `DimensionDef`, `DimensionValue`, `RESERVED_KEYS`, `FORBIDDEN_KEYS` (Task 1)
- Produces:
  - `DimensionService.declare(tenant, key, slot, scope, max_cardinality)` → `DimensionDef`,
    raises `DimensionError`
  - `DimensionService.admit(tenant, values: dict[str, str], scope: str) -> dict[str, str]`
    — returns `{slot: value}`, raises `DimensionError` on unknown key, wrong scope, or cap
  - `apps.platform.dimensions.queries.slot_map(tenant_id) -> dict[str, str]` (key → slot)
  - `apps.platform.dimensions.queries.declared_dimensions(tenant_id) -> list[dict]`

- [ ] **Step 1: Write the failing test**

```python
# apps/platform/dimensions/tests/test_services.py
import pytest
from apps.platform.tenants.models import Tenant
from apps.platform.dimensions.models import DimensionDef, DimensionValue
from apps.platform.dimensions.services import DimensionService, DimensionError


@pytest.mark.django_db
class TestDeclare:
    def _t(self):
        return Tenant.objects.create(name="T")

    def test_declare_binds_key_to_slot(self):
        t = self._t()
        d = DimensionService.declare(t, key="region", slot="dim1", scope="task")
        assert d.key == "region" and d.slot == "dim1"

    def test_reserved_key_rejected(self):
        t = self._t()
        with pytest.raises(DimensionError, match="reserved"):
            DimensionService.declare(t, key="provider", slot="dim1", scope="event")

    def test_correlation_id_rejected(self):
        t = self._t()
        with pytest.raises(DimensionError, match="correlation"):
            DimensionService.declare(t, key="task_id", slot="dim1", scope="event")

    def test_slot_is_immutable(self):
        t = self._t()
        DimensionService.declare(t, key="region", slot="dim1", scope="task")
        with pytest.raises(DimensionError, match="slot is immutable"):
            DimensionService.declare(t, key="region", slot="dim2", scope="task")

    def test_scope_is_immutable(self):
        t = self._t()
        DimensionService.declare(t, key="region", slot="dim1", scope="task")
        with pytest.raises(DimensionError, match="scope is immutable"):
            DimensionService.declare(t, key="region", slot="dim1", scope="event")

    def test_cardinality_raises_only(self):
        t = self._t()
        DimensionService.declare(t, key="region", slot="dim1", scope="task",
                                 max_cardinality=50)
        DimensionService.declare(t, key="region", slot="dim1", scope="task",
                                 max_cardinality=80)
        with pytest.raises(DimensionError, match="lowered"):
            DimensionService.declare(t, key="region", slot="dim1", scope="task",
                                     max_cardinality=10)


@pytest.mark.django_db
class TestAdmit:
    def _t(self):
        t = Tenant.objects.create(name="T")
        DimensionService.declare(t, key="region", slot="dim1", scope="task",
                                 max_cardinality=2)
        DimensionService.declare(t, key="model", slot="dim2", scope="event")
        return t

    def test_admit_maps_keys_to_slots(self):
        t = self._t()
        assert DimensionService.admit(t, {"model": "gpt-4"}, scope="event") == {"dim2": "gpt-4"}

    def test_admit_records_the_value(self):
        t = self._t()
        DimensionService.admit(t, {"model": "gpt-4"}, scope="event")
        assert DimensionValue.objects.filter(tenant=t, key="model", value="gpt-4").exists()

    def test_admit_is_idempotent_on_repeat_value(self):
        t = self._t()
        DimensionService.admit(t, {"model": "gpt-4"}, scope="event")
        DimensionService.admit(t, {"model": "gpt-4"}, scope="event")
        assert DimensionValue.objects.filter(tenant=t, key="model").count() == 1

    def test_unknown_key_rejected(self):
        t = self._t()
        with pytest.raises(DimensionError, match="unknown dimension"):
            DimensionService.admit(t, {"nope": "x"}, scope="event")

    def test_wrong_scope_rejected(self):
        t = self._t()
        with pytest.raises(DimensionError, match="scope"):
            DimensionService.admit(t, {"region": "eu"}, scope="event")

    def test_cardinality_cap_rejects_novel_value(self):
        t = self._t()
        DimensionService.admit(t, {"region": "eu"}, scope="task")
        DimensionService.admit(t, {"region": "us"}, scope="task")
        with pytest.raises(DimensionError, match="cardinality"):
            DimensionService.admit(t, {"region": "ap"}, scope="task")

    def test_cap_does_not_block_known_value(self):
        t = self._t()
        DimensionService.admit(t, {"region": "eu"}, scope="task")
        DimensionService.admit(t, {"region": "us"}, scope="task")
        assert DimensionService.admit(t, {"region": "eu"}, scope="task") == {"dim1": "eu"}

    def test_retired_def_rejects_novel_value(self):
        t = self._t()
        DimensionService.admit(t, {"model": "gpt-4"}, scope="event")
        DimensionDef.objects.filter(tenant=t, key="model").update(
            retired_at="2026-07-27T00:00:00Z")
        with pytest.raises(DimensionError, match="retired"):
            DimensionService.admit(t, {"model": "gpt-5"}, scope="event")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/platform/dimensions/tests/test_services.py -v`
Expected: FAIL — `ImportError: cannot import name 'DimensionService'`

- [ ] **Step 3: Write the implementation**

```python
# apps/platform/dimensions/services.py
import re

from django.db import IntegrityError, transaction

from apps.platform.dimensions.models import (
    FORBIDDEN_KEYS, RESERVED_KEYS, DimensionDef, DimensionValue,
)

KEY_PATTERN = re.compile(r"[a-z][a-z0-9_]{1,63}")


class DimensionError(ValueError):
    """A declaration or value admission violated the registry's rules."""


class DimensionService:
    @staticmethod
    def declare(tenant, *, key, slot, scope, max_cardinality=100):
        """Declare or update one dimension. Idempotent on (key, slot, scope);
        enforces the D8 mutability rules."""
        if not KEY_PATTERN.fullmatch(key or ""):
            raise DimensionError(
                f"invalid dimension key {key!r}: must match [a-z][a-z0-9_]{{1,63}}")
        if key in RESERVED_KEYS:
            raise DimensionError(
                f"{key!r} is a reserved dimension — always present, never declared")
        if key in FORBIDDEN_KEYS:
            raise DimensionError(
                f"{key!r} is a correlation identifier, not a dimension: it is "
                "unbounded, so it is a filter parameter and cannot be grouped by")

        existing = DimensionDef.objects.filter(tenant=tenant, key=key).first()
        if existing is None:
            return DimensionDef.objects.create(
                tenant=tenant, key=key, slot=slot, scope=scope,
                max_cardinality=max_cardinality)

        if existing.slot != slot:
            raise DimensionError(
                f"{key!r} slot is immutable: bound to {existing.slot}, cannot "
                f"rebind to {slot} — historical rows in that column would "
                "silently change meaning")
        if existing.scope != scope:
            raise DimensionError(
                f"{key!r} scope is immutable: declared {existing.scope}, cannot "
                f"change to {scope} — inheritance would differ between old and "
                "new rows")
        if max_cardinality < existing.max_cardinality:
            raise DimensionError(
                f"{key!r} max_cardinality cannot be lowered "
                f"({existing.max_cardinality} -> {max_cardinality})")
        if max_cardinality != existing.max_cardinality:
            existing.max_cardinality = max_cardinality
            existing.save(update_fields=["max_cardinality", "updated_at"])
        return existing

    @staticmethod
    def admit(tenant, values, scope):
        """Validate a {key: value} map for one scope and return {slot: value}.

        Records novel values in the DimensionValue ledger, refusing any that
        would push a key past its cap (D4). The cap is a keyspace guard, not
        an invariant: concurrent novel values at the boundary may overshoot by
        the number of writers, which is harmless.
        """
        values = values or {}
        if not values:
            return {}
        defs = {d.key: d for d in DimensionDef.objects.filter(
            tenant=tenant, key__in=list(values))}
        out = {}
        for key, raw in values.items():
            d = defs.get(key)
            if d is None:
                raise DimensionError(f"unknown dimension {key!r}: declare it first")
            if d.scope != scope:
                raise DimensionError(
                    f"{key!r} is declared at {d.scope} scope and cannot be set "
                    f"at {scope} scope")
            value = str(raw)
            if len(value) > 100:
                raise DimensionError(
                    f"dimension {key!r} value exceeds 100 characters")
            DimensionService._record_value(tenant, d, value)
            out[d.slot] = value
        return out

    @staticmethod
    def _record_value(tenant, dimension_def, value):
        if DimensionValue.objects.filter(
                tenant=tenant, key=dimension_def.key, value=value).exists():
            return
        if dimension_def.retired_at is not None:
            raise DimensionError(
                f"dimension {dimension_def.key!r} is retired and accepts no new "
                f"values (got {value!r})")
        count = DimensionValue.objects.filter(
            tenant=tenant, key=dimension_def.key).count()
        if count >= dimension_def.max_cardinality:
            raise DimensionError(
                f"dimension {dimension_def.key!r} cardinality exceeded: "
                f"{count} distinct values already recorded (max "
                f"{dimension_def.max_cardinality}); {value!r} refused. High-"
                "cardinality data belongs in tags or a filter, not a dimension")
        try:
            with transaction.atomic():
                DimensionValue.objects.create(
                    tenant=tenant, key=dimension_def.key, value=value)
        except IntegrityError:
            # A concurrent writer admitted the same novel value — benign.
            pass
```

```python
# apps/platform/dimensions/queries.py
"""Read contract for the dimension registry (ADR-001).

Products (metering pricing/analytics, billing start-gate) call these instead of
importing the ORM models, so the registry can be reshaped without touching
product code. Returns plain data only — never ORM objects.
"""
from apps.platform.dimensions.models import DimensionDef


def slot_map(tenant_id) -> dict:
    """{declared key: slot} for a tenant, retired defs included.

    Retired defs stay in the map so historical rows remain groupable (D8) —
    retirement blocks new VALUES, not reads.
    """
    return dict(DimensionDef.objects.filter(tenant_id=tenant_id)
                .values_list("key", "slot"))


def declared_dimensions(tenant_id) -> list[dict]:
    """Full registry as plain dicts, ordered by slot."""
    return [
        {"key": d["key"], "slot": d["slot"], "scope": d["scope"],
         "max_cardinality": d["max_cardinality"],
         "retired": d["retired_at"] is not None}
        for d in DimensionDef.objects.filter(tenant_id=tenant_id)
        .order_by("slot")
        .values("key", "slot", "scope", "max_cardinality", "retired_at")
    ]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/platform/dimensions/tests/test_services.py -v`
Expected: 13 passed

- [ ] **Step 5: Commit**

```bash
git add apps/platform/dimensions
git commit -m "feat(dimensions): DimensionService declare/admit with cardinality cap"
```

---

## Task 3: Dimension registry API

**Files:**
- Modify: `api/v1/schemas.py` (add `DimensionDefIn`, `DimensionDefOut`, `DimensionValuesOut`)
- Modify: `api/v1/metering_endpoints.py` (three routes)
- Create: `api/v1/tests/test_dimension_registry.py`

**Interfaces:**
- Consumes: `DimensionService.declare` (Task 2), `queries.declared_dimensions` (Task 2)
- Produces: `PUT /api/v1/metering/dimensions`, `GET /api/v1/metering/dimensions`,
  `GET /api/v1/metering/dimensions/{key}/values`

- [ ] **Step 1: Write the failing test**

```python
# api/v1/tests/test_dimension_registry.py
import pytest
from apps.platform.dimensions.models import DimensionDef, DimensionValue


@pytest.mark.django_db
class TestDimensionRegistry:
    def test_put_declares_dimensions(self, client, tenant, api_headers):
        r = client.put("/api/v1/metering/dimensions",
                       data={"dimensions": [
                           {"key": "region", "slot": "dim1", "scope": "task",
                            "max_cardinality": 20},
                           {"key": "model", "slot": "dim2", "scope": "event"}]},
                       content_type="application/json", **api_headers)
        assert r.status_code == 200
        assert DimensionDef.objects.filter(tenant=tenant).count() == 2

    def test_get_lists_declared_dimensions(self, client, tenant, api_headers):
        DimensionDef.objects.create(tenant=tenant, key="region", slot="dim1",
                                    scope="task", max_cardinality=20)
        r = client.get("/api/v1/metering/dimensions", **api_headers)
        assert r.status_code == 200
        assert r.json()["dimensions"] == [
            {"key": "region", "slot": "dim1", "scope": "task",
             "max_cardinality": 20, "retired": False}]

    def test_reserved_key_is_422(self, client, tenant, api_headers):
        r = client.put("/api/v1/metering/dimensions",
                       data={"dimensions": [
                           {"key": "provider", "slot": "dim1", "scope": "event"}]},
                       content_type="application/json", **api_headers)
        assert r.status_code == 422
        assert "reserved" in r.json()["detail"]

    def test_task_id_as_dimension_is_422(self, client, tenant, api_headers):
        r = client.put("/api/v1/metering/dimensions",
                       data={"dimensions": [
                           {"key": "task_id", "slot": "dim1", "scope": "event"}]},
                       content_type="application/json", **api_headers)
        assert r.status_code == 422
        assert "correlation" in r.json()["detail"]

    def test_values_endpoint_lists_admitted_values(self, client, tenant, api_headers):
        DimensionDef.objects.create(tenant=tenant, key="region", slot="dim1",
                                    scope="task")
        DimensionValue.objects.create(tenant=tenant, key="region", value="eu-west-1")
        r = client.get("/api/v1/metering/dimensions/region/values", **api_headers)
        assert r.status_code == 200
        assert r.json()["values"] == ["eu-west-1"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest api/v1/tests/test_dimension_registry.py -v`
Expected: FAIL — 404 on every route

Note: reuse the `client`, `tenant`, `api_headers` fixtures already used by
`api/v1/tests/test_metering_endpoints.py`. If they live in that module rather than a
`conftest.py`, move them to `api/v1/tests/conftest.py` first as part of this step.

- [ ] **Step 3: Add the schemas**

```python
# api/v1/schemas.py — append near the other metering schemas
class DimensionDefIn(Schema):
    key: str = Field(max_length=64)
    slot: str = Field(max_length=8)
    scope: str = "event"
    max_cardinality: int = Field(default=100, ge=1, le=100_000)


class DimensionRegistryIn(Schema):
    dimensions: list[DimensionDefIn] = Field(min_length=1, max_length=6)


class DimensionDefOut(Schema):
    key: str
    slot: str
    scope: str
    max_cardinality: int
    retired: bool


class DimensionRegistryOut(Schema):
    dimensions: list[DimensionDefOut]


class DimensionValuesOut(Schema):
    key: str
    values: list[str]
```

- [ ] **Step 4: Add the routes**

```python
# api/v1/metering_endpoints.py — after the pricing routes
@metering_router.put("/dimensions", response={200: DimensionRegistryOut, 422: ProblemOut})
@role_floor(ADMIN)
@records_audit("dimension.declared")
def declare_dimensions(request, payload: DimensionRegistryIn):
    """Declare this tenant's slicing axes — the ONE vocabulary used by both
    analytics grouping and rate selection (design D1). Idempotent: re-PUTting
    an identical declaration is a no-op. `slot` and `scope` are immutable once
    bound and `max_cardinality` may only be raised (D8)."""
    _product_check(request)
    from apps.platform.dimensions.queries import declared_dimensions
    from apps.platform.dimensions.services import DimensionError, DimensionService

    tenant = request.auth.tenant
    try:
        for d in payload.dimensions:
            DimensionService.declare(tenant, key=d.key, slot=d.slot, scope=d.scope,
                                     max_cardinality=d.max_cardinality)
    except DimensionError as exc:
        raise Problem("validation_error", str(exc))
    return 200, {"dimensions": declared_dimensions(tenant.id)}


@metering_router.get("/dimensions", response=DimensionRegistryOut)
@role_floor(READ)
def list_dimensions(request):
    """This tenant's declared dimension vocabulary."""
    _product_check(request)
    from apps.platform.dimensions.queries import declared_dimensions
    return {"dimensions": declared_dimensions(request.auth.tenant.id)}


@metering_router.get("/dimensions/{key}/values",
                     response={200: DimensionValuesOut, 404: ProblemOut})
@role_floor(READ)
def list_dimension_values(request, key: str):
    """Every value admitted for one dimension — the read model a dashboard
    filter dropdown needs. Bounded by the key's max_cardinality (D4)."""
    _product_check(request)
    from apps.platform.dimensions.models import DimensionDef, DimensionValue

    if not DimensionDef.objects.filter(tenant=request.auth.tenant, key=key).exists():
        raise Problem("not_found", f"dimension {key!r} is not declared", status=404)
    values = list(DimensionValue.objects.filter(
        tenant=request.auth.tenant, key=key).order_by("value").values_list("value", flat=True))
    return 200, {"key": key, "values": values}
```

Add `DimensionRegistryIn`, `DimensionRegistryOut`, `DimensionValuesOut` to the
existing `from api.v1.schemas import (...)` block at the top of the module.

- [ ] **Step 5: Run test to verify it passes**

Run: `DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest api/v1/tests/test_dimension_registry.py -v`
Expected: 5 passed

- [ ] **Step 6: Regenerate the spec and commit**

```bash
DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python scripts/export_openapi.py
git add api/v1 openapi/v1.json
git commit -m "feat(api): dimension registry routes"
```

---

## Task 4: TaskType registry

**Files:**
- Modify: `apps/platform/tasks/models.py` (add `TaskType`)
- Create: `apps/platform/tasks/queries.py`
- Create: `apps/platform/tasks/tests/test_task_type.py`

**Interfaces:**
- Produces: `TaskType(tenant, key, kind, default_provider_cost_limit_micros,
  required_dimensions, retired_at)` with `TASK_TYPE_KIND_CHOICES = ["task", "subtask"]`;
  `apps.platform.tasks.queries.task_type_policy(tenant_id, key, kind) -> dict | None`

- [ ] **Step 1: Write the failing test**

```python
# apps/platform/tasks/tests/test_task_type.py
import pytest
from django.db import IntegrityError
from apps.platform.tenants.models import Tenant
from apps.platform.tasks.models import TaskType
from apps.platform.tasks.queries import task_type_policy


@pytest.mark.django_db
class TestTaskType:
    def _t(self):
        return Tenant.objects.create(name="T")

    def test_key_unique_per_tenant_and_kind(self):
        t = self._t()
        TaskType.objects.create(tenant=t, key="invoice_batch", kind="task")
        with pytest.raises(IntegrityError):
            TaskType.objects.create(tenant=t, key="invoice_batch", kind="task")

    def test_same_key_allowed_across_kinds(self):
        t = self._t()
        TaskType.objects.create(tenant=t, key="ocr", kind="task")
        TaskType.objects.create(tenant=t, key="ocr", kind="subtask")
        assert TaskType.objects.filter(tenant=t, key="ocr").count() == 2

    def test_policy_returns_plain_dict(self):
        t = self._t()
        TaskType.objects.create(tenant=t, key="invoice_batch", kind="task",
                                default_provider_cost_limit_micros=5_000_000,
                                required_dimensions=["region"])
        assert task_type_policy(t.id, "invoice_batch", "task") == {
            "key": "invoice_batch",
            "default_provider_cost_limit_micros": 5_000_000,
            "required_dimensions": ["region"],
            "retired": False,
        }

    def test_policy_none_for_unknown_key(self):
        t = self._t()
        assert task_type_policy(t.id, "nope", "task") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/platform/tasks/tests/test_task_type.py -v`
Expected: FAIL — `ImportError: cannot import name 'TaskType'`

- [ ] **Step 3: Write the model and query contract**

```python
# apps/platform/tasks/models.py — insert ABOVE class Task
TASK_TYPE_KIND_CHOICES = [("task", "Task"), ("subtask", "Subtask")]


def _empty_list():
    return []


class TaskType(BaseModel):
    """The tenant's declared work vocabulary, carrying POLICY (design D7).

    Before this existed, a unit's COGS ceiling came from the per-call
    `provider_cost_limit_micros` or one tenant-wide default
    (RiskConfig.default_task_provider_cost_limit_micros) — so every kind of job
    shared one ceiling, and a job that legitimately costs 50x its sibling forced
    you to either cap both at the large number or let the client declare its own
    spending limit. The ceiling now belongs to the KIND of work, server-side: a
    start call may request lower, never higher.
    """
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE,
                               related_name="task_types")
    key = models.SlugField(max_length=64)
    kind = models.CharField(max_length=8, choices=TASK_TYPE_KIND_CHOICES,
                            default="task")
    # COGS-denominated, matching Task.provider_cost_limit_micros. NULL = fall
    # back to the RiskConfig tenant default, then to uncapped.
    default_provider_cost_limit_micros = models.BigIntegerField(null=True, blank=True)
    # Declared dimension keys a start call MUST supply for this kind of work.
    required_dimensions = models.JSONField(default=_empty_list, blank=True)
    retired_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "ubb_task_type"
        constraints = [
            models.UniqueConstraint(fields=["tenant", "kind", "key"],
                                    name="uq_task_type_key"),
        ]

    def __str__(self):
        return f"TaskType({self.kind}:{self.key})"
```

```python
# apps/platform/tasks/queries.py
"""Read contract for tasks and task types (ADR-001).

Billing's start-gate reads task-type policy through here; the API's analytics
routes read task rollups through here. Plain data only — never ORM objects.
"""
from apps.platform.tasks.models import Task, TaskType


def task_type_policy(tenant_id, key, kind) -> dict | None:
    """One task type's policy, or None when the key is not declared."""
    row = TaskType.objects.filter(
        tenant_id=tenant_id, key=key, kind=kind
    ).values("key", "default_provider_cost_limit_micros", "required_dimensions",
             "retired_at").first()
    if row is None:
        return None
    return {"key": row["key"],
            "default_provider_cost_limit_micros":
                row["default_provider_cost_limit_micros"],
            "required_dimensions": row["required_dimensions"] or [],
            "retired": row["retired_at"] is not None}


def declared_task_types(tenant_id) -> list[dict]:
    """The tenant's whole work vocabulary, ordered by kind then key."""
    return [
        {"key": r["key"], "kind": r["kind"],
         "default_provider_cost_limit_micros":
             r["default_provider_cost_limit_micros"],
         "required_dimensions": r["required_dimensions"] or [],
         "retired": r["retired_at"] is not None}
        for r in TaskType.objects.filter(tenant_id=tenant_id)
        .order_by("kind", "key")
        .values("key", "kind", "default_provider_cost_limit_micros",
                "required_dimensions", "retired_at")
    ]
```

- [ ] **Step 4: Make and run the migration**

```bash
DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python manage.py makemigrations tasks
# NOTE: do NOT run `manage.py migrate` — see Global Constraints. pytest builds a
# fresh test DB and applies migrations in dependency order, which is the check.
```

- [ ] **Step 5: Run test to verify it passes**

Run: `DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/platform/tasks/tests/test_task_type.py -v`
Expected: 4 passed

- [ ] **Step 6: Commit**

```bash
git add apps/platform/tasks
git commit -m "feat(tasks): TaskType registry with per-kind COGS ceiling policy"
```

---

## Task 5: Task carries its type, immutably

**Files:**
- Modify: `apps/platform/tasks/models.py` (`Task.task_type`, `Task.subtask_type`)
- Modify: `apps/platform/tasks/services.py` (`TaskService.start` signature + immutability)
- Create: `apps/platform/tasks/tests/test_task_typing.py`

**Interfaces:**
- Consumes: `TaskType`, `task_type_policy` (Task 4)
- Produces: `Task.task_type: str`, `Task.subtask_type: str`, both `""` when untyped;
  `Task.save()` raises `ValueError` on a type change

- [ ] **Step 1: Write the failing test**

```python
# apps/platform/tasks/tests/test_task_typing.py
import pytest
from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.platform.tasks.models import Task


@pytest.mark.django_db
class TestTaskTyping:
    def _tc(self):
        t = Tenant.objects.create(name="T")
        return t, Customer.objects.create(tenant=t, external_id="c1")

    def test_task_stores_its_type(self):
        t, c = self._tc()
        task = Task.objects.create(tenant=t, customer=c, balance_snapshot_micros=0,
                                   task_type="invoice_batch")
        assert task.task_type == "invoice_batch" and task.subtask_type == ""

    def test_task_type_is_immutable(self):
        t, c = self._tc()
        task = Task.objects.create(tenant=t, customer=c, balance_snapshot_micros=0,
                                   task_type="invoice_batch")
        task.task_type = "receipt_scan"
        with pytest.raises(ValueError, match="task_type is immutable"):
            task.save()

    def test_subtask_type_is_immutable(self):
        t, c = self._tc()
        parent = Task.objects.create(tenant=t, customer=c, balance_snapshot_micros=0,
                                    task_type="invoice_batch")
        sub = Task.objects.create(tenant=t, customer=c, parent=parent,
                                  balance_snapshot_micros=0, subtask_type="ocr")
        sub.subtask_type = "classify"
        with pytest.raises(ValueError, match="subtask_type is immutable"):
            sub.save()

    def test_unrelated_field_still_saves(self):
        t, c = self._tc()
        task = Task.objects.create(tenant=t, customer=c, balance_snapshot_micros=0,
                                   task_type="invoice_batch")
        task.event_count = 5
        task.save()
        task.refresh_from_db()
        assert task.event_count == 5
```

- [ ] **Step 2: Run test to verify it fails**

Run: `DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/platform/tasks/tests/test_task_typing.py -v`
Expected: FAIL — `TypeError: Task() got unexpected keyword arguments: 'task_type'`

- [ ] **Step 3: Add the fields and the immutability guard**

```python
# apps/platform/tasks/models.py — inside class Task, after the `parent` field
    # The KIND of work this instance is (design D7). Immutable after creation
    # for the same reason `parent` is: accumulate_cost reads it without a lock,
    # and a re-typed task would retroactively change what every already-settled
    # event on it means. "" = untyped (a tenant who never declared a vocabulary).
    task_type = models.CharField(max_length=64, blank=True, default="", db_index=True)
    # Set instead of task_type when `parent` is set. Same immutability.
    subtask_type = models.CharField(max_length=64, blank=True, default="",
                                    db_index=True)
```

```python
# apps/platform/tasks/models.py — add to class Task, after __str__
    def save(self, *args, **kwargs):
        """Guard the two immutable type fields (D7/D8).

        Loaded via `from_db`, so `_loaded_type` is only present on rows read
        back from the database — a freshly constructed instance skips the check.
        """
        if not self._state.adding and hasattr(self, "_loaded_types"):
            was_task, was_subtask = self._loaded_types
            if self.task_type != was_task:
                raise ValueError(
                    f"task_type is immutable: {was_task!r} -> {self.task_type!r}")
            if self.subtask_type != was_subtask:
                raise ValueError(
                    f"subtask_type is immutable: {was_subtask!r} -> "
                    f"{self.subtask_type!r}")
        super().save(*args, **kwargs)

    @classmethod
    def from_db(cls, db, field_names, values):
        instance = super().from_db(db, field_names, values)
        if "task_type" in field_names and "subtask_type" in field_names:
            instance._loaded_types = (instance.task_type, instance.subtask_type)
        return instance
```

Also add to `Task.Meta.indexes`:

```python
            # Unit-economics rollup (design D7): mean/p95 cost per KIND of job.
            models.Index(fields=["tenant", "task_type", "-created_at"],
                         name="idx_task_type_created"),
```

- [ ] **Step 4: Make and run the migration**

```bash
DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python manage.py makemigrations tasks
# NOTE: do NOT run `manage.py migrate` — see Global Constraints. pytest builds a
# fresh test DB and applies migrations in dependency order, which is the check.
```

- [ ] **Step 5: Run the new test plus the existing task suite**

Run: `DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/platform/tasks -v`
Expected: 4 new passed, all pre-existing task tests still passing.

If any existing test fails because `TaskService` mutates and re-saves a task, the guard
is correct and the caller must be fixed to use `update_fields` without the type columns.

- [ ] **Step 6: Commit**

```bash
git add apps/platform/tasks
git commit -m "feat(tasks): immutable task_type/subtask_type on Task"
```

---

## Task 6: Start-gate resolves the ceiling from the task type

**Files:**
- Modify: `apps/billing/gating/services.py` (`RiskService.check` — see the ownership note below)
- Modify: `apps/platform/tasks/services.py` (`TaskService.create_task` gains the new fields)
- Modify: `api/v1/schemas.py` (`PreCheckRequest`, `PreCheckResponse`)
- Modify: `api/v1/billing_endpoints.py:234-247` (`pre_check`)
- Create: `api/v1/tests/test_precheck_task_type.py`

**Ownership note — read before writing code.** `TaskService.create_task`'s docstring
(`tasks/services.py:24-27`) states that limits are "passed explicitly by the caller
(billing pre-check), which owns the explicit-or-tenant-default resolution, the
cost-coverage gate, and the parent active/depth refusals". Ceiling resolution therefore
belongs in **`apps/billing/gating`**, beside the existing `RiskConfig` fallback — not in
`TaskService`. `TaskService.create_task` only gains new pass-through fields. Billing reads
`TaskType` via `apps.platform.tasks.queries` and calls
`apps.platform.dimensions.services.DimensionService`; both are platform, so ADR-001 is
satisfied (the four named channels govern product-to-product imports; the platform kernel
is importable by anyone).

**Interfaces:**
- Consumes: `task_type_policy` (Task 4), `Task.task_type` (Task 5),
  `DimensionService.admit` (Task 2)
- Produces: `PreCheckRequest.task_type`, `.subtask_type`, `.dimensions`;
  `PreCheckResponse.task_type`, `.provider_cost_limit_micros` sourced from policy

**Ceiling precedence (implement exactly):**
1. The start call's explicit `provider_cost_limit_micros`, **only if ≤ the type's default**
2. The `TaskType.default_provider_cost_limit_micros`
3. `RiskConfig.default_task_provider_cost_limit_micros` (or `..._subtask_...` for a subtask)
4. Uncapped

- [ ] **Step 1: Write the failing test**

```python
# api/v1/tests/test_precheck_task_type.py
import pytest
from apps.platform.tasks.models import Task, TaskType
from apps.platform.dimensions.models import DimensionDef


@pytest.mark.django_db
class TestPreCheckTaskType:
    def _declare(self, tenant):
        TaskType.objects.create(tenant=tenant, key="invoice_batch", kind="task",
                                default_provider_cost_limit_micros=5_000_000)
        DimensionDef.objects.create(tenant=tenant, key="region", slot="dim1",
                                    scope="task", max_cardinality=20)

    def test_ceiling_comes_from_the_task_type(self, client, tenant, customer,
                                              funded_wallet, api_headers):
        self._declare(tenant)
        r = client.post("/api/v1/billing/pre-check",
                        data={"customer_id": str(customer.id), "start_task": True,
                              "task_type": "invoice_batch",
                              "dimensions": {"region": "eu-west-1"}},
                        content_type="application/json", **api_headers)
        assert r.status_code == 200
        body = r.json()
        assert body["allowed"] is True
        assert body["provider_cost_limit_micros"] == 5_000_000
        task = Task.objects.get(id=body["task_id"])
        assert task.task_type == "invoice_batch" and task.dim1 == "eu-west-1"

    def test_caller_may_request_lower(self, client, tenant, customer,
                                     funded_wallet, api_headers):
        self._declare(tenant)
        r = client.post("/api/v1/billing/pre-check",
                        data={"customer_id": str(customer.id), "start_task": True,
                              "task_type": "invoice_batch",
                              "provider_cost_limit_micros": 1_000_000,
                              "dimensions": {"region": "eu-west-1"}},
                        content_type="application/json", **api_headers)
        assert r.json()["provider_cost_limit_micros"] == 1_000_000

    def test_caller_may_not_request_higher(self, client, tenant, customer,
                                           funded_wallet, api_headers):
        self._declare(tenant)
        r = client.post("/api/v1/billing/pre-check",
                        data={"customer_id": str(customer.id), "start_task": True,
                              "task_type": "invoice_batch",
                              "provider_cost_limit_micros": 99_000_000,
                              "dimensions": {"region": "eu-west-1"}},
                        content_type="application/json", **api_headers)
        assert r.status_code == 422
        assert "exceeds" in r.json()["detail"]

    def test_undeclared_task_type_is_422(self, client, tenant, customer,
                                         funded_wallet, api_headers):
        r = client.post("/api/v1/billing/pre-check",
                        data={"customer_id": str(customer.id), "start_task": True,
                              "task_type": "nope"},
                        content_type="application/json", **api_headers)
        assert r.status_code == 422
        assert "not declared" in r.json()["detail"]

    def test_missing_required_dimension_is_422(self, client, tenant, customer,
                                               funded_wallet, api_headers):
        TaskType.objects.create(tenant=tenant, key="invoice_batch", kind="task",
                                required_dimensions=["region"])
        DimensionDef.objects.create(tenant=tenant, key="region", slot="dim1",
                                    scope="task")
        r = client.post("/api/v1/billing/pre-check",
                        data={"customer_id": str(customer.id), "start_task": True,
                              "task_type": "invoice_batch"},
                        content_type="application/json", **api_headers)
        assert r.status_code == 422
        assert "required dimension" in r.json()["detail"]
```

Reuse `customer`, `funded_wallet` fixtures from `api/v1/tests/test_billing_endpoints.py`,
moving them to `api/v1/tests/conftest.py` if they are not already there.

- [ ] **Step 2: Run test to verify it fails**

Run: `DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest api/v1/tests/test_precheck_task_type.py -v`
Expected: FAIL — `task_type` is not a `PreCheckRequest` field, so it is ignored and the
ceiling assertion fails.

- [ ] **Step 3: Add `Task` dimension slots**

The task must carry task-scoped dimension values so events can inherit them (D6).

```python
# apps/platform/tasks/models.py — inside class Task, after subtask_type
    # Task-scoped dimension values (design D6), bound to slots by the tenant's
    # DimensionDef registry. Inherited by EVERY event in this task's tree,
    # including events on its subtasks, so a caller sets them once per job
    # instead of on every metered call. Immutable with the task.
    dim1 = models.CharField(max_length=100, blank=True, default="")
    dim2 = models.CharField(max_length=100, blank=True, default="")
    dim3 = models.CharField(max_length=100, blank=True, default="")
    dim4 = models.CharField(max_length=100, blank=True, default="")
    dim5 = models.CharField(max_length=100, blank=True, default="")
    dim6 = models.CharField(max_length=100, blank=True, default="")
```

- [ ] **Step 4: Extend the schemas**

```python
# api/v1/schemas.py — in PreCheckRequest, after external_task_id
    # The declared KIND of work (design D7). Resolves the server-side COGS
    # ceiling; a caller may request lower via provider_cost_limit_micros but
    # never higher.
    task_type: Optional[str] = Field(default=None, max_length=64)
    # Set instead of task_type when parent_task_id is present.
    subtask_type: Optional[str] = Field(default=None, max_length=64)
    # Declared dimension values at task/subtask scope, inherited by every event
    # in the tree (design D6). Keys must be declared; values are cardinality-
    # capped on write.
    dimensions: dict = Field(default_factory=dict)
```

```python
# api/v1/schemas.py — in PreCheckResponse, after parent_task_id
    task_type: Optional[str] = None
    subtask_type: Optional[str] = None
```

- [ ] **Step 5: Resolve the ceiling in billing's start-gate**

```python
# apps/billing/gating/services.py — inside RiskService, add this helper
    @staticmethod
    def resolve_type_policy(tenant, *, task_type, subtask_type, dimensions,
                            requested_limit_micros, is_subtask):
        """Validate the declared type + dimensions and resolve the ceiling.

        Precedence (design D7): caller request (only if <= the type default) ->
        type default -> RiskConfig tenant default -> uncapped. Returns
        (key, slot_values, limit_micros).
        """
        from apps.platform.dimensions.services import DimensionError, DimensionService
        from apps.platform.tasks.queries import task_type_policy

        kind = "subtask" if is_subtask else "task"
        key = (subtask_type if is_subtask else task_type) or ""
        policy = None
        if key:
            policy = task_type_policy(tenant.id, key, kind)
            if policy is None:
                raise ValueError(f"{kind}_type {key!r} is not declared")
            if policy["retired"]:
                raise ValueError(f"{kind}_type {key!r} is retired")

        scope = "subtask" if is_subtask else "task"
        try:
            slot_values = DimensionService.admit(tenant, dimensions or {}, scope=scope)
        except DimensionError as exc:
            raise ValueError(str(exc)) from exc

        if policy:
            supplied = set((dimensions or {}).keys())
            missing = [d for d in policy["required_dimensions"] if d not in supplied]
            if missing:
                raise ValueError(
                    f"{kind}_type {key!r} requires dimension(s) {missing}")

        type_default = policy["default_provider_cost_limit_micros"] if policy else None
        if requested_limit_micros is not None:
            if type_default is not None and requested_limit_micros > type_default:
                raise ValueError(
                    f"provider_cost_limit_micros {requested_limit_micros} exceeds "
                    f"the {kind}_type ceiling {type_default}")
            limit = requested_limit_micros
        elif type_default is not None:
            limit = type_default
        else:
            limit = None  # the existing RiskConfig fallback applies downstream
        return key, slot_values, limit
```

`RiskService.check` calls `resolve_type_policy` before `TaskService.create_task`, and
passes the resolved `limit` into the existing `provider_cost_limit_micros` argument — so the
`RiskConfig` fallback it already applies stays exactly where it is, reached only when
`resolve_type_policy` returns `None`.

Then extend `TaskService.create_task` (`tasks/services.py:15-19`) with `task_type=""`,
`subtask_type=""`, `dimension_slots=None`, spreading the slots into its existing
`Task.objects.create(...)` call. When `parent` is not None, write `subtask_type` and leave
`task_type` as `""` — the root's type is what events inherit (Task 10).

- [ ] **Step 6: Wire the endpoint**

```python
# api/v1/billing_endpoints.py — replace the body of pre_check
@billing_router.post("/pre-check", response={200: PreCheckResponse, 422: ProblemOut})
@role_floor(WRITE)
def pre_check(request, payload: PreCheckRequest):
    _product_check(request)
    customer = get_object_or_404(Customer, id=payload.customer_id,
                                tenant=request.auth.tenant)
    try:
        result = RiskService.check(
            customer,
            create_task=payload.start_task,
            task_metadata=payload.task_metadata,
            external_task_id=payload.external_task_id,
            provider_cost_limit_micros=payload.provider_cost_limit_micros,
            parent_task_id=payload.parent_task_id,
            task_type=payload.task_type,
            subtask_type=payload.subtask_type,
            dimensions=payload.dimensions,
        )
    except ValueError as exc:
        raise Problem("validation_error", str(exc))
    return 200, result
```

`RiskService.check` gains the same three keyword arguments and forwards them to
`TaskService.start`, which calls `resolve_type_policy` before creating the row.

- [ ] **Step 7: Migrate, run tests**

```bash
DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python manage.py makemigrations tasks
# NOTE: do NOT run `manage.py migrate` — see Global Constraints. pytest builds a
# fresh test DB and applies migrations in dependency order, which is the check.
DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest api/v1/tests/test_precheck_task_type.py apps/billing/gating apps/platform/tasks -v
```
Expected: 5 new passed; gating and task suites still green.

- [ ] **Step 8: Regenerate the spec and commit**

```bash
DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python scripts/export_openapi.py
git add apps/platform/tasks apps/billing/gating api/v1 openapi/v1.json
git commit -m "feat(gating): resolve task ceiling from TaskType policy"
```

---

## Task 7: TaskType registry API

**Files:**
- Modify: `api/v1/schemas.py` (`TaskTypeIn`, `TaskTypeOut`, `TaskTypeRegistryIn/Out`)
- Modify: `api/v1/metering_endpoints.py` (two routes)
- Create: `api/v1/tests/test_task_type_registry.py`

**Interfaces:**
- Consumes: `TaskType` (Task 4), `declared_task_types` (Task 4)
- Produces: `PUT /api/v1/metering/task-types`, `GET /api/v1/metering/task-types`

- [ ] **Step 1: Write the failing test**

```python
# api/v1/tests/test_task_type_registry.py
import pytest
from apps.platform.tasks.models import TaskType


@pytest.mark.django_db
class TestTaskTypeRegistry:
    def test_put_declares_types(self, client, tenant, api_headers):
        r = client.put("/api/v1/metering/task-types",
                       data={"task_types": [
                           {"key": "invoice_batch", "kind": "task",
                            "default_provider_cost_limit_micros": 5_000_000,
                            "required_dimensions": ["region"]},
                           {"key": "ocr", "kind": "subtask",
                            "default_provider_cost_limit_micros": 2_000_000}]},
                       content_type="application/json", **api_headers)
        assert r.status_code == 200
        assert TaskType.objects.filter(tenant=tenant).count() == 2

    def test_put_is_idempotent(self, client, tenant, api_headers):
        body = {"task_types": [{"key": "invoice_batch", "kind": "task",
                                "default_provider_cost_limit_micros": 5_000_000}]}
        client.put("/api/v1/metering/task-types", data=body,
                   content_type="application/json", **api_headers)
        client.put("/api/v1/metering/task-types", data=body,
                   content_type="application/json", **api_headers)
        assert TaskType.objects.filter(tenant=tenant).count() == 1

    def test_put_updates_the_ceiling(self, client, tenant, api_headers):
        TaskType.objects.create(tenant=tenant, key="invoice_batch", kind="task",
                                default_provider_cost_limit_micros=1_000_000)
        client.put("/api/v1/metering/task-types",
                   data={"task_types": [
                       {"key": "invoice_batch", "kind": "task",
                        "default_provider_cost_limit_micros": 9_000_000}]},
                   content_type="application/json", **api_headers)
        assert TaskType.objects.get(
            tenant=tenant, key="invoice_batch"
        ).default_provider_cost_limit_micros == 9_000_000

    def test_undeclared_required_dimension_is_422(self, client, tenant, api_headers):
        r = client.put("/api/v1/metering/task-types",
                       data={"task_types": [
                           {"key": "invoice_batch", "kind": "task",
                            "required_dimensions": ["region"]}]},
                       content_type="application/json", **api_headers)
        assert r.status_code == 422
        assert "not declared" in r.json()["detail"]

    def test_get_lists_types(self, client, tenant, api_headers):
        TaskType.objects.create(tenant=tenant, key="ocr", kind="subtask")
        r = client.get("/api/v1/metering/task-types", **api_headers)
        assert r.status_code == 200
        assert r.json()["task_types"][0]["key"] == "ocr"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest api/v1/tests/test_task_type_registry.py -v`
Expected: FAIL — 404 on both routes

- [ ] **Step 3: Add the schemas**

```python
# api/v1/schemas.py
class TaskTypeIn(Schema):
    key: str = Field(max_length=64)
    kind: str = "task"
    default_provider_cost_limit_micros: Optional[int] = Field(default=None, gt=0)
    required_dimensions: list[str] = Field(default_factory=list, max_length=6)


class TaskTypeRegistryIn(Schema):
    task_types: list[TaskTypeIn] = Field(min_length=1, max_length=100)


class TaskTypeOut(Schema):
    key: str
    kind: str
    default_provider_cost_limit_micros: Optional[int] = None
    required_dimensions: list[str]
    retired: bool


class TaskTypeRegistryOut(Schema):
    task_types: list[TaskTypeOut]
```

- [ ] **Step 4: Add the routes**

```python
# api/v1/metering_endpoints.py — after the dimension routes
@metering_router.put("/task-types", response={200: TaskTypeRegistryOut, 422: ProblemOut})
@role_floor(ADMIN)
@records_audit("task_type.declared")
def declare_task_types(request, payload: TaskTypeRegistryIn):
    """Declare the tenant's work vocabulary and its per-kind COGS ceilings
    (design D7). Idempotent; the ceiling and required_dimensions may be updated
    on a re-PUT."""
    _product_check(request)
    from apps.platform.dimensions.queries import slot_map
    from apps.platform.tasks.models import TaskType
    from apps.platform.tasks.queries import declared_task_types

    tenant = request.auth.tenant
    declared = set(slot_map(tenant.id))
    for tt in payload.task_types:
        if tt.kind not in ("task", "subtask"):
            raise Problem("validation_error", f"invalid kind {tt.kind!r}")
        missing = [d for d in tt.required_dimensions if d not in declared]
        if missing:
            raise Problem("validation_error",
                          f"required_dimensions not declared: {missing}")
        TaskType.objects.update_or_create(
            tenant=tenant, key=tt.key, kind=tt.kind,
            defaults={
                "default_provider_cost_limit_micros":
                    tt.default_provider_cost_limit_micros,
                "required_dimensions": tt.required_dimensions,
            })
    return 200, {"task_types": declared_task_types(tenant.id)}


@metering_router.get("/task-types", response=TaskTypeRegistryOut)
@role_floor(READ)
def list_task_types(request):
    """The tenant's declared work vocabulary."""
    _product_check(request)
    from apps.platform.tasks.queries import declared_task_types
    return {"task_types": declared_task_types(request.auth.tenant.id)}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest api/v1/tests/test_task_type_registry.py -v`
Expected: 5 passed

- [ ] **Step 6: Regenerate the spec and commit**

```bash
DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python scripts/export_openapi.py
git add api/v1 openapi/v1.json
git commit -m "feat(api): task-type registry routes"
```

---

## Task 8: UsageEvent selector columns

**Files:**
- Modify: `apps/metering/usage/models.py`
- Modify: `apps/metering/usage/admin.py`, `apps/metering/queries.py`,
  `api/v1/metering_endpoints.py`, `api/v1/schemas.py` (rename call sites)
- Create: `apps/metering/usage/tests/test_selector_columns.py`

**Interfaces:**
- Produces: `UsageEvent.dim1..dim6`, `.task_type`, `.subtask_type`; `provider` indexed;
  `product_id`/`service_id`/`agent_id` and `RESERVED_DIM_KEYS` gone

- [ ] **Step 1: Write the failing test**

```python
# apps/metering/usage/tests/test_selector_columns.py
import pytest
from django.db import connection
from apps.metering.usage.models import UsageEvent


@pytest.mark.django_db
class TestSelectorColumns:
    def test_ten_selector_columns_exist(self):
        names = {f.name for f in UsageEvent._meta.get_fields()}
        for col in ("provider", "event_type", "task_type", "subtask_type",
                    "dim1", "dim2", "dim3", "dim4", "dim5", "dim6"):
            assert col in names, f"missing selector column {col}"

    def test_legacy_attribution_columns_are_gone(self):
        names = {f.name for f in UsageEvent._meta.get_fields()}
        assert "product_id" not in names
        assert "service_id" not in names
        assert "agent_id" not in names

    def test_provider_is_indexed(self):
        with connection.cursor() as cur:
            cur.execute("""
                SELECT indexdef FROM pg_indexes
                WHERE tablename = 'ubb_usage_event'
            """)
            defs = " ".join(row[0] for row in cur.fetchall())
        assert "provider" in defs, "provider must be indexed — it is grouped on every /analytics/usage call"

    def test_reserved_dim_keys_constant_is_gone(self):
        import apps.metering.usage.models as m
        assert not hasattr(m, "RESERVED_DIM_KEYS")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/metering/usage/tests/test_selector_columns.py -v`
Expected: FAIL — `missing selector column task_type`

- [ ] **Step 3: Rewrite the model's selector block**

Replace lines 7 and 24-30 of `apps/metering/usage/models.py`. Delete
`RESERVED_DIM_KEYS` entirely, and replace the five attribution fields with:

```python
    # --- The ten selector columns (design D2/D3) ---
    # One vocabulary for analytics grouping AND rate selection. Four reserved
    # keys plus six tenant slots bound by the DimensionDef registry. "" means
    # "not set" on an event and "matches anything" on a Rate; specificity =
    # the count of non-empty selectors.
    event_type = models.CharField(max_length=100, blank=True, default="", db_index=True)
    # Indexed: /analytics/usage groups by provider unconditionally on every call.
    provider = models.CharField(max_length=100, blank=True, default="", db_index=True)
    # Inherited from the event's task chain, never sent by the caller (D6).
    task_type = models.CharField(max_length=64, blank=True, default="", db_index=True)
    subtask_type = models.CharField(max_length=64, blank=True, default="", db_index=True)
    dim1 = models.CharField(max_length=100, blank=True, default="", db_index=True)
    dim2 = models.CharField(max_length=100, blank=True, default="", db_index=True)
    dim3 = models.CharField(max_length=100, blank=True, default="", db_index=True)
    dim4 = models.CharField(max_length=100, blank=True, default="", db_index=True)
    dim5 = models.CharField(max_length=100, blank=True, default="", db_index=True)
    dim6 = models.CharField(max_length=100, blank=True, default="", db_index=True)
```

Replace the `idx_usage_attribution` entry in `Meta.indexes` with:

```python
            models.Index(fields=["tenant", "task_type", "subtask_type", "-effective_at"],
                         name="idx_usage_work_attribution"),
            models.Index(fields=["tenant", "dim1", "dim2", "-effective_at"],
                         name="idx_usage_dim_attribution"),
```

- [ ] **Step 4: Update every call site**

Rename mechanically. The complete list:

- `apps/metering/queries.py:281` — `valid_group_by` tuple → the ten selector names
- `apps/metering/queries.py:324,354-359` — `get_dimensional_margin` group_by allowlist
- `apps/metering/queries.py:442` — `.values("product_id")` → `.values("dim1")`
- `apps/metering/usage/admin.py` — `list_display` / `list_filter` entries
- `api/v1/metering_endpoints.py:401` — `_ANALYTICS_ALLOWED_COLS`
- `api/v1/metering_endpoints.py:464-470` — the `by_product` block → `by_task_type`
- `api/v1/metering_endpoints.py:236-238` — `UsageEventDetailOut` serializer keys
- `api/v1/metering_endpoints.py:571` — the timeseries `group_by` allowlist
- `api/v1/schemas.py:80,164-165,223-225,676,751,772` — request/response fields
- `apps/metering/usage/services/usage_service.py:257-259,356-359` — see Task 10

Find any remainder with:

```bash
grep -rn "product_id\|service_id\|agent_id" --include="*.py" apps/ api/ core/ | grep -v "/tests/"
```

- [ ] **Step 5: Migrate and run the metering suite**

```bash
DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python manage.py makemigrations usage
# NOTE: do NOT run `manage.py migrate` — see Global Constraints. pytest builds a
# fresh test DB and applies migrations in dependency order, which is the check.
DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/metering -v
```
Expected: 4 new passed. Existing metering tests referencing the old names will fail —
rename them in the same commit; that is the intended blast radius.

- [ ] **Step 6: Commit**

```bash
git add apps/metering api/v1
git commit -m "refactor(metering): ten selector columns on UsageEvent, provider indexed"
```

---

## Task 9: `dimensions` on the write contract

**Files:**
- Modify: `api/v1/schemas.py` (`RecordUsageRequest`)
- Modify: `api/v1/metering_endpoints.py:57-83` (sync record), `111-134` (ingest)
- Create: `api/v1/tests/test_usage_dimensions.py`

**Interfaces:**
- Consumes: `DimensionService.admit` (Task 2)
- Produces: `RecordUsageRequest.dimensions: dict`; `422 validation_error` on an unknown
  key, a wrong-scope key, or a cardinality overflow

- [ ] **Step 1: Write the failing test**

```python
# api/v1/tests/test_usage_dimensions.py
import pytest
from apps.metering.usage.models import UsageEvent
from apps.platform.dimensions.models import DimensionDef


@pytest.mark.django_db
class TestUsageDimensions:
    def _declare(self, tenant):
        DimensionDef.objects.create(tenant=tenant, key="model", slot="dim2",
                                    scope="event", max_cardinality=2)
        DimensionDef.objects.create(tenant=tenant, key="region", slot="dim1",
                                    scope="task")

    def _post(self, client, customer, api_headers, **extra):
        body = {"customer_id": str(customer.id), "request_id": "r1",
                "idempotency_key": "k1", "provider": "openai",
                "event_type": "completion", "provider_cost_micros": 1000}
        body.update(extra)
        return client.post("/api/v1/metering/usage", data=body,
                           content_type="application/json", **api_headers)

    def test_declared_event_dimension_lands_in_its_slot(self, client, tenant,
                                                        customer, api_headers):
        self._declare(tenant)
        r = self._post(client, customer, api_headers,
                       dimensions={"model": "gpt-4"})
        assert r.status_code == 200
        assert UsageEvent.objects.get(id=r.json()["event_id"]).dim2 == "gpt-4"

    def test_unknown_dimension_is_422(self, client, tenant, customer, api_headers):
        self._declare(tenant)
        r = self._post(client, customer, api_headers, dimensions={"nope": "x"})
        assert r.status_code == 422
        assert "unknown dimension" in r.json()["detail"]

    def test_task_scoped_dimension_rejected_on_an_event(self, client, tenant,
                                                       customer, api_headers):
        self._declare(tenant)
        r = self._post(client, customer, api_headers, dimensions={"region": "eu"})
        assert r.status_code == 422
        assert "scope" in r.json()["detail"]

    def test_cardinality_overflow_is_422(self, client, tenant, customer, api_headers):
        self._declare(tenant)
        self._post(client, customer, api_headers, dimensions={"model": "a"})
        self._post(client, customer, api_headers, dimensions={"model": "b"})
        r = client.post("/api/v1/metering/usage",
                        data={"customer_id": str(customer.id), "request_id": "r9",
                              "idempotency_key": "k9", "provider": "openai",
                              "event_type": "completion", "provider_cost_micros": 1,
                              "dimensions": {"model": "c"}},
                        content_type="application/json", **api_headers)
        assert r.status_code == 422
        assert "cardinality" in r.json()["detail"]

    def test_tags_no_longer_become_dimensions(self, client, tenant, customer,
                                              api_headers):
        """The reserved-tag lifting at usage_service.py:257-259 is deleted:
        tags are free-form labels only (design 'What this deletes')."""
        self._declare(tenant)
        r = self._post(client, customer, api_headers,
                       tags={"service": "extract", "agent": "textract-v2"})
        assert r.status_code == 200
        e = UsageEvent.objects.get(id=r.json()["event_id"])
        assert e.dim1 == "" and e.dim2 == ""
        assert e.tags == {"service": "extract", "agent": "textract-v2"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest api/v1/tests/test_usage_dimensions.py -v`
Expected: FAIL — `dimensions` is not a field on `RecordUsageRequest`, so `dim2` stays `""`

- [ ] **Step 3: Add the request field**

```python
# api/v1/schemas.py — in RecordUsageRequest, replacing the tags docstring block
    # Free-form analytics labels. Never grouped, never priced, never unit
    # attribution — see `dimensions` for anything you want to slice or price on.
    tags: Optional[dict[str, str]] = None
    # Declared EVENT-scoped dimension values (design D1/D6). Keys must be in the
    # tenant's DimensionDef registry and declared at event scope; task- and
    # subtask-scoped values are set at the start-gate and inherited, not sent
    # here. Values are cardinality-capped on write.
    dimensions: dict = Field(default_factory=dict)
```

- [ ] **Step 4: Admit dimensions in both write endpoints**

In `record_usage` (`metering_endpoints.py:57`), after the existing task validation:

```python
    from apps.platform.dimensions.services import DimensionError, DimensionService
    try:
        dimension_slots = DimensionService.admit(
            request.auth.tenant, payload.dimensions, scope="event")
    except DimensionError as exc:
        raise Problem("validation_error", str(exc))
```

Pass `dimension_slots=dimension_slots` into the `UsageService.record_usage(...)` call.

In `ingest_usage` (`metering_endpoints.py:111`), admit per item and turn a
`DimensionError` into that item's rejection verdict rather than failing the batch:

```python
        try:
            item_slots = DimensionService.admit(tenant, item.dimensions, scope="event")
        except DimensionError as exc:
            results.append({"accepted": False, "code": "validation_error",
                            "detail": str(exc), "stop": False,
                            "stop_reason": None, "stop_scope": None})
            rejected += 1
            continue
```

Store `item_slots` in the `RawIngestEvent.payload` dict under `"dimension_slots"` so the
settle worker does not re-admit (admission is a write; settle must stay idempotent).

- [ ] **Step 5: Run test to verify it passes**

Run: `DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest api/v1/tests/test_usage_dimensions.py -v`
Expected: 5 passed

- [ ] **Step 6: Regenerate the spec and commit**

```bash
DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python scripts/export_openapi.py
git add api/v1 apps/metering openapi/v1.json
git commit -m "feat(metering): declared dimensions on the usage write contract"
```

---

## Task 10: Inheritance at the recording seam

**Files:**
- Modify: `apps/metering/usage/services/usage_service.py` (`RecordingInput`, `gather`,
  the create site at line 348)
- Modify: `apps/metering/usage/services/ingest_accept.py:167` (widen the task read)
- Create: `apps/metering/usage/tests/test_dimension_inheritance.py`

**Interfaces:**
- Consumes: `Task.task_type`, `Task.subtask_type`, `Task.dim1..dim6` (Tasks 5, 6)
- Produces: `RecordingInput.gather(..., dimension_slots: dict)` resolving inherited values;
  `RecordingInput` fields `task_type`, `subtask_type`, `dim1..dim6`

**Inheritance rule (implement exactly):** for each of the six slots, the event's own
event-scoped value wins; else the leaf task's value; else the leaf task's parent's value;
else `""`. `task_type` comes from the root of the chain, `subtask_type` from the leaf when
it has a parent.

- [ ] **Step 1: Write the failing test**

```python
# apps/metering/usage/tests/test_dimension_inheritance.py
import pytest
from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.platform.tasks.models import Task
from apps.metering.usage.models import UsageEvent
from apps.metering.usage.services.usage_service import UsageService


@pytest.mark.django_db
class TestDimensionInheritance:
    def _fixture(self):
        t = Tenant.objects.create(name="T")
        c = Customer.objects.create(tenant=t, external_id="c1")
        parent = Task.objects.create(tenant=t, customer=c, balance_snapshot_micros=0,
                                    task_type="invoice_batch", dim1="eu-west-1")
        sub = Task.objects.create(tenant=t, customer=c, parent=parent,
                                  balance_snapshot_micros=0, subtask_type="ocr")
        return t, c, parent, sub

    def _record(self, t, c, task, **kw):
        return UsageService.record_usage(
            tenant=t, customer=c, request_id="r1", idempotency_key=kw.pop("key", "k1"),
            provider="aws_textract", event_type="ocr_page",
            provider_cost_micros=1000, task_id=task.id, **kw)

    def test_event_inherits_task_type_from_the_root(self):
        t, c, parent, sub = self._fixture()
        e = self._record(t, c, sub)
        assert e.task_type == "invoice_batch"

    def test_event_inherits_subtask_type_from_the_leaf(self):
        t, c, parent, sub = self._fixture()
        assert self._record(t, c, sub).subtask_type == "ocr"

    def test_event_inherits_task_scoped_slot_through_the_parent(self):
        t, c, parent, sub = self._fixture()
        assert self._record(t, c, sub).dim1 == "eu-west-1"

    def test_event_scoped_value_overrides_inheritance(self):
        t, c, parent, sub = self._fixture()
        e = self._record(t, c, sub, dimension_slots={"dim1": "us-east-1"})
        assert e.dim1 == "us-east-1"

    def test_top_level_task_event_has_no_subtask_type(self):
        t, c, parent, sub = self._fixture()
        assert self._record(t, c, parent).subtask_type == ""

    def test_unattributed_event_inherits_nothing(self):
        t = Tenant.objects.create(name="T2")
        c = Customer.objects.create(tenant=t, external_id="c2")
        e = UsageService.record_usage(
            tenant=t, customer=c, request_id="r1", idempotency_key="k1",
            provider="openai", event_type="completion", provider_cost_micros=1)
        assert e.task_type == "" and e.dim1 == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/metering/usage/tests/test_dimension_inheritance.py -v`
Expected: FAIL — `AttributeError: 'UsageEvent' object has no attribute 'task_type'` or the
inherited values are `""`

- [ ] **Step 3: Add the inheritance resolver**

```python
# apps/metering/usage/services/usage_service.py — module level, above RecordingInput
SLOTS = ("dim1", "dim2", "dim3", "dim4", "dim5", "dim6")


def _inherit_dimensions(task_id, dimension_slots):
    """Resolve the ten selector values for one event (design D6).

    Precedence per slot: the event's own value, then the leaf unit's, then its
    parent's, then "". `task_type` always comes from the ROOT of the chain and
    `subtask_type` from the leaf when it has a parent — so a subtask's events
    carry both without the caller repeating either.

    One query for the leaf and one for its parent; containment is a single level
    (tasks/models.py:34-38), so this never recurses.
    """
    out = {"task_type": "", "subtask_type": ""}
    out.update({s: (dimension_slots or {}).get(s, "") for s in SLOTS})
    if task_id is None:
        return out

    from apps.platform.tasks.models import Task
    cols = ("id", "parent_id", "task_type", "subtask_type") + SLOTS
    leaf = Task.objects.filter(id=task_id).values(*cols).first()
    if leaf is None:
        return out

    if leaf["parent_id"] is None:
        out["task_type"] = leaf["task_type"]
        chain = (leaf,)
    else:
        out["subtask_type"] = leaf["subtask_type"]
        root = Task.objects.filter(id=leaf["parent_id"]).values(*cols).first()
        out["task_type"] = (root or {}).get("task_type", "")
        chain = (leaf, root) if root else (leaf,)

    for slot in SLOTS:
        if out[slot]:
            continue  # the event's own value wins
        for unit in chain:
            if unit and unit.get(slot):
                out[slot] = unit[slot]
                break
    return out
```

- [ ] **Step 4: Wire it into `gather` and the create site**

In `RecordingInput`, replace the `product_id`/`service_id`/`agent_id` field annotations
with `task_type: str`, `subtask_type: str`, and `dim1: str` … `dim6: str`.

In `gather`, replace the reserved-tag lifting block (lines 257-259) with:

```python
        # Dimensions are DECLARED and INHERITED (design D1/D6) — there is no
        # tag-fallback inference. `tags` is free-form labels only.
        dims = _inherit_dimensions(task_id, dimension_slots)
```

and spread `**dims` into the `cls(...)` call, dropping `product_id=`, `service_id=`,
`agent_id=`. Add `dimension_slots=None` to `gather`'s keyword arguments.

At the create site (line 348), replace
`product_id=inp.product_id, ... service_id=inp.service_id, agent_id=inp.agent_id`
with:

```python
                    task_type=inp.task_type, subtask_type=inp.subtask_type,
                    dim1=inp.dim1, dim2=inp.dim2, dim3=inp.dim3,
                    dim4=inp.dim4, dim5=inp.dim5, dim6=inp.dim6,
```

Both `gather` call sites (lines 473 sync, 578 settle) pass `dimension_slots` — the sync
lane from the endpoint (Task 9), the settle lane from
`raw.payload.get("dimension_slots")`.

- [ ] **Step 5: Widen the accept-path task read**

`ingest_accept.py:167` already batch-reads tasks through a 30s L1 cache. Extend its
`.values()` to `("id", "customer_id", "parent_id", "task_type", "subtask_type") + SLOTS`
and widen the cache entry tuple accordingly, so accept-time estimation prices on the same
inherited dimensions that settle will use. Update `reset_task_meta_cache`'s docstring to
note the widened shape.

- [ ] **Step 6: Run the tests**

```bash
DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/metering/usage api/v1/tests/test_ingest_endpoint.py -v
```
Expected: 6 new passed; the usage and ingest suites green.

- [ ] **Step 7: Commit**

```bash
git add apps/metering
git commit -m "feat(metering): inherit task/subtask dimensions onto events at the recording seam"
```

---

## Task 11: Rate selector columns

**Files:**
- Modify: `apps/metering/pricing/models.py` (`Rate`)
- Modify: `apps/metering/pricing/services/book_service.py:10,39`
- Modify: `apps/metering/pricing/tests/_helpers.py`
- Create: `apps/metering/pricing/tests/test_rate_selectors.py`

**Interfaces:**
- Produces: `Rate.task_type`, `.subtask_type`, `.dim1..dim6`; `Rate.selector_tuple` and
  `Rate.specificity` properties; `Rate.dimensions`, `.dimensions_hash` and the hash
  `save()` hook deleted

- [ ] **Step 1: Write the failing test**

```python
# apps/metering/pricing/tests/test_rate_selectors.py
import pytest
from django.db import IntegrityError
from apps.platform.tenants.models import Tenant
from apps.metering.pricing.models import Rate
from apps.metering.pricing.tests._helpers import rate_in_default_book


@pytest.mark.django_db
class TestRateSelectors:
    def _t(self):
        return Tenant.objects.create(name="T")

    def test_jsonb_dimensions_are_gone(self):
        names = {f.name for f in Rate._meta.get_fields()}
        assert "dimensions" not in names
        assert "dimensions_hash" not in names

    def test_specificity_counts_non_empty_selectors(self):
        t = self._t()
        r = rate_in_default_book(t, card_type="cost", provider="openai",
                                 event_type="chat", metric_name="input_tokens",
                                 dim1="eu-west-1")
        assert r.specificity == 3

    def test_wildcard_rate_has_zero_specificity(self):
        t = self._t()
        r = rate_in_default_book(t, card_type="cost", metric_name="input_tokens")
        assert r.specificity == 0

    def test_uniqueness_spans_all_selectors(self):
        t = self._t()
        rate_in_default_book(t, card_type="cost", provider="openai",
                             metric_name="input_tokens", dim1="eu")
        # Same book, same metric, DIFFERENT dim1 -> allowed.
        rate_in_default_book(t, card_type="cost", provider="openai",
                             metric_name="input_tokens", dim1="us")
        assert Rate.objects.filter(metric_name="input_tokens").count() == 2

    def test_duplicate_selector_set_is_rejected(self):
        t = self._t()
        rate_in_default_book(t, card_type="cost", provider="openai",
                             metric_name="input_tokens", dim1="eu")
        with pytest.raises(IntegrityError):
            rate_in_default_book(t, card_type="cost", provider="openai",
                                 metric_name="input_tokens", dim1="eu")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/metering/pricing/tests/test_rate_selectors.py -v`
Expected: FAIL — `dimensions` is still a field; `specificity` does not exist

- [ ] **Step 3: Rewrite `Rate`'s selector block**

Delete `dimensions`, `dimensions_hash`, `product_id`, and the `save()` hook that computes
the hash (`pricing/models.py:69-70,76,99-101`). Add:

```python
    # --- The ten selector columns (design D3) ---
    # "" means WILDCARD here (it means "not set" on a UsageEvent). Among rates
    # matching an event, the winner has the most non-empty selectors. This is
    # the ONE matching semantic — the old JSONB `dimensions` subset match and
    # the exact-equality provider/event_type match were two different rules on
    # one query.
    provider = models.CharField(max_length=100, blank=True, default="", db_index=True)
    event_type = models.CharField(max_length=100, blank=True, default="", db_index=True)
    task_type = models.CharField(max_length=64, blank=True, default="")
    subtask_type = models.CharField(max_length=64, blank=True, default="")
    dim1 = models.CharField(max_length=100, blank=True, default="")
    dim2 = models.CharField(max_length=100, blank=True, default="")
    dim3 = models.CharField(max_length=100, blank=True, default="")
    dim4 = models.CharField(max_length=100, blank=True, default="")
    dim5 = models.CharField(max_length=100, blank=True, default="")
    dim6 = models.CharField(max_length=100, blank=True, default="")
```

Add, below `Meta`:

```python
    SELECTORS = ("provider", "event_type", "task_type", "subtask_type",
                 "dim1", "dim2", "dim3", "dim4", "dim5", "dim6")

    @property
    def selector_tuple(self):
        return tuple(getattr(self, s) for s in self.SELECTORS)

    @property
    def specificity(self):
        """How many selectors this rate pins. The resolution tie-breaker (D3):
        a rate pinning provider+event_type+dim1 beats one pinning provider
        alone, so a tenant writes a broad default plus narrow overrides."""
        return sum(1 for v in self.selector_tuple if v)
```

Replace the uniqueness constraint:

```python
            models.UniqueConstraint(
                fields=["rate_card", "metric_name", "currency", "provider",
                        "event_type", "task_type", "subtask_type",
                        "dim1", "dim2", "dim3", "dim4", "dim5", "dim6"],
                condition=models.Q(valid_to__isnull=True),
                name="uq_rate_active_in_book"),
```

- [ ] **Step 4: Update the book service and the test helper**

In `book_service.py:10`, replace `"dimensions"` in the copied-field tuple with the ten
selector names. At line 39, replace `.filter(Q(dimensions=ch.get("dimensions", {})))`
with equality filters on the ten selector columns drawn from `ch`.

In `pricing/tests/_helpers.py`, change `rate_in_default_book` to accept the ten selector
names as keyword arguments (defaulting to `""`) instead of `dimensions=`.

- [ ] **Step 5: Migrate and run the pricing suite**

```bash
DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python manage.py makemigrations pricing
# NOTE: do NOT run `manage.py migrate` — see Global Constraints. pytest builds a
# fresh test DB and applies migrations in dependency order, which is the check.
DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/metering/pricing -v
```
Expected: 5 new passed. Tests passing `dimensions={...}` fail — port them to the slot
keyword arguments in this commit.

- [ ] **Step 6: Commit**

```bash
git add apps/metering/pricing
git commit -m "refactor(pricing): ten selector columns on Rate, JSONB dimensions deleted"
```

---

## Task 12: Wildcard resolution with specificity ranking

**Files:**
- Modify: `apps/metering/pricing/services/pricing_service.py:31-77,159-179,181-216`
- Create: `apps/metering/pricing/tests/test_wildcard_resolution.py`

**Interfaces:**
- Consumes: `Rate.SELECTORS`, `Rate.specificity` (Task 11)
- Produces: `PricingService.price(..., selectors: dict)` and `.estimate(..., selectors: dict)`
  replacing the `provider`/`event_type`/`tags` arguments; `_dimensions_match` deleted

- [ ] **Step 1: Write the failing test**

```python
# apps/metering/pricing/tests/test_wildcard_resolution.py
import pytest
from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.metering.pricing.services.pricing_service import PricingService
from apps.metering.pricing.tests._helpers import rate_in_default_book


@pytest.mark.django_db
class TestWildcardResolution:
    def _tc(self):
        t = Tenant.objects.create(name="T")
        return t, Customer.objects.create(tenant=t, external_id="c1")

    def _price(self, t, c, **selectors):
        base = {"provider": "", "event_type": "", "task_type": "",
                "subtask_type": "", "dim1": "", "dim2": "", "dim3": "",
                "dim4": "", "dim5": "", "dim6": ""}
        base.update(selectors)
        return PricingService.price(
            tenant=t, customer=c, selectors=base,
            usage_metrics={"input_tokens": 1_000_000}, currency="usd",
            caller_provider_cost=None, caller_billed=None)

    def test_wildcard_rate_matches_any_provider(self):
        """The headline fix: one provider-agnostic rate, not one per provider."""
        t, c = self._tc()
        rate_in_default_book(t, card_type="cost", metric_name="input_tokens",
                             rate_per_unit_micros=2_000, unit_quantity=1_000_000)
        prov, _, p = self._price(t, c, provider="anthropic")
        assert prov == 2_000 and p["cost_source"] == "rate_card"

    def test_specific_rate_beats_the_wildcard(self):
        t, c = self._tc()
        rate_in_default_book(t, card_type="cost", metric_name="input_tokens",
                             rate_per_unit_micros=2_000, unit_quantity=1_000_000)
        rate_in_default_book(t, card_type="cost", provider="openai",
                             metric_name="input_tokens",
                             rate_per_unit_micros=9_000, unit_quantity=1_000_000)
        assert self._price(t, c, provider="openai")[0] == 9_000

    def test_wildcard_still_applies_to_other_providers(self):
        t, c = self._tc()
        rate_in_default_book(t, card_type="cost", metric_name="input_tokens",
                             rate_per_unit_micros=2_000, unit_quantity=1_000_000)
        rate_in_default_book(t, card_type="cost", provider="openai",
                             metric_name="input_tokens",
                             rate_per_unit_micros=9_000, unit_quantity=1_000_000)
        assert self._price(t, c, provider="anthropic")[0] == 2_000

    def test_more_pinned_selectors_wins(self):
        t, c = self._tc()
        rate_in_default_book(t, card_type="cost", provider="openai",
                             metric_name="input_tokens",
                             rate_per_unit_micros=5_000, unit_quantity=1_000_000)
        rate_in_default_book(t, card_type="cost", provider="openai",
                             task_type="year_end_close", metric_name="input_tokens",
                             rate_per_unit_micros=1_000, unit_quantity=1_000_000)
        assert self._price(t, c, provider="openai",
                           task_type="year_end_close")[0] == 1_000

    def test_non_matching_pinned_selector_excludes_the_rate(self):
        t, c = self._tc()
        rate_in_default_book(t, card_type="cost", provider="openai",
                             dim1="eu-west-1", metric_name="input_tokens",
                             rate_per_unit_micros=1_000, unit_quantity=1_000_000)
        prov, _, p = self._price(t, c, provider="openai", dim1="us-east-1")
        assert prov == 0 and p["uncosted_metrics"] == ["input_tokens"]

    def test_task_type_can_price_a_kind_of_job(self):
        t, c = self._tc()
        rate_in_default_book(t, card_type="price", task_type="year_end_close",
                             metric_name="input_tokens",
                             rate_per_unit_micros=7_000, unit_quantity=1_000_000)
        _, billed, p = self._price(t, c, task_type="year_end_close")
        assert billed == 7_000 and p["price_source"] == "rate_card"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/metering/pricing/tests/test_wildcard_resolution.py -v`
Expected: FAIL — `PricingService.price() got an unexpected keyword argument 'selectors'`

- [ ] **Step 3: Rewrite resolution**

Delete `_dimensions_match` (lines 31-36). Replace `_resolve_rate_within` and
`_resolve_card`:

```python
    @staticmethod
    def _resolve_rate_within(book, selectors, metric_name, currency, as_of):
        """One matching semantic for all ten selectors (design D3).

        A rate's "" selector is a WILDCARD; a pinned selector must equal the
        event's value. Among matches the most-pinned rate wins, tie-broken by
        latest valid_from. `metric_name` alone keeps exact-match semantics —
        pricing is per-metric and a metric wildcard would be meaningless.
        """
        if book is None:
            return None
        qs = Rate.objects.filter(
            rate_card=book, metric_name=metric_name, currency=currency,
            valid_from__lte=as_of,
        ).filter(Q(valid_to__isnull=True) | Q(valid_to__gt=as_of))
        for name in Rate.SELECTORS:
            qs = qs.filter(Q(**{name: selectors.get(name) or ""}) | Q(**{name: ""}))
        cands = list(qs)
        if not cands:
            return None
        cands.sort(key=lambda c: (c.specificity, c.valid_from), reverse=True)
        return cands[0]

    @staticmethod
    def _resolve_card(tenant, customer, card_type, selectors, metric_name,
                      currency, as_of):
        book = PricingService._assigned_book(tenant, customer, card_type, currency)
        if book is not None:
            rate = PricingService._resolve_rate_within(
                book, selectors, metric_name, currency, as_of)
            if rate is not None:
                return rate
        default_book = PricingService._default_book(
            tenant, card_type, selectors.get("provider"), currency)
        return PricingService._resolve_rate_within(
            default_book, selectors, metric_name, currency, as_of)
```

Change `price` and `estimate` to take `selectors: dict` in place of
`event_type`/`provider`/`tags`, and pass it through their `resolve_card` closures. Their
bodies are otherwise unchanged — `_compute` never touched the selectors.

- [ ] **Step 4: Update the two callers**

`usage_service.py:339-344` (`PricingService.price`) and the estimation path both build a
`selectors` dict from the `RecordingInput` fields:

```python
                selectors = {"provider": inp.provider, "event_type": inp.event_type,
                             "task_type": inp.task_type,
                             "subtask_type": inp.subtask_type,
                             "dim1": inp.dim1, "dim2": inp.dim2, "dim3": inp.dim3,
                             "dim4": inp.dim4, "dim5": inp.dim5, "dim6": inp.dim6}
```

- [ ] **Step 5: Run the tests**

```bash
DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/metering -v
```
Expected: 6 new passed; metering green.

- [ ] **Step 6: Commit**

```bash
git add apps/metering
git commit -m "feat(pricing): wildcard selectors with specificity ranking, one matching rule"
```

---

## Task 13: Dimension-keyed rate cache

**Files:**
- Modify: `apps/metering/pricing/services/card_cache.py:61-86`
- Modify: `apps/metering/pricing/tests/test_card_cache.py`
- Create: `apps/metering/pricing/tests/test_card_cache_dimensions.py`

**Interfaces:**
- Consumes: `PricingService._resolve_card(selectors=...)` (Task 12)
- Produces: `CardCache.resolve(tenant, customer, card_type, selectors, metric, currency)`
  — no `tags`, no bypass

- [ ] **Step 1: Write the failing test**

```python
# apps/metering/pricing/tests/test_card_cache_dimensions.py
import pytest
from django.test.utils import CaptureQueriesContext
from django.db import connection
from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.metering.pricing.services import card_cache as card_cache_module
from apps.metering.pricing.services.card_cache import CardCache
from apps.metering.pricing.tests._helpers import rate_in_default_book


def _sel(**kw):
    base = {"provider": "", "event_type": "", "task_type": "", "subtask_type": "",
            "dim1": "", "dim2": "", "dim3": "", "dim4": "", "dim5": "", "dim6": ""}
    base.update(kw)
    return base


@pytest.mark.django_db
class TestCardCacheDimensions:
    def _tc(self):
        """Reset via the module-private _l1 and begin_request, matching the
        convention the existing test_card_cache.py uses (lines 52, 62)."""
        t = Tenant.objects.create(name="T")
        c = Customer.objects.create(tenant=t, external_id="c1")
        rate_in_default_book(t, card_type="cost", provider="openai", dim1="eu",
                             metric_name="input_tokens", rate_per_unit_micros=1_000,
                             unit_quantity=1_000_000)
        card_cache_module._l1.clear()
        CardCache.begin_request(t.id)
        return t, c

    def test_dimension_bearing_resolution_is_cached(self):
        """Before this change CardCache bypassed L1 whenever tags were present
        (card_cache.py:67-73), so every dimension-bearing event hit Postgres.
        Bounded cardinality (design D4) is what makes the key safe."""
        t, c = self._tc()
        sel = _sel(provider="openai", dim1="eu")
        CardCache.resolve(t, c, "cost", sel, "input_tokens", "usd")
        with CaptureQueriesContext(connection) as ctx:
            CardCache.resolve(t, c, "cost", sel, "input_tokens", "usd")
        assert len(ctx) == 0, "second resolve must be served from L1"

    def test_different_dimension_values_do_not_collide(self):
        t, c = self._tc()
        hit = CardCache.resolve(t, c, "cost", _sel(provider="openai", dim1="eu"),
                                "input_tokens", "usd")
        miss = CardCache.resolve(t, c, "cost", _sel(provider="openai", dim1="us"),
                                 "input_tokens", "usd")
        assert hit is not None and miss is None

    def test_invalidation_forces_a_re_resolve(self):
        """invalidate() bumps the Redis version counter; a NEW request observes
        the bump via begin_request, which is what stales the L1 entry."""
        t, c = self._tc()
        sel = _sel(provider="openai", dim1="eu")
        CardCache.resolve(t, c, "cost", sel, "input_tokens", "usd")
        CardCache.invalidate(t.id)
        CardCache.begin_request(t.id)
        with CaptureQueriesContext(connection) as ctx:
            CardCache.resolve(t, c, "cost", sel, "input_tokens", "usd")
        assert len(ctx) > 0, "a version bump must force a re-resolve"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/metering/pricing/tests/test_card_cache_dimensions.py -v`
Expected: FAIL — `resolve()` still takes `provider, event_type, ..., tags`

- [ ] **Step 3: Rewrite `resolve`**

```python
# apps/metering/pricing/services/card_cache.py — replace resolve entirely
    @staticmethod
    def resolve(tenant, customer, card_type, selectors, metric, currency):
        """Resolve with PricingService._resolve_card semantics, always via L1.

        The old implementation bypassed the cache whenever `tags` were present,
        because an unbounded tag keyspace would poison a tag-less key — which
        meant every dimension-bearing event hit Postgres. Dimensions are now
        declared and cardinality-capped (design D4), so the selector tuple is a
        bounded, safe cache key and the bypass is gone.

        Returned Rate instances are shared cache objects — callers must NOT
        mutate them.
        """
        from django.utils import timezone
        from apps.metering.pricing.models import Rate
        from apps.metering.pricing.services.pricing_service import PricingService

        sel_tuple = tuple(selectors.get(s) or "" for s in Rate.SELECTORS)
        ver = _ctx_versions.get({}).get(str(tenant.id), 0)
        key = (str(tenant.id), str(customer.id) if customer else "",
               card_type, metric, currency, sel_tuple)
        hit = _l1.get(key)
        if hit and hit[0] == ver and hit[1] > time.monotonic():
            return hit[2]
        rate = PricingService._resolve_card(
            tenant, customer, card_type, selectors, metric, currency,
            timezone.now())
        if len(_l1) >= _L1_MAX:
            _l1.clear()  # crude bound; entries repopulate within one TTL
        _l1[key] = (ver, time.monotonic() + TTL_SECONDS, rate)
        return rate
```

- [ ] **Step 4: Update the estimation caller**

`pricing_service.py:201-203` (`estimate`'s `resolve_card` closure) passes `selectors`
instead of `provider, event_type, ..., tags`.

- [ ] **Step 5: Run the tests**

```bash
DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/metering/pricing api/v1/tests/test_ingest_endpoint.py -v
```
Expected: 3 new passed. One existing case asserts the behaviour this task deletes:
`test_dimensioned_card_bypasses_l1_for_different_tag_sets`
(`apps/metering/pricing/tests/test_card_cache.py:87`). Rewrite it as
`test_dimensioned_card_is_cached_per_selector_set` — same setup, inverted assertion — rather
than deleting it, so the file still documents what happens to dimension-bearing
resolutions.

- [ ] **Step 6: Commit**

```bash
git add apps/metering/pricing
git commit -m "perf(pricing): dimension-keyed L1 cache, tag bypass removed"
```

---

## Task 14: Task read endpoints

**Files:**
- Modify: `apps/platform/tasks/queries.py` (add `task_detail`, `task_page_queryset`)
- Modify: `api/v1/schemas.py` (`TaskOut`, `TaskDetailOut`, `PaginatedTasks`, `task_out`)
- Modify: `api/v1/metering_endpoints.py` (two routes)
- Create: `api/v1/tests/test_task_reads.py`

**Interfaces:**
- Consumes: `Task.task_type`, `.subtask_type`, `.dim1..dim6` (Tasks 5, 6)
- Produces: `GET /api/v1/metering/tasks`, `GET /api/v1/metering/tasks/{task_id}`

- [ ] **Step 1: Write the failing test**

```python
# api/v1/tests/test_task_reads.py
import pytest
from apps.platform.tasks.models import Task


@pytest.mark.django_db
class TestTaskReads:
    def _tree(self, tenant, customer):
        parent = Task.objects.create(
            tenant=tenant, customer=customer, balance_snapshot_micros=0,
            task_type="invoice_batch", dim1="eu-west-1",
            provider_cost_limit_micros=5_000_000,
            total_provider_cost_micros=2_010_000,
            total_billed_cost_micros=2_480_000, event_count=412)
        Task.objects.create(
            tenant=tenant, customer=customer, parent=parent,
            balance_snapshot_micros=0, subtask_type="ocr",
            total_provider_cost_micros=1_740_000, event_count=340)
        return parent

    def test_detail_returns_rollups_and_subtasks(self, client, tenant, customer,
                                                 api_headers):
        parent = self._tree(tenant, customer)
        r = client.get(f"/api/v1/metering/tasks/{parent.id}", **api_headers)
        assert r.status_code == 200
        body = r.json()
        assert body["task_type"] == "invoice_batch"
        assert body["total_provider_cost_micros"] == 2_010_000
        assert len(body["subtasks"]) == 1
        assert body["subtasks"][0]["subtask_type"] == "ocr"

    def test_list_returns_top_level_tasks_only(self, client, tenant, customer,
                                               api_headers):
        self._tree(tenant, customer)
        r = client.get("/api/v1/metering/tasks", **api_headers)
        assert r.status_code == 200
        assert [t["task_type"] for t in r.json()["results"]] == ["invoice_batch"]

    def test_list_filters_by_task_type(self, client, tenant, customer, api_headers):
        self._tree(tenant, customer)
        Task.objects.create(tenant=tenant, customer=customer,
                            balance_snapshot_micros=0, task_type="receipt_scan")
        r = client.get("/api/v1/metering/tasks?task_type=receipt_scan", **api_headers)
        assert [t["task_type"] for t in r.json()["results"]] == ["receipt_scan"]

    def test_foreign_task_is_404(self, client, other_tenant_task, api_headers):
        r = client.get(f"/api/v1/metering/tasks/{other_tenant_task.id}", **api_headers)
        assert r.status_code == 404
```

Add an `other_tenant_task` fixture to `api/v1/tests/conftest.py` creating a `Task` under a
second tenant.

- [ ] **Step 2: Run test to verify it fails**

Run: `DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest api/v1/tests/test_task_reads.py -v`
Expected: FAIL — 404 on both routes

- [ ] **Step 3: Add the schemas**

```python
# api/v1/schemas.py
class TaskOut(Schema):
    task_id: str
    parent_task_id: Optional[str] = None
    task_type: str = ""
    subtask_type: str = ""
    status: str
    total_provider_cost_micros: int
    total_billed_cost_micros: int
    event_count: int
    provider_cost_limit_micros: Optional[int] = None
    dimensions: dict = Field(default_factory=dict)
    created_at: str
    completed_at: Optional[str] = None


def task_out(t):
    """TaskOut's serializer — the per-unit cost receipt, read straight off the
    materialized rollups the accumulate primitive maintains."""
    return {
        "task_id": str(t.id),
        "parent_task_id": str(t.parent_id) if t.parent_id else None,
        "task_type": t.task_type, "subtask_type": t.subtask_type,
        "status": t.status,
        "total_provider_cost_micros": t.total_provider_cost_micros,
        "total_billed_cost_micros": t.total_billed_cost_micros,
        "event_count": t.event_count,
        "provider_cost_limit_micros": t.provider_cost_limit_micros,
        "dimensions": {s: getattr(t, s) for s in
                       ("dim1", "dim2", "dim3", "dim4", "dim5", "dim6")
                       if getattr(t, s)},
        "created_at": t.created_at.isoformat(),
        "completed_at": t.completed_at.isoformat() if t.completed_at else None,
    }


class TaskDetailOut(TaskOut):
    subtasks: list[TaskOut] = Field(default_factory=list)


class PaginatedTasks(Paginated[TaskOut]):
    pass
```

- [ ] **Step 4: Add the routes**

```python
# api/v1/metering_endpoints.py — after the close_task route
@metering_router.get("/tasks", response=PaginatedTasks)
@role_floor(READ)
def list_tasks(request, cursor: str = None, limit: int = None,
               customer_id: UUIDIdentifier = None, task_type: str = None,
               status: str = None):
    """Top-level units of work with their materialized cost rollups.

    Subtasks are omitted — they belong to their parent's detail view, so a
    listing counts JOBS, not steps."""
    _product_check(request)
    from apps.platform.tasks.models import Task

    qs = Task.objects.filter(tenant=request.auth.tenant, parent__isnull=True)
    if customer_id:
        qs = qs.filter(customer_id=customer_id)
    if task_type:
        qs = qs.filter(task_type=task_type)
    if status:
        qs = qs.filter(status=status)
    return page(qs, cursor, limit, serialize=task_out, time_field="created_at")


@metering_router.get("/tasks/{task_id}", response={200: TaskDetailOut, 404: ProblemOut})
@role_floor(READ)
def get_task(request, task_id: UUID):
    """One unit's cost receipt plus its subtask tree.

    Reads the rollups `TaskService.accumulate_cost` maintains — including events
    that landed after a kill (tasks/models.py:22-25) — so this never aggregates
    ubb_usage_event. One indexed row read plus its children."""
    _product_check(request)
    from apps.platform.tasks.models import Task

    task = get_object_or_404(Task, id=task_id, tenant=request.auth.tenant)
    body = task_out(task)
    body["subtasks"] = [task_out(s) for s in
                        task.subtasks.all().order_by("created_at")]
    return 200, body
```

- [ ] **Step 5: Run test to verify it passes**

Run: `DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest api/v1/tests/test_task_reads.py -v`
Expected: 4 passed

- [ ] **Step 6: Regenerate the spec and commit**

```bash
DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python scripts/export_openapi.py
git add api/v1 apps/platform/tasks openapi/v1.json
git commit -m "feat(api): task read endpoints over the materialized rollups"
```

---

## Task 15: Analytics on declared dimensions, filter by task

**Files:**
- Modify: `api/v1/metering_endpoints.py:196-212` (usage list), `401`, `404-557`
  (`usage_analytics`), `559-584` (timeseries)
- Modify: `apps/metering/queries.py:281,320-359`
- Modify: `apps/subscriptions/api/margin_endpoints.py:85-98`
- Create: `api/v1/tests/test_analytics_dimensions.py`

**Interfaces:**
- Consumes: `slot_map` (Task 2), the ten selector columns (Task 8)
- Produces: `dimensions=` accepting declared keys and reserved keys; `task_id` /
  `include_subtasks` filters; `group_by` as a real string on `/margin/by-dimension`

- [ ] **Step 1: Write the failing test**

```python
# api/v1/tests/test_analytics_dimensions.py
import pytest
from apps.metering.usage.models import UsageEvent
from apps.platform.dimensions.models import DimensionDef
from apps.platform.tasks.models import Task


@pytest.mark.django_db
class TestAnalyticsDimensions:
    def _seed(self, tenant, customer):
        DimensionDef.objects.create(tenant=tenant, key="region", slot="dim1",
                                    scope="task")
        parent = Task.objects.create(tenant=tenant, customer=customer,
                                     balance_snapshot_micros=0,
                                     task_type="invoice_batch")
        sub = Task.objects.create(tenant=tenant, customer=customer, parent=parent,
                                  balance_snapshot_micros=0, subtask_type="ocr")
        for i, (task, dim1, cost) in enumerate([
                (parent, "eu-west-1", 1_000), (sub, "eu-west-1", 2_000),
                (sub, "us-east-1", 4_000)]):
            UsageEvent.objects.create(
                tenant=tenant, customer=customer, request_id=f"r{i}",
                idempotency_key=f"k{i}", provider="aws_textract",
                event_type="ocr_page", task_id=task.id,
                task_type="invoice_batch",
                subtask_type=task.subtask_type, dim1=dim1,
                provider_cost_micros=cost, billed_cost_micros=cost * 2)
        return parent, sub

    def test_group_by_declared_key_name(self, client, tenant, customer, api_headers):
        self._seed(tenant, customer)
        r = client.get("/api/v1/metering/analytics/usage?dimensions=region",
                       **api_headers)
        assert r.status_code == 200
        rows = {x["dimension"]: x["total_provider_cost_micros"]
                for x in r.json()["breakdowns"]["region"]}
        assert rows == {"eu-west-1": 3_000, "us-east-1": 4_000}

    def test_group_by_reserved_subtask_type(self, client, tenant, customer,
                                           api_headers):
        self._seed(tenant, customer)
        r = client.get("/api/v1/metering/analytics/usage?dimensions=subtask_type",
                       **api_headers)
        rows = {x["dimension"]: x["total_provider_cost_micros"]
                for x in r.json()["breakdowns"]["subtask_type"]}
        assert rows == {"ocr": 6_000, "(unattributed)": 1_000}

    def test_undeclared_key_is_422(self, client, tenant, customer, api_headers):
        self._seed(tenant, customer)
        r = client.get("/api/v1/metering/analytics/usage?dimensions=nope",
                       **api_headers)
        assert r.status_code == 422
        assert "unknown dimension" in r.json()["detail"]

    def test_task_id_as_a_dimension_is_422(self, client, tenant, customer,
                                           api_headers):
        """Correlation ids are filter-only (design D9) — grouping by one would
        build a bucket per run."""
        self._seed(tenant, customer)
        r = client.get("/api/v1/metering/analytics/usage?dimensions=task_id",
                       **api_headers)
        assert r.status_code == 422

    def test_task_id_filter_scopes_to_one_unit(self, client, tenant, customer,
                                               api_headers):
        parent, sub = self._seed(tenant, customer)
        r = client.get(f"/api/v1/metering/analytics/usage?task_id={parent.id}",
                       **api_headers)
        assert r.json()["total_provider_cost_micros"] == 1_000

    def test_include_subtasks_rolls_the_tree_up(self, client, tenant, customer,
                                                api_headers):
        parent, sub = self._seed(tenant, customer)
        r = client.get(f"/api/v1/metering/analytics/usage?task_id={parent.id}"
                       "&include_subtasks=true", **api_headers)
        assert r.json()["total_provider_cost_micros"] == 7_000

    def test_usage_list_filters_by_task(self, client, tenant, customer, api_headers):
        parent, sub = self._seed(tenant, customer)
        r = client.get(f"/api/v1/metering/customers/{customer.id}/usage"
                       f"?task_id={sub.id}", **api_headers)
        assert len(r.json()["results"]) == 2

    def test_margin_group_by_any_declared_key(self, client, tenant, customer,
                                              api_headers):
        self._seed(tenant, customer)
        r = client.get("/api/v1/margin/by-dimension?group_by=subtask_type",
                       **api_headers)
        assert r.status_code == 200
        assert {x["dimension"] for x in r.json()["rows"]} == {"ocr"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest api/v1/tests/test_analytics_dimensions.py -v`
Expected: FAIL — `dimensions=region` is rejected as an unknown dimension because the
allowlist is still the hardcoded `_ANALYTICS_ALLOWED_COLS`

- [ ] **Step 3: Replace the allowlist with the registry**

```python
# api/v1/metering_endpoints.py — replace _ANALYTICS_ALLOWED_COLS
# The four reserved dimensions (design D1) plus "customer", which is a column
# on the event rather than a slot. Tenant keys come from the registry.
_RESERVED_ANALYTICS_DIMS = ("provider", "event_type", "task_type", "subtask_type",
                            "customer")


def _resolve_dimension(tenant, dim):
    """Map a requested dimension name to the column to GROUP BY.

    Reserved names map to themselves; declared tenant keys map to their slot.
    Anything else — notably a correlation id like task_id (design D9) — is a
    422, so an unbounded key can never become a group-by.
    """
    from apps.platform.dimensions.queries import slot_map

    if dim in _RESERVED_ANALYTICS_DIMS:
        return "customer__external_id" if dim == "customer" else dim
    slot = slot_map(tenant.id).get(dim)
    if slot is None:
        raise Problem("validation_error", f"unknown dimension {dim!r}")
    return slot
```

In `usage_analytics`, replace the `dimensions` loop body: drop the `tag:` branch entirely
(tags are no longer groupable — design "What this deletes"), call `_resolve_dimension`,
and keep the existing `(unattributed)` sentinel mapping and the `total_billed_cost_micros`
ordering. Replace the unconditional `by_product` block with `by_task_type` grouping on
`task_type`. Do the same registry lookup in the timeseries route's `group_by` validation.

- [ ] **Step 4: Add the task filters**

```python
# api/v1/metering_endpoints.py — a shared helper, used by both the usage list
# and usage_analytics
def _apply_task_filter(qs, tenant, task_id, include_subtasks):
    """Correlation-id filtering (design D9). With include_subtasks the whole
    tree is in scope — one extra indexed query for the child ids, since
    containment is a single level."""
    if task_id is None:
        return qs
    from apps.platform.tasks.models import Task

    ids = [task_id]
    if include_subtasks:
        ids += list(Task.objects.filter(
            tenant=tenant, parent_id=task_id).values_list("id", flat=True))
    return qs.filter(task_id__in=ids)
```

Add `task_id: UUID = None, include_subtasks: bool = False` to both `list_usage`
(line 196) and `usage_analytics` (line 406) and call the helper after the existing
filters.

- [ ] **Step 5: Widen the margin group_by**

```python
# apps/metering/queries.py — replace the group_by guard at 354-355
    valid = ("provider", "event_type", "task_type", "subtask_type",
             "dim1", "dim2", "dim3", "dim4", "dim5", "dim6")
    if group_by not in valid:
        raise ValueError(f"group_by must be one of {valid}")
```

```python
# apps/subscriptions/api/margin_endpoints.py — replace margin_by_dimension
@margin_router.get("/by-dimension", response={200: MarginByDimensionOut,
                                             422: ProblemOut})
@role_floor(READ)
def margin_by_dimension(request, group_by: str = "provider",
                        start_date: date = None, end_date: date = None):
    """Margin by any declared dimension.

    Replaces the old `provider: int` / `product: int` pseudo-flags, which could
    not reach event_type at all despite get_dimensional_margin supporting it."""
    _product_check(request)
    s, e = _window(start_date, end_date)
    from apps.metering.queries import get_dimensional_margin
    from apps.platform.dimensions.queries import slot_map

    col = group_by
    if group_by not in ("provider", "event_type", "task_type", "subtask_type"):
        col = slot_map(request.auth.tenant.id).get(group_by)
        if col is None:
            raise Problem("validation_error", f"unknown dimension {group_by!r}")
    try:
        rows = get_dimensional_margin(request.auth.tenant.id, group_by=col,
                                      start_date=s, end_date=e)
    except ValueError as exc:
        raise Problem("validation_error", str(exc))
    return 200, {"period": {"start": s.isoformat(), "end": e.isoformat()},
                 "rows": rows}
```

- [ ] **Step 6: Run the tests**

```bash
DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest api/v1/tests/test_analytics_dimensions.py apps/metering apps/subscriptions/tests -v
```
Expected: 8 new passed; metering green.

- [ ] **Step 7: Regenerate the spec and commit**

```bash
DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python scripts/export_openapi.py
git add api/v1 apps/metering apps/subscriptions openapi/v1.json
git commit -m "feat(analytics): group by declared dimensions, filter by task"
```

---

## Task 16: Task analytics — unit economics

**Files:**
- Modify: `apps/platform/tasks/queries.py` (add `task_rollup_by_type`)
- Modify: `api/v1/schemas.py` (`TaskAnalyticsOut`)
- Modify: `api/v1/metering_endpoints.py` (one route)
- Create: `api/v1/tests/test_task_analytics.py`

**Interfaces:**
- Consumes: `Task.task_type` (Task 5)
- Produces: `apps.platform.tasks.queries.task_rollup_by_type(tenant_id, start_date,
  end_date) -> list[dict]` with keys `task_type`, `run_count`,
  `avg_provider_cost_micros`, `p95_provider_cost_micros`, `total_provider_cost_micros`,
  `limit_hit_count`; `GET /api/v1/metering/analytics/tasks`

- [ ] **Step 1: Write the failing test**

```python
# api/v1/tests/test_task_analytics.py
import pytest
from apps.platform.tasks.models import Task


@pytest.mark.django_db
class TestTaskAnalytics:
    def _seed(self, tenant, customer):
        for cost in (1_000, 2_000, 3_000, 100_000):
            Task.objects.create(
                tenant=tenant, customer=customer, balance_snapshot_micros=0,
                task_type="invoice_batch", status="completed",
                provider_cost_limit_micros=50_000,
                total_provider_cost_micros=cost, event_count=1)
        Task.objects.create(
            tenant=tenant, customer=customer, balance_snapshot_micros=0,
            task_type="receipt_scan", status="completed",
            total_provider_cost_micros=500, event_count=1)

    def test_rollup_by_task_type(self, client, tenant, customer, api_headers):
        self._seed(tenant, customer)
        r = client.get("/api/v1/metering/analytics/tasks?group_by=task_type",
                       **api_headers)
        assert r.status_code == 200
        rows = {x["task_type"]: x for x in r.json()["rows"]}
        assert rows["invoice_batch"]["run_count"] == 4
        assert rows["invoice_batch"]["avg_provider_cost_micros"] == 26_500
        assert rows["receipt_scan"]["run_count"] == 1

    def test_p95_is_reported(self, client, tenant, customer, api_headers):
        self._seed(tenant, customer)
        r = client.get("/api/v1/metering/analytics/tasks?group_by=task_type",
                       **api_headers)
        rows = {x["task_type"]: x for x in r.json()["rows"]}
        assert rows["invoice_batch"]["p95_provider_cost_micros"] >= 3_000

    def test_limit_hits_are_counted(self, client, tenant, customer, api_headers):
        self._seed(tenant, customer)
        r = client.get("/api/v1/metering/analytics/tasks?group_by=task_type",
                       **api_headers)
        rows = {x["task_type"]: x for x in r.json()["rows"]}
        assert rows["invoice_batch"]["limit_hit_count"] == 1

    def test_subtasks_are_excluded_from_run_counts(self, client, tenant, customer,
                                                  api_headers):
        self._seed(tenant, customer)
        parent = Task.objects.filter(tenant=tenant, task_type="invoice_batch").first()
        Task.objects.create(tenant=tenant, customer=customer, parent=parent,
                            balance_snapshot_micros=0, subtask_type="ocr",
                            total_provider_cost_micros=999)
        r = client.get("/api/v1/metering/analytics/tasks?group_by=task_type",
                       **api_headers)
        rows = {x["task_type"]: x for x in r.json()["rows"]}
        assert rows["invoice_batch"]["run_count"] == 4

    def test_invalid_group_by_is_422(self, client, tenant, customer, api_headers):
        r = client.get("/api/v1/metering/analytics/tasks?group_by=nope",
                       **api_headers)
        assert r.status_code == 422
```

- [ ] **Step 2: Run test to verify it fails**

Run: `DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest api/v1/tests/test_task_analytics.py -v`
Expected: FAIL — 404, the route does not exist

- [ ] **Step 3: Add the query**

```python
# apps/platform/tasks/queries.py — append at MODULE level, above the function
class PercentileCont(Aggregate):
    """p95 over a grouped column. Postgres-only, which matches the project —
    DATABASE_URL is Postgres and GinIndex is already in use at
    apps/metering/usage/models.py:83."""
    function = "PERCENTILE_CONT"
    name = "PercentileCont"
    template = "%(function)s(0.95) WITHIN GROUP (ORDER BY %(expressions)s)"
    output_field = models.BigIntegerField()


def task_rollup_by_type(tenant_id, *, start_date=None, end_date=None,
                        group_by="task_type") -> list[dict]:
    """Unit economics per KIND of job — the number that sets a price.

    Aggregates ubb_task rows, never ubb_usage_event: per-unit costs are already
    materialized by the accumulate primitive, with subtask spend rolled into its
    parent. Top-level units only, so run_count counts JOBS not steps.
    """
    if group_by not in ("task_type", "subtask_type"):
        raise ValueError("group_by must be task_type or subtask_type")

    qs = Task.objects.filter(tenant_id=tenant_id)
    qs = qs.filter(parent__isnull=True) if group_by == "task_type" \
        else qs.filter(parent__isnull=False)
    if start_date:
        qs = qs.filter(created_at__gte=start_date)
    if end_date:
        qs = qs.filter(created_at__lt=end_date)

    rows = (qs.exclude(**{group_by: ""})
            .values(group_by)
            .annotate(
                run_count=Count("id"),
                total_provider_cost_micros=Sum("total_provider_cost_micros"),
                total_billed_cost_micros=Sum("total_billed_cost_micros"),
                avg_provider_cost_micros=Avg("total_provider_cost_micros"),
                p95_provider_cost_micros=PercentileCont("total_provider_cost_micros"),
                limit_hit_count=Count("id", filter=Q(
                    provider_cost_limit_micros__isnull=False,
                    total_provider_cost_micros__gte=F("provider_cost_limit_micros"))),
            )
            .order_by("-total_provider_cost_micros"))

    return [{"task_type": r[group_by],
             "run_count": r["run_count"],
             "total_provider_cost_micros": r["total_provider_cost_micros"] or 0,
             "total_billed_cost_micros": r["total_billed_cost_micros"] or 0,
             "avg_provider_cost_micros": int(r["avg_provider_cost_micros"] or 0),
             "p95_provider_cost_micros": int(r["p95_provider_cost_micros"] or 0),
             "limit_hit_count": r["limit_hit_count"]}
            for r in rows]
```

Add to the module's imports at the top of `apps/platform/tasks/queries.py`:

```python
from django.db import models
from django.db.models import Avg, Count, F, Q, Sum
from django.db.models.aggregates import Aggregate
```

- [ ] **Step 4: Add the schema and route**

```python
# api/v1/schemas.py
class TaskAnalyticsRow(Schema):
    task_type: str
    run_count: int
    total_provider_cost_micros: int
    total_billed_cost_micros: int
    avg_provider_cost_micros: int
    p95_provider_cost_micros: int
    limit_hit_count: int


class TaskAnalyticsOut(Schema):
    group_by: str
    rows: list[TaskAnalyticsRow]
```

```python
# api/v1/metering_endpoints.py
@metering_router.get("/analytics/tasks", response={200: TaskAnalyticsOut,
                                                  422: ProblemOut})
@role_floor(READ)
def task_analytics(request, group_by: str = "task_type", start_date: date = None,
                   end_date: date = None):
    """Cost per KIND of job: run count, mean, p95, and limit hits.

    A p95 approaching the type's ceiling is the signal that the limit is about
    to start biting real customers."""
    _product_check(request)
    from apps.platform.tasks.queries import task_rollup_by_type

    if start_date and end_date:
        if end_date < start_date:
            raise Problem("validation_error",
                          "end_date must not precede start_date")
        if (end_date - start_date).days > REPORT_WINDOW_MAX_DAYS:
            raise Problem("validation_error", "date window must not exceed 366 days")
    try:
        rows = task_rollup_by_type(
            request.auth.tenant.id, group_by=group_by,
            start_date=utc_day_start(start_date) if start_date else None,
            end_date=utc_next_day_start(end_date) if end_date else None)
    except ValueError as exc:
        raise Problem("validation_error", str(exc))
    return 200, {"group_by": group_by, "rows": rows}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest api/v1/tests/test_task_analytics.py -v`
Expected: 5 passed

- [ ] **Step 6: Regenerate the spec and commit**

```bash
DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python scripts/export_openapi.py
git add api/v1 apps/platform/tasks openapi/v1.json
git commit -m "feat(analytics): per-task-type unit economics rollup"
```

---

## Task 17: ADR, boundary gate, full suite

**Files:**
- Create: `docs/adr/0005-declared-dimensions.md`
- Create: `apps/platform/tests/test_dimension_invariants.py`
- Modify: `apps/metering/CONTEXT.md`, `apps/platform/CONTEXT.md`, `CONTEXT-MAP.md`

**Interfaces:**
- Consumes: everything above

- [ ] **Step 1: Write the invariant test**

```python
# apps/platform/tests/test_dimension_invariants.py
"""Tests backing ADR-0005, in the manner ADR-001 establishes: the hard rules
are enforced here, not merely documented."""
import pytest
from apps.platform.tenants.models import Tenant
from apps.platform.dimensions.models import DimensionDef
from apps.platform.dimensions.services import DimensionError, DimensionService


@pytest.mark.django_db
class TestDimensionInvariants:
    def _t(self):
        return Tenant.objects.create(name="T")

    def test_slot_rebinding_is_refused(self):
        t = self._t()
        DimensionService.declare(t, key="region", slot="dim1", scope="task")
        with pytest.raises(DimensionError, match="immutable"):
            DimensionService.declare(t, key="region", slot="dim4", scope="task")

    def test_scope_change_is_refused(self):
        t = self._t()
        DimensionService.declare(t, key="region", slot="dim1", scope="task")
        with pytest.raises(DimensionError, match="immutable"):
            DimensionService.declare(t, key="region", slot="dim1", scope="event")

    def test_cardinality_cannot_be_lowered(self):
        t = self._t()
        DimensionService.declare(t, key="region", slot="dim1", scope="task",
                                 max_cardinality=100)
        with pytest.raises(DimensionError, match="lowered"):
            DimensionService.declare(t, key="region", slot="dim1", scope="task",
                                     max_cardinality=99)

    def test_every_correlation_id_is_refused_as_a_dimension(self):
        t = self._t()
        from apps.platform.dimensions.models import FORBIDDEN_KEYS
        for key in FORBIDDEN_KEYS:
            with pytest.raises(DimensionError, match="correlation"):
                DimensionService.declare(t, key=key, slot="dim1", scope="event")

    def test_every_reserved_key_is_refused_as_a_dimension(self):
        t = self._t()
        from apps.platform.dimensions.models import RESERVED_KEYS
        for key in RESERVED_KEYS:
            with pytest.raises(DimensionError, match="reserved"):
                DimensionService.declare(t, key=key, slot="dim1", scope="event")

    def test_retired_def_stays_in_the_slot_map(self):
        """Retirement blocks new VALUES, not reads — historical rows must stay
        groupable (design D8)."""
        from django.utils import timezone
        from apps.platform.dimensions.queries import slot_map
        t = self._t()
        DimensionService.declare(t, key="region", slot="dim1", scope="task")
        DimensionDef.objects.filter(tenant=t, key="region").update(
            retired_at=timezone.now())
        assert slot_map(t.id)["region"] == "dim1"

    def test_usage_event_and_rate_share_one_selector_vocabulary(self):
        """The unification (design D3): one word list, both sides."""
        from apps.metering.pricing.models import Rate
        from apps.metering.usage.models import UsageEvent
        event_cols = {f.name for f in UsageEvent._meta.get_fields()}
        for selector in Rate.SELECTORS:
            assert selector in event_cols, (
                f"Rate selects on {selector!r} but UsageEvent has no such column")
```

- [ ] **Step 2: Run it**

Run: `DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/platform/tests/test_dimension_invariants.py -v`
Expected: 7 passed

- [ ] **Step 3: Write the ADR**

```markdown
<!-- docs/adr/0005-declared-dimensions.md -->
# ADR-0005: Dimensions are declared, bounded, and slot-bound

**Status:** accepted
**Date:** 2026-07-27
**Design:** `docs/plans/2026-07-27-unified-dimension-model-design.md`

## Context

UBB had three mechanisms for "what axis is this spend on" — named columns, `tags` JSONB, and
`Rate.dimensions` JSONB — with two different matching semantics on a single query, an
unbounded keyspace that forced the rate cache to bypass itself on any dimension-bearing
event, and a write contract that returned fields it could not accept.

## Decision

One per-tenant `DimensionDef` registry is the sole vocabulary for analytics grouping and
rate selection. Four reserved keys (`provider`, `event_type`, `task_type`, `subtask_type`)
plus six tenant slots (`dim1`..`dim6`) exist as indexed columns on both `UsageEvent` and
`Rate`. In a `Rate`, `""` is a wildcard and the most-pinned match wins.

**Invariants (enforced by `apps/platform/tests/test_dimension_invariants.py`):**

1. `DimensionDef.slot` is immutable. Re-slotting would silently change the meaning of every
   historical row in that column.
2. `DimensionDef.scope` is immutable. Changing it changes inheritance, so old and new rows
   would disagree about where a value came from.
3. `max_cardinality` may be raised, never lowered.
4. Retirement blocks new values; it never removes a def from the slot map, so historical
   rows stay groupable.
5. Correlation identifiers (`task_id`, `subtask_id`, `request_id`, `idempotency_key`,
   `customer_id`, `event_id`) can never be declared as dimensions. They are filter
   parameters; grouping by one builds a bucket per occurrence.
6. Reserved keys can never be bound to a tenant slot.
7. Every `Rate.SELECTORS` name exists as a `UsageEvent` column — one vocabulary, both sides.

## Consequences

- `tags` becomes what its docstring always claimed: free-form labels, never grouped, never
  priced.
- A bounded keyspace lets `CardCache` key on dimensions, so dimension-bearing events are
  cacheable for the first time.
- A seventh tenant axis requires a migration. Deliberate: six is generous, and adding
  columns later is the expensive move.
- `Task.task_type` is immutable for the same reason `Task.parent` is — `accumulate_cost`
  reads it without a lock.
```

- [ ] **Step 4: Fold into the living docs**

Per the CLAUDE.md ratchet:
- `apps/platform/CONTEXT.md` — add **Dimension**, **Slot**, **Scope**, **Task type**,
  **Subtask type** to the glossary, each one sentence, pointing at ADR-0005
- `apps/metering/CONTEXT.md` — update **Rate**, **Selector**, **Specificity**; delete the
  **Reserved tag key** entry
- `CONTEXT-MAP.md` — add the `apps/platform/dimensions` row

- [ ] **Step 5: Run the boundary gate and the full suite**

```bash
DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/platform/tests/test_product_boundaries.py -v
DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python manage.py check
DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest --tb=short -q
```

Expected: boundaries pass; `check` clean; full suite shows only the 27 pre-existing
`apps/billing/invoicing` + `apps/subscriptions` failures noted in Global Constraints. Any
other failure is yours — fix before committing.

- [ ] **Step 6: Commit**

```bash
git add docs/adr apps/platform CONTEXT-MAP.md apps/metering/CONTEXT.md
git commit -m "docs: ADR-0005 declared dimensions, with enforcing tests"
```

---

## Self-Review

**Spec coverage** — every design decision maps to a task:

| Decision | Task |
|---|---|
| D1 one declared vocabulary | 1, 2, 3 |
| D2 indexed slots not JSONB | 8, 11 |
| D3 `""` wildcard + specificity | 11, 12 |
| D4 cardinality enforced on write | 2, 9 |
| D5 dimension-keyed rate cache | 13 |
| D6 scope + inheritance | 6, 10 |
| D7 `task_type` registry with policy | 4, 5, 6, 7 |
| D8 registry mutability rules | 2, 17 |
| D9 correlation ids are filter-only | 15, 17 |
| "What this deletes" | 8 (`RESERVED_DIM_KEYS`), 9 (tag lifting), 11 (JSONB), 12 (`_dimensions_match`), 13 (bypass), 15 (margin pseudo-flags) |

**Naming consistency, checked across tasks:** `dim1`..`dim6` on `UsageEvent` (8), `Rate`
(11), and `Task` (6). `Rate.SELECTORS` is the single ordered tuple, consumed by Task 12's
resolution, Task 13's cache key, and Task 17's invariant test. `DimensionService.admit`
returns `{slot: value}` in Task 2 and is consumed under that shape by Tasks 6 and 9.
`_inherit_dimensions` (10) returns the ten keys the create site spreads.

**Two things a reviewer should push on:**

1. **Task 8 is a wide mechanical rename** touching ~12 files with a long test blast
   radius. It is one commit because a half-renamed column set does not run. If the
   executing agent wants it split, the only safe seam is model-plus-migration first, then
   call sites — but the suite is red in between.
2. **Task 16's `PercentileCont`** hard-codes Postgres. That matches the project (`DATABASE_URL`
   is Postgres and `GinIndex` is already in use at `usage/models.py:83`), but it is the
   first raw window function in a `queries.py` and worth a second look.

---

**Plan complete and saved to `docs/plans/2026-07-27-unified-dimension-model-plan.md`**
(repo convention per CLAUDE.md, alongside the design doc). Two execution options:

**1. Subagent-Driven (recommended)** — a fresh subagent per task, review between tasks, fast
iteration.

**2. Inline Execution** — execute tasks in this session using executing-plans, batch
execution with checkpoints.
