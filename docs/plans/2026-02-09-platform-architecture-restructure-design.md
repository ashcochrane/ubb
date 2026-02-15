# Platform Architecture Restructure Design

**Date:** 2026-02-09
**Status:** Draft
**Scope:** Full architectural restructure to make billing and referrals independently sellable products

## Context

A codebase audit against the product intent identified the following gaps:

- No "spend-tracker-only" customer type (Type B) -- the entire usage path deducts from a wallet
- Legacy `/api/v1/` endpoints bypass product access gating
- Wallet/billing models live in the shared platform layer instead of billing
- Stripe is hardcoded with no payment provider abstraction
- The event bus is synchronous, swallows errors, and loses failed events
- Referrals has no payout export, no fraud prevention, and no Celery wiring
- No outgoing webhook system for tenant integrations
- Cross-product imports exist in reconciliation code and core/locking.py

This design addresses all of these by restructuring the codebase so that products are fully independent building blocks communicating exclusively through a transactional outbox.

## Target Architecture

### Dependency Graph

```
                  core/
           (pure utilities, zero domain imports)
                    |
              apps/platform/
        (tenants, customers, events/outbox,
              tenant_billing)
                    |
    +----------+----+----------+----------+
    |          |               |          |
 metering   billing      subscriptions  referrals
```

Zero cross-product imports. Every product depends only on platform + core. All cross-product communication goes through the outbox.

### Data Flow

```
SDK: POST /metering/usage
  -> MeteringService.record_usage()
    -> Creates UsageEvent (atomic)
    -> Writes OutboxEvent (same transaction)
    -> transaction.on_commit -> Celery task

Outbox processing (seconds later):
  -> Billing handler: lock wallet, deduct, check arrears
  -> Subscriptions handler: accumulate CustomerCostAccumulator
  -> Referrals handler: calculate reward, accumulate
  -> Tenant webhook delivery: notify customer's system

Platform fee aggregation (monthly):
  -> Each product's handler accumulates into TenantBillingPeriod
  -> close_period() collects ProductFeeConfig per product
  -> Generates TenantInvoice with per-product LineItems
  -> Charges via PaymentProvider (Stripe)
```

### Target File Structure

```
ubb-platform/
  core/
    __init__.py
    auth.py              # ApiKeyAuth, ProductAccess
    locking.py           # Generic lock_row() -- zero domain imports
    models.py            # BaseModel (abstract)
    soft_delete.py       # SoftDeleteMixin
    logging.py           # Structured logging, correlation IDs
    middleware.py        # CorrelationIdMiddleware
    exceptions.py        # UBBError hierarchy

  apps/
    platform/
      tenants/           # Tenant, TenantApiKey
      customers/         # Customer only (no wallet/billing models)
      tenant_billing/    # TenantBillingPeriod, TenantInvoice, LineItems, ProductFeeConfig
      events/            # OutboxEvent, HandlerCheckpoint, schemas, webhooks
        models.py        #   OutboxEvent, HandlerCheckpoint,
                         #   TenantWebhookConfig, TenantWebhookDelivery
        schemas.py       #   Frozen dataclasses per event type (contracts)
        outbox.py        #   write_event(), dispatch_to_handlers()
        registry.py      #   Handler registration
        webhooks.py      #   Outgoing tenant webhook delivery
        tasks.py         #   process_single_event, sweep, cleanup, deliver_webhook
        api/
          endpoints.py           # Admin: failed events, retry, skip, replay
          webhook_config_endpoints.py  # Tenant webhook CRUD

    metering/
      usage/             # UsageEvent, Invoice, Refund, UsageService
      pricing/           # ProviderRate, TenantMarkup, PricingService

    billing/
      wallets/           # Wallet, WalletTransaction, WalletService
      topups/            # AutoTopUpConfig, TopUpAttempt, AutoTopUpService
      gating/            # RiskConfig, RiskService
      invoicing/         # ReceiptService (no models)
      payments/          # PaymentProvider protocol + StripeProvider
      stripe/            # StripeWebhookEvent, webhook handling
      handlers.py        # Outbox: wallet deduction, fee accumulation
      api/
        endpoints.py     # All billing endpoints

    subscriptions/
      models.py          # StripeSubscription, SubscriptionInvoice
      economics/         # CustomerCostAccumulator, CustomerEconomics, EconomicsService
      stripe/            # sync.py
      handlers.py        # Outbox: cost accumulation
      api/
        endpoints.py
        webhooks.py

    referrals/
      models.py          # ReferralProgram, Referrer, Referral
      rewards/           # Accumulator, Ledger, RewardService, reconciliation
      handlers.py        # Outbox: reward accumulation, fee accumulation
      api/
        endpoints.py     # Includes payout export

  api/
    v1/
      endpoints.py             # Health + ready only
      platform_endpoints.py    # Customer CRUD (shared)
      metering_endpoints.py    # Metering API
      billing_endpoints.py     # Billing API
```

---

## 1. Product Model and Fee Architecture

### Product gating

`Tenant.products` remains a JSONField. Add validation:

- `"metering"` must always be present
- No unknown product names (valid: `metering`, `billing`, `subscriptions`, `referrals`)
- Stored as a sorted, deduplicated list

Validation enforced in `Tenant.clean()`.

### Customer types

- **Type A (cost-plus billing):** `products` includes `"billing"`. Full wallet, Stripe Connect, auto-charge, arrears/suspension, % throughput platform fee.
- **Type B (spend tracker):** `products` does not include `"billing"`. Usage recording without wallet deduction. No Stripe Connect required. Flat monthly platform fee.
- Both types can optionally add `"subscriptions"` and/or `"referrals"`.

### Per-product fee configuration

New `ProductFeeConfig` model in `apps/platform/tenant_billing/`:

```python
class ProductFeeConfig(BaseModel):
    tenant = FK(Tenant)
    product = CharField(100)       # "metering", "billing", "referrals"
    fee_type = CharField(100)      # extensible: "percentage", "flat_monthly", etc.
    config = JSONField()           # fee-type-specific params

    class Meta:
        unique_together = ("tenant", "product")
```

Fee config examples:

| Product | fee_type | config |
|---|---|---|
| billing | `percentage` | `{"percentage": "1.00"}` |
| metering (Type B) | `flat_monthly` | `{"amount_micros": 49000000}` |
| referrals | `percentage_of_payouts` | `{"percentage": "5.00"}` |
| referrals | `flat_per_referral` | `{"amount_micros": 500000}` |

Each product's service reads its own `ProductFeeConfig` row and computes the fee. `TenantBillingService` aggregates all product fees into line items on a single `TenantInvoice`.

`Tenant.platform_fee_percentage` is removed. Existing values are migrated to `ProductFeeConfig(product="billing", fee_type="percentage")` rows.

### Invoice line items

New `TenantInvoiceLineItem` model:

```python
class TenantInvoiceLineItem(BaseModel):
    invoice = FK(TenantInvoice, related_name="line_items")
    product = CharField(100)
    description = CharField(255)   # "Usage throughput fee (1.00%)"
    amount_micros = BigIntegerField
```

---

## 2. Usage Recording Path

`UsageService.record_usage()` is bifurcated based on whether the tenant has `"billing"` in products.

### Type A flow (tenant has `"billing"`)

1. Idempotency check
2. Price the event (if `usage_metrics` provided)
3. Create immutable `UsageEvent`
4. Write `OutboxEvent` (same transaction)
5. `transaction.on_commit` dispatches Celery task
6. Return result

Wallet deduction happens asynchronously via billing's outbox handler.

### Type B flow (tenant does NOT have `"billing"`)

Identical to Type A. Without `"billing"` in products, the billing outbox handler is skipped (product gating). No wallet deduction occurs.

The only behavioral difference is that billing's handler does not fire. The usage recording path itself is identical for both types.

### Key changes

- `UsageService.record_usage()` no longer calls `Wallet.deduct()` directly. It records the event and writes to the outbox. Wallet deduction is billing's responsibility via the outbox handler.
- `Customer.save()` no longer auto-creates a `Wallet`. Wallet creation happens when a tenant activates the billing product.
- `balance_after_micros` on `UsageEvent` is set by billing's handler (or left null for Type B).

---

## 3. Transactional Outbox

Replaces `core/event_bus.py` entirely. Located in `apps/platform/events/`.

### OutboxEvent model

```python
class OutboxEvent(BaseModel):
    event_type = CharField(100, db_index=True)
    payload = JSONField()
    tenant_id = UUIDField(db_index=True)

    status = CharField(20, db_index=True)   # pending/processing/processed/failed
    retry_count = IntegerField(default=0)
    max_retries = IntegerField(default=5)
    next_retry_at = DateTimeField(null=True, db_index=True)
    last_error = TextField(blank=True)
    processed_at = DateTimeField(null=True)
    correlation_id = CharField(100, blank=True)

    class Meta:
        indexes = [
            Index(fields=["status", "next_retry_at"]),
            Index(fields=["status", "created_at"]),
            Index(fields=["tenant_id", "event_type", "created_at"]),
        ]
```

### Event schema contracts

Each event type has a frozen dataclass in `apps/platform/events/schemas.py`. New fields always have defaults (additive-only evolution, no versioning needed).

```python
@dataclass(frozen=True)
class UsageRecorded:
    EVENT_TYPE = "usage.recorded"

    tenant_id: str
    customer_id: str
    event_id: str
    cost_micros: int
    provider_cost_micros: int | None = None
    billed_cost_micros: int | None = None
    event_type: str = ""
    provider: str = ""
```

Producers construct the dataclass (validates at creation) and write `asdict()` to the outbox. Consumers reconstruct via `UsageRecorded(**payload)` -- missing fields get defaults, extra fields are handled gracefully.

Breaking changes (field renames, type changes, field removals) require a new schema class with a version suffix. Additive changes (new fields with defaults) do not.

### Writing events

```python
def write_event(schema_instance):
    outbox = OutboxEvent.objects.create(
        event_type=schema_instance.EVENT_TYPE,
        payload=asdict(schema_instance),
        tenant_id=schema_instance.tenant_id,
        correlation_id=get_current_correlation_id(),
    )
    transaction.on_commit(
        lambda: process_single_event.delay(str(outbox.id))
    )
```

Written inside the same `@transaction.atomic` as the domain change. If the transaction rolls back, the event disappears. If it commits, the event is guaranteed to exist.

### Processing events

Two mechanisms (belt and suspenders):

1. **Immediate:** `transaction.on_commit()` dispatches a Celery task for the specific event. Happy path latency: seconds.
2. **Sweep:** Celery beat task runs every minute. Picks up pending events with `next_retry_at` in the past, and reclaims stuck `processing` events older than 5 minutes.

Each event gets its own Celery task. A poison pill fails on its own schedule without blocking other events.

```python
@shared_task(queue="ubb_events", bind=True, max_retries=0)
def process_single_event(self, event_id):
    event = OutboxEvent.objects.select_for_update(skip_locked=True).get(id=event_id)

    if event.status != "pending":
        return

    event.status = "processing"
    event.save(update_fields=["status", "updated_at"])

    try:
        dispatch_to_handlers(event)
        event.status = "processed"
        event.processed_at = now()
    except Exception as e:
        event.retry_count += 1
        event.last_error = str(e)[:2000]
        if event.retry_count >= event.max_retries:
            event.status = "failed"
            alert_dead_letter(event)
        else:
            event.status = "pending"
            event.next_retry_at = calculate_backoff(event.retry_count)

    event.save()
```

`select_for_update(skip_locked=True)` prevents double processing when immediate dispatch and sweep race.

Backoff schedule: 30s, 2m, 10m, 30m, 2h.

### Idempotent handlers

At-least-once delivery means handlers must be idempotent. Each handler tracks processed events:

```python
class HandlerCheckpoint(BaseModel):
    outbox_event = ForeignKey(OutboxEvent, CASCADE)
    handler_name = CharField(100)

    class Meta:
        unique_together = ("outbox_event", "handler_name")
```

Handler wrapper:

```python
def idempotent_handler(handler_name, event_id, fn, payload):
    if HandlerCheckpoint.objects.filter(
        outbox_event_id=event_id, handler_name=handler_name
    ).exists():
        return  # already processed

    fn(payload)

    HandlerCheckpoint.objects.create(
        outbox_event_id=event_id, handler_name=handler_name
    )
```

### Dead letter handling

When an event reaches `max_retries`:

1. Status set to `"failed"`
2. `alert_dead_letter(event)` sends to configured alert channel (CRITICAL log, optional Slack/PagerDuty webhook)
3. Alert includes: event type, tenant ID, retry count, last error, correlation ID

Admin resolution endpoints in `apps/platform/events/api/`:

| Endpoint | Purpose |
|---|---|
| `GET /platform/events/failed` | List failed events (filterable by tenant/type/date) |
| `POST /platform/events/{id}/retry` | Reset failed event to pending |
| `POST /platform/events/{id}/skip` | Mark as skipped (operator decision) |
| `POST /platform/events/replay` | Replay a range of events by type + date range |

Documented resolution per failure type:

| Failed handler | Business impact | Resolution |
|---|---|---|
| Billing wallet deduction | Customer used API without being charged | Retry event or manually deduct via billing admin API |
| Billing fee accumulation | Platform fee undercount for the period | Retry event; reconciliation also catches this |
| Subscriptions cost accumulation | Economics slightly off for the period | Retry event; next calculation run self-corrects |
| Referrals reward accumulation | Referrer not credited for one event | Retry event; batch reconciliation also catches this |

### Outbox cleanup

Daily Celery beat task:

- Delete `processed` events older than 30 days
- Delete `skipped` events older than 90 days
- `failed` events are never auto-deleted; they require operator action
- `HandlerCheckpoint` rows cascade-delete with their `OutboxEvent`

### Handler registration

Products register handlers in `AppConfig.ready()`, same pattern as the current event bus. Product gating (`requires_product`) works identically -- the outbox dispatcher checks `tenant.products` (cached) before invoking each handler.

### Events and handlers

| Event | Handler | Product gate | Action |
|---|---|---|---|
| `usage.recorded` | billing | `billing` | Lock wallet, deduct, check arrears, auto-topup, accumulate billing period |
| `usage.recorded` | subscriptions | `subscriptions` | Accumulate `CustomerCostAccumulator` |
| `usage.recorded` | referrals | `referrals` | Calculate + accumulate referral reward |
| `usage.refunded` | billing | `billing` | Credit wallet |
| `referral.created` | (future) | -- | Audit / external integration |
| `referral.reward_earned` | referrals | `referrals` | Accumulate referrals platform fee |
| `referral.expired` | (future) | -- | Audit / external integration |

### What gets deleted

`core/event_bus.py` is removed entirely. The `EventBus` class, synchronous dispatch, and error swallowing are all gone.

---

## 4. Model Relocation

### Wallet models to `apps/billing/wallets/`

`Wallet` and `WalletTransaction` move from `apps/platform/customers/models.py` to `apps/billing/wallets/models.py`.

These are billing primitives (balance, deductions, credits). Type B tenants don't have wallets. They don't belong in the shared platform layer.

`Customer.save()` no longer auto-creates a `Wallet`. Wallet creation happens when a tenant activates the billing product.

Django migration strategy: `SeparateDatabaseAndState` in both apps. New app model sets `db_table = "ubb_wallet"` explicitly. The actual DB table doesn't change.

New billing wallet service in `apps/billing/wallets/services.py`:

```python
class WalletService:
    @staticmethod
    def lock_and_deduct(customer_id, amount_micros, idempotency_key):
        wallet = lock_row(Wallet, customer_id=customer_id)
        # deduct, create WalletTransaction, check arrears...

    @staticmethod
    def credit(customer_id, amount_micros, transaction_type, idempotency_key):
        wallet = lock_row(Wallet, customer_id=customer_id)
        # credit, create WalletTransaction...
```

### TopUp models to `apps/billing/topups/`

`AutoTopUpConfig` and `TopUpAttempt` move from `apps/platform/customers/models.py` to `apps/billing/topups/models.py`.

`AutoTopUpService` moves from `apps/metering/usage/services/` to `apps/billing/topups/services.py`.

Same migration strategy.

### `tenant_billing/` to `apps/platform/tenant_billing/`

With `ProductFeeConfig`, tenant billing aggregates fees from ALL products. It's shared platform infrastructure, not billing-specific.

Moves from `apps/billing/tenant_billing/` to `apps/platform/tenant_billing/`.

### Remove `Tenant.platform_fee_percentage`

Migrated to `ProductFeeConfig(product="billing", fee_type="percentage")` rows. Column dropped after migration.

### `core/locking.py` to generic utility

Core provides a generic locking utility with zero domain imports:

```python
# core/locking.py
def lock_row(model_class, **lookup):
    """Acquire a row lock. Must be inside @transaction.atomic."""
    return model_class.objects.select_for_update().get(**lookup)
```

Product-specific locking helpers move to their respective products. Billing's `lock_for_billing()` moves to `apps/billing/wallets/services.py`.

### Remove Invoice re-export

`billing/invoicing/models.py` currently re-exports `Invoice` from metering. Remove the re-export. Invoice stays in metering. `ReceiptService` imports `Invoice` from metering -- acceptable since billing depends on platform + core (and metering models are accessed read-only for receipt generation).

### `apps/platform/customers/models.py` after relocation

Contains only the shared `Customer` model:

```python
class Customer(SoftDeleteMixin, BaseModel):
    tenant = FK(Tenant)
    external_id = CharField(255)
    stripe_customer_id = CharField(255, blank=True)
    status = CharField(choices=["active", "suspended", "closed"])
    arrears_threshold_micros = BigIntegerField(null=True)
    metadata = JSONField
```

No wallet, no top-up, no billing concepts.

---

## 5. Payment Provider Abstraction

### Protocol-based interface

```python
# apps/billing/payments/protocol.py
from typing import Protocol

class PaymentProvider(Protocol):
    def create_checkout_session(
        self, connected_account_id: str, customer_id: str,
        amount_micros: int, idempotency_key: str,
        success_url: str, cancel_url: str,
    ) -> str: ...

    def charge_saved_payment_method(
        self, connected_account_id: str, customer_id: str,
        amount_micros: int, idempotency_key: str,
    ) -> str: ...

    def create_platform_invoice(
        self, platform_customer_id: str,
        line_items: list[dict], idempotency_key: str,
    ) -> str: ...

    def verify_webhook_signature(
        self, payload: bytes, signature: str, secret: str,
    ) -> dict: ...
```

### Stripe implementation

`StripeProvider` in `apps/billing/payments/stripe_provider.py` absorbs the current `StripeService`. The `stripe_call()` retry wrapper stays inside the provider.

### Wiring

```python
# config/settings.py
PAYMENT_PROVIDER = "stripe"

# apps/billing/payments/__init__.py
def get_payment_provider() -> PaymentProvider:
    if settings.PAYMENT_PROVIDER == "stripe":
        from apps.billing.payments.stripe_provider import StripeProvider
        return StripeProvider()
    raise ValueError(f"Unknown provider: {settings.PAYMENT_PROVIDER}")
```

All billing code calls `get_payment_provider()` instead of importing Stripe directly.

### What this does NOT do (YAGNI)

- No adapter registry, no plugin system, no dynamic loading
- No multi-provider per tenant (one provider for the whole platform)
- No abstract webhook handler (webhooks are too provider-specific)

### File structure

```
apps/billing/
    payments/
        __init__.py        # get_payment_provider()
        protocol.py        # PaymentProvider Protocol
        stripe_provider.py # StripeProvider
    stripe/
        models.py          # StripeWebhookEvent (Stripe-specific, stays)
        webhooks.py        # Stripe webhook handling (stays)
        tasks.py           # cleanup_webhook_events (stays)
```

---

## 6. Legacy API Deprecation + SDK Changes

### Legacy endpoint disposition

| Legacy endpoint | Disposition | Replacement |
|---|---|---|
| `GET /api/v1/health` | Keep | Stays in `api/v1/endpoints.py` |
| `GET /api/v1/ready` | Keep | Stays |
| `POST /api/v1/customers` | Move to platform | `POST /api/v1/platform/customers` |
| `POST /api/v1/usage` | Remove | `POST /api/v1/metering/usage` |
| `POST /api/v1/pre-check` | Remove | `POST /api/v1/billing/pre-check` |
| `GET /customers/{id}/balance` | Remove | `GET /api/v1/billing/customers/{id}/balance` |
| `GET /customers/{id}/usage` | Remove | `GET /api/v1/metering/customers/{id}/usage` |
| `PUT /customers/{id}/auto-top-up` | Remove | `PUT /api/v1/billing/customers/{id}/auto-top-up` |
| `POST /customers/{id}/top-up` | Remove | `POST /api/v1/billing/customers/{id}/top-up` |
| `POST /customers/{id}/withdraw` | Remove | `POST /api/v1/billing/customers/{id}/withdraw` |
| `POST /customers/{id}/refund` | Remove | `POST /api/v1/billing/customers/{id}/refund` |
| `GET /customers/{id}/transactions` | Remove | `GET /api/v1/billing/customers/{id}/transactions` |

After this, `api/v1/endpoints.py` contains only `/health` and `/ready`.

### New platform API

`api/v1/platform_endpoints.py` handles customer CRUD. Mounted at `/api/v1/platform/`. Gated by `ApiKeyAuth` only -- any authenticated tenant can create customers.

### SDK changes

`UBBClient` becomes a thin facade that delegates to product clients. The legacy `self._http` client is removed entirely.

Methods that require a product client raise `UBBError` if the client is not enabled:

```python
def get_balance(self, customer_id: str) -> BalanceResult:
    if not self.billing:
        raise UBBError("get_balance requires billing=True")
    return self.billing.get_balance(customer_id)
```

`SubscriptionsClient` is added to `ubb/__init__.py` exports.

---

## 7. Referrals Completion

### Payout instruction export

New endpoint: `GET /api/v1/referrals/payouts/export`

Returns a structured payout report for a given period with:
- Per-referrer breakdown of earned amounts
- Per-referral detail (referred customer, earned amount, calculation method)
- Summary totals (total payout, referrer count, referral count)
- Platform fee breakdown (fee type, percentage, amount)

Supports `Accept: text/csv` header for CSV download.

### Platform fee for referrals

Referrals fee handler consumes `referral.reward_earned` outbox events. Reads `ProductFeeConfig` for the tenant's referrals fee configuration. Accumulates platform fee into `TenantBillingPeriod`. During period close, referrals contributes a `TenantInvoiceLineItem`.

### Fraud prevention basics

New fields on `ReferralProgram`:

- `max_referrals_per_day` -- IntegerField, default 50. Velocity limit per referrer.
- `min_customer_age_hours` -- IntegerField, default 0. Referred customer must have been created at least N hours ago.

The attribution endpoint checks both before creating a referral. Returns 429 for velocity limit, 400 for customer age.

### Analytics fix

`GET /analytics/earnings` endpoint: wire up `period_start`/`period_end` query parameters to actually filter the query (currently accepted but ignored).

---

## 8. Outgoing Tenant Webhooks

Platform-level feature in `apps/platform/events/`. When an internal outbox event fires, check if the tenant has subscribed to that event type. If yes, send a signed HTTP POST.

### Models

```python
class TenantWebhookConfig(BaseModel):
    tenant = FK(Tenant)
    url = URLField()
    secret = CharField(64)              # HMAC-SHA256 signing
    event_types = JSONField()           # ["referral.reward_earned", "usage.recorded"]
    is_active = BooleanField(default=True)

class TenantWebhookDelivery(BaseModel):
    config = FK(TenantWebhookConfig)
    outbox_event = FK(OutboxEvent)
    status = CharField(20)              # pending/delivered/failed
    response_status = IntegerField(null=True)
    retry_count = IntegerField(default=0)
    next_retry_at = DateTimeField(null=True)
```

### Flow

1. Outbox event is processed (product handlers run)
2. After handlers succeed, check for matching `TenantWebhookConfig` rows
3. Create `TenantWebhookDelivery` for each matching config
4. Dispatch `deliver_webhook.delay(delivery_id)` Celery task
5. Task sends signed HTTP POST to tenant's URL
6. Retries with backoff on failure

### Payload format

```json
{
  "event_type": "referral.reward_earned",
  "timestamp": "2026-02-09T14:30:00Z",
  "data": {
    "referral_id": "...",
    "referrer_customer_id": "...",
    "referred_customer_id": "...",
    "reward_micros": 500000,
    "total_earned_micros": 4500000,
    "calculation_method": "actual_cost"
  }
}
```

Signed with HMAC-SHA256 using the tenant's webhook secret, sent in `X-UBB-Signature` header.

### Subscribable events

| Event | Product | When it fires |
|---|---|---|
| `usage.recorded` | metering | Every usage event (high volume) |
| `usage.refunded` | metering | Usage event refunded |
| `customer.suspended` | billing | Customer crosses arrears threshold |
| `customer.topup.completed` | billing | Top-up succeeds |
| `referral.created` | referrals | New referral attributed |
| `referral.reward_earned` | referrals | Reward calculated |
| `referral.expired` | referrals | Referral window closed |
| `subscription.updated` | subscriptions | Stripe subscription status change |

---

## 9. Celery Configuration

### New queues

```python
CELERY_TASK_QUEUES = [
    Queue("ubb_invoicing"),
    Queue("ubb_webhooks"),
    Queue("ubb_topups"),
    Queue("ubb_billing"),
    Queue("ubb_events"),         # outbox processing
    Queue("ubb_economics"),      # subscriptions
    Queue("ubb_subscriptions"),  # subscription sync
    Queue("ubb_referrals"),      # referral reconciliation
]
```

### New beat schedule entries

```python
CELERY_BEAT_SCHEDULE = {
    # ... existing entries ...

    # Outbox
    "sweep-outbox": {
        "task": "apps.platform.events.tasks.sweep_outbox",
        "schedule": crontab(minute="*/1"),
    },
    "cleanup-outbox": {
        "task": "apps.platform.events.tasks.cleanup_outbox",
        "schedule": crontab(minute=0, hour=4),
    },

    # Subscriptions
    "calculate-all-economics": {
        "task": "apps.subscriptions.tasks.calculate_all_economics_task",
        "schedule": crontab(minute=0, hour=2),
    },

    # Referrals
    "reconcile-all-referrals": {
        "task": "apps.referrals.tasks.reconcile_all_referrals_task",
        "schedule": crontab(minute=0, hour=3),
    },
}
```

### New settings

```python
STRIPE_SUBSCRIPTIONS_WEBHOOK_SECRET = os.environ.get(
    "STRIPE_SUBSCRIPTIONS_WEBHOOK_SECRET", ""
)
```

---

## 10. Complete Change List

| # | Change | Section |
|---|---|---|
| 1 | Add `Tenant.products` validation | 1 |
| 2 | Add `ProductFeeConfig` model | 1 |
| 3 | Remove `Tenant.platform_fee_percentage` (migrate to ProductFeeConfig) | 1 |
| 4 | Add `TenantInvoiceLineItem` model | 1 |
| 5 | Remove wallet deduction from `UsageService.record_usage()` | 2 |
| 6 | Stop auto-creating Wallet on Customer save | 2 |
| 7 | Create `apps/platform/events/` app | 3 |
| 8 | Create `OutboxEvent` and `HandlerCheckpoint` models | 3 |
| 9 | Create event schema dataclasses | 3 |
| 10 | Build outbox processing (per-event Celery tasks, sweep, cleanup) | 3 |
| 11 | Build idempotent handler wrapper | 3 |
| 12 | Build dead letter alerting + admin endpoints | 3 |
| 13 | Delete `core/event_bus.py` | 3 |
| 14 | Rewrite all product handlers as outbox consumers | 3 |
| 15 | Move Wallet, WalletTransaction to `billing/wallets/` | 4 |
| 16 | Move AutoTopUpConfig, TopUpAttempt to `billing/topups/` | 4 |
| 17 | Move `tenant_billing/` to `platform/tenant_billing/` | 4 |
| 18 | Refactor `core/locking.py` to generic `lock_row()` | 4 |
| 19 | Remove Invoice re-export from `billing/invoicing/` | 4 |
| 20 | Create `PaymentProvider` protocol + `StripeProvider` | 5 |
| 21 | Remove all legacy endpoints from `api/v1/endpoints.py` | 6 |
| 22 | Create `api/v1/platform_endpoints.py` for customer CRUD | 6 |
| 23 | Rewire SDK `UBBClient` to delegate to product clients | 6 |
| 24 | Add `SubscriptionsClient` to SDK exports | 6 |
| 25 | Add payout export endpoint to referrals | 7 |
| 26 | Add referrals fee handler + ProductFeeConfig integration | 7 |
| 27 | Add velocity limiting + min customer age to referrals | 7 |
| 28 | Fix analytics earnings period filtering | 7 |
| 29 | Add all missing Celery queues + beat schedule entries | 9 |
| 30 | Add `STRIPE_SUBSCRIPTIONS_WEBHOOK_SECRET` to settings | 9 |
| 31 | Build outgoing tenant webhook system | 8 |
| 32 | Add `TenantWebhookConfig` and `TenantWebhookDelivery` models | 8 |
