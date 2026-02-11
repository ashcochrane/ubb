# Subscriptions Product Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build the Subscriptions product — a read-only Stripe subscription sync layer that provides per-customer unit economics (revenue vs. usage cost) for tenants with `["metering", "subscriptions"]`.

**Architecture:** New `apps/subscriptions/` Django app with three sub-modules: sync (Stripe subscription/invoice mirroring), economics (cost accumulation + margin calculation), and API (endpoints + webhooks). Subscriptions never imports from metering or billing — it reads cost data via event bus accumulation and revenue data from its own synced Stripe mirror. The SDK gets a new `SubscriptionsClient` and `UBBClient` gains a `subscriptions` flag.

**Tech Stack:** Django 6.0, django-ninja, Celery, Stripe API (on Connected Accounts), pytest, factory-boy

**Design doc:** `docs/plans/2026-02-05-subscriptions-product-design.md`

---

## Phase 1: App Skeleton + Data Models

> Create the `apps/subscriptions/` directory structure, register the app, and build the three core models: `StripeSubscription`, `SubscriptionInvoice`, `CustomerCostAccumulator`, and `CustomerEconomics`.

### Task 1: Create subscriptions app skeleton

**Files:**
- Create: `ubb-platform/apps/subscriptions/__init__.py`
- Create: `ubb-platform/apps/subscriptions/apps.py`
- Create: `ubb-platform/apps/subscriptions/models.py`
- Create: `ubb-platform/apps/subscriptions/economics/__init__.py`
- Create: `ubb-platform/apps/subscriptions/economics/models.py`
- Create: `ubb-platform/apps/subscriptions/economics/services.py`
- Create: `ubb-platform/apps/subscriptions/stripe/__init__.py`
- Create: `ubb-platform/apps/subscriptions/stripe/services.py`
- Create: `ubb-platform/apps/subscriptions/stripe/sync.py`
- Create: `ubb-platform/apps/subscriptions/handlers.py`
- Create: `ubb-platform/apps/subscriptions/api/__init__.py`
- Create: `ubb-platform/apps/subscriptions/api/endpoints.py`
- Create: `ubb-platform/apps/subscriptions/api/schemas.py`
- Create: `ubb-platform/apps/subscriptions/api/webhooks.py`
- Create: `ubb-platform/apps/subscriptions/tasks.py`
- Create: `ubb-platform/apps/subscriptions/tests/__init__.py`
- Modify: `ubb-platform/config/settings.py` — add to `INSTALLED_APPS`

**Step 1: Create all directories and empty files**

```bash
cd ubb-platform
mkdir -p apps/subscriptions/economics apps/subscriptions/stripe apps/subscriptions/api apps/subscriptions/tests
touch apps/subscriptions/__init__.py
touch apps/subscriptions/economics/__init__.py
touch apps/subscriptions/stripe/__init__.py
touch apps/subscriptions/api/__init__.py
touch apps/subscriptions/tests/__init__.py
touch apps/subscriptions/models.py
touch apps/subscriptions/economics/models.py
touch apps/subscriptions/economics/services.py
touch apps/subscriptions/stripe/services.py
touch apps/subscriptions/stripe/sync.py
touch apps/subscriptions/handlers.py
touch apps/subscriptions/api/endpoints.py
touch apps/subscriptions/api/schemas.py
touch apps/subscriptions/api/webhooks.py
touch apps/subscriptions/tasks.py
```

**Step 2: Write `apps/subscriptions/apps.py`**

```python
from django.apps import AppConfig


class SubscriptionsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.subscriptions"
    label = "subscriptions"

    def ready(self):
        from core.event_bus import event_bus
        from apps.subscriptions.handlers import handle_usage_recorded

        event_bus.subscribe(
            "usage.recorded",
            handle_usage_recorded,
            requires_product="subscriptions",
        )
```

**Step 3: Add `"apps.subscriptions"` to `config/settings.py` INSTALLED_APPS**

Add after `"apps.billing.tenant_billing"`:

```python
    # Subscriptions
    "apps.subscriptions",
```

**Step 4: Write a placeholder `handlers.py`**

```python
# apps/subscriptions/handlers.py
import logging

logger = logging.getLogger("ubb.events")


def handle_usage_recorded(data):
    """Accumulate usage cost for unit economics. Implemented in Task 5."""
    pass
```

**Step 5: Verify Django starts up**

```bash
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python manage.py check
```
Expected: "System check identified no issues."

**Step 6: Commit**

```bash
git add apps/subscriptions config/settings.py
git commit -m "chore: create subscriptions app skeleton and register in INSTALLED_APPS"
```

---

### Task 2: Create StripeSubscription and SubscriptionInvoice models

**Files:**
- Modify: `ubb-platform/apps/subscriptions/models.py`
- Create: migration via `makemigrations`
- Create: `ubb-platform/apps/subscriptions/tests/test_models.py`

**Step 1: Write the failing test**

```python
# apps/subscriptions/tests/test_models.py
import pytest
from django.utils import timezone
from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer


@pytest.mark.django_db
class TestStripeSubscription:
    def test_create_stripe_subscription(self):
        from apps.subscriptions.models import StripeSubscription

        tenant = Tenant.objects.create(name="test", products=["metering", "subscriptions"])
        customer = Customer.objects.create(tenant=tenant, external_id="cust-1")
        now = timezone.now()

        sub = StripeSubscription.objects.create(
            tenant=tenant,
            customer=customer,
            stripe_subscription_id="sub_123abc",
            stripe_product_name="Pro Plan",
            status="active",
            amount_micros=49_000_000,  # $49/mo
            currency="usd",
            interval="month",
            current_period_start=now,
            current_period_end=now,
            last_synced_at=now,
        )
        sub.refresh_from_db()
        assert sub.stripe_subscription_id == "sub_123abc"
        assert sub.status == "active"
        assert sub.amount_micros == 49_000_000

    def test_stripe_subscription_id_is_unique(self):
        from apps.subscriptions.models import StripeSubscription
        from django.db import IntegrityError

        tenant = Tenant.objects.create(name="test", products=["metering", "subscriptions"])
        customer = Customer.objects.create(tenant=tenant, external_id="cust-1")
        now = timezone.now()

        StripeSubscription.objects.create(
            tenant=tenant, customer=customer,
            stripe_subscription_id="sub_dup",
            stripe_product_name="Plan", status="active",
            amount_micros=10_000_000, currency="usd", interval="month",
            current_period_start=now, current_period_end=now, last_synced_at=now,
        )
        with pytest.raises(IntegrityError):
            StripeSubscription.objects.create(
                tenant=tenant, customer=customer,
                stripe_subscription_id="sub_dup",
                stripe_product_name="Plan", status="active",
                amount_micros=10_000_000, currency="usd", interval="month",
                current_period_start=now, current_period_end=now, last_synced_at=now,
            )


@pytest.mark.django_db
class TestSubscriptionInvoice:
    def test_create_subscription_invoice(self):
        from apps.subscriptions.models import StripeSubscription, SubscriptionInvoice

        tenant = Tenant.objects.create(name="test", products=["metering", "subscriptions"])
        customer = Customer.objects.create(tenant=tenant, external_id="cust-1")
        now = timezone.now()

        sub = StripeSubscription.objects.create(
            tenant=tenant, customer=customer,
            stripe_subscription_id="sub_inv_test",
            stripe_product_name="Enterprise", status="active",
            amount_micros=199_000_000, currency="usd", interval="month",
            current_period_start=now, current_period_end=now, last_synced_at=now,
        )

        invoice = SubscriptionInvoice.objects.create(
            tenant=tenant,
            customer=customer,
            stripe_subscription=sub,
            stripe_invoice_id="in_abc123",
            amount_paid_micros=199_000_000,
            currency="usd",
            period_start=now,
            period_end=now,
            paid_at=now,
        )
        invoice.refresh_from_db()
        assert invoice.stripe_invoice_id == "in_abc123"
        assert invoice.amount_paid_micros == 199_000_000

    def test_stripe_invoice_id_is_unique(self):
        from apps.subscriptions.models import StripeSubscription, SubscriptionInvoice
        from django.db import IntegrityError

        tenant = Tenant.objects.create(name="test", products=["metering", "subscriptions"])
        customer = Customer.objects.create(tenant=tenant, external_id="cust-1")
        now = timezone.now()

        sub = StripeSubscription.objects.create(
            tenant=tenant, customer=customer,
            stripe_subscription_id="sub_inv_dup",
            stripe_product_name="Plan", status="active",
            amount_micros=10_000_000, currency="usd", interval="month",
            current_period_start=now, current_period_end=now, last_synced_at=now,
        )
        SubscriptionInvoice.objects.create(
            tenant=tenant, customer=customer, stripe_subscription=sub,
            stripe_invoice_id="in_dup", amount_paid_micros=10_000_000,
            currency="usd", period_start=now, period_end=now, paid_at=now,
        )
        with pytest.raises(IntegrityError):
            SubscriptionInvoice.objects.create(
                tenant=tenant, customer=customer, stripe_subscription=sub,
                stripe_invoice_id="in_dup", amount_paid_micros=10_000_000,
                currency="usd", period_start=now, period_end=now, paid_at=now,
            )
```

**Step 2: Run test to verify it fails**

```bash
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/subscriptions/tests/test_models.py -v
```
Expected: FAIL — `StripeSubscription` doesn't exist.

**Step 3: Implement the models**

```python
# apps/subscriptions/models.py
from django.db import models
from core.models import BaseModel


SUBSCRIPTION_STATUS_CHOICES = [
    ("active", "Active"),
    ("past_due", "Past Due"),
    ("canceled", "Canceled"),
    ("incomplete", "Incomplete"),
    ("incomplete_expired", "Incomplete Expired"),
    ("trialing", "Trialing"),
    ("unpaid", "Unpaid"),
    ("paused", "Paused"),
]


class StripeSubscription(BaseModel):
    """Read-only mirror of a Stripe subscription on the tenant's Connected Account."""
    tenant = models.ForeignKey(
        "tenants.Tenant", on_delete=models.CASCADE, related_name="stripe_subscriptions"
    )
    customer = models.ForeignKey(
        "customers.Customer", on_delete=models.CASCADE, related_name="stripe_subscriptions"
    )
    stripe_subscription_id = models.CharField(max_length=255, unique=True, db_index=True)
    stripe_product_name = models.CharField(max_length=255)
    status = models.CharField(max_length=20, choices=SUBSCRIPTION_STATUS_CHOICES, db_index=True)
    amount_micros = models.BigIntegerField()
    currency = models.CharField(max_length=3, default="usd")
    interval = models.CharField(max_length=10)  # month, year
    current_period_start = models.DateTimeField()
    current_period_end = models.DateTimeField()
    last_synced_at = models.DateTimeField()

    class Meta:
        db_table = "ubb_stripe_subscription"
        indexes = [
            models.Index(fields=["tenant", "status"], name="idx_stripesub_tenant_status"),
        ]

    def __str__(self):
        return f"StripeSubscription({self.stripe_subscription_id}: {self.status})"


class SubscriptionInvoice(BaseModel):
    """Synced from Stripe — tracks each paid invoice for revenue attribution."""
    tenant = models.ForeignKey(
        "tenants.Tenant", on_delete=models.CASCADE, related_name="subscription_invoices"
    )
    customer = models.ForeignKey(
        "customers.Customer", on_delete=models.CASCADE, related_name="subscription_invoices"
    )
    stripe_subscription = models.ForeignKey(
        StripeSubscription, on_delete=models.CASCADE, related_name="invoices"
    )
    stripe_invoice_id = models.CharField(max_length=255, unique=True, db_index=True)
    amount_paid_micros = models.BigIntegerField()
    currency = models.CharField(max_length=3, default="usd")
    period_start = models.DateTimeField()
    period_end = models.DateTimeField()
    paid_at = models.DateTimeField()

    class Meta:
        db_table = "ubb_subscription_invoice"

    def __str__(self):
        return f"SubscriptionInvoice({self.stripe_invoice_id})"
```

**Step 4: Generate and run migration**

```bash
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python manage.py makemigrations subscriptions -n create_stripe_subscription_and_invoice
DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python manage.py migrate
```

**Step 5: Run tests to verify they pass**

```bash
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/subscriptions/tests/test_models.py -v
```
Expected: All 4 tests PASS.

**Step 6: Commit**

```bash
git add apps/subscriptions/models.py apps/subscriptions/migrations/ apps/subscriptions/tests/test_models.py
git commit -m "feat: add StripeSubscription and SubscriptionInvoice models"
```

---

### Task 3: Create CustomerCostAccumulator model

This is the lightweight accumulator for event-bus-driven usage cost data. Subscriptions uses this instead of importing from metering.

**Files:**
- Modify: `ubb-platform/apps/subscriptions/economics/models.py`
- Create: migration via `makemigrations`
- Add tests to: `ubb-platform/apps/subscriptions/tests/test_models.py`

**Step 1: Write the failing test**

Add to `apps/subscriptions/tests/test_models.py`:

```python
@pytest.mark.django_db
class TestCustomerCostAccumulator:
    def test_create_accumulator(self):
        from apps.subscriptions.economics.models import CustomerCostAccumulator
        from datetime import date

        tenant = Tenant.objects.create(name="test", products=["metering", "subscriptions"])
        customer = Customer.objects.create(tenant=tenant, external_id="cust-1")

        acc = CustomerCostAccumulator.objects.create(
            tenant=tenant,
            customer=customer,
            period_start=date(2026, 1, 1),
            period_end=date(2026, 2, 1),
            total_cost_micros=5_000_000,
            event_count=10,
        )
        acc.refresh_from_db()
        assert acc.total_cost_micros == 5_000_000
        assert acc.event_count == 10

    def test_accumulator_unique_constraint(self):
        from apps.subscriptions.economics.models import CustomerCostAccumulator
        from django.db import IntegrityError
        from datetime import date

        tenant = Tenant.objects.create(name="test", products=["metering", "subscriptions"])
        customer = Customer.objects.create(tenant=tenant, external_id="cust-1")

        CustomerCostAccumulator.objects.create(
            tenant=tenant, customer=customer,
            period_start=date(2026, 1, 1), period_end=date(2026, 2, 1),
        )
        with pytest.raises(IntegrityError):
            CustomerCostAccumulator.objects.create(
                tenant=tenant, customer=customer,
                period_start=date(2026, 1, 1), period_end=date(2026, 2, 1),
            )
```

**Step 2: Run test to verify it fails**

```bash
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/subscriptions/tests/test_models.py::TestCustomerCostAccumulator -v
```
Expected: FAIL — `CustomerCostAccumulator` doesn't exist.

**Step 3: Implement the model**

```python
# apps/subscriptions/economics/models.py
from django.db import models
from core.models import BaseModel


class CustomerCostAccumulator(BaseModel):
    """Lightweight accumulator for per-customer, per-period usage costs.

    Populated by the usage.recorded event handler. Avoids cross-product
    imports — subscriptions has its own copy of cost data.
    """
    tenant = models.ForeignKey(
        "tenants.Tenant", on_delete=models.CASCADE, related_name="cost_accumulators"
    )
    customer = models.ForeignKey(
        "customers.Customer", on_delete=models.CASCADE, related_name="cost_accumulators"
    )
    period_start = models.DateField()
    period_end = models.DateField()
    total_cost_micros = models.BigIntegerField(default=0)
    event_count = models.IntegerField(default=0)

    class Meta:
        db_table = "ubb_customer_cost_accumulator"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "customer", "period_start"],
                name="uq_cost_accumulator_tenant_customer_period",
            ),
        ]

    def __str__(self):
        return f"CostAccumulator({self.customer_id}: {self.period_start})"


class CustomerEconomics(BaseModel):
    """Per-customer, per-period unit economics snapshot."""
    tenant = models.ForeignKey(
        "tenants.Tenant", on_delete=models.CASCADE, related_name="customer_economics"
    )
    customer = models.ForeignKey(
        "customers.Customer", on_delete=models.CASCADE, related_name="economics"
    )
    period_start = models.DateField()
    period_end = models.DateField()
    subscription_revenue_micros = models.BigIntegerField(default=0)
    usage_cost_micros = models.BigIntegerField(default=0)
    gross_margin_micros = models.BigIntegerField(default=0)
    margin_percentage = models.DecimalField(max_digits=7, decimal_places=2, default=0)

    class Meta:
        db_table = "ubb_customer_economics"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "customer", "period_start"],
                name="uq_economics_tenant_customer_period",
            ),
        ]

    def __str__(self):
        return f"Economics({self.customer_id}: {self.margin_percentage}%)"
```

> **NOTE:** Both `CustomerCostAccumulator` and `CustomerEconomics` are defined in `economics/models.py`. They share the same migration. The `economics/` sub-package is not a separate Django app — it lives under the `subscriptions` app label.

**Step 4: Generate and run migration**

```bash
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python manage.py makemigrations subscriptions -n create_cost_accumulator_and_economics
DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python manage.py migrate
```

**Step 5: Run tests**

```bash
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/subscriptions/tests/test_models.py -v
```
Expected: All tests PASS.

**Step 6: Commit**

```bash
git add apps/subscriptions/economics/models.py apps/subscriptions/migrations/ apps/subscriptions/tests/test_models.py
git commit -m "feat: add CustomerCostAccumulator and CustomerEconomics models"
```

---

## Phase 2: Event Bus Handler + Cost Accumulation

> Wire up the `usage.recorded` event handler so subscriptions accumulates usage costs in real time, without importing from metering.

### Task 4: Implement usage cost accumulation handler

**Files:**
- Modify: `ubb-platform/apps/subscriptions/handlers.py`
- Create: `ubb-platform/apps/subscriptions/tests/test_handlers.py`

**Step 1: Write the failing test**

```python
# apps/subscriptions/tests/test_handlers.py
import pytest
from datetime import date
from django.utils import timezone
from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer


@pytest.mark.django_db
class TestHandleUsageRecorded:
    def test_creates_accumulator_on_first_event(self):
        from apps.subscriptions.handlers import handle_usage_recorded
        from apps.subscriptions.economics.models import CustomerCostAccumulator

        tenant = Tenant.objects.create(name="test", products=["metering", "subscriptions"])
        customer = Customer.objects.create(tenant=tenant, external_id="cust-1")

        handle_usage_recorded({
            "tenant_id": str(tenant.id),
            "customer_id": str(customer.id),
            "cost_micros": 1_500_000,
            "event_type": "api_call",
            "event_id": "evt-1",
        })

        acc = CustomerCostAccumulator.objects.get(
            tenant=tenant, customer=customer,
        )
        assert acc.total_cost_micros == 1_500_000
        assert acc.event_count == 1

    def test_accumulates_on_subsequent_events(self):
        from apps.subscriptions.handlers import handle_usage_recorded
        from apps.subscriptions.economics.models import CustomerCostAccumulator

        tenant = Tenant.objects.create(name="test", products=["metering", "subscriptions"])
        customer = Customer.objects.create(tenant=tenant, external_id="cust-1")

        for i in range(3):
            handle_usage_recorded({
                "tenant_id": str(tenant.id),
                "customer_id": str(customer.id),
                "cost_micros": 1_000_000,
                "event_type": "api_call",
                "event_id": f"evt-{i}",
            })

        acc = CustomerCostAccumulator.objects.get(
            tenant=tenant, customer=customer,
        )
        assert acc.total_cost_micros == 3_000_000
        assert acc.event_count == 3

    def test_skips_zero_cost_events(self):
        from apps.subscriptions.handlers import handle_usage_recorded
        from apps.subscriptions.economics.models import CustomerCostAccumulator

        tenant = Tenant.objects.create(name="test", products=["metering", "subscriptions"])
        customer = Customer.objects.create(tenant=tenant, external_id="cust-1")

        handle_usage_recorded({
            "tenant_id": str(tenant.id),
            "customer_id": str(customer.id),
            "cost_micros": 0,
            "event_type": "api_call",
            "event_id": "evt-0",
        })

        assert not CustomerCostAccumulator.objects.filter(
            tenant=tenant, customer=customer,
        ).exists()
```

**Step 2: Run test to verify it fails**

```bash
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/subscriptions/tests/test_handlers.py -v
```
Expected: FAIL — handler is a no-op stub.

**Step 3: Implement the handler**

```python
# apps/subscriptions/handlers.py
import logging

from django.db.models import F
from django.utils import timezone

logger = logging.getLogger("ubb.events")


def _current_period_bounds():
    """Return (period_start, period_end) for the current calendar month."""
    today = timezone.now().date()
    first_of_month = today.replace(day=1)
    if today.month == 12:
        first_of_next_month = today.replace(year=today.year + 1, month=1, day=1)
    else:
        first_of_next_month = today.replace(month=today.month + 1, day=1)
    return first_of_month, first_of_next_month


def handle_usage_recorded(data):
    """Accumulate usage cost for unit economics calculation.

    Called by event bus when usage.recorded fires for subscriptions tenants.
    Uses atomic F() increment — no SELECT needed for the hot path.
    """
    cost_micros = data.get("cost_micros", 0)
    if cost_micros <= 0:
        return

    from apps.subscriptions.economics.models import CustomerCostAccumulator

    period_start, period_end = _current_period_bounds()

    # Try atomic increment first (fast path — row already exists)
    rows = CustomerCostAccumulator.objects.filter(
        tenant_id=data["tenant_id"],
        customer_id=data["customer_id"],
        period_start=period_start,
    ).update(
        total_cost_micros=F("total_cost_micros") + cost_micros,
        event_count=F("event_count") + 1,
    )

    if rows == 0:
        # Row doesn't exist yet — create it. Race condition handled by unique constraint.
        from django.db import IntegrityError
        try:
            CustomerCostAccumulator.objects.create(
                tenant_id=data["tenant_id"],
                customer_id=data["customer_id"],
                period_start=period_start,
                period_end=period_end,
                total_cost_micros=cost_micros,
                event_count=1,
            )
        except IntegrityError:
            # Lost race — retry the update
            CustomerCostAccumulator.objects.filter(
                tenant_id=data["tenant_id"],
                customer_id=data["customer_id"],
                period_start=period_start,
            ).update(
                total_cost_micros=F("total_cost_micros") + cost_micros,
                event_count=F("event_count") + 1,
            )
```

**Step 4: Run tests**

```bash
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/subscriptions/tests/test_handlers.py -v
```
Expected: All 3 tests PASS.

**Step 5: Run full test suite to verify no regressions**

```bash
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest --tb=short -q
```

**Step 6: Commit**

```bash
git add apps/subscriptions/handlers.py apps/subscriptions/tests/test_handlers.py
git commit -m "feat: implement usage.recorded handler for cost accumulation"
```

---

## Phase 3: Stripe Sync

> Build the Stripe subscription sync: webhook handlers for live updates and a full-sync service for initial import.

### Task 5: Implement Stripe subscription webhook handlers

**Files:**
- Modify: `ubb-platform/apps/subscriptions/api/webhooks.py`
- Create: `ubb-platform/apps/subscriptions/tests/test_webhooks.py`

**Step 1: Write the failing tests**

```python
# apps/subscriptions/tests/test_webhooks.py
import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch
from django.utils import timezone
from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer


@pytest.mark.django_db
class TestHandleSubscriptionCreated:
    def test_creates_local_mirror(self):
        from apps.subscriptions.api.webhooks import handle_subscription_created
        from apps.subscriptions.models import StripeSubscription

        tenant = Tenant.objects.create(
            name="test",
            products=["metering", "subscriptions"],
            stripe_connected_account_id="acct_123",
        )
        customer = Customer.objects.create(
            tenant=tenant, external_id="cust-1", stripe_customer_id="cus_abc",
        )

        event = MagicMock()
        event.account = "acct_123"
        event.data.object.id = "sub_new"
        event.data.object.customer = "cus_abc"
        event.data.object.status = "active"
        event.data.object.current_period_start = 1738368000  # unix timestamp
        event.data.object.current_period_end = 1740960000
        event.data.object.plan.product.name = "Pro Plan"
        event.data.object.plan.amount = 4900  # cents
        event.data.object.plan.currency = "usd"
        event.data.object.plan.interval = "month"

        handle_subscription_created(event)

        sub = StripeSubscription.objects.get(stripe_subscription_id="sub_new")
        assert sub.tenant == tenant
        assert sub.customer == customer
        assert sub.stripe_product_name == "Pro Plan"
        assert sub.amount_micros == 49_000_000  # 4900 cents * 10_000
        assert sub.status == "active"


@pytest.mark.django_db
class TestHandleSubscriptionUpdated:
    def test_updates_existing_mirror(self):
        from apps.subscriptions.api.webhooks import handle_subscription_updated
        from apps.subscriptions.models import StripeSubscription

        tenant = Tenant.objects.create(
            name="test", products=["metering", "subscriptions"],
        )
        customer = Customer.objects.create(tenant=tenant, external_id="cust-1")
        now = timezone.now()

        sub = StripeSubscription.objects.create(
            tenant=tenant, customer=customer,
            stripe_subscription_id="sub_upd",
            stripe_product_name="Pro", status="active",
            amount_micros=49_000_000, currency="usd", interval="month",
            current_period_start=now, current_period_end=now, last_synced_at=now,
        )

        event = MagicMock()
        event.data.object.id = "sub_upd"
        event.data.object.status = "past_due"
        event.data.object.current_period_start = 1738368000
        event.data.object.current_period_end = 1740960000

        handle_subscription_updated(event)

        sub.refresh_from_db()
        assert sub.status == "past_due"


@pytest.mark.django_db
class TestHandleSubscriptionDeleted:
    def test_marks_as_canceled(self):
        from apps.subscriptions.api.webhooks import handle_subscription_deleted
        from apps.subscriptions.models import StripeSubscription

        tenant = Tenant.objects.create(
            name="test", products=["metering", "subscriptions"],
        )
        customer = Customer.objects.create(tenant=tenant, external_id="cust-1")
        now = timezone.now()

        sub = StripeSubscription.objects.create(
            tenant=tenant, customer=customer,
            stripe_subscription_id="sub_del",
            stripe_product_name="Pro", status="active",
            amount_micros=49_000_000, currency="usd", interval="month",
            current_period_start=now, current_period_end=now, last_synced_at=now,
        )

        event = MagicMock()
        event.data.object.id = "sub_del"

        handle_subscription_deleted(event)

        sub.refresh_from_db()
        assert sub.status == "canceled"


@pytest.mark.django_db
class TestHandleInvoicePaid:
    def test_creates_subscription_invoice(self):
        from apps.subscriptions.api.webhooks import handle_invoice_paid
        from apps.subscriptions.models import StripeSubscription, SubscriptionInvoice

        tenant = Tenant.objects.create(
            name="test", products=["metering", "subscriptions"],
        )
        customer = Customer.objects.create(tenant=tenant, external_id="cust-1")
        now = timezone.now()

        sub = StripeSubscription.objects.create(
            tenant=tenant, customer=customer,
            stripe_subscription_id="sub_inv",
            stripe_product_name="Pro", status="active",
            amount_micros=49_000_000, currency="usd", interval="month",
            current_period_start=now, current_period_end=now, last_synced_at=now,
        )

        event = MagicMock()
        event.data.object.id = "in_paid123"
        event.data.object.subscription = "sub_inv"
        event.data.object.amount_paid = 4900  # cents
        event.data.object.currency = "usd"
        event.data.object.period_start = 1738368000
        event.data.object.period_end = 1740960000
        event.data.object.status_transitions.paid_at = 1738400000

        handle_invoice_paid(event)

        inv = SubscriptionInvoice.objects.get(stripe_invoice_id="in_paid123")
        assert inv.amount_paid_micros == 49_000_000
        assert inv.stripe_subscription == sub

    def test_skips_non_subscription_invoice(self):
        from apps.subscriptions.api.webhooks import handle_invoice_paid
        from apps.subscriptions.models import SubscriptionInvoice

        event = MagicMock()
        event.data.object.subscription = None  # Not a subscription invoice

        handle_invoice_paid(event)

        assert SubscriptionInvoice.objects.count() == 0
```

**Step 2: Run tests to verify they fail**

```bash
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/subscriptions/tests/test_webhooks.py -v
```
Expected: FAIL — webhook handlers don't exist.

**Step 3: Implement webhook handlers**

```python
# apps/subscriptions/api/webhooks.py
import logging
from datetime import datetime

from django.utils import timezone

from apps.subscriptions.models import StripeSubscription, SubscriptionInvoice
from apps.platform.customers.models import Customer

logger = logging.getLogger(__name__)


def _unix_to_datetime(ts):
    """Convert unix timestamp to timezone-aware datetime."""
    if ts is None:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc)


def handle_subscription_created(event):
    """New subscription on tenant's Connected Account — create local mirror."""
    stripe_sub = event.data.object
    connected_account = event.account

    customer = Customer.objects.get(
        stripe_customer_id=stripe_sub.customer,
        tenant__stripe_connected_account_id=connected_account,
    )

    StripeSubscription.objects.create(
        tenant=customer.tenant,
        customer=customer,
        stripe_subscription_id=stripe_sub.id,
        stripe_product_name=stripe_sub.plan.product.name,
        status=stripe_sub.status,
        amount_micros=stripe_sub.plan.amount * 10_000,  # cents to micros
        currency=stripe_sub.plan.currency,
        interval=stripe_sub.plan.interval,
        current_period_start=_unix_to_datetime(stripe_sub.current_period_start),
        current_period_end=_unix_to_datetime(stripe_sub.current_period_end),
        last_synced_at=timezone.now(),
    )


def handle_subscription_updated(event):
    """Subscription changed — update local mirror."""
    stripe_sub = event.data.object
    sub = StripeSubscription.objects.get(stripe_subscription_id=stripe_sub.id)
    sub.status = stripe_sub.status
    sub.current_period_start = _unix_to_datetime(stripe_sub.current_period_start)
    sub.current_period_end = _unix_to_datetime(stripe_sub.current_period_end)
    sub.last_synced_at = timezone.now()
    sub.save(update_fields=[
        "status", "current_period_start", "current_period_end",
        "last_synced_at", "updated_at",
    ])


def handle_subscription_deleted(event):
    """Subscription canceled — mark as canceled."""
    stripe_sub = event.data.object
    sub = StripeSubscription.objects.get(stripe_subscription_id=stripe_sub.id)
    sub.status = "canceled"
    sub.last_synced_at = timezone.now()
    sub.save(update_fields=["status", "last_synced_at", "updated_at"])


def handle_invoice_paid(event):
    """A subscription invoice was paid — record the revenue."""
    invoice = event.data.object
    if not invoice.subscription:
        return  # Not a subscription invoice — skip

    try:
        stripe_sub = StripeSubscription.objects.get(
            stripe_subscription_id=invoice.subscription
        )
    except StripeSubscription.DoesNotExist:
        logger.warning(
            "StripeSubscription not found for invoice",
            extra={"data": {
                "stripe_invoice_id": invoice.id,
                "stripe_subscription_id": invoice.subscription,
            }},
        )
        raise  # Re-raise so webhook framework retries

    SubscriptionInvoice.objects.get_or_create(
        stripe_invoice_id=invoice.id,
        defaults={
            "tenant": stripe_sub.tenant,
            "customer": stripe_sub.customer,
            "stripe_subscription": stripe_sub,
            "amount_paid_micros": invoice.amount_paid * 10_000,  # cents to micros
            "currency": invoice.currency,
            "period_start": _unix_to_datetime(invoice.period_start),
            "period_end": _unix_to_datetime(invoice.period_end),
            "paid_at": _unix_to_datetime(invoice.status_transitions.paid_at),
        },
    )
```

**Step 4: Run tests**

```bash
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/subscriptions/tests/test_webhooks.py -v
```
Expected: All 5 tests PASS.

**Step 5: Commit**

```bash
git add apps/subscriptions/api/webhooks.py apps/subscriptions/tests/test_webhooks.py
git commit -m "feat: implement Stripe subscription webhook handlers"
```

---

### Task 6: Implement full Stripe sync service

**Files:**
- Modify: `ubb-platform/apps/subscriptions/stripe/sync.py`
- Create: `ubb-platform/apps/subscriptions/tests/test_sync.py`

**Step 1: Write the failing test**

```python
# apps/subscriptions/tests/test_sync.py
import pytest
from unittest.mock import patch, MagicMock
from django.utils import timezone
from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer


@pytest.mark.django_db
class TestFullSync:
    def test_syncs_active_subscriptions(self):
        from apps.subscriptions.stripe.sync import sync_subscriptions
        from apps.subscriptions.models import StripeSubscription

        tenant = Tenant.objects.create(
            name="test",
            products=["metering", "subscriptions"],
            stripe_connected_account_id="acct_test",
        )
        customer = Customer.objects.create(
            tenant=tenant, external_id="cust-1", stripe_customer_id="cus_sync",
        )

        mock_sub = MagicMock()
        mock_sub.id = "sub_sync_1"
        mock_sub.customer = "cus_sync"
        mock_sub.status = "active"
        mock_sub.plan.product.name = "Enterprise"
        mock_sub.plan.amount = 19900  # $199
        mock_sub.plan.currency = "usd"
        mock_sub.plan.interval = "month"
        mock_sub.current_period_start = 1738368000
        mock_sub.current_period_end = 1740960000

        mock_list = MagicMock()
        mock_list.auto_paging_iter.return_value = [mock_sub]

        with patch("apps.subscriptions.stripe.sync.stripe") as mock_stripe:
            mock_stripe.Subscription.list.return_value = mock_list

            result = sync_subscriptions(tenant)

        assert result["synced"] == 1
        assert result["skipped"] == 0

        sub = StripeSubscription.objects.get(stripe_subscription_id="sub_sync_1")
        assert sub.stripe_product_name == "Enterprise"
        assert sub.amount_micros == 199_000_000

    def test_skips_subscription_with_unknown_customer(self):
        from apps.subscriptions.stripe.sync import sync_subscriptions
        from apps.subscriptions.models import StripeSubscription

        tenant = Tenant.objects.create(
            name="test",
            products=["metering", "subscriptions"],
            stripe_connected_account_id="acct_test2",
        )

        mock_sub = MagicMock()
        mock_sub.id = "sub_unknown_cust"
        mock_sub.customer = "cus_nobody"
        mock_sub.status = "active"
        mock_sub.plan.product.name = "Pro"
        mock_sub.plan.amount = 4900
        mock_sub.plan.currency = "usd"
        mock_sub.plan.interval = "month"
        mock_sub.current_period_start = 1738368000
        mock_sub.current_period_end = 1740960000

        mock_list = MagicMock()
        mock_list.auto_paging_iter.return_value = [mock_sub]

        with patch("apps.subscriptions.stripe.sync.stripe") as mock_stripe:
            mock_stripe.Subscription.list.return_value = mock_list

            result = sync_subscriptions(tenant)

        assert result["synced"] == 0
        assert result["skipped"] == 1
        assert not StripeSubscription.objects.filter(stripe_subscription_id="sub_unknown_cust").exists()

    def test_updates_existing_subscription(self):
        from apps.subscriptions.stripe.sync import sync_subscriptions
        from apps.subscriptions.models import StripeSubscription

        tenant = Tenant.objects.create(
            name="test",
            products=["metering", "subscriptions"],
            stripe_connected_account_id="acct_test3",
        )
        customer = Customer.objects.create(
            tenant=tenant, external_id="cust-1", stripe_customer_id="cus_existing",
        )
        now = timezone.now()
        StripeSubscription.objects.create(
            tenant=tenant, customer=customer,
            stripe_subscription_id="sub_exists",
            stripe_product_name="Old Plan", status="trialing",
            amount_micros=29_000_000, currency="usd", interval="month",
            current_period_start=now, current_period_end=now, last_synced_at=now,
        )

        mock_sub = MagicMock()
        mock_sub.id = "sub_exists"
        mock_sub.customer = "cus_existing"
        mock_sub.status = "active"
        mock_sub.plan.product.name = "Pro Plan"
        mock_sub.plan.amount = 4900
        mock_sub.plan.currency = "usd"
        mock_sub.plan.interval = "month"
        mock_sub.current_period_start = 1738368000
        mock_sub.current_period_end = 1740960000

        mock_list = MagicMock()
        mock_list.auto_paging_iter.return_value = [mock_sub]

        with patch("apps.subscriptions.stripe.sync.stripe") as mock_stripe:
            mock_stripe.Subscription.list.return_value = mock_list

            result = sync_subscriptions(tenant)

        assert result["synced"] == 1
        sub = StripeSubscription.objects.get(stripe_subscription_id="sub_exists")
        assert sub.status == "active"
        assert sub.stripe_product_name == "Pro Plan"
        assert sub.amount_micros == 49_000_000
```

**Step 2: Run tests to verify they fail**

```bash
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/subscriptions/tests/test_sync.py -v
```
Expected: FAIL — `sync_subscriptions` doesn't exist.

**Step 3: Implement sync service**

```python
# apps/subscriptions/stripe/sync.py
import logging
from datetime import datetime

import stripe
from django.conf import settings
from django.utils import timezone

from apps.subscriptions.models import StripeSubscription
from apps.platform.customers.models import Customer

logger = logging.getLogger(__name__)

stripe.api_key = settings.STRIPE_SECRET_KEY


def _unix_to_datetime(ts):
    """Convert unix timestamp to timezone-aware datetime."""
    if ts is None:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc)


def sync_subscriptions(tenant):
    """Full sync of active subscriptions from tenant's Connected Account.

    Returns dict with counts: {"synced": N, "skipped": N, "errors": N}
    """
    if not tenant.stripe_connected_account_id:
        logger.warning("Tenant has no stripe_connected_account_id", extra={
            "data": {"tenant_id": str(tenant.id)},
        })
        return {"synced": 0, "skipped": 0, "errors": 0}

    # Build a lookup of stripe_customer_id → Customer for this tenant
    customers_by_stripe_id = {
        c.stripe_customer_id: c
        for c in Customer.objects.filter(
            tenant=tenant,
            stripe_customer_id__gt="",
        )
    }

    subscriptions = stripe.Subscription.list(
        status="all",
        stripe_account=tenant.stripe_connected_account_id,
        expand=["data.plan.product"],
    )

    synced = 0
    skipped = 0
    errors = 0

    for stripe_sub in subscriptions.auto_paging_iter():
        customer = customers_by_stripe_id.get(stripe_sub.customer)
        if not customer:
            logger.info("Skipping subscription — no matching customer", extra={
                "data": {
                    "stripe_subscription_id": stripe_sub.id,
                    "stripe_customer_id": stripe_sub.customer,
                },
            })
            skipped += 1
            continue

        try:
            StripeSubscription.objects.update_or_create(
                stripe_subscription_id=stripe_sub.id,
                defaults={
                    "tenant": tenant,
                    "customer": customer,
                    "stripe_product_name": stripe_sub.plan.product.name,
                    "status": stripe_sub.status,
                    "amount_micros": stripe_sub.plan.amount * 10_000,
                    "currency": stripe_sub.plan.currency,
                    "interval": stripe_sub.plan.interval,
                    "current_period_start": _unix_to_datetime(stripe_sub.current_period_start),
                    "current_period_end": _unix_to_datetime(stripe_sub.current_period_end),
                    "last_synced_at": timezone.now(),
                },
            )
            synced += 1
        except Exception:
            logger.exception("Error syncing subscription", extra={
                "data": {"stripe_subscription_id": stripe_sub.id},
            })
            errors += 1

    return {"synced": synced, "skipped": skipped, "errors": errors}
```

**Step 4: Run tests**

```bash
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/subscriptions/tests/test_sync.py -v
```
Expected: All 3 tests PASS.

**Step 5: Commit**

```bash
git add apps/subscriptions/stripe/sync.py apps/subscriptions/tests/test_sync.py
git commit -m "feat: implement Stripe subscription full sync service"
```

---

## Phase 4: Unit Economics Calculation

> Build the EconomicsService that combines subscription revenue (from synced Stripe invoices) with usage costs (from event bus accumulator) to calculate per-customer margins.

### Task 7: Implement EconomicsService

**Files:**
- Modify: `ubb-platform/apps/subscriptions/economics/services.py`
- Create: `ubb-platform/apps/subscriptions/tests/test_economics.py`

**Step 1: Write the failing test**

```python
# apps/subscriptions/tests/test_economics.py
import pytest
from datetime import date
from decimal import Decimal
from django.utils import timezone
from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer


@pytest.mark.django_db
class TestEconomicsService:
    def _create_tenant_and_customer(self):
        tenant = Tenant.objects.create(name="test", products=["metering", "subscriptions"])
        customer = Customer.objects.create(tenant=tenant, external_id="cust-1")
        return tenant, customer

    def test_calculates_profitable_customer(self):
        from apps.subscriptions.economics.services import EconomicsService
        from apps.subscriptions.economics.models import CustomerCostAccumulator, CustomerEconomics
        from apps.subscriptions.models import StripeSubscription, SubscriptionInvoice

        tenant, customer = self._create_tenant_and_customer()
        now = timezone.now()
        period_start = date(2026, 1, 1)
        period_end = date(2026, 2, 1)

        # Subscription: $199/mo
        sub = StripeSubscription.objects.create(
            tenant=tenant, customer=customer,
            stripe_subscription_id="sub_econ_1",
            stripe_product_name="Enterprise", status="active",
            amount_micros=199_000_000, currency="usd", interval="month",
            current_period_start=now, current_period_end=now, last_synced_at=now,
        )
        SubscriptionInvoice.objects.create(
            tenant=tenant, customer=customer, stripe_subscription=sub,
            stripe_invoice_id="in_econ_1",
            amount_paid_micros=199_000_000,
            currency="usd",
            period_start=timezone.make_aware(timezone.datetime(2026, 1, 1)),
            period_end=timezone.make_aware(timezone.datetime(2026, 2, 1)),
            paid_at=now,
        )

        # Usage cost: $47.20
        CustomerCostAccumulator.objects.create(
            tenant=tenant, customer=customer,
            period_start=period_start, period_end=period_end,
            total_cost_micros=47_200_000, event_count=500,
        )

        result = EconomicsService.calculate_customer_economics(
            tenant.id, customer.id, period_start, period_end,
        )

        assert result.subscription_revenue_micros == 199_000_000
        assert result.usage_cost_micros == 47_200_000
        assert result.gross_margin_micros == 151_800_000
        assert result.margin_percentage == Decimal("76.28")

    def test_calculates_unprofitable_customer(self):
        from apps.subscriptions.economics.services import EconomicsService
        from apps.subscriptions.economics.models import CustomerCostAccumulator
        from apps.subscriptions.models import StripeSubscription, SubscriptionInvoice

        tenant, customer = self._create_tenant_and_customer()
        now = timezone.now()
        period_start = date(2026, 1, 1)
        period_end = date(2026, 2, 1)

        sub = StripeSubscription.objects.create(
            tenant=tenant, customer=customer,
            stripe_subscription_id="sub_econ_2",
            stripe_product_name="Pro", status="active",
            amount_micros=49_000_000, currency="usd", interval="month",
            current_period_start=now, current_period_end=now, last_synced_at=now,
        )
        SubscriptionInvoice.objects.create(
            tenant=tenant, customer=customer, stripe_subscription=sub,
            stripe_invoice_id="in_econ_2",
            amount_paid_micros=49_000_000, currency="usd",
            period_start=timezone.make_aware(timezone.datetime(2026, 1, 1)),
            period_end=timezone.make_aware(timezone.datetime(2026, 2, 1)),
            paid_at=now,
        )
        CustomerCostAccumulator.objects.create(
            tenant=tenant, customer=customer,
            period_start=period_start, period_end=period_end,
            total_cost_micros=62_300_000, event_count=1000,
        )

        result = EconomicsService.calculate_customer_economics(
            tenant.id, customer.id, period_start, period_end,
        )

        assert result.gross_margin_micros == -13_300_000
        assert result.margin_percentage == Decimal("-27.14")

    def test_zero_revenue_gives_zero_margin(self):
        from apps.subscriptions.economics.services import EconomicsService
        from apps.subscriptions.economics.models import CustomerCostAccumulator

        tenant, customer = self._create_tenant_and_customer()
        period_start = date(2026, 1, 1)
        period_end = date(2026, 2, 1)

        CustomerCostAccumulator.objects.create(
            tenant=tenant, customer=customer,
            period_start=period_start, period_end=period_end,
            total_cost_micros=10_000_000, event_count=100,
        )

        result = EconomicsService.calculate_customer_economics(
            tenant.id, customer.id, period_start, period_end,
        )

        assert result.subscription_revenue_micros == 0
        assert result.usage_cost_micros == 10_000_000
        assert result.gross_margin_micros == -10_000_000
        assert result.margin_percentage == Decimal("0")  # Can't divide by zero revenue

    def test_calculate_all_economics(self):
        from apps.subscriptions.economics.services import EconomicsService
        from apps.subscriptions.economics.models import CustomerCostAccumulator, CustomerEconomics
        from apps.subscriptions.models import StripeSubscription, SubscriptionInvoice

        tenant, cust1 = self._create_tenant_and_customer()
        cust2 = Customer.objects.create(tenant=tenant, external_id="cust-2")
        now = timezone.now()
        period_start = date(2026, 1, 1)
        period_end = date(2026, 2, 1)

        for i, (cust, sub_id, inv_id, rev, cost) in enumerate([
            (cust1, "sub_all_1", "in_all_1", 199_000_000, 47_200_000),
            (cust2, "sub_all_2", "in_all_2", 49_000_000, 62_300_000),
        ]):
            sub = StripeSubscription.objects.create(
                tenant=tenant, customer=cust,
                stripe_subscription_id=sub_id,
                stripe_product_name="Plan", status="active",
                amount_micros=rev, currency="usd", interval="month",
                current_period_start=now, current_period_end=now, last_synced_at=now,
            )
            SubscriptionInvoice.objects.create(
                tenant=tenant, customer=cust, stripe_subscription=sub,
                stripe_invoice_id=inv_id, amount_paid_micros=rev, currency="usd",
                period_start=timezone.make_aware(timezone.datetime(2026, 1, 1)),
                period_end=timezone.make_aware(timezone.datetime(2026, 2, 1)),
                paid_at=now,
            )
            CustomerCostAccumulator.objects.create(
                tenant=tenant, customer=cust,
                period_start=period_start, period_end=period_end,
                total_cost_micros=cost, event_count=100,
            )

        results = EconomicsService.calculate_all_economics(
            tenant.id, period_start, period_end,
        )

        assert len(results) == 2
        assert CustomerEconomics.objects.filter(tenant=tenant).count() == 2
```

**Step 2: Run tests to verify they fail**

```bash
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/subscriptions/tests/test_economics.py -v
```
Expected: FAIL — `EconomicsService` doesn't exist.

**Step 3: Implement EconomicsService**

```python
# apps/subscriptions/economics/services.py
from decimal import Decimal, ROUND_HALF_UP

from django.db.models import Sum

from apps.subscriptions.economics.models import CustomerCostAccumulator, CustomerEconomics
from apps.subscriptions.models import StripeSubscription, SubscriptionInvoice


class EconomicsService:
    @staticmethod
    def calculate_customer_economics(tenant_id, customer_id, period_start, period_end):
        """Calculate unit economics for a single customer in a period.

        Revenue: from synced Stripe invoices (SubscriptionInvoice)
        Cost: from event-bus accumulated usage data (CustomerCostAccumulator)
        """
        # Revenue from synced Stripe invoices
        revenue = SubscriptionInvoice.objects.filter(
            tenant_id=tenant_id,
            customer_id=customer_id,
            period_start__gte=period_start,
            period_end__lte=period_end,
        ).aggregate(total=Sum("amount_paid_micros"))["total"] or 0

        # Usage cost from accumulator (populated by event bus handler)
        cost = CustomerCostAccumulator.objects.filter(
            tenant_id=tenant_id,
            customer_id=customer_id,
            period_start__gte=period_start,
            period_end__lte=period_end,
        ).aggregate(total=Sum("total_cost_micros"))["total"] or 0

        margin = revenue - cost
        if revenue > 0:
            margin_pct = (Decimal(margin) / Decimal(revenue) * 100).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
        else:
            margin_pct = Decimal("0")

        economics, _ = CustomerEconomics.objects.update_or_create(
            tenant_id=tenant_id,
            customer_id=customer_id,
            period_start=period_start,
            defaults={
                "period_end": period_end,
                "subscription_revenue_micros": revenue,
                "usage_cost_micros": cost,
                "gross_margin_micros": margin,
                "margin_percentage": margin_pct,
            },
        )
        return economics

    @staticmethod
    def calculate_all_economics(tenant_id, period_start, period_end):
        """Calculate unit economics for all customers with active subscriptions."""
        customer_ids = StripeSubscription.objects.filter(
            tenant_id=tenant_id,
            status="active",
        ).values_list("customer_id", flat=True).distinct()

        results = []
        for customer_id in customer_ids:
            result = EconomicsService.calculate_customer_economics(
                tenant_id, customer_id, period_start, period_end,
            )
            results.append(result)
        return results
```

**Step 4: Run tests**

```bash
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/subscriptions/tests/test_economics.py -v
```
Expected: All 4 tests PASS.

**Step 5: Run full test suite**

```bash
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest --tb=short -q
```

**Step 6: Commit**

```bash
git add apps/subscriptions/economics/services.py apps/subscriptions/tests/test_economics.py
git commit -m "feat: implement EconomicsService for per-customer unit economics"
```

---

## Phase 5: API Endpoints

> Build the `/api/v1/subscriptions/` API surface with ProductAccess gating, Stripe webhook endpoint, and all dashboard endpoints.

### Task 8: Create subscriptions API schemas

**Files:**
- Modify: `ubb-platform/apps/subscriptions/api/schemas.py`

**Step 1: Write schemas**

```python
# apps/subscriptions/api/schemas.py
from typing import Optional
from ninja import Schema


class SyncResponse(Schema):
    synced: int
    skipped: int
    errors: int


class StripeSubscriptionOut(Schema):
    id: str
    stripe_subscription_id: str
    stripe_product_name: str
    status: str
    amount_micros: int
    currency: str
    interval: str
    current_period_start: str
    current_period_end: str
    last_synced_at: str


class SubscriptionInvoiceOut(Schema):
    id: str
    stripe_invoice_id: str
    amount_paid_micros: int
    currency: str
    period_start: str
    period_end: str
    paid_at: str


class CustomerEconomicsOut(Schema):
    customer_id: str
    external_id: str
    plan: str
    subscription_revenue_micros: int
    usage_cost_micros: int
    gross_margin_micros: int
    margin_percentage: float


class EconomicsListResponse(Schema):
    period: dict
    customers: list[CustomerEconomicsOut]
    summary: dict


class EconomicsSummaryResponse(Schema):
    period: dict
    total_revenue_micros: int
    total_cost_micros: int
    total_margin_micros: int
    avg_margin_percentage: float
    unprofitable_customers: int
    total_customers: int


class PaginatedInvoicesResponse(Schema):
    data: list[SubscriptionInvoiceOut]
    next_cursor: Optional[str] = None
    has_more: bool
```

**Step 2: Commit**

```bash
git add apps/subscriptions/api/schemas.py
git commit -m "feat: add subscriptions API schemas"
```

---

### Task 9: Create subscriptions API endpoints

**Files:**
- Modify: `ubb-platform/apps/subscriptions/api/endpoints.py`
- Modify: `ubb-platform/config/urls.py`
- Create: `ubb-platform/apps/subscriptions/tests/test_endpoints.py`

**Step 1: Write the failing tests**

```python
# apps/subscriptions/tests/test_endpoints.py
import pytest
import json
from datetime import date
from django.utils import timezone
from django.test import TestCase, Client
from apps.platform.tenants.models import Tenant, TenantApiKey
from apps.platform.customers.models import Customer


class TestSubscriptionsProductAccess(TestCase):
    def setUp(self):
        self.http_client = Client()

    def test_returns_403_without_subscriptions_product(self):
        tenant = Tenant.objects.create(
            name="metering-only", products=["metering"],
        )
        _, raw_key = TenantApiKey.create_key(tenant=tenant, label="test")

        response = self.http_client.get(
            "/api/v1/subscriptions/economics",
            HTTP_AUTHORIZATION=f"Bearer {raw_key}",
        )
        self.assertEqual(response.status_code, 403)

    def test_allows_subscriptions_tenant(self):
        tenant = Tenant.objects.create(
            name="sub-tenant",
            products=["metering", "subscriptions"],
        )
        _, raw_key = TenantApiKey.create_key(tenant=tenant, label="test")

        response = self.http_client.get(
            "/api/v1/subscriptions/economics",
            HTTP_AUTHORIZATION=f"Bearer {raw_key}",
        )
        # Should not be 403 (may be 200 with empty data)
        self.assertNotEqual(response.status_code, 403)


class TestEconomicsEndpoints(TestCase):
    def setUp(self):
        self.http_client = Client()
        self.tenant = Tenant.objects.create(
            name="test", products=["metering", "subscriptions"],
        )
        _, self.raw_key = TenantApiKey.create_key(tenant=self.tenant, label="test")
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="cust-1",
        )

    def test_economics_returns_customer_data(self):
        from apps.subscriptions.models import StripeSubscription, SubscriptionInvoice
        from apps.subscriptions.economics.models import CustomerCostAccumulator

        now = timezone.now()
        sub = StripeSubscription.objects.create(
            tenant=self.tenant, customer=self.customer,
            stripe_subscription_id="sub_ep_1",
            stripe_product_name="Pro", status="active",
            amount_micros=49_000_000, currency="usd", interval="month",
            current_period_start=now, current_period_end=now, last_synced_at=now,
        )
        today = timezone.now().date()
        period_start = today.replace(day=1)
        SubscriptionInvoice.objects.create(
            tenant=self.tenant, customer=self.customer,
            stripe_subscription=sub,
            stripe_invoice_id="in_ep_1",
            amount_paid_micros=49_000_000, currency="usd",
            period_start=timezone.make_aware(
                timezone.datetime(period_start.year, period_start.month, 1)
            ),
            period_end=now,
            paid_at=now,
        )
        CustomerCostAccumulator.objects.create(
            tenant=self.tenant, customer=self.customer,
            period_start=period_start,
            period_end=period_start.replace(
                month=period_start.month + 1 if period_start.month < 12 else 1,
                year=period_start.year if period_start.month < 12 else period_start.year + 1,
            ),
            total_cost_micros=20_000_000, event_count=200,
        )

        response = self.http_client.get(
            "/api/v1/subscriptions/economics",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("customers", body)
        self.assertEqual(len(body["customers"]), 1)
        self.assertEqual(body["customers"][0]["subscription_revenue_micros"], 49_000_000)

    def test_customer_economics_endpoint(self):
        response = self.http_client.get(
            f"/api/v1/subscriptions/economics/{self.customer.id}",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        # Should return 200 even with no data
        self.assertEqual(response.status_code, 200)

    def test_subscription_detail_endpoint(self):
        from apps.subscriptions.models import StripeSubscription

        now = timezone.now()
        StripeSubscription.objects.create(
            tenant=self.tenant, customer=self.customer,
            stripe_subscription_id="sub_detail",
            stripe_product_name="Pro", status="active",
            amount_micros=49_000_000, currency="usd", interval="month",
            current_period_start=now, current_period_end=now, last_synced_at=now,
        )

        response = self.http_client.get(
            f"/api/v1/subscriptions/customers/{self.customer.id}/subscription",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        self.assertEqual(response.status_code, 200)
```

**Step 2: Run tests to verify they fail**

```bash
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/subscriptions/tests/test_endpoints.py -v
```
Expected: FAIL — 404, endpoints don't exist.

**Step 3: Implement endpoints**

```python
# apps/subscriptions/api/endpoints.py
from datetime import date
from decimal import Decimal

from django.db.models import Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone
from ninja import NinjaAPI

from api.v1.pagination import apply_cursor_filter, encode_cursor
from apps.platform.customers.models import Customer
from apps.subscriptions.api.schemas import (
    SyncResponse, StripeSubscriptionOut,
    CustomerEconomicsOut, EconomicsListResponse,
    EconomicsSummaryResponse, PaginatedInvoicesResponse,
    SubscriptionInvoiceOut,
)
from apps.subscriptions.economics.services import EconomicsService
from apps.subscriptions.models import StripeSubscription, SubscriptionInvoice
from core.auth import ApiKeyAuth, ProductAccess

subscriptions_api = NinjaAPI(auth=ApiKeyAuth(), urls_namespace="ubb_subscriptions_v1")

_product_check = ProductAccess("subscriptions")


def _current_period():
    """Return (period_start, period_end) for the current calendar month."""
    today = timezone.now().date()
    first_of_month = today.replace(day=1)
    if today.month == 12:
        first_of_next_month = today.replace(year=today.year + 1, month=1, day=1)
    else:
        first_of_next_month = today.replace(month=today.month + 1, day=1)
    return first_of_month, first_of_next_month


# ---------- Sync ----------


@subscriptions_api.post("/sync", response=SyncResponse)
def trigger_sync(request):
    _product_check(request)
    from apps.subscriptions.stripe.sync import sync_subscriptions
    result = sync_subscriptions(request.auth.tenant)
    return result


# ---------- Unit Economics ----------


@subscriptions_api.get("/economics")
def list_economics(request, period_start: date = None, period_end: date = None):
    _product_check(request)
    tenant = request.auth.tenant

    if period_start is None or period_end is None:
        period_start, period_end = _current_period()

    results = EconomicsService.calculate_all_economics(
        tenant.id, period_start, period_end,
    )

    customers_out = []
    for econ in results:
        customer = Customer.objects.get(id=econ.customer_id)
        # Find the subscription plan name for this customer
        sub = StripeSubscription.objects.filter(
            tenant=tenant, customer=customer, status="active",
        ).first()
        plan_name = sub.stripe_product_name if sub else "Unknown"

        customers_out.append({
            "customer_id": str(customer.id),
            "external_id": customer.external_id,
            "plan": plan_name,
            "subscription_revenue_micros": econ.subscription_revenue_micros,
            "usage_cost_micros": econ.usage_cost_micros,
            "gross_margin_micros": econ.gross_margin_micros,
            "margin_percentage": float(econ.margin_percentage),
        })

    total_revenue = sum(c["subscription_revenue_micros"] for c in customers_out)
    total_cost = sum(c["usage_cost_micros"] for c in customers_out)
    total_margin = total_revenue - total_cost
    avg_margin = (
        float(Decimal(total_margin) / Decimal(total_revenue) * 100)
        if total_revenue > 0 else 0.0
    )
    unprofitable = sum(1 for c in customers_out if c["gross_margin_micros"] < 0)

    return {
        "period": {"start": period_start.isoformat(), "end": period_end.isoformat()},
        "customers": customers_out,
        "summary": {
            "total_revenue_micros": total_revenue,
            "total_cost_micros": total_cost,
            "total_margin_micros": total_margin,
            "avg_margin_percentage": round(avg_margin, 2),
            "unprofitable_customers": unprofitable,
        },
    }


@subscriptions_api.get("/economics/{customer_id}")
def get_customer_economics(request, customer_id: str,
                           period_start: date = None, period_end: date = None):
    _product_check(request)
    tenant = request.auth.tenant
    customer = get_object_or_404(Customer, id=customer_id, tenant=tenant)

    if period_start is None or period_end is None:
        period_start, period_end = _current_period()

    econ = EconomicsService.calculate_customer_economics(
        tenant.id, customer.id, period_start, period_end,
    )

    sub = StripeSubscription.objects.filter(
        tenant=tenant, customer=customer, status="active",
    ).first()
    plan_name = sub.stripe_product_name if sub else "Unknown"

    return {
        "customer_id": str(customer.id),
        "external_id": customer.external_id,
        "plan": plan_name,
        "period": {"start": period_start.isoformat(), "end": period_end.isoformat()},
        "subscription_revenue_micros": econ.subscription_revenue_micros,
        "usage_cost_micros": econ.usage_cost_micros,
        "gross_margin_micros": econ.gross_margin_micros,
        "margin_percentage": float(econ.margin_percentage),
    }


@subscriptions_api.get("/economics/summary")
def get_economics_summary(request, period_start: date = None, period_end: date = None):
    _product_check(request)
    tenant = request.auth.tenant

    if period_start is None or period_end is None:
        period_start, period_end = _current_period()

    results = EconomicsService.calculate_all_economics(
        tenant.id, period_start, period_end,
    )

    total_revenue = sum(r.subscription_revenue_micros for r in results)
    total_cost = sum(r.usage_cost_micros for r in results)
    total_margin = total_revenue - total_cost
    avg_margin = (
        float(Decimal(total_margin) / Decimal(total_revenue) * 100)
        if total_revenue > 0 else 0.0
    )
    unprofitable = sum(1 for r in results if r.gross_margin_micros < 0)

    return {
        "period": {"start": period_start.isoformat(), "end": period_end.isoformat()},
        "total_revenue_micros": total_revenue,
        "total_cost_micros": total_cost,
        "total_margin_micros": total_margin,
        "avg_margin_percentage": round(avg_margin, 2),
        "unprofitable_customers": unprofitable,
        "total_customers": len(results),
    }


# ---------- Subscription Data (read-only) ----------


@subscriptions_api.get("/customers/{customer_id}/subscription")
def get_subscription(request, customer_id: str):
    _product_check(request)
    tenant = request.auth.tenant
    customer = get_object_or_404(Customer, id=customer_id, tenant=tenant)

    sub = StripeSubscription.objects.filter(
        tenant=tenant, customer=customer,
    ).order_by("-created_at").first()

    if not sub:
        return subscriptions_api.create_response(request, {"error": "No subscription found"}, status=404)

    return {
        "id": str(sub.id),
        "stripe_subscription_id": sub.stripe_subscription_id,
        "stripe_product_name": sub.stripe_product_name,
        "status": sub.status,
        "amount_micros": sub.amount_micros,
        "currency": sub.currency,
        "interval": sub.interval,
        "current_period_start": sub.current_period_start.isoformat(),
        "current_period_end": sub.current_period_end.isoformat(),
        "last_synced_at": sub.last_synced_at.isoformat(),
    }


@subscriptions_api.get("/customers/{customer_id}/invoices")
def get_invoices(request, customer_id: str, cursor: str = None, limit: int = 50):
    _product_check(request)
    tenant = request.auth.tenant
    customer = get_object_or_404(Customer, id=customer_id, tenant=tenant)
    limit = min(max(limit, 1), 100)

    qs = SubscriptionInvoice.objects.filter(
        tenant=tenant, customer=customer,
    ).order_by("-paid_at", "-id")

    if cursor:
        try:
            qs = apply_cursor_filter(qs, cursor, time_field="paid_at")
        except ValueError:
            from ninja.errors import HttpError
            raise HttpError(400, "Invalid cursor")

    invoices = list(qs[:limit + 1])
    has_more = len(invoices) > limit
    invoices = invoices[:limit]

    next_cursor = None
    if has_more and invoices:
        last = invoices[-1]
        next_cursor = encode_cursor(last.paid_at, last.id)

    return {
        "data": [
            {
                "id": str(inv.id),
                "stripe_invoice_id": inv.stripe_invoice_id,
                "amount_paid_micros": inv.amount_paid_micros,
                "currency": inv.currency,
                "period_start": inv.period_start.isoformat(),
                "period_end": inv.period_end.isoformat(),
                "paid_at": inv.paid_at.isoformat(),
            }
            for inv in invoices
        ],
        "next_cursor": next_cursor,
        "has_more": has_more,
    }
```

**Step 4: Wire up in `config/urls.py`**

Add import and route:

```python
from apps.subscriptions.api.endpoints import subscriptions_api

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/me/", me_api.urls),
    path("api/v1/tenant/", tenant_api.urls),
    path("api/v1/metering/", metering_api.urls),
    path("api/v1/billing/", billing_api.urls),
    path("api/v1/subscriptions/", subscriptions_api.urls),  # NEW
    path("api/v1/webhooks/stripe", stripe_webhook),
    path("api/v1/", api.urls),
]
```

**Step 5: Run tests**

```bash
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/subscriptions/tests/test_endpoints.py -v
```
Expected: All tests PASS.

**Step 6: Run full test suite**

```bash
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest --tb=short -q
```

**Step 7: Commit**

```bash
git add apps/subscriptions/api/endpoints.py config/urls.py apps/subscriptions/tests/test_endpoints.py
git commit -m "feat: add subscriptions API endpoints with ProductAccess gating"
```

---

### Task 10: Create subscriptions webhook endpoint

The subscriptions product needs its own Stripe webhook endpoint, separate from billing's. It handles `invoice.paid`, `customer.subscription.created`, `customer.subscription.updated`, `customer.subscription.deleted`.

**Files:**
- Modify: `ubb-platform/apps/subscriptions/api/endpoints.py` — add webhook view
- Modify: `ubb-platform/config/urls.py` — add webhook route
- Create: `ubb-platform/apps/subscriptions/tests/test_webhook_endpoint.py`

**Step 1: Write the failing test**

```python
# apps/subscriptions/tests/test_webhook_endpoint.py
import json
import pytest
from unittest.mock import patch, MagicMock
from django.test import TestCase, Client
from django.utils import timezone


class TestSubscriptionsWebhookEndpoint(TestCase):
    def setUp(self):
        self.http_client = Client()

    @patch("apps.subscriptions.api.endpoints.stripe")
    def test_returns_400_on_bad_signature(self, mock_stripe):
        mock_stripe.Webhook.construct_event.side_effect = ValueError("bad sig")

        response = self.http_client.post(
            "/api/v1/subscriptions/webhooks/stripe",
            data=b"{}",
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="bad",
        )
        self.assertEqual(response.status_code, 400)

    @patch("apps.subscriptions.api.endpoints.stripe")
    def test_dispatches_subscription_created(self, mock_stripe):
        from apps.platform.tenants.models import Tenant
        from apps.platform.customers.models import Customer

        tenant = Tenant.objects.create(
            name="test",
            products=["metering", "subscriptions"],
            stripe_connected_account_id="acct_wh_test",
        )
        customer = Customer.objects.create(
            tenant=tenant, external_id="cust-1", stripe_customer_id="cus_wh",
        )

        mock_event = MagicMock()
        mock_event.id = "evt_wh_1"
        mock_event.type = "customer.subscription.created"
        mock_event.account = "acct_wh_test"
        mock_event.data.object.id = "sub_wh_1"
        mock_event.data.object.customer = "cus_wh"
        mock_event.data.object.status = "active"
        mock_event.data.object.current_period_start = 1738368000
        mock_event.data.object.current_period_end = 1740960000
        mock_event.data.object.plan.product.name = "Pro"
        mock_event.data.object.plan.amount = 4900
        mock_event.data.object.plan.currency = "usd"
        mock_event.data.object.plan.interval = "month"

        mock_stripe.Webhook.construct_event.return_value = mock_event

        response = self.http_client.post(
            "/api/v1/subscriptions/webhooks/stripe",
            data=b"{}",
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="valid",
        )
        self.assertEqual(response.status_code, 200)

        from apps.subscriptions.models import StripeSubscription
        self.assertTrue(
            StripeSubscription.objects.filter(stripe_subscription_id="sub_wh_1").exists()
        )
```

**Step 2: Run tests to verify they fail**

```bash
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/subscriptions/tests/test_webhook_endpoint.py -v
```
Expected: FAIL — endpoint doesn't exist.

**Step 3: Add webhook endpoint to subscriptions API**

Add to `apps/subscriptions/api/endpoints.py`:

```python
import stripe
from django.conf import settings
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from apps.subscriptions.api.webhooks import (
    handle_subscription_created, handle_subscription_updated,
    handle_subscription_deleted, handle_invoice_paid,
)

SUBSCRIPTIONS_WEBHOOK_HANDLERS = {
    "customer.subscription.created": handle_subscription_created,
    "customer.subscription.updated": handle_subscription_updated,
    "customer.subscription.deleted": handle_subscription_deleted,
    "invoice.paid": handle_invoice_paid,
}


@csrf_exempt
@require_POST
def subscriptions_stripe_webhook(request):
    """Stripe webhook endpoint for subscription events."""
    payload = request.body
    sig_header = request.META.get("HTTP_STRIPE_SIGNATURE", "")

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header,
            settings.STRIPE_SUBSCRIPTIONS_WEBHOOK_SECRET
            if hasattr(settings, "STRIPE_SUBSCRIPTIONS_WEBHOOK_SECRET")
            else settings.STRIPE_WEBHOOK_SECRET,
        )
    except (ValueError, stripe.error.SignatureVerificationError):
        return HttpResponse(status=400)

    handler = SUBSCRIPTIONS_WEBHOOK_HANDLERS.get(event.type)
    if not handler:
        return JsonResponse({"status": "ok"})

    try:
        handler(event)
    except Exception:
        import logging
        logging.getLogger(__name__).exception(
            "Subscriptions webhook handler failed",
            extra={"data": {"event_id": event.id, "event_type": event.type}},
        )
        return HttpResponse(status=500)

    return JsonResponse({"status": "ok"})
```

**Step 4: Wire up webhook in `config/urls.py`**

```python
from apps.subscriptions.api.endpoints import subscriptions_api, subscriptions_stripe_webhook

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/me/", me_api.urls),
    path("api/v1/tenant/", tenant_api.urls),
    path("api/v1/metering/", metering_api.urls),
    path("api/v1/billing/", billing_api.urls),
    path("api/v1/subscriptions/", subscriptions_api.urls),
    path("api/v1/subscriptions/webhooks/stripe", subscriptions_stripe_webhook),  # NEW
    path("api/v1/webhooks/stripe", stripe_webhook),
    path("api/v1/", api.urls),
]
```

> **NOTE:** The subscriptions webhook path MUST come before the NinjaAPI `subscriptions_api.urls` would catch it, or use a distinct prefix. Since we're using a separate `path()`, order matters — place it before the NinjaAPI catch-all. Alternatively, if NinjaAPI catches all `/api/v1/subscriptions/*`, move the webhook outside to `/api/v1/subscriptions-webhooks/stripe`. Check which approach works by running the test.

**Step 5: Run tests**

```bash
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/subscriptions/tests/test_webhook_endpoint.py -v
```
Expected: All PASS.

**Step 6: Commit**

```bash
git add apps/subscriptions/api/endpoints.py config/urls.py apps/subscriptions/tests/test_webhook_endpoint.py
git commit -m "feat: add subscriptions Stripe webhook endpoint"
```

---

## Phase 6: Celery Tasks

> Add periodic task for daily economics recalculation and sync retry.

### Task 11: Add Celery tasks for economics calculation

**Files:**
- Modify: `ubb-platform/apps/subscriptions/tasks.py`
- Create: `ubb-platform/apps/subscriptions/tests/test_tasks.py`

**Step 1: Write the failing test**

```python
# apps/subscriptions/tests/test_tasks.py
import pytest
from unittest.mock import patch, MagicMock
from apps.platform.tenants.models import Tenant


@pytest.mark.django_db
class TestCalculateAllEconomicsTask:
    def test_runs_for_subscriptions_tenants_only(self):
        from apps.subscriptions.tasks import calculate_all_economics_task

        Tenant.objects.create(name="metering-only", products=["metering"])
        sub_tenant = Tenant.objects.create(
            name="sub-tenant", products=["metering", "subscriptions"],
        )

        with patch(
            "apps.subscriptions.tasks.EconomicsService.calculate_all_economics"
        ) as mock_calc:
            mock_calc.return_value = []
            calculate_all_economics_task()

            # Should only be called for the subscriptions tenant
            assert mock_calc.call_count == 1
            assert mock_calc.call_args[0][0] == sub_tenant.id
```

**Step 2: Run test to verify it fails**

```bash
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/subscriptions/tests/test_tasks.py -v
```
Expected: FAIL — task doesn't exist.

**Step 3: Implement tasks**

```python
# apps/subscriptions/tasks.py
import logging

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task(queue="ubb_economics")
def calculate_all_economics_task():
    """Daily task: recalculate unit economics for all subscriptions tenants."""
    from apps.platform.tenants.models import Tenant
    from apps.subscriptions.economics.services import EconomicsService

    today = timezone.now().date()
    period_start = today.replace(day=1)
    if today.month == 12:
        period_end = today.replace(year=today.year + 1, month=1, day=1)
    else:
        period_end = today.replace(month=today.month + 1, day=1)

    tenants = Tenant.objects.filter(
        products__contains=["subscriptions"],
        is_active=True,
    )

    for tenant in tenants:
        try:
            results = EconomicsService.calculate_all_economics(
                tenant.id, period_start, period_end,
            )
            logger.info(
                "Economics calculated",
                extra={"data": {
                    "tenant_id": str(tenant.id),
                    "customers": len(results),
                }},
            )
        except Exception:
            logger.exception(
                "Economics calculation failed",
                extra={"data": {"tenant_id": str(tenant.id)}},
            )


@shared_task(queue="ubb_subscriptions")
def sync_tenant_subscriptions_task(tenant_id):
    """On-demand task: sync subscriptions for a specific tenant."""
    from apps.platform.tenants.models import Tenant
    from apps.subscriptions.stripe.sync import sync_subscriptions

    tenant = Tenant.objects.get(id=tenant_id)
    result = sync_subscriptions(tenant)
    logger.info(
        "Subscription sync completed",
        extra={"data": {"tenant_id": str(tenant_id), **result}},
    )
    return result
```

**Step 4: Run tests**

```bash
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/subscriptions/tests/test_tasks.py -v
```
Expected: PASS.

**Step 5: Commit**

```bash
git add apps/subscriptions/tasks.py apps/subscriptions/tests/test_tasks.py
git commit -m "feat: add Celery tasks for economics calculation and subscription sync"
```

---

## Phase 7: SDK Support

> Add `SubscriptionsClient` to the SDK and wire it into `UBBClient`.

### Task 12: Create SubscriptionsClient in SDK

**Files:**
- Create: `ubb-sdk/ubb/subscriptions.py`
- Create: `ubb-sdk/tests/test_subscriptions_client.py`

**Step 1: Write the failing test**

```python
# ubb-sdk/tests/test_subscriptions_client.py
import pytest
import httpx
from unittest.mock import patch
from ubb.subscriptions import SubscriptionsClient


class TestSubscriptionsClient:
    def test_sync_calls_subscriptions_endpoint(self):
        client = SubscriptionsClient(api_key="ubb_live_test", base_url="http://localhost:8001")

        with patch.object(client._http, "post") as mock_post:
            mock_post.return_value = httpx.Response(
                200, json={"synced": 5, "skipped": 1, "errors": 0},
            )
            result = client.sync()

            call_url = mock_post.call_args[0][0]
            assert "/subscriptions/sync" in call_url
            assert result["synced"] == 5

    def test_get_economics_calls_subscriptions_endpoint(self):
        client = SubscriptionsClient(api_key="ubb_live_test", base_url="http://localhost:8001")

        with patch.object(client._http, "get") as mock_get:
            mock_get.return_value = httpx.Response(200, json={
                "period": {"start": "2026-01-01", "end": "2026-02-01"},
                "customers": [],
                "summary": {
                    "total_revenue_micros": 0,
                    "total_cost_micros": 0,
                    "total_margin_micros": 0,
                    "avg_margin_percentage": 0,
                    "unprofitable_customers": 0,
                },
            })

            result = client.get_economics()
            call_url = mock_get.call_args[0][0]
            assert "/subscriptions/economics" in call_url
            assert "customers" in result

    def test_get_customer_economics(self):
        client = SubscriptionsClient(api_key="ubb_live_test", base_url="http://localhost:8001")

        with patch.object(client._http, "get") as mock_get:
            mock_get.return_value = httpx.Response(200, json={
                "customer_id": "cust-1",
                "external_id": "acme",
                "plan": "Pro",
                "subscription_revenue_micros": 49_000_000,
                "usage_cost_micros": 20_000_000,
                "gross_margin_micros": 29_000_000,
                "margin_percentage": 59.18,
            })

            result = client.get_customer_economics("cust-1")
            assert result["gross_margin_micros"] == 29_000_000

    def test_get_subscription(self):
        client = SubscriptionsClient(api_key="ubb_live_test", base_url="http://localhost:8001")

        with patch.object(client._http, "get") as mock_get:
            mock_get.return_value = httpx.Response(200, json={
                "id": "uuid-1",
                "stripe_subscription_id": "sub_abc",
                "stripe_product_name": "Pro",
                "status": "active",
                "amount_micros": 49_000_000,
                "currency": "usd",
                "interval": "month",
                "current_period_start": "2026-01-01T00:00:00Z",
                "current_period_end": "2026-02-01T00:00:00Z",
                "last_synced_at": "2026-01-15T12:00:00Z",
            })

            result = client.get_subscription("cust-1")
            assert result["status"] == "active"

    def test_get_invoices(self):
        client = SubscriptionsClient(api_key="ubb_live_test", base_url="http://localhost:8001")

        with patch.object(client._http, "get") as mock_get:
            mock_get.return_value = httpx.Response(200, json={
                "data": [], "next_cursor": None, "has_more": False,
            })

            result = client.get_invoices("cust-1")
            assert result["has_more"] is False
```

**Step 2: Run test to verify it fails**

```bash
cd ubb-sdk && python -m pytest tests/test_subscriptions_client.py -v
```
Expected: FAIL — `SubscriptionsClient` doesn't exist.

**Step 3: Implement SubscriptionsClient**

```python
# ubb-sdk/ubb/subscriptions.py
from __future__ import annotations

import httpx

from ubb.exceptions import (
    UBBAuthError, UBBAPIError, UBBConflictError, UBBConnectionError,
)


class SubscriptionsClient:
    """Product-specific client for the UBB Subscriptions API (/api/v1/subscriptions/)."""

    def __init__(self, api_key: str, base_url: str = "http://localhost:8001",
                 timeout: float = 10.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._http = httpx.Client(
            base_url=self._base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout,
        )

    def __enter__(self) -> SubscriptionsClient:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        try:
            response = getattr(self._http, method)(path, **kwargs)
        except httpx.TimeoutException as e:
            raise UBBConnectionError("Request timed out", original=e) from e
        except httpx.ConnectError as e:
            raise UBBConnectionError("Could not connect to UBB API", original=e) from e
        if response.status_code == 401:
            raise UBBAuthError("Invalid or revoked API key")
        detail = self._extract_error_detail(response)
        if response.status_code == 409:
            raise UBBConflictError(detail)
        if response.status_code >= 400:
            raise UBBAPIError(response.status_code, detail)
        return response

    @staticmethod
    def _extract_error_detail(response: httpx.Response) -> str:
        try:
            body = response.json()
            if isinstance(body, dict) and "error" in body:
                return body["error"]
            if isinstance(body, dict) and "detail" in body:
                return body["detail"]
        except Exception:
            pass
        return response.text

    # ---- public API ----

    def sync(self) -> dict:
        """Trigger full Stripe subscription sync via POST /api/v1/subscriptions/sync."""
        r = self._request("post", "/api/v1/subscriptions/sync")
        return r.json()

    def get_economics(self, period_start: str | None = None,
                      period_end: str | None = None) -> dict:
        """Get unit economics for all customers via GET /api/v1/subscriptions/economics."""
        params = {}
        if period_start:
            params["period_start"] = period_start
        if period_end:
            params["period_end"] = period_end
        r = self._request("get", "/api/v1/subscriptions/economics", params=params)
        return r.json()

    def get_customer_economics(self, customer_id: str,
                               period_start: str | None = None,
                               period_end: str | None = None) -> dict:
        """Get unit economics for a single customer."""
        params = {}
        if period_start:
            params["period_start"] = period_start
        if period_end:
            params["period_end"] = period_end
        r = self._request("get", f"/api/v1/subscriptions/economics/{customer_id}", params=params)
        return r.json()

    def get_economics_summary(self, period_start: str | None = None,
                              period_end: str | None = None) -> dict:
        """Get aggregate economics summary."""
        params = {}
        if period_start:
            params["period_start"] = period_start
        if period_end:
            params["period_end"] = period_end
        r = self._request("get", "/api/v1/subscriptions/economics/summary", params=params)
        return r.json()

    def get_subscription(self, customer_id: str) -> dict:
        """Get customer's current subscription (synced from Stripe)."""
        r = self._request("get", f"/api/v1/subscriptions/customers/{customer_id}/subscription")
        return r.json()

    def get_invoices(self, customer_id: str, cursor: str | None = None,
                     limit: int = 20) -> dict:
        """Get customer's subscription invoice history."""
        params: dict = {"limit": limit}
        if cursor:
            params["cursor"] = cursor
        r = self._request("get", f"/api/v1/subscriptions/customers/{customer_id}/invoices", params=params)
        return r.json()

    def close(self) -> None:
        self._http.close()
```

**Step 4: Run tests**

```bash
cd ubb-sdk && python -m pytest tests/test_subscriptions_client.py -v
```
Expected: All PASS.

**Step 5: Commit**

```bash
git add ubb-sdk/ubb/subscriptions.py ubb-sdk/tests/test_subscriptions_client.py
git commit -m "feat: add SubscriptionsClient to SDK"
```

---

### Task 13: Wire SubscriptionsClient into UBBClient

**Files:**
- Modify: `ubb-sdk/ubb/client.py`
- Create: `ubb-sdk/tests/test_ubb_client_subscriptions.py`

**Step 1: Write the failing test**

```python
# ubb-sdk/tests/test_ubb_client_subscriptions.py
import pytest
from ubb.client import UBBClient


class TestUBBClientSubscriptions:
    def test_subscriptions_client_created_when_enabled(self):
        client = UBBClient(
            api_key="ubb_live_test",
            base_url="http://localhost:8001",
            metering=True,
            subscriptions=True,
        )
        assert client.subscriptions is not None
        from ubb.subscriptions import SubscriptionsClient
        assert isinstance(client.subscriptions, SubscriptionsClient)
        client.close()

    def test_subscriptions_client_none_when_disabled(self):
        client = UBBClient(
            api_key="ubb_live_test",
            base_url="http://localhost:8001",
            metering=True,
            subscriptions=False,
        )
        assert client.subscriptions is None
        client.close()

    def test_subscriptions_default_is_false(self):
        client = UBBClient(
            api_key="ubb_live_test",
            base_url="http://localhost:8001",
        )
        assert client.subscriptions is None
        client.close()
```

**Step 2: Run test to verify it fails**

```bash
cd ubb-sdk && python -m pytest tests/test_ubb_client_subscriptions.py -v
```
Expected: FAIL — `UBBClient` doesn't accept `subscriptions` param.

**Step 3: Update UBBClient**

In `ubb-sdk/ubb/client.py`, update `__init__` to accept `subscriptions: bool = False` and create the client:

Add to the `__init__` method signature:
```python
def __init__(self, api_key: str, base_url: str = "http://localhost:8001",
             timeout: float = 10.0, widget_secret: str | None = None,
             tenant_id: str | None = None,
             metering: bool = True, billing: bool = False,
             subscriptions: bool = False) -> None:
```

Add after the billing client creation:
```python
        from ubb.subscriptions import SubscriptionsClient

        self.subscriptions: SubscriptionsClient | None = (
            SubscriptionsClient(api_key, base_url, timeout) if subscriptions else None
        )
```

Update `close()`:
```python
    def close(self) -> None:
        self._http.close()
        if self.metering is not None:
            self.metering.close()
        if self.billing is not None:
            self.billing.close()
        if self.subscriptions is not None:
            self.subscriptions.close()
```

**Step 4: Run tests**

```bash
cd ubb-sdk && python -m pytest tests/test_ubb_client_subscriptions.py -v
```
Expected: All PASS.

**Step 5: Run full SDK tests**

```bash
cd ubb-sdk && python -m pytest --tb=short -q
```

**Step 6: Commit**

```bash
git add ubb-sdk/ubb/client.py ubb-sdk/tests/test_ubb_client_subscriptions.py
git commit -m "feat: wire SubscriptionsClient into UBBClient"
```

---

## Phase 8: End-to-End Tests + Cleanup

> Verify product isolation, cross-product boundary integrity, and full workflow.

### Task 14: Add end-to-end product isolation tests for subscriptions

**Files:**
- Create: `ubb-platform/apps/subscriptions/tests/test_product_isolation.py`

**Step 1: Write the integration tests**

```python
# apps/subscriptions/tests/test_product_isolation.py
import json
from django.test import TestCase, Client
from apps.platform.tenants.models import Tenant, TenantApiKey
from apps.platform.customers.models import Customer


class TestSubscriptionsProductIsolation(TestCase):
    def setUp(self):
        self.http_client = Client()

    def test_metering_only_tenant_gets_403_on_subscriptions(self):
        tenant = Tenant.objects.create(
            name="metering-only", products=["metering"],
        )
        _, raw_key = TenantApiKey.create_key(tenant=tenant, label="test")

        response = self.http_client.get(
            "/api/v1/subscriptions/economics",
            HTTP_AUTHORIZATION=f"Bearer {raw_key}",
        )
        self.assertEqual(response.status_code, 403)

    def test_billing_tenant_gets_403_on_subscriptions(self):
        tenant = Tenant.objects.create(
            name="billing-tenant", products=["metering", "billing"],
        )
        _, raw_key = TenantApiKey.create_key(tenant=tenant, label="test")

        response = self.http_client.get(
            "/api/v1/subscriptions/economics",
            HTTP_AUTHORIZATION=f"Bearer {raw_key}",
        )
        self.assertEqual(response.status_code, 403)

    def test_subscriptions_tenant_can_access_subscriptions(self):
        tenant = Tenant.objects.create(
            name="sub-tenant", products=["metering", "subscriptions"],
        )
        _, raw_key = TenantApiKey.create_key(tenant=tenant, label="test")

        response = self.http_client.get(
            "/api/v1/subscriptions/economics",
            HTTP_AUTHORIZATION=f"Bearer {raw_key}",
        )
        self.assertNotEqual(response.status_code, 403)

    def test_subscriptions_tenant_gets_403_on_billing(self):
        tenant = Tenant.objects.create(
            name="sub-tenant", products=["metering", "subscriptions"],
        )
        _, raw_key = TenantApiKey.create_key(tenant=tenant, label="test")
        customer = Customer.objects.create(tenant=tenant, external_id="cust-1")

        response = self.http_client.get(
            f"/api/v1/billing/customers/{customer.id}/balance",
            HTTP_AUTHORIZATION=f"Bearer {raw_key}",
        )
        self.assertEqual(response.status_code, 403)

    def test_subscriptions_tenant_can_access_metering(self):
        tenant = Tenant.objects.create(
            name="sub-tenant", products=["metering", "subscriptions"],
        )
        _, raw_key = TenantApiKey.create_key(tenant=tenant, label="test")
        customer = Customer.objects.create(tenant=tenant, external_id="cust-1")
        customer.wallet.balance_micros = 100_000_000
        customer.wallet.save()

        response = self.http_client.post(
            "/api/v1/metering/usage",
            data=json.dumps({
                "customer_id": str(customer.id),
                "request_id": "req-isolation-1",
                "idempotency_key": "idem-isolation-1",
                "cost_micros": 500_000,
            }),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {raw_key}",
        )
        self.assertEqual(response.status_code, 200)
```

**Step 2: Run tests**

```bash
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/subscriptions/tests/test_product_isolation.py -v
```
Expected: All 5 tests PASS.

**Step 3: Commit**

```bash
git add apps/subscriptions/tests/test_product_isolation.py
git commit -m "test: add end-to-end product isolation tests for subscriptions"
```

---

### Task 15: Verify no cross-product imports

**Step 1: Search for cross-product imports**

```bash
cd ubb-platform

# Subscriptions importing from billing (should find ZERO)
grep -rn "from apps.billing" apps/subscriptions/ || echo "CLEAN: No subscriptions→billing imports"

# Subscriptions importing from metering (should find ZERO)
grep -rn "from apps.metering" apps/subscriptions/ || echo "CLEAN: No subscriptions→metering imports"

# Billing importing from subscriptions (should find ZERO)
grep -rn "from apps.subscriptions" apps/billing/ || echo "CLEAN: No billing→subscriptions imports"

# Metering importing from subscriptions (should find ZERO)
grep -rn "from apps.subscriptions" apps/metering/ || echo "CLEAN: No metering→subscriptions imports"

# All products importing from platform (OK)
grep -rn "from apps.platform" apps/subscriptions/ apps/metering/ apps/billing/
```

Expected: Zero cross-product imports. All imports go through platform.

**Step 2: Run full test suite**

```bash
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest --tb=short -q
```
Expected: All tests pass.

**Step 3: Verify Django checks**

```bash
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python manage.py check
DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python manage.py makemigrations --check --dry-run
```
Expected: "System check identified no issues." and "No changes detected."

**Step 4: Run SDK tests**

```bash
cd ubb-sdk && python -m pytest --tb=short -q
```

**Step 5: Commit**

```bash
git add -A
git commit -m "chore: verify cross-product boundaries and finalize subscriptions product"
```

---

## Summary

| Phase | Tasks | Description |
|-------|-------|-------------|
| **Phase 1** | Tasks 1–3 | App skeleton, `StripeSubscription`, `SubscriptionInvoice`, `CustomerCostAccumulator`, `CustomerEconomics` models |
| **Phase 2** | Task 4 | Event bus `usage.recorded` handler for cost accumulation |
| **Phase 3** | Tasks 5–6 | Stripe webhook handlers + full sync service |
| **Phase 4** | Task 7 | `EconomicsService` for per-customer margin calculation |
| **Phase 5** | Tasks 8–10 | API endpoints with `ProductAccess("subscriptions")`, webhook endpoint |
| **Phase 6** | Task 11 | Celery tasks for periodic economics calculation |
| **Phase 7** | Tasks 12–13 | `SubscriptionsClient` SDK + `UBBClient` integration |
| **Phase 8** | Tasks 14–15 | End-to-end product isolation tests, cross-product import audit |

**Total tasks:** 15
**Each phase is independently deployable and verifiable.**
