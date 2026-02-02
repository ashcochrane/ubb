# UBB Platform Production Readiness — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Harden the UBB billing platform for production by fixing critical Stripe safety issues, race conditions, webhook reliability, and logging, then adding database indexes, pagination, input validation, soft deletes, security hardening, and missing endpoints.

**Architecture:** Phased approach — foundational modules first (exceptions, locking, logging), then layer Stripe safety, transaction boundaries, webhook reliability, and finally API improvements. Each task is independently testable and committable.

**Tech Stack:** Django 6.0, Django Ninja, PostgreSQL, Celery/Redis, Stripe SDK, pytest-django

**Design Document:** `docs/plans/2025-01-29-production-readiness-design.md` — the source of truth for all design decisions. Read it before starting.

**Test runner:** `python manage.py test` (Django test runner — no pytest config exists). All test files live in `apps/<app>/tests/`.

**Working directory:** `/Users/ashtoncochrane/Git/localscouta/ubb-platform/`

---

## Task Dependency Graph

```
Task 1 (exceptions) ─┐
Task 2 (locking)  ───┤
Task 3 (logging)  ───┤
                     ├─> Task 4 (TopUpAttempt model)
                     │   ├─> Task 5 (stripe_service rewrite)
                     │   │   ├─> Task 7 (auto_topup_service rewrite)
                     │   │   │   └─> Task 8 (usage_service rewrite)
                     │   │   └─> Task 9 (invoicing rewrite)
                     │   └─> Task 6 (StripeWebhookEvent model)
                     │       └─> Task 10 (webhooks rewrite)
                     │
Task 11 (settings hardening) ── independent
Task 12 (database indexes) ── independent
Task 13 (input validation + pagination) ── after Task 8
Task 14 (soft deletes) ── after Task 4
Task 15 (missing endpoints) ── after Task 13
Task 16 (Celery config + periodic tasks) ── after Tasks 7, 10
Task 17 (health endpoints) ── independent
```

---

## Phase 1: Critical Issues

### Task 1: Domain Exceptions

**Files:**
- Modify: `core/exceptions.py`
- Create: `core/tests/__init__.py` (if missing)
- Create: `core/tests/test_exceptions.py`

**Step 1: Write the failing test**

Create `core/tests/test_exceptions.py`:

```python
from django.test import TestCase
from core.exceptions import (
    UBBError,
    StripeTransientError,
    StripePaymentError,
    StripeFatalError,
)


class StripeExceptionHierarchyTest(TestCase):
    def test_transient_error_is_ubb_error(self):
        err = StripeTransientError("rate limited")
        self.assertIsInstance(err, UBBError)

    def test_payment_error_is_ubb_error(self):
        err = StripePaymentError("card declined", code="card_declined", decline_code="insufficient_funds")
        self.assertIsInstance(err, UBBError)
        self.assertEqual(err.code, "card_declined")
        self.assertEqual(err.decline_code, "insufficient_funds")

    def test_fatal_error_is_ubb_error(self):
        err = StripeFatalError("invalid api key")
        self.assertIsInstance(err, UBBError)

    def test_transient_error_message(self):
        err = StripeTransientError("network timeout")
        self.assertEqual(str(err), "network timeout")

    def test_payment_error_defaults(self):
        err = StripePaymentError("declined")
        self.assertIsNone(err.code)
        self.assertIsNone(err.decline_code)
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/ashtoncochrane/Git/localscouta/ubb-platform && python manage.py test core.tests.test_exceptions -v2`

Expected: `ImportError` — classes don't exist yet.

**Step 3: Write minimal implementation**

Modify `core/exceptions.py` — add after existing classes:

```python
class StripeTransientError(UBBError):
    """Retryable Stripe errors (network, rate limit, server 5xx)."""
    pass


class StripePaymentError(UBBError):
    """Non-retryable payment errors (card declined, insufficient funds)."""
    def __init__(self, message, code=None, decline_code=None):
        super().__init__(message)
        self.code = code
        self.decline_code = decline_code


class StripeFatalError(UBBError):
    """Non-retryable fatal errors (auth, config, idempotency mismatch)."""
    pass
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/ashtoncochrane/Git/localscouta/ubb-platform && python manage.py test core.tests.test_exceptions -v2`

Expected: All 5 tests PASS.

**Step 5: Commit**

```bash
cd /Users/ashtoncochrane/Git/localscouta/ubb-platform
git add core/exceptions.py core/tests/
git commit -m "feat: add Stripe domain exception hierarchy (transient, payment, fatal)"
```

---

### Task 2: Lock Ordering Helpers

**Files:**
- Create: `core/locking.py`
- Create: `core/tests/test_locking.py`

**Step 1: Write the failing test**

Create `core/tests/test_locking.py`:

```python
from django.test import TestCase
from apps.tenants.models import Tenant
from apps.customers.models import Customer, Wallet
from core.locking import lock_for_billing, lock_customer


class LockForBillingTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Test Tenant",
            stripe_connected_account_id="acct_test",
        )
        self.customer = Customer.objects.create(
            tenant=self.tenant,
            external_id="cust_1",
            email="test@test.com",
        )

    def test_lock_for_billing_returns_wallet_and_customer(self):
        from django.db import transaction
        with transaction.atomic():
            wallet, customer = lock_for_billing(self.customer.id)
            self.assertIsInstance(wallet, Wallet)
            self.assertIsInstance(customer, Customer)
            self.assertEqual(wallet.customer_id, self.customer.id)
            self.assertEqual(customer.id, self.customer.id)

    def test_lock_customer_returns_customer(self):
        from django.db import transaction
        with transaction.atomic():
            customer = lock_customer(self.customer.id)
            self.assertIsInstance(customer, Customer)
            self.assertEqual(customer.id, self.customer.id)

    def test_lock_for_billing_nonexistent_raises(self):
        import uuid
        from django.db import transaction
        from apps.customers.models import Wallet
        with self.assertRaises(Wallet.DoesNotExist):
            with transaction.atomic():
                lock_for_billing(uuid.uuid4())
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/ashtoncochrane/Git/localscouta/ubb-platform && python manage.py test core.tests.test_locking -v2`

Expected: `ImportError` — `core.locking` doesn't exist.

**Step 3: Write minimal implementation**

Create `core/locking.py`:

```python
"""
Canonical lock ordering helpers for billing operations.

Lock order: Wallet -> Customer -> TopUpAttempt -> Invoice

INVARIANT: No code path may acquire locks in a different order.
All code that needs multiple locks MUST use these helpers.
Do not call select_for_update() directly on these models.
"""

from apps.customers.models import Customer, Wallet


def lock_for_billing(customer_id):
    """
    Acquire Wallet -> Customer locks in canonical order.

    Use for: usage recording, wallet credits/debits, suspension checks.
    MUST be called within @transaction.atomic.
    """
    wallet = Wallet.objects.select_for_update().get(customer_id=customer_id)
    customer = Customer.objects.select_for_update().get(id=customer_id)
    return wallet, customer


def lock_customer(customer_id):
    """
    Acquire Customer lock only.

    Use for: status changes without wallet mutation (e.g., webhook suspension).
    MUST be called within @transaction.atomic.
    """
    return Customer.objects.select_for_update().get(id=customer_id)
```

Note: `lock_top_up_attempt` and `lock_invoice` will be added when those models are updated in later tasks.

**Step 4: Run test to verify it passes**

Run: `cd /Users/ashtoncochrane/Git/localscouta/ubb-platform && python manage.py test core.tests.test_locking -v2`

Expected: All 3 tests PASS.

**Step 5: Commit**

```bash
cd /Users/ashtoncochrane/Git/localscouta/ubb-platform
git add core/locking.py core/tests/test_locking.py
git commit -m "feat: add canonical lock ordering helpers for billing operations"
```

---

### Task 3: Logging Infrastructure

**Files:**
- Create: `core/logging.py`
- Create: `core/middleware.py`
- Modify: `config/settings.py` (add LOGGING, add middleware)
- Modify: `config/celery.py` (add correlation ID propagation)
- Create: `core/tests/test_logging.py`

**Step 1: Write the failing tests**

Create `core/tests/test_logging.py`:

```python
import json
import logging
import re
import uuid

from django.test import TestCase, RequestFactory
from core.logging import (
    correlation_id_var,
    CorrelationIdFilter,
    RedactingFilter,
    JsonFormatter,
    STANDARD_LOG_KEYS,
)


class CorrelationIdVarTest(TestCase):
    def test_default_is_empty_string(self):
        token = correlation_id_var.set("")
        self.assertEqual(correlation_id_var.get(), "")
        correlation_id_var.reset(token)

    def test_set_and_get(self):
        test_id = str(uuid.uuid4())
        token = correlation_id_var.set(test_id)
        self.assertEqual(correlation_id_var.get(), test_id)
        correlation_id_var.reset(token)


class RedactingFilterTest(TestCase):
    def setUp(self):
        self.filter = RedactingFilter()

    def test_redacts_email_key_in_data(self):
        record = logging.LogRecord("test", logging.INFO, "", 0, "msg", (), None)
        record.data = {"email": "user@example.com", "amount": 100}
        self.filter.filter(record)
        self.assertEqual(record.data["email"], "***REDACTED***")
        self.assertEqual(record.data["amount"], 100)

    def test_redacts_key_substrings(self):
        record = logging.LogRecord("test", logging.INFO, "", 0, "msg", (), None)
        record.data = {"stripe_api_key": "sk_live_xxx", "status": "ok"}
        self.filter.filter(record)
        self.assertEqual(record.data["stripe_api_key"], "***REDACTED***")
        self.assertEqual(record.data["status"], "ok")

    def test_redacts_email_in_message(self):
        record = logging.LogRecord(
            "test", logging.INFO, "", 0, "user %s logged in", ("test@example.com",), None
        )
        self.filter.filter(record)
        self.assertNotIn("test@example.com", record.msg)
        self.assertIn("***@REDACTED***", record.msg)

    def test_does_not_redact_stripe_customer_id(self):
        record = logging.LogRecord("test", logging.INFO, "", 0, "msg", (), None)
        record.data = {"stripe_customer_id": "cus_abc123"}
        self.filter.filter(record)
        self.assertEqual(record.data["stripe_customer_id"], "cus_abc123")

    def test_standard_log_keys_is_frozenset(self):
        self.assertIsInstance(STANDARD_LOG_KEYS, frozenset)


class JsonFormatterTest(TestCase):
    def test_formats_as_json(self):
        formatter = JsonFormatter()
        record = logging.LogRecord("test", logging.INFO, "", 0, "hello", (), None)
        output = formatter.format(record)
        parsed = json.loads(output)
        self.assertEqual(parsed["message"], "hello")
        self.assertEqual(parsed["level"], "INFO")
        self.assertIn("timestamp", parsed)
        self.assertIn("correlation_id", parsed)

    def test_safe_serialize_handles_non_serializable(self):
        formatter = JsonFormatter()
        record = logging.LogRecord("test", logging.INFO, "", 0, "msg", (), None)
        record.data = {"obj": object()}
        output = formatter.format(record)
        parsed = json.loads(output)
        self.assertIn("data", parsed)
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/ashtoncochrane/Git/localscouta/ubb-platform && python manage.py test core.tests.test_logging -v2`

Expected: `ImportError` — `core.logging` doesn't exist.

**Step 3: Write implementation**

Create `core/logging.py`:

```python
"""
Structured logging with correlation IDs and PII redaction.

Convention: All logging calls use extra={"data": {...}} for structured payloads.
The RedactingFilter scans this payload and all non-standard record attributes.

RedactingFilter MUST be last in the filter chain because it sets record.args = None.
"""

import contextvars
import json
import logging
import re

correlation_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "correlation_id", default=""
)

REDACT_KEYS = {
    "email", "phone", "name", "payment_method", "card",
    "ip_address", "address",
}

REDACT_KEY_SUBSTRINGS = {
    "secret", "token", "api_key", "authorization", "password", "credential",
}

STANDARD_LOG_KEYS = frozenset(
    logging.LogRecord("", 0, "", 0, "", (), None).__dict__.keys()
)

EMAIL_PATTERN = re.compile(r"[\w.-]+@[\w.-]+\.\w+")


def _should_redact_key(key):
    key_lower = key.lower()
    if key_lower in REDACT_KEYS:
        return True
    return any(sub in key_lower for sub in REDACT_KEY_SUBSTRINGS)


def _redact(obj):
    if isinstance(obj, dict):
        return {
            k: "***REDACTED***" if _should_redact_key(k) else _redact(v)
            for k, v in obj.items()
        }
    if isinstance(obj, (list, tuple)):
        return type(obj)(_redact(v) for v in obj)
    if isinstance(obj, str):
        return _redact_string(obj)
    return obj


def _redact_string(msg):
    return EMAIL_PATTERN.sub("***@REDACTED***", str(msg))


class CorrelationIdFilter(logging.Filter):
    """Injects correlation_id into log records."""

    def filter(self, record):
        record.correlation_id = correlation_id_var.get("")
        return True


class RedactingFilter(logging.Filter):
    """
    Redacts PII from log records. MUST be last in filter chain.

    Scans:
    1. record.data (standardized extra payload)
    2. Non-standard extras on the record
    3. Formatted message (resolves record.args, catches PII from %s formatting)

    Sets record.args = None after resolving — non-JSON handlers downstream
    won't get %-style formatting.
    """

    def filter(self, record):
        # 1. Redact standardized data payload
        if hasattr(record, "data") and isinstance(record.data, dict):
            record.data = _redact(record.data)

        # 2. Redact non-standard extras
        for key in set(record.__dict__.keys()) - STANDARD_LOG_KEYS - {"data", "correlation_id"}:
            val = getattr(record, key)
            if isinstance(val, dict):
                setattr(record, key, _redact(val))

        # 3. Redact formatted message (catches PII from args)
        record.msg = _redact_string(record.getMessage())
        record.args = None

        return True


class JsonFormatter(logging.Formatter):
    """JSON log formatter with safe serialization and PII-redacted exceptions."""

    def format(self, record):
        log_entry = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "correlation_id": getattr(record, "correlation_id", ""),
            "message": record.msg if isinstance(record.msg, str) else str(record.msg),
        }
        if hasattr(record, "data") and record.data:
            log_entry["data"] = self._safe_serialize(record.data)
        if record.exc_info:
            log_entry["exception"] = _redact_string(
                self.formatException(record.exc_info)
            )
        return json.dumps(log_entry, default=str)

    def _safe_serialize(self, obj):
        if isinstance(obj, dict):
            return {k: self._safe_serialize(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [self._safe_serialize(v) for v in obj]
        try:
            json.dumps(obj)
            return obj
        except (TypeError, ValueError):
            return str(obj)
```

Create `core/middleware.py`:

```python
"""
Correlation ID middleware for request tracing.

Reads X-Correlation-ID from incoming requests, validates as UUID format,
generates fresh UUID if missing/invalid, and sets it on the response.
"""

import uuid
import re

from core.logging import correlation_id_var

UUID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


class CorrelationIdMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        incoming_id = request.META.get("HTTP_X_CORRELATION_ID", "")
        if incoming_id and UUID_PATTERN.match(incoming_id) and len(incoming_id) <= 36:
            cid = incoming_id
        else:
            cid = str(uuid.uuid4())

        token = correlation_id_var.set(cid)
        try:
            response = self.get_response(request)
            response["X-Correlation-ID"] = cid
            return response
        finally:
            correlation_id_var.reset(token)
```

**Step 4: Modify `config/settings.py`**

Add CorrelationIdMiddleware to MIDDLEWARE (after SecurityMiddleware):

```python
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "core.middleware.CorrelationIdMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    # ... rest unchanged
]
```

Add LOGGING dict at the end of settings.py (before Stripe section):

```python
# Logging
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "correlation_id": {"()": "core.logging.CorrelationIdFilter"},
        "redacting": {"()": "core.logging.RedactingFilter"},
    },
    "formatters": {
        "json": {"()": "core.logging.JsonFormatter"},
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json",
            "filters": ["correlation_id", "redacting"],
        },
    },
    "loggers": {
        "apps": {"level": "INFO", "handlers": ["console"], "propagate": False},
        "core": {"level": "INFO", "handlers": ["console"], "propagate": False},
        "api": {"level": "INFO", "handlers": ["console"], "propagate": False},
        "django.request": {"level": "WARNING", "handlers": ["console"], "propagate": False},
        "stripe": {"level": "WARNING", "handlers": ["console"], "propagate": False},
        "celery": {"level": "INFO", "handlers": ["console"], "propagate": False},
    },
    "root": {"level": "WARNING", "handlers": ["console"]},
}
```

**Step 5: Modify `config/celery.py`**

Add correlation ID propagation signals:

```python
import os
import uuid

from celery import Celery
from celery.signals import before_task_publish, task_prerun

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

app = Celery('ubb_platform')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()


@before_task_publish.connect
def propagate_correlation_id(headers=None, **kwargs):
    if headers is None:
        return
    from core.logging import correlation_id_var
    cid = correlation_id_var.get("")
    if cid:
        headers["correlation_id"] = cid


@task_prerun.connect
def restore_correlation_id(task=None, **kwargs):
    from core.logging import correlation_id_var
    cid = getattr(task.request, "correlation_id", None)
    if not cid:
        # Periodic tasks or retries without header — generate fresh ID
        cid = str(uuid.uuid4())
    correlation_id_var.set(cid)
```

**Step 6: Run tests**

Run: `cd /Users/ashtoncochrane/Git/localscouta/ubb-platform && python manage.py test core.tests.test_logging -v2`

Expected: All tests PASS.

**Step 7: Commit**

```bash
cd /Users/ashtoncochrane/Git/localscouta/ubb-platform
git add core/logging.py core/middleware.py core/tests/test_logging.py config/settings.py config/celery.py
git commit -m "feat: add structured logging with correlation IDs and PII redaction"
```

---

### Task 4: TopUpAttempt Model + BillingPeriod Changes

**Files:**
- Modify: `apps/customers/models.py` (add TopUpAttempt)
- Modify: `apps/usage/models.py` (add invoice_attempt_number to BillingPeriod)
- Modify: `core/locking.py` (add lock_top_up_attempt, lock_invoice)
- Create: `apps/customers/tests/test_top_up_attempt.py`
- Run migrations

**Step 1: Write the failing test**

Create `apps/customers/tests/test_top_up_attempt.py`:

```python
from django.test import TestCase
from django.db import IntegrityError, transaction
from apps.tenants.models import Tenant
from apps.customers.models import Customer, TopUpAttempt


class TopUpAttemptModelTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Test", stripe_connected_account_id="acct_test"
        )
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="c1", email="t@t.com"
        )

    def test_create_pending_attempt(self):
        attempt = TopUpAttempt.objects.create(
            customer=self.customer,
            amount_micros=20_000_000,
            trigger="auto_topup",
            status="pending",
        )
        self.assertEqual(attempt.status, "pending")
        self.assertEqual(attempt.amount_micros, 20_000_000)
        self.assertIsNone(attempt.stripe_payment_intent_id)
        self.assertIsNone(attempt.failure_reason)

    def test_unique_pending_auto_topup_per_customer(self):
        TopUpAttempt.objects.create(
            customer=self.customer,
            amount_micros=20_000_000,
            trigger="auto_topup",
            status="pending",
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                TopUpAttempt.objects.create(
                    customer=self.customer,
                    amount_micros=10_000_000,
                    trigger="auto_topup",
                    status="pending",
                )

    def test_multiple_manual_pending_allowed(self):
        TopUpAttempt.objects.create(
            customer=self.customer,
            amount_micros=20_000_000,
            trigger="manual",
            status="pending",
        )
        attempt2 = TopUpAttempt.objects.create(
            customer=self.customer,
            amount_micros=30_000_000,
            trigger="manual",
            status="pending",
        )
        self.assertEqual(attempt2.trigger, "manual")

    def test_pending_auto_topup_allowed_after_previous_succeeded(self):
        attempt1 = TopUpAttempt.objects.create(
            customer=self.customer,
            amount_micros=20_000_000,
            trigger="auto_topup",
            status="pending",
        )
        attempt1.status = "succeeded"
        attempt1.save()
        attempt2 = TopUpAttempt.objects.create(
            customer=self.customer,
            amount_micros=20_000_000,
            trigger="auto_topup",
            status="pending",
        )
        self.assertEqual(attempt2.status, "pending")

    def test_expired_status(self):
        attempt = TopUpAttempt.objects.create(
            customer=self.customer,
            amount_micros=20_000_000,
            trigger="auto_topup",
            status="pending",
        )
        attempt.status = "expired"
        attempt.save()
        self.assertEqual(attempt.status, "expired")
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/ashtoncochrane/Git/localscouta/ubb-platform && python manage.py test apps.customers.tests.test_top_up_attempt -v2`

Expected: `ImportError` — `TopUpAttempt` doesn't exist.

**Step 3: Write implementation**

Add to `apps/customers/models.py` after `AutoTopUpConfig`:

```python
TOP_UP_ATTEMPT_TRIGGERS = [
    ("manual", "Manual"),
    ("auto_topup", "Auto Top-Up"),
]

TOP_UP_ATTEMPT_STATUSES = [
    ("pending", "Pending"),
    ("succeeded", "Succeeded"),
    ("failed", "Failed"),
    ("expired", "Expired"),
]


class TopUpAttempt(BaseModel):
    """
    Persisted charge attempt — created before calling Stripe.
    Provides deterministic idempotency keys for Stripe API calls.
    """
    customer = models.ForeignKey(
        Customer, on_delete=models.CASCADE, related_name="top_up_attempts"
    )
    amount_micros = models.PositiveBigIntegerField()
    trigger = models.CharField(max_length=20, choices=TOP_UP_ATTEMPT_TRIGGERS)
    status = models.CharField(
        max_length=20, choices=TOP_UP_ATTEMPT_STATUSES, default="pending", db_index=True
    )
    stripe_payment_intent_id = models.CharField(max_length=255, blank=True, null=True)
    stripe_checkout_session_id = models.CharField(max_length=255, blank=True, null=True)
    failure_reason = models.JSONField(null=True, blank=True)

    class Meta:
        db_table = "ubb_top_up_attempt"
        constraints = [
            models.UniqueConstraint(
                fields=["customer"],
                condition=models.Q(status="pending", trigger="auto_topup"),
                name="uq_one_pending_auto_topup_per_customer",
            ),
        ]

    def __str__(self):
        return f"TopUpAttempt({self.customer.external_id}: {self.trigger} {self.status})"
```

Add `invoice_attempt_number` to `BillingPeriod` in `apps/usage/models.py`:

```python
# Add this field to BillingPeriod class (after event_count):
    invoice_attempt_number = models.PositiveIntegerField(default=0)
```

Add lock helpers to `core/locking.py`:

```python
from apps.usage.models import Invoice


def lock_top_up_attempt(attempt_id):
    """
    Acquire TopUpAttempt lock.

    Use for: status transitions after Stripe calls.
    MUST be called within @transaction.atomic.
    """
    from apps.customers.models import TopUpAttempt
    return TopUpAttempt.objects.select_for_update().get(id=attempt_id)


def lock_invoice(invoice_id):
    """
    Acquire Invoice lock.

    Use for: status transitions from webhooks.
    MUST be called within @transaction.atomic.
    """
    return Invoice.objects.select_for_update().get(id=invoice_id)
```

**Step 4: Make and run migrations**

```bash
cd /Users/ashtoncochrane/Git/localscouta/ubb-platform
python manage.py makemigrations customers usage
python manage.py migrate
```

**Step 5: Run tests**

Run: `cd /Users/ashtoncochrane/Git/localscouta/ubb-platform && python manage.py test apps.customers.tests.test_top_up_attempt -v2`

Expected: All 5 tests PASS.

**Step 6: Commit**

```bash
cd /Users/ashtoncochrane/Git/localscouta/ubb-platform
git add apps/customers/models.py apps/customers/migrations/ apps/customers/tests/test_top_up_attempt.py
git add apps/usage/models.py apps/usage/migrations/
git add core/locking.py
git commit -m "feat: add TopUpAttempt model with pending constraint and invoice attempt counter"
```

---

### Task 5: Stripe Service Rewrite

**Files:**
- Modify: `apps/stripe_integration/services/stripe_service.py` (full rewrite)
- Modify: `apps/stripe_integration/apps.py` (add AppConfig.ready validation)
- Modify: `apps/stripe_integration/tests/test_stripe_service.py` (update tests)

**Step 1: Write the failing tests**

Replace `apps/stripe_integration/tests/test_stripe_service.py`:

```python
import stripe
from unittest.mock import patch, MagicMock
from django.test import TestCase, override_settings
from core.exceptions import StripeTransientError, StripePaymentError, StripeFatalError
from apps.stripe_integration.services.stripe_service import stripe_call


class StripeCallWrapperTest(TestCase):
    def test_successful_call(self):
        mock_fn = MagicMock(return_value="result")
        result = stripe_call(mock_fn, arg1="val1")
        self.assertEqual(result, "result")
        mock_fn.assert_called_once_with(arg1="val1")

    def test_rate_limit_raises_transient(self):
        mock_fn = MagicMock(side_effect=stripe.error.RateLimitError("rate limited"))
        with self.assertRaises(StripeTransientError):
            stripe_call(mock_fn, retryable=False)

    def test_card_error_raises_payment_error(self):
        err = stripe.error.CardError("declined", "param", "card_declined")
        mock_fn = MagicMock(side_effect=err)
        with self.assertRaises(StripePaymentError):
            stripe_call(mock_fn)

    def test_auth_error_raises_fatal(self):
        mock_fn = MagicMock(side_effect=stripe.error.AuthenticationError("bad key"))
        with self.assertRaises(StripeFatalError):
            stripe_call(mock_fn)

    def test_idempotency_error_raises_fatal(self):
        mock_fn = MagicMock(side_effect=stripe.error.IdempotencyError("mismatch"))
        with self.assertRaises(StripeFatalError):
            stripe_call(mock_fn)

    def test_retryable_with_idempotency_key_retries(self):
        mock_fn = MagicMock(
            side_effect=[
                stripe.error.APIConnectionError("timeout"),
                "success",
            ]
        )
        result = stripe_call(mock_fn, retryable=True, idempotency_key="key-1", max_retries=2)
        self.assertEqual(result, "success")
        self.assertEqual(mock_fn.call_count, 2)

    def test_retryable_without_key_does_not_retry(self):
        mock_fn = MagicMock(side_effect=stripe.error.APIConnectionError("timeout"))
        with self.assertRaises(StripeTransientError):
            stripe_call(mock_fn, retryable=True, idempotency_key=None)
        self.assertEqual(mock_fn.call_count, 1)

    def test_amount_validation_rejects_zero(self):
        from apps.stripe_integration.services.stripe_service import validate_amount_micros
        with self.assertRaises(StripeFatalError):
            validate_amount_micros(0)

    def test_amount_validation_rejects_negative(self):
        from apps.stripe_integration.services.stripe_service import validate_amount_micros
        with self.assertRaises(StripeFatalError):
            validate_amount_micros(-100)

    def test_amount_validation_accepts_positive(self):
        from apps.stripe_integration.services.stripe_service import validate_amount_micros
        validate_amount_micros(1_000_000)  # should not raise
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/ashtoncochrane/Git/localscouta/ubb-platform && python manage.py test apps.stripe_integration.tests.test_stripe_service -v2`

Expected: `ImportError` — `stripe_call` doesn't exist.

**Step 3: Write implementation**

Rewrite `apps/stripe_integration/services/stripe_service.py`:

```python
import logging
import random
import time

import stripe
from django.conf import settings

from core.exceptions import StripeTransientError, StripePaymentError, StripeFatalError

stripe.api_key = settings.STRIPE_SECRET_KEY
logger = logging.getLogger(__name__)


def validate_amount_micros(amount_micros):
    """Validate amount_micros > 0. Raises StripeFatalError otherwise."""
    if amount_micros is None or amount_micros <= 0:
        raise StripeFatalError(f"amount_micros must be > 0, got {amount_micros}")


def stripe_call(fn, *, retryable=False, idempotency_key=None, max_retries=3, **kwargs):
    """
    Wrap a Stripe API call with error mapping and optional retry.

    - retryable=True + idempotency_key: retries with exponential backoff + jitter
    - retryable=True + no key: forced to non-retryable (safety)
    - Maps Stripe exceptions to domain exceptions
    """
    if retryable and not idempotency_key:
        retryable = False

    attempts = max_retries if retryable else 1

    for attempt in range(attempts):
        try:
            if idempotency_key:
                kwargs["idempotency_key"] = idempotency_key
            return fn(**kwargs)
        except stripe.error.RateLimitError as e:
            _log_stripe_error(fn, e, attempt)
            if attempt < attempts - 1:
                _backoff(attempt)
                continue
            raise StripeTransientError(str(e)) from e
        except stripe.error.APIConnectionError as e:
            _log_stripe_error(fn, e, attempt)
            if attempt < attempts - 1:
                _backoff(attempt)
                continue
            raise StripeTransientError(str(e)) from e
        except stripe.error.APIError as e:
            _log_stripe_error(fn, e, attempt)
            if attempt < attempts - 1:
                _backoff(attempt)
                continue
            raise StripeTransientError(str(e)) from e
        except stripe.error.CardError as e:
            _log_stripe_error(fn, e, attempt)
            raise StripePaymentError(
                str(e),
                code=getattr(e, "code", None),
                decline_code=getattr(e, "decline_code", None),
            ) from e
        except stripe.error.IdempotencyError as e:
            _log_stripe_error(fn, e, attempt)
            raise StripeFatalError(str(e)) from e
        except stripe.error.AuthenticationError as e:
            _log_stripe_error(fn, e, attempt)
            raise StripeFatalError(str(e)) from e
        except stripe.error.PermissionError as e:
            _log_stripe_error(fn, e, attempt)
            raise StripeFatalError(str(e)) from e
        except stripe.error.InvalidRequestError as e:
            _log_stripe_error(fn, e, attempt)
            raise StripeFatalError(str(e)) from e


def _backoff(attempt):
    """Exponential backoff with jitter: base 0.5s, factor 2x, +/-25% jitter."""
    base = 0.5 * (2 ** attempt)
    jitter = base * 0.25 * (2 * random.random() - 1)
    delay = min(base + jitter, 10.0)
    time.sleep(delay)


def _log_stripe_error(fn, error, attempt):
    logger.warning(
        "Stripe API error",
        extra={"data": {
            "function": getattr(fn, "__name__", str(fn)),
            "error_type": type(error).__name__,
            "error_code": getattr(error, "code", None),
            "attempt": attempt + 1,
        }},
    )


class StripeService:
    @staticmethod
    def create_customer(customer):
        """Create Stripe customer under tenant's connected account. Skip if already synced."""
        if customer.stripe_customer_id:
            return customer.stripe_customer_id
        stripe_customer = stripe_call(
            stripe.Customer.create,
            retryable=True,
            idempotency_key=f"create-customer-{customer.id}",
            email=customer.email,
            metadata={"ubb_customer_id": str(customer.id), "external_id": customer.external_id},
            stripe_account=customer.tenant.stripe_connected_account_id,
        )
        customer.stripe_customer_id = stripe_customer.id
        customer.save(update_fields=["stripe_customer_id", "updated_at"])
        return stripe_customer.id

    @staticmethod
    def create_checkout_session(customer, amount_micros, top_up_attempt):
        """Create Stripe Checkout session for top-up."""
        validate_amount_micros(amount_micros)
        amount_cents = amount_micros // 10_000
        session = stripe_call(
            stripe.checkout.Session.create,
            retryable=True,
            idempotency_key=f"checkout-{top_up_attempt.id}",
            customer=customer.stripe_customer_id,
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
            success_url=settings.UBB_TOPUP_SUCCESS_URL,
            cancel_url=settings.UBB_TOPUP_CANCEL_URL,
            stripe_account=customer.tenant.stripe_connected_account_id,
        )
        top_up_attempt.stripe_checkout_session_id = session.id
        top_up_attempt.save(update_fields=["stripe_checkout_session_id", "updated_at"])
        return session.url

    @staticmethod
    def credit_customer_invoice_balance(customer, amount_micros):
        """Credit prepaid funds to Stripe customer invoice balance."""
        validate_amount_micros(amount_micros)
        amount_cents = amount_micros // 10_000
        stripe_call(
            stripe.Customer.modify,
            retryable=True,
            idempotency_key=None,  # modify is naturally idempotent
            sid=customer.stripe_customer_id,
            balance=-amount_cents,
            stripe_account=customer.tenant.stripe_connected_account_id,
        )

    @staticmethod
    def create_invoice_with_line_items(customer, billing_period, usage_events):
        """
        Create Stripe invoice with itemized usage events.

        Idempotency:
        - Invoice: invoice-{billing_period.id}-v{attempt_number}
        - Items: invitem-{usage_event.id}-inv{stripe_invoice.id}
        - Void only on non-retryable failure, then increment attempt number.
        - Usage events marked invoiced only after finalize succeeds.
        """
        connected_account = customer.tenant.stripe_connected_account_id
        total_micros = sum(e.cost_micros for e in usage_events)
        attempt_num = billing_period.invoice_attempt_number

        if attempt_num >= 5:
            raise StripeFatalError(
                f"Invoice attempt cap reached for billing period {billing_period.id}. "
                "Manual intervention required."
            )

        invoice_idem_key = f"invoice-{billing_period.id}-v{attempt_num}"

        invoice = stripe_call(
            stripe.Invoice.create,
            retryable=True,
            idempotency_key=invoice_idem_key,
            customer=customer.stripe_customer_id,
            auto_advance=True,
            collection_method="charge_automatically",
            stripe_account=connected_account,
            application_fee_amount=StripeService._calculate_platform_fee(
                customer.tenant, total_micros
            ),
        )

        for event in usage_events:
            amount_cents = event.cost_micros // 10_000
            if amount_cents <= 0:
                continue
            item_idem_key = f"invitem-{event.id}-inv{invoice.id}"
            stripe_call(
                stripe.InvoiceItem.create,
                retryable=True,
                idempotency_key=item_idem_key,
                customer=customer.stripe_customer_id,
                invoice=invoice.id,
                amount=amount_cents,
                currency="usd",
                description=f"Usage: {event.request_id} ({event.metadata.get('model', 'api_call')})",
                stripe_account=connected_account,
            )

        try:
            finalized = stripe_call(
                stripe.Invoice.finalize_invoice,
                retryable=True,
                idempotency_key=f"finalize-{invoice.id}",
                invoice=invoice.id,
                stripe_account=connected_account,
            )
            return finalized.id
        except StripeFatalError:
            # Non-retryable finalize failure — void and increment attempt
            try:
                stripe_call(
                    stripe.Invoice.void_invoice,
                    retryable=False,
                    invoice=invoice.id,
                    stripe_account=connected_account,
                )
            except Exception:
                logger.exception("Failed to void invoice %s", invoice.id)
            billing_period.invoice_attempt_number += 1
            billing_period.save(update_fields=["invoice_attempt_number", "updated_at"])
            raise

    @staticmethod
    def _calculate_platform_fee(tenant, total_cost_micros):
        """Calculate platform application fee in cents."""
        fee_micros = int(total_cost_micros * float(tenant.platform_fee_percentage) / 100)
        return fee_micros // 10_000

    @staticmethod
    def charge_saved_payment_method(customer, amount_micros, top_up_attempt):
        """
        Charge saved payment method for top-up.

        Idempotency key derived from top_up_attempt.id — deterministic across retries.
        """
        validate_amount_micros(amount_micros)
        amount_cents = amount_micros // 10_000
        connected_account = customer.tenant.stripe_connected_account_id

        payment_methods = stripe_call(
            stripe.PaymentMethod.list,
            retryable=True,
            idempotency_key=None,  # list is naturally idempotent
            customer=customer.stripe_customer_id,
            type="card",
            stripe_account=connected_account,
        )
        if not payment_methods.data:
            return None

        intent = stripe_call(
            stripe.PaymentIntent.create,
            retryable=True,
            idempotency_key=f"charge-{top_up_attempt.id}",
            customer=customer.stripe_customer_id,
            amount=amount_cents,
            currency="usd",
            payment_method=payment_methods.data[0].id,
            off_session=True,
            confirm=True,
            stripe_account=connected_account,
        )
        return intent
```

**Step 4: Add AppConfig.ready validation**

Modify `apps/stripe_integration/apps.py`:

```python
from django.apps import AppConfig
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


class StripeIntegrationConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.stripe_integration"

    def ready(self):
        if not getattr(settings, "STRIPE_SECRET_KEY", ""):
            raise ImproperlyConfigured("STRIPE_SECRET_KEY must be set")
        if not getattr(settings, "STRIPE_WEBHOOK_SECRET", ""):
            raise ImproperlyConfigured("STRIPE_WEBHOOK_SECRET must be set")
```

Note: For test environments, set these in test settings or environment. The existing test setup likely mocks Stripe calls and may need `STRIPE_SECRET_KEY=test` and `STRIPE_WEBHOOK_SECRET=test` in the test environment.

**Step 5: Run tests**

Run: `cd /Users/ashtoncochrane/Git/localscouta/ubb-platform && python manage.py test apps.stripe_integration.tests.test_stripe_service -v2`

Expected: All tests PASS (may need to set env vars `STRIPE_SECRET_KEY=test STRIPE_WEBHOOK_SECRET=test`).

**Step 6: Commit**

```bash
cd /Users/ashtoncochrane/Git/localscouta/ubb-platform
git add apps/stripe_integration/
git commit -m "feat: rewrite StripeService with error handling, idempotency keys, and retry logic"
```

---

### Task 6: StripeWebhookEvent Model

**Files:**
- Create: `apps/stripe_integration/models.py`
- Create: `apps/stripe_integration/tests/test_webhook_event.py`
- Run migrations

**Step 1: Write the failing test**

Create `apps/stripe_integration/tests/test_webhook_event.py`:

```python
from django.test import TestCase
from django.db import IntegrityError, transaction
from django.utils import timezone
from apps.stripe_integration.models import StripeWebhookEvent


class StripeWebhookEventModelTest(TestCase):
    def test_create_event(self):
        event = StripeWebhookEvent.objects.create(
            stripe_event_id="evt_test_123",
            event_type="checkout.session.completed",
            status="processing",
        )
        self.assertEqual(event.stripe_event_id, "evt_test_123")
        self.assertEqual(event.status, "processing")
        self.assertEqual(event.duplicate_count, 0)
        self.assertIsNotNone(event.last_seen_at)

    def test_unique_stripe_event_id(self):
        StripeWebhookEvent.objects.create(
            stripe_event_id="evt_dup",
            event_type="invoice.paid",
            status="succeeded",
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                StripeWebhookEvent.objects.create(
                    stripe_event_id="evt_dup",
                    event_type="invoice.paid",
                    status="processing",
                )

    def test_failure_reason_json(self):
        event = StripeWebhookEvent.objects.create(
            stripe_event_id="evt_fail",
            event_type="invoice.paid",
            status="failed",
            failure_reason={"error": "test", "retryable": True},
        )
        event.refresh_from_db()
        self.assertTrue(event.failure_reason["retryable"])
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/ashtoncochrane/Git/localscouta/ubb-platform && python manage.py test apps.stripe_integration.tests.test_webhook_event -v2`

Expected: `ImportError`.

**Step 3: Write implementation**

Create `apps/stripe_integration/models.py`:

```python
from django.db import models
from django.utils import timezone

from core.models import BaseModel

WEBHOOK_EVENT_STATUSES = [
    ("processing", "Processing"),
    ("succeeded", "Succeeded"),
    ("failed", "Failed"),
    ("skipped", "Skipped"),
]


class StripeWebhookEvent(BaseModel):
    """
    Tracks Stripe webhook event processing for deduplication and auditing.

    Original outcome (succeeded/failed/skipped) is never overwritten by duplicates.
    Duplicate deliveries increment duplicate_count and update last_seen_at.
    """
    stripe_event_id = models.CharField(max_length=255, unique=True, db_index=True)
    event_type = models.CharField(max_length=255, db_index=True)
    status = models.CharField(max_length=20, choices=WEBHOOK_EVENT_STATUSES, default="processing")
    failure_reason = models.JSONField(null=True, blank=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    duplicate_count = models.PositiveIntegerField(default=0)
    last_seen_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "ubb_stripe_webhook_event"
        indexes = [
            models.Index(fields=["status", "created_at"], name="idx_webhook_status_created"),
            models.Index(fields=["created_at"], name="idx_webhook_created_at"),
        ]

    def __str__(self):
        return f"WebhookEvent({self.stripe_event_id}: {self.status})"
```

**Step 4: Make and run migrations**

```bash
cd /Users/ashtoncochrane/Git/localscouta/ubb-platform
python manage.py makemigrations stripe_integration
python manage.py migrate
```

**Step 5: Run tests**

Run: `cd /Users/ashtoncochrane/Git/localscouta/ubb-platform && python manage.py test apps.stripe_integration.tests.test_webhook_event -v2`

Expected: All 3 tests PASS.

**Step 6: Commit**

```bash
cd /Users/ashtoncochrane/Git/localscouta/ubb-platform
git add apps/stripe_integration/models.py apps/stripe_integration/migrations/ apps/stripe_integration/tests/test_webhook_event.py
git commit -m "feat: add StripeWebhookEvent model for webhook dedup and auditing"
```

---

### Task 7: Auto-Topup Service Rewrite

**Files:**
- Modify: `apps/usage/services/auto_topup_service.py`
- Create: `apps/usage/tasks.py` (Celery task)
- Update: `apps/usage/tests/test_auto_topup.py`

**Step 1: Write the failing tests**

Replace `apps/usage/tests/test_auto_topup.py`:

```python
from unittest.mock import patch, MagicMock
from django.test import TestCase
from django.db import transaction

from apps.tenants.models import Tenant
from apps.customers.models import Customer, AutoTopUpConfig, TopUpAttempt
from apps.usage.services.auto_topup_service import AutoTopUpService


class AutoTopUpServiceTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Test", stripe_connected_account_id="acct_test"
        )
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="c1", email="t@t.com"
        )
        self.wallet = self.customer.wallet
        self.wallet.balance_micros = -1_000_000  # below threshold
        self.wallet.save()
        AutoTopUpConfig.objects.create(
            customer=self.customer,
            is_enabled=True,
            trigger_threshold_micros=0,
            top_up_amount_micros=20_000_000,
        )

    def test_creates_pending_attempt(self):
        with transaction.atomic():
            attempt = AutoTopUpService.create_pending_attempt(self.customer, self.wallet)
        self.assertIsNotNone(attempt)
        self.assertEqual(attempt.status, "pending")
        self.assertEqual(attempt.trigger, "auto_topup")
        self.assertEqual(attempt.amount_micros, 20_000_000)

    def test_returns_none_if_pending_exists(self):
        TopUpAttempt.objects.create(
            customer=self.customer,
            amount_micros=20_000_000,
            trigger="auto_topup",
            status="pending",
        )
        with transaction.atomic():
            attempt = AutoTopUpService.create_pending_attempt(self.customer, self.wallet)
        self.assertIsNone(attempt)

    def test_returns_none_if_balance_above_threshold(self):
        self.wallet.balance_micros = 10_000_000  # above threshold
        self.wallet.save()
        with transaction.atomic():
            attempt = AutoTopUpService.create_pending_attempt(self.customer, self.wallet)
        self.assertIsNone(attempt)

    def test_returns_none_if_not_enabled(self):
        config = self.customer.auto_top_up_config
        config.is_enabled = False
        config.save()
        with transaction.atomic():
            attempt = AutoTopUpService.create_pending_attempt(self.customer, self.wallet)
        self.assertIsNone(attempt)

    def test_returns_none_if_no_config(self):
        self.customer.auto_top_up_config.delete()
        with transaction.atomic():
            attempt = AutoTopUpService.create_pending_attempt(self.customer, self.wallet)
        self.assertIsNone(attempt)
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/ashtoncochrane/Git/localscouta/ubb-platform && python manage.py test apps.usage.tests.test_auto_topup -v2`

Expected: `AttributeError` — `create_pending_attempt` doesn't exist.

**Step 3: Write implementation**

Rewrite `apps/usage/services/auto_topup_service.py`:

```python
import logging

from django.db import IntegrityError, transaction

from apps.customers.models import AutoTopUpConfig, TopUpAttempt

logger = logging.getLogger(__name__)


class AutoTopUpService:
    @staticmethod
    def create_pending_attempt(customer, wallet):
        """
        Check auto-topup eligibility and create a pending TopUpAttempt.

        MUST be called within @transaction.atomic with wallet already locked
        via lock_for_billing().

        Returns TopUpAttempt if created, None if skipped (not eligible or
        another pending attempt already exists).
        """
        try:
            config = customer.auto_top_up_config
        except AutoTopUpConfig.DoesNotExist:
            return None

        if not config.is_enabled:
            return None

        if wallet.balance_micros >= config.trigger_threshold_micros:
            return None

        logger.info(
            "Auto top-up triggered",
            extra={"data": {
                "customer_id": str(customer.id),
                "balance_micros": wallet.balance_micros,
                "threshold_micros": config.trigger_threshold_micros,
            }},
        )

        # Savepoint: IntegrityError must not abort the outer transaction
        try:
            with transaction.atomic():
                attempt = TopUpAttempt.objects.create(
                    customer=customer,
                    amount_micros=config.top_up_amount_micros,
                    trigger="auto_topup",
                    status="pending",
                )
            return attempt
        except IntegrityError:
            # Another pending auto-topup already exists
            logger.info(
                "Auto top-up skipped: pending attempt exists",
                extra={"data": {"customer_id": str(customer.id)}},
            )
            return None
```

Create `apps/usage/tasks.py`:

```python
import json
import logging

from celery import shared_task
from django.db import transaction

from core.exceptions import StripeTransientError, StripePaymentError, StripeFatalError
from core.locking import lock_for_billing, lock_top_up_attempt

logger = logging.getLogger(__name__)


@shared_task(
    queue="ubb_topups",
    autoretry_for=(StripeTransientError,),
    max_retries=3,
    retry_backoff=True,
    acks_late=True,
)
def charge_auto_topup_task(attempt_id):
    """
    Charge Stripe for an auto-topup attempt.

    Dispatched via transaction.on_commit after usage recording.
    Idempotent: checks attempt status before and after charging.
    """
    from apps.customers.models import TopUpAttempt
    from apps.stripe_integration.services.stripe_service import StripeService

    # Pre-charge check (outside transaction — no lock needed)
    try:
        attempt = TopUpAttempt.objects.get(id=attempt_id)
    except TopUpAttempt.DoesNotExist:
        logger.warning(
            "TopUpAttempt not found, skipping",
            extra={"data": {"attempt_id": str(attempt_id)}},
        )
        return

    if attempt.status != "pending":
        logger.info(
            "TopUpAttempt already processed, skipping",
            extra={"data": {"attempt_id": str(attempt_id), "status": attempt.status}},
        )
        return

    # Charge Stripe (outside transaction — no DB locks held)
    charge_result = None
    charge_error = None
    try:
        charge_result = StripeService.charge_saved_payment_method(
            attempt.customer, attempt.amount_micros, attempt
        )
    except (StripePaymentError, StripeFatalError) as e:
        charge_error = e
    # StripeTransientError propagates to Celery for autoretry

    # Post-charge update (atomic, with locks)
    with transaction.atomic():
        wallet, customer = lock_for_billing(attempt.customer_id)
        attempt = lock_top_up_attempt(attempt.id)

        if attempt.status != "pending":
            # Race: webhook or another worker already processed it
            return

        if charge_error:
            attempt.status = "failed"
            attempt.failure_reason = {
                "error_type": type(charge_error).__name__,
                "code": getattr(charge_error, "code", None),
                "decline_code": getattr(charge_error, "decline_code", None),
                "message": str(charge_error),
            }
            attempt.save(update_fields=["status", "failure_reason", "updated_at"])
            logger.warning(
                "Auto top-up charge failed",
                extra={"data": {
                    "attempt_id": str(attempt.id),
                    "customer_id": str(customer.id),
                    "error": attempt.failure_reason,
                }},
            )
            return

        if charge_result and getattr(charge_result, "status", "") == "succeeded":
            wallet.balance_micros += attempt.amount_micros
            wallet.save(update_fields=["balance_micros", "updated_at"])

            from apps.customers.models import WalletTransaction
            WalletTransaction.objects.create(
                wallet=wallet,
                transaction_type="TOP_UP",
                amount_micros=attempt.amount_micros,
                balance_after_micros=wallet.balance_micros,
                description="Auto top-up",
                reference_id=str(attempt.id),
            )

            attempt.status = "succeeded"
            attempt.stripe_payment_intent_id = charge_result.id
            attempt.save(update_fields=[
                "status", "stripe_payment_intent_id", "updated_at"
            ])

            logger.info(
                "Auto top-up succeeded",
                extra={"data": {
                    "attempt_id": str(attempt.id),
                    "customer_id": str(customer.id),
                    "amount_micros": attempt.amount_micros,
                }},
            )
        else:
            attempt.status = "failed"
            attempt.failure_reason = {
                "error_type": "NoPaymentMethod",
                "message": "No saved payment method or charge did not succeed",
            }
            attempt.save(update_fields=["status", "failure_reason", "updated_at"])
```

**Step 4: Run tests**

Run: `cd /Users/ashtoncochrane/Git/localscouta/ubb-platform && python manage.py test apps.usage.tests.test_auto_topup -v2`

Expected: All 5 tests PASS.

**Step 5: Commit**

```bash
cd /Users/ashtoncochrane/Git/localscouta/ubb-platform
git add apps/usage/services/auto_topup_service.py apps/usage/tasks.py apps/usage/tests/test_auto_topup.py
git commit -m "feat: rewrite auto-topup with pending attempt model and Celery charge task"
```

---

### Task 8: UsageService Rewrite

**Files:**
- Modify: `apps/usage/services/usage_service.py`
- Update: `apps/usage/tests/test_usage_service.py`

**Step 1: Write the failing tests**

Add to `apps/usage/tests/test_usage_service.py` (keep existing tests, add new ones):

```python
# Add these test methods to the existing test class or create new class:

from unittest.mock import patch
from django.test import TestCase
from apps.tenants.models import Tenant
from apps.customers.models import Customer, AutoTopUpConfig, TopUpAttempt
from apps.usage.services.usage_service import UsageService


class UsageServiceLockingTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Test", stripe_connected_account_id="acct_test"
        )
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="c1", email="t@t.com"
        )
        # Credit wallet so we can deduct
        self.customer.wallet.balance_micros = 100_000_000
        self.customer.wallet.save()

    def test_record_usage_deducts_wallet(self):
        result = UsageService.record_usage(
            tenant=self.tenant,
            customer=self.customer,
            request_id="req_1",
            idempotency_key="idem_1",
            cost_micros=1_000_000,
        )
        self.assertEqual(result["new_balance_micros"], 99_000_000)
        self.assertFalse(result["suspended"])

    def test_record_usage_suspends_on_threshold(self):
        self.customer.wallet.balance_micros = 0
        self.customer.wallet.save()
        result = UsageService.record_usage(
            tenant=self.tenant,
            customer=self.customer,
            request_id="req_2",
            idempotency_key="idem_2",
            cost_micros=10_000_000,  # pushes past threshold
        )
        self.assertTrue(result["suspended"])
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.status, "suspended")

    @patch("apps.usage.tasks.charge_auto_topup_task.delay")
    def test_auto_topup_dispatched_on_commit(self, mock_delay):
        self.customer.wallet.balance_micros = 0
        self.customer.wallet.save()
        AutoTopUpConfig.objects.create(
            customer=self.customer,
            is_enabled=True,
            trigger_threshold_micros=5_000_000,
            top_up_amount_micros=20_000_000,
        )
        UsageService.record_usage(
            tenant=self.tenant,
            customer=self.customer,
            request_id="req_3",
            idempotency_key="idem_3",
            cost_micros=1_000_000,
        )
        # on_commit fires after the test transaction
        # In TestCase, on_commit doesn't fire. Use TransactionTestCase for full test.
        # Here we just verify the attempt was created.
        attempt = TopUpAttempt.objects.filter(
            customer=self.customer, trigger="auto_topup", status="pending"
        ).first()
        self.assertIsNotNone(attempt)
```

**Step 2: Write implementation**

Rewrite `apps/usage/services/usage_service.py`:

```python
import logging

from django.db import transaction, IntegrityError

from apps.usage.models import UsageEvent
from apps.customers.models import Wallet, WalletTransaction
from core.locking import lock_for_billing

logger = logging.getLogger(__name__)


class UsageService:
    @staticmethod
    @transaction.atomic
    def record_usage(tenant, customer, request_id, idempotency_key, cost_micros, metadata=None):
        # 1. Idempotency check — fast path before locking
        existing = UsageEvent.objects.filter(
            tenant=tenant, idempotency_key=idempotency_key
        ).first()
        if existing:
            wallet = Wallet.objects.get(customer=customer)
            return {
                "event_id": str(existing.id),
                "new_balance_micros": wallet.balance_micros,
                "suspended": customer.status == "suspended",
            }

        # 2. Lock wallet + customer in canonical order
        wallet, customer = lock_for_billing(customer.id)

        # 3. Create event (handle race via IntegrityError)
        try:
            event = UsageEvent.objects.create(
                tenant=tenant,
                customer=customer,
                request_id=request_id,
                idempotency_key=idempotency_key,
                cost_micros=cost_micros,
                metadata=metadata or {},
            )
        except IntegrityError:
            existing = UsageEvent.objects.get(tenant=tenant, idempotency_key=idempotency_key)
            return {
                "event_id": str(existing.id),
                "new_balance_micros": wallet.balance_micros,
                "suspended": customer.status == "suspended",
            }

        # 4. Deduct wallet (already locked via select_for_update)
        wallet.balance_micros -= cost_micros
        wallet.save(update_fields=["balance_micros", "updated_at"])

        WalletTransaction.objects.create(
            wallet=wallet,
            transaction_type="USAGE_DEDUCTION",
            amount_micros=-cost_micros,
            balance_after_micros=wallet.balance_micros,
            description=f"Usage: {request_id}",
            reference_id=str(event.id),
        )

        # 5. Check arrears threshold — customer already locked
        suspended = False
        threshold = customer.get_arrears_threshold()
        if wallet.balance_micros < -threshold:
            customer.status = "suspended"
            customer.save(update_fields=["status", "updated_at"])
            suspended = True

        # 6. Auto top-up check — creates pending attempt if eligible
        attempt = None
        from apps.usage.services.auto_topup_service import AutoTopUpService
        try:
            attempt = AutoTopUpService.create_pending_attempt(customer, wallet)
        except Exception:
            logger.exception(
                "Auto top-up check failed",
                extra={"data": {"customer_id": str(customer.id)}},
            )

        # 7. Dispatch charge task after commit
        if attempt is not None:
            from apps.usage.tasks import charge_auto_topup_task
            transaction.on_commit(
                lambda aid=attempt.id: charge_auto_topup_task.delay(aid)
            )

        return {
            "event_id": str(event.id),
            "new_balance_micros": wallet.balance_micros,
            "suspended": suspended,
        }
```

**Step 3: Run tests**

Run: `cd /Users/ashtoncochrane/Git/localscouta/ubb-platform && python manage.py test apps.usage.tests -v2`

Expected: All usage tests PASS.

**Step 4: Commit**

```bash
cd /Users/ashtoncochrane/Git/localscouta/ubb-platform
git add apps/usage/services/usage_service.py apps/usage/tests/test_usage_service.py
git commit -m "feat: rewrite UsageService with lock ordering and auto-topup dispatch via on_commit"
```

---

### Task 9: Invoicing Task Rewrite

**Files:**
- Modify: `apps/invoicing/tasks.py`
- Update: `apps/invoicing/tests/test_tasks.py`

This task updates `_invoice_period` to use `invoice_attempt_number` and handle the cap. The `StripeService.create_invoice_with_line_items` already handles idempotency keys internally (from Task 5). Usage events are only linked to the invoice after successful finalization.

**Step 1: Update `apps/invoicing/tasks.py`**

The current code already uses `select_for_update` on BillingPeriod and creates the invoice in a transaction. Update to:
- Use `invoice_attempt_number` from `BillingPeriod` (already added in Task 4)
- Only link usage events after Stripe finalize succeeds (already the design — `update(invoice=invoice)` is last)
- Add `acks_late=True` for financial safety

The existing implementation is mostly correct. The key change is that `StripeService.create_invoice_with_line_items` now handles idempotency internally. Add error handling for `StripeFatalError`:

```python
import logging

from django.utils import timezone
from django.db import transaction
from celery import shared_task

from apps.usage.models import BillingPeriod, UsageEvent, Invoice
from apps.stripe_integration.services.stripe_service import StripeService
from core.exceptions import StripeFatalError

logger = logging.getLogger(__name__)


@shared_task(queue="ubb_invoicing", acks_late=True)
def generate_weekly_invoices():
    """Find all open billing periods that have ended and generate invoices."""
    now = timezone.now()
    periods = BillingPeriod.objects.filter(
        status="open", period_end__lte=now
    ).select_related("customer", "tenant")
    for period in periods:
        try:
            _invoice_period(period)
        except StripeFatalError:
            logger.exception(
                "Fatal Stripe error invoicing period, requires manual intervention",
                extra={"data": {"period_id": str(period.id)}},
            )
        except Exception:
            logger.exception(
                "Failed to invoice period",
                extra={"data": {"period_id": str(period.id)}},
            )


@transaction.atomic
def _invoice_period(period):
    period = BillingPeriod.objects.select_for_update().get(pk=period.pk)
    if period.status != "open":
        return

    customer = period.customer
    events = list(UsageEvent.objects.filter(
        customer=customer,
        tenant=period.tenant,
        effective_at__gte=period.period_start,
        effective_at__lt=period.period_end,
        invoice__isnull=True,
    ))

    if not events:
        period.status = "closed"
        period.save(update_fields=["status", "updated_at"])
        return

    total_micros = sum(e.cost_micros for e in events)

    # StripeService handles idempotency keys and attempt counting internally
    stripe_invoice_id = StripeService.create_invoice_with_line_items(
        customer=customer,
        billing_period=period,
        usage_events=events,
    )

    invoice = Invoice.objects.create(
        tenant=period.tenant,
        customer=customer,
        billing_period=period,
        stripe_invoice_id=stripe_invoice_id,
        total_amount_micros=total_micros,
        status="finalized",
        finalized_at=timezone.now(),
    )

    # Link usage events ONLY after finalize succeeded
    UsageEvent.objects.filter(id__in=[e.id for e in events]).update(invoice=invoice)

    period.status = "invoiced"
    period.total_cost_micros = total_micros
    period.event_count = len(events)
    period.save(update_fields=["status", "total_cost_micros", "event_count", "updated_at"])
```

**Step 2: Run tests**

Run: `cd /Users/ashtoncochrane/Git/localscouta/ubb-platform && python manage.py test apps.invoicing.tests -v2`

Expected: Tests PASS.

**Step 3: Commit**

```bash
cd /Users/ashtoncochrane/Git/localscouta/ubb-platform
git add apps/invoicing/tasks.py apps/invoicing/tests/
git commit -m "feat: update invoicing with acks_late and StripeFatalError handling"
```

---

### Task 10: Webhooks Rewrite

**Files:**
- Modify: `api/v1/webhooks.py` (full rewrite)
- Update: `api/v1/tests/test_webhooks.py`

**Step 1: Write implementation**

Rewrite `api/v1/webhooks.py` per the design document section 3.2 (v4). This is a large rewrite — the full dispatcher with CAS, event dedup, error classification, and handler-level idempotency.

See design document section 3.2 for the complete code. Key additions:
- `StripeWebhookEvent` dedup via `get_or_create` + `IntegrityError` handling
- CAS for retryable failures and stale processing (30min TTL)
- `ObjectDoesNotExist` returns 500 (retryable)
- `StripeFatalError` returns 200 (non-retryable)
- Handler-level status checks before mutating
- All handlers use `lock_for_billing` / `lock_customer` / `lock_invoice` as appropriate

**Step 2: Update tests**

Update `api/v1/tests/test_webhooks.py` to test:
- Event dedup (same event ID processed twice)
- Handler failure returns 500
- Fatal error returns 200
- Signature verification failure returns 400

**Step 3: Run tests**

Run: `cd /Users/ashtoncochrane/Git/localscouta/ubb-platform && python manage.py test api.v1.tests.test_webhooks -v2`

**Step 4: Commit**

```bash
cd /Users/ashtoncochrane/Git/localscouta/ubb-platform
git add api/v1/webhooks.py api/v1/tests/test_webhooks.py
git commit -m "feat: rewrite webhooks with event dedup, CAS retry, and error classification"
```

---

## Phase 2: High Priority

### Task 11: Settings Hardening + Security Headers

**Files:**
- Modify: `config/settings.py`
- Modify: `requirements.txt` (add django-cors-headers)

**Step 1: Modify `config/settings.py`**

Replace lines 12, 16 (SECRET_KEY, ALLOWED_HOSTS):

```python
SECRET_KEY = os.environ["SECRET_KEY"]  # Required — KeyError = fail to start

_hosts = os.environ.get("ALLOWED_HOSTS", "")
ALLOWED_HOSTS = [h.strip() for h in _hosts.split(",") if h.strip()]
if not DEBUG and not ALLOWED_HOSTS:
    from django.core.exceptions import ImproperlyConfigured
    raise ImproperlyConfigured("ALLOWED_HOSTS must be set when DEBUG=False")
```

Add `corsheaders` to `INSTALLED_APPS`, add `CorsMiddleware` to `MIDDLEWARE` (before CommonMiddleware).

Add security settings:

```python
# CORS
_cors = os.environ.get("CORS_ALLOWED_ORIGINS", "")
CORS_ALLOWED_ORIGINS = [o.strip() for o in _cors.split(",") if o.strip()]
CORS_ALLOW_CREDENTIALS = True

# Security headers
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"

if not DEBUG:
    SECURE_SSL_REDIRECT = True
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
```

**Step 2: Add django-cors-headers to requirements.txt**

```
django-cors-headers>=4.3
```

**Step 3: Install and verify**

```bash
cd /Users/ashtoncochrane/Git/localscouta/ubb-platform
pip install django-cors-headers
SECRET_KEY=test-key python manage.py check
```

**Step 4: Commit**

```bash
cd /Users/ashtoncochrane/Git/localscouta/ubb-platform
git add config/settings.py requirements.txt
git commit -m "feat: harden settings, add security headers and CORS middleware"
```

---

### Task 12: Database Indexes

**Files:**
- Modify: `apps/usage/models.py` (add indexes to UsageEvent, Invoice, BillingPeriod)
- Modify: `apps/customers/models.py` (add index to WalletTransaction)
- Run migrations

**Step 1: Add indexes**

In `apps/usage/models.py`, update `UsageEvent.Meta`:

```python
class Meta:
    db_table = "ubb_usage_event"
    constraints = [...]
    ordering = ["-effective_at"]
    indexes = [
        models.Index(fields=["customer", "-effective_at"], name="idx_usage_customer_effective"),
    ]
```

In `Invoice.Meta`:
```python
    indexes = [
        models.Index(fields=["customer", "status"], name="idx_invoice_customer_status"),
    ]
```

In `BillingPeriod.Meta`:
```python
    indexes = [
        models.Index(fields=["status", "period_end"], name="idx_billing_period_status_end"),
    ]
```

In `apps/customers/models.py`, update `WalletTransaction.Meta`:
```python
    indexes = [
        models.Index(fields=["wallet", "created_at"], name="idx_wallet_txn_wallet_created"),
    ]
```

**Step 2: Make and run migrations**

```bash
cd /Users/ashtoncochrane/Git/localscouta/ubb-platform
python manage.py makemigrations usage customers
python manage.py migrate
```

**Step 3: Run full test suite to verify no regressions**

```bash
cd /Users/ashtoncochrane/Git/localscouta/ubb-platform
python manage.py test -v2
```

**Step 4: Commit**

```bash
cd /Users/ashtoncochrane/Git/localscouta/ubb-platform
git add apps/usage/models.py apps/customers/models.py apps/*/migrations/
git commit -m "feat: add composite database indexes for production query patterns"
```

---

### Task 13: Input Validation + Cursor Pagination

**Files:**
- Modify: `api/v1/schemas.py` (add validation, pagination schemas)
- Modify: `api/v1/endpoints.py` (update usage list with pagination, add validation)
- Create: `api/v1/pagination.py` (cursor encode/decode helpers)
- Create: `api/v1/tests/test_pagination.py`

**Step 1: Create cursor pagination helpers**

Create `api/v1/pagination.py`:

```python
import base64
import json
import uuid
from datetime import datetime, timezone

from django.db.models import Q


def encode_cursor(effective_at, record_id):
    """Encode pagination cursor as base64 JSON."""
    payload = {
        "v": 1,
        "t": effective_at.astimezone(timezone.utc).isoformat(timespec="microseconds"),
        "id": str(record_id),
    }
    return base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()


def decode_cursor(cursor_str):
    """Decode pagination cursor. Returns (datetime, uuid) or raises ValueError."""
    try:
        raw = base64.urlsafe_b64decode(cursor_str.encode())
        payload = json.loads(raw)
    except (ValueError, json.JSONDecodeError) as e:
        raise ValueError(f"Invalid cursor: {e}")

    if payload.get("v") != 1:
        raise ValueError("Unsupported cursor version")

    try:
        t = datetime.fromisoformat(payload["t"])
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
    except (KeyError, ValueError) as e:
        raise ValueError(f"Invalid cursor timestamp: {e}")

    try:
        record_id = uuid.UUID(payload["id"])
    except (KeyError, ValueError) as e:
        raise ValueError(f"Invalid cursor id: {e}")

    return t, record_id


def apply_cursor_filter(queryset, cursor_str, time_field="effective_at"):
    """Apply cursor-based pagination filter to queryset."""
    if not cursor_str:
        return queryset
    t, record_id = decode_cursor(cursor_str)
    return queryset.filter(
        Q(**{f"{time_field}__lt": t})
        | Q(**{time_field: t, "id__lt": record_id})
    )
```

**Step 2: Update schemas**

Add to `api/v1/schemas.py`:

```python
from typing import Optional, Literal
from ninja import Schema, Field


class RecordUsageRequest(Schema):
    customer_id: UUID
    request_id: str
    idempotency_key: str = Field(min_length=1, max_length=500)
    cost_micros: int = Field(gt=0, le=999_999_999_999)
    metadata: Optional[dict] = None
```

Add `PaginationParams` and `PaginatedResponse` schemas.

**Step 3: Update endpoints**

Update `get_usage` in `api/v1/endpoints.py` to use cursor pagination.

Update `create_customer` to catch `IntegrityError` and return 409.

**Step 4: Write pagination tests and run**

**Step 5: Commit**

```bash
cd /Users/ashtoncochrane/Git/localscouta/ubb-platform
git add api/v1/schemas.py api/v1/endpoints.py api/v1/pagination.py api/v1/tests/
git commit -m "feat: add cursor pagination, input validation, and 409 on duplicate customer"
```

---

### Task 14: Soft Deletes

**Files:**
- Modify: `apps/customers/models.py` (add SoftDeleteMixin to Customer, Wallet, AutoTopUpConfig)
- Create: `core/soft_delete.py` (mixin + manager)
- Modify: `requirements.txt` (if using django-safedelete, or write own mixin)
- Run migrations

Per design doc section 7.1: implement a simple `SoftDeleteMixin` with `deleted_at` field and custom manager. Avoid external dependency.

**Step 1: Create mixin, add to models, write tests, migrate**

**Step 2: Commit**

```bash
git commit -m "feat: add soft delete support for Customer, Wallet, and AutoTopUpConfig"
```

---

### Task 15: Missing Endpoints (Withdraw, Refund, Transactions)

**Files:**
- Modify: `apps/customers/models.py` (add idempotency_key to WalletTransaction)
- Create: `apps/usage/models.py` (add Refund model)
- Modify: `api/v1/schemas.py` (add request/response schemas)
- Modify: `api/v1/endpoints.py` (add 3 new endpoints)
- Run migrations

Per design doc section 8. Add:
- `POST /customers/{customer_id}/withdraw`
- `POST /customers/{customer_id}/refund`
- `GET /customers/{customer_id}/transactions`

**Step 1: Add WalletTransaction.idempotency_key, Refund model, write tests**

**Step 2: Add endpoint implementations with idempotency patterns**

**Step 3: Run tests and commit**

```bash
git commit -m "feat: add withdraw, refund, and transaction list endpoints"
```

---

### Task 16: Celery Config + Periodic Tasks

**Files:**
- Modify: `config/settings.py` (add ubb_topups queue, task routing)
- Create: `apps/stripe_integration/tasks.py` (cleanup task)
- Create: `apps/customers/tasks.py` (stale attempt expiry, wallet reconciliation)
- Create: `apps/stripe_integration/management/commands/reprocess_webhook.py`

Per design doc sections 3.4, 3.5, and cross-cutting requirements.

**Step 1: Add queue config and periodic tasks**

**Step 2: Write management command**

**Step 3: Test and commit**

```bash
git commit -m "feat: add Celery periodic tasks and reprocess_webhook management command"
```

---

### Task 17: Health Endpoints

**Files:**
- Modify: `api/v1/endpoints.py` (add /health, /ready)
- Modify: `config/urls.py` (if needed)

Per design doc section 10.

**Step 1: Add endpoints (no auth required)**

```python
@api.get("/health", auth=None)
def health(request):
    return {"status": "ok"}

@api.get("/ready", auth=None)
def ready(request):
    # Check DB, Redis, Stripe connectivity
    checks = {}
    try:
        from django.db import connection
        connection.ensure_connection()
        checks["database"] = "ok"
    except Exception:
        checks["database"] = "error"
    # Add Redis and Stripe checks similarly
    all_ok = all(v == "ok" for v in checks.values())
    return api.create_response(
        request, {"status": "ready" if all_ok else "not_ready", "checks": checks},
        status=200 if all_ok else 503,
    )
```

**Step 2: Test and commit**

```bash
git commit -m "feat: add health and readiness check endpoints"
```

---

## Summary

| Task | Description | Depends On |
|------|-------------|------------|
| 1 | Domain exceptions | — |
| 2 | Lock ordering helpers | — |
| 3 | Logging infrastructure | — |
| 4 | TopUpAttempt model | — |
| 5 | Stripe service rewrite | 1, 4 |
| 6 | StripeWebhookEvent model | — |
| 7 | Auto-topup service rewrite | 2, 4, 5 |
| 8 | UsageService rewrite | 2, 7 |
| 9 | Invoicing rewrite | 5 |
| 10 | Webhooks rewrite | 2, 5, 6 |
| 11 | Settings hardening | — |
| 12 | Database indexes | — |
| 13 | Input validation + pagination | 8 |
| 14 | Soft deletes | 4 |
| 15 | Missing endpoints | 2, 13 |
| 16 | Celery config + periodic tasks | 6, 7 |
| 17 | Health endpoints | — |

**Parallel tracks:**
- Tasks 1, 2, 3, 4, 6, 11, 12, 17 can all start independently
- Tasks 5, 7, 8, 9, 10 must be sequential (service dependency chain)
- Tasks 13, 14, 15 can proceed after their dependencies complete
