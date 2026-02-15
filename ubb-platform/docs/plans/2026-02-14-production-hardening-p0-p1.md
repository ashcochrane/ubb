# Production Hardening (P0 + P1) Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix the 6 P0 and 9 P1 issues identified in the production readiness audit, bringing the platform from "architecturally sound" to "deployable under real load."

**Architecture:** Config-only changes first (settings.py, celery.py), then data-integrity one-liners, then security hardening, then scalability optimizations. Each task is independent and testable.

**Tech Stack:** Django 6.0, django-ninja, Celery, Redis, PostgreSQL, httpx, Stripe

**Baseline:** 580 tests passing on `feat/subscriptions` branch.

---

## Phase 1: Configuration Fixes (P0)

Three config-only changes in `config/settings.py` that fix broken production behavior.

### Task 1: Add Redis-backed cache

Without this, `RiskService` rate limiting and tenant product dispatch caching are per-process only (broken under multi-worker Gunicorn).

**Files:**
- Modify: `config/settings.py:105-113`

**Step 1: Add CACHES setting after REDIS_URL**

In `config/settings.py`, after line 106 (`REDIS_URL = ...`), add:

```python
# Cache (Redis-backed — required for cross-process rate limiting and dispatch caching)
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
    }
}
```

**Step 2: Run tests**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest --tb=short -q`
Expected: 580 passed (cache is already used via `django.core.cache` — it just switches backend)

**Step 3: Commit**

```bash
git add config/settings.py
git commit -m "fix: add Redis-backed cache config for cross-process rate limiting"
```

---

### Task 2: Add Celery safety defaults

Only 1/17 tasks has `acks_late`. Worker crash = lost tasks. These global settings fix all 17 tasks at once.

**Files:**
- Modify: `config/settings.py:108-113`

**Step 1: Add Celery safety settings after existing Celery config**

In `config/settings.py`, after line 113 (`CELERY_TIMEZONE = "UTC"`), add:

```python
# Celery safety defaults
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_TASK_TIME_LIMIT = 600          # 10 min hard kill
CELERY_TASK_SOFT_TIME_LIMIT = 300     # 5 min SoftTimeLimitExceeded
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_WORKER_MAX_TASKS_PER_CHILD = 1000
```

**Step 2: Run tests**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest --tb=short -q`
Expected: 580 passed

**Step 3: Commit**

```bash
git add config/settings.py
git commit -m "fix: add Celery safety defaults (acks_late, time limits, worker recycling)"
```

---

### Task 3: Add CONN_HEALTH_CHECKS

Prevents stale DB connections after PostgreSQL restarts from causing request failures.

**Files:**
- Modify: `config/settings.py:80-86`

**Step 1: Add CONN_HEALTH_CHECKS to DATABASES config**

In `config/settings.py`, after line 86 (closing `}` of DATABASES), add:

```python
DATABASES["default"]["CONN_HEALTH_CHECKS"] = True
```

**Step 2: Run tests**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest --tb=short -q`
Expected: 580 passed

**Step 3: Commit**

```bash
git add config/settings.py
git commit -m "fix: enable DB connection health checks for stale connection detection"
```

---

## Phase 2: Critical Data Integrity Fixes (P0)

### Task 4: Add idempotency key to billing outbox handler

The highest-volume financial handler (`handle_usage_recorded_billing`) creates `WalletTransaction` without an idempotency key. If the outbox checkpoint write fails after the handler runs, replay would double-deduct.

**Files:**
- Modify: `apps/billing/handlers.py:44-51`
- Test: `apps/billing/tests/test_outbox_handlers.py`

**Step 1: Write the failing test**

Add to `apps/billing/tests/test_outbox_handlers.py`:

```python
def test_usage_deduction_idempotency_key(self):
    """WalletTransaction should have idempotency_key based on outbox event ID."""
    from apps.billing.wallets.models import WalletTransaction
    self._record_usage(cost_micros=500_000)
    txn = WalletTransaction.objects.get(wallet=self.wallet)
    assert txn.idempotency_key is not None
    assert "usage_deduction:" in txn.idempotency_key
```

**Step 2: Run test to verify it fails**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/billing/tests/test_outbox_handlers.py::TestHandleUsageRecordedBilling::test_usage_deduction_idempotency_key -v`
Expected: FAIL — `idempotency_key` is None

**Step 3: Add idempotency key to WalletTransaction.objects.create**

In `apps/billing/handlers.py`, modify lines 44-51. Change the `WalletTransaction.objects.create(...)` call to include `idempotency_key`:

```python
            WalletTransaction.objects.create(
                wallet=wallet,
                transaction_type="USAGE_DEDUCTION",
                amount_micros=-billed_cost_micros,
                balance_after_micros=wallet.balance_micros,
                description=f"Usage: {payload.get('event_id', '')}",
                reference_id=payload.get("event_id", ""),
                idempotency_key=f"usage_deduction:{event_id}",
            )
```

**Step 4: Write replay-safety test**

Add to `apps/billing/tests/test_outbox_handlers.py`:

```python
def test_usage_deduction_replay_does_not_double_deduct(self):
    """Replaying the same outbox event must not create a second deduction."""
    from apps.billing.wallets.models import WalletTransaction
    self._record_usage(cost_micros=500_000)
    balance_after_first = self.wallet.balance_micros

    # Simulate replay: call handler again with same event_id
    # The idempotency_key unique constraint should prevent a second txn.
    from django.db import IntegrityError
    try:
        self._record_usage(cost_micros=500_000)
    except IntegrityError:
        pass  # Expected — unique constraint on idempotency_key

    self.wallet.refresh_from_db()
    txn_count = WalletTransaction.objects.filter(wallet=self.wallet).count()
    assert txn_count == 1
```

Note: This test may need adjustment depending on how `_record_usage` generates event IDs. The key point is that the same `event_id` produces the same `idempotency_key`, and the unique constraint prevents duplicates.

**Step 5: Run all tests**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest --tb=short -q`
Expected: All pass (including 2 new tests)

**Step 6: Commit**

```bash
git add apps/billing/handlers.py apps/billing/tests/test_outbox_handlers.py
git commit -m "fix: add idempotency key to billing usage deduction handler"
```

---

### Task 5: Re-raise network errors in webhook delivery

Currently only `httpx.TimeoutException` re-raises for Celery retry. DNS failures, connection refused, SSL errors are silently swallowed — permanently lost webhook deliveries.

**Files:**
- Modify: `apps/platform/events/webhooks.py:89-101`
- Test: `apps/platform/events/tests/test_webhooks.py`

**Step 1: Write failing test**

Add to the webhook delivery test file:

```python
def test_connection_error_raises_for_retry(self):
    """Non-timeout network errors should re-raise for Celery retry."""
    import httpx

    with patch("apps.platform.events.webhooks.httpx.Client") as MockClient:
        mock_client = MagicMock()
        mock_client.post.side_effect = httpx.ConnectError("Connection refused")
        MockClient.return_value.__enter__ = MagicMock(return_value=mock_client)
        MockClient.return_value.__exit__ = MagicMock(return_value=False)

        with pytest.raises(httpx.ConnectError):
            _deliver_to_config(self.config, self.event)

    # Attempt should still be saved before re-raising
    assert WebhookDeliveryAttempt.objects.filter(outbox_event=self.event).exists()
```

**Step 2: Fix the except block**

In `apps/platform/events/webhooks.py`, change lines 89-101 to re-raise network errors:

```python
    except httpx.TimeoutException as e:
        attempt.success = False
        attempt.error_message = str(e)[:500]
        attempt.save()
        logger.warning(
            "webhook.delivery_timeout",
            extra={
                "data": {
                    "config_id": str(config.id),
                    "event_id": str(event.id),
                    "error": str(e)[:200],
                }
            },
        )
        raise  # Re-raise for Celery retry
    except Exception as e:
        attempt.success = False
        attempt.error_message = str(e)[:500]
        attempt.save()
        logger.warning(
            "webhook.delivery_failed",
            extra={
                "data": {
                    "config_id": str(config.id),
                    "event_id": str(event.id),
                    "error": str(e)[:200],
                }
            },
        )
        # Re-raise network errors for Celery retry; swallow only non-network issues
        if isinstance(e, (httpx.HTTPError, OSError)):
            raise
```

**Step 3: Run tests**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest --tb=short -q`
Expected: All pass

**Step 4: Commit**

```bash
git add apps/platform/events/webhooks.py apps/platform/events/tests/test_webhooks.py
git commit -m "fix: re-raise network errors in webhook delivery for Celery retry"
```

---

## Phase 3: Security Fixes (P0 + P1)

### Task 6: Add SSRF protection to webhook URL validation

Tenants can set webhook URLs to `http://169.254.169.254/` (AWS metadata) or `http://localhost:8000/admin/`. Block private/internal IPs.

**Files:**
- Create: `core/url_validation.py`
- Modify: `apps/platform/events/api/webhook_endpoints.py:7-11`
- Test: `core/tests/test_url_validation.py`

**Step 1: Write the validation tests**

Create `core/tests/test_url_validation.py`:

```python
import pytest
from core.url_validation import validate_webhook_url


class TestWebhookUrlValidation:
    def test_rejects_localhost(self):
        with pytest.raises(ValueError, match="private"):
            validate_webhook_url("http://localhost:8080/hook")

    def test_rejects_127(self):
        with pytest.raises(ValueError, match="private"):
            validate_webhook_url("http://127.0.0.1/hook")

    def test_rejects_metadata_endpoint(self):
        with pytest.raises(ValueError, match="private"):
            validate_webhook_url("http://169.254.169.254/latest/meta-data/")

    def test_rejects_rfc1918_10(self):
        with pytest.raises(ValueError, match="private"):
            validate_webhook_url("http://10.0.0.1/hook")

    def test_rejects_rfc1918_172(self):
        with pytest.raises(ValueError, match="private"):
            validate_webhook_url("http://172.16.0.1/hook")

    def test_rejects_rfc1918_192(self):
        with pytest.raises(ValueError, match="private"):
            validate_webhook_url("http://192.168.1.1/hook")

    def test_rejects_http_scheme(self):
        with pytest.raises(ValueError, match="https"):
            validate_webhook_url("http://example.com/hook")

    def test_accepts_valid_https(self):
        validate_webhook_url("https://example.com/webhook")  # Should not raise

    def test_rejects_non_url(self):
        with pytest.raises(ValueError):
            validate_webhook_url("not-a-url")
```

**Step 2: Implement validation**

Create `core/url_validation.py`:

```python
import ipaddress
import socket
from urllib.parse import urlparse


def validate_webhook_url(url: str) -> None:
    """Validate a webhook URL is safe to deliver to.

    Rejects:
    - Non-HTTPS schemes
    - Private/internal IP addresses (RFC 1918, loopback, link-local)
    - AWS metadata endpoint (169.254.169.254)
    """
    parsed = urlparse(url)

    if parsed.scheme != "https":
        raise ValueError("Webhook URL must use https scheme")

    hostname = parsed.hostname
    if not hostname:
        raise ValueError("Webhook URL must have a hostname")

    # Check for obvious private hostnames
    if hostname in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):
        raise ValueError("Webhook URL must not point to private/internal addresses")

    # Resolve hostname and check IP
    try:
        addr_infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        raise ValueError(f"Cannot resolve hostname: {hostname}")

    for addr_info in addr_infos:
        ip = ipaddress.ip_address(addr_info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            raise ValueError("Webhook URL must not point to private/internal addresses")
```

**Step 3: Wire into webhook config creation**

In `apps/platform/events/api/webhook_endpoints.py`, at the top of `create_webhook_config`:

```python
from core.url_validation import validate_webhook_url

@webhook_api.post("/configs", response={201: WebhookConfigResponse})
def create_webhook_config(request, payload: WebhookConfigCreateRequest):
    try:
        validate_webhook_url(payload.url)
    except ValueError as e:
        from ninja.errors import HttpError
        raise HttpError(400, str(e))
    # ... rest unchanged
```

**Step 4: Run tests**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest --tb=short -q`
Expected: All pass (including 9 new URL validation tests)

**Step 5: Commit**

```bash
git add core/url_validation.py core/tests/test_url_validation.py apps/platform/events/api/webhook_endpoints.py
git commit -m "fix: add SSRF protection to webhook URL validation"
```

---

### Task 7: Add input validation bounds

Multiple schemas have unbounded fields. Add upper bounds to monetary fields and enum validation to referral types.

**Files:**
- Modify: `api/v1/schemas.py:155-167` (DebitRequest, CreditRequest)
- Modify: `apps/referrals/api/schemas.py:8-16` (ProgramCreateRequest)
- Modify: `apps/platform/events/api/webhook_endpoints.py:7-11` (WebhookConfigCreateRequest)

**Step 1: Add upper bounds to DebitRequest and CreditRequest**

In `api/v1/schemas.py`, change:

```python
class DebitRequest(Schema):
    customer_id: str = Field(min_length=1, max_length=255)
    amount_micros: int = Field(gt=0, le=999_999_999_999)
    reference: str = Field(min_length=1, max_length=500)
    idempotency_key: Optional[str] = Field(default=None, max_length=500)


class CreditRequest(Schema):
    customer_id: str = Field(min_length=1, max_length=255)
    amount_micros: int = Field(gt=0, le=999_999_999_999)
    source: str = Field(min_length=1, max_length=255)
    reference: str = Field(min_length=1, max_length=500)
    idempotency_key: Optional[str] = Field(default=None, max_length=500)
```

**Step 2: Add enum + bounds to referral schemas**

In `apps/referrals/api/schemas.py`, change `ProgramCreateRequest`:

```python
from typing import Literal, Optional

class ProgramCreateRequest(Schema):
    reward_type: Literal["flat_fee", "revenue_share", "profit_share"]
    reward_value: float = Field(gt=0, le=100_000_000_000)  # max $100K for flat, 100% for share
    attribution_window_days: int = Field(default=30, ge=1, le=365)
    reward_window_days: Optional[int] = Field(default=None, ge=1, le=3650)
    max_reward_micros: Optional[int] = Field(default=None, gt=0, le=999_999_999_999)
    estimated_cost_percentage: Optional[float] = Field(default=None, ge=0, le=100)
    max_referrals_per_day: Optional[int] = Field(default=None, ge=1, le=10000)
    min_customer_age_hours: Optional[int] = Field(default=None, ge=0, le=8760)
```

**Step 3: Add minimum secret length to webhook config**

In `apps/platform/events/api/webhook_endpoints.py`:

```python
class WebhookConfigCreateRequest(Schema):
    url: str = Field(max_length=500)
    secret: str = Field(min_length=32, max_length=255)
    event_types: list[str] = Field(default_factory=list, max_length=50)
    is_active: bool = True
```

**Step 4: Run tests**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest --tb=short -q`
Expected: All pass (existing tests already use valid values)

**Step 5: Commit**

```bash
git add api/v1/schemas.py apps/referrals/api/schemas.py apps/platform/events/api/webhook_endpoints.py
git commit -m "fix: add bounds to monetary fields, enum to reward_type, webhook secret min length"
```

---

### Task 8: Add Redis graceful degradation to RiskService

If Redis is down, `cache.incr` raises `ConnectionError` which crashes the pre-check endpoint. Should degrade gracefully (skip rate limiting).

**Files:**
- Modify: `apps/billing/gating/services/risk_service.py:17-26`
- Test: `apps/billing/gating/tests/test_risk_service.py`

**Step 1: Write the failing test**

Add to `apps/billing/gating/tests/test_risk_service.py`:

```python
def test_allows_when_redis_unavailable(self):
    """Pre-check should degrade gracefully when Redis is down."""
    with patch("apps.billing.gating.services.risk_service.cache") as mock_cache:
        mock_cache.get.side_effect = ConnectionError("Redis unavailable")
        result = RiskService.check(self.customer)
    assert result["allowed"] is True
```

**Step 2: Wrap cache calls in try/except**

In `apps/billing/gating/services/risk_service.py`, change the rate limiting block (lines 17-26):

```python
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
```

**Step 3: Run tests**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest --tb=short -q`
Expected: All pass

**Step 4: Commit**

```bash
git add apps/billing/gating/services/risk_service.py apps/billing/gating/tests/test_risk_service.py
git commit -m "fix: RiskService degrades gracefully when Redis is unavailable"
```

---

## Phase 4: Scalability Fixes (P1)

### Task 9: Buffer auth last_used_at via Redis

Every API call writes `UPDATE ubb_tenant_api_key SET last_used_at=...`. At 10K req/s this is 10K writes/sec on a shared table. Buffer via Redis and flush periodically.

**Files:**
- Modify: `core/auth.py:14`
- Create: `core/tasks.py`
- Modify: `config/settings.py` (add beat schedule entry)

**Step 1: Replace DB write with Redis increment**

In `core/auth.py`, replace line 14:

```python
from django.utils import timezone
from django.core.cache import cache
from ninja.errors import HttpError
from ninja.security import HttpBearer

from apps.platform.tenants.models import TenantApiKey


class ApiKeyAuth(HttpBearer):
    def authenticate(self, request, token):
        key_obj = TenantApiKey.verify_key(token)
        if key_obj is None:
            return None
        request.tenant = key_obj.tenant
        # Buffer last_used_at in Redis — flushed to DB by periodic task
        cache.set(f"apikey_used:{key_obj.pk}", timezone.now().isoformat(), timeout=3600)
        return key_obj
```

**Step 2: Create flush task**

Create `core/tasks.py`:

```python
import logging
from datetime import datetime

from celery import shared_task
from django.core.cache import cache
from django.utils import timezone

from apps.platform.tenants.models import TenantApiKey

logger = logging.getLogger(__name__)


@shared_task(queue="ubb_billing")
def flush_api_key_last_used():
    """Flush buffered last_used_at timestamps from Redis to DB.

    Runs every 5 minutes. Scans all active API keys and updates
    last_used_at if a Redis entry exists.
    """
    keys = TenantApiKey.objects.filter(is_active=True).values_list("pk", flat=True)
    updated = 0
    for pk in keys:
        cache_key = f"apikey_used:{pk}"
        ts = cache.get(cache_key)
        if ts:
            TenantApiKey.objects.filter(pk=pk).update(
                last_used_at=datetime.fromisoformat(ts)
            )
            cache.delete(cache_key)
            updated += 1
    if updated:
        logger.info("api_key.last_used_flushed", extra={"data": {"count": updated}})
```

**Step 3: Add beat schedule entry**

In `config/settings.py`, add to `CELERY_BEAT_SCHEDULE`:

```python
    "flush-api-key-last-used": {
        "task": "core.tasks.flush_api_key_last_used",
        "schedule": crontab(minute="*/5"),
    },
```

**Step 4: Run tests**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest --tb=short -q`
Expected: All pass (auth tests still verify authentication works; last_used_at is not asserted in sync)

**Step 5: Commit**

```bash
git add core/auth.py core/tasks.py config/settings.py
git commit -m "perf: buffer API key last_used_at via Redis, flush every 5 min"
```

---

### Task 10: Add TenantMarkup composite index

Up to 3 sequential queries per event hit `ubb_tenant_markup` with no composite index. Add `(tenant, event_type, provider)`.

**Files:**
- Modify: `apps/metering/pricing/models.py:65-66`

**Step 1: Add the composite index**

In `apps/metering/pricing/models.py`, change the `TenantMarkup.Meta`:

```python
    class Meta:
        db_table = "ubb_tenant_markup"
        indexes = [
            models.Index(
                fields=["tenant", "event_type", "provider"],
                name="idx_markup_tenant_lookup",
            ),
        ]
```

**Step 2: Generate migration**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python manage.py makemigrations pricing --name add_markup_composite_index`

**Step 3: Apply migration**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python manage.py migrate`

**Step 4: Run tests**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest --tb=short -q`
Expected: All pass

**Step 5: Commit**

```bash
git add apps/metering/pricing/models.py apps/metering/pricing/migrations/
git commit -m "perf: add composite index on TenantMarkup (tenant, event_type, provider)"
```

---

### Task 11: Add UsageEvent analytics composite index

Analytics queries filter by `(tenant_id, effective_at)` but have no composite index. Tenant-level analytics become full table scans as the table grows.

**Files:**
- Modify: `apps/metering/usage/models.py:43-45`

**Step 1: Add the composite index**

In `apps/metering/usage/models.py`, add to the `indexes` list in `UsageEvent.Meta`:

```python
        indexes = [
            models.Index(fields=["customer", "-effective_at"], name="idx_usage_customer_effective"),
            models.Index(fields=["tenant", "-effective_at"], name="idx_usage_tenant_effective"),
        ]
```

**Step 2: Generate migration**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python manage.py makemigrations usage --name add_tenant_effective_index`

**Step 3: Apply migration**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python manage.py migrate`

**Step 4: Run tests**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest --tb=short -q`
Expected: All pass

**Step 5: Commit**

```bash
git add apps/metering/usage/models.py apps/metering/usage/migrations/
git commit -m "perf: add composite index on UsageEvent (tenant, -effective_at) for analytics"
```

---

### Task 12: Add WebhookDeliveryAttempt cleanup task

This table grows unboundedly with no archival. Add a cleanup task matching the pattern used for `StripeWebhookEvent`.

**Files:**
- Create: `apps/platform/events/tasks_webhook_cleanup.py`
- Modify: `config/settings.py` (beat schedule)

**Step 1: Create cleanup task**

Create `apps/platform/events/tasks_webhook_cleanup.py`:

```python
import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from apps.platform.events.webhook_models import WebhookDeliveryAttempt

logger = logging.getLogger(__name__)


@shared_task(queue="ubb_webhooks")
def cleanup_webhook_delivery_attempts():
    """Delete old webhook delivery attempts.

    - Successful attempts: delete after 30 days
    - Failed attempts: delete after 90 days
    """
    now = timezone.now()

    success_cutoff = now - timedelta(days=30)
    success_count, _ = WebhookDeliveryAttempt.objects.filter(
        success=True, created_at__lt=success_cutoff
    ).delete()

    fail_cutoff = now - timedelta(days=90)
    fail_count, _ = WebhookDeliveryAttempt.objects.filter(
        success=False, created_at__lt=fail_cutoff
    ).delete()

    if success_count or fail_count:
        logger.info(
            "webhook_delivery_attempts.cleanup",
            extra={"data": {"success_deleted": success_count, "failed_deleted": fail_count}},
        )
```

**Step 2: Add beat schedule**

In `config/settings.py`, add to `CELERY_BEAT_SCHEDULE`:

```python
    "cleanup-webhook-delivery-attempts": {
        "task": "apps.platform.events.tasks_webhook_cleanup.cleanup_webhook_delivery_attempts",
        "schedule": crontab(minute=0, hour=3),  # Daily at 3 AM UTC
    },
```

**Step 3: Run tests**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest --tb=short -q`
Expected: All pass

**Step 4: Commit**

```bash
git add apps/platform/events/tasks_webhook_cleanup.py config/settings.py
git commit -m "feat: add WebhookDeliveryAttempt cleanup task (30d success, 90d failed)"
```

---

## Phase 5: Remaining P1 Fixes

### Task 13: Handle Redis errors in RiskService pre-check

Already done in Task 8 above. Skip if completed.

---

### Task 14: Add Celery retry to financial tasks

Add `autoretry_for` to the most critical scheduled tasks that currently have no retry config.

**Files:**
- Modify: `apps/billing/tenant_billing/tasks.py`
- Modify: `apps/platform/runs/tasks.py`

**Step 1: Add retry config to tenant billing tasks**

In `apps/billing/tenant_billing/tasks.py`, update the task decorators for `close_tenant_billing_periods` and `generate_tenant_platform_invoices`:

```python
@shared_task(
    queue="ubb_billing",
    autoretry_for=(OperationalError, InterfaceError),
    max_retries=3,
    retry_backoff=True,
)
def close_tenant_billing_periods():
    ...
```

```python
@shared_task(
    queue="ubb_billing",
    autoretry_for=(OperationalError, InterfaceError),
    max_retries=3,
    retry_backoff=True,
)
def generate_tenant_platform_invoices():
    ...
```

Add imports at the top if not present:
```python
from django.db.utils import OperationalError, InterfaceError
```

**Step 2: Add retry config to close_abandoned_runs**

In `apps/platform/runs/tasks.py`, update:

```python
from django.db.utils import OperationalError, InterfaceError

@shared_task(
    queue="ubb_billing",
    autoretry_for=(OperationalError, InterfaceError),
    max_retries=3,
    retry_backoff=True,
)
def close_abandoned_runs():
    ...
```

**Step 3: Run tests**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest --tb=short -q`
Expected: All pass

**Step 4: Commit**

```bash
git add apps/billing/tenant_billing/tasks.py apps/platform/runs/tasks.py
git commit -m "fix: add Celery autoretry to financial tasks for transient DB errors"
```

---

## Summary

| Task | Phase | Issue | Type | Est. |
|------|-------|-------|------|------|
| 1. Redis cache config | 1 | P0 | Config | 2 min |
| 2. Celery safety defaults | 1 | P0 | Config | 2 min |
| 3. CONN_HEALTH_CHECKS | 1 | P0 | Config | 2 min |
| 4. Billing handler idempotency | 2 | P0 | Code + Test | 15 min |
| 5. Webhook error re-raise | 2 | P0 | Code + Test | 10 min |
| 6. SSRF protection | 3 | P0 | Code + Test | 20 min |
| 7. Input validation bounds | 3 | P1 | Code | 10 min |
| 8. Redis graceful degradation | 3 | P1 | Code + Test | 10 min |
| 9. Auth last_used_at buffer | 4 | P1 | Code | 15 min |
| 10. TenantMarkup composite index | 4 | P1 | Migration | 5 min |
| 11. UsageEvent analytics index | 4 | P1 | Migration | 5 min |
| 12. Webhook delivery cleanup | 4 | P1 | Code | 10 min |
| 14. Celery retry on financial tasks | 5 | P1 | Code | 10 min |
| **Total** | | **6 P0 + 7 P1** | | ~2 hrs |

## Verification

After each phase:
```bash
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest --tb=short -q
```

After index migrations (Tasks 10-11):
```bash
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python manage.py makemigrations --check
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python manage.py migrate
```
