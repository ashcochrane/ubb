# Plan as a Kernel Concept — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move `Plan` out of `apps/subscriptions/` into the platform kernel, give it a third commercial axis (markup on metered compute), retire the `subscriptions` product flag, and collapse the tenant-facing surface to one Plans page.

**Architecture:** A plan has three axes — access fee, per-seat fee, markup. The first two are realized by Stripe (licensed Prices on a Subscription); the third is realized by UBB's rating engine and Stripe cannot represent it. Because `Plan` has two consumers (subscriptions and metering) and ADR-001 forbids direct product↔product imports, `Plan` moves to `apps/platform/plans/`, which every product may import. Design doc: `docs/plans/2026-07-27-plan-as-kernel-design.md`.

**Tech Stack:** Django 6.0, django-ninja, pytest, Celery, PostgreSQL, React + TanStack Router + vitest (UI).

## Global Constraints

- Money is integer **micros**: `1_000_000` = 1 major unit; cents = micros / 10_000.
- Markup percentage is **`markup_percentage_micros`, where `1_000_000 == 1%`** (so 20% = `20_000_000`).
- Run the backend suite from `ubb-platform/`: `DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest`
- Run the UI suite from `apps/ui/`: `pnpm test`
- All models inherit `core.models.BaseModel` (UUID pk + timestamps).
- Import discipline (ADR-001) is load-bearing. Products may import `apps.platform.*` and `core.*` freely; product↔product only via outbox / `queries.py` / `ports.py` / platform hooks. Enforced by `apps/platform/tests/test_product_boundaries.py`.
- Every API surface change requires regenerating the committed spec: `.venv/bin/python scripts/export_openapi.py` (ADR-002).
- **Pre-launch: no production data.** Clean removal — no `SeparateDatabaseAndState`, no compatibility shims, no data migrations.
- Work on a fresh branch off `origin/main` (the current branch carries unmerged independent work).

---

## File Structure

**Create:**
- `ubb-platform/apps/platform/plans/{__init__,apps,models,queries,services,admin}.py` — the kernel module
- `ubb-platform/apps/platform/plans/migrations/{__init__,0001_initial}.py`
- `ubb-platform/apps/platform/plans/tests/{__init__,test_models,test_services,test_queries}.py`
- `ubb-platform/api/v1/plan_endpoints.py` — the `/api/v1/plans` router
- `ubb-platform/api/v1/tests/test_plan_endpoints.py`
- `apps/ui/src/features/plans/` — the Plans page feature
- `apps/ui/src/app/routes/_app/plans/index.tsx`

**Modify:**
- `ubb-platform/apps/metering/pricing/services/markup_service.py` — the precedence chain
- `ubb-platform/apps/metering/pricing/services/markup_cache.py` — invalidation on plan writes
- `ubb-platform/apps/subscriptions/models.py` — delete `TenantBillingPlan`, repoint `CustomerSubscriptionItem.plan`
- `ubb-platform/apps/subscriptions/orchestration/service.py` — kernel `Plan`, zero-axis guard
- `ubb-platform/apps/subscriptions/api/endpoints.py` — lifecycle verbs land here
- `ubb-platform/api/v1/platform_endpoints.py` — plan + lifecycle routes leave
- `ubb-platform/apps/platform/tenants/models.py` — retire the `subscriptions` flag
- `ubb-platform/config/settings.py` — `INSTALLED_APPS` + the mirror reconciler

---

## Task 1: The kernel plans module

**Files:**
- Create: `ubb-platform/apps/platform/plans/__init__.py`, `apps.py`, `models.py`, `admin.py`
- Create: `ubb-platform/apps/platform/plans/migrations/__init__.py`
- Create: `ubb-platform/apps/platform/plans/tests/__init__.py`, `tests/test_models.py`
- Modify: `ubb-platform/config/settings.py:38` (add to `INSTALLED_APPS` after `apps.platform.dimensions`)

**Interfaces:**
- Consumes: nothing (first task).
- Produces: `apps.platform.plans.models.Plan` and `apps.platform.plans.models.CustomerPlanAssignment`. `Plan` exposes `markup_percentage_micros: int`, `fixed_uplift_micros: int`, `access_fee_micros: int`, `per_seat_micros: int`, `key: str`, `interval: str`, `archived_at: datetime | None`, plus the Stripe binding fields. `CustomerPlanAssignment` exposes `customer`, `plan`, `assigned_at`.

- [ ] **Step 1: Write the failing model tests**

Create `ubb-platform/apps/platform/plans/tests/test_models.py`:

```python
import pytest
from django.db import IntegrityError

from apps.platform.customers.models import Customer
from apps.platform.plans.models import Plan, CustomerPlanAssignment
from apps.platform.tenants.models import Tenant


@pytest.mark.django_db
class TestPlan:
    def _t(self):
        return Tenant.objects.create(name="T", products=["metering", "billing"])

    def test_key_unique_per_tenant(self):
        t = self._t()
        Plan.objects.create(tenant=t, key="pro", name="Pro")
        with pytest.raises(IntegrityError):
            Plan.objects.create(tenant=t, key="pro", name="Pro Again")

    def test_same_key_allowed_across_tenants(self):
        a, b = self._t(), self._t()
        Plan.objects.create(tenant=a, key="pro", name="Pro")
        Plan.objects.create(tenant=b, key="pro", name="Pro")
        assert Plan.objects.count() == 2

    def test_defaults_are_a_zero_fee_zero_markup_plan(self):
        t = self._t()
        p = Plan.objects.create(tenant=t, key="lite", name="Lite")
        assert p.access_fee_micros == 0
        assert p.per_seat_micros == 0
        assert p.markup_percentage_micros == 0
        assert p.fixed_uplift_micros == 0
        assert p.interval == "month"
        assert p.archived_at is None

    def test_personal_lite_shape_is_representable(self):
        # $0 access, $0 seat, 50% markup — the plan with no Stripe presence.
        t = self._t()
        p = Plan.objects.create(tenant=t, key="personal-lite", name="Personal Lite",
                                markup_percentage_micros=50_000_000)
        assert p.has_stripe_axes is False

    def test_enterprise_shape_has_stripe_axes(self):
        t = self._t()
        p = Plan.objects.create(tenant=t, key="enterprise", name="Enterprise",
                                access_fee_micros=100_000_000,
                                per_seat_micros=10_000_000,
                                markup_percentage_micros=20_000_000)
        assert p.has_stripe_axes is True


@pytest.mark.django_db
class TestCustomerPlanAssignment:
    def _t(self):
        return Tenant.objects.create(name="T", products=["metering", "billing"])

    def test_one_assignment_per_customer(self):
        t = self._t()
        c = Customer.objects.create(tenant=t, external_id="c1")
        a = Plan.objects.create(tenant=t, key="a", name="A")
        b = Plan.objects.create(tenant=t, key="b", name="B")
        CustomerPlanAssignment.objects.create(tenant=t, customer=c, plan=a)
        with pytest.raises(IntegrityError):
            CustomerPlanAssignment.objects.create(tenant=t, customer=c, plan=b)
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/platform/plans/tests/test_models.py -v
```

Expected: collection error — `ModuleNotFoundError: No module named 'apps.platform.plans'`.

- [ ] **Step 3: Create the module scaffolding**

`apps/platform/plans/__init__.py` — empty file.
`apps/platform/plans/migrations/__init__.py` — empty file.
`apps/platform/plans/tests/__init__.py` — empty file.

`apps/platform/plans/apps.py`:

```python
from django.apps import AppConfig


class PlansConfig(AppConfig):
    name = "apps.platform.plans"
    label = "plans"
```

- [ ] **Step 4: Write the models**

`apps/platform/plans/models.py`:

```python
from django.db import models

from core.models import BaseModel

INTERVAL_CHOICES = [("month", "Month"), ("year", "Year")]


class Plan(BaseModel):
    """A tenant's commercial offer, with three axes.

    Two axes are realized by Stripe (licensed Prices on a Subscription);
    the third — markup on metered compute — Stripe cannot represent, because
    it has no knowledge of provider cost. That is why Plan is a kernel
    concept: subscriptions and metering each realize one part of it, and
    neither owns it (ADR-001 rule 1 — any product may import apps.platform.*).

    The stripe_* fields are an OPAQUE external binding: the kernel stores
    them and never interprets them. Only apps/subscriptions reads or writes
    them.
    """
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE,
                               related_name="plans")
    key = models.SlugField(max_length=64)
    name = models.CharField(max_length=255)

    # Stripe-realized axes. 0 means "this axis is absent", not "free" — an
    # absent axis produces no Stripe Price and no subscription item.
    access_fee_micros = models.BigIntegerField(default=0)
    per_seat_micros = models.BigIntegerField(default=0)
    interval = models.CharField(max_length=5, choices=INTERVAL_CHOICES, default="month")

    # UBB-realized axis. Units match TenantMarkup exactly: 1_000_000 == 1%.
    markup_percentage_micros = models.BigIntegerField(default=0)
    fixed_uplift_micros = models.BigIntegerField(default=0)

    # Opaque Stripe binding — written only by apps/subscriptions.
    stripe_access_product_id = models.CharField(max_length=255, blank=True, default="")
    stripe_access_price_id = models.CharField(max_length=255, blank=True, default="")
    stripe_seat_product_id = models.CharField(max_length=255, blank=True, default="")
    stripe_seat_price_id = models.CharField(max_length=255, blank=True, default="")
    provisioned_at = models.DateTimeField(null=True, blank=True)
    # Bumped once per re-price of a provisioned axis. Stripe Prices are
    # immutable, so a fee edit mints a NEW Price and existing subscribers are
    # grandfathered on the old one unless explicitly migrated. Markup has no
    # Stripe object and is therefore always live — the asymmetry is deliberate.
    pricing_version = models.PositiveIntegerField(default=1)

    archived_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "ubb_plan"
        constraints = [
            models.UniqueConstraint(fields=["tenant", "key"], name="uq_plan_tenant_key"),
        ]

    def __str__(self):
        return f"Plan({self.key})"

    @property
    def has_stripe_axes(self) -> bool:
        """True when this plan charges a fee Stripe must bill.

        False for a markup-only plan (e.g. $0 access + 50% markup), which has
        no Stripe Product, Price, or Subscription at all.
        """
        return self.access_fee_micros > 0 or self.per_seat_micros > 0


class CustomerPlanAssignment(BaseModel):
    """Which plan a customer is on.

    This row — not the Stripe subscription — is the source of truth for plan
    membership, which is what lets a markup-only customer be on a real plan
    with zero presence in Stripe Billing.
    """
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE,
                               related_name="plan_assignments")
    customer = models.ForeignKey("customers.Customer", on_delete=models.CASCADE,
                                 related_name="plan_assignments")
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT,
                             related_name="assignments")
    assigned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "ubb_customer_plan_assignment"
        constraints = [
            models.UniqueConstraint(fields=["tenant", "customer"],
                                    name="uq_plan_assignment_customer"),
        ]

    def __str__(self):
        return f"CustomerPlanAssignment({self.customer_id} -> {self.plan_id})"
```

- [ ] **Step 5: Register the app and generate the migration**

Add `"apps.platform.plans",` to `INSTALLED_APPS` in `ubb-platform/config/settings.py` immediately after `"apps.platform.dimensions",` (line 38).

```bash
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python manage.py makemigrations plans
```

Expected: creates `apps/platform/plans/migrations/0001_initial.py` with both models.

- [ ] **Step 6: Write the admin**

`apps/platform/plans/admin.py`:

```python
from django.contrib import admin

from apps.platform.plans.models import CustomerPlanAssignment, Plan


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = ("key", "name", "tenant", "access_fee_micros",
                    "per_seat_micros", "markup_percentage_micros", "archived_at")
    list_filter = ("tenant", "interval")
    search_fields = ("key", "name")


@admin.register(CustomerPlanAssignment)
class CustomerPlanAssignmentAdmin(admin.ModelAdmin):
    list_display = ("customer", "plan", "assigned_at")
    list_filter = ("tenant",)
```

- [ ] **Step 7: Run the tests to verify they pass**

```bash
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/platform/plans/tests/test_models.py -v
```

Expected: 7 passed.

- [ ] **Step 8: Verify the boundary test still passes**

```bash
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/platform/tests/test_product_boundaries.py -v
```

Expected: all pass. The kernel imports no product.

- [ ] **Step 9: Commit**

```bash
git add ubb-platform/apps/platform/plans ubb-platform/config/settings.py
git commit -m "feat(plans): Plan and CustomerPlanAssignment in the platform kernel"
```

---

## Task 2: Read contract and service

**Files:**
- Create: `ubb-platform/apps/platform/plans/queries.py`
- Create: `ubb-platform/apps/platform/plans/services.py`
- Create: `ubb-platform/apps/platform/plans/tests/test_queries.py`, `tests/test_services.py`

**Interfaces:**
- Consumes: `Plan`, `CustomerPlanAssignment` from Task 1.
- Produces:
  - `queries.get_plan_markup_for_customer(tenant_id, customer_id) -> dict | None` returning `{"markup_percentage_micros": int, "fixed_uplift_micros": int}` — the plain-data contract metering reads in Task 3.
  - `queries.get_plan_by_key(tenant_id, key) -> Plan | None`
  - `queries.list_plans(tenant_id, include_archived=False) -> list[Plan]`
  - `services.PlanService.assign(tenant, customer, plan) -> CustomerPlanAssignment`
  - `services.PlanService.archive(plan) -> None` raising `PlanInUse` when assignments exist.

- [ ] **Step 1: Write the failing tests**

Create `ubb-platform/apps/platform/plans/tests/test_queries.py`:

```python
import pytest

from apps.platform.customers.models import Customer
from apps.platform.plans import queries
from apps.platform.plans.models import CustomerPlanAssignment, Plan
from apps.platform.tenants.models import Tenant


@pytest.mark.django_db
class TestPlanQueries:
    def setup_method(self):
        self.tenant = Tenant.objects.create(name="T", products=["metering", "billing"])
        self.customer = Customer.objects.create(tenant=self.tenant, external_id="c1")

    def test_markup_for_unassigned_customer_is_none(self):
        assert queries.get_plan_markup_for_customer(
            self.tenant.id, self.customer.id) is None

    def test_markup_for_assigned_customer_is_plain_data(self):
        plan = Plan.objects.create(tenant=self.tenant, key="lite", name="Lite",
                                   markup_percentage_micros=50_000_000,
                                   fixed_uplift_micros=1_000)
        CustomerPlanAssignment.objects.create(
            tenant=self.tenant, customer=self.customer, plan=plan)
        assert queries.get_plan_markup_for_customer(self.tenant.id, self.customer.id) == {
            "markup_percentage_micros": 50_000_000,
            "fixed_uplift_micros": 1_000,
        }

    def test_archived_plan_yields_no_markup(self):
        from django.utils import timezone
        plan = Plan.objects.create(tenant=self.tenant, key="old", name="Old",
                                   markup_percentage_micros=50_000_000,
                                   archived_at=timezone.now())
        CustomerPlanAssignment.objects.create(
            tenant=self.tenant, customer=self.customer, plan=plan)
        assert queries.get_plan_markup_for_customer(
            self.tenant.id, self.customer.id) is None

    def test_list_plans_excludes_archived_by_default(self):
        from django.utils import timezone
        Plan.objects.create(tenant=self.tenant, key="live", name="Live")
        Plan.objects.create(tenant=self.tenant, key="gone", name="Gone",
                            archived_at=timezone.now())
        assert [p.key for p in queries.list_plans(self.tenant.id)] == ["live"]
        assert len(queries.list_plans(self.tenant.id, include_archived=True)) == 2

    def test_get_plan_by_key(self):
        Plan.objects.create(tenant=self.tenant, key="pro", name="Pro")
        assert queries.get_plan_by_key(self.tenant.id, "pro").name == "Pro"
        assert queries.get_plan_by_key(self.tenant.id, "nope") is None
```

Create `ubb-platform/apps/platform/plans/tests/test_services.py`:

```python
import pytest

from apps.platform.customers.models import Customer
from apps.platform.plans.models import CustomerPlanAssignment, Plan
from apps.platform.plans.services import PlanInUse, PlanService
from apps.platform.tenants.models import Tenant


@pytest.mark.django_db
class TestPlanService:
    def setup_method(self):
        self.tenant = Tenant.objects.create(name="T", products=["metering", "billing"])
        self.customer = Customer.objects.create(tenant=self.tenant, external_id="c1")

    def test_assign_creates_the_row(self):
        plan = Plan.objects.create(tenant=self.tenant, key="pro", name="Pro")
        PlanService.assign(self.tenant, self.customer, plan)
        assert CustomerPlanAssignment.objects.filter(
            tenant=self.tenant, customer=self.customer, plan=plan).exists()

    def test_reassign_moves_the_customer_rather_than_duplicating(self):
        a = Plan.objects.create(tenant=self.tenant, key="a", name="A")
        b = Plan.objects.create(tenant=self.tenant, key="b", name="B")
        PlanService.assign(self.tenant, self.customer, a)
        PlanService.assign(self.tenant, self.customer, b)
        rows = CustomerPlanAssignment.objects.filter(customer=self.customer)
        assert rows.count() == 1
        assert rows.first().plan_id == b.id

    def test_archive_marks_the_plan(self):
        plan = Plan.objects.create(tenant=self.tenant, key="pro", name="Pro")
        PlanService.archive(plan)
        plan.refresh_from_db()
        assert plan.archived_at is not None

    def test_archive_refuses_an_assigned_plan(self):
        plan = Plan.objects.create(tenant=self.tenant, key="pro", name="Pro")
        PlanService.assign(self.tenant, self.customer, plan)
        with pytest.raises(PlanInUse):
            PlanService.archive(plan)
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/platform/plans/tests/test_queries.py apps/platform/plans/tests/test_services.py -v
```

Expected: `ModuleNotFoundError: No module named 'apps.platform.plans.queries'`.

- [ ] **Step 3: Write the read contract**

`apps/platform/plans/queries.py`:

```python
"""Plans read contract — plain data for product consumers.

Metering reads markup through this module rather than touching the ORM, so
the rating hot path depends on a stable shape rather than a model.
"""
from apps.platform.plans.models import CustomerPlanAssignment, Plan


def get_plan_markup_for_customer(tenant_id, customer_id):
    """The markup axis of the customer's plan, or None if unassigned.

    An archived plan yields None: archival must stop it pricing new events.
    """
    row = (
        CustomerPlanAssignment.objects
        .filter(tenant_id=tenant_id, customer_id=customer_id,
                plan__archived_at__isnull=True)
        .select_related("plan")
        .first()
    )
    if row is None:
        return None
    return {
        "markup_percentage_micros": row.plan.markup_percentage_micros,
        "fixed_uplift_micros": row.plan.fixed_uplift_micros,
    }


def get_plan_by_key(tenant_id, key):
    """The tenant's plan with this key, archived or not, or None."""
    return Plan.objects.filter(tenant_id=tenant_id, key=key).first()


def list_plans(tenant_id, include_archived=False):
    """The tenant's plans, oldest first."""
    qs = Plan.objects.filter(tenant_id=tenant_id)
    if not include_archived:
        qs = qs.filter(archived_at__isnull=True)
    return list(qs.order_by("created_at"))
```

- [ ] **Step 4: Write the service**

`apps/platform/plans/services.py`:

```python
"""Plan lifecycle operations that are not plain reads."""
from django.db import transaction
from django.utils import timezone

from apps.platform.plans.models import CustomerPlanAssignment


class PlanInUse(Exception):
    """Raised when archiving a plan that still has assigned customers."""


class PlanService:
    @staticmethod
    @transaction.atomic
    def assign(tenant, customer, plan):
        """Put a customer on a plan, replacing any existing assignment.

        One assignment per customer (DB-enforced), so this is an upsert rather
        than an insert — reassignment moves the customer, never duplicates.
        """
        row, _ = CustomerPlanAssignment.objects.update_or_create(
            tenant=tenant, customer=customer, defaults={"plan": plan},
        )
        return row

    @staticmethod
    def archive(plan):
        """Soft-archive a plan. Refuses while customers are still on it —
        archiving an assigned plan would silently drop their markup to the
        tenant default."""
        if CustomerPlanAssignment.objects.filter(plan=plan).exists():
            raise PlanInUse(f"plan '{plan.key}' still has assigned customers")
        plan.archived_at = timezone.now()
        plan.save(update_fields=["archived_at", "updated_at"])
```

- [ ] **Step 5: Run the tests to verify they pass**

```bash
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/platform/plans/tests/ -v
```

Expected: 16 passed.

- [ ] **Step 6: Commit**

```bash
git add ubb-platform/apps/platform/plans
git commit -m "feat(plans): read contract and PlanService"
```

---

## Task 3: The markup precedence chain

This is the task that closes the revenue leak. `MarkupService.resolve` currently returns a `TenantMarkup` instance; it will now return a `ResolvedMarkup` value object so a plan and a `TenantMarkup` can both answer.

**Files:**
- Modify: `ubb-platform/apps/metering/pricing/services/markup_service.py` (whole file)
- Modify: `ubb-platform/apps/metering/pricing/services/markup_cache.py:61-75`
- Test: `ubb-platform/apps/metering/pricing/tests/test_markup_service.py`

**Interfaces:**
- Consumes: `apps.platform.plans.queries.get_plan_markup_for_customer` from Task 2.
- Produces: `ResolvedMarkup` — a frozen dataclass with `markup_percentage_micros: int`, `fixed_uplift_micros: int`, `source: str` (`"customer"` | `"plan"` | `"tenant_default"`) and `calculate_markup_micros(provider_cost_micros: int) -> int`. `MarkupService.resolve(tenant, customer) -> ResolvedMarkup | None` and `MarkupService.apply(provider_cost_micros, tenant, customer) -> int` keep their names and call signatures.

- [ ] **Step 1: Write the failing tests**

Append to `ubb-platform/apps/metering/pricing/tests/test_markup_service.py`:

```python
import pytest

from apps.metering.pricing.models import TenantMarkup
from apps.metering.pricing.services.markup_service import MarkupService
from apps.platform.customers.models import Customer
from apps.platform.plans.models import CustomerPlanAssignment, Plan
from apps.platform.tenants.models import Tenant


@pytest.mark.django_db
class TestMarkupPrecedenceWithPlans:
    def setup_method(self):
        self.tenant = Tenant.objects.create(name="T", products=["metering", "billing"])
        self.customer = Customer.objects.create(tenant=self.tenant, external_id="c1")

    def _assign(self, key, pct):
        plan = Plan.objects.create(tenant=self.tenant, key=key, name=key,
                                   markup_percentage_micros=pct)
        CustomerPlanAssignment.objects.create(
            tenant=self.tenant, customer=self.customer, plan=plan)
        return plan

    def test_plan_markup_beats_tenant_default(self):
        """THE REVENUE LEAK, PINNED. A Personal Lite customer (50%) must not
        fall through to the tenant default (20%). If this test ever passes
        with 600_000, the plan rung has been lost."""
        TenantMarkup.objects.create(tenant=self.tenant, customer=None,
                                    markup_percentage_micros=20_000_000)
        self._assign("personal-lite", 50_000_000)
        # $0.50 provider cost -> 50% -> $0.75, NOT the default's $0.60.
        assert MarkupService.apply(500_000, self.tenant, self.customer) == 750_000

    def test_customer_override_beats_plan(self):
        self._assign("personal-lite", 50_000_000)
        TenantMarkup.objects.create(tenant=self.tenant, customer=self.customer,
                                    markup_percentage_micros=10_000_000)
        assert MarkupService.apply(500_000, self.tenant, self.customer) == 550_000

    def test_unassigned_customer_falls_through_to_tenant_default(self):
        TenantMarkup.objects.create(tenant=self.tenant, customer=None,
                                    markup_percentage_micros=20_000_000)
        assert MarkupService.apply(500_000, self.tenant, self.customer) == 600_000

    def test_no_markup_anywhere_bills_at_provider_cost(self):
        assert MarkupService.apply(500_000, self.tenant, self.customer) == 500_000

    def test_resolve_reports_its_source(self):
        self._assign("personal-lite", 50_000_000)
        assert MarkupService.resolve(self.tenant, self.customer).source == "plan"

    def test_plan_fixed_uplift_is_applied(self):
        plan = Plan.objects.create(tenant=self.tenant, key="p", name="P",
                                   markup_percentage_micros=20_000_000,
                                   fixed_uplift_micros=7_000)
        CustomerPlanAssignment.objects.create(
            tenant=self.tenant, customer=self.customer, plan=plan)
        assert MarkupService.apply(500_000, self.tenant, self.customer) == 607_000

    def test_enterprise_and_personal_both_rate_at_twenty_percent(self):
        self._assign("enterprise", 20_000_000)
        assert MarkupService.apply(500_000, self.tenant, self.customer) == 600_000
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/metering/pricing/tests/test_markup_service.py::TestMarkupPrecedenceWithPlans -v
```

Expected: `test_plan_markup_beats_tenant_default` FAILS with `assert 600000 == 750000` — the leak, reproduced.

- [ ] **Step 3: Rewrite the markup service**

Replace the whole of `ubb-platform/apps/metering/pricing/services/markup_service.py`:

```python
"""Markup resolution.

Precedence (design doc §5):

    customer TenantMarkup override -> customer's Plan -> tenant default -> none

The plan rung is why a Personal Lite customer (50%) cannot silently bill at
the tenant default (20%). Plans live in the kernel, so reading them here is
an apps.platform.* import, not a cross-product one (ADR-001 rule 1).
"""
from dataclasses import dataclass

from apps.metering.pricing.models import TenantMarkup


@dataclass(frozen=True)
class ResolvedMarkup:
    """The markup that applies to one (tenant, customer), and where it came from.

    Frozen: instances are shared through the L1 cache and must never be mutated
    by a caller. ``source`` is carried for provenance — it answers "why was this
    event priced this way" without re-deriving the chain.
    """
    markup_percentage_micros: int
    fixed_uplift_micros: int
    source: str  # "customer" | "plan" | "tenant_default"

    def calculate_markup_micros(self, provider_cost_micros: int) -> int:
        # Rounding is half-up on the micro, matching TenantMarkup exactly —
        # changing it would silently re-price every event.
        percent = (
            provider_cost_micros * self.markup_percentage_micros + 50_000_000
        ) // 100_000_000
        return percent + self.fixed_uplift_micros


def _from_tenant_markup(row, source):
    return ResolvedMarkup(
        markup_percentage_micros=row.markup_percentage_micros,
        fixed_uplift_micros=row.fixed_uplift_micros,
        source=source,
    )


class MarkupService:
    @staticmethod
    def resolve(tenant, customer):
        """Return the applicable ResolvedMarkup, or None if nothing applies."""
        if customer is not None:
            override = TenantMarkup.objects.filter(
                tenant=tenant, customer=customer).first()
            if override:
                return _from_tenant_markup(override, "customer")

            from apps.platform.plans.queries import get_plan_markup_for_customer
            plan_markup = get_plan_markup_for_customer(tenant.id, customer.id)
            if plan_markup is not None:
                return ResolvedMarkup(source="plan", **plan_markup)

        default = TenantMarkup.objects.filter(
            tenant=tenant, customer__isnull=True).first()
        if default:
            return _from_tenant_markup(default, "tenant_default")
        return None

    @staticmethod
    def apply(provider_cost_micros, tenant, customer):
        """billed = provider + markup(provider); nothing configured -> billed == provider."""
        markup = MarkupService.resolve(tenant, customer)
        if markup is None:
            return provider_cost_micros
        return provider_cost_micros + markup.calculate_markup_micros(provider_cost_micros)
```

- [ ] **Step 4: Update the cache docstring**

In `ubb-platform/apps/metering/pricing/services/markup_cache.py`, replace the `resolve` docstring (line 63-64) — it currently promises `TenantMarkup` instances:

```python
    def resolve(tenant, customer):
        """MarkupService.resolve via the L1 cache. Returns a ResolvedMarkup
        (frozen) or None. Instances are shared cache objects; the frozen
        dataclass makes accidental mutation an error rather than a silent
        cross-request bug."""
```

- [ ] **Step 5: Run the tests to verify they pass**

```bash
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/metering/pricing/tests/ -v
```

Expected: all pass, including the full pre-existing markup and cache suites.

- [ ] **Step 6: Run the boundary test**

```bash
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/platform/tests/test_product_boundaries.py -v
```

Expected: pass — metering imports `apps.platform.plans`, which is always allowed.

- [ ] **Step 7: Commit**

```bash
git add ubb-platform/apps/metering/pricing/services ubb-platform/apps/metering/pricing/tests
git commit -m "feat(pricing): plan markup rung in the precedence chain"
```

---

## Task 4: Invalidate the markup cache on plan writes

The L1 cache is versioned per tenant and bumped by `TenantMarkup.save/delete`. Plan writes and assignment changes must bump it too, or a re-priced plan takes up to `TTL_SECONDS` to take effect.

**Files:**
- Modify: `ubb-platform/apps/platform/plans/models.py` (add `save`/`delete` hooks to both models)
- Test: `ubb-platform/apps/platform/plans/tests/test_cache_invalidation.py` (create)

**Interfaces:**
- Consumes: `Plan`, `CustomerPlanAssignment` (Task 1); `MarkupCache.invalidate` (existing, `markup_cache.py:55`).
- Produces: no new API. Writing a `Plan` or `CustomerPlanAssignment` invalidates that tenant's markup cache.

- [ ] **Step 1: Write the failing test**

Create `ubb-platform/apps/platform/plans/tests/test_cache_invalidation.py`:

```python
from unittest.mock import patch

import pytest

from apps.platform.customers.models import Customer
from apps.platform.plans.models import CustomerPlanAssignment, Plan
from apps.platform.tenants.models import Tenant


@pytest.mark.django_db
class TestMarkupCacheInvalidation:
    def setup_method(self):
        self.tenant = Tenant.objects.create(name="T", products=["metering", "billing"])

    def test_saving_a_plan_invalidates_the_tenant_markup_cache(self):
        target = "apps.metering.pricing.services.markup_cache.MarkupCache.invalidate"
        with patch(target) as invalidate:
            Plan.objects.create(tenant=self.tenant, key="pro", name="Pro")
        invalidate.assert_called_once_with(self.tenant.id)

    def test_assigning_a_plan_invalidates_the_tenant_markup_cache(self):
        plan = Plan.objects.create(tenant=self.tenant, key="pro", name="Pro")
        customer = Customer.objects.create(tenant=self.tenant, external_id="c1")
        target = "apps.metering.pricing.services.markup_cache.MarkupCache.invalidate"
        with patch(target) as invalidate:
            CustomerPlanAssignment.objects.create(
                tenant=self.tenant, customer=customer, plan=plan)
        invalidate.assert_called_once_with(self.tenant.id)

    def test_deleting_an_assignment_invalidates_the_tenant_markup_cache(self):
        plan = Plan.objects.create(tenant=self.tenant, key="pro", name="Pro")
        customer = Customer.objects.create(tenant=self.tenant, external_id="c1")
        row = CustomerPlanAssignment.objects.create(
            tenant=self.tenant, customer=customer, plan=plan)
        target = "apps.metering.pricing.services.markup_cache.MarkupCache.invalidate"
        with patch(target) as invalidate:
            row.delete()
        invalidate.assert_called_once_with(self.tenant.id)
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/platform/plans/tests/test_cache_invalidation.py -v
```

Expected: FAIL — `Expected 'invalidate' to have been called once. Called 0 times.`

- [ ] **Step 3: Add the hooks**

The kernel must not import metering at module scope (ADR-001: platform imports no product). The import is deliberately lazy and inside the method, mirroring `TenantMarkup.save` (`apps/metering/pricing/models.py:38-48`) in reverse.

Add to `Plan` in `apps/platform/plans/models.py`, after `has_stripe_axes`:

```python
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        _invalidate_markup_cache(self.tenant_id)

    def delete(self, *args, **kwargs):
        tenant_id = self.tenant_id
        result = super().delete(*args, **kwargs)
        _invalidate_markup_cache(tenant_id)
        return result
```

Add the identical pair to `CustomerPlanAssignment`.

Add this helper at the bottom of the module:

```python
def _invalidate_markup_cache(tenant_id):
    """Bump the tenant's markup cache version.

    Lazy import: the kernel may not import a product at module scope
    (ADR-001), and metering is an optional consumer of plans. A missing
    metering app must not break a plan write, so the import is best-effort.
    """
    try:
        from apps.metering.pricing.services.markup_cache import MarkupCache
    except ImportError:  # pragma: no cover - metering always installed today
        return
    MarkupCache.invalidate(tenant_id)
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/platform/plans/tests/ -v
```

Expected: 19 passed.

- [ ] **Step 5: Verify the boundary test tolerates the lazy import**

```bash
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/platform/tests/test_product_boundaries.py -v
```

Expected: **This will FAIL.** The AST walker visits function bodies, so the lazy import is caught as `platform-imports-product`. **This concession is blessed by the plan owner (2026-07-27)** — it is the narrowest seam that keeps a re-priced plan from serving stale markup for a full cache TTL. The alternatives (an async outbox event, or accepting the staleness) were considered and rejected. Reviewers: do not re-litigate the seam itself; do check that the allowlist entry is narrow and the comment explains it.

Add `apps/platform/plans/models.py` to `PLATFORM_FILE_ALLOWLIST` in `apps/platform/tests/test_product_boundaries.py:57`, with this comment:

```python
    # plans/models.py bumps metering's markup cache version on write. The kernel
    # owns the Plan; metering owns the cache keyed off it. A lazy, best-effort
    # import is the narrowest seam that keeps a re-priced plan from serving
    # stale markup for a full cache TTL.
    "apps/platform/plans/models.py",
```

Re-run; expected: pass.

- [ ] **Step 6: Commit**

```bash
git add ubb-platform/apps/platform/plans ubb-platform/apps/platform/tests/test_product_boundaries.py
git commit -m "feat(plans): invalidate the markup cache on plan and assignment writes"
```

---

## Task 5: Repoint subscriptions at the kernel Plan

**Files:**
- Modify: `ubb-platform/apps/subscriptions/models.py:84-120` (delete `TenantBillingPlan`, repoint `CustomerSubscriptionItem.plan`)
- Modify: `ubb-platform/apps/subscriptions/orchestration/service.py` (all `TenantBillingPlan` references)
- Modify: `ubb-platform/apps/subscriptions/ports.py:44` (the `line_items__plan__isnull` filter still works — verify only)
- Create: `ubb-platform/apps/subscriptions/migrations/0011_plan_to_kernel.py`
- Test: `ubb-platform/apps/subscriptions/tests/test_plan_models.py`, `apps/subscriptions/orchestration/tests/test_plan_versioning.py`

**Interfaces:**
- Consumes: `apps.platform.plans.models.Plan` (Task 1).
- Produces: `SubscriptionOrchestrator.ensure_plan_provisioned(plan)`, `.subscribe(customer, plan, seats)`, `.set_seats(business, plan, new_seats, *, change_event_id)`, `.update_plan_prices(tenant, plan_key, *, access_fee_micros, per_seat_micros, migrate_existing)` — all unchanged in name and signature, now taking a kernel `Plan`.

- [ ] **Step 1: Update the existing tests to import the kernel Plan**

In `ubb-platform/apps/subscriptions/tests/test_plan_models.py`, `apps/subscriptions/tests/test_sync.py`, `apps/subscriptions/orchestration/tests/test_plan_versioning.py`, `test_service.py`, `test_seat_hooks.py`, and `test_automatic_tax.py`, replace every:

```python
from apps.subscriptions.models import TenantBillingPlan
```

with:

```python
from apps.platform.plans.models import Plan
```

and every `TenantBillingPlan.objects.create(...)` / type reference with `Plan`. Find them all:

```bash
cd ubb-platform && grep -rln "TenantBillingPlan" apps/ api/
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/subscriptions/ -v
```

Expected: failures — `CustomerSubscriptionItem.plan` still points at the old model, so assigning a kernel `Plan` raises `ValueError: Cannot assign ... must be a TenantBillingPlan instance`.

- [ ] **Step 3: Delete the old model and repoint the FK**

In `ubb-platform/apps/subscriptions/models.py`, delete the entire `TenantBillingPlan` class (lines 84-103) and change `CustomerSubscriptionItem.plan`:

```python
    plan = models.ForeignKey("plans.Plan", on_delete=models.SET_NULL,
                             null=True, blank=True)
```

- [ ] **Step 4: Update the orchestrator**

In `ubb-platform/apps/subscriptions/orchestration/service.py`, replace the import:

```python
from apps.platform.plans.models import Plan
```

and change every `plan: TenantBillingPlan` annotation to `plan: Plan`. In `update_plan_prices`, replace the lookup:

```python
        plan = Plan.objects.filter(tenant=tenant, key=plan_key).first()
```

- [ ] **Step 5: Generate the migration**

```bash
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python manage.py makemigrations subscriptions
```

Expected: `0011_...` deleting `TenantBillingPlan` and altering `customersubscriptionitem.plan`. Pre-launch, no data migration — confirm the generated file contains no `RunPython`.

- [ ] **Step 6: Run the tests to verify they pass**

```bash
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/subscriptions/ -v
```

Expected: pass. Note the 27 pre-existing failures in `apps/billing/invoicing` + `apps/subscriptions` documented in project memory — compare against a baseline run on `origin/main` and confirm you have added none.

- [ ] **Step 7: Commit**

```bash
git add ubb-platform/apps/subscriptions
git commit -m "refactor(subscriptions): use the kernel Plan; delete TenantBillingPlan"
```

---

## Task 6: Zero-axis subscribe guard (Personal Lite)

**Files:**
- Modify: `ubb-platform/apps/subscriptions/orchestration/service.py:179-206`
- Test: `ubb-platform/apps/subscriptions/orchestration/tests/test_service.py`

**Interfaces:**
- Consumes: `Plan.has_stripe_axes` (Task 1), `SubscriptionOrchestrator.subscribe` (Task 5).
- Produces: `subscribe()` returns `None` for a markup-only plan instead of calling Stripe. Callers must handle `None` — the API layer does so in Task 8.

- [ ] **Step 1: Write the failing test**

Append to `ubb-platform/apps/subscriptions/orchestration/tests/test_service.py`:

```python
from unittest.mock import patch

import pytest

from apps.platform.customers.models import Customer
from apps.platform.plans.models import Plan
from apps.platform.tenants.models import Tenant
from apps.subscriptions.models import StripeSubscription
from apps.subscriptions.orchestration.service import SubscriptionOrchestrator


@pytest.mark.django_db
class TestMarkupOnlyPlanSubscribe:
    def setup_method(self):
        self.tenant = Tenant.objects.create(
            name="T", products=["metering", "billing"],
            stripe_connected_account_id="acct_test", stripe_charges_enabled=True,
            default_currency="usd")
        self.customer = Customer.objects.create(tenant=self.tenant, external_id="sam-hobby")

    def test_markup_only_plan_creates_no_stripe_objects(self):
        """Personal Lite: $0 access, $0 seat, 50% markup. There is nothing for
        Stripe to bill, so no Product, Price, Subscription, or Customer is
        created — and crucially Stripe is never called with items=[]."""
        plan = Plan.objects.create(tenant=self.tenant, key="personal-lite",
                                   name="Personal Lite",
                                   markup_percentage_micros=50_000_000)
        with patch("apps.subscriptions.orchestration.service.stripe_call") as stripe_call:
            result = SubscriptionOrchestrator.subscribe(self.customer, plan, seats=0)
        assert result is None
        stripe_call.assert_not_called()
        assert not StripeSubscription.objects.filter(customer=self.customer).exists()
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/subscriptions/orchestration/tests/test_service.py::TestMarkupOnlyPlanSubscribe -v
```

Expected: FAIL — `stripe_call` was called (with `items=[]`).

- [ ] **Step 3: Add the guard**

In `ubb-platform/apps/subscriptions/orchestration/service.py`, insert at the top of `subscribe()`, immediately after the docstring and before `tenant = plan.tenant`:

```python
        # A markup-only plan (both Stripe axes zero) has nothing for Stripe to
        # bill. Building items=[] and calling Subscription.create would be
        # rejected by Stripe, which is what made such plans unsellable. Plan
        # membership lives in CustomerPlanAssignment, not here, so returning
        # early leaves the customer correctly on the plan with no Stripe
        # presence at all.
        if not plan.has_stripe_axes:
            return None
```

Note `_require_charge_ready(tenant)` must run *after* this guard, so a markup-only plan works for a tenant with no connected Stripe account.

- [ ] **Step 4: Run the test to verify it passes**

```bash
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/subscriptions/orchestration/tests/ -v
```

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add ubb-platform/apps/subscriptions
git commit -m "fix(subscriptions): markup-only plans subscribe without calling Stripe"
```

---

## Task 7: The `/api/v1/plans` router

**Files:**
- Create: `ubb-platform/api/v1/plan_endpoints.py`
- Create: `ubb-platform/api/v1/tests/test_plan_endpoints.py`
- Modify: `ubb-platform/api/v1/schemas.py:879-901` (replace the Plan schemas)
- Modify: `ubb-platform/api/v1/api.py` (mount the router)
- Modify: `ubb-platform/apps/platform/audit/actions.py:73-74` (add `plan.archived`, `plan.assigned`)

**Interfaces:**
- Consumes: `queries.list_plans`, `queries.get_plan_by_key`, `PlanService.assign`, `PlanService.archive`, `PlanInUse` (Task 2).
- Produces: routes `GET|POST /api/v1/plans`, `GET|PATCH|DELETE /api/v1/plans/{key}`, `POST /api/v1/customers/{external_id}/plan`. `PlanOut` gains `markup_percentage_micros`, `fixed_uplift_micros`, `archived_at`.

- [ ] **Step 1: Write the failing endpoint tests**

Create `ubb-platform/api/v1/tests/test_plan_endpoints.py`:

```python
import pytest
from django.test import Client

from apps.platform.customers.models import Customer
from apps.platform.plans.models import CustomerPlanAssignment, Plan
from apps.platform.tenants.models import Tenant, TenantApiKey


@pytest.mark.django_db
class TestPlanEndpoints:
    def setup_method(self):
        # products=["metering", "billing"] is REQUIRED: plan routes gate on
        # ProductAccess("billing"), so a metering-only tenant gets 403.
        self.tenant = Tenant.objects.create(name="T", products=["metering", "billing"])
        _, self.raw_key = TenantApiKey.create_key(self.tenant)
        self.client = Client()

    def _auth(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {self.raw_key}"}

    def _post(self, path, data):
        return self.client.post(path, data=data, content_type="application/json",
                                **self._auth())

    def _get(self, path):
        return self.client.get(path, **self._auth())

    def test_create_plan_with_all_three_axes(self):
        r = self._post("/api/v1/plans", {
            "key": "enterprise", "name": "Enterprise",
            "access_fee_micros": 100_000_000, "per_seat_micros": 10_000_000,
            "markup_percentage_micros": 20_000_000, "interval": "month"})
        assert r.status_code == 201
        body = r.json()
        assert body["key"] == "enterprise"
        assert body["markup_percentage_micros"] == 20_000_000

    def test_create_markup_only_plan(self):
        r = self._post("/api/v1/plans", {
            "key": "personal-lite", "name": "Personal Lite",
            "markup_percentage_micros": 50_000_000})
        assert r.status_code == 201
        assert r.json()["access_fee_micros"] == 0

    def test_duplicate_key_is_409(self):
        self._post("/api/v1/plans", {"key": "pro", "name": "Pro"})
        r = self._post("/api/v1/plans", {"key": "pro", "name": "Pro"})
        assert r.status_code == 409

    def test_invalid_interval_is_422(self):
        r = self._post("/api/v1/plans", {"key": "p", "name": "P", "interval": "day"})
        assert r.status_code == 422

    def test_list_plans(self):
        Plan.objects.create(tenant=self.tenant, key="a", name="A")
        Plan.objects.create(tenant=self.tenant, key="b", name="B")
        r = self._get("/api/v1/plans")
        assert r.status_code == 200
        assert [p["key"] for p in r.json()["plans"]] == ["a", "b"]

    def test_get_plan_by_key(self):
        Plan.objects.create(tenant=self.tenant, key="pro", name="Pro")
        assert self._get("/api/v1/plans/pro").status_code == 200
        assert self._get("/api/v1/plans/nope").status_code == 404

    def test_patch_updates_markup_without_touching_stripe(self):
        Plan.objects.create(tenant=self.tenant, key="lite", name="Lite",
                            markup_percentage_micros=50_000_000)
        r = self.client.patch("/api/v1/plans/lite",
                              data={"markup_percentage_micros": 60_000_000},
                              content_type="application/json", **self._auth())
        assert r.status_code == 200
        assert r.json()["markup_percentage_micros"] == 60_000_000

    def test_assign_customer_to_plan(self):
        Plan.objects.create(tenant=self.tenant, key="lite", name="Lite")
        Customer.objects.create(tenant=self.tenant, external_id="c1")
        r = self._post("/api/v1/customers/c1/plan", {"plan_key": "lite"})
        assert r.status_code == 200
        assert CustomerPlanAssignment.objects.filter(plan__key="lite").exists()

    def test_archive_refuses_an_assigned_plan(self):
        plan = Plan.objects.create(tenant=self.tenant, key="lite", name="Lite")
        c = Customer.objects.create(tenant=self.tenant, external_id="c1")
        CustomerPlanAssignment.objects.create(tenant=self.tenant, customer=c, plan=plan)
        r = self.client.delete("/api/v1/plans/lite", **self._auth())
        assert r.status_code == 409

    def test_tenant_without_billing_is_403(self):
        other = Tenant.objects.create(name="M", products=["metering"])
        _, key = TenantApiKey.create_key(other)
        r = self.client.get("/api/v1/plans", HTTP_AUTHORIZATION=f"Bearer {key}")
        assert r.status_code == 403
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest api/v1/tests/test_plan_endpoints.py -v
```

Expected: all 404 — the router does not exist.

- [ ] **Step 3: Replace the Plan schemas**

In `ubb-platform/api/v1/schemas.py`, replace `PlanIn`, `PlanOut`, `PlanUpdateIn` (lines 879-901):

```python
class PlanIn(Schema):
    key: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    access_fee_micros: int = Field(default=0, ge=0)
    per_seat_micros: int = Field(default=0, ge=0)
    # 1_000_000 == 1%. Capped at 1000% — a higher value is far more likely a
    # unit error (percent passed as micros) than a real commercial term.
    markup_percentage_micros: int = Field(default=0, ge=0, le=1_000_000_000)
    fixed_uplift_micros: int = Field(default=0, ge=0)
    interval: Literal["month", "year"] = "month"


class PlanOut(Schema):
    id: str
    key: str
    name: str
    access_fee_micros: int
    per_seat_micros: int
    markup_percentage_micros: int
    fixed_uplift_micros: int
    interval: str
    pricing_version: int
    archived_at: Optional[str] = None


class PlanListOut(Schema):
    plans: List[PlanOut]


class PlanUpdateIn(Schema):
    # None = leave the axis alone (0 is a meaningful value, not an omission).
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    access_fee_micros: Optional[int] = Field(default=None, ge=0)
    per_seat_micros: Optional[int] = Field(default=None, ge=0)
    markup_percentage_micros: Optional[int] = Field(default=None, ge=0, le=1_000_000_000)
    fixed_uplift_micros: Optional[int] = Field(default=None, ge=0)
    migrate_existing: bool = False


class AssignPlanIn(Schema):
    plan_key: str
```

Ensure `Literal` and `List` are imported at the top of `schemas.py`; add to the existing `typing` import if absent.

- [ ] **Step 4: Write the router**

Create `ubb-platform/api/v1/plan_endpoints.py`:

```python
"""The plans surface — /api/v1/plans.

Plans are a KERNEL concept (design doc 2026-07-27): a plan's fee axes are
realized by subscriptions via Stripe, its markup axis by metering at rating
time, and neither product owns it. The router lives in the composition layer,
which may import any product.

Gated on ProductAccess("billing"): a plan is a commercial offer, and charging
for one is what the billing product is.
"""
from django.db import IntegrityError, transaction
from ninja import Router

from api.v1.schemas import AssignPlanIn, PlanIn, PlanListOut, PlanOut, PlanUpdateIn
from apps.platform.audit.ledger import record as audit_record
from apps.platform.audit.marker import records_audit
from apps.platform.customers.models import Customer
from apps.platform.plans import queries
from apps.platform.plans.models import Plan
from apps.platform.plans.services import PlanInUse, PlanService
from core.auth import ADMIN, ApiKeyAuth, ProductAccess, READ, WRITE, role_floor
from core.problems import Problem, ProblemOut

plan_router = Router(auth=ApiKeyAuth())

_product_check = ProductAccess("billing")


def _plan_out(plan):
    return {
        "id": str(plan.id),
        "key": plan.key,
        "name": plan.name,
        "access_fee_micros": plan.access_fee_micros,
        "per_seat_micros": plan.per_seat_micros,
        "markup_percentage_micros": plan.markup_percentage_micros,
        "fixed_uplift_micros": plan.fixed_uplift_micros,
        "interval": plan.interval,
        "pricing_version": plan.pricing_version,
        "archived_at": plan.archived_at.isoformat() if plan.archived_at else None,
    }


@plan_router.get("/plans", response={200: PlanListOut})
@role_floor(READ)
def list_plans(request, include_archived: bool = False):
    _product_check(request)
    plans = queries.list_plans(request.auth.tenant.id, include_archived=include_archived)
    return 200, {"plans": [_plan_out(p) for p in plans]}


@plan_router.get("/plans/{key}", response={200: PlanOut, 404: ProblemOut})
@role_floor(READ)
def get_plan(request, key: str):
    _product_check(request)
    plan = queries.get_plan_by_key(request.auth.tenant.id, key)
    if plan is None:
        raise Problem("not_found", f"plan with key '{key}' not found")
    return 200, _plan_out(plan)


@plan_router.post("/plans", response={201: PlanOut, 409: ProblemOut})
@role_floor(ADMIN)
@records_audit("plan.created")
def create_plan(request, payload: PlanIn):
    _product_check(request)
    tenant = request.auth.tenant
    try:
        with transaction.atomic():
            plan = Plan.objects.create(
                tenant=tenant, key=payload.key, name=payload.name,
                access_fee_micros=payload.access_fee_micros,
                per_seat_micros=payload.per_seat_micros,
                markup_percentage_micros=payload.markup_percentage_micros,
                fixed_uplift_micros=payload.fixed_uplift_micros,
                interval=payload.interval,
            )
            audit_record(
                action="plan.created", tenant_id=tenant.id,
                resource_type="plan", resource_id=plan.key,
                metadata=_plan_out(plan))
    except IntegrityError:
        raise Problem("conflict", f"plan with key '{payload.key}' already exists")
    return 201, _plan_out(plan)


@plan_router.patch("/plans/{key}", response={200: PlanOut, 404: ProblemOut, 422: ProblemOut})
@role_floor(ADMIN)
@records_audit("plan.updated")
def update_plan(request, key: str, payload: PlanUpdateIn):
    """Edit a plan.

    The two axis families reprice differently, deliberately:
      - FEE axes are grandfathered. Stripe Prices are immutable, so a fee edit
        mints a new versioned Price and existing subscribers keep the old one
        unless migrate_existing=true.
      - MARKUP is live. It has no Stripe object, so an edit applies to the next
        rated event for every customer on the plan.

    Trials and coupons are deliberate non-goals: Stripe owns those levers.
    """
    from apps.subscriptions.orchestration.service import (
        OrchestrationError, SubscriptionOrchestrator,
    )
    from core.exceptions import StripeFatalError

    _product_check(request)
    tenant = request.auth.tenant
    plan = queries.get_plan_by_key(tenant.id, key)
    if plan is None:
        raise Problem("not_found", f"plan with key '{key}' not found")

    # Markup and name are UBB-side: a plain write, no Stripe involvement.
    fields = []
    if payload.name is not None:
        plan.name = payload.name
        fields.append("name")
    if payload.markup_percentage_micros is not None:
        plan.markup_percentage_micros = payload.markup_percentage_micros
        fields.append("markup_percentage_micros")
    if payload.fixed_uplift_micros is not None:
        plan.fixed_uplift_micros = payload.fixed_uplift_micros
        fields.append("fixed_uplift_micros")
    if fields:
        # Full save(), not update_fields only — the save hook bumps the markup
        # cache version, and a re-priced plan must take effect immediately.
        plan.save()

    # Fee axes go through the orchestrator, which mints versioned Stripe Prices.
    if payload.access_fee_micros is not None or payload.per_seat_micros is not None:
        try:
            plan = SubscriptionOrchestrator.update_plan_prices(
                tenant, key,
                access_fee_micros=payload.access_fee_micros,
                per_seat_micros=payload.per_seat_micros,
                migrate_existing=payload.migrate_existing)
        except (OrchestrationError, StripeFatalError) as e:
            raise Problem("validation_error", str(e))

    audit_record(
        action="plan.updated", tenant_id=tenant.id,
        resource_type="plan", resource_id=plan.key,
        metadata={**_plan_out(plan), "migrate_existing": payload.migrate_existing})
    return 200, _plan_out(plan)


@plan_router.delete("/plans/{key}", response={204: None, 404: ProblemOut, 409: ProblemOut})
@role_floor(ADMIN)
@records_audit("plan.archived")
def archive_plan(request, key: str):
    """Archive a plan. Refused while customers are still assigned — archiving
    an assigned plan would silently drop their markup to the tenant default."""
    _product_check(request)
    tenant = request.auth.tenant
    plan = queries.get_plan_by_key(tenant.id, key)
    if plan is None:
        raise Problem("not_found", f"plan with key '{key}' not found")
    try:
        PlanService.archive(plan)
    except PlanInUse as e:
        raise Problem("conflict", str(e))
    audit_record(
        action="plan.archived", tenant_id=tenant.id,
        resource_type="plan", resource_id=plan.key, metadata={"key": plan.key})
    return 204, None


@plan_router.post("/customers/{external_id}/plan",
                  response={200: dict, 404: ProblemOut})
@role_floor(WRITE)
@records_audit("plan.assigned")
def assign_plan(request, external_id: str, payload: AssignPlanIn):
    """Put a customer on a plan.

    This is the plan-membership write and it never touches Stripe. Starting the
    Stripe subscription for a plan's fee axes is a separate call
    (POST /subscriptions/customers/{external_id}/subscribe), because a
    markup-only plan has no Stripe subscription to start.
    """
    _product_check(request)
    tenant = request.auth.tenant
    customer = Customer.objects.filter(tenant=tenant, external_id=external_id).first()
    if customer is None:
        raise Problem("not_found", "customer not found")
    plan = queries.get_plan_by_key(tenant.id, payload.plan_key)
    if plan is None or plan.archived_at is not None:
        raise Problem("not_found", f"plan with key '{payload.plan_key}' not found")
    PlanService.assign(tenant, customer, plan)
    audit_record(
        action="plan.assigned", tenant_id=tenant.id,
        resource_type="customer", resource_id=customer.external_id,
        metadata={"external_id": customer.external_id, "plan_key": plan.key})
    return 200, {"external_id": customer.external_id, "plan_key": plan.key}
```

- [ ] **Step 5: Register the audit actions**

In `ubb-platform/apps/platform/audit/actions.py`, add after `"plan.updated",` (line 74):

```python
    "plan.archived",
    "plan.assigned",
```

- [ ] **Step 6: Mount the router**

In `ubb-platform/api/v1/api.py`, add the import alongside the others:

```python
from api.v1.plan_endpoints import plan_router
```

and mount it at the root prefix, immediately **before** `api.add_router("", root_router)` (line 79) so its concrete paths bind before the catch-all:

```python
api.add_router("", plan_router)
```

- [ ] **Step 7: Run the tests to verify they pass**

```bash
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest api/v1/tests/test_plan_endpoints.py -v
```

Expected: 10 passed.

- [ ] **Step 8: Commit**

```bash
git add ubb-platform/api/v1 ubb-platform/apps/platform/audit/actions.py
git commit -m "feat(api): /api/v1/plans CRUD with the markup axis"
```

---

## Task 8: Move the lifecycle verbs onto the subscriptions router

**Files:**
- Modify: `ubb-platform/api/v1/platform_endpoints.py` (delete lines 125-389 — the plan and lifecycle routes)
- Modify: `ubb-platform/apps/subscriptions/api/endpoints.py` (add the moved routes)
- Test: `ubb-platform/api/v1/tests/test_subscription_lifecycle.py` (create)

**Interfaces:**
- Consumes: `SubscriptionOrchestrator` (Task 5), `Plan.has_stripe_axes` (Task 6), `queries.get_plan_by_key` (Task 2).
- Produces: `POST /api/v1/subscriptions/customers/{external_id}/{subscribe,seats}` and `.../subscription/{cancel,pause,resume}`, all gated on `ProductAccess("billing")`.

- [ ] **Step 1: Write the failing tests**

Create `ubb-platform/api/v1/tests/test_subscription_lifecycle.py`:

```python
import pytest
from django.test import Client

from apps.platform.customers.models import Customer
from apps.platform.plans.models import Plan
from apps.platform.tenants.models import Tenant, TenantApiKey


@pytest.mark.django_db
class TestLifecycleRoutesMoved:
    def setup_method(self):
        self.tenant = Tenant.objects.create(
            name="T", products=["metering", "billing"],
            stripe_connected_account_id="acct_test", stripe_charges_enabled=True,
            default_currency="usd")
        _, self.raw_key = TenantApiKey.create_key(self.tenant)
        self.client = Client()
        Customer.objects.create(tenant=self.tenant, external_id="c1")
        Plan.objects.create(tenant=self.tenant, key="lite", name="Lite",
                            markup_percentage_micros=50_000_000)

    def _auth(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {self.raw_key}"}

    def _post(self, path, data=None):
        return self.client.post(path, data=data or {},
                                content_type="application/json", **self._auth())

    def test_old_platform_routes_are_gone(self):
        assert self._post("/api/v1/platform/plans",
                          {"key": "x", "name": "X"}).status_code == 404
        assert self._post("/api/v1/platform/customers/c1/subscribe",
                          {"plan_key": "lite"}).status_code == 404

    def test_subscribe_lives_on_the_subscriptions_router(self):
        r = self._post("/api/v1/subscriptions/customers/c1/subscribe",
                       {"plan_key": "lite", "seats": 0})
        # Markup-only plan: assigned, but no Stripe subscription created.
        assert r.status_code == 200
        assert r.json()["subscription_id"] is None

    def test_lifecycle_requires_billing_product(self):
        other = Tenant.objects.create(name="M", products=["metering"])
        _, key = TenantApiKey.create_key(other)
        r = self.client.post("/api/v1/subscriptions/customers/c1/subscribe",
                             data={"plan_key": "lite"},
                             content_type="application/json",
                             HTTP_AUTHORIZATION=f"Bearer {key}")
        assert r.status_code == 403
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest api/v1/tests/test_subscription_lifecycle.py -v
```

Expected: `test_old_platform_routes_are_gone` fails (routes still 201/200); the new-route tests 404.

- [ ] **Step 3: Delete the routes from platform_endpoints.py**

In `ubb-platform/api/v1/platform_endpoints.py`, delete everything from `def _plan_out(plan):` (line 125) to the end of the file (line 389). Keep `create_customer` and `get_business`. Remove the now-unused imports at the top: `PlanIn`, `PlanOut`, `PlanUpdateIn`, `SeatsIn`, `SubscribeIn`, `SubscriptionCancelIn`, `uuid`, `transaction`, `ADMIN`.

- [ ] **Step 4: Add the routes to the subscriptions router**

Append to `ubb-platform/apps/subscriptions/api/endpoints.py`. Note `_product_check` there must become `ProductAccess("billing")` — see Task 9.

```python
# ---------- Lifecycle (moved from platform_router, design doc §6) ----------

import uuid

from api.v1.schemas import SeatsIn, SubscribeIn, SubscriptionCancelIn
from apps.platform.audit.ledger import record as audit_record
from apps.platform.audit.marker import records_audit
from apps.platform.plans import queries as plan_queries

_LIFECYCLE_AUDIT_ACTION = {
    "cancel": "subscription.canceled",
    "pause": "subscription.paused",
    "resume": "subscription.resumed",
}


def _lifecycle_call(request, external_id, verb_kwargs):
    """Shared problem mapping for the subscription lifecycle verbs."""
    from apps.subscriptions.orchestration.service import (
        NoActiveSubscription, OrchestrationError, SubscriptionOrchestrator,
    )
    from core.exceptions import StripeFatalError

    tenant = request.auth.tenant
    customer = Customer.objects.filter(tenant=tenant, external_id=external_id).first()
    if customer is None:
        raise Problem("not_found", "customer not found")

    verb = verb_kwargs.pop("verb")
    change_event_id = str(uuid.uuid4())
    try:
        mirror = getattr(SubscriptionOrchestrator, verb)(
            tenant, customer, change_event_id=change_event_id, **verb_kwargs)
    except NoActiveSubscription as e:
        raise Problem("not_found", str(e))
    except (OrchestrationError, StripeFatalError) as e:
        raise Problem("validation_error", str(e))

    audit_record(
        action=_LIFECYCLE_AUDIT_ACTION[verb], tenant_id=tenant.id,
        resource_type="subscription", resource_id=mirror.stripe_subscription_id,
        metadata={"external_id": customer.external_id, "status": mirror.status,
                  "cancel_at_period_end": mirror.cancel_at_period_end,
                  "paused": mirror.paused, "change_event_id": change_event_id})
    return 200, {
        "subscription_id": mirror.stripe_subscription_id,
        "status": mirror.status,
        "cancel_at_period_end": mirror.cancel_at_period_end,
        "paused": mirror.paused,
    }


@subscriptions_router.post("/customers/{external_id}/subscribe",
                           response={200: dict, 404: ProblemOut, 422: ProblemOut})
@role_floor(WRITE)
@records_audit("subscription.created")
def subscribe_customer(request, external_id: str, payload: SubscribeIn):
    """Assign the customer to the plan and, if the plan has fee axes, start the
    Stripe subscription.

    A markup-only plan assigns and returns subscription_id=None — there is
    nothing for Stripe to bill.
    """
    from apps.platform.plans.services import PlanService
    from apps.subscriptions.orchestration.service import (
        OrchestrationError, SubscriptionOrchestrator,
    )
    from core.exceptions import StripeFatalError

    _product_check(request)
    tenant = request.auth.tenant
    customer = Customer.objects.filter(tenant=tenant, external_id=external_id).first()
    if customer is None:
        raise Problem("not_found", "customer not found")

    plan = plan_queries.get_plan_by_key(tenant.id, payload.plan_key)
    if plan is None or plan.archived_at is not None:
        raise Problem("not_found", f"plan with key '{payload.plan_key}' not found")

    PlanService.assign(tenant, customer, plan)
    try:
        mirror = SubscriptionOrchestrator.subscribe(customer, plan, payload.seats)
    except (OrchestrationError, StripeFatalError) as e:
        raise Problem("validation_error", str(e))

    audit_record(
        action="subscription.created", tenant_id=tenant.id,
        resource_type="subscription",
        resource_id=mirror.stripe_subscription_id if mirror else customer.external_id,
        metadata={"external_id": customer.external_id, "plan_key": plan.key,
                  "seats": payload.seats,
                  "stripe_subscription_created": mirror is not None})
    if mirror is None:
        return 200, {"subscription_id": None, "amount_micros": 0, "quantity": 0}
    return 200, {
        "subscription_id": mirror.stripe_subscription_id,
        "amount_micros": mirror.amount_micros,
        "quantity": mirror.quantity,
    }


@subscriptions_router.post("/customers/{external_id}/seats",
                           response={200: dict, 404: ProblemOut, 422: ProblemOut})
@role_floor(WRITE)
@records_audit("subscription.seats_changed")
def set_customer_seats(request, external_id: str, payload: SeatsIn):
    from apps.subscriptions.models import CustomerSubscriptionItem
    from apps.subscriptions.orchestration.service import (
        OrchestrationError, SubscriptionOrchestrator,
    )

    _product_check(request)
    tenant = request.auth.tenant
    customer = Customer.objects.filter(tenant=tenant, external_id=external_id).first()
    if customer is None:
        raise Problem("not_found", "customer not found")

    business = customer.resolve_billing_owner()
    seat_item = (
        CustomerSubscriptionItem.objects.filter(customer=business, axis="seat")
        .order_by("-created_at").first()
    )
    if seat_item is None or seat_item.plan is None:
        raise Problem("not_found", "no seat subscription item for this customer")

    change_event_id = str(uuid.uuid4())
    try:
        SubscriptionOrchestrator.set_seats(
            business, seat_item.plan, payload.seats, change_event_id=change_event_id)
    except OrchestrationError as e:
        raise Problem("validation_error", str(e))

    audit_record(
        action="subscription.seats_changed", tenant_id=tenant.id,
        resource_type="subscription", resource_id=business.external_id,
        metadata={"external_id": business.external_id, "seats": payload.seats,
                  "change_event_id": change_event_id})
    return 200, {"seats": payload.seats}


@subscriptions_router.post("/customers/{external_id}/subscription/cancel",
                           response={200: dict, 404: ProblemOut, 422: ProblemOut})
@role_floor(WRITE)
@records_audit("subscription.canceled")
def cancel_subscription(request, external_id: str, payload: SubscriptionCancelIn = None):
    """Cancel the customer's subscription (default: at period end).

    Trials and coupons are deliberate non-goals: Stripe owns those levers.
    """
    _product_check(request)
    at_period_end = payload.at_period_end if payload is not None else True
    return _lifecycle_call(request, external_id,
                           {"verb": "cancel", "at_period_end": at_period_end})


@subscriptions_router.post("/customers/{external_id}/subscription/pause",
                           response={200: dict, 404: ProblemOut, 422: ProblemOut})
@role_floor(WRITE)
@records_audit("subscription.paused")
def pause_subscription(request, external_id: str):
    """Pause collection (void) — the subscription stays active but stops billing."""
    _product_check(request)
    return _lifecycle_call(request, external_id, {"verb": "pause"})


@subscriptions_router.post("/customers/{external_id}/subscription/resume",
                           response={200: dict, 404: ProblemOut, 422: ProblemOut})
@role_floor(WRITE)
@records_audit("subscription.resumed")
def resume_subscription(request, external_id: str):
    """Resume billing: clears a pause AND any pending at-period-end cancel."""
    _product_check(request)
    return _lifecycle_call(request, external_id, {"verb": "resume"})
```

- [ ] **Step 5: Run the tests to verify they pass**

```bash
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest api/v1/tests/test_subscription_lifecycle.py api/v1/tests/test_accounts_api.py -v
```

Expected: pass. `test_lifecycle_requires_billing_product` needs Task 9's gate change — if it fails on 403-vs-200, complete Task 9 and re-run.

- [ ] **Step 6: Commit**

```bash
git add ubb-platform/api/v1 ubb-platform/apps/subscriptions/api
git commit -m "refactor(api): lifecycle verbs move to /subscriptions and gate on billing"
```

---

## Task 9: Retire the `subscriptions` product flag

**Files:**
- Modify: `ubb-platform/apps/platform/tenants/models.py:15`
- Modify: `ubb-platform/apps/subscriptions/api/endpoints.py:35`
- Modify: `ubb-platform/apps/platform/tenants/management/commands/seed_dev_data.py`
- Test: `ubb-platform/apps/platform/tenants/tests/test_models.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `VALID_PRODUCTS` no longer contains `"subscriptions"`; a tenant configured with it fails validation.

- [ ] **Step 1: Write the failing test**

Append to `ubb-platform/apps/platform/tenants/tests/test_models.py`:

```python
import pytest
from django.core.exceptions import ValidationError

from apps.platform.tenants.models import VALID_PRODUCTS, Tenant


@pytest.mark.django_db
class TestSubscriptionsFlagRetired:
    def test_subscriptions_is_not_a_valid_product(self):
        assert "subscriptions" not in VALID_PRODUCTS

    def test_configuring_subscriptions_is_rejected(self):
        t = Tenant(name="T", products=["metering", "subscriptions"])
        with pytest.raises(ValidationError):
            t.full_clean()
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/platform/tenants/tests/test_models.py::TestSubscriptionsFlagRetired -v
```

Expected: FAIL — `"subscriptions"` is still in `VALID_PRODUCTS`.

- [ ] **Step 3: Retire the flag**

In `ubb-platform/apps/platform/tenants/models.py:15`:

```python
# "subscriptions" was retired 2026-07-27: it is not a standalone product but a
# capability of billing (a wrapper over Stripe Billing, valuable only next to
# metering and margin). Plans and subscription lifecycle gate on "billing".
VALID_PRODUCTS = {"metering", "billing", "referrals", "metering_async"}
```

In `ubb-platform/apps/subscriptions/api/endpoints.py:35`:

```python
_product_check = ProductAccess("billing")
```

- [ ] **Step 4: Purge remaining references**

```bash
cd ubb-platform && grep -rn '"subscriptions"' apps/ api/ --include="*.py" | grep -v "apps.subscriptions" | grep -v test
```

Update every hit that is a *product flag* usage (notably `seed_dev_data.py`). Do **not** touch `apps.subscriptions` module paths, the `ubb_subscriptions` Celery queue name, or route prefixes.

- [ ] **Step 5: Update tests that grant the flag**

```bash
cd ubb-platform && grep -rln 'products=\[.*subscriptions' apps/ api/
```

In each, replace `"subscriptions"` in the `products=[...]` list with `"billing"` (deduplicating if `"billing"` is already present).

- [ ] **Step 6: Run the full suite**

```bash
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest -q
```

Expected: no new failures beyond the 27 pre-existing ones in `apps/billing/invoicing` + `apps/subscriptions`.

- [ ] **Step 7: Commit**

```bash
git add ubb-platform/apps ubb-platform/api
git commit -m "refactor(tenants): retire the subscriptions product flag; gate on billing"
```

---

## Task 10: Wire the subscription mirror reconciler

**Files:**
- Modify: `ubb-platform/config/settings.py` (`CELERY_BEAT_SCHEDULE`)
- Modify: `ubb-platform/apps/subscriptions/tasks.py:172`
- Test: `ubb-platform/apps/subscriptions/tests/test_reconcile_schedule.py` (create)

**Interfaces:**
- Consumes: `sync_tenant_subscriptions_task(tenant_id)` (existing, currently dead code).
- Produces: a new task `reconcile_subscription_mirrors()` that fans out per tenant, scheduled hourly at `:35`.

- [ ] **Step 1: Write the failing test**

Create `ubb-platform/apps/subscriptions/tests/test_reconcile_schedule.py`:

```python
from unittest.mock import patch

import pytest
from django.conf import settings

from apps.platform.tenants.models import Tenant


class TestReconcilerIsScheduled:
    def test_mirror_reconciler_is_in_the_beat_schedule(self):
        """The Stripe subscription mirror is a pure cache of another system's
        state. Every other cache in this codebase has a scheduled reconciler;
        this one was dead code until 2026-07-27."""
        entry = settings.CELERY_BEAT_SCHEDULE["reconcile-subscription-mirrors"]
        assert entry["task"] == (
            "apps.subscriptions.tasks.reconcile_subscription_mirrors")


@pytest.mark.django_db
class TestReconcilerFansOut:
    def test_only_tenants_with_a_connected_account_are_synced(self):
        from apps.subscriptions.tasks import reconcile_subscription_mirrors

        Tenant.objects.create(name="connected", products=["metering", "billing"],
                              stripe_connected_account_id="acct_1")
        Tenant.objects.create(name="unconnected", products=["metering", "billing"])
        target = "apps.subscriptions.tasks.sync_tenant_subscriptions_task.delay"
        with patch(target) as delay:
            reconcile_subscription_mirrors()
        assert delay.call_count == 1
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/subscriptions/tests/test_reconcile_schedule.py -v
```

Expected: `KeyError: 'reconcile-subscription-mirrors'`.

Note the `:35` slot is free between `reconcile-live-ledgers` (`:25`) and `reconcile-usage-drawdowns` (`:40`) — verified by reading `CELERY_BEAT_SCHEDULE`, not by a test. A test asserting our own schedule choice back to itself proves nothing.

- [ ] **Step 3: Add the fan-out task**

Append to `ubb-platform/apps/subscriptions/tasks.py`:

```python
@shared_task(queue="ubb_subscriptions")
def reconcile_subscription_mirrors():
    """Hourly repair of the Stripe subscription mirror.

    The mirror is a pure cache of Stripe's state, refreshed by
    customer.subscription.* webhooks. A missed webhook would otherwise leave a
    canceled subscription displayed as active indefinitely — every other cache
    in this codebase has a scheduled reconciler; this one did not until
    2026-07-27 (sync_tenant_subscriptions_task existed but was never wired).

    Fans out one task per tenant with a connected account; tenants without one
    have no subscriptions to mirror.
    """
    from apps.platform.tenants.models import Tenant

    tenant_ids = Tenant.objects.exclude(
        stripe_connected_account_id="",
    ).exclude(
        stripe_connected_account_id__isnull=True,
    ).values_list("id", flat=True)
    for tenant_id in tenant_ids:
        sync_tenant_subscriptions_task.delay(str(tenant_id))
```

Verify `shared_task` is already imported at the top of the file; add `from celery import shared_task` if not.

- [ ] **Step 4: Schedule it**

In `ubb-platform/config/settings.py`, add to `CELERY_BEAT_SCHEDULE` after the `reconcile-live-ledgers` entry:

```python
    "reconcile-subscription-mirrors": {
        "task": "apps.subscriptions.tasks.reconcile_subscription_mirrors",
        # hourly at :35 — a free slot between reconcile-live-ledgers (:25) and
        # reconcile-usage-drawdowns (:40).
        "schedule": crontab(minute=35),
    },
```

- [ ] **Step 5: Run the test to verify it passes**

```bash
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/subscriptions/tests/test_reconcile_schedule.py -v
```

Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add ubb-platform/apps/subscriptions/tasks.py ubb-platform/config/settings.py ubb-platform/apps/subscriptions/tests
git commit -m "fix(subscriptions): schedule the mirror reconciler"
```

---

## Task 11: Regenerate the OpenAPI spec

**Files:**
- Modify: `openapi/v1.json` (generated)
- Modify: `apps/ui/src/api/generated/api.ts`, `apps/ui/src/api/schema.json` (generated)

**Interfaces:**
- Consumes: every route change from Tasks 7-9.
- Produces: the committed contract that the UI and SDK generate from.

- [ ] **Step 1: Regenerate the backend spec**

```bash
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python scripts/export_openapi.py
```

- [ ] **Step 2: Verify the surface changed as intended**

```bash
cd /Users/ashtoncochrane/Git/localscouta/ubb && python3 -c "
import json
spec = json.load(open('openapi/v1.json'))
paths = sorted(spec['paths'])
assert '/api/v1/plans' in paths, 'plans list route missing'
assert '/api/v1/plans/{key}' in paths, 'plans detail route missing'
assert '/api/v1/platform/plans' not in paths, 'old plan route still present'
print('plan routes:', [p for p in paths if 'plan' in p])
print('subscription routes:', [p for p in paths if 'subscri' in p])
"
```

Expected: the new routes present, `/api/v1/platform/plans` absent.

- [ ] **Step 3: Regenerate the UI client**

```bash
cd apps/ui && pnpm api:sync
```

- [ ] **Step 4: Typecheck the UI**

```bash
cd apps/ui && pnpm build
```

Expected: **failures** in `src/features/subscriptions/api/api.ts` — it still calls `POST /plans` on `platformApi`. Task 12 replaces that feature; leave the build red and proceed.

- [ ] **Step 5: Commit**

```bash
git add openapi/v1.json apps/ui/src/api
git commit -m "chore(openapi): regenerate for the plans surface"
```

---

## Task 12: The Plans page

**Files:**
- Create: `apps/ui/src/features/plans/api/{api,queries,types}.ts`
- Create: `apps/ui/src/features/plans/components/{plans-page,plans-table,plan-form-dialog}.tsx`
- Create: `apps/ui/src/features/plans/components/plans-page.test.tsx`
- Create: `apps/ui/src/app/routes/_app/plans/index.tsx`
- Delete: `apps/ui/src/features/subscriptions/`, `apps/ui/src/app/routes/_app/subscriptions/`
- Modify: `apps/ui/src/features/pricing/components/pricing-page.tsx` (drop the markup card)
- Delete: `apps/ui/src/features/pricing/components/tenant-markup-card.tsx`
- Modify: `apps/ui/src/app/router-smoke.test.tsx:24`

**Interfaces:**
- Consumes: the generated client from Task 11 — `GET /plans`, `POST /plans`, `PATCH /plans/{key}`, `DELETE /plans/{key}`.
- Produces: route `/plans`; `/subscriptions` no longer exists.

- [ ] **Step 1: Write the failing page test**

Create `apps/ui/src/features/plans/components/plans-page.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { PlansPage } from "./plans-page";

vi.mock("../api/queries", () => ({
  usePlans: () => ({
    data: {
      plans: [
        { id: "1", key: "enterprise", name: "Enterprise",
          access_fee_micros: 100_000_000, per_seat_micros: 10_000_000,
          markup_percentage_micros: 20_000_000, fixed_uplift_micros: 0,
          interval: "month", pricing_version: 1, archived_at: null },
        { id: "3", key: "personal-lite", name: "Personal Lite",
          access_fee_micros: 0, per_seat_micros: 0,
          markup_percentage_micros: 50_000_000, fixed_uplift_micros: 0,
          interval: "month", pricing_version: 1, archived_at: null },
      ],
    },
    isLoading: false,
    error: null,
  }),
  useCreatePlan: () => ({ mutate: vi.fn(), isPending: false }),
  useUpdatePlan: () => ({ mutate: vi.fn(), isPending: false }),
}));

describe("PlansPage", () => {
  it("shows all three axes in one row", () => {
    render(<PlansPage />);
    expect(screen.getByText("Enterprise")).toBeInTheDocument();
    expect(screen.getByText("$100.00/mo")).toBeInTheDocument();
    expect(screen.getByText("$10.00/seat")).toBeInTheDocument();
    expect(screen.getByText("20%")).toBeInTheDocument();
  });

  it("renders a markup-only plan as a normal plan, not an error", () => {
    render(<PlansPage />);
    expect(screen.getByText("Personal Lite")).toBeInTheDocument();
    expect(screen.getByText("50%")).toBeInTheDocument();
    expect(screen.queryByText(/invalid|error|unsupported/i)).not.toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd apps/ui && pnpm test plans-page
```

Expected: `Failed to resolve import "./plans-page"`.

- [ ] **Step 3: Write the types and formatters**

Create `apps/ui/src/features/plans/api/types.ts`:

```ts
import type { components } from "@/api/generated/api";

export type Plan = components["schemas"]["PlanOut"];
export type PlanInput = components["schemas"]["PlanIn"];
export type PlanUpdateInput = components["schemas"]["PlanUpdateIn"];

/** Micros -> display money. 1_000_000 micros == 1 major unit. */
export function formatMicros(micros: number): string {
  return `$${(micros / 1_000_000).toFixed(2)}`;
}

/** Markup micros -> percent. 1_000_000 micros == 1%. */
export function formatMarkup(micros: number): string {
  const pct = micros / 1_000_000;
  return `${Number.isInteger(pct) ? pct : pct.toFixed(2)}%`;
}
```

- [ ] **Step 4: Write the API client**

Create `apps/ui/src/features/plans/api/api.ts`, following the existing pattern in `src/features/subscriptions/api/api.ts` (read it before writing — it shows how `unwrap` and the typed client are used in this codebase):

```ts
import { api, unwrap } from "@/api/client";

import type { Plan, PlanInput, PlanUpdateInput } from "./types";

/** GET /api/v1/plans */
export async function listPlans(): Promise<{ plans: Plan[] }> {
  return unwrap(await api.GET("/plans"));
}

/** POST /api/v1/plans — 409 on a duplicate key. */
export async function createPlan(input: PlanInput): Promise<Plan> {
  return unwrap(await api.POST("/plans", { body: input }));
}

/** PATCH /api/v1/plans/{key} */
export async function updatePlan(key: string, input: PlanUpdateInput): Promise<Plan> {
  return unwrap(await api.PATCH("/plans/{key}", {
    params: { path: { key } }, body: input,
  }));
}

/** DELETE /api/v1/plans/{key} — 409 while customers are still assigned. */
export async function archivePlan(key: string): Promise<void> {
  await unwrap(await api.DELETE("/plans/{key}", { params: { path: { key } } }));
}
```

Adjust the import of `api`/`unwrap` to match whatever `src/features/subscriptions/api/api.ts` actually imports (it uses a `platformApi` binding; the root-mounted plan router needs the root client).

- [ ] **Step 5: Write the query hooks**

Create `apps/ui/src/features/plans/api/queries.ts`, mirroring `src/features/subscriptions/api/queries.ts`:

```ts
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { archivePlan, createPlan, listPlans, updatePlan } from "./api";
import type { PlanInput, PlanUpdateInput } from "./types";

const PLANS_KEY = ["plans"] as const;

export function usePlans() {
  return useQuery({ queryKey: PLANS_KEY, queryFn: listPlans });
}

export function useCreatePlan() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: PlanInput) => createPlan(input),
    onSuccess: () => qc.invalidateQueries({ queryKey: PLANS_KEY }),
  });
}

export function useUpdatePlan() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ key, input }: { key: string; input: PlanUpdateInput }) =>
      updatePlan(key, input),
    onSuccess: () => qc.invalidateQueries({ queryKey: PLANS_KEY }),
  });
}

export function useArchivePlan() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (key: string) => archivePlan(key),
    onSuccess: () => qc.invalidateQueries({ queryKey: PLANS_KEY }),
  });
}
```

- [ ] **Step 6: Write the table**

Create `apps/ui/src/features/plans/components/plans-table.tsx`:

```tsx
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow }
  from "@/components/ui/table";

import { formatMarkup, formatMicros, type Plan } from "../api/types";

/** An absent fee axis renders as an em dash, not "$0.00" — the plan does not
 *  charge it, which is different from charging zero. */
function Fee({ micros, suffix }: { micros: number; suffix: string }) {
  if (micros === 0) return <span className="text-muted-foreground">—</span>;
  return <>{formatMicros(micros)}{suffix}</>;
}

export function PlansTable({ plans, onEdit }: {
  plans: Plan[];
  onEdit: (plan: Plan) => void;
}) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Plan</TableHead>
          <TableHead>Access</TableHead>
          <TableHead>Per seat</TableHead>
          <TableHead>Markup</TableHead>
          <TableHead />
        </TableRow>
      </TableHeader>
      <TableBody>
        {plans.map((plan) => (
          <TableRow key={plan.id}>
            <TableCell className="font-medium">{plan.name}</TableCell>
            <TableCell>
              <Fee micros={plan.access_fee_micros}
                   suffix={plan.interval === "year" ? "/yr" : "/mo"} />
            </TableCell>
            <TableCell><Fee micros={plan.per_seat_micros} suffix="/seat" /></TableCell>
            <TableCell>{formatMarkup(plan.markup_percentage_micros)}</TableCell>
            <TableCell>
              <button type="button" onClick={() => onEdit(plan)}
                      className="text-sm underline underline-offset-2">
                Edit
              </button>
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
```

- [ ] **Step 7: Write the page**

Create `apps/ui/src/features/plans/components/plans-page.tsx`:

```tsx
import { useState } from "react";

import { PageHeader } from "@/components/shared/page-header";
import { ProductGate } from "@/components/shared/product-gate";
import { Card, CardContent } from "@/components/ui/card";

import { usePlans } from "../api/queries";
import type { Plan } from "../api/types";
import { PlansTable } from "./plans-table";

export function PlansPage() {
  const { data, isLoading, error } = usePlans();
  const [editing, setEditing] = useState<Plan | null>(null);

  return (
    <ProductGate product="billing">
      <div className="flex flex-col gap-4">
        <PageHeader
          title="Plans"
          description="What you sell: an access fee, a per-seat fee, and a markup on metered compute."
        />
        <Card size="sm">
          <CardContent>
            {isLoading && <p className="text-sm text-muted-foreground">Loading plans…</p>}
            {error && <p className="text-sm text-destructive">Could not load plans.</p>}
            {data && (
              <PlansTable plans={data.plans} onEdit={setEditing} />
            )}
          </CardContent>
        </Card>
        {editing && (
          <p className="text-xs text-muted-foreground">
            Editing {editing.name}. Fee changes create a new Stripe price; existing
            subscribers keep their current one. Markup changes apply immediately.
          </p>
        )}
      </div>
    </ProductGate>
  );
}
```

- [ ] **Step 8: Run the test to verify it passes**

```bash
cd apps/ui && pnpm test plans-page
```

Expected: 2 passed.

- [ ] **Step 9: Add the route and remove the old surface**

Create `apps/ui/src/app/routes/_app/plans/index.tsx`:

```tsx
import { createFileRoute } from "@tanstack/react-router";
import { PlansPage } from "@/features/plans/components/plans-page";

export const Route = createFileRoute("/_app/plans/")({
  component: PlansPage,
});
```

Then:

```bash
cd /Users/ashtoncochrane/Git/localscouta/ubb
rm -rf apps/ui/src/features/subscriptions apps/ui/src/app/routes/_app/subscriptions
rm apps/ui/src/features/pricing/components/tenant-markup-card.tsx
```

Remove the `TenantMarkupCard` import and usage from `apps/ui/src/features/pricing/components/pricing-page.tsx`.

In `apps/ui/src/app/router-smoke.test.tsx`, replace line 24:

```tsx
  { path: "/plans", expectText: /plans/i },
```

Update the nav component (find it with `grep -rn "subscriptions" apps/ui/src/components/`) to point at `/plans` with the label `Plans`.

- [ ] **Step 10: Run the full UI suite and build**

```bash
cd apps/ui && pnpm test && pnpm build
```

Expected: all pass, build clean.

- [ ] **Step 11: Commit**

```bash
git add apps/ui
git commit -m "feat(ui): one Plans page showing all three axes"
```

---

## Task 13: Fold the outcome into the living docs

Required by the ratchet in `CLAUDE.md`. Two of these files are actively wrong today.

**Files:**
- Modify: `CLAUDE.md`
- Modify: `docs/architecture/positioning.md`
- Modify: `CONTEXT-MAP.md`
- Modify: `ubb-platform/apps/platform/CONTEXT.md`
- Modify: `ubb-platform/apps/subscriptions/CONTEXT.md`

- [ ] **Step 1: Correct `CLAUDE.md`**

The header claims "**Stripe owns** … subscription/seat lifecycle", which has been false since the J2 program (2026-06-09). Replace that sentence with:

```markdown
**UBB owns** metering, real-time spend control, provider/billed-cost tracking, customer margin,
the **plan catalog** (access fee + per-seat fee + markup), and (for billing tenants) prepaid credit
drawdown / period-close Stripe line-item push. **Stripe owns** the subscription billing *engine* —
invoicing, payment collection, tax, dunning, portal, refunds, disputes, proration — which UBB
drives as a control plane but never reimplements.
```

Also update the products line: four products become three (`metering, billing, referrals`) plus the kernel.

- [ ] **Step 2: Correct `docs/architecture/positioning.md`**

Replace the `## Boundary` section with the design doc's §4 ownership table, and remove "full subscription lifecycle" from the *does not build* list — UBB does drive it. Add:

```markdown
UBB is a **control plane** over Stripe Billing, not a reimplementation of it and not a passive
mirror. Every piece of Stripe-owned state UBB stores is a cache: it has a refresh path, a staleness
bound, and it never decides money on its own.
```

- [ ] **Step 3: Add Plan vocabulary to the kernel CONTEXT**

Append to `ubb-platform/apps/platform/CONTEXT.md`:

```markdown
## Plans

**Plan**:
A tenant's commercial offer, with three axes — access fee, per-seat fee, and markup on metered
compute. A kernel concept because subscriptions realizes the first two (as Stripe Prices) and
metering realizes the third (at rating time), and neither owns it.
(`apps/platform/plans/models.py:Plan`)

**Markup-only plan**:
A plan whose fee axes are both zero, e.g. $0 access + 50% markup. It has no Stripe Product, Price,
or Subscription at all — plan membership lives in `CustomerPlanAssignment`, so such a customer is
on a real plan with zero presence in Stripe Billing. (`Plan.has_stripe_axes`)

**Repricing asymmetry**:
Fee edits are **grandfathered** (Stripe Prices are immutable, so a new versioned Price is minted and
existing subscribers keep the old one unless migrated); markup edits are **live** (no Stripe object
exists, so the change applies to the next rated event).

**Markup precedence**:
`customer TenantMarkup override -> customer's Plan -> tenant default -> none`. The plan rung is what
stops a Personal Lite customer silently billing at the tenant default.
(`apps/metering/pricing/services/markup_service.py`)
```

- [ ] **Step 4: Update the subscriptions CONTEXT**

In `ubb-platform/apps/subscriptions/CONTEXT.md`, delete the "Plans & provisioning" **Billing plan** entry (it moved to the kernel) and replace it with a pointer:

```markdown
**Billing plan**: moved to the platform kernel — see `apps/platform/CONTEXT.md` → Plans.
Subscriptions realizes a plan's *fee* axes as Stripe Prices; it does not own the plan.
```

- [ ] **Step 5: Update `CONTEXT-MAP.md`**

Add `apps/platform/plans/` to the Platform kernel bullet, and drop `subscriptions` from any list of gated products.

- [ ] **Step 6: Commit**

```bash
git add CLAUDE.md CONTEXT-MAP.md docs/architecture/positioning.md ubb-platform/apps/platform/CONTEXT.md ubb-platform/apps/subscriptions/CONTEXT.md
git commit -m "docs: fold the kernel Plan into the living docs; correct the Stripe-ownership claim"
```

---

## Task 14: Full verification

- [ ] **Step 1: Full backend suite**

```bash
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest -q
```

Expected: no failures beyond the 27 pre-existing ones in `apps/billing/invoicing` + `apps/subscriptions`. Compare against a baseline captured on `origin/main` before starting:

```bash
git stash && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest -q 2>&1 | tail -3 && git stash pop
```

- [ ] **Step 2: Boundary + sanity checks**

```bash
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/platform/tests/test_product_boundaries.py -v
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python manage.py check
```

- [ ] **Step 3: Confirm no `TenantBillingPlan` or stale flag remains**

```bash
cd /Users/ashtoncochrane/Git/localscouta/ubb
grep -rn "TenantBillingPlan" ubb-platform/ apps/ --include="*.py" --include="*.ts" --include="*.tsx" | grep -v migrations
grep -rn '"subscriptions"' ubb-platform/apps ubb-platform/api --include="*.py" | grep -v "apps.subscriptions"
```

Expected: no output from either (migrations legitimately retain the historical name).

- [ ] **Step 4: UI suite and build**

```bash
cd apps/ui && pnpm test && pnpm build && pnpm lint
```

- [ ] **Step 5: Spec drift check**

```bash
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python scripts/export_openapi.py
cd /Users/ashtoncochrane/Git/localscouta/ubb && git diff --exit-code -- openapi/v1.json
```

Expected: no diff — the spec committed in Task 11 is current.

- [ ] **Step 6: Commit any residue and open the PR**

```bash
git add -A && git commit -m "chore: verification pass" || echo "nothing to commit"
gh auth status   # confirm the ashcochrane account is active before pushing
git push -u origin HEAD
gh pr create --title "Plan as a kernel concept" --body "$(cat <<'EOF'
Implements `docs/plans/2026-07-27-plan-as-kernel-design.md`.

Moves `Plan` into the platform kernel and gives it a third commercial axis
(markup on metered compute), which Stripe structurally cannot represent.

- Closes the markup revenue leak: a plan's markup no longer falls through to
  the tenant default (pinned by a test that fails if the rung is lost).
- Makes markup-only plans sellable — they previously called Stripe with
  `items=[]` and were rejected.
- Retires the `subscriptions` product flag; plans and lifecycle gate on `billing`.
- Schedules the Stripe subscription mirror reconciler, which was dead code.
- Collapses the tenant UI to one Plans page showing all three axes.
- Corrects `CLAUDE.md` / `positioning.md`, which claimed Stripe owns the
  subscription lifecycle.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Self-Review

**Spec coverage** — every design section maps to a task: §3 model → Task 1; §4 ownership → Tasks 3, 5; §5 markup precedence → Tasks 3, 4; §6 API → Tasks 7, 8, 11; §7 product flag → Task 9; §8 UI → Task 12; §9 bundled fixes → Task 6 (zero-axis), Task 7 (interval validation via `Literal`), Task 10 (reconciler), Task 5 (rename), Task 13 (docs); §10 migration → Tasks 1, 5; §11 testing → distributed, verified in Task 14.

**One §9 item is deliberately deferred:** "surface plan fee drift" (showing Stripe's live Price alongside the stored value) is **not** implemented here. It requires a Stripe read on every plan GET, which is a latency and rate-limit decision the design doc did not settle. File it as a follow-up issue rather than guessing. Everything else in §9 ships.

**Type consistency** — `ResolvedMarkup` (Task 3) is the single return type of `MarkupService.resolve`, consumed only via `.calculate_markup_micros()`; `get_plan_markup_for_customer` returns exactly the two keys `ResolvedMarkup(source=..., **plan_markup)` expects. `Plan.has_stripe_axes` is defined in Task 1 and used in Tasks 6 and 12. `PlanService.assign/archive` and `PlanInUse` are defined in Task 2 and used in Tasks 7 and 8. `subscribe()` returns `StripeSubscription | None` from Task 6 onward, and Task 8's endpoint handles the `None`.
