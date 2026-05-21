# Billing Config Extraction Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Extract billing-specific fields from platform shared kernel models into billing-owned config models, establish query interfaces for all cross-module reads.

**Architecture:** Two new billing-owned models (`BillingTenantConfig`, `CustomerBillingProfile`) absorb billing fields from Tenant/Customer. Three new `queries.py` files (`platform/`, `billing/`, `subscriptions/`) provide named query interfaces for all cross-module reads. `RunService.create_run()` signature changes to accept limits as parameters. All 14 production consumer files switch to query interfaces.

**Tech Stack:** Django 6.0, PostgreSQL, django-ninja, Celery, Stripe

---

### Task 1: Create BillingTenantConfig Model

**Files:**
- Modify: `ubb-platform/apps/billing/tenant_billing/models.py` (append after line 120)

**Step 1: Add BillingTenantConfig model**

Add to the end of `apps/billing/tenant_billing/models.py`:

```python
class BillingTenantConfig(BaseModel):
    tenant = models.OneToOneField(
        "tenants.Tenant", on_delete=models.CASCADE, related_name="billing_config"
    )
    stripe_customer_id = models.CharField(max_length=255, blank=True, default="")
    platform_fee_percentage = models.DecimalField(
        max_digits=5, decimal_places=2, default=1.00
    )
    min_balance_micros = models.BigIntegerField(default=0)
    run_cost_limit_micros = models.BigIntegerField(null=True, blank=True)
    hard_stop_balance_micros = models.BigIntegerField(null=True, blank=True)

    class Meta:
        db_table = "ubb_billing_tenant_config"

    def __str__(self):
        return f"BillingTenantConfig({self.tenant.name})"
```

**Step 2: Generate migration**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python manage.py makemigrations tenant_billing --name billing_tenant_config`
Expected: New migration file `0006_billing_tenant_config.py`

**Step 3: Apply migration**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python manage.py migrate tenant_billing`
Expected: `Applying tenant_billing.0006_billing_tenant_config... OK`

**Step 4: Run existing tests to verify no breakage**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/billing/tenant_billing/tests/ --tb=short -q`
Expected: All existing tests PASS

**Step 5: Commit**

```bash
git add ubb-platform/apps/billing/tenant_billing/models.py ubb-platform/apps/billing/tenant_billing/migrations/
git commit -m "feat: add BillingTenantConfig model for billing field extraction"
```

---

### Task 2: Create CustomerBillingProfile Model

**Files:**
- Modify: `ubb-platform/apps/billing/wallets/models.py` (append after line 98)

**Step 1: Add CustomerBillingProfile model**

Add to the end of `apps/billing/wallets/models.py`:

```python
class CustomerBillingProfile(BaseModel):
    customer = models.OneToOneField(
        "customers.Customer", on_delete=models.CASCADE,
        related_name="billing_profile"
    )
    min_balance_micros = models.BigIntegerField(null=True, blank=True)

    class Meta:
        db_table = "ubb_customer_billing_profile"

    def __str__(self):
        return f"CustomerBillingProfile({self.customer.external_id})"
```

**Step 2: Generate migration**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python manage.py makemigrations wallets --name customer_billing_profile`
Expected: New migration file `0003_customer_billing_profile.py`

**Step 3: Apply migration**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python manage.py migrate wallets`
Expected: `Applying wallets.0003_customer_billing_profile... OK`

**Step 4: Run existing tests to verify no breakage**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/billing/wallets/ --tb=short -q`
Expected: All existing tests PASS

**Step 5: Commit**

```bash
git add ubb-platform/apps/billing/wallets/models.py ubb-platform/apps/billing/wallets/migrations/
git commit -m "feat: add CustomerBillingProfile model for billing field extraction"
```

---

### Task 3: Create Data Migration

**Files:**
- Create: `ubb-platform/apps/billing/tenant_billing/migrations/0007_populate_billing_tenant_config.py`

This migration copies existing values from `Tenant` and `Customer` into the new billing config models.

**Step 1: Write data migration**

Create `ubb-platform/apps/billing/tenant_billing/migrations/0007_populate_billing_tenant_config.py`:

```python
from django.db import migrations


def populate_billing_tenant_config(apps, schema_editor):
    Tenant = apps.get_model("tenants", "Tenant")
    BillingTenantConfig = apps.get_model("tenant_billing", "BillingTenantConfig")

    for tenant in Tenant.objects.all():
        BillingTenantConfig.objects.get_or_create(
            tenant=tenant,
            defaults={
                "stripe_customer_id": tenant.stripe_customer_id,
                "platform_fee_percentage": tenant.platform_fee_percentage,
                "min_balance_micros": tenant.min_balance_micros,
                "run_cost_limit_micros": tenant.run_cost_limit_micros,
                "hard_stop_balance_micros": tenant.hard_stop_balance_micros,
            },
        )


def populate_customer_billing_profile(apps, schema_editor):
    Customer = apps.get_model("customers", "Customer")
    CustomerBillingProfile = apps.get_model("wallets", "CustomerBillingProfile")

    for customer in Customer.objects.filter(min_balance_micros__isnull=False):
        CustomerBillingProfile.objects.get_or_create(
            customer=customer,
            defaults={
                "min_balance_micros": customer.min_balance_micros,
            },
        )


class Migration(migrations.Migration):

    dependencies = [
        ("tenant_billing", "0006_billing_tenant_config"),
        ("wallets", "0003_customer_billing_profile"),
        ("tenants", "0001_initial"),
        ("customers", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(
            populate_billing_tenant_config,
            migrations.RunPython.noop,
        ),
        migrations.RunPython(
            populate_customer_billing_profile,
            migrations.RunPython.noop,
        ),
    ]
```

Note: The `dependencies` list includes `("tenants", "0001_initial")` and `("customers", "0001_initial")` — check actual latest migration names in those apps and adjust if needed.

**Step 2: Apply data migration**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python manage.py migrate tenant_billing`
Expected: `Applying tenant_billing.0007_populate_billing_tenant_config... OK`

**Step 3: Verify data migrated (quick sanity check)**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python manage.py shell -c "from apps.billing.tenant_billing.models import BillingTenantConfig; print(BillingTenantConfig.objects.count())"`
Expected: Count matches number of tenants in local DB

**Step 4: Commit**

```bash
git add ubb-platform/apps/billing/tenant_billing/migrations/0007_populate_billing_tenant_config.py
git commit -m "feat: data migration to populate BillingTenantConfig and CustomerBillingProfile"
```

---

### Task 4: Create Billing Query Interface

**Files:**
- Create: `ubb-platform/apps/billing/queries.py`
- Test: `ubb-platform/apps/billing/tests/test_queries.py`

**Step 1: Write the failing tests**

Create `ubb-platform/apps/billing/tests/test_queries.py`:

```python
from decimal import Decimal

from django.test import TestCase

from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.billing.queries import (
    get_billing_config,
    get_customer_min_balance,
    get_customer_balance,
)


class GetBillingConfigTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Test")

    def test_creates_config_on_first_access(self):
        config = get_billing_config(self.tenant.id)
        self.assertEqual(config.tenant_id, self.tenant.id)
        self.assertEqual(config.stripe_customer_id, "")
        self.assertEqual(config.platform_fee_percentage, Decimal("1.00"))
        self.assertEqual(config.min_balance_micros, 0)
        self.assertIsNone(config.run_cost_limit_micros)
        self.assertIsNone(config.hard_stop_balance_micros)

    def test_returns_existing_config(self):
        from apps.billing.tenant_billing.models import BillingTenantConfig
        BillingTenantConfig.objects.create(
            tenant=self.tenant,
            stripe_customer_id="cus_abc",
            platform_fee_percentage=Decimal("2.50"),
            min_balance_micros=5_000_000,
        )
        config = get_billing_config(self.tenant.id)
        self.assertEqual(config.stripe_customer_id, "cus_abc")
        self.assertEqual(config.platform_fee_percentage, Decimal("2.50"))
        self.assertEqual(config.min_balance_micros, 5_000_000)

    def test_idempotent_lazy_creation(self):
        get_billing_config(self.tenant.id)
        get_billing_config(self.tenant.id)
        from apps.billing.tenant_billing.models import BillingTenantConfig
        self.assertEqual(
            BillingTenantConfig.objects.filter(tenant=self.tenant).count(), 1
        )


class GetCustomerMinBalanceTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Test")
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="cust-1"
        )

    def test_returns_zero_when_no_profile_and_no_config(self):
        result = get_customer_min_balance(self.customer.id, self.tenant.id)
        self.assertEqual(result, 0)

    def test_returns_tenant_default_when_no_customer_override(self):
        from apps.billing.tenant_billing.models import BillingTenantConfig
        BillingTenantConfig.objects.create(
            tenant=self.tenant, min_balance_micros=5_000_000,
        )
        result = get_customer_min_balance(self.customer.id, self.tenant.id)
        self.assertEqual(result, 5_000_000)

    def test_customer_override_takes_precedence(self):
        from apps.billing.tenant_billing.models import BillingTenantConfig
        from apps.billing.wallets.models import CustomerBillingProfile
        BillingTenantConfig.objects.create(
            tenant=self.tenant, min_balance_micros=5_000_000,
        )
        CustomerBillingProfile.objects.create(
            customer=self.customer, min_balance_micros=10_000_000,
        )
        result = get_customer_min_balance(self.customer.id, self.tenant.id)
        self.assertEqual(result, 10_000_000)

    def test_customer_override_zero_is_valid(self):
        from apps.billing.tenant_billing.models import BillingTenantConfig
        from apps.billing.wallets.models import CustomerBillingProfile
        BillingTenantConfig.objects.create(
            tenant=self.tenant, min_balance_micros=5_000_000,
        )
        CustomerBillingProfile.objects.create(
            customer=self.customer, min_balance_micros=0,
        )
        result = get_customer_min_balance(self.customer.id, self.tenant.id)
        self.assertEqual(result, 0)


class GetCustomerBalanceTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Test")
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="cust-1"
        )

    def test_returns_zero_when_no_wallet(self):
        result = get_customer_balance(self.customer.id)
        self.assertEqual(result, 0)

    def test_returns_wallet_balance(self):
        from apps.billing.wallets.models import Wallet
        Wallet.objects.create(customer=self.customer, balance_micros=7_000_000)
        result = get_customer_balance(self.customer.id)
        self.assertEqual(result, 7_000_000)
```

**Step 2: Run tests to verify they fail**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/billing/tests/test_queries.py --tb=short -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'apps.billing.queries'`

**Step 3: Write the billing query interface**

Create `ubb-platform/apps/billing/queries.py`:

```python
"""Billing Query Interface — Cross-Product Read Contract.

This module provides the ONLY approved way for other products
(and the API layer) to read billing data. Functions return
model instances or scalars, never require callers to import
billing models directly.

If billing becomes a separate service, these functions become
HTTP calls. All callers remain untouched.

Consumers:
- apps/billing/gating/services/risk_service.py → get_billing_config(), get_customer_min_balance()
- apps/billing/handlers.py → get_customer_min_balance()
- apps/billing/stripe/services/stripe_service.py → get_billing_config()
- apps/billing/tenant_billing/services.py → get_billing_config()
"""


def get_billing_config(tenant_id):
    """Returns billing config for a tenant. Lazily creates with defaults if missing."""
    from apps.billing.tenant_billing.models import BillingTenantConfig

    config, _ = BillingTenantConfig.objects.get_or_create(tenant_id=tenant_id)
    return config


def get_customer_min_balance(customer_id, tenant_id):
    """Returns the effective min balance: customer override -> tenant default -> 0."""
    from apps.billing.wallets.models import CustomerBillingProfile

    try:
        profile = CustomerBillingProfile.objects.get(customer_id=customer_id)
        if profile.min_balance_micros is not None:
            return profile.min_balance_micros
    except CustomerBillingProfile.DoesNotExist:
        pass

    config = get_billing_config(tenant_id)
    return config.min_balance_micros


def get_customer_balance(customer_id):
    """Returns wallet balance, or 0 if no wallet exists."""
    from apps.billing.wallets.models import Wallet

    try:
        wallet = Wallet.objects.get(customer_id=customer_id)
        return wallet.balance_micros
    except Wallet.DoesNotExist:
        return 0
```

**Step 4: Run tests to verify they pass**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/billing/tests/test_queries.py --tb=short -q`
Expected: All PASS

**Step 5: Commit**

```bash
git add ubb-platform/apps/billing/queries.py ubb-platform/apps/billing/tests/test_queries.py
git commit -m "feat: add billing query interface (get_billing_config, get_customer_min_balance, get_customer_balance)"
```

---

### Task 5: Create Platform Query Interface

**Files:**
- Create: `ubb-platform/apps/platform/queries.py`
- Test: `ubb-platform/apps/platform/tests/test_queries.py`

**Step 1: Write the failing tests**

Create `ubb-platform/apps/platform/tests/__init__.py` (if it doesn't exist) and `ubb-platform/apps/platform/tests/test_queries.py`:

```python
from django.test import TestCase

from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.platform.queries import (
    get_tenant_stripe_account,
    get_customer_stripe_id,
    get_customers_by_stripe_id,
)


class GetTenantStripeAccountTest(TestCase):
    def test_returns_account_id(self):
        tenant = Tenant.objects.create(
            name="Test", stripe_connected_account_id="acct_123"
        )
        result = get_tenant_stripe_account(tenant.id)
        self.assertEqual(result, "acct_123")

    def test_returns_none_when_empty(self):
        tenant = Tenant.objects.create(name="Test")
        result = get_tenant_stripe_account(tenant.id)
        self.assertIsNone(result)


class GetCustomerStripeIdTest(TestCase):
    def test_returns_stripe_id(self):
        tenant = Tenant.objects.create(name="Test")
        customer = Customer.objects.create(
            tenant=tenant, external_id="c1", stripe_customer_id="cus_abc"
        )
        result = get_customer_stripe_id(customer.id)
        self.assertEqual(result, "cus_abc")

    def test_returns_none_when_empty(self):
        tenant = Tenant.objects.create(name="Test")
        customer = Customer.objects.create(tenant=tenant, external_id="c1")
        result = get_customer_stripe_id(customer.id)
        self.assertIsNone(result)


class GetCustomersByStripeIdTest(TestCase):
    def test_returns_mapping(self):
        tenant = Tenant.objects.create(name="Test")
        c1 = Customer.objects.create(
            tenant=tenant, external_id="c1", stripe_customer_id="cus_aaa"
        )
        c2 = Customer.objects.create(
            tenant=tenant, external_id="c2", stripe_customer_id="cus_bbb"
        )
        Customer.objects.create(tenant=tenant, external_id="c3")  # no stripe id

        result = get_customers_by_stripe_id(tenant.id)
        self.assertEqual(result, {
            "cus_aaa": str(c1.id),
            "cus_bbb": str(c2.id),
        })

    def test_returns_empty_dict_when_no_stripe_customers(self):
        tenant = Tenant.objects.create(name="Test")
        Customer.objects.create(tenant=tenant, external_id="c1")
        result = get_customers_by_stripe_id(tenant.id)
        self.assertEqual(result, {})
```

**Step 2: Run tests to verify they fail**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/platform/tests/test_queries.py --tb=short -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'apps.platform.queries'`

**Step 3: Write the platform query interface**

Create `ubb-platform/apps/platform/queries.py`:

```python
"""Platform Query Interface — Cross-Product Read Contract.

This module provides the ONLY approved way for product modules
(billing, subscriptions) to read platform identity data like
Stripe account IDs. Functions return scalars or dicts, never
ORM instances.

If platform becomes a separate service, these functions become
HTTP calls. All callers remain untouched.

Consumers:
- apps/billing/connectors/stripe/stripe_api.py → get_customer_stripe_id(), get_tenant_stripe_account()
- apps/billing/connectors/stripe/receipts.py → get_customer_stripe_id(), get_tenant_stripe_account()
- apps/billing/connectors/stripe/tasks.py → get_tenant_stripe_account()
- apps/billing/connectors/stripe/handlers.py → get_tenant_stripe_account()
- apps/subscriptions/stripe/sync.py → get_tenant_stripe_account(), get_customers_by_stripe_id()
- api/v1/billing_endpoints.py → get_tenant_stripe_account(), get_customer_stripe_id()
- api/v1/me_endpoints.py → get_tenant_stripe_account(), get_customer_stripe_id()
- api/v1/platform_endpoints.py → get_customer_stripe_id()
"""
from typing import Optional


def get_tenant_stripe_account(tenant_id) -> Optional[str]:
    """Returns the tenant's Stripe connected account ID, or None if not set."""
    from apps.platform.tenants.models import Tenant

    value = Tenant.objects.filter(id=tenant_id).values_list(
        "stripe_connected_account_id", flat=True
    ).first()
    return value if value else None


def get_customer_stripe_id(customer_id) -> Optional[str]:
    """Returns the customer's Stripe customer ID, or None if not set."""
    from apps.platform.customers.models import Customer

    value = Customer.objects.filter(id=customer_id).values_list(
        "stripe_customer_id", flat=True
    ).first()
    return value if value else None


def get_customers_by_stripe_id(tenant_id) -> dict[str, str]:
    """Returns {stripe_customer_id: customer_id} for all customers with Stripe IDs.

    Used by subscription sync to match Stripe subscriptions to platform customers.
    """
    from apps.platform.customers.models import Customer

    return {
        stripe_id: str(cust_id)
        for cust_id, stripe_id in Customer.objects.filter(
            tenant_id=tenant_id,
            stripe_customer_id__gt="",
        ).values_list("id", "stripe_customer_id")
    }
```

**Step 4: Ensure `apps/platform/tests/__init__.py` exists**

Run: `touch ubb-platform/apps/platform/tests/__init__.py`

**Step 5: Run tests to verify they pass**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/platform/tests/test_queries.py --tb=short -q`
Expected: All PASS

**Step 6: Commit**

```bash
git add ubb-platform/apps/platform/queries.py ubb-platform/apps/platform/tests/
git commit -m "feat: add platform query interface (get_tenant_stripe_account, get_customer_stripe_id, get_customers_by_stripe_id)"
```

---

### Task 6: Create Subscriptions Query Interface

**Files:**
- Create: `ubb-platform/apps/subscriptions/queries.py`
- Test: `ubb-platform/apps/subscriptions/tests/test_queries.py`

**Step 1: Write the failing tests**

Create `ubb-platform/apps/subscriptions/tests/test_queries.py`:

```python
from datetime import date
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.subscriptions.queries import (
    get_customer_economics,
    get_economics_summary,
    get_customer_subscription,
)
from apps.subscriptions.models import StripeSubscription


class GetCustomerEconomicsTest(TestCase):
    def test_returns_none_when_no_data(self):
        tenant = Tenant.objects.create(name="Test")
        customer = Customer.objects.create(tenant=tenant, external_id="c1")
        result = get_customer_economics(
            tenant.id, customer.id,
            date(2026, 1, 1), date(2026, 2, 1),
        )
        self.assertIsNone(result)


class GetCustomerSubscriptionTest(TestCase):
    def test_returns_none_when_no_subscription(self):
        tenant = Tenant.objects.create(name="Test")
        customer = Customer.objects.create(tenant=tenant, external_id="c1")
        result = get_customer_subscription(tenant.id, customer.id)
        self.assertIsNone(result)

    def test_returns_latest_subscription(self):
        tenant = Tenant.objects.create(name="Test")
        customer = Customer.objects.create(tenant=tenant, external_id="c1")
        now = timezone.now()
        sub = StripeSubscription.objects.create(
            tenant=tenant,
            customer=customer,
            stripe_subscription_id="sub_123",
            stripe_product_name="Pro",
            status="active",
            amount_micros=100_000_000,
            interval="month",
            current_period_start=now,
            current_period_end=now,
            last_synced_at=now,
        )
        result = get_customer_subscription(tenant.id, customer.id)
        self.assertEqual(result.id, sub.id)
```

**Step 2: Run tests to verify they fail**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/subscriptions/tests/test_queries.py --tb=short -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'apps.subscriptions.queries'`

**Step 3: Write the subscriptions query interface**

Create `ubb-platform/apps/subscriptions/queries.py`:

```python
"""Subscriptions Query Interface — Cross-Product Read Contract.

This module provides the ONLY approved way for other products
(and the API layer) to read subscriptions data.

If subscriptions becomes a separate service, these functions
become HTTP calls. All callers remain untouched.

Consumers:
- api/v1/subscriptions_endpoints.py (future)
"""
from datetime import date


def get_customer_economics(tenant_id, customer_id, period_start: date, period_end: date):
    """Returns CustomerEconomics or None."""
    from apps.subscriptions.economics.models import CustomerEconomics

    return CustomerEconomics.objects.filter(
        tenant_id=tenant_id,
        customer_id=customer_id,
        period_start__gte=period_start,
        period_end__lte=period_end,
    ).order_by("-period_start").first()


def get_economics_summary(tenant_id, period_start: date, period_end: date):
    """Returns aggregated economics for all customers."""
    from apps.subscriptions.economics.models import CustomerEconomics
    from django.db.models import Sum

    qs = CustomerEconomics.objects.filter(
        tenant_id=tenant_id,
        period_start__gte=period_start,
        period_end__lte=period_end,
    )
    totals = qs.aggregate(
        total_revenue=Sum("subscription_revenue_micros"),
        total_cost=Sum("usage_cost_micros"),
        total_margin=Sum("gross_margin_micros"),
    )
    return {
        "total_revenue_micros": totals["total_revenue"] or 0,
        "total_cost_micros": totals["total_cost"] or 0,
        "total_margin_micros": totals["total_margin"] or 0,
        "customer_count": qs.count(),
    }


def get_customer_subscription(tenant_id, customer_id):
    """Returns latest StripeSubscription or None."""
    from apps.subscriptions.models import StripeSubscription

    return StripeSubscription.objects.filter(
        tenant_id=tenant_id,
        customer_id=customer_id,
    ).order_by("-created_at").first()
```

**Step 4: Run tests to verify they pass**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/subscriptions/tests/test_queries.py --tb=short -q`
Expected: All PASS

**Step 5: Commit**

```bash
git add ubb-platform/apps/subscriptions/queries.py ubb-platform/apps/subscriptions/tests/test_queries.py
git commit -m "feat: add subscriptions query interface (get_customer_economics, get_economics_summary, get_customer_subscription)"
```

---

### Task 7: Update RunService.create_run() Signature

**Files:**
- Modify: `ubb-platform/apps/platform/runs/services.py:36-49`
- Test: `ubb-platform/apps/platform/runs/tests/test_services.py`

**Step 1: Update the tests first**

In `ubb-platform/apps/platform/runs/tests/test_services.py`, update `RunServiceCreateTest`:

Replace the entire `RunServiceCreateTest` class with:

```python
class RunServiceCreateTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Test Tenant",
            products=["metering", "billing"],
        )
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="cust-1"
        )

    def test_create_run_with_explicit_limits(self):
        run = RunService.create_run(
            self.tenant, self.customer, balance_snapshot_micros=3_000_000,
            cost_limit_micros=10_000_000,
            hard_stop_balance_micros=-5_000_000,
        )
        self.assertEqual(run.status, "active")
        self.assertEqual(run.balance_snapshot_micros, 3_000_000)
        self.assertEqual(run.cost_limit_micros, 10_000_000)
        self.assertEqual(run.hard_stop_balance_micros, -5_000_000)
        self.assertEqual(run.total_cost_micros, 0)
        self.assertEqual(run.event_count, 0)
        self.assertEqual(run.tenant_id, self.tenant.id)
        self.assertEqual(run.customer_id, self.customer.id)

    def test_create_run_null_limits(self):
        run = RunService.create_run(
            self.tenant, self.customer, balance_snapshot_micros=0,
        )
        self.assertIsNone(run.cost_limit_micros)
        self.assertIsNone(run.hard_stop_balance_micros)

    def test_create_run_with_metadata_and_external_id(self):
        run = RunService.create_run(
            self.tenant, self.customer, balance_snapshot_micros=0,
            metadata={"foo": "bar"}, external_run_id="ext-123",
        )
        self.assertEqual(run.metadata, {"foo": "bar"})
        self.assertEqual(run.external_run_id, "ext-123")
```

Also update the `RunServiceAccumulateTest.setUp` to pass limits explicitly:

```python
class RunServiceAccumulateTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Test Tenant",
            products=["metering", "billing"],
        )
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="cust-1"
        )
        self.cost_limit = 10_000_000
        self.hard_stop = -5_000_000
```

And update all `RunService.create_run()` calls in `RunServiceAccumulateTest` to pass limits:

- `test_accumulate_cost_increments_total_and_count`: `RunService.create_run(self.tenant, self.customer, balance_snapshot_micros=20_000_000, cost_limit_micros=self.cost_limit, hard_stop_balance_micros=self.hard_stop)`
- `test_accumulate_cost_ceiling_exceeded_raises`: same
- `test_accumulate_cost_floor_exceeded_raises`: `RunService.create_run(self.tenant, self.customer, balance_snapshot_micros=3_000_000, cost_limit_micros=self.cost_limit, hard_stop_balance_micros=self.hard_stop)`
- `test_accumulate_cost_null_limits_never_stops`: `RunService.create_run(self.tenant, self.customer, balance_snapshot_micros=1_000_000)` (no limits — tests None behavior)
- `test_accumulate_cost_exact_ceiling_allowed`: `RunService.create_run(self.tenant, self.customer, balance_snapshot_micros=20_000_000, cost_limit_micros=self.cost_limit, hard_stop_balance_micros=self.hard_stop)`
- `test_accumulate_cost_one_over_ceiling_raises`: same
- `test_accumulate_cost_on_killed_run_raises_not_active`: `RunService.create_run(self.tenant, self.customer, balance_snapshot_micros=20_000_000, cost_limit_micros=self.cost_limit, hard_stop_balance_micros=self.hard_stop)`
- `test_accumulate_cost_on_completed_run_raises_not_active`: same

No changes needed for `RunServiceKillTest` or `RunServiceCompleteTest` — those don't set limits on tenant.

**Step 2: Run tests to verify they fail**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/platform/runs/tests/test_services.py --tb=short -q`
Expected: FAIL — `create_run` still reads from tenant, but tests no longer set limits on tenant

**Step 3: Update RunService.create_run()**

In `ubb-platform/apps/platform/runs/services.py`, replace lines 35-49:

```python
    @staticmethod
    def create_run(tenant, customer, balance_snapshot_micros,
                   cost_limit_micros=None, hard_stop_balance_micros=None,
                   metadata=None, external_run_id=""):
        """Create a Run, snapshotting hard stop config and wallet balance.

        Limits are passed explicitly by the caller (billing pre-check).
        Must be called inside @transaction.atomic.
        """
        return Run.objects.create(
            tenant=tenant,
            customer=customer,
            balance_snapshot_micros=balance_snapshot_micros,
            cost_limit_micros=cost_limit_micros,
            hard_stop_balance_micros=hard_stop_balance_micros,
            metadata=metadata or {},
            external_run_id=external_run_id,
        )
```

**Step 4: Run tests to verify they pass**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/platform/runs/tests/test_services.py --tb=short -q`
Expected: All PASS

**Step 5: Commit**

```bash
git add ubb-platform/apps/platform/runs/services.py ubb-platform/apps/platform/runs/tests/test_services.py
git commit -m "refactor: RunService.create_run() accepts limits as parameters instead of reading from tenant"
```

---

### Task 8: Update RiskService to Use Billing Queries

**Files:**
- Modify: `ubb-platform/apps/billing/gating/services/risk_service.py`
- Modify: `ubb-platform/apps/billing/gating/tests/test_risk_service.py`

**Step 1: Update the tests**

In `ubb-platform/apps/billing/gating/tests/test_risk_service.py`:

Add import for `BillingTenantConfig` and `CustomerBillingProfile`:

```python
from apps.billing.tenant_billing.models import BillingTenantConfig
from apps.billing.wallets.models import CustomerBillingProfile
```

Update `RiskServiceTest`:
- `test_affordability_denied_when_balance_below_negative_threshold` — currently relies on tenant default `min_balance_micros=0`. This still works because `get_billing_config()` lazily creates with `min_balance_micros=0` default. No change needed.
- `test_affordability_allowed_within_min_balance` — currently sets `self.tenant.min_balance_micros = 5_000_000`. Change to create `BillingTenantConfig`:

Replace:
```python
    def test_affordability_allowed_within_min_balance(self):
        """Allow when balance >= -min_balance (custom threshold)."""
        # Set a 5M min_balance on tenant so -3M >= -5M → allowed
        self.tenant.min_balance_micros = 5_000_000
        self.tenant.save(update_fields=["min_balance_micros", "updated_at"])
        Wallet.objects.create(customer=self.customer, balance_micros=-3_000_000)
        result = RiskService.check(self.customer)
        self.assertTrue(result["allowed"])
        self.assertEqual(result["balance_micros"], -3_000_000)
```

With:
```python
    def test_affordability_allowed_within_min_balance(self):
        """Allow when balance >= -min_balance (custom threshold)."""
        BillingTenantConfig.objects.create(
            tenant=self.tenant, min_balance_micros=5_000_000,
        )
        Wallet.objects.create(customer=self.customer, balance_micros=-3_000_000)
        result = RiskService.check(self.customer)
        self.assertTrue(result["allowed"])
        self.assertEqual(result["balance_micros"], -3_000_000)
```

- `test_affordability_denied_no_wallet_zero_threshold` — currently sets `self.customer.min_balance_micros = 0`. Change to create `CustomerBillingProfile`:

Replace:
```python
    def test_affordability_denied_no_wallet_zero_threshold(self):
        """No wallet (balance=0), zero threshold: balance(0) < -0 is false → allowed."""
        self.customer.min_balance_micros = 0
        self.customer.save()
        result = RiskService.check(self.customer)
        self.assertTrue(result["allowed"])
        self.assertEqual(result["balance_micros"], 0)
```

With:
```python
    def test_affordability_denied_no_wallet_zero_threshold(self):
        """No wallet (balance=0), zero threshold: balance(0) < -0 is false → allowed."""
        CustomerBillingProfile.objects.create(
            customer=self.customer, min_balance_micros=0,
        )
        result = RiskService.check(self.customer)
        self.assertTrue(result["allowed"])
        self.assertEqual(result["balance_micros"], 0)
```

Update `RiskServiceRunTest.setUp` to create `BillingTenantConfig` instead of setting fields on tenant:

Replace:
```python
class RiskServiceRunTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Test",
            run_cost_limit_micros=10_000_000,
            hard_stop_balance_micros=-5_000_000,
        )
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="u1"
        )
        RiskConfig.objects.create(tenant=self.tenant)
```

With:
```python
class RiskServiceRunTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Test")
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="u1"
        )
        RiskConfig.objects.create(tenant=self.tenant)
        BillingTenantConfig.objects.create(
            tenant=self.tenant,
            run_cost_limit_micros=10_000_000,
            hard_stop_balance_micros=-5_000_000,
        )
```

**Step 2: Run tests to verify they fail**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/billing/gating/tests/test_risk_service.py --tb=short -q`
Expected: FAIL — `RiskService.check()` still reads from `customer.get_min_balance()` and passes no limits to `RunService.create_run()`

**Step 3: Update RiskService.check()**

Replace entire `ubb-platform/apps/billing/gating/services/risk_service.py`:

```python
from django.core.cache import cache

from apps.billing.gating.models import RiskConfig


class RiskService:
    @staticmethod
    def check(customer, create_run=False, run_metadata=None, external_run_id=""):
        if customer.status == "suspended":
            return {"allowed": False, "reason": "insufficient_funds", "balance_micros": None, "run_id": None}
        if customer.status == "closed":
            return {"allowed": False, "reason": "account_closed", "balance_micros": None, "run_id": None}
        try:
            config = customer.tenant.risk_config
        except RiskConfig.DoesNotExist:
            config = None
        # Fixed-window rate limiting (degrades gracefully if Redis is down)
        if config and config.max_requests_per_minute and config.max_requests_per_minute > 0:
            try:
                cache_key = f"ratelimit:{customer.id}:rpm"
                current_count = cache.get(cache_key, 0)
                if current_count >= config.max_requests_per_minute:
                    return {"allowed": False, "reason": "rate_limit_exceeded", "balance_micros": None, "run_id": None}
                try:
                    cache.incr(cache_key)
                except ValueError:
                    cache.set(cache_key, 1, timeout=60)
            except Exception:
                pass  # Degrade: skip rate limiting if cache is unavailable

        # Affordability check
        from apps.billing.wallets.models import Wallet
        try:
            wallet = Wallet.objects.get(customer=customer)
            balance = wallet.balance_micros
        except Wallet.DoesNotExist:
            balance = 0

        from apps.billing.queries import get_customer_min_balance
        threshold = get_customer_min_balance(customer.id, customer.tenant_id)
        if balance < -threshold:
            return {"allowed": False, "reason": "insufficient_funds", "balance_micros": balance, "run_id": None}

        result = {"allowed": True, "reason": None, "balance_micros": balance, "run_id": None}

        # Optionally create a Run, snapshotting wallet balance and billing config limits
        if create_run:
            from apps.billing.queries import get_billing_config
            from apps.platform.runs.services import RunService

            billing_config = get_billing_config(customer.tenant_id)
            run = RunService.create_run(
                tenant=customer.tenant,
                customer=customer,
                balance_snapshot_micros=balance,
                cost_limit_micros=billing_config.run_cost_limit_micros,
                hard_stop_balance_micros=billing_config.hard_stop_balance_micros,
                metadata=run_metadata or {},
                external_run_id=external_run_id,
            )
            result["run_id"] = str(run.id)
            result["cost_limit_micros"] = run.cost_limit_micros
            result["hard_stop_balance_micros"] = run.hard_stop_balance_micros

        return result
```

**Step 4: Run tests to verify they pass**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/billing/gating/tests/test_risk_service.py --tb=short -q`
Expected: All PASS

**Step 5: Commit**

```bash
git add ubb-platform/apps/billing/gating/services/risk_service.py ubb-platform/apps/billing/gating/tests/test_risk_service.py
git commit -m "refactor: RiskService reads from billing queries instead of tenant/customer model fields"
```

---

### Task 9: Update Billing Handlers to Use Billing Queries

**Files:**
- Modify: `ubb-platform/apps/billing/handlers.py:55`

**Step 1: Update handle_usage_recorded_billing**

In `ubb-platform/apps/billing/handlers.py`, replace line 55:

```python
            threshold = customer.get_min_balance()
```

With:

```python
            from apps.billing.queries import get_customer_min_balance
            threshold = get_customer_min_balance(customer.id, tenant.id)
```

**Step 2: Run full test suite to verify**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest --tb=short -q`
Expected: All PASS

**Step 3: Commit**

```bash
git add ubb-platform/apps/billing/handlers.py
git commit -m "refactor: billing handler uses get_customer_min_balance() instead of customer.get_min_balance()"
```

---

### Task 10: Update StripeService to Use Billing Queries

**Files:**
- Modify: `ubb-platform/apps/billing/stripe/services/stripe_service.py:125,139,148`

**Step 1: Update create_tenant_platform_invoice**

In `ubb-platform/apps/billing/stripe/services/stripe_service.py`, replace the `create_tenant_platform_invoice` method (lines 116-163):

```python
class StripeService:
    @staticmethod
    def create_tenant_platform_invoice(tenant, billing_period):
        """
        Create a Stripe invoice for the platform fee billed directly to the tenant.

        Uses BillingTenantConfig.stripe_customer_id (tenant as UBB's customer).
        NOT on the connected account — this is UBB billing the tenant.
        auto_advance=False until items attached, then finalize explicitly.
        """
        from apps.billing.queries import get_billing_config
        billing_config = get_billing_config(tenant.id)

        if not billing_config.stripe_customer_id:
            raise StripeFatalError(
                f"Tenant {tenant.id} has no stripe_customer_id for platform billing"
            )

        amount_cents = micros_to_cents(billing_period.platform_fee_micros)
        if amount_cents <= 0:
            return None

        # Create invoice with auto_advance=False to prevent early finalization
        invoice = stripe_call(
            stripe.Invoice.create,
            retryable=True,
            idempotency_key=f"platform-invoice-{billing_period.id}",
            customer=billing_config.stripe_customer_id,
            auto_advance=False,
            collection_method="charge_automatically",
        )

        stripe_call(
            stripe.InvoiceItem.create,
            retryable=True,
            idempotency_key=f"platform-item-{billing_period.id}",
            customer=billing_config.stripe_customer_id,
            invoice=invoice.id,
            amount=amount_cents,
            currency="usd",
            description=f"UBB Platform fee: {billing_period.period_start} - {billing_period.period_end}",
        )

        finalized = stripe_call(
            stripe.Invoice.finalize_invoice,
            retryable=True,
            idempotency_key=f"platform-finalize-{billing_period.id}",
            invoice=invoice.id,
            auto_advance=True,  # Now enable auto-advance for collection
        )

        return finalized.id
```

**Step 2: Run existing tests**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/billing/stripe/ --tb=short -q`
Expected: All PASS (or no tests in this directory — check)

**Step 3: Commit**

```bash
git add ubb-platform/apps/billing/stripe/services/stripe_service.py
git commit -m "refactor: StripeService reads stripe_customer_id from BillingTenantConfig"
```

---

### Task 11: Update TenantBillingService to Use Billing Queries

**Files:**
- Modify: `ubb-platform/apps/billing/tenant_billing/services.py:109`
- Modify: `ubb-platform/apps/billing/tenant_billing/tests/test_tasks.py`

**Step 1: Update tests to create BillingTenantConfig**

In `ubb-platform/apps/billing/tenant_billing/tests/test_tasks.py`, update the test classes that set `platform_fee_percentage` on Tenant to also create a `BillingTenantConfig`:

Add import at top:
```python
from apps.billing.tenant_billing.models import TenantBillingPeriod, BillingTenantConfig
```

In `CloseBillingPeriodTest.setUp`, after creating the tenant, create the config:

Replace:
```python
class CloseBillingPeriodTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Test", stripe_connected_account_id="acct_test",
            platform_fee_percentage=Decimal("2.50"),
        )
```

With:
```python
class CloseBillingPeriodTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Test", stripe_connected_account_id="acct_test",
            platform_fee_percentage=Decimal("2.50"),
        )
        BillingTenantConfig.objects.create(
            tenant=self.tenant,
            platform_fee_percentage=Decimal("2.50"),
        )
```

In `test_close_period_decimal_precision`, replace:
```python
        self.tenant.platform_fee_percentage = Decimal("0.33")
        self.tenant.save()
```
With:
```python
        BillingTenantConfig.objects.filter(tenant=self.tenant).update(
            platform_fee_percentage=Decimal("0.33"),
        )
```

**Step 2: Update _calculate_fees to read from billing config**

In `ubb-platform/apps/billing/tenant_billing/services.py`, replace the legacy fallback section in `_calculate_fees` (lines 105-119):

Replace:
```python
        else:
            # Legacy fallback: single percentage
            raw_fee = (
                Decimal(period.total_usage_cost_micros)
                * tenant.platform_fee_percentage
                / Decimal(100)
            )
            fee = int(raw_fee)
            fee = (fee // 10_000) * 10_000
            total_fee = fee
            line_items.append({
                "product": "platform",
                "description": "Platform fee",
                "amount_micros": fee,
            })
```

With:
```python
        else:
            # Legacy fallback: single percentage from billing config
            from apps.billing.queries import get_billing_config
            billing_config = get_billing_config(tenant.id)
            raw_fee = (
                Decimal(period.total_usage_cost_micros)
                * billing_config.platform_fee_percentage
                / Decimal(100)
            )
            fee = int(raw_fee)
            fee = (fee // 10_000) * 10_000
            total_fee = fee
            line_items.append({
                "product": "platform",
                "description": "Platform fee",
                "amount_micros": fee,
            })
```

**Step 3: Run tests to verify**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/billing/tenant_billing/tests/test_tasks.py --tb=short -q`
Expected: All PASS

**Step 4: Commit**

```bash
git add ubb-platform/apps/billing/tenant_billing/services.py ubb-platform/apps/billing/tenant_billing/tests/test_tasks.py
git commit -m "refactor: TenantBillingService reads platform_fee_percentage from BillingTenantConfig"
```

---

### Task 12: Update Stripe Connector (stripe_api.py) to Use Platform Queries

**Files:**
- Modify: `ubb-platform/apps/billing/connectors/stripe/stripe_api.py`

**Step 1: Update create_checkout_session and charge_saved_payment_method**

Replace entire `ubb-platform/apps/billing/connectors/stripe/stripe_api.py`:

```python
"""Customer-facing Stripe API operations.

These are part of the Stripe connector — they operate on the tenant's
Stripe Connected Account to handle customer-facing payments.
"""
import stripe
from django.conf import settings

from apps.billing.stripe.services.stripe_service import (
    stripe_call,
    validate_amount_micros,
    micros_to_cents,
)
from apps.platform.queries import get_customer_stripe_id, get_tenant_stripe_account

stripe.api_key = settings.STRIPE_SECRET_KEY


def create_checkout_session(customer, amount_micros, top_up_attempt, *, success_url, cancel_url):
    """Create Stripe Checkout session for top-up."""
    validate_amount_micros(amount_micros)
    amount_cents = micros_to_cents(amount_micros)
    customer_stripe_id = get_customer_stripe_id(customer.id)
    connected_account = get_tenant_stripe_account(customer.tenant_id)

    session = stripe_call(
        stripe.checkout.Session.create,
        retryable=True,
        idempotency_key=f"checkout-{top_up_attempt.id}",
        customer=customer_stripe_id,
        client_reference_id=str(top_up_attempt.id),
        mode="payment",
        line_items=[{
            "price_data": {
                "currency": "usd",
                "unit_amount": amount_cents,
                "product_data": {"name": "Account Top-Up"},
            },
            "quantity": 1,
        }],
        success_url=success_url,
        cancel_url=cancel_url,
        stripe_account=connected_account,
    )
    top_up_attempt.stripe_checkout_session_id = session.id
    top_up_attempt.save(update_fields=["stripe_checkout_session_id", "updated_at"])
    return session.url


def charge_saved_payment_method(customer, amount_micros, top_up_attempt):
    """Charge saved payment method for top-up.

    Idempotency key derived from top_up_attempt.id — deterministic across retries.
    """
    validate_amount_micros(amount_micros)
    amount_cents = micros_to_cents(amount_micros)
    customer_stripe_id = get_customer_stripe_id(customer.id)
    connected_account = get_tenant_stripe_account(customer.tenant_id)

    payment_methods = stripe_call(
        stripe.PaymentMethod.list,
        retryable=True,
        idempotency_key=None,  # list is naturally idempotent
        customer=customer_stripe_id,
        type="card",
        stripe_account=connected_account,
    )
    if not payment_methods.data:
        return None

    intent = stripe_call(
        stripe.PaymentIntent.create,
        retryable=True,
        idempotency_key=f"charge-{top_up_attempt.id}",
        customer=customer_stripe_id,
        amount=amount_cents,
        currency="usd",
        payment_method=payment_methods.data[0].id,
        off_session=True,
        confirm=True,
        stripe_account=connected_account,
    )
    return intent
```

**Step 2: Run tests**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest --tb=short -q`
Expected: All PASS

**Step 3: Commit**

```bash
git add ubb-platform/apps/billing/connectors/stripe/stripe_api.py
git commit -m "refactor: stripe_api.py uses platform query interface for Stripe IDs"
```

---

### Task 13: Update Stripe Connector (receipts.py) to Use Platform Queries

**Files:**
- Modify: `ubb-platform/apps/billing/connectors/stripe/receipts.py`

**Step 1: Update ReceiptService.create_topup_receipt**

In `ubb-platform/apps/billing/connectors/stripe/receipts.py`, replace lines 28-42:

Old:
```python
        import stripe

        connected_account = customer.tenant.stripe_connected_account_id
        amount_cents = micros_to_cents(top_up_attempt.amount_micros)

        try:
            stripe_invoice = stripe_call(
                stripe.Invoice.create,
                retryable=True,
                idempotency_key=f"receipt-{top_up_attempt.id}",
                customer=customer.stripe_customer_id,
```

New:
```python
        import stripe
        from apps.platform.queries import get_customer_stripe_id, get_tenant_stripe_account

        connected_account = get_tenant_stripe_account(customer.tenant_id)
        customer_stripe_id = get_customer_stripe_id(customer.id)
        amount_cents = micros_to_cents(top_up_attempt.amount_micros)

        try:
            stripe_invoice = stripe_call(
                stripe.Invoice.create,
                retryable=True,
                idempotency_key=f"receipt-{top_up_attempt.id}",
                customer=customer_stripe_id,
```

And replace line 48 (`customer=customer.stripe_customer_id,`) with `customer=customer_stripe_id,`.

**Step 2: Run tests**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest --tb=short -q`
Expected: All PASS

**Step 3: Commit**

```bash
git add ubb-platform/apps/billing/connectors/stripe/receipts.py
git commit -m "refactor: receipts.py uses platform query interface for Stripe IDs"
```

---

### Task 14: Update Stripe Connector (tasks.py) to Use Platform Queries

**Files:**
- Modify: `ubb-platform/apps/billing/connectors/stripe/tasks.py:156`

**Step 1: Update reconcile_topups_with_stripe**

In `ubb-platform/apps/billing/connectors/stripe/tasks.py`, in the `reconcile_topups_with_stripe` function, replace line 156:

```python
                stripe_account=attempt.customer.tenant.stripe_connected_account_id,
```

With:
```python
                stripe_account=get_tenant_stripe_account(attempt.customer.tenant_id),
```

And add the import inside the function (after the TopUpAttempt import on line 141):
```python
        from apps.platform.queries import get_tenant_stripe_account
```

**Step 2: Run tests**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest --tb=short -q`
Expected: All PASS

**Step 3: Commit**

```bash
git add ubb-platform/apps/billing/connectors/stripe/tasks.py
git commit -m "refactor: tasks.py uses platform query interface for Stripe account ID"
```

---

### Task 15: Update Stripe Connector (handlers.py) to Use Platform Queries

**Files:**
- Modify: `ubb-platform/apps/billing/connectors/stripe/handlers.py:26`

**Step 1: Update handle_balance_low_stripe**

In `ubb-platform/apps/billing/connectors/stripe/handlers.py`, replace line 26:

```python
    if not tenant.stripe_connected_account_id:
```

With:
```python
    from apps.platform.queries import get_tenant_stripe_account
    if not get_tenant_stripe_account(tenant_id):
```

And remove line 25 (`tenant = Tenant.objects.get(id=tenant_id)`) since we can defer it to after the check. Actually, `tenant` is still needed later in lock_for_billing context. Keep the Tenant fetch but use query interface for the check:

Replace lines 25-27:
```python
    tenant = Tenant.objects.get(id=tenant_id)
    if not tenant.stripe_connected_account_id:
        return  # No Stripe connector -- tenant handles via webhook
```

With:
```python
    from apps.platform.queries import get_tenant_stripe_account
    if not get_tenant_stripe_account(tenant_id):
        return  # No Stripe connector -- tenant handles via webhook
```

And remove the `Tenant` import from line 14 and the `tenant` fetch entirely (it's no longer used — `lock_for_billing` takes `customer_id` not `tenant`).

Actually, looking at the code more carefully, the `Tenant` import is also used elsewhere (no, it's only used in this function). Let's remove it cleanly:

Replace the import line:
```python
from apps.platform.tenants.models import Tenant
```
Remove it entirely (no other usage in the file).

**Step 2: Run tests**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest --tb=short -q`
Expected: All PASS

**Step 3: Commit**

```bash
git add ubb-platform/apps/billing/connectors/stripe/handlers.py
git commit -m "refactor: stripe handlers.py uses platform query interface for Stripe account check"
```

---

### Task 16: Update Subscription Sync to Use Platform Queries

**Files:**
- Modify: `ubb-platform/apps/subscriptions/stripe/sync.py`

**Step 1: Update sync_subscriptions**

Replace entire `ubb-platform/apps/subscriptions/stripe/sync.py`:

```python
import logging
from datetime import datetime, timezone as dt_timezone

import stripe
from django.utils import timezone

from apps.subscriptions.models import StripeSubscription
from apps.platform.queries import get_tenant_stripe_account, get_customers_by_stripe_id

logger = logging.getLogger(__name__)


def _unix_to_datetime(ts):
    """Convert unix timestamp to timezone-aware datetime."""
    if ts is None:
        return None
    return datetime.fromtimestamp(ts, tz=dt_timezone.utc)


def sync_subscriptions(tenant):
    """Full sync of active subscriptions from tenant's Connected Account.

    Returns dict with counts: {"synced": N, "skipped": N, "errors": N}
    """
    connected_account = get_tenant_stripe_account(tenant.id)
    if not connected_account:
        logger.warning("Tenant has no stripe_connected_account_id", extra={
            "data": {"tenant_id": str(tenant.id)},
        })
        return {"synced": 0, "skipped": 0, "errors": 0}

    # Build a lookup of stripe_customer_id -> customer_id for this tenant
    customers_by_stripe_id = get_customers_by_stripe_id(tenant.id)

    try:
        subscriptions = stripe.Subscription.list(
            status="all",
            stripe_account=connected_account,
            expand=["data.plan.product"],
        )
    except stripe.error.StripeError:
        logger.exception("Stripe API error during subscription sync", extra={
            "data": {"tenant_id": str(tenant.id)},
        })
        return {"synced": 0, "skipped": 0, "errors": 1}

    synced = 0
    skipped = 0
    errors = 0

    for stripe_sub in subscriptions.auto_paging_iter():
        customer_id = customers_by_stripe_id.get(stripe_sub.customer)
        if not customer_id:
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
                    "customer_id": customer_id,
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

**Step 2: Run tests**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/subscriptions/ --tb=short -q`
Expected: All PASS

**Step 3: Commit**

```bash
git add ubb-platform/apps/subscriptions/stripe/sync.py
git commit -m "refactor: subscription sync uses platform query interface for Stripe IDs"
```

---

### Task 17: Update API Endpoints to Use Platform Queries

**Files:**
- Modify: `ubb-platform/api/v1/billing_endpoints.py:142,144`
- Modify: `ubb-platform/api/v1/me_endpoints.py:139,140`
- Modify: `ubb-platform/api/v1/platform_endpoints.py:36`

**Step 1: Update billing_endpoints.py**

In `ubb-platform/api/v1/billing_endpoints.py`, in the `create_top_up` function (around lines 140-147):

Replace:
```python
    if tenant.stripe_connected_account_id:
        # Stripe connector is active — create checkout session
        if not customer.stripe_customer_id:
```

With:
```python
    from apps.platform.queries import get_tenant_stripe_account, get_customer_stripe_id
    if get_tenant_stripe_account(tenant.id):
        # Stripe connector is active — create checkout session
        if not get_customer_stripe_id(customer.id):
```

**Step 2: Update me_endpoints.py**

In `ubb-platform/api/v1/me_endpoints.py`, in the `create_top_up` function (around lines 139-143):

Replace:
```python
    if tenant.stripe_connected_account_id:
        if not customer.stripe_customer_id:
```

With:
```python
    from apps.platform.queries import get_tenant_stripe_account, get_customer_stripe_id
    if get_tenant_stripe_account(tenant.id):
        if not get_customer_stripe_id(customer.id):
```

**Step 3: Update platform_endpoints.py**

In `ubb-platform/api/v1/platform_endpoints.py`, the response already returns `customer.stripe_customer_id` on line 36. This is the platform's own model — it can read its own fields directly. However, per the design doc, we route through query interface for consistency.

Actually, `platform_endpoints.py` is IN the platform module returning platform data. It's reading its own model's field. Per the design principles, platform code reading platform models is fine. Only cross-module reads need query interfaces. **No change needed here.**

**Step 4: Run API endpoint tests**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest api/ --tb=short -q`
Expected: All PASS

**Step 5: Commit**

```bash
git add ubb-platform/api/v1/billing_endpoints.py ubb-platform/api/v1/me_endpoints.py
git commit -m "refactor: API endpoints use platform query interface for Stripe ID checks"
```

---

### Task 18: Delete Customer.get_min_balance()

**Files:**
- Modify: `ubb-platform/apps/platform/customers/models.py:38-42`

**Step 1: Verify no remaining callers**

Search for `get_min_balance` across the codebase. After Tasks 8 and 9, there should be zero callers.

Run: `cd ubb-platform && grep -rn "get_min_balance" --include="*.py" .`
Expected: Only the definition in `customers/models.py` remains (and possibly this plan file)

**Step 2: Delete the method**

In `ubb-platform/apps/platform/customers/models.py`, remove lines 38-42:

```python
    def get_min_balance(self):
        """Return customer-level min balance or fall back to tenant default."""
        if self.min_balance_micros is not None:
            return self.min_balance_micros
        return self.tenant.min_balance_micros
```

**Step 3: Run full test suite**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest --tb=short -q`
Expected: All PASS

**Step 4: Commit**

```bash
git add ubb-platform/apps/platform/customers/models.py
git commit -m "refactor: delete Customer.get_min_balance() — replaced by billing query interface"
```

---

### Task 19: Update Seed Command

**Files:**
- Modify: `ubb-platform/apps/platform/tenants/management/commands/seed_dev_data.py`

**Step 1: Update seed to also create BillingTenantConfig**

In `ubb-platform/apps/platform/tenants/management/commands/seed_dev_data.py`, after the tenant creation block (after line 48), add:

```python
        # Create or update billing config for this tenant
        from apps.billing.tenant_billing.models import BillingTenantConfig
        billing_config, bc_created = BillingTenantConfig.objects.get_or_create(
            tenant=tenant,
            defaults={
                "stripe_customer_id": "",
                "platform_fee_percentage": Decimal(options["platform_fee"]),
            },
        )
        if not bc_created:
            billing_config.platform_fee_percentage = Decimal(options["platform_fee"])
            billing_config.save(update_fields=["platform_fee_percentage", "updated_at"])
```

**Step 2: Run the seed command to verify**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python manage.py seed_dev_data --stripe-account acct_test --dry-run 2>&1 || echo "No dry-run option — just verify import works"`

Actually, just verify the import works:
Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -c "from apps.platform.tenants.management.commands.seed_dev_data import Command; print('OK')"`
Expected: `OK`

**Step 3: Commit**

```bash
git add ubb-platform/apps/platform/tenants/management/commands/seed_dev_data.py
git commit -m "feat: seed command creates BillingTenantConfig alongside tenant"
```

---

### Task 20: Full Test Suite Verification

**Step 1: Run the complete test suite**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest --tb=short -q`
Expected: All tests PASS with zero failures

**Step 2: Check for any remaining direct field reads**

Run a grep for the billing fields that should now be read through queries:

```bash
cd ubb-platform && grep -rn "tenant\.stripe_customer_id" --include="*.py" . | grep -v "migrations/" | grep -v "__pycache__" | grep -v "test_" | grep -v "models.py"
cd ubb-platform && grep -rn "tenant\.platform_fee_percentage" --include="*.py" . | grep -v "migrations/" | grep -v "__pycache__" | grep -v "test_" | grep -v "models.py"
cd ubb-platform && grep -rn "tenant\.min_balance_micros" --include="*.py" . | grep -v "migrations/" | grep -v "__pycache__" | grep -v "test_" | grep -v "models.py"
cd ubb-platform && grep -rn "tenant\.run_cost_limit_micros" --include="*.py" . | grep -v "migrations/" | grep -v "__pycache__" | grep -v "test_" | grep -v "models.py"
cd ubb-platform && grep -rn "tenant\.hard_stop_balance_micros" --include="*.py" . | grep -v "migrations/" | grep -v "__pycache__" | grep -v "test_" | grep -v "models.py"
cd ubb-platform && grep -rn "customer\.get_min_balance" --include="*.py" . | grep -v "__pycache__"
```

Expected: Zero results for all (except the field definitions in `models.py` which are excluded)

**Step 3: Final commit with verification note (if needed)**

If any grep results found remaining direct reads, fix them and commit. Otherwise, all done.

---

### Task 21: Squash Commit (Optional)

If preferred, create a single feature branch commit:

```bash
git log --oneline HEAD~15..HEAD  # Review all commits from this work
```

This task is optional — the individual commits are fine for PR review.

---

## Summary

| Task | Description | Files Changed |
|------|-------------|---------------|
| 1 | BillingTenantConfig model | `tenant_billing/models.py` + migration |
| 2 | CustomerBillingProfile model | `wallets/models.py` + migration |
| 3 | Data migration | 1 migration file |
| 4 | Billing query interface | `billing/queries.py` + tests |
| 5 | Platform query interface | `platform/queries.py` + tests |
| 6 | Subscriptions query interface | `subscriptions/queries.py` + tests |
| 7 | RunService signature change | `runs/services.py` + tests |
| 8 | RiskService → billing queries | `risk_service.py` + tests |
| 9 | Billing handler → billing queries | `handlers.py` |
| 10 | StripeService → billing queries | `stripe_service.py` |
| 11 | TenantBillingService → billing queries | `tenant_billing/services.py` + tests |
| 12 | stripe_api.py → platform queries | `stripe_api.py` |
| 13 | receipts.py → platform queries | `receipts.py` |
| 14 | tasks.py → platform queries | `tasks.py` |
| 15 | handlers.py → platform queries | `connectors/stripe/handlers.py` |
| 16 | sync.py → platform queries | `subscriptions/stripe/sync.py` |
| 17 | API endpoints → platform queries | `billing_endpoints.py`, `me_endpoints.py` |
| 18 | Delete Customer.get_min_balance() | `customers/models.py` |
| 19 | Update seed command | `seed_dev_data.py` |
| 20 | Full verification | grep + full test suite |
