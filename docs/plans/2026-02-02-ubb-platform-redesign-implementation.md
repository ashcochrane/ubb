# UBB Platform Redesign Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Redesign UBB from period-based invoicing to a prepaid wallet model with top-up receipts, tenant platform fee invoicing, group_keys on events, and widget JWT auth.

**Architecture:** Remove BillingPeriod, simplify Invoice to top-up receipt, add TenantBillingPeriod + TenantInvoice for platform fees, add group_keys to UsageEvent, add widget_secret to Tenant for JWT auth, add widget API endpoints.

**Tech Stack:** Django 6.0, Django Ninja, Celery, PostgreSQL, Stripe Connect, PyJWT, httpx (SDK)

## Review Fixes Applied

This plan incorporates the following review corrections:

- **Partial unique index** on TenantBillingPeriod: `UniqueConstraint(fields=["tenant"], condition=Q(status="open"))` ensures only one open period per tenant at a time
- **Decimal arithmetic** for platform fee calculation — no float conversion, uses `Decimal(100)` to avoid precision loss
- **Tenant.stripe_customer_id** — new field distinct from `stripe_connected_account_id`. The connected account ID is the tenant's Stripe account; the customer ID is the tenant as UBB's customer for platform fee billing
- **URL routing order** — widget and tenant paths registered before the generic `api/v1/` catch-all, or mounted as routers on the main NinjaAPI to avoid shadowing
- **ReceiptService** — does NOT create local Invoice record on Stripe failure; only creates when Stripe succeeds. Failures are logged and retryable
- **apps.invoicing stays in INSTALLED_APPS** — receipt service and tests live there, removing it would break test discovery and Celery autodiscovery
- **Tenant invoice retry path** — `_create_tenant_invoice` only sets `period.status="invoiced"` on success. On Stripe failure, period stays "closed" so the next scheduled run retries
- **widget_secret data migration** — explicit data migration backfills existing tenants with generated secrets
- **Widget JWT security** — validates UUID format on `tid` before DB lookup to prevent arbitrary DB queries
- **Widget top-up trigger** — new `"widget"` trigger choice on TopUpAttempt for analytics distinction
- **Analytics date params** — use `date` type in Django Ninja, not `str`, for automatic validation
- **accumulate_tenant_usage** — documented as synchronous service call in UsageService, not a Celery task
- **Billing period end semantics** — consistently uses `[first_of_month, first_of_next_month)` half-open interval; variable named `first_of_next_month` not `last_of_month`
- **timezone.now().date()** instead of `date.today()` for UTC-safe month boundaries
- **Stripe auto_advance=False** on platform invoice until items attached, then finalize explicitly
- **Analytics aggregation** — uses `billed_cost_micros` (falls back to `cost_micros` via Coalesce) to handle both pricing modes correctly
- **GROUP_KEY_PATTERN** — minimum 2 chars: `r'^[a-z][a-z0-9_]{1,63}$'`
- **rotate_widget_secret()** method on Tenant
- **Existing Invoice data migration** — handles existing Invoice records that reference BillingPeriod
- **SDK test** — clean, no inline correction; only final version with `tenant_id` param
- **git add** — enumerates specific files, never uses `git add -A`

---

### Task 1: Remove BillingPeriod Model and Related Code

**Files:**
- Modify: `ubb-platform/apps/usage/models.py:133-165` (remove BillingPeriod class)
- Modify: `ubb-platform/apps/usage/models.py:75-81` (remove invoice FK from UsageEvent)
- Modify: `ubb-platform/apps/usage/models.py:21-51` (simplify Invoice to top-up receipt)
- Modify: `ubb-platform/apps/invoicing/tasks.py` (remove generate_weekly_invoices, keep file for Task 6)
- Modify: `ubb-platform/api/v1/endpoints.py:242-246` (remove invoice_id refund guard)
- Modify: `ubb-platform/api/v1/tests/test_endpoints.py:366-397` (remove BillingPeriod test)
- Modify: `ubb-platform/apps/stripe_integration/services/stripe_service.py:171-249` (remove create_invoice_with_line_items)

**Note:** `apps.invoicing` stays in INSTALLED_APPS — it will host the receipt service in Task 6.

**Step 1: Remove BillingPeriod from usage/models.py**

Delete the `BillingPeriod` class (lines 133-165) and the `BILLING_PERIOD_STATUS_CHOICES` constant (lines 6-10).

**Step 2: Remove invoice FK from UsageEvent**

In `ubb-platform/apps/usage/models.py`, remove the `invoice` ForeignKey field (lines 75-81) from UsageEvent.

**Step 3: Simplify Invoice model to top-up receipt**

Replace the `Invoice` model with:

```python
INVOICE_STATUS_CHOICES = [
    ("draft", "Draft"),
    ("finalized", "Finalized"),
    ("paid", "Paid"),
    ("void", "Void"),
]


class Invoice(BaseModel):
    """Receipt invoice for a top-up payment."""
    tenant = models.ForeignKey(
        "tenants.Tenant", on_delete=models.CASCADE, related_name="invoices"
    )
    customer = models.ForeignKey(
        "customers.Customer", on_delete=models.CASCADE, related_name="invoices"
    )
    top_up_attempt = models.OneToOneField(
        "customers.TopUpAttempt", on_delete=models.CASCADE, related_name="invoice"
    )
    stripe_invoice_id = models.CharField(max_length=255, blank=True, default="", db_index=True)
    total_amount_micros = models.BigIntegerField(default=0)
    status = models.CharField(
        max_length=20,
        choices=INVOICE_STATUS_CHOICES,
        default="draft",
        db_index=True,
    )
    finalized_at = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "ubb_invoice"
        indexes = [
            models.Index(fields=["customer", "status"], name="idx_invoice_customer_status"),
        ]

    def __str__(self):
        return f"Invoice({self.customer.external_id}: {self.status})"
```

**Step 4: Remove invoice_id refund guard from endpoint**

In `ubb-platform/api/v1/endpoints.py`, remove lines 242-246 (the `if event.invoice_id is not None` block). The invoice FK on UsageEvent is gone — the receipt invoice is for top-ups, not usage events.

**Step 5: Remove the test that depends on BillingPeriod**

In `ubb-platform/api/v1/tests/test_endpoints.py`, delete the entire `test_refund_blocked_when_event_invoiced` method (lines 366-397).

**Step 6: Clear invoicing tasks file**

Replace `ubb-platform/apps/invoicing/tasks.py` with:

```python
# Receipt generation service lives in apps.invoicing.services (see Task 6).
# Old generate_weekly_invoices task has been removed.
```

**Step 7: Remove create_invoice_with_line_items from StripeService**

In `ubb-platform/apps/stripe_integration/services/stripe_service.py`, delete the `create_invoice_with_line_items` method (lines 171-249) and `credit_customer_invoice_balance` method (lines 157-168). These were for period-based invoicing. Also remove `_calculate_platform_fee` (lines 251-256) — platform fee logic moves to TenantBillingService.

**Step 8: Create data migration for existing Invoice records**

Existing Invoice records reference BillingPeriod via a OneToOneField. The migration must:
1. Remove the `billing_period` FK from Invoice
2. Add the `top_up_attempt` FK to Invoice (nullable initially)
3. Delete any existing Invoice records that can't be linked to a TopUpAttempt (or mark them void)

Create a data migration after the schema migration:

```python
from django.db import migrations


def clear_orphan_invoices(apps, schema_editor):
    """Delete existing invoices that reference billing periods (legacy data)."""
    Invoice = apps.get_model("usage", "Invoice")
    # These invoices were for period-based billing and have no top_up_attempt
    Invoice.objects.filter(top_up_attempt__isnull=True).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("usage", "XXXX_schema_migration"),  # replace with actual name
    ]

    operations = [
        migrations.RunPython(clear_orphan_invoices, migrations.RunPython.noop),
    ]
```

After the data migration, make `top_up_attempt` non-nullable.

**Step 9: Create migration**

Run: `cd ubb-platform && python manage.py makemigrations usage`

**Step 10: Run migration**

Run: `cd ubb-platform && python manage.py migrate`

**Step 11: Run tests**

Run: `cd ubb-platform && python manage.py test`
Expected: PASS

**Step 12: Commit**

```bash
git add ubb-platform/apps/usage/models.py ubb-platform/apps/invoicing/tasks.py ubb-platform/api/v1/endpoints.py ubb-platform/api/v1/tests/test_endpoints.py ubb-platform/apps/stripe_integration/services/stripe_service.py ubb-platform/apps/usage/migrations/
git commit -m "refactor: remove BillingPeriod, simplify Invoice to top-up receipt

Remove period-based end-user invoicing. Invoice model now links to
TopUpAttempt instead of BillingPeriod (receipt per top-up). Remove
invoice FK from UsageEvent, invoiced-event refund guard, and
create_invoice_with_line_items from StripeService. Existing Invoice
records without top_up_attempt are deleted via data migration.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

### Task 2: Add group_keys to UsageEvent

**Files:**
- Modify: `ubb-platform/apps/usage/models.py` (add group_keys field)
- Modify: `ubb-platform/api/v1/schemas.py` (add group_keys to RecordUsageRequest)
- Modify: `ubb-platform/apps/usage/services/usage_service.py` (pass group_keys through)
- Modify: `ubb-platform/api/v1/endpoints.py` (pass group_keys, add query params)
- Create: `ubb-platform/apps/usage/tests/test_group_keys.py`

**Step 1: Write the failing test**

Create `ubb-platform/apps/usage/tests/test_group_keys.py`:

```python
import json
from django.test import TestCase, Client
from apps.tenants.models import Tenant, TenantApiKey
from apps.customers.models import Customer
from apps.usage.models import UsageEvent
from apps.usage.services.usage_service import UsageService


class GroupKeysValidationTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Test", stripe_connected_account_id="acct_test"
        )
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="c1", email="t@t.com"
        )
        self.customer.wallet.balance_micros = 100_000_000
        self.customer.wallet.save()

    def test_group_keys_stored_on_event(self):
        result = UsageService.record_usage(
            tenant=self.tenant,
            customer=self.customer,
            request_id="req_gk1",
            idempotency_key="idem_gk1",
            cost_micros=1_000_000,
            group_keys={"department": "sales", "workflow_run": "wf_123"},
        )
        event = UsageEvent.objects.get(id=result["event_id"])
        self.assertEqual(event.group_keys, {"department": "sales", "workflow_run": "wf_123"})

    def test_group_keys_null_by_default(self):
        result = UsageService.record_usage(
            tenant=self.tenant,
            customer=self.customer,
            request_id="req_gk2",
            idempotency_key="idem_gk2",
            cost_micros=1_000_000,
        )
        event = UsageEvent.objects.get(id=result["event_id"])
        self.assertIsNone(event.group_keys)

    def test_group_keys_max_10_keys(self):
        keys = {f"key_{i}": f"val_{i}" for i in range(11)}
        with self.assertRaises(ValueError):
            UsageService.record_usage(
                tenant=self.tenant,
                customer=self.customer,
                request_id="req_gk3",
                idempotency_key="idem_gk3",
                cost_micros=1_000_000,
                group_keys=keys,
            )

    def test_group_keys_key_format_validation(self):
        with self.assertRaises(ValueError):
            UsageService.record_usage(
                tenant=self.tenant,
                customer=self.customer,
                request_id="req_gk4",
                idempotency_key="idem_gk4",
                cost_micros=1_000_000,
                group_keys={"Invalid-Key": "value"},
            )

    def test_group_keys_single_char_key_rejected(self):
        """Keys must be at least 2 characters."""
        with self.assertRaises(ValueError):
            UsageService.record_usage(
                tenant=self.tenant,
                customer=self.customer,
                request_id="req_gk6",
                idempotency_key="idem_gk6",
                cost_micros=1_000_000,
                group_keys={"x": "value"},
            )

    def test_group_keys_value_must_be_string(self):
        with self.assertRaises(ValueError):
            UsageService.record_usage(
                tenant=self.tenant,
                customer=self.customer,
                request_id="req_gk5",
                idempotency_key="idem_gk5",
                cost_micros=1_000_000,
                group_keys={"key": 123},
            )


class GroupKeysEndpointTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.tenant = Tenant.objects.create(name="Test Tenant")
        self.key_obj, self.raw_key = TenantApiKey.create_key(self.tenant, label="test")
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="cust_gk", email="gk@t.com"
        )
        self.customer.wallet.balance_micros = 100_000_000
        self.customer.wallet.save()

    def test_record_usage_with_group_keys(self):
        response = self.client.post(
            "/api/v1/usage",
            data=json.dumps({
                "customer_id": str(self.customer.id),
                "request_id": "req_gk_ep1",
                "idempotency_key": "idem_gk_ep1",
                "cost_micros": 1_000_000,
                "group_keys": {"department": "engineering"},
            }),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        self.assertEqual(response.status_code, 200)
        event = UsageEvent.objects.get(idempotency_key="idem_gk_ep1")
        self.assertEqual(event.group_keys, {"department": "engineering"})

    def test_usage_filter_by_group_key(self):
        for i, dept in enumerate(["sales", "engineering", "sales"]):
            self.client.post(
                "/api/v1/usage",
                data=json.dumps({
                    "customer_id": str(self.customer.id),
                    "request_id": f"req_filter_{i}",
                    "idempotency_key": f"idem_filter_{i}",
                    "cost_micros": 1_000_000,
                    "group_keys": {"department": dept},
                }),
                content_type="application/json",
                HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
            )

        response = self.client.get(
            f"/api/v1/customers/{self.customer.id}/usage?group_key=department&group_value=sales",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(len(body["data"]), 2)
```

**Step 2: Run test to verify it fails**

Run: `cd ubb-platform && python manage.py test apps.usage.tests.test_group_keys -v 2`
Expected: FAIL (group_keys not recognized)

**Step 3: Add group_keys field to UsageEvent**

In `ubb-platform/apps/usage/models.py`, add to UsageEvent class after `pricing_provenance`:

```python
    group_keys = models.JSONField(null=True, blank=True)
```

**Step 4: Add GIN index via migration**

After running makemigrations, create a manual migration for the GIN index. **Note:** replace the dependency with the actual auto migration name generated in the previous step.

```python
from django.db import migrations

class Migration(migrations.Migration):
    dependencies = [
        ("usage", "XXXX_auto"),  # IMPORTANT: replace with actual migration name from makemigrations
    ]

    operations = [
        migrations.RunSQL(
            sql='CREATE INDEX idx_usage_event_group_keys ON ubb_usage_event USING GIN (group_keys jsonb_path_ops);',
            reverse_sql='DROP INDEX IF EXISTS idx_usage_event_group_keys;',
        ),
    ]
```

**Step 5: Add validation helper**

In `ubb-platform/apps/usage/services/usage_service.py`, add before the class:

```python
import re

# Min 2 chars, max 64 chars, starts with letter, lowercase alphanumeric + underscores
GROUP_KEY_PATTERN = re.compile(r'^[a-z][a-z0-9_]{1,63}$')


def validate_group_keys(group_keys):
    """Validate group_keys dict. Raises ValueError on invalid input."""
    if group_keys is None:
        return
    if not isinstance(group_keys, dict):
        raise ValueError("group_keys must be a dict")
    if len(group_keys) > 10:
        raise ValueError("group_keys cannot have more than 10 keys")
    for key, value in group_keys.items():
        if not GROUP_KEY_PATTERN.match(key):
            raise ValueError(
                f"group_keys key '{key}' must be lowercase alphanumeric + underscores, "
                "start with a letter, 2-64 chars"
            )
        if not isinstance(value, str):
            raise ValueError(f"group_keys value for '{key}' must be a string")
        if len(value) > 256:
            raise ValueError(f"group_keys value for '{key}' exceeds 256 chars")
```

**Step 6: Update UsageService.record_usage to accept and store group_keys**

Add `group_keys=None` parameter to `record_usage`. Call `validate_group_keys(group_keys)` at the top (before idempotency check). Pass `group_keys=group_keys` to `UsageEvent.objects.create()`.

**Step 7: Add group_keys to RecordUsageRequest schema**

In `ubb-platform/api/v1/schemas.py`, add to `RecordUsageRequest`:

```python
    group_keys: Optional[dict[str, str]] = None
```

**Step 8: Pass group_keys through in endpoint**

In `ubb-platform/api/v1/endpoints.py`, update the `record_usage` endpoint to pass `group_keys=payload.group_keys` to `UsageService.record_usage()`.

**Step 9: Add group_key/group_value filtering to get_usage endpoint**

In `ubb-platform/api/v1/endpoints.py`, update `get_usage`:

```python
@api.get("/customers/{customer_id}/usage", response=PaginatedUsageResponse)
def get_usage(request, customer_id: str, cursor: str = None, limit: int = 50,
              group_key: str = None, group_value: str = None):
    customer = get_object_or_404(Customer, id=customer_id, tenant=request.auth.tenant)
    limit = min(max(limit, 1), 100)

    qs = customer.usage_events.all().order_by("-effective_at", "-id")

    if group_key and group_value:
        qs = qs.filter(group_keys__contains={group_key: group_value})

    # ... rest stays the same
```

**Step 10: Create migration**

Run: `cd ubb-platform && python manage.py makemigrations usage`

**Step 11: Run migration**

Run: `cd ubb-platform && python manage.py migrate`

**Step 12: Run tests**

Run: `cd ubb-platform && python manage.py test apps.usage.tests.test_group_keys -v 2`
Expected: PASS

**Step 13: Run full test suite**

Run: `cd ubb-platform && python manage.py test`
Expected: PASS

**Step 14: Commit**

```bash
git add ubb-platform/apps/usage/ ubb-platform/api/v1/schemas.py ubb-platform/api/v1/endpoints.py
git commit -m "feat: add group_keys to UsageEvent for aggregation tagging

Adds nullable JSONField with GIN index on UsageEvent. Supports up to
10 keys per event, lowercase alphanumeric key names (2-64 chars),
string values (max 256 chars). Filterable via group_key/group_value
query params on GET /usage.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

### Task 3: Add widget_secret to Tenant and JWT Auth

**Files:**
- Modify: `ubb-platform/apps/tenants/models.py` (add widget_secret + rotate method)
- Create: `ubb-platform/core/widget_auth.py` (JWT verification with UUID validation)
- Create: `ubb-platform/core/tests/test_widget_auth.py`

**Step 1: Install PyJWT**

Run: `cd ubb-platform && pip install PyJWT`
Add `PyJWT>=2.8` to pyproject.toml dependencies.

**Step 2: Write the failing test**

Create `ubb-platform/core/tests/test_widget_auth.py`:

```python
import uuid
import jwt
import time
from django.test import TestCase
from apps.tenants.models import Tenant
from apps.customers.models import Customer
from core.widget_auth import create_widget_token, verify_widget_token


class WidgetTokenTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Test", stripe_connected_account_id="acct_test"
        )
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="c1", email="t@t.com"
        )

    def test_create_and_verify_token(self):
        token = create_widget_token(
            self.tenant.widget_secret, str(self.customer.id), str(self.tenant.id)
        )
        payload = verify_widget_token(token)
        self.assertEqual(payload["sub"], str(self.customer.id))
        self.assertEqual(payload["tid"], str(self.tenant.id))

    def test_expired_token_rejected(self):
        token = create_widget_token(
            self.tenant.widget_secret, str(self.customer.id), str(self.tenant.id),
            expires_in=-1,
        )
        result = verify_widget_token(token)
        self.assertIsNone(result)

    def test_wrong_secret_rejected_via_two_step(self):
        """Token signed with wrong secret fails two-step verification."""
        token = create_widget_token(
            "wrong_secret_that_doesnt_match", str(self.customer.id), str(self.tenant.id)
        )
        # Two-step: decodes unverified to get tid, looks up tenant, verifies with real secret
        result = verify_widget_token(token)
        self.assertIsNone(result)

    def test_invalid_tid_uuid_rejected_without_db_query(self):
        """Non-UUID tid is rejected before any DB lookup."""
        payload = {
            "sub": str(self.customer.id),
            "tid": "not-a-uuid",
            "iss": "ubb",
            "exp": int(time.time()) + 900,
        }
        token = jwt.encode(payload, "any_secret", algorithm="HS256")
        result = verify_widget_token(token)
        self.assertIsNone(result)

    def test_tenant_auto_generates_widget_secret(self):
        self.assertTrue(len(self.tenant.widget_secret) > 0)

    def test_widget_secret_is_unique_per_tenant(self):
        tenant2 = Tenant.objects.create(name="Test2")
        self.assertNotEqual(self.tenant.widget_secret, tenant2.widget_secret)

    def test_rotate_widget_secret(self):
        old_secret = self.tenant.widget_secret
        self.tenant.rotate_widget_secret()
        self.assertNotEqual(self.tenant.widget_secret, old_secret)
        # Old token signed with old secret should fail
        token = create_widget_token(old_secret, str(self.customer.id), str(self.tenant.id))
        result = verify_widget_token(token)
        self.assertIsNone(result)
```

**Step 3: Run test to verify it fails**

Run: `cd ubb-platform && python manage.py test core.tests.test_widget_auth -v 2`
Expected: FAIL

**Step 4: Add widget_secret to Tenant model**

In `ubb-platform/apps/tenants/models.py` (secrets is already imported), add field and methods to Tenant:

```python
    widget_secret = models.CharField(max_length=64, blank=True, default="")

    def save(self, *args, **kwargs):
        if not self.widget_secret:
            self.widget_secret = secrets.token_urlsafe(48)
        super().save(*args, **kwargs)

    def rotate_widget_secret(self):
        """Generate a new widget_secret. Invalidates all existing widget JWTs."""
        self.widget_secret = secrets.token_urlsafe(48)
        self.save(update_fields=["widget_secret", "updated_at"])
```

**Step 5: Create widget_auth module with UUID validation**

Create `ubb-platform/core/widget_auth.py`:

```python
import time
import uuid
import logging

import jwt

logger = logging.getLogger(__name__)


def create_widget_token(secret, customer_id, tenant_id, expires_in=900):
    """Create a signed JWT for widget authentication."""
    payload = {
        "sub": customer_id,
        "tid": tenant_id,
        "iss": "ubb",
        "exp": int(time.time()) + expires_in,
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def verify_widget_token(token):
    """
    Verify a widget JWT via two-step decode:
    1. Decode without verification to extract tid
    2. Validate tid is a UUID (prevents arbitrary DB queries)
    3. Look up tenant to get the real secret
    4. Verify signature with tenant's secret

    Returns decoded payload dict or None if invalid/expired.
    """
    try:
        # Step 1: decode unverified to get tenant_id
        unverified = jwt.decode(token, options={"verify_signature": False})
        tenant_id = unverified.get("tid")
        if not tenant_id:
            return None

        # Step 2: validate UUID format before any DB query
        try:
            uuid.UUID(str(tenant_id))
        except (ValueError, AttributeError):
            return None

        # Step 3: look up tenant
        from apps.tenants.models import Tenant
        try:
            tenant = Tenant.objects.get(id=tenant_id, is_active=True)
        except Tenant.DoesNotExist:
            return None

        # Step 4: verify with real secret
        return jwt.decode(token, tenant.widget_secret, algorithms=["HS256"], issuer="ubb")

    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None
```

**Step 6: Create schema migration**

Run: `cd ubb-platform && python manage.py makemigrations tenants`

**Step 7: Create data migration to backfill existing tenants**

```python
import secrets
from django.db import migrations


def backfill_widget_secrets(apps, schema_editor):
    Tenant = apps.get_model("tenants", "Tenant")
    for tenant in Tenant.objects.filter(widget_secret=""):
        tenant.widget_secret = secrets.token_urlsafe(48)
        tenant.save(update_fields=["widget_secret"])


class Migration(migrations.Migration):
    dependencies = [
        ("tenants", "XXXX_add_widget_secret"),  # replace with actual schema migration name
    ]

    operations = [
        migrations.RunPython(backfill_widget_secrets, migrations.RunPython.noop),
    ]
```

**Step 8: Run migration**

Run: `cd ubb-platform && python manage.py migrate`

**Step 9: Run tests**

Run: `cd ubb-platform && python manage.py test core.tests.test_widget_auth -v 2`
Expected: PASS

**Step 10: Commit**

```bash
git add ubb-platform/apps/tenants/models.py ubb-platform/apps/tenants/migrations/ ubb-platform/core/widget_auth.py ubb-platform/core/tests/test_widget_auth.py
git commit -m "feat: add widget_secret to Tenant and JWT auth for widgets

Auto-generates widget_secret on tenant creation. Backfills existing
tenants via data migration. Adds rotate_widget_secret() method.
Two-step JWT verification validates UUID format on tid before DB
lookup to prevent arbitrary queries.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

### Task 4: Add TenantBillingPeriod, TenantInvoice, and stripe_customer_id

**Files:**
- Create: `ubb-platform/apps/tenant_billing/` (new Django app)
- Modify: `ubb-platform/apps/tenants/models.py` (add stripe_customer_id)
- Modify: `ubb-platform/config/settings.py` (add to INSTALLED_APPS)
- Create: `ubb-platform/apps/tenant_billing/tests/test_models.py`

**Step 1: Write the failing test**

Create `ubb-platform/apps/tenant_billing/tests/test_models.py`:

```python
from datetime import date
from django.test import TestCase
from django.db import IntegrityError, transaction
from apps.tenants.models import Tenant
from apps.tenant_billing.models import TenantBillingPeriod, TenantInvoice


class TenantBillingPeriodTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Test", stripe_connected_account_id="acct_test",
            platform_fee_percentage=1.00,
        )

    def test_create_billing_period(self):
        period = TenantBillingPeriod.objects.create(
            tenant=self.tenant,
            period_start=date(2026, 1, 1),
            period_end=date(2026, 2, 1),
        )
        self.assertEqual(period.status, "open")
        self.assertEqual(period.total_usage_cost_micros, 0)
        self.assertEqual(period.event_count, 0)
        self.assertEqual(period.platform_fee_micros, 0)

    def test_only_one_open_period_per_tenant(self):
        """Partial unique index ensures only one open period per tenant."""
        TenantBillingPeriod.objects.create(
            tenant=self.tenant,
            period_start=date(2026, 1, 1),
            period_end=date(2026, 2, 1),
        )
        # Different date range, same tenant, still open — should fail
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                TenantBillingPeriod.objects.create(
                    tenant=self.tenant,
                    period_start=date(2026, 2, 1),
                    period_end=date(2026, 3, 1),
                )

    def test_closed_period_allows_new_open(self):
        """After closing a period, a new open period can be created."""
        period = TenantBillingPeriod.objects.create(
            tenant=self.tenant,
            period_start=date(2026, 1, 1),
            period_end=date(2026, 2, 1),
        )
        period.status = "closed"
        period.save(update_fields=["status"])

        # New open period should succeed
        new_period = TenantBillingPeriod.objects.create(
            tenant=self.tenant,
            period_start=date(2026, 2, 1),
            period_end=date(2026, 3, 1),
        )
        self.assertEqual(new_period.status, "open")


class TenantInvoiceTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Test", stripe_connected_account_id="acct_test",
        )
        self.period = TenantBillingPeriod.objects.create(
            tenant=self.tenant,
            period_start=date(2026, 1, 1),
            period_end=date(2026, 2, 1),
            status="closed",
            total_usage_cost_micros=50_000_000_000,
            platform_fee_micros=500_000_000,
        )

    def test_create_tenant_invoice(self):
        invoice = TenantInvoice.objects.create(
            tenant=self.tenant,
            billing_period=self.period,
            total_amount_micros=500_000_000,
        )
        self.assertEqual(invoice.status, "draft")

    def test_one_invoice_per_period(self):
        TenantInvoice.objects.create(
            tenant=self.tenant,
            billing_period=self.period,
            total_amount_micros=500_000_000,
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                TenantInvoice.objects.create(
                    tenant=self.tenant,
                    billing_period=self.period,
                    total_amount_micros=500_000_000,
                )
```

**Step 2: Run test to verify it fails**

Run: `cd ubb-platform && python manage.py test apps.tenant_billing.tests.test_models -v 2`
Expected: FAIL (module not found)

**Step 3: Create the tenant_billing app**

Create `ubb-platform/apps/tenant_billing/__init__.py` (empty).

Create `ubb-platform/apps/tenant_billing/apps.py`:

```python
from django.apps import AppConfig


class TenantBillingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.tenant_billing"
```

Create `ubb-platform/apps/tenant_billing/admin.py` (empty, just `from django.contrib import admin`).

Create `ubb-platform/apps/tenant_billing/tests/__init__.py` (empty).

Create `ubb-platform/apps/tenant_billing/models.py`:

```python
from django.db import models

from core.models import BaseModel


TENANT_BILLING_PERIOD_STATUS_CHOICES = [
    ("open", "Open"),
    ("closed", "Closed"),
    ("invoiced", "Invoiced"),
]

TENANT_INVOICE_STATUS_CHOICES = [
    ("draft", "Draft"),
    ("finalized", "Finalized"),
    ("paid", "Paid"),
    ("void", "Void"),
    ("uncollectible", "Uncollectible"),
]


class TenantBillingPeriod(BaseModel):
    tenant = models.ForeignKey(
        "tenants.Tenant", on_delete=models.CASCADE, related_name="billing_periods"
    )
    period_start = models.DateField(db_index=True)
    period_end = models.DateField(db_index=True)
    status = models.CharField(
        max_length=20,
        choices=TENANT_BILLING_PERIOD_STATUS_CHOICES,
        default="open",
        db_index=True,
    )
    total_usage_cost_micros = models.BigIntegerField(default=0)
    event_count = models.IntegerField(default=0)
    platform_fee_micros = models.BigIntegerField(default=0)

    class Meta:
        db_table = "ubb_tenant_billing_period"
        constraints = [
            # Composite uniqueness for idempotent period creation
            models.UniqueConstraint(
                fields=["tenant", "period_start", "period_end"],
                name="uq_tenant_billing_period",
            ),
            # Only one open period per tenant at a time
            models.UniqueConstraint(
                fields=["tenant"],
                condition=models.Q(status="open"),
                name="uq_one_open_period_per_tenant",
            ),
        ]
        indexes = [
            models.Index(fields=["status", "period_end"], name="idx_tbp_status_end"),
        ]

    def __str__(self):
        return f"TenantBillingPeriod({self.tenant.name}: {self.period_start} - {self.period_end})"


class TenantInvoice(BaseModel):
    tenant = models.ForeignKey(
        "tenants.Tenant", on_delete=models.CASCADE, related_name="platform_invoices"
    )
    billing_period = models.OneToOneField(
        TenantBillingPeriod, on_delete=models.CASCADE, related_name="invoice"
    )
    stripe_invoice_id = models.CharField(max_length=255, blank=True, default="", db_index=True)
    total_amount_micros = models.BigIntegerField(default=0)
    status = models.CharField(
        max_length=20,
        choices=TENANT_INVOICE_STATUS_CHOICES,
        default="draft",
        db_index=True,
    )
    finalized_at = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "ubb_tenant_invoice"

    def __str__(self):
        return f"TenantInvoice({self.tenant.name}: {self.status})"
```

**Step 4: Add stripe_customer_id to Tenant model**

In `ubb-platform/apps/tenants/models.py`, add to Tenant:

```python
    # stripe_connected_account_id = tenant's own Stripe account (for end-user charges)
    # stripe_customer_id = tenant as UBB's customer (for platform fee billing)
    stripe_customer_id = models.CharField(max_length=255, blank=True, default="")
```

**Step 5: Add to INSTALLED_APPS**

In `ubb-platform/config/settings.py`, add `"apps.tenant_billing"` to INSTALLED_APPS.

**Step 6: Create migrations**

Run: `cd ubb-platform && python manage.py makemigrations tenant_billing tenants`

**Step 7: Run migration**

Run: `cd ubb-platform && python manage.py migrate`

**Step 8: Run tests**

Run: `cd ubb-platform && python manage.py test apps.tenant_billing.tests.test_models -v 2`
Expected: PASS

**Step 9: Commit**

```bash
git add ubb-platform/apps/tenant_billing/ ubb-platform/apps/tenants/models.py ubb-platform/apps/tenants/migrations/ ubb-platform/config/settings.py
git commit -m "feat: add TenantBillingPeriod, TenantInvoice, and stripe_customer_id

New app for monthly platform fee billing. TenantBillingPeriod has
partial unique index ensuring only one open period per tenant.
Tenant gets stripe_customer_id for platform fee billing (distinct
from stripe_connected_account_id which is the tenant's own account).

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

### Task 5: Add Tenant Billing Service and Celery Tasks

**Files:**
- Create: `ubb-platform/apps/tenant_billing/services.py`
- Create: `ubb-platform/apps/tenant_billing/tasks.py`
- Create: `ubb-platform/apps/tenant_billing/tests/test_tasks.py`
- Modify: `ubb-platform/apps/usage/services/usage_service.py` (trigger accumulation)
- Modify: `ubb-platform/config/settings.py` (update beat schedule + queues)
- Modify: `ubb-platform/apps/customers/models.py` (add "widget" trigger)

**Step 1: Add "widget" trigger to TopUpAttempt**

In `ubb-platform/apps/customers/models.py`, update `TOP_UP_ATTEMPT_TRIGGERS`:

```python
TOP_UP_ATTEMPT_TRIGGERS = [
    ("manual", "Manual"),
    ("auto_topup", "Auto Top-Up"),
    ("widget", "Widget"),
]
```

**Step 2: Write the failing test**

Create `ubb-platform/apps/tenant_billing/tests/test_tasks.py`:

```python
from datetime import date
from decimal import Decimal
from django.test import TestCase
from django.utils import timezone
from apps.tenants.models import Tenant
from apps.customers.models import Customer
from apps.tenant_billing.models import TenantBillingPeriod
from apps.tenant_billing.services import TenantBillingService


class AccumulateUsageTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Test", stripe_connected_account_id="acct_test",
            platform_fee_percentage=Decimal("1.00"),
        )

    def test_accumulate_creates_period_if_none(self):
        TenantBillingService.accumulate_usage(self.tenant, 1_000_000)
        period = TenantBillingPeriod.objects.get(tenant=self.tenant, status="open")
        self.assertEqual(period.total_usage_cost_micros, 1_000_000)
        self.assertEqual(period.event_count, 1)

    def test_accumulate_increments_existing_period(self):
        TenantBillingService.accumulate_usage(self.tenant, 1_000_000)
        TenantBillingService.accumulate_usage(self.tenant, 2_000_000)
        period = TenantBillingPeriod.objects.get(tenant=self.tenant, status="open")
        self.assertEqual(period.total_usage_cost_micros, 3_000_000)
        self.assertEqual(period.event_count, 2)


class CloseBillingPeriodTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Test", stripe_connected_account_id="acct_test",
            platform_fee_percentage=Decimal("2.50"),
        )

    def test_close_period_calculates_fee_with_decimal(self):
        period = TenantBillingPeriod.objects.create(
            tenant=self.tenant,
            period_start=date(2026, 1, 1),
            period_end=date(2026, 2, 1),
            total_usage_cost_micros=100_000_000_000,  # $100k
            event_count=5000,
        )
        TenantBillingService.close_period(period)
        period.refresh_from_db()
        self.assertEqual(period.status, "closed")
        # 2.5% of $100k = $2,500 = 2_500_000_000 micros
        self.assertEqual(period.platform_fee_micros, 2_500_000_000)

    def test_close_period_decimal_precision(self):
        """Verify no floating-point precision loss."""
        self.tenant.platform_fee_percentage = Decimal("0.33")
        self.tenant.save()
        period = TenantBillingPeriod.objects.create(
            tenant=self.tenant,
            period_start=date(2026, 1, 1),
            period_end=date(2026, 2, 1),
            total_usage_cost_micros=100_000_000,  # $100
            event_count=10,
        )
        TenantBillingService.close_period(period)
        period.refresh_from_db()
        # 0.33% of $100 = $0.33 = 330_000 micros (exact with Decimal)
        self.assertEqual(period.platform_fee_micros, 330_000)
```

**Step 3: Run test to verify it fails**

Run: `cd ubb-platform && python manage.py test apps.tenant_billing.tests.test_tasks -v 2`
Expected: FAIL

**Step 4: Create TenantBillingService**

Create `ubb-platform/apps/tenant_billing/services.py`:

```python
import logging
from decimal import Decimal

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from apps.tenant_billing.models import TenantBillingPeriod

logger = logging.getLogger(__name__)


class TenantBillingService:
    @staticmethod
    def get_or_create_current_period(tenant):
        """Get or create the current month's open billing period for a tenant.

        Uses half-open interval [first_of_month, first_of_next_month).
        Uses timezone.now().date() for UTC-safe month boundaries.
        """
        today = timezone.now().date()
        first_of_month = today.replace(day=1)
        if today.month == 12:
            first_of_next_month = today.replace(year=today.year + 1, month=1, day=1)
        else:
            first_of_next_month = today.replace(month=today.month + 1, day=1)

        period, _ = TenantBillingPeriod.objects.get_or_create(
            tenant=tenant,
            period_start=first_of_month,
            period_end=first_of_next_month,
            defaults={"status": "open"},
        )
        return period

    @staticmethod
    def accumulate_usage(tenant, billed_cost_micros):
        """Atomically increment the current billing period's usage totals.

        Called synchronously in the usage recording hot path. The atomic
        UPDATE is fast (no select, just increment) so this does not add
        meaningful latency.
        """
        period = TenantBillingService.get_or_create_current_period(tenant)
        TenantBillingPeriod.objects.filter(id=period.id, status="open").update(
            total_usage_cost_micros=F("total_usage_cost_micros") + billed_cost_micros,
            event_count=F("event_count") + 1,
        )

    @staticmethod
    @transaction.atomic
    def close_period(period):
        """Close a billing period and calculate platform fee using Decimal arithmetic."""
        period = TenantBillingPeriod.objects.select_for_update().get(pk=period.pk)
        if period.status != "open":
            return

        # Use Decimal arithmetic — no float conversion
        fee_micros = int(
            period.total_usage_cost_micros
            * period.tenant.platform_fee_percentage
            / Decimal(100)
        )

        period.status = "closed"
        period.platform_fee_micros = fee_micros
        period.save(update_fields=["status", "platform_fee_micros", "updated_at"])
```

**Step 5: Create Celery tasks**

Create `ubb-platform/apps/tenant_billing/tasks.py`:

```python
import logging

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from apps.tenant_billing.models import TenantBillingPeriod, TenantInvoice
from apps.tenant_billing.services import TenantBillingService

logger = logging.getLogger(__name__)


@shared_task(queue="ubb_billing")
def close_tenant_billing_periods():
    """Close all open billing periods from previous months."""
    today = timezone.now().date()
    first_of_month = today.replace(day=1)

    periods = TenantBillingPeriod.objects.filter(
        status="open",
        period_end__lte=first_of_month,
    ).select_related("tenant")

    for period in periods:
        try:
            TenantBillingService.close_period(period)
            logger.info(
                "Closed tenant billing period",
                extra={"data": {"period_id": str(period.id), "tenant": period.tenant.name}},
            )
        except Exception:
            logger.exception(
                "Failed to close tenant billing period",
                extra={"data": {"period_id": str(period.id)}},
            )


@shared_task(queue="ubb_billing")
def generate_tenant_platform_invoices():
    """Generate Stripe invoices for closed billing periods without invoices."""
    # Find closed periods that don't yet have an invoice
    periods = TenantBillingPeriod.objects.filter(
        status="closed",
    ).filter(
        invoice__isnull=True,
    ).select_related("tenant")

    for period in periods:
        if period.platform_fee_micros <= 0:
            period.status = "invoiced"
            period.save(update_fields=["status", "updated_at"])
            continue

        try:
            _create_tenant_invoice(period)
        except Exception:
            logger.exception(
                "Failed to create tenant platform invoice",
                extra={"data": {"period_id": str(period.id)}},
            )


@transaction.atomic
def _create_tenant_invoice(period):
    """Create a platform fee invoice for a tenant.

    On Stripe failure: period stays "closed" so the next scheduled run retries.
    On success: period moves to "invoiced".
    """
    period = TenantBillingPeriod.objects.select_for_update().get(pk=period.pk)
    if period.status != "closed":
        return

    # Idempotency: skip if invoice already exists
    if TenantInvoice.objects.filter(billing_period=period).exists():
        return

    # TODO: Stripe integration added in Task 10.
    # For now, create local record as draft.
    invoice = TenantInvoice.objects.create(
        tenant=period.tenant,
        billing_period=period,
        total_amount_micros=period.platform_fee_micros,
        status="draft",
    )

    period.status = "invoiced"
    period.save(update_fields=["status", "updated_at"])

    logger.info(
        "Created tenant platform invoice",
        extra={"data": {
            "invoice_id": str(invoice.id),
            "tenant": period.tenant.name,
            "amount_micros": period.platform_fee_micros,
        }},
    )
```

**Step 6: Wire accumulation into UsageService**

In `ubb-platform/apps/usage/services/usage_service.py`, after step 5 (wallet deduction, line ~96) and before step 6 (arrears check), add:

```python
        # 5b. Accumulate usage for tenant billing (synchronous — atomic UPDATE is fast)
        # billed_cost_micros is set for metric-priced events; cost_micros is the fallback
        # for legacy caller-provided cost mode.
        effective_cost = billed_cost_micros if billed_cost_micros is not None else cost_micros
        from apps.tenant_billing.services import TenantBillingService
        try:
            TenantBillingService.accumulate_usage(tenant, effective_cost)
        except Exception:
            logger.exception(
                "Failed to accumulate tenant usage",
                extra={"data": {"tenant_id": str(tenant.id)}},
            )
```

**Step 7: Update settings — add queue and beat schedule**

In `ubb-platform/config/settings.py`, add `Queue("ubb_billing")` to `CELERY_TASK_QUEUES`.

Add to `CELERY_BEAT_SCHEDULE`:

```python
    "close-tenant-billing-periods": {
        "task": "apps.tenant_billing.tasks.close_tenant_billing_periods",
        "schedule": crontab(minute=0, hour=0, day_of_month=1),  # 1st of month 00:00 UTC
    },
    "generate-tenant-platform-invoices": {
        "task": "apps.tenant_billing.tasks.generate_tenant_platform_invoices",
        "schedule": crontab(minute=0, hour=1, day_of_month=1),  # 1st of month 01:00 UTC
    },
```

**Step 8: Create migration for TopUpAttempt trigger choices**

Run: `cd ubb-platform && python manage.py makemigrations customers`

**Step 9: Run full test suite**

Run: `cd ubb-platform && python manage.py test`
Expected: PASS

**Step 10: Commit**

```bash
git add ubb-platform/apps/tenant_billing/ ubb-platform/apps/usage/services/usage_service.py ubb-platform/config/settings.py ubb-platform/apps/customers/models.py ubb-platform/apps/customers/migrations/
git commit -m "feat: add tenant billing service, tasks, and usage accumulation

TenantBillingService uses Decimal arithmetic for fee calculation.
accumulate_usage is synchronous (not a Celery task) — called in the
usage recording hot path. Celery tasks close periods and generate
invoices on 1st of each month. Adds 'widget' trigger to TopUpAttempt.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

### Task 6: Add Top-Up Receipt Invoice Generation

**Files:**
- Create: `ubb-platform/apps/invoicing/services.py`
- Create: `ubb-platform/apps/invoicing/tests/test_receipt.py`
- Modify: `ubb-platform/api/v1/webhooks.py` (trigger receipt after checkout)

**Note:** `apps.invoicing` remains in INSTALLED_APPS so tests are discovered and services importable.

**Step 1: Write the failing test**

Create `ubb-platform/apps/invoicing/tests/test_receipt.py`:

```python
from unittest.mock import patch, MagicMock
from django.test import TestCase
from apps.tenants.models import Tenant
from apps.customers.models import Customer, TopUpAttempt
from apps.usage.models import Invoice


class TopUpReceiptTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Test", stripe_connected_account_id="acct_test"
        )
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="c1", email="t@t.com",
            stripe_customer_id="cus_test",
        )
        self.attempt = TopUpAttempt.objects.create(
            customer=self.customer,
            amount_micros=20_000_000,
            trigger="manual",
            status="succeeded",
            stripe_checkout_session_id="cs_test",
        )

    @patch("apps.invoicing.services.stripe_call")
    def test_create_receipt_invoice(self, mock_stripe_call):
        mock_invoice = MagicMock()
        mock_invoice.id = "inv_test123"
        mock_stripe_call.return_value = mock_invoice

        from apps.invoicing.services import ReceiptService
        ReceiptService.create_topup_receipt(self.customer, self.attempt)

        invoice = Invoice.objects.get(top_up_attempt=self.attempt)
        self.assertEqual(invoice.total_amount_micros, 20_000_000)
        self.assertEqual(invoice.status, "paid")
        self.assertIsNotNone(invoice.paid_at)

    @patch("apps.invoicing.services.stripe_call")
    def test_stripe_failure_does_not_create_local_invoice(self, mock_stripe_call):
        """If Stripe fails, no local Invoice is created — allows retry."""
        mock_stripe_call.side_effect = Exception("Stripe API error")

        from apps.invoicing.services import ReceiptService
        ReceiptService.create_topup_receipt(self.customer, self.attempt)

        self.assertFalse(Invoice.objects.filter(top_up_attempt=self.attempt).exists())

    def test_receipt_idempotent(self):
        Invoice.objects.create(
            tenant=self.tenant,
            customer=self.customer,
            top_up_attempt=self.attempt,
            total_amount_micros=20_000_000,
            status="paid",
        )
        from apps.invoicing.services import ReceiptService
        ReceiptService.create_topup_receipt(self.customer, self.attempt)
        self.assertEqual(Invoice.objects.filter(top_up_attempt=self.attempt).count(), 1)
```

**Step 2: Run test to verify it fails**

Run: `cd ubb-platform && python manage.py test apps.invoicing.tests.test_receipt -v 2`
Expected: FAIL

**Step 3: Create ReceiptService**

Create `ubb-platform/apps/invoicing/services.py`:

```python
import logging
from django.utils import timezone
from apps.usage.models import Invoice
from apps.stripe_integration.services.stripe_service import stripe_call, micros_to_cents

logger = logging.getLogger(__name__)


class ReceiptService:
    @staticmethod
    def create_topup_receipt(customer, top_up_attempt):
        """Create a paid receipt invoice for a completed top-up.

        Only creates local Invoice record if ALL Stripe calls succeed.
        On Stripe failure, no local record is created — the next webhook
        retry or manual trigger can retry from scratch.
        """
        # Idempotency: skip if invoice already exists
        if Invoice.objects.filter(top_up_attempt=top_up_attempt).exists():
            return

        import stripe

        connected_account = customer.tenant.stripe_connected_account_id
        amount_cents = micros_to_cents(top_up_attempt.amount_micros)

        try:
            stripe_invoice = stripe_call(
                stripe.Invoice.create,
                retryable=True,
                idempotency_key=f"receipt-{top_up_attempt.id}",
                customer=customer.stripe_customer_id,
                auto_advance=False,
                collection_method="send_invoice",
                days_until_due=0,
                stripe_account=connected_account,
            )

            stripe_call(
                stripe.InvoiceItem.create,
                retryable=True,
                idempotency_key=f"receipt-item-{top_up_attempt.id}",
                customer=customer.stripe_customer_id,
                invoice=stripe_invoice.id,
                amount=amount_cents,
                currency="usd",
                description="Account Top-Up",
                stripe_account=connected_account,
            )

            stripe_call(
                stripe.Invoice.finalize_invoice,
                retryable=True,
                idempotency_key=f"receipt-finalize-{top_up_attempt.id}",
                invoice=stripe_invoice.id,
                stripe_account=connected_account,
            )

            stripe_call(
                stripe.Invoice.pay,
                retryable=True,
                idempotency_key=f"receipt-pay-{top_up_attempt.id}",
                invoice=stripe_invoice.id,
                paid_out_of_band=True,
                stripe_account=connected_account,
            )
        except Exception:
            logger.exception(
                "Failed to create Stripe receipt invoice — no local record created, retryable",
                extra={"data": {"attempt_id": str(top_up_attempt.id)}},
            )
            return  # No local record — allows retry

        Invoice.objects.create(
            tenant=customer.tenant,
            customer=customer,
            top_up_attempt=top_up_attempt,
            stripe_invoice_id=stripe_invoice.id,
            total_amount_micros=top_up_attempt.amount_micros,
            status="paid",
            finalized_at=timezone.now(),
            paid_at=timezone.now(),
        )
```

**Step 4: Wire into webhook handler**

In `ubb-platform/api/v1/webhooks.py`, at the end of `handle_checkout_completed` (after the `with transaction.atomic():` block, outside it), add:

```python
    # Generate receipt invoice (after commit)
    if attempt:
        transaction.on_commit(lambda: _dispatch_receipt(customer.id, attempt.id))


def _dispatch_receipt(customer_id, attempt_id):
    from apps.customers.models import Customer, TopUpAttempt
    from apps.invoicing.services import ReceiptService
    try:
        customer = Customer.objects.select_related("tenant").get(id=customer_id)
        attempt = TopUpAttempt.objects.get(id=attempt_id)
        ReceiptService.create_topup_receipt(customer, attempt)
    except Exception:
        logger.exception(
            "Failed to generate top-up receipt",
            extra={"data": {"customer_id": str(customer_id), "attempt_id": str(attempt_id)}},
        )
```

**Step 5: Clean up old invoicing tests**

Replace `ubb-platform/apps/invoicing/tests/test_tasks.py` with:

```python
# Old generate_weekly_invoices tests removed.
# Receipt tests are in test_receipt.py.
```

**Step 6: Run tests**

Run: `cd ubb-platform && python manage.py test apps.invoicing -v 2`
Expected: PASS

**Step 7: Run full test suite**

Run: `cd ubb-platform && python manage.py test`
Expected: PASS

**Step 8: Commit**

```bash
git add ubb-platform/apps/invoicing/services.py ubb-platform/apps/invoicing/tests/ ubb-platform/api/v1/webhooks.py
git commit -m "feat: generate receipt invoice on top-up completion

Creates a Stripe Invoice (marked paid out-of-band) on the tenant's
Connected Account after each successful top-up. Only creates local
Invoice record when all Stripe calls succeed — failures are retryable.
Triggered via on_commit from checkout webhook handler.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

### Task 7: Add Widget API Endpoints

**Files:**
- Create: `ubb-platform/api/v1/widget_endpoints.py`
- Create: `ubb-platform/api/v1/tests/test_widget_endpoints.py`
- Modify: `ubb-platform/core/widget_auth.py` (add WidgetJWTAuth class)
- Modify: `ubb-platform/config/urls.py` (add widget routes — BEFORE generic api/v1/)

**Step 1: Write the failing test**

Create `ubb-platform/api/v1/tests/test_widget_endpoints.py`:

```python
import json
from django.test import TestCase, Client
from apps.tenants.models import Tenant
from apps.customers.models import Customer, WalletTransaction
from core.widget_auth import create_widget_token


class WidgetBalanceTest(TestCase):
    def setUp(self):
        self.http_client = Client()
        self.tenant = Tenant.objects.create(
            name="Test", stripe_connected_account_id="acct_test"
        )
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="c1", email="t@t.com"
        )
        self.customer.wallet.balance_micros = 50_000_000
        self.customer.wallet.save()
        self.token = create_widget_token(
            self.tenant.widget_secret, str(self.customer.id), str(self.tenant.id)
        )

    def test_get_balance(self):
        response = self.http_client.get(
            "/api/v1/widget/balance",
            HTTP_AUTHORIZATION=f"Bearer {self.token}",
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["balance_micros"], 50_000_000)
        self.assertEqual(body["currency"], "USD")

    def test_no_token_returns_401(self):
        response = self.http_client.get("/api/v1/widget/balance")
        self.assertEqual(response.status_code, 401)

    def test_expired_token_returns_401(self):
        token = create_widget_token(
            self.tenant.widget_secret, str(self.customer.id), str(self.tenant.id),
            expires_in=-1,
        )
        response = self.http_client.get(
            "/api/v1/widget/balance",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        self.assertEqual(response.status_code, 401)


class WidgetTransactionsTest(TestCase):
    def setUp(self):
        self.http_client = Client()
        self.tenant = Tenant.objects.create(
            name="Test", stripe_connected_account_id="acct_test"
        )
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="c1", email="t@t.com"
        )
        wallet = self.customer.wallet
        wallet.balance_micros = 100_000_000
        wallet.save()
        for i in range(3):
            WalletTransaction.objects.create(
                wallet=wallet,
                transaction_type="TOP_UP",
                amount_micros=10_000_000,
                balance_after_micros=100_000_000 + (i + 1) * 10_000_000,
                description=f"Top up {i}",
            )
        self.token = create_widget_token(
            self.tenant.widget_secret, str(self.customer.id), str(self.tenant.id)
        )

    def test_list_transactions(self):
        response = self.http_client.get(
            "/api/v1/widget/transactions",
            HTTP_AUTHORIZATION=f"Bearer {self.token}",
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(len(body["data"]), 3)


class WidgetTopUpTest(TestCase):
    def setUp(self):
        self.http_client = Client()
        self.tenant = Tenant.objects.create(
            name="Test", stripe_connected_account_id="acct_test"
        )
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="c1", email="t@t.com",
            stripe_customer_id="cus_test",
        )
        self.token = create_widget_token(
            self.tenant.widget_secret, str(self.customer.id), str(self.tenant.id)
        )

    def test_create_topup_requires_amount(self):
        response = self.http_client.post(
            "/api/v1/widget/top-up",
            data=json.dumps({}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.token}",
        )
        self.assertEqual(response.status_code, 422)
```

**Step 2: Run test to verify it fails**

Run: `cd ubb-platform && python manage.py test api.v1.tests.test_widget_endpoints -v 2`
Expected: FAIL

**Step 3: Add WidgetJWTAuth to widget_auth.py**

Append to `ubb-platform/core/widget_auth.py`:

```python
from ninja.security import HttpBearer


class WidgetJWTAuth(HttpBearer):
    def authenticate(self, request, token):
        payload = verify_widget_token(token)
        if payload is None:
            return None

        from apps.customers.models import Customer
        try:
            customer = Customer.objects.select_related("tenant").get(
                id=payload["sub"],
                tenant_id=payload["tid"],
                tenant__is_active=True,
            )
        except Customer.DoesNotExist:
            return None

        request.widget_customer = customer
        request.widget_tenant = customer.tenant
        return customer
```

**Step 4: Create widget_endpoints.py**

Create `ubb-platform/api/v1/widget_endpoints.py`:

```python
from ninja import NinjaAPI, Schema, Field
from typing import Optional

from core.widget_auth import WidgetJWTAuth
from api.v1.pagination import encode_cursor, apply_cursor_filter
from apps.customers.models import TopUpAttempt
from apps.stripe_integration.services.stripe_service import StripeService
from apps.usage.models import Invoice

widget_api = NinjaAPI(auth=WidgetJWTAuth(), urls_namespace="ubb_widget_v1")


class WidgetBalanceResponse(Schema):
    balance_micros: int
    currency: str


class WidgetTopUpRequest(Schema):
    amount_micros: int = Field(gt=0)


class WidgetTopUpResponse(Schema):
    checkout_url: str


class WidgetTransactionOut(Schema):
    id: str
    transaction_type: str
    amount_micros: int
    balance_after_micros: int
    description: str
    created_at: str


class WidgetPaginatedTransactions(Schema):
    data: list[WidgetTransactionOut]
    next_cursor: Optional[str] = None
    has_more: bool


class WidgetInvoiceOut(Schema):
    id: str
    total_amount_micros: int
    status: str
    stripe_invoice_id: str
    created_at: str


class WidgetPaginatedInvoices(Schema):
    data: list[WidgetInvoiceOut]
    next_cursor: Optional[str] = None
    has_more: bool


@widget_api.get("/balance", response=WidgetBalanceResponse)
def widget_balance(request):
    customer = request.widget_customer
    wallet = customer.wallet
    return {"balance_micros": wallet.balance_micros, "currency": wallet.currency}


@widget_api.get("/transactions", response=WidgetPaginatedTransactions)
def widget_transactions(request, cursor: str = None, limit: int = 50):
    customer = request.widget_customer
    limit = min(max(limit, 1), 100)

    qs = customer.wallet.transactions.all().order_by("-created_at", "-id")

    if cursor:
        try:
            qs = apply_cursor_filter(qs, cursor, time_field="created_at")
        except ValueError:
            return widget_api.create_response(request, {"error": "Invalid cursor"}, status=400)

    txns = list(qs[:limit + 1])
    has_more = len(txns) > limit
    txns = txns[:limit]

    next_cursor = None
    if has_more and txns:
        last = txns[-1]
        next_cursor = encode_cursor(last.created_at, last.id)

    return {
        "data": [
            {
                "id": str(t.id),
                "transaction_type": t.transaction_type,
                "amount_micros": t.amount_micros,
                "balance_after_micros": t.balance_after_micros,
                "description": t.description,
                "created_at": t.created_at.isoformat(),
            }
            for t in txns
        ],
        "next_cursor": next_cursor,
        "has_more": has_more,
    }


@widget_api.post("/top-up", response=WidgetTopUpResponse)
def widget_top_up(request, payload: WidgetTopUpRequest):
    customer = request.widget_customer

    if not customer.stripe_customer_id:
        StripeService.create_customer(customer)

    attempt = TopUpAttempt.objects.create(
        customer=customer,
        amount_micros=payload.amount_micros,
        trigger="widget",  # Distinct from "manual" for analytics
        status="pending",
    )

    checkout_url = StripeService.create_checkout_session(
        customer, payload.amount_micros, attempt
    )
    return {"checkout_url": checkout_url}


@widget_api.get("/invoices", response=WidgetPaginatedInvoices)
def widget_invoices(request, cursor: str = None, limit: int = 50):
    customer = request.widget_customer
    limit = min(max(limit, 1), 100)

    qs = Invoice.objects.filter(customer=customer).order_by("-created_at", "-id")

    if cursor:
        try:
            qs = apply_cursor_filter(qs, cursor, time_field="created_at")
        except ValueError:
            return widget_api.create_response(request, {"error": "Invalid cursor"}, status=400)

    invoices = list(qs[:limit + 1])
    has_more = len(invoices) > limit
    invoices = invoices[:limit]

    next_cursor = None
    if has_more and invoices:
        last = invoices[-1]
        next_cursor = encode_cursor(last.created_at, last.id)

    return {
        "data": [
            {
                "id": str(inv.id),
                "total_amount_micros": inv.total_amount_micros,
                "status": inv.status,
                "stripe_invoice_id": inv.stripe_invoice_id,
                "created_at": inv.created_at.isoformat(),
            }
            for inv in invoices
        ],
        "next_cursor": next_cursor,
        "has_more": has_more,
    }
```

**Step 5: Add routes to urls.py — widget and tenant BEFORE generic api/v1/**

In `ubb-platform/config/urls.py`:

```python
from django.contrib import admin
from django.urls import path
from api.v1.endpoints import api
from api.v1.webhooks import stripe_webhook
from api.v1.widget_endpoints import widget_api

urlpatterns = [
    path("admin/", admin.site.urls),
    # Widget and tenant routes BEFORE generic api/v1/ to avoid shadowing
    path("api/v1/widget/", widget_api.urls),
    path("api/v1/webhooks/stripe", stripe_webhook),
    path("api/v1/", api.urls),
]
```

**Step 6: Run tests**

Run: `cd ubb-platform && python manage.py test api.v1.tests.test_widget_endpoints -v 2`
Expected: PASS

**Step 7: Run full test suite**

Run: `cd ubb-platform && python manage.py test`
Expected: PASS

**Step 8: Commit**

```bash
git add ubb-platform/api/v1/widget_endpoints.py ubb-platform/api/v1/tests/test_widget_endpoints.py ubb-platform/core/widget_auth.py ubb-platform/config/urls.py
git commit -m "feat: add widget API endpoints with JWT auth

Adds /widget/balance, /widget/transactions, /widget/top-up, and
/widget/invoices. Authenticated via JWT signed with tenant's
widget_secret. Widget top-ups use trigger='widget' for analytics.
Routes registered before generic api/v1/ to avoid shadowing.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

### Task 8: Add Tenant Dashboard Endpoints

**Files:**
- Create: `ubb-platform/api/v1/tenant_endpoints.py`
- Create: `ubb-platform/api/v1/tests/test_tenant_endpoints.py`
- Modify: `ubb-platform/config/urls.py`

**Step 1: Write the failing test**

Create `ubb-platform/api/v1/tests/test_tenant_endpoints.py`:

```python
from datetime import date
from django.test import TestCase, Client
from apps.tenants.models import Tenant, TenantApiKey
from apps.customers.models import Customer
from apps.usage.services.usage_service import UsageService
from apps.tenant_billing.models import TenantBillingPeriod, TenantInvoice


class TenantBillingPeriodsEndpointTest(TestCase):
    def setUp(self):
        self.http_client = Client()
        self.tenant = Tenant.objects.create(
            name="Test", stripe_connected_account_id="acct_test",
            platform_fee_percentage=1.00,
        )
        self.key_obj, self.raw_key = TenantApiKey.create_key(self.tenant, label="test")
        TenantBillingPeriod.objects.create(
            tenant=self.tenant,
            period_start=date(2026, 1, 1),
            period_end=date(2026, 2, 1),
            status="closed",
            total_usage_cost_micros=50_000_000_000,
            event_count=1000,
            platform_fee_micros=500_000_000,
        )

    def test_list_billing_periods(self):
        response = self.http_client.get(
            "/api/v1/tenant/billing-periods",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(len(body["data"]), 1)
        self.assertEqual(body["data"][0]["total_usage_cost_micros"], 50_000_000_000)

    def test_unauthenticated_returns_401(self):
        response = self.http_client.get("/api/v1/tenant/billing-periods")
        self.assertEqual(response.status_code, 401)


class TenantInvoicesEndpointTest(TestCase):
    def setUp(self):
        self.http_client = Client()
        self.tenant = Tenant.objects.create(
            name="Test", stripe_connected_account_id="acct_test",
        )
        self.key_obj, self.raw_key = TenantApiKey.create_key(self.tenant, label="test")
        period = TenantBillingPeriod.objects.create(
            tenant=self.tenant,
            period_start=date(2026, 1, 1),
            period_end=date(2026, 2, 1),
            status="invoiced",
            total_usage_cost_micros=50_000_000_000,
            platform_fee_micros=500_000_000,
        )
        TenantInvoice.objects.create(
            tenant=self.tenant,
            billing_period=period,
            total_amount_micros=500_000_000,
            status="paid",
        )

    def test_list_invoices(self):
        response = self.http_client.get(
            "/api/v1/tenant/invoices",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(len(body["data"]), 1)
        self.assertEqual(body["data"][0]["total_amount_micros"], 500_000_000)


class TenantUsageAnalyticsEndpointTest(TestCase):
    def setUp(self):
        self.http_client = Client()
        self.tenant = Tenant.objects.create(
            name="Test", stripe_connected_account_id="acct_test",
        )
        self.key_obj, self.raw_key = TenantApiKey.create_key(self.tenant, label="test")
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="c1", email="t@t.com"
        )
        self.customer.wallet.balance_micros = 100_000_000
        self.customer.wallet.save()
        for i in range(3):
            UsageService.record_usage(
                tenant=self.tenant,
                customer=self.customer,
                request_id=f"req_analytics_{i}",
                idempotency_key=f"idem_analytics_{i}",
                cost_micros=1_000_000,
            )

    def test_usage_analytics(self):
        response = self.http_client.get(
            "/api/v1/tenant/analytics/usage",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["total_events"], 3)
        self.assertEqual(body["total_billed_cost_micros"], 3_000_000)
```

**Step 2: Run test to verify it fails**

Run: `cd ubb-platform && python manage.py test api.v1.tests.test_tenant_endpoints -v 2`
Expected: FAIL

**Step 3: Create tenant_endpoints.py**

Create `ubb-platform/api/v1/tenant_endpoints.py`:

```python
from datetime import date
from typing import Optional

from django.db.models import Sum, Count
from django.db.models.functions import TruncDate, Coalesce
from ninja import NinjaAPI, Schema

from core.auth import ApiKeyAuth
from apps.tenant_billing.models import TenantBillingPeriod, TenantInvoice
from apps.usage.models import UsageEvent

tenant_api = NinjaAPI(auth=ApiKeyAuth(), urls_namespace="ubb_tenant_v1")


class TenantBillingPeriodOut(Schema):
    id: str
    period_start: str
    period_end: str
    status: str
    total_usage_cost_micros: int
    event_count: int
    platform_fee_micros: int


class TenantBillingPeriodListResponse(Schema):
    data: list[TenantBillingPeriodOut]


class TenantInvoiceOut(Schema):
    id: str
    billing_period_id: str
    stripe_invoice_id: str
    total_amount_micros: int
    status: str
    created_at: str


class TenantInvoiceListResponse(Schema):
    data: list[TenantInvoiceOut]


class UsageAnalyticsResponse(Schema):
    total_events: int
    total_billed_cost_micros: int
    total_provider_cost_micros: int
    by_provider: list[dict]
    by_event_type: list[dict]


class RevenueAnalyticsResponse(Schema):
    total_provider_cost_micros: int
    total_billed_cost_micros: int
    total_markup_micros: int
    daily: list[dict]


@tenant_api.get("/billing-periods", response=TenantBillingPeriodListResponse)
def list_billing_periods(request):
    tenant = request.auth.tenant
    periods = TenantBillingPeriod.objects.filter(tenant=tenant).order_by("-period_start")
    return {
        "data": [
            {
                "id": str(p.id),
                "period_start": p.period_start.isoformat(),
                "period_end": p.period_end.isoformat(),
                "status": p.status,
                "total_usage_cost_micros": p.total_usage_cost_micros,
                "event_count": p.event_count,
                "platform_fee_micros": p.platform_fee_micros,
            }
            for p in periods
        ]
    }


@tenant_api.get("/invoices", response=TenantInvoiceListResponse)
def list_invoices(request):
    tenant = request.auth.tenant
    invoices = TenantInvoice.objects.filter(tenant=tenant).order_by("-created_at")
    return {
        "data": [
            {
                "id": str(inv.id),
                "billing_period_id": str(inv.billing_period_id),
                "stripe_invoice_id": inv.stripe_invoice_id,
                "total_amount_micros": inv.total_amount_micros,
                "status": inv.status,
                "created_at": inv.created_at.isoformat(),
            }
            for inv in invoices
        ]
    }


@tenant_api.get("/analytics/usage", response=UsageAnalyticsResponse)
def usage_analytics(request, start_date: date = None, end_date: date = None):
    """Usage analytics. Uses billed_cost_micros (falls back to cost_micros via Coalesce)
    to correctly aggregate both pricing modes."""
    tenant = request.auth.tenant
    qs = UsageEvent.objects.filter(tenant=tenant)

    if start_date:
        qs = qs.filter(effective_at__date__gte=start_date)
    if end_date:
        qs = qs.filter(effective_at__date__lte=end_date)

    # Coalesce: use billed_cost_micros if set (metric pricing), else cost_micros (legacy)
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

    by_event_type = list(
        qs.exclude(event_type="").values("event_type").annotate(
            event_count=Count("id"),
            total_cost_micros=Sum(effective_cost),
        ).order_by("-total_cost_micros")
    )

    return {
        "total_events": totals["total_events"] or 0,
        "total_billed_cost_micros": totals["total_billed_cost_micros"] or 0,
        "total_provider_cost_micros": totals["total_provider_cost_micros"] or 0,
        "by_provider": by_provider,
        "by_event_type": by_event_type,
    }


@tenant_api.get("/analytics/revenue", response=RevenueAnalyticsResponse)
def revenue_analytics(request, start_date: date = None, end_date: date = None):
    tenant = request.auth.tenant
    qs = UsageEvent.objects.filter(tenant=tenant)

    if start_date:
        qs = qs.filter(effective_at__date__gte=start_date)
    if end_date:
        qs = qs.filter(effective_at__date__lte=end_date)

    totals = qs.aggregate(
        total_provider_cost_micros=Sum("provider_cost_micros"),
        total_billed_cost_micros=Sum(Coalesce("billed_cost_micros", "cost_micros")),
    )

    provider_cost = totals["total_provider_cost_micros"] or 0
    billed_cost = totals["total_billed_cost_micros"] or 0

    daily = list(
        qs.annotate(day=TruncDate("effective_at")).values("day").annotate(
            provider_cost_micros=Sum("provider_cost_micros"),
            billed_cost_micros=Sum(Coalesce("billed_cost_micros", "cost_micros")),
            event_count=Count("id"),
        ).order_by("day")
    )

    for entry in daily:
        if entry.get("day"):
            entry["day"] = entry["day"].isoformat()

    return {
        "total_provider_cost_micros": provider_cost,
        "total_billed_cost_micros": billed_cost,
        "total_markup_micros": billed_cost - provider_cost,
        "daily": daily,
    }
```

**Step 4: Add tenant routes to urls.py — BEFORE generic api/v1/**

In `ubb-platform/config/urls.py`, add import and path:

```python
from api.v1.tenant_endpoints import tenant_api

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/widget/", widget_api.urls),
    path("api/v1/tenant/", tenant_api.urls),
    path("api/v1/webhooks/stripe", stripe_webhook),
    path("api/v1/", api.urls),
]
```

**Step 5: Run tests**

Run: `cd ubb-platform && python manage.py test api.v1.tests.test_tenant_endpoints -v 2`
Expected: PASS

**Step 6: Run full test suite**

Run: `cd ubb-platform && python manage.py test`
Expected: PASS

**Step 7: Commit**

```bash
git add ubb-platform/api/v1/tenant_endpoints.py ubb-platform/api/v1/tests/test_tenant_endpoints.py ubb-platform/config/urls.py
git commit -m "feat: add tenant dashboard endpoints for billing and analytics

Adds /tenant/billing-periods, /tenant/invoices, /tenant/analytics/usage,
and /tenant/analytics/revenue. Uses date type params for validation.
Analytics use Coalesce(billed_cost_micros, cost_micros) to handle
both pricing modes. Routes before generic api/v1/ to avoid shadowing.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

### Task 9: Update SDK — Add Widget Token and group_keys Support

**Files:**
- Modify: `ubb-sdk/ubb/client.py` (add create_widget_token, update record_usage)
- Create: `ubb-sdk/tests/test_widget_token.py`
- Modify: `ubb-sdk/pyproject.toml` (add PyJWT dependency)

**Step 1: Write the failing test**

Create `ubb-sdk/tests/test_widget_token.py`:

```python
import jwt
from ubb.client import UBBClient


def test_create_widget_token():
    client = UBBClient(
        api_key="ubb_test_abc123",
        base_url="http://localhost:8001",
        widget_secret="test_secret_key_1234567890",
        tenant_id="tid_abc123",
    )
    token = client.create_widget_token(customer_id="cust_abc123")
    decoded = jwt.decode(token, "test_secret_key_1234567890", algorithms=["HS256"])
    assert decoded["sub"] == "cust_abc123"
    assert decoded["tid"] == "tid_abc123"
    assert decoded["iss"] == "ubb"
    assert "exp" in decoded


def test_create_widget_token_no_secret_raises():
    client = UBBClient(api_key="ubb_test_abc123")
    try:
        client.create_widget_token(customer_id="cust_abc123")
        assert False, "Should have raised"
    except ValueError:
        pass


def test_create_widget_token_no_tenant_id_raises():
    client = UBBClient(api_key="ubb_test_abc123", widget_secret="secret")
    try:
        client.create_widget_token(customer_id="cust_abc123")
        assert False, "Should have raised"
    except ValueError:
        pass
```

**Step 2: Run test to verify it fails**

Run: `cd ubb-sdk && pip install PyJWT && python -m pytest tests/test_widget_token.py -v`
Expected: FAIL

**Step 3: Update UBBClient constructor**

In `ubb-sdk/ubb/client.py`, update constructor to accept `widget_secret` and `tenant_id`:

```python
def __init__(self, api_key: str, base_url: str = "http://localhost:8001",
             timeout: float = 10.0, widget_secret: str | None = None,
             tenant_id: str | None = None) -> None:
    self._base_url = base_url.rstrip("/")
    self._widget_secret = widget_secret
    self._tenant_id = tenant_id
    self._http = httpx.Client(
        base_url=self._base_url,
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=timeout,
    )
```

**Step 4: Add create_widget_token method**

```python
def create_widget_token(self, customer_id: str, expires_in: int = 900) -> str:
    """Create a signed JWT for widget authentication."""
    if not self._widget_secret:
        raise ValueError("widget_secret is required to create widget tokens")
    if not self._tenant_id:
        raise ValueError("tenant_id is required to create widget tokens")

    import time
    import jwt

    payload = {
        "sub": customer_id,
        "tid": self._tenant_id,
        "iss": "ubb",
        "exp": int(time.time()) + expires_in,
    }
    return jwt.encode(payload, self._widget_secret, algorithm="HS256")
```

**Step 5: Update record_usage to support both modes and group_keys**

The existing `record_usage` only supports `cost_micros` mode. Update to support both modes (the API already supports both). **Note:** `event_type`, `provider`, `usage_metrics`, and `properties` are not new to the API — they were already supported server-side but missing from the SDK.

```python
def record_usage(self, customer_id: str, request_id: str, idempotency_key: str,
                 cost_micros: int | None = None, metadata: dict | None = None,
                 event_type: str | None = None, provider: str | None = None,
                 usage_metrics: dict | None = None, properties: dict | None = None,
                 group_keys: dict | None = None) -> RecordUsageResult:
    body: dict = {
        "customer_id": customer_id, "request_id": request_id,
        "idempotency_key": idempotency_key, "metadata": metadata or {},
    }
    if cost_micros is not None:
        _check_micros(cost_micros, "cost_micros")
        body["cost_micros"] = cost_micros
    if usage_metrics is not None:
        body["event_type"] = event_type
        body["provider"] = provider
        body["usage_metrics"] = usage_metrics
        if properties:
            body["properties"] = properties
    if group_keys is not None:
        body["group_keys"] = group_keys
    r = self._request("post", "/api/v1/usage", json=body)
    return RecordUsageResult(**r.json())
```

**Step 6: Add PyJWT to SDK dependencies**

In `ubb-sdk/pyproject.toml`, add `PyJWT>=2.8` to dependencies.

**Step 7: Run tests**

Run: `cd ubb-sdk && python -m pytest tests/test_widget_token.py -v`
Expected: PASS

**Step 8: Commit**

```bash
git add ubb-sdk/ubb/client.py ubb-sdk/tests/test_widget_token.py ubb-sdk/pyproject.toml
git commit -m "feat: add widget token generation and group_keys to SDK

UBBClient accepts widget_secret and tenant_id for JWT creation.
record_usage() now supports both pricing modes (cost_micros and
usage_metrics) plus group_keys parameter. Adds PyJWT dependency.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

### Task 10: Wire Stripe for Tenant Platform Fee Invoicing

**Files:**
- Modify: `ubb-platform/apps/stripe_integration/services/stripe_service.py`
- Modify: `ubb-platform/apps/tenant_billing/tasks.py` (wire in Stripe calls)
- Create: `ubb-platform/apps/tenant_billing/tests/test_platform_invoice.py`

**Critical:** Platform fee invoices are billed to `tenant.stripe_customer_id` (the tenant as UBB's customer on UBB's own Stripe account), NOT `tenant.stripe_connected_account_id` (the tenant's own Stripe Connect account). These are different Stripe objects.

**Step 1: Write the failing test**

Create `ubb-platform/apps/tenant_billing/tests/test_platform_invoice.py`:

```python
from datetime import date
from unittest.mock import patch, MagicMock
from django.test import TestCase
from apps.tenants.models import Tenant
from apps.tenant_billing.models import TenantBillingPeriod, TenantInvoice
from apps.tenant_billing.tasks import generate_tenant_platform_invoices


class PlatformInvoiceStripeTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Test",
            stripe_connected_account_id="acct_test",
            stripe_customer_id="cus_tenant_test",  # Tenant as UBB's customer
            platform_fee_percentage=1.00,
        )
        self.period = TenantBillingPeriod.objects.create(
            tenant=self.tenant,
            period_start=date(2026, 1, 1),
            period_end=date(2026, 2, 1),
            status="closed",
            total_usage_cost_micros=100_000_000_000,
            event_count=5000,
            platform_fee_micros=1_000_000_000,
        )

    @patch("apps.stripe_integration.services.stripe_service.stripe_call")
    def test_creates_stripe_invoice_for_platform_fee(self, mock_stripe_call):
        mock_invoice = MagicMock()
        mock_invoice.id = "inv_platform_test"
        mock_stripe_call.return_value = mock_invoice

        generate_tenant_platform_invoices()

        invoice = TenantInvoice.objects.get(billing_period=self.period)
        self.assertEqual(invoice.total_amount_micros, 1_000_000_000)
        self.assertEqual(invoice.status, "finalized")

        # Verify Stripe was called with tenant's customer ID, not connected account
        create_call = mock_stripe_call.call_args_list[0]
        self.assertNotIn("stripe_account", create_call.kwargs)

    @patch("apps.stripe_integration.services.stripe_service.stripe_call")
    def test_stripe_failure_keeps_period_closed_for_retry(self, mock_stripe_call):
        """On Stripe failure, period stays closed so next run retries."""
        mock_stripe_call.side_effect = Exception("Stripe down")

        generate_tenant_platform_invoices()

        self.period.refresh_from_db()
        self.assertEqual(self.period.status, "closed")  # NOT "invoiced"
        self.assertFalse(TenantInvoice.objects.filter(billing_period=self.period).exists())

    def test_zero_fee_period_auto_invoiced(self):
        self.period.platform_fee_micros = 0
        self.period.save()

        generate_tenant_platform_invoices()

        self.period.refresh_from_db()
        self.assertEqual(self.period.status, "invoiced")
        self.assertFalse(TenantInvoice.objects.filter(billing_period=self.period).exists())
```

**Step 2: Run test to verify it fails**

Run: `cd ubb-platform && python manage.py test apps.tenant_billing.tests.test_platform_invoice -v 2`
Expected: FAIL

**Step 3: Add tenant platform invoice to StripeService**

In `ubb-platform/apps/stripe_integration/services/stripe_service.py`, add:

```python
    @staticmethod
    def create_tenant_platform_invoice(tenant, billing_period):
        """
        Create a Stripe invoice for the platform fee billed directly to the tenant.

        Uses tenant.stripe_customer_id (tenant as UBB's customer on UBB's Stripe account).
        NOT on the connected account — this is UBB billing the tenant.
        auto_advance=False until items attached, then finalize explicitly.
        """
        if not tenant.stripe_customer_id:
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
            customer=tenant.stripe_customer_id,
            auto_advance=False,
            collection_method="charge_automatically",
        )

        stripe_call(
            stripe.InvoiceItem.create,
            retryable=True,
            idempotency_key=f"platform-item-{billing_period.id}",
            customer=tenant.stripe_customer_id,
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

**Step 4: Update _create_tenant_invoice in tasks.py with retry-safe logic**

In `ubb-platform/apps/tenant_billing/tasks.py`, replace `_create_tenant_invoice`:

```python
@transaction.atomic
def _create_tenant_invoice(period):
    """Create a platform fee invoice for a tenant.

    On Stripe failure: period stays 'closed', no local record — allows retry.
    On success: local TenantInvoice created, period moves to 'invoiced'.
    """
    period = TenantBillingPeriod.objects.select_for_update().get(pk=period.pk)
    if period.status != "closed":
        return

    if TenantInvoice.objects.filter(billing_period=period).exists():
        return

    from apps.stripe_integration.services.stripe_service import StripeService

    # If Stripe fails, exception propagates, transaction rolls back,
    # period stays "closed", and next scheduled run retries.
    stripe_invoice_id = StripeService.create_tenant_platform_invoice(
        period.tenant, period
    )

    if not stripe_invoice_id:
        return

    TenantInvoice.objects.create(
        tenant=period.tenant,
        billing_period=period,
        stripe_invoice_id=stripe_invoice_id,
        total_amount_micros=period.platform_fee_micros,
        status="finalized",
        finalized_at=timezone.now(),
    )

    period.status = "invoiced"
    period.save(update_fields=["status", "updated_at"])

    logger.info(
        "Created tenant platform invoice",
        extra={"data": {
            "invoice_id": stripe_invoice_id,
            "tenant": period.tenant.name,
            "amount_micros": period.platform_fee_micros,
        }},
    )
```

**Step 5: Run tests**

Run: `cd ubb-platform && python manage.py test apps.tenant_billing.tests.test_platform_invoice -v 2`
Expected: PASS

**Step 6: Run full test suite**

Run: `cd ubb-platform && python manage.py test`
Expected: PASS

**Step 7: Commit**

```bash
git add ubb-platform/apps/stripe_integration/services/stripe_service.py ubb-platform/apps/tenant_billing/tasks.py ubb-platform/apps/tenant_billing/tests/test_platform_invoice.py
git commit -m "feat: wire Stripe for tenant platform fee invoicing

StripeService.create_tenant_platform_invoice bills tenant via their
stripe_customer_id (UBB's Stripe account, not connected account).
Creates invoice with auto_advance=False, adds items, then finalizes.
On failure, period stays closed for retry on next scheduled run.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

### Task 11: Final Cleanup and Full Test Suite

**Files:**
- Verify all dangling imports removed
- Run full test suite
- Run SDK tests

**Step 1: Run full platform test suite**

Run: `cd ubb-platform && python manage.py test -v 2`
Expected: ALL PASS

**Step 2: Verify no dangling BillingPeriod references**

Run: `cd ubb-platform && grep -r "BillingPeriod" --include="*.py" | grep -v migrations | grep -v __pycache__ | grep -v TenantBillingPeriod`
Expected: No results (only TenantBillingPeriod references remain)

**Step 3: Verify generate_weekly_invoices removed**

Run: `cd ubb-platform && grep -r "generate_weekly_invoices" --include="*.py" | grep -v migrations | grep -v __pycache__`
Expected: No results

**Step 4: Run SDK tests**

Run: `cd ubb-sdk && python -m pytest -v`
Expected: PASS

**Step 5: Commit**

```bash
git add ubb-platform/apps/invoicing/tests/test_tasks.py
git commit -m "chore: clean up stale invoicing tests and verify full suite

Remove old generate_weekly_invoices test file contents. Verify no
dangling BillingPeriod references. All platform and SDK tests passing.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```
