# UBB Platform — Production Readiness Design (Updated Draft)

## Overview

This document covers all changes required to make the UBB platform production-ready before real money flows. Organized in two phases: critical issues (must fix first) and high-priority improvements (before scale). It also includes a Ledger-Grade Requirements section to ensure auditability and correctness for real-money systems.

---

## Phase 1: Critical Issues

### 1. Stripe Service Error Handling + Idempotency

#### 1.1 Domain Exceptions (`core/exceptions.py`)

Three new exception classes:

- `StripeTransientError` — retryable (network, rate limit, server errors)
- `StripePaymentError` — payment declined, card errors — never retry
- `StripeFatalError` — config, auth, idempotency mismatch — never retry, alerts required

#### 1.2 Error Mapping in `stripe_call()` Wrapper

| Stripe Exception         | Domain Exception       | Retryable? |
|--------------------------|------------------------|------------|
| `RateLimitError`         | `StripeTransientError` | Yes        |
| `APIConnectionError`     | `StripeTransientError` | Yes        |
| `APIError` (5xx)         | `StripeTransientError` | Yes        |
| `CardError`              | `StripePaymentError`   | Never      |
| `IdempotencyError`       | `StripeFatalError`     | Never      |
| `AuthenticationError`    | `StripeFatalError`     | Never      |
| `PermissionError`        | `StripeFatalError`     | Never      |
| `InvalidRequestError`    | `StripeFatalError`     | Never*     |

\*Note: `InvalidRequestError` should be sub-classified by error `code` where possible — some are data-dependent (e.g., "customer has no attached payment method") vs true programmer/config errors. Log the full error code for triage.

Only retries operations that have an idempotency key attached. If `idempotency_key` is `None`, `retryable` is forced to `False`.

#### 1.3 TopUpAttempt Model (`apps/customers/models.py`)

New model to persist charge attempts before calling Stripe:

```
TopUpAttempt(BaseModel)
  - customer (FK -> Customer)
  - amount_micros (PositiveBigIntegerField, validated > 0 at service layer)
  - trigger ("manual" | "auto_topup")
  - status ("pending" | "succeeded" | "failed" | "expired")
  - stripe_payment_intent_id (CharField, nullable)
  - stripe_checkout_session_id (CharField, nullable)
  - failure_reason (JSONField, nullable — stores error_type, code, decline_code, message)

  constraints:
    - UniqueConstraint(fields=["customer"], condition=Q(status="pending", trigger="auto_topup"),
                       name="uq_one_pending_auto_topup_per_customer")
```

Manual checkout top-ups can have multiple pending attempts concurrently. Only auto-topup is limited to one pending per customer.

**Stale attempt watchdog:** Add a periodic task to expire stale pending attempts (auto-topup > 30 minutes, checkout > 24 hours). A stuck pending auto-topup blocks new auto-topups via the UniqueConstraint, which means revenue flow stops for that customer. Transition stale attempts to `"expired"` status. This also prevents reconciliation gaps in the ledger.

For checkout flow: `top_up_attempt.id` stored in Stripe's `client_reference_id`. The `handle_checkout_completed` webhook reads it, looks up the attempt, transitions to `succeeded`, credits wallet.

#### 1.4 Invoice Attempt Counter (`apps/usage/models.py`)

New field on `BillingPeriod`:

```
BillingPeriod
  + invoice_attempt_number (PositiveIntegerField, default=0)
```

When creating an invoice:
1. `BillingPeriod.objects.select_for_update().get(id=period_id)`
2. Use `invoice_attempt_number` for key: `invoice-{billing_period.id}-v{invoice_attempt_number}`
3. Only increment after a non-retryable failure triggers a void
4. `select_for_update()` prevents two workers from allocating the same attempt

**Cap:** Maximum `invoice_attempt_number` of 5. After exhaustion, alert and require manual intervention. Prevents unbounded voided invoices from recurring bugs.

#### 1.5 Deterministic Idempotency Keys

| Operation       | Key Format                                           | Source                                           |
|-----------------|------------------------------------------------------|--------------------------------------------------|
| Charge          | `charge-{top_up_attempt.id}`                         | TopUpAttempt created pending first               |
| Checkout        | `checkout-{top_up_attempt.id}`                       | TopUpAttempt created pending first               |
| Invoice         | `invoice-{billing_period.id}-v{attempt_number}`      | BillingPeriod.invoice_attempt_number with lock    |
| Invoice item    | `invitem-{usage_event.id}-inv{stripe_invoice.id}`    | Stripe invoice ID from invoice creation step     |

Keys are deterministic from persisted entities. Retries and restarts produce the same key.

**Note:** Invoice item keys depend on having a known Stripe invoice ID from the invoice creation step. If `Invoice.create()` succeeds but the response is lost (network timeout), retrying with the same idempotency key returns the same invoice and its ID. Document this ordering dependency for future maintainers.

#### 1.6 Invoice Lifecycle

1. `Invoice.create()` with deterministic key — Stripe returns same invoice on retry
2. `InvoiceItem.create()` per usage event with key including `stripe_invoice.id` — items bound to specific invoice
3. `Invoice.finalize_invoice()` — retryable on transient failure
4. Only void on non-retryable failure, then increment `attempt_number` for next try (capped at max attempts)
5. Usage events marked `invoiced=True` only after finalize succeeds (single bulk update in same transaction)

Transient failures retry the same invoice. Only fatal errors trigger void + new attempt.

#### 1.7 Input Validation

- `amount_micros > 0` validated at service layer (not just DB constraint)
- `UBB_TOPUP_SUCCESS_URL` and `UBB_TOPUP_CANCEL_URL` validated in `AppConfig.ready()` (safe for tests, migrations, Celery)

#### 1.8 Stripe Inline Retry Strategy

For synchronous (non-Celery) Stripe calls via `stripe_call()`:

- Exponential backoff with jitter (base 0.5s, factor 2x, ±25% jitter)
- Max 3 attempts
- Total timeout cap: 10 seconds
- Only retries `StripeTransientError` with an idempotency key present

This mirrors the Celery task retry config but operates inline for request-time calls (e.g., checkout session creation). Without jitter, correlated retries under load cause thundering herd effects.

---

### 2. Race Conditions and Transaction Boundaries

#### 2.1 Lock Ordering — Enforced via Helpers (`core/locking.py`)

Canonical order: **Wallet -> Customer -> TopUpAttempt -> Invoice**

```python
def lock_for_billing(customer_id):
    """Wallet -> Customer. For usage recording, wallet credits.

    INVARIANT: No code path may hold a Customer lock and then attempt
    a Wallet lock. This would violate canonical lock ordering and risk
    deadlock. Always use this helper when both locks are needed.
    """
    wallet = Wallet.objects.select_for_update().get(customer_id=customer_id)
    customer = Customer.objects.select_for_update().get(id=customer_id)
    return wallet, customer

def lock_customer(customer_id):
    """Customer only. For status changes without wallet mutation."""
    return Customer.objects.select_for_update().get(id=customer_id)

def lock_top_up_attempt(attempt_id):
    """TopUpAttempt only. For status transitions after Stripe calls."""
    return TopUpAttempt.objects.select_for_update().get(id=attempt_id)

def lock_invoice(invoice_id):
    """Invoice only. For status transitions from webhooks."""
    return Invoice.objects.select_for_update().get(id=invoice_id)
```

No direct `select_for_update()` on these models outside helpers. New combinations must add a helper respecting canonical order.

#### 2.2 UsageService Flow

```
1. @transaction.atomic
2. wallet, customer = lock_for_billing(customer_id)
3. Deduct wallet, create UsageEvent
4. Check suspension threshold, suspend if needed
5. If below auto-topup threshold:
     attempt = _handle_auto_topup(customer, wallet)
     (creates pending TopUpAttempt, or returns None if one exists — see 2.6)
6. Commit

7. if attempt is not None:
     transaction.on_commit(
         lambda aid=attempt.id: charge_auto_topup_task.delay(aid)
     )
```

`transaction.on_commit` guarantees Celery task only dispatched if transaction commits. Default arg capture on lambda avoids late-binding. Usage response returns immediately.

#### 2.3 Auto-Topup Celery Task (`charge_auto_topup_task`)

Queue: `ubb_topups` (dedicated, isolated from `ubb_invoicing` and `ubb_webhooks`).

```
1. try:
       attempt = TopUpAttempt.objects.get(id=attempt_id)
   except DoesNotExist:
       logger.warning("TopUpAttempt %s not found, skipping", attempt_id)
       return
2. If attempt.status != "pending": return (no-op, idempotent)
3. charge_result = StripeService.charge(attempt)
   (internally sets idempotency_key=f"charge-{attempt.id}" unconditionally)

4. @transaction.atomic
5. wallet, customer = lock_for_billing(attempt.customer_id)
6. attempt = lock_top_up_attempt(attempt.id)
7. If attempt.status != "pending": return (race with webhook, no-op)
8. If charge succeeded:
     wallet.credit(...)
     attempt.status = "succeeded"
     attempt.stripe_payment_intent_id = result.id
9. If charge failed:
     attempt.status = "failed"
     attempt.failure_reason = {
         "error_type": type(e).__name__,
         "code": getattr(e, "code", None),
         "decline_code": getattr(e, "decline_code", None),
         "message": str(e),
     }
```

Lock order: Wallet -> Customer -> TopUpAttempt. Canonical order respected.

**Crash recovery:** If the Stripe charge succeeds (step 3) but the worker crashes before the DB transaction commits (steps 4-9), the wallet is not credited. On retry, `StripeService.charge()` returns the same successful result (idempotency key match), and the task proceeds to credit the wallet normally. This is the expected recovery path — no manual intervention needed.

Task config:
- `autoretry_for = (StripeTransientError,)`
- `max_retries = 3`, `retry_backoff = True`
- `acks_late = True`
- `StripePaymentError` / `StripeFatalError` not retried — task updates attempt to `failed`

#### 2.4 Webhook Handler Locking

- `handle_checkout_completed`: `lock_for_billing(customer_id)`, then `lock_top_up_attempt(attempt_id)`. Check attempt status before credit. Canonical order: Wallet -> Customer -> TopUpAttempt.
- `handle_invoice_paid`: `lock_invoice(invoice_id)`. Check if already `paid`.
- `handle_invoice_payment_failed`: `lock_customer(customer_id)`. Update status.

No handler locks both Wallet and Customer without using `lock_for_billing()`.

#### 2.5 Test Requirements

- Concurrency tests use `TransactionTestCase` with threaded DB connections to exercise `select_for_update()` behavior
- Integration test: two concurrent usage requests assert only one `TopUpAttempt` created
- Unit test: `_handle_auto_topup` raises if called outside `@transaction.atomic`
- Savepoint test: `IntegrityError` in `_handle_auto_topup` does not abort outer transaction (see 2.6)

#### 2.6 `_handle_auto_topup` IntegrityError Handling

The UniqueConstraint race on `TopUpAttempt` must not abort the outer `@transaction.atomic` block. In PostgreSQL, an `IntegrityError` inside `@transaction.atomic` aborts the entire atomic block unless a savepoint is used.

Use a savepoint:

```python
def _handle_auto_topup(customer, wallet):
    # ... threshold checks ...
    try:
        with transaction.atomic():  # creates a savepoint
            attempt = TopUpAttempt.objects.create(
                customer=customer,
                amount_micros=config.top_up_amount_micros,
                trigger="auto_topup",
                status="pending",
            )
        return attempt
    except IntegrityError:
        # Another pending auto-topup already exists for this customer
        return None
```

Alternative: use `get_or_create`, which handles the race internally. Either approach is acceptable; the key requirement is that the outer transaction survives.

---

### 3. Webhooks

#### 3.1 StripeWebhookEvent Model (`apps/stripe_integration/models.py`)

```
StripeWebhookEvent(BaseModel)
  - stripe_event_id (CharField, unique, indexed)
  - event_type (CharField, indexed)
  - status ("processing" | "succeeded" | "failed" | "skipped")
  - failure_reason (JSONField, nullable)
  - processed_at (DateTimeField, nullable)
  - duplicate_count (PositiveIntegerField, default=0)
  - last_seen_at (DateTimeField, default=timezone.now)

  # Inherited from BaseModel: id (UUID), created_at, updated_at

  indexes:
    - (status, created_at)
    - (created_at)  — supports retention cleanup query
```

No `"duplicate"` status. Original outcome always preserved. Duplicate deliveries increment `duplicate_count` and update `last_seen_at`.

#### 3.2 Webhook Dispatcher

```python
@csrf_exempt
@require_POST
def stripe_webhook(request):
    # 1. Verify signature
    try:
        event = stripe.Webhook.construct_event(...)
    except (ValueError, stripe.error.SignatureVerificationError):
        return HttpResponse(status=400)

    # 2. Event-level dedup with IntegrityError handling
    try:
        with transaction.atomic():
            webhook_event, created = StripeWebhookEvent.objects.get_or_create(
                stripe_event_id=event.id,
                defaults={"event_type": event.type, "status": "processing"}
            )
    except IntegrityError:
        # Safety net for race conditions beyond get_or_create's internal handling
        # (e.g., read replica lag). get_or_create handles most races internally.
        StripeWebhookEvent.objects.filter(stripe_event_id=event.id).update(
            duplicate_count=F("duplicate_count") + 1,
            last_seen_at=timezone.now(),
            updated_at=timezone.now(),
        )
        return JsonResponse({"status": "already_received"})

    if not created:
        processing_ttl = timezone.now() - timedelta(minutes=30)

        # CAS: allow retry of retryable failures or stale processing
        if (
            (webhook_event.status == "failed"
             and webhook_event.failure_reason
             and webhook_event.failure_reason.get("retryable") is True)
            or (webhook_event.status == "processing"
                and webhook_event.updated_at < processing_ttl)
        ):
            rows_updated = StripeWebhookEvent.objects.filter(
                id=webhook_event.id,
                status=webhook_event.status,
                updated_at=webhook_event.updated_at,
            ).update(
                status="processing",
                failure_reason=None,
                duplicate_count=F("duplicate_count") + 1,
                last_seen_at=timezone.now(),
                updated_at=timezone.now(),
            )
            if rows_updated == 0:
                return JsonResponse({"status": "already_processing"})
            # Won CAS — fall through to handler
        else:
            StripeWebhookEvent.objects.filter(stripe_event_id=event.id).update(
                duplicate_count=F("duplicate_count") + 1,
                last_seen_at=timezone.now(),
                updated_at=timezone.now(),
            )
            return JsonResponse({"status": "already_processed"})

    # 3. Dispatch
    handler = WEBHOOK_HANDLERS.get(event.type)
    if not handler:
        webhook_event.status = "skipped"
        webhook_event.save(update_fields=["status", "updated_at"])
        return JsonResponse({"status": "ok"})

    # 4. Execute with error classification
    try:
        handler(event)
        webhook_event.status = "succeeded"
        webhook_event.processed_at = timezone.now()
        webhook_event.save(update_fields=["status", "processed_at", "updated_at"])
    except ObjectDoesNotExist as e:
        # Out-of-order delivery: object not yet persisted locally.
        # Return 500 so Stripe retries. Mark as retryable failure.
        logger.warning(
            "Webhook handler ObjectDoesNotExist for %s (likely out-of-order): %s",
            event.id, e
        )
        webhook_event.status = "failed"
        webhook_event.failure_reason = {
            "error": str(e), "type": type(e).__name__, "retryable": True
        }
        webhook_event.processed_at = timezone.now()
        webhook_event.save(update_fields=["status", "failure_reason", "processed_at", "updated_at"])
        return HttpResponse(status=500)  # Stripe retries
    except StripeFatalError as e:
        logger.error("Webhook handler fatal error for %s: %s", event.id, e)
        webhook_event.status = "failed"
        webhook_event.failure_reason = {
            "error": str(e), "type": type(e).__name__, "retryable": False
        }
        webhook_event.processed_at = timezone.now()
        webhook_event.save(update_fields=["status", "failure_reason", "processed_at", "updated_at"])
        return JsonResponse({"status": "failed"})  # 200 — no Stripe retry
    except Exception as e:
        logger.exception("Webhook handler transient error for %s", event.id)
        webhook_event.status = "failed"
        webhook_event.failure_reason = {
            "error": str(e), "type": type(e).__name__, "retryable": True
        }
        webhook_event.processed_at = timezone.now()
        webhook_event.save(update_fields=["status", "failure_reason", "processed_at", "updated_at"])
        return HttpResponse(status=500)  # Stripe retries

    return JsonResponse({"status": "ok"})
```

**Key changes from original:**
- `ObjectDoesNotExist` is now **retryable** (returns 500) instead of fatal. Out-of-order event delivery (e.g., `invoice.paid` before local invoice record) should be retried, not silently dropped. In a ledger system, silently dropping money-related events is not acceptable.
- Processing TTL increased from 10 to 30 minutes to reduce risk of double-apply when handlers involve Stripe API calls.
- **All handlers must be fully idempotent including external side effects.** If any handler triggers emails, external analytics, or third-party calls, those must also be idempotent or guarded.

#### 3.3 Handler-Level Idempotency (Belt and Suspenders)

Each handler checks domain state before mutating:
- `handle_checkout_completed`: checks `TopUpAttempt.status` before crediting
- `handle_invoice_paid`: checks `invoice.status != "paid"` before updating
- `handle_invoice_payment_failed`: checks `customer.status` before suspending

#### 3.4 Retention Cleanup Task

```python
@shared_task(queue="ubb_webhooks")
def cleanup_webhook_events():
    """Batch-delete old webhook events to avoid long-running deletes and WAL bloat."""
    succeeded_cutoff = timezone.now() - timedelta(days=90)
    failed_cutoff = timezone.now() - timedelta(days=180)

    # Delete succeeded/skipped events older than 90 days in batches
    _batched_delete(
        StripeWebhookEvent.objects.filter(
            status__in=["succeeded", "skipped"],
            created_at__lt=succeeded_cutoff,
        )
    )

    # Delete failed events older than 180 days in batches
    # (keep failed events longer for investigation)
    _batched_delete(
        StripeWebhookEvent.objects.filter(
            status="failed",
            created_at__lt=failed_cutoff,
        )
    )


def _batched_delete(queryset, batch_size=1000):
    """Delete in batches by PK range to avoid long locks."""
    while True:
        batch_ids = list(queryset.values_list("id", flat=True)[:batch_size])
        if not batch_ids:
            break
        deleted, _ = StripeWebhookEvent.objects.filter(id__in=batch_ids).delete()
        logger.info("Cleaned up %d webhook events", deleted)
```

**Changes:** Batched deletes to avoid table locks and WAL bloat on large tables. Failed events retained for 180 days (vs 90 for succeeded/skipped) to allow investigation. Consider regulatory requirements for longer retention.

#### 3.5 Management Command

`python manage.py reprocess_webhook <stripe_event_id>` — resets a `failed` event to `processing` for manual replay.

---

### 4. Logging

#### 4.1 Correlation ID via `contextvars` (`core/logging.py`)

```python
import contextvars
correlation_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "correlation_id", default=""
)
```

Safe under ASGI, async views, and threaded workers.

#### 4.2 Correlation ID Middleware (`core/middleware.py`)

- Reads `X-Correlation-ID` from request headers
- Validates: UUID format, max 36 chars. Invalid or missing generates fresh `uuid4()`
- Sets `correlation_id_var.set(validated_id)`
- Adds `X-Correlation-ID` to response headers

#### 4.3 Celery Propagation

- `before_task_publish` signal: reads `correlation_id_var`, passes as task header
- `task_prerun` signal: reads header, sets `correlation_id_var`. Missing header (periodic tasks) generates fresh UUID

#### 4.4 PII Redaction (`core/logging.py`)

Standardized extra payload convention: all logging uses `extra={"data": {...}}`.

```python
REDACT_KEYS = {
    "email", "phone", "name", "payment_method", "card",
    "ip_address", "address",
}
REDACT_KEY_SUBSTRINGS = {"secret", "token", "api_key", "authorization", "password", "credential"}

STANDARD_LOG_KEYS = frozenset(
    logging.LogRecord("", 0, "", 0, "", (), None).__dict__.keys()
)

EMAIL_PATTERN = re.compile(r'[\w.-]+@[\w.-]+\.\w+')
```

**Note:** `stripe_customer_id` is intentionally **not** redacted. It is a Stripe-internal ID (e.g., `cus_xxx`), not directly PII, and is needed to correlate logs with the Stripe dashboard during debugging.

`RedactingFilter`:
1. Redacts standardized `record.data` payload
2. Scans non-standard extras via `record.__dict__` diff against `STANDARD_LOG_KEYS`
3. Calls `record.getMessage()` to resolve args, replaces `record.msg`, sets `record.args = None`
4. Key substring matching: any key containing `secret`, `token`, etc. is redacted
5. Email pattern regex on all string values

**Important:** `RedactingFilter` must be **last** in the filter chain, because it sets `record.args = None`. Any filter running after it that expects `record.args` will break.

Docstring documents the `extra={"data": {...}}` convention for contributors.

#### 4.5 JSON Formatter (`core/logging.py`)

```python
class JsonFormatter(logging.Formatter):
    def format(self, record):
        log_entry = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "correlation_id": correlation_id_var.get(""),
            "message": record.msg,  # already redacted + resolved by filter
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

Exception output redacted via `_redact_string` as final safety net.

#### 4.6 Settings (`config/settings.py`)

```python
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "correlation_id": {"()": "core.logging.CorrelationIdFilter"},
        "redacting": {"()": "core.logging.RedactingFilter"},  # must be last
    },
    "formatters": {
        "json": {"()": "core.logging.JsonFormatter"},
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json",
            "filters": ["correlation_id", "redacting"],  # redacting last
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

`propagate: False` on all named loggers prevents duplicate output.

#### 4.7 What Gets Logged

- Every Stripe API call: method, redacted params, response status, idempotency key
- Every usage recording: customer, cost, wallet balance before/after
- Every webhook: event type, stripe_event_id, handler outcome
- Every auto-topup: trigger, amount, charge result
- Every error: full exception with correlation ID

#### 4.8 Tests

- Incoming correlation ID header preserved
- Missing header generates fresh UUID
- Invalid header rejected and replaced
- Response header set
- Celery header round-trip
- Periodic task gets fresh ID

---

## Phase 2: High Priority

### 5. Database Indexes

Additive — no existing indexes removed. One migration per app.

**UsageEvent:**
```python
models.Index(fields=["customer", "-effective_at"], name="idx_usage_customer_effective")
```
Descending composite matches `ORDER BY effective_at DESC` in usage list endpoint.

**Invoice:**
```python
models.Index(fields=["customer", "status"], name="idx_invoice_customer_status")
```

**BillingPeriod:**
```python
models.Index(fields=["status", "period_end"], name="idx_billing_period_status_end")
```
Supports invoicing task: `.filter(status="open", period_end__lte=now)`.

**WalletTransaction:**
```python
models.Index(fields=["wallet", "created_at"], name="idx_wallet_txn_wallet_created")
```

**StripeWebhookEvent:**
```python
models.Index(fields=["created_at"], name="idx_webhook_created_at")
```
Supports retention cleanup query that filters only by `created_at`.

**Future optimizations (deferred — no current bottleneck):**
- Partial index on UsageEvent: `invoice_id IS NULL` + `(customer_id, effective_at)` for invoicing query
- `(tenant, status)` on Invoice for admin/reporting queries
- `(customer, created_at)` on TopUpAttempt for customer history queries

---

### 6. Pagination and Input Validation

#### 6.1 Cursor-Based Pagination

Versioned JSON cursor encoded as base64:
```json
{"v": 1, "t": "2025-01-15T10:30:00.000000+00:00", "id": "uuid-here"}
```

- Ordering: `-effective_at, -id` (UUID as deterministic tie-breaker, not chronological)
- Cursor filter: `Q(effective_at__lt=t) | Q(effective_at=t, id__lt=id)`
- Cursor encoding: `effective_at.astimezone(timezone.utc).isoformat(timespec="microseconds")`
- **Standardize on `+00:00` format** (Python's default from `isoformat()`). Do not use `Z` suffix — `datetime.fromisoformat()` in Python <3.11 rejects it. Decode should accept both formats defensively.
- Decode errors return 400
- Fetch `limit + 1` to detect next page without count query

```python
class PaginationParams(Schema):
    limit: int = Field(default=50, ge=1, le=100)
    cursor: Optional[str] = None
```

Same cursor pattern used for usage list and transactions list.

**Note:** UUID tie-breaker ordering is arbitrary (UUIDv4 is random), used only for determinism. If migrating to UUIDv7 in future, tie-breaking behavior changes — document this assumption.

#### 6.2 Input Validation on RecordUsageRequest

```python
class RecordUsageRequest(Schema):
    customer_id: UUID  # unchanged — matches current SDK
    cost_micros: int = Field(gt=0, le=999_999_999_999)
    idempotency_key: str = Field(min_length=1, max_length=500)  # matches DB field
    metadata: Optional[dict] = Field(default=None)

    @field_validator("metadata")
    def validate_metadata(cls, v):
        if v is not None:
            try:
                raw = json.dumps(v)
            except (TypeError, ValueError):
                raise ValueError("metadata must be JSON-serializable")
            if len(raw.encode("utf-8")) > 4096:
                raise ValueError("metadata must be under 4KB")
        return v
```

No breaking API changes.

#### 6.3 Duplicate Customer Creation — 409

```python
customer = Customer.objects.create(tenant=request.auth.tenant, ...)
# except IntegrityError -> 409
```

Design note: if idempotent create semantics are preferred (return existing on duplicate), switch to 200 with existing customer payload. Current choice is 409 to distinguish create from retrieve.

---

### 7. Soft Deletes, Settings Hardening, Security Headers

#### 7.1 Soft Deletes

| Model              | Soft delete? | Rationale                                      |
|--------------------|--------------|-------------------------------------------------|
| Customer           | Yes          | Undelete only. See uniqueness note below.       |
| Wallet             | Yes          | Cascades with Customer.                         |
| AutoTopUpConfig    | Yes          | Cascades with Customer.                         |
| TenantApiKey       | No           | `is_active` sufficient for deactivation.        |
| TopUpAttempt       | No           | Immutable financial record.                     |
| UsageEvent         | No           | Already immutable.                              |
| WalletTransaction  | No           | Immutable ledger.                               |
| Invoice            | No           | Immutable financial record.                     |
| StripeWebhookEvent | No           | Hard-deleted by retention task.                  |

**Uniqueness after soft delete — decision required:**

Option A: If re-creating a customer with the same `external_id` should be allowed after soft delete, change the unique constraint to a partial index:
```python
UniqueConstraint(
    fields=["tenant", "external_id"],
    condition=Q(deleted_at__isnull=True),
    name="uq_customer_tenant_external_id_active",
)
```

Option B: If soft-delete means "deactivated, never re-creatable with same external_id," keep the constraint unchanged and provide a "reactivate" endpoint instead. Document this decision.

**Ledger visibility:** Soft-deleted customers must remain visible to ledger and audit queries. Use `all_objects` or `with_deleted` manager for any code paths that query WalletTransaction, UsageEvent, Invoice, or Refund records. The default manager (which excludes deleted records) must NOT be used in ledger/audit/reconciliation contexts.

Customer soft-delete cascades to Wallet and `auto_top_up_config`:
```python
def delete(self, *args, **kwargs):
    with transaction.atomic():
        try:
            self.wallet.delete()  # soft delete
        except Wallet.DoesNotExist:
            pass
        try:
            self.auto_top_up_config.delete()  # soft delete
        except AutoTopUpConfig.DoesNotExist:
            pass
        super().delete(*args, **kwargs)
```

Uses `try/except DoesNotExist` instead of `hasattr` to avoid silently catching unrelated attribute errors.

Unit test confirms related rows have `deleted_at` set.

Soft-deleted customers return 404 on `record_usage` (default manager excludes deleted records).

**Library choice:** Vet `django-softdelete` vs `django-safedelete` (which has built-in cascade policies). Since cascade logic is already manual, a simple `SoftDeleteMixin` (just `deleted_at` + custom manager) may be sufficient and avoids external dependency risk.

#### 7.2 Settings Hardening (`config/settings.py`)

```python
SECRET_KEY = os.environ["SECRET_KEY"]  # KeyError = fail to start

_hosts = os.environ.get("ALLOWED_HOSTS", "")
ALLOWED_HOSTS = [h.strip() for h in _hosts.split(",") if h.strip()]
if not DEBUG and not ALLOWED_HOSTS:
    raise ImproperlyConfigured("ALLOWED_HOSTS must be set when DEBUG=False")

# Stripe keys validated in AppConfig.ready()
STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
```

#### 7.3 Security Headers and CORS

Add `django-cors-headers` to `requirements.txt`.

```python
MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",  # before CommonMiddleware
    ...
]

_cors = os.environ.get("CORS_ALLOWED_ORIGINS", "")
CORS_ALLOWED_ORIGINS = [o.strip() for o in _cors.split(",") if o.strip()]
CORS_ALLOW_CREDENTIALS = True

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

---

### 8. Missing Endpoints

#### 8.1 WalletTransaction Model Changes (`apps/customers/models.py`)

```python
+ idempotency_key = CharField(max_length=500, null=True, blank=True)

constraints = [
    UniqueConstraint(
        fields=["wallet", "idempotency_key"],
        condition=Q(idempotency_key__isnull=False) & ~Q(idempotency_key=""),
        name="uq_wallet_txn_idempotency",
    ),
]
```

Service layer normalizes empty strings to `None`: `idempotency_key = payload.idempotency_key.strip() or None`

#### 8.2 Refund Model (`apps/usage/models.py`)

```python
class Refund(BaseModel):
    tenant = ForeignKey(Tenant, related_name="refunds")
    customer = ForeignKey(Customer, related_name="refunds")
    usage_event = OneToOneField(UsageEvent, related_name="refund")  # enforces one refund per event
    wallet_transaction = ForeignKey(WalletTransaction, related_name="refund")
    reason = CharField(max_length=500)
    refunded_by_api_key = ForeignKey(TenantApiKey, on_delete=SET_NULL, null=True)
```

`UsageEvent` stays fully immutable. Refund state tracked on separate model.

**Note:** `refunded_by_api_key` is a FK to `TenantApiKey` (not free-text) for verifiable audit trails. The API key ID is captured from `request.auth` at request time.

Refund policy: non-invoiced usage events only. If `usage_event.invoice_id is not None`, return 422 with message: "Cannot refund invoiced usage. Credit note support not yet available."

#### 8.3 Endpoints

**`POST /customers/{customer_id}/withdraw`**

```python
class WithdrawRequest(Schema):
    amount_micros: int = Field(gt=0, le=999_999_999_999)
    description: str = Field(min_length=1, max_length=500)
    idempotency_key: str = Field(min_length=1, max_length=500)
```

- Fetches customer via `Customer.objects.get(id=customer_id, tenant=request.auth.tenant)`
- Checks `wallet.balance_micros >= amount_micros` (no negative balance for withdrawals)
- Uses `_idempotent_wallet_operation` pattern
- Returns 200 with transaction details (both new and retry)

**`POST /customers/{customer_id}/refund`**

```python
class RefundRequest(Schema):
    usage_event_id: UUID
    reason: str = Field(min_length=1, max_length=500)
    idempotency_key: str = Field(min_length=1, max_length=500)
```

Flow:
1. Validate `usage_event.tenant == request.auth.tenant`
2. Check `usage_event.invoice_id is None` (non-invoiced only, else 422)
3. Check for existing `Refund` on this usage event — return 200 if exists
4. `lock_for_billing(customer_id)`
5. Check `WalletTransaction` idempotency key — return 200 if exists
6. Create transaction + refund + credit wallet
7. Catch `IntegrityError` on OneToOne collision — return existing refund (200)

Three layers of idempotency: existing Refund check, WalletTransaction key, IntegrityError catch.

**`GET /customers/{customer_id}/transactions`**

```python
class TransactionListParams(Schema):
    limit: int = Field(default=50, ge=1, le=100)
    cursor: Optional[str] = None
    transaction_type: Optional[Literal[
        "USAGE_DEDUCTION", "TOP_UP", "WITHDRAWAL", "REFUND"
    ]] = None
```

Cursor pagination with `(created_at, id)` tie-breaker, same pattern as usage list. `Literal` type validates `transaction_type` automatically — invalid values return 422.

**Endpoints NOT added (YAGNI):** partial refunds, bulk operations, admin override endpoints.

---

## Cross-Cutting Operational Requirements

### 9. Rate Limiting

Add per-tenant and per-endpoint rate limits before production:
- Per-tenant rate limit via Django middleware + Redis
- Per-endpoint rate limits (usage recording will be highest volume)
- Return `429 Too Many Requests` with `Retry-After` header

### 10. Health and Readiness Endpoints

- `GET /health` — basic liveness (returns 200)
- `GET /ready` — readiness check (DB connection, Redis connection, Stripe API reachable)
- Required for Kubernetes/ECS health probes and zero-downtime deploys

### 11. Celery Failure Handling

- Define behavior on max retries exhausted: dead-letter queue or alert (not silent discard)
- Set `acks_late = True` on all financial tasks (not just `charge_auto_topup_task`)
- Consider `task_reject_on_worker_lost = True` for financial tasks to ensure redelivery on worker crash
- Invoicing tasks that fail after max retries should alert and leave the BillingPeriod in `open` status for manual retry

### 12. Stripe Reconciliation

Add a periodic reconciliation task that compares the local ledger against Stripe's actual state:
- List recent Stripe charges and compare to local TopUpAttempt/WalletTransaction records
- List recent Stripe invoices and compare to local Invoice records
- Flag any discrepancies (charge succeeded in Stripe but no local credit, invoice paid but not updated locally)
- Detect refunds initiated in Stripe dashboard that the system doesn't know about
- Log results as immutable audit entries; alert on any drift

---

## Celery Queue Configuration

```python
CELERY_TASK_QUEUES = [
    Queue("ubb_invoicing"),
    Queue("ubb_webhooks"),
    Queue("ubb_topups"),
]
```

Task routing:
- `charge_auto_topup_task` -> `ubb_topups`
- `cleanup_webhook_events` -> `ubb_webhooks`
- `expire_stale_topup_attempts` -> `ubb_topups`
- `reconcile_wallet_balances` -> `ubb_invoicing`
- `reconcile_stripe_state` -> `ubb_invoicing`
- Invoicing tasks -> `ubb_invoicing`

---

## Ledger-Grade Requirements

This is a billing platform that handles real money. The following requirements go beyond "production web app" into financial system territory.

### L1. Wallet Balance Integrity (Required before production)

`wallet.balance_micros` is a **performance cache**. `WalletTransaction` is the **source of truth**.

All balance changes must go through `WalletTransaction` creation within the same DB transaction as the `balance_micros` update. No code path may update `balance_micros` without a corresponding ledger entry.

**Reconciliation task:** A periodic task recomputes `SUM(amount_micros)` from `WalletTransaction` for each wallet and compares to `wallet.balance_micros`. Any drift triggers an alert and is treated as a production incident. The reconciliation result is logged as an immutable audit entry.

### L2. Double-Entry Discipline (Decision required)

Current design uses single-sided wallet deltas. For a true ledger, consider explicit debit/credit postings with balanced journal entries per business event. Every transaction balances to zero across accounts.

**Decision:** If deferring double-entry, document why and the upgrade path. Single-sided deltas with reconciliation (L1) are acceptable for initial production if the reconciliation task runs frequently (e.g., hourly).

### L3. Monotonic Ledger Sequence (Recommended)

Add a monotonically increasing sequence number per wallet on `WalletTransaction`:

```python
sequence_number = PositiveIntegerField()
# UniqueConstraint(fields=["wallet", "sequence_number"])
```

Enables:
- **No-gaps checks**: sequence 5 and 7 exist but 6 doesn't → something went wrong
- **Ordering guarantees**: `created_at` can have ties; sequence numbers cannot
- **Audit proof**: demonstrates completeness of the ledger

### L4. Immutable Billing Snapshot (Recommended)

When invoicing, record the exact set of usage event IDs and totals in a snapshot (e.g., JSON blob on the Invoice model). This makes invoices provable even if the query to reconstruct them changes. The current `invoice_id` FK on UsageEvent is good but relies on the link being maintained.

### L5. External Stripe Reconciliation (Required)

See section 12. Periodic task to compare local ledger against Stripe's actual state. Catches:
- Charges that succeeded in Stripe but were never recorded locally (crash scenarios)
- Invoices paid in Stripe but not updated locally (webhook failures)
- Refunds initiated in Stripe dashboard

### L6. Idempotency Coverage Audit (Required)

Confirm every money-touching path is idempotent end-to-end:
- Usage recording ✓ (idempotency_key on UsageEvent)
- Top-up charge ✓ (TopUpAttempt + Stripe idempotency key)
- Top-up checkout ✓ (TopUpAttempt + Stripe idempotency key)
- Invoice creation ✓ (invoice_attempt_number)
- Refund ✓ (three layers)
- Withdrawal ✓ (WalletTransaction idempotency_key)
- **Auto-topup wallet credit after charge** — verify this is idempotent if the same charge result is processed by both the Celery task and a webhook (status check in both paths should handle this)

### L7. Rounding Rules (Required)

Define and enforce rounding rules at every money boundary:
- `micros ÷ 10,000 → cents` conversion: define rule (round half-up, truncate, or reject non-even amounts)
- Usage pricing: `ProviderRate.calculate_cost_micros` uses round-half-up — document this
- Invoice totals: sum then convert, or convert then sum? Document and test
- Apply consistent `le=999_999_999_999` bounds on all `amount_micros` / `cost_micros` fields

### L8. Multi-Currency Stance (Document)

Even if USD-only now, codify `currency` in every ledger row and enforce consistency at the service layer. Prevent future migration nightmare.

### L9. Table Growth / Partitioning Strategy (Document)

`UsageEvent` and `WalletTransaction` will be the fastest-growing tables. Document:
- Expected row growth rate
- When partitioning (by `effective_at` / `created_at`) becomes necessary
- Archiving strategy for old rows

---

## Ledger-Specific Tests

- **Reconciliation test**: recompute balance from `SUM(WalletTransaction.amount_micros)` vs stored `wallet.balance_micros` — must match
- **Replay test**: reprocess the same Stripe event twice and assert no balance drift
- **Out-of-order webhook test**: process `invoice.paid` before `invoice.created` — ensure the event is retried (not dropped)
- **Crash recovery test**: force failure after ledger entry insert but before balance update — verify atomicity prevented partial state
- **Overflow test**: exercise maximum `cost_micros` and `amount_micros` values through all arithmetic paths
- **Rounding test**: verify micros-to-cents conversion at boundary values (e.g., amounts not evenly divisible by 10,000)

---

## New Files Summary

| File | Purpose |
|------|---------|
| `core/exceptions.py` | `StripeTransientError`, `StripePaymentError`, `StripeFatalError` |
| `core/locking.py` | `lock_for_billing()`, `lock_customer()`, `lock_top_up_attempt()`, `lock_invoice()` |
| `core/logging.py` | `correlation_id_var`, `CorrelationIdFilter`, `RedactingFilter`, `JsonFormatter` |
| `core/middleware.py` | Correlation ID middleware |
| `apps/stripe_integration/models.py` | `StripeWebhookEvent` |
| `apps/stripe_integration/management/commands/reprocess_webhook.py` | Management command |
| `apps/stripe_integration/tasks.py` | `reconcile_stripe_state` task |
| `apps/customers/tasks.py` | `expire_stale_topup_attempts`, `reconcile_wallet_balances` tasks |

## Modified Files Summary

| File | Changes |
|------|---------|
| `apps/customers/models.py` | `TopUpAttempt` model (with `expired` status), `WalletTransaction.idempotency_key`, soft delete on Customer/Wallet/AutoTopUpConfig |
| `apps/usage/models.py` | `Refund` model (with `refunded_by_api_key` FK), `BillingPeriod.invoice_attempt_number`, new indexes |
| `apps/stripe_integration/services/stripe_service.py` | `stripe_call()` wrapper, idempotency keys, error handling, input validation, inline retry with backoff+jitter |
| `apps/usage/services/usage_service.py` | Lock ordering via helpers, `transaction.on_commit` for auto-topup, savepoint for IntegrityError |
| `apps/usage/services/auto_topup_service.py` | Receives locked wallet, creates pending TopUpAttempt with savepoint |
| `api/v1/webhooks.py` | Event dedup, CAS retry (30m TTL), `ObjectDoesNotExist` as retryable, error classification, batched cleanup |
| `api/v1/endpoints.py` | Cursor pagination (`+00:00` format), input validation, new endpoints, tenant scoping, health/ready |
| `api/v1/schemas.py` | Validation constraints, pagination params, new request schemas |
| `config/settings.py` | `LOGGING` (redacting filter last), security headers, settings hardening, Celery queues, CORS filtering |
| `config/celery.py` | Correlation ID propagation via task signals |
| `requirements.txt` | `django-softdelete` (or alternative — see 7.1), `django-cors-headers` |
