# Two-Product Separation Design

## Overview

UBB is split into two independent products — **Usage Metering** and **Billing & Payments** — that can be sold separately or together. A single deployment serves all tenants, with access controlled at the tenant level.

---

## Architecture

### Architecture

```
                    ┌─────────────────────────────┐
                    │           SDK                │
                    │   Orchestrates multi-product │
                    │   calls for tenants using    │
                    │   both products              │
                    └──────┬──────────────┬────────┘
                           │              │
                    ┌──────▼──┐    ┌──────▼──────┐
                    │Metering │    │  Billing    │
                    │  API    │    │   API       │
                    └──────┬──┘    └──────┬──────┘
                           │              │
           ┌───────────────▼──┐  ┌────────▼───────────────┐
           │  Usage Metering  │  │  Billing & Payments     │
           │                  │  │                         │
           │  Records events  │  │  Manages money          │
           │  Calculates costs│  │  Wallets, payments      │
           │  Pricing rules   │  │  Gating (balance-based) │
           │                  │  │                         │
           └───────┬──┬───────┘  └────────┬──┬────────────┘
                   │  │                   │  │
                   │  │   ┌──────────┐    │  │
                   │  └──►│Event Bus │◄───┘  │
                   │      │(side     │       │
                   │      │effects)  │       │
                   │      └──────────┘       │
                   │                         │
             ┌─────▼─────────────────────────▼──────┐
             │              Platform                 │
             │        (tenants, customers)           │
             │      Always installed. Shared.        │
             └──────────────────────────────────────┘
```

### Key Rules

- **Metering** and **Billing** never import from each other.
- Both can import from **Platform** (customers, tenants).
- The **SDK** orchestrates multi-product flows (e.g. record usage + debit wallet). No server-side composition layer.
- The **Event Bus** handles async side effects only. The critical financial path (debit/credit wallet) uses direct API calls from the SDK.
- Products are truly independent. Metering can work alone. Billing can work alone (fed by external metering). Both can work together.
- Adding new products (e.g. Subscriptions) means adding a new lego block — existing products don't change.

### Deployment Model

Single deployment. All products always installed. Tenant-level access control determines which APIs a tenant can hit.

No separate deployments needed. If independent scaling is required later, the clean code boundaries make extraction into separate services a mechanical change.

---

## Tenant Product Access

```python
# platform/tenants/models.py
class Tenant(BaseModel):
    products = ArrayField(
        models.CharField(max_length=20),
        default=list,  # ["metering"], ["billing"], ["metering", "billing"]
    )
```

Three configurations:

| Tenant | `products` | Use case |
|--------|-----------|----------|
| HeyOtis | `["metering"]` | Subscription customers. Just needs cost tracking and analytics. |
| WalletCo | `["billing"]` | Has own metering. Needs wallet management and payments. |
| FullPlatform | `["metering", "billing"]` | Uses both products together. |

Access enforced at the API layer via `ProductAccess` auth:

```python
# core/auth.py
class ProductAccess:
    def __init__(self, required_product):
        self.required_product = required_product

    def __call__(self, request):
        if self.required_product not in request.tenant.products:
            raise HttpError(403, f"Tenant does not have access to {self.required_product}")
```

---

## Event Bus

### Design

Handles **side effects only** — things where failure is tolerable. The critical financial path (debit/credit wallet) uses direct service calls, not the event bus.

- **Sync emit** — handlers run inline in the request cycle.
- **Handlers choose sync/async** — light work runs inline, heavy work dispatches to Celery.
- **Errors swallowed** — handler failures are logged but never break the emitting product.
- **Product access checked by the bus** — handlers declare which product they require. The bus checks the tenant's products (cached in Redis) before calling the handler.

### Implementation

```python
# core/event_bus.py
import logging
from django.core.cache import cache

logger = logging.getLogger("ubb.events")

class EventBus:
    def __init__(self):
        self._handlers = {}

    def subscribe(self, event_name, handler, requires_product=None):
        self._handlers.setdefault(event_name, []).append({
            "handler": handler,
            "requires_product": requires_product,
        })

    def _tenant_has_product(self, tenant_id, product):
        cache_key = f"tenant_products:{tenant_id}"
        products = cache.get(cache_key)
        if products is None:
            from apps.platform.tenants.models import Tenant
            tenant = Tenant.objects.get(id=tenant_id)
            products = tenant.products
            cache.set(cache_key, products, timeout=300)  # 5 min
        return product in products

    def emit(self, event_name, data):
        logger.info("event.emitted", extra={"event": event_name, "data": data})
        for entry in self._handlers.get(event_name, []):
            try:
                if entry["requires_product"] and data.get("tenant_id"):
                    if not self._tenant_has_product(
                        data["tenant_id"], entry["requires_product"]
                    ):
                        continue
                entry["handler"](data)
            except Exception:
                logger.exception(
                    "event.handler_failed",
                    extra={"event": event_name, "handler": entry["handler"].__name__}
                )

event_bus = EventBus()
```

### Events

| Event | Emitted by | Payload | Purpose |
|-------|-----------|---------|---------|
| `usage.recorded` | `metering/usage` | `tenant_id`, `customer_id`, `cost_micros`, `event_type`, `event_id` | Billing accumulates tenant stats, sends notifications |

### Handler Registration

```python
# billing/apps.py
class BillingConfig(AppConfig):
    name = "apps.billing"

    def ready(self):
        from core.event_bus import event_bus
        from apps.billing.handlers import handle_usage_recorded

        event_bus.subscribe(
            "usage.recorded",
            handle_usage_recorded,
            requires_product="billing",
        )
```

### Cache Invalidation

```python
# platform/tenants/services.py
def update_tenant_products(tenant, products):
    tenant.products = products
    tenant.save()
    cache.delete(f"tenant_products:{tenant.id}")
```

---

## Product Interfaces

### Usage Metering — Services

```python
# metering/usage/services.py
class UsageService:
    def record_usage(self, tenant_id, customer_id, ...) -> UsageResult:
        """Record event, apply pricing, return cost. Emits usage.recorded."""

    def get_usage(self, customer_id, filters) -> list[UsageEvent]:
        """Query usage history."""

    def estimate_cost(self, tenant_id, event_type, provider, metrics) -> int:
        """What would this cost? No recording, no side effects."""

# metering/pricing/services.py
class PricingService:
    def calculate_cost(self, tenant_id, event_type, provider, metrics) -> int:
        """Apply ProviderRate + TenantMarkup. Return cost in micros."""
```

### Billing & Payments — Services

```python
# billing/wallets/services.py
class WalletService:
    def debit(self, customer_id, amount_micros, reference) -> DebitResult:
        """Deduct from wallet. Returns new balance."""

    def credit(self, customer_id, amount_micros, source, reference) -> CreditResult:
        """Add to wallet. Returns new balance."""

    def get_balance(self, customer_id) -> BalanceResult:
        """Current balance."""

# billing/gating/services.py
class GatingService:
    def pre_check(self, customer_id, estimated_cost) -> PreCheckResult:
        """Can this customer afford this operation?"""

# billing/topups/services.py
class TopUpService:
    def create_checkout(self, customer_id, amount_micros, ...) -> CheckoutResult:
        """Create Stripe checkout session."""

    def configure_auto_topup(self, customer_id, enabled, ...) -> AutoTopUpConfig:
        """Set up auto top-up rules."""
```

---

## API Surface

### Platform (always available)

```
POST   /api/v1/customers                    # Create customer
GET    /api/v1/customers/{id}               # Get customer
GET    /api/v1/health                       # Health check
GET    /api/v1/ready                        # Readiness check
```

### Metering (`/api/v1/metering/`) — requires `products` contains `"metering"`

```
POST   /metering/usage                      # Record usage event, return cost
GET    /metering/customers/{id}/usage       # Usage history (paginated)
GET    /metering/analytics/costs            # Cost breakdown by provider/type/customer
GET    /metering/analytics/usage            # Volume breakdown (request counts, etc.)
```

### Billing (`/api/v1/billing/`) — requires `products` contains `"billing"`

```
POST   /billing/debit                       # Debit wallet (for external metering)
POST   /billing/credit                      # Credit wallet (refund, adjustment)
GET    /billing/customers/{id}/balance      # Current balance
GET    /billing/customers/{id}/transactions # Wallet transaction history
POST   /billing/customers/{id}/top-up      # Create Stripe checkout session
PUT    /billing/customers/{id}/auto-top-up  # Configure auto top-up
POST   /billing/customers/{id}/withdraw     # Withdraw from wallet
POST   /billing/pre-check                   # Can customer afford X amount?
GET    /billing/customers/{id}/invoices     # Top-up receipts
POST   /billing/webhooks/stripe             # Stripe webhook handler

# Analytics (revenue/markup — billing concern)
GET    /billing/analytics/revenue           # Revenue breakdown with markup

# Tenant billing (platform fees)
GET    /billing/tenant/billing-periods      # List billing periods
GET    /billing/tenant/billing-periods/{id} # Period detail
GET    /billing/tenant/invoices             # Platform fee invoices
```

### Widget (`/api/v1/widget/`) — requires `products` contains `"billing"`

```
GET    /widget/balance                      # Customer balance
GET    /widget/transactions                 # Top-ups and deductions
POST   /widget/top-up                       # Create checkout
GET    /widget/invoices                     # Top-up receipts
```

---

## SDK Orchestration

The SDK handles multi-product flows. No server-side composition layer needed. This scales cleanly as new products are added — the SDK is updated, the APIs stay pure.

```python
# ubb-sdk

class UBBClient:
    def __init__(self, api_key, base_url, metering=True, billing=False):
        self.metering = MeteringClient(api_key, base_url) if metering else None
        self.billing = BillingClient(api_key, base_url) if billing else None

    def record_usage(self, customer_id, event_type, provider, metrics, ...):
        """Record usage. If billing enabled, also debits wallet."""
        if not self.metering:
            raise UBBError("Metering not configured")

        result = self.metering.record_usage(
            customer_id, event_type, provider, metrics, ...
        )  # POST /metering/usage

        if self.billing:
            debit = self.billing.debit(
                customer_id,
                amount_micros=result.cost_micros,
                reference=str(result.event_id),
            )  # POST /billing/debit
            result.balance_after_micros = debit.new_balance

        return result

    def pre_check(self, customer_id, event_type, provider, metrics):
        """Estimate cost. If billing enabled, also checks balance."""
        if not self.metering:
            raise UBBError("Metering not configured")

        cost = self.metering.estimate_cost(
            event_type, provider, metrics
        )  # GET /metering/estimate

        if self.billing:
            check = self.billing.pre_check(
                customer_id, estimated_cost=cost
            )  # POST /billing/pre-check
            return PreCheckResult(
                can_proceed=check.can_proceed,
                estimated_cost_micros=cost,
                balance_micros=check.balance,
            )

        return PreCheckResult(
            can_proceed=True,  # no billing = no balance check
            estimated_cost_micros=cost,
        )


# Metering-only tenant (HeyOtis):
client = UBBClient(api_key="ubb_live_...", base_url="...", metering=True)
result = client.record_usage(...)  # returns cost only

# Both products (PayPerUse):
client = UBBClient(api_key="ubb_live_...", base_url="...", metering=True, billing=True)
result = client.record_usage(...)  # returns cost + balance

# Billing-only tenant (WalletCo) — uses billing client directly:
client = UBBClient(api_key="ubb_live_...", base_url="...", billing=True)
client.billing.debit(customer_id, amount_micros=2500000, reference="ext-123")
```

---

## Directory Structure

```
ubb-platform/
  core/
    event_bus.py              # EventBus singleton
    models.py                 # BaseModel (UUID, timestamps)
    auth.py                   # ApiKeyAuth, ProductAccess
    widget_auth.py            # JWT widget auth
    middleware.py              # Correlation ID
    locking.py                # Distributed locks
    exceptions.py             # Shared exceptions

  apps/
    platform/
      tenants/
        models.py             # Tenant, TenantApiKey
      customers/
        models.py             # Customer (identity only)
        api/
          endpoints.py        # CRUD customers
          schemas.py

    metering/
      usage/
        models.py             # UsageEvent (immutable)
        services.py           # UsageService (record, price)
      pricing/
        models.py             # ProviderRate, TenantMarkup
        services.py           # PricingService
      api/
        endpoints.py          # /metering/usage, /metering/analytics
        schemas.py
      apps.py                 # MeteringConfig — emits events

    billing/
      wallets/
        models.py             # Wallet, WalletTransaction
        services.py           # WalletService (debit, credit, balance)
      topups/
        models.py             # AutoTopUpConfig, TopUpAttempt
        services.py           # TopUpService
        tasks.py              # charge_auto_topup_task
      stripe/
        models.py             # StripeWebhookEvent
        services.py           # StripeService
      invoicing/
        services.py           # Receipt invoices
        tasks.py
      tenant_billing/
        models.py             # TenantBillingPeriod, TenantInvoice
        services.py
        tasks.py
      gating/
        models.py             # RiskConfig
        services.py           # RiskService (pre-check based on balance)
      handlers.py             # Event bus handlers
      api/
        endpoints.py          # /billing/* endpoints
        schemas.py
        webhooks.py           # Stripe webhooks
      apps.py                 # BillingConfig.ready() — subscribes to events
```

### Key Migrations from Current Structure

| Current location | New location | Notes |
|-----------------|-------------|-------|
| `apps/customers/Wallet` | `billing/wallets/` | Wallet is a billing concept |
| `apps/customers/WalletTransaction` | `billing/wallets/` | Ledger is a billing concept |
| `apps/customers/AutoTopUpConfig` | `billing/topups/` | Payment automation |
| `apps/customers/TopUpAttempt` | `billing/topups/` | Payment attempts |
| `apps/customers/Customer` | `platform/customers/` | Slimmed to identity only |
| `apps/usage/` | `metering/usage/` | Unchanged logic |
| `apps/pricing/` | `metering/pricing/` | Unchanged logic |
| `apps/gating/` | `billing/gating/` | Pre-check is balance-based |
| `apps/stripe_integration/` | `billing/stripe/` | Payment provider |
| `apps/invoicing/` | `billing/invoicing/` | Unchanged logic |
| `apps/tenant_billing/` | `billing/tenant_billing/` | Unchanged logic |
| `apps/usage/Refund` | `billing/wallets/` | Refunding is a financial operation |

---

## Migration Strategy

Four phases, each deployable independently:

### Phase 1: Restructure Directories (no logic changes)

- Move files into `platform/`, `metering/`, `billing/` structure
- Update all imports
- Update `INSTALLED_APPS`
- Update Django app labels and migration dependencies
- Zero behaviour change — just file moves and import rewrites
- Deploy and verify

### Phase 2: Introduce the Event Bus

- Add `core/event_bus.py`
- Add `usage.recorded` event emission in `UsageService`
- Move tenant billing accumulation from direct call to event handler
- The critical path (wallet debit) stays as direct calls
- Deploy and verify

### Phase 3: Extract Product APIs

- Create `metering/api/` and `billing/api/`
- Move existing endpoints into their product's API module
- New `/metering/` and `/billing/` namespaced paths
- Add `products` field to Tenant model with `ProductAccess` auth
- Deploy and verify

### Phase 4: Update SDK + Clean Up

- Update SDK to support product-specific clients (`MeteringClient`, `BillingClient`)
- SDK orchestrates multi-product flows (record usage + debit wallet)
- Remove any remaining cross-product imports
- Verify metering works with `products=["metering"]` tenant
- Verify billing works with `products=["billing"]` tenant
- Update documentation

---

## Decisions Log

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Communication pattern | Event bus + direct service calls | Event bus for side effects (composable). Direct calls for critical financial path (reliable). |
| Event bus execution | Sync emit, handlers choose sync/async | Handlers can do quick checks inline, dispatch heavy work to Celery. Avoids unnecessary task overhead. |
| Error handling | Swallow handler errors | Emitting product never breaks due to handler failure. Errors logged. |
| Product access | Tenant-level field, not separate deployments | Single deployment is simpler. Standard SaaS pattern. Can extract later if needed. |
| Directory structure | Nested by product | Makes boundaries visible in filesystem. Easier to extract later. |
| Customer/Tenant ownership | Shared platform layer | Both products need these. Neither owns them. |
| Wallet ownership | Billing product | Wallets manage money. Metering just measures consumption. |
| Gating ownership | Billing product | Pre-check is balance-based, a billing concern. |
| API structure | Each product owns its own API. SDK orchestrates multi-product flows. | No composition layer needed. Scales cleanly as new products are added. SDK handles coordination. |
| Event bus product checks | Bus checks tenant products (cached in Redis, 5-min TTL) | Handlers stay clean. No product checks scattered through code. |
