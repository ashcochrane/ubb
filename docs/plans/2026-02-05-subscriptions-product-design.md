# Subscriptions Product Design

## Overview

A third independent product — **Subscriptions** — that manages recurring subscription billing for tenants' end-users via Stripe. It's a management layer on top of Stripe Subscriptions, not a replacement. We handle the orchestration; Stripe handles the payments.

This product follows the same lego block architecture defined in `docs/plans/2026-02-05-two-product-separation-design.md`.

---

## Context: The Four Customer Types

| Customer type | Products | Our revenue model |
|---|---|---|
| 1. Metering only (HeyOtis today) | `["metering"]` | Flat subscription fee (e.g. $1,000/mo) |
| 2. Full usage-based billing | `["metering", "billing"]` | 1% platform fee on billed amounts |
| 3. Billing with external metering | `["billing"]` | 1% platform fee on transactions |
| 4. Subscription billing + usage visibility | `["metering", "subscriptions"]` | 1% platform fee on subscription revenue |

Future combinations:

| Customer type | Products | Our revenue model |
|---|---|---|
| Subscriptions + overage wallets | `["metering", "subscriptions", "billing"]` | 1% on everything |
| Subscription management only | `["subscriptions"]` | 1% on subscription revenue |

---

## What We Do vs What Stripe Does

**Stripe handles:**
- Recurring payment collection
- Card management
- Invoice generation for subscription charges
- Payment failure retries (dunning)
- Proration on plan changes

**We handle:**
- Multi-tenant plan management (create plans on tenant's Connected Account, or import existing ones)
- Subscription lifecycle orchestration (subscribe, upgrade, downgrade, cancel)
- Platform fee collection (1% cut of subscription revenue)
- Unified dashboard for the tenant (subscriptions alongside usage data if metering is enabled)
- Event bus integration (metering data can inform subscription analytics)

**The tenant never needs to touch Stripe directly.** They configure plans and manage subscriptions through our API. We handle the Stripe wiring.

---

## Architecture

### Where It Fits

```
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│   Metering   │  │   Billing    │  │Subscriptions │
│              │  │  (Wallets)   │  │              │
│ Tracks usage │  │ Prepaid      │  │ Plans, tiers │
│ Calculates   │  │ balances     │  │ Recurring    │
│ costs        │  │ Pay-as-you-go│  │ billing      │
└──────┬───────┘  └──────┬───────┘  └──────┬───────┘
       │                 │                 │
       │     ┌───────────┴─────────┐       │
       │     │      Event Bus      │       │
       │     └───────────┬─────────┘       │
       │                 │                 │
 ┌─────▼─────────────────▼─────────────────▼─────┐
 │                   Platform                     │
 │         (tenants, customers, tenant_billing)   │
 └───────────────────────────────────────────────┘
```

### Rules

- Subscriptions **never imports** from Metering or Billing. And vice versa.
- Subscriptions **can import** from Platform (tenants, customers, tenant_billing).
- Subscriptions subscribes to `usage.recorded` events via the event bus for analytics (e.g. usage dashboards alongside subscription data). The handler is a side effect — not on the critical path.
- The **SDK** orchestrates multi-product flows (e.g. record usage for a subscribed customer).

---

## Data Model

### Plans

```python
# subscriptions/plans/models.py

class Plan(BaseModel):
    tenant = ForeignKey(Tenant, on_delete=CASCADE, related_name="plans")
    name = CharField(max_length=255)              # "Pro", "Enterprise"
    description = TextField(blank=True)
    status = CharField(max_length=20)             # active, archived
    stripe_product_id = CharField(max_length=255) # prod_xxx on tenant's Connected Account
    metadata = JSONField(default=dict)
    is_imported = BooleanField(default=False)      # True if imported from existing Stripe plan

    class Meta:
        unique_together = [("tenant", "name")]


class PlanPrice(BaseModel):
    plan = ForeignKey(Plan, on_delete=CASCADE, related_name="prices")
    amount_micros = BigIntegerField()             # 49_000_000 = $49
    currency = CharField(max_length=3, default="usd")
    interval = CharField(max_length=10)           # month, year
    stripe_price_id = CharField(max_length=255)   # price_xxx
    is_default = BooleanField(default=False)      # default price for this plan
    status = CharField(max_length=20)             # active, archived

    class Meta:
        unique_together = [("plan", "currency", "interval")]
```

### Subscriptions

```python
# subscriptions/subscriptions/models.py

class Subscription(BaseModel):
    tenant = ForeignKey(Tenant, on_delete=CASCADE, related_name="subscriptions")
    customer = ForeignKey(Customer, on_delete=CASCADE, related_name="subscriptions")
    plan = ForeignKey(Plan, on_delete=PROTECT, related_name="subscriptions")
    plan_price = ForeignKey(PlanPrice, on_delete=PROTECT, related_name="subscriptions")
    status = CharField(max_length=20)             # active, trialing, past_due,
                                                  # canceled, unpaid
    stripe_subscription_id = CharField(max_length=255)  # sub_xxx
    current_period_start = DateTimeField()
    current_period_end = DateTimeField()
    trial_end = DateTimeField(null=True, blank=True)
    canceled_at = DateTimeField(null=True, blank=True)
    cancel_at_period_end = BooleanField(default=False)

    class Meta:
        constraints = [
            # One active subscription per customer (can have canceled ones)
            UniqueConstraint(
                fields=["customer"],
                condition=Q(status__in=["active", "trialing", "past_due"]),
                name="one_active_subscription_per_customer",
            )
        ]


class SubscriptionEvent(BaseModel):
    subscription = ForeignKey(Subscription, on_delete=CASCADE, related_name="events")
    event_type = CharField(max_length=50)         # created, renewed, upgraded,
                                                  # downgraded, canceled,
                                                  # payment_failed, payment_succeeded,
                                                  # trial_started, trial_ended
    metadata = JSONField(default=dict)            # old_plan_id, new_plan_id, etc.
```

### Key Design Decisions

- **Plan and PlanPrice are separate** — one plan can have multiple prices (monthly vs yearly, different currencies).
- **`is_imported` flag on Plan** — distinguishes plans we created from plans imported from Stripe.
- **One active subscription per customer** — enforced at the DB level. A customer can have historical canceled subscriptions.
- **SubscriptionEvent is an audit trail** — every lifecycle change is recorded.
- **All Stripe IDs are stored** — `stripe_product_id`, `stripe_price_id`, `stripe_subscription_id` for staying in sync.

---

## API Surface

### Plan Management (`/api/v1/subscriptions/`)

```
POST   /subscriptions/plans                        # Create plan (creates in Stripe)
GET    /subscriptions/plans                        # List plans
GET    /subscriptions/plans/{id}                   # Get plan detail with prices
PUT    /subscriptions/plans/{id}                   # Update plan (name, description)
POST   /subscriptions/plans/{id}/archive           # Archive plan (deactivate in Stripe)
POST   /subscriptions/plans/{id}/prices            # Add a new price to a plan
POST   /subscriptions/plans/import                 # Import existing plans from Stripe
POST   /subscriptions/plans/sync                   # Sync plan/price data from Stripe
```

### Subscription Management

```
POST   /subscriptions/customers/{id}/subscribe     # Subscribe customer to a plan
GET    /subscriptions/customers/{id}/subscription   # Get current subscription
PUT    /subscriptions/customers/{id}/subscription   # Change plan (upgrade/downgrade)
POST   /subscriptions/customers/{id}/subscription/cancel  # Cancel subscription
GET    /subscriptions/customers/{id}/events         # Subscription event history
```

### Webhooks

```
POST   /subscriptions/webhooks/stripe              # Subscription-specific webhook handler
```

Webhook events handled:
- `invoice.paid` — renewal succeeded, accumulate platform fee
- `invoice.payment_failed` — update subscription status to `past_due`
- `customer.subscription.updated` — sync status changes from Stripe
- `customer.subscription.deleted` — mark subscription as canceled

All endpoints require `ProductAccess("subscriptions")`.

---

## Stripe Integration

### Plan Creation Flow

```
Tenant calls: POST /subscriptions/plans
  { name: "Pro", prices: [{ amount_micros: 49_000_000, interval: "month" }] }

Our API:
  1. Create Stripe Product on tenant's Connected Account
     stripe.Product.create(name="Pro", stripe_account=tenant.stripe_connected_account_id)

  2. Create Stripe Price
     stripe.Price.create(
       product=product.id,
       unit_amount=4900,  # $49 in cents
       currency="usd",
       recurring={"interval": "month"},
       stripe_account=tenant.stripe_connected_account_id,
     )

  3. Store Plan + PlanPrice locally with Stripe IDs

Return: Plan object with prices
```

### Plan Import Flow

```
Tenant calls: POST /subscriptions/plans/import
  { stripe_product_ids: ["prod_xxx", "prod_yyy"] }  # optional, imports all if empty

Our API:
  1. List Stripe Products on tenant's Connected Account
     stripe.Product.list(stripe_account=tenant.stripe_connected_account_id)

  2. For each product, list its Prices
     stripe.Price.list(product=product.id, stripe_account=...)

  3. Create local Plan + PlanPrice records (is_imported=True)
  4. Skip any already imported (match on stripe_product_id)

Return: List of imported Plans
```

### Subscribe Flow

```
Tenant calls: POST /subscriptions/customers/{id}/subscribe
  { plan_id: "...", price_id: "..." }

Our API:
  1. Verify customer has a stripe_customer_id on tenant's Connected Account
     (if not, create one)

  2. Create Stripe Subscription
     stripe.Subscription.create(
       customer=customer.stripe_customer_id,
       items=[{"price": plan_price.stripe_price_id}],
       stripe_account=tenant.stripe_connected_account_id,
     )

  3. Store Subscription locally with Stripe IDs

Return: Subscription object
```

### Upgrade/Downgrade Flow

```
Tenant calls: PUT /subscriptions/customers/{id}/subscription
  { plan_id: "new-plan", price_id: "new-price" }

Our API:
  1. Get current Stripe Subscription
  2. Update it with new price
     stripe.Subscription.modify(
       sub_id,
       items=[{
         "id": current_item_id,
         "price": new_plan_price.stripe_price_id,
       }],
       proration_behavior="create_prorations",
       stripe_account=tenant.stripe_connected_account_id,
     )
  3. Update local Subscription record
  4. Record SubscriptionEvent (upgraded/downgraded)

Return: Updated Subscription object
```

### Cancellation Flow

```
Tenant calls: POST /subscriptions/customers/{id}/subscription/cancel
  { at_period_end: true }  # cancel at end of billing period

Our API:
  1. Update Stripe Subscription
     stripe.Subscription.modify(
       sub_id,
       cancel_at_period_end=True,
       stripe_account=tenant.stripe_connected_account_id,
     )
  2. Update local record (cancel_at_period_end=True)
  3. Record SubscriptionEvent (canceled)

  When Stripe fires customer.subscription.deleted at period end:
  4. Webhook handler updates local status to "canceled"
  5. Record SubscriptionEvent (expired)

Return: Updated Subscription object
```

---

## Webhook Handling

Subscriptions has its own Stripe webhook endpoint — separate from billing's.

When a tenant enables subscriptions, we programmatically create a webhook endpoint on their Connected Account:

```python
stripe.WebhookEndpoint.create(
    url="https://api.ubb.io/api/v1/subscriptions/webhooks/stripe",
    enabled_events=[
        "invoice.paid",
        "invoice.payment_failed",
        "customer.subscription.updated",
        "customer.subscription.deleted",
    ],
    connect=True,
)
```

### Webhook Handlers

```python
# subscriptions/webhooks.py

def handle_invoice_paid(event):
    """Subscription renewed successfully."""
    subscription = Subscription.objects.get(
        stripe_subscription_id=event.data.object.subscription
    )
    subscription.current_period_start = event.data.object.period_start
    subscription.current_period_end = event.data.object.period_end
    subscription.status = "active"
    subscription.save()

    SubscriptionEvent.objects.create(
        subscription=subscription,
        event_type="renewed",
    )

    # Accumulate platform fee
    tenant_billing_service.accumulate_revenue(
        tenant_id=subscription.tenant_id,
        amount_micros=event.data.object.amount_paid * 1000,  # cents to micros
        source="subscriptions",
    )


def handle_invoice_payment_failed(event):
    """Payment failed on renewal."""
    subscription = Subscription.objects.get(
        stripe_subscription_id=event.data.object.subscription
    )
    subscription.status = "past_due"
    subscription.save()

    SubscriptionEvent.objects.create(
        subscription=subscription,
        event_type="payment_failed",
    )


def handle_subscription_updated(event):
    """Stripe-side subscription update (e.g. dunning resolved)."""
    stripe_sub = event.data.object
    subscription = Subscription.objects.get(
        stripe_subscription_id=stripe_sub.id
    )
    subscription.status = stripe_sub.status
    subscription.current_period_start = stripe_sub.current_period_start
    subscription.current_period_end = stripe_sub.current_period_end
    subscription.save()


def handle_subscription_deleted(event):
    """Subscription canceled/expired."""
    subscription = Subscription.objects.get(
        stripe_subscription_id=event.data.object.id
    )
    subscription.status = "canceled"
    subscription.canceled_at = event.data.object.canceled_at
    subscription.save()

    SubscriptionEvent.objects.create(
        subscription=subscription,
        event_type="expired",
    )
```

---

## Platform Fee Accumulation

Subscriptions uses the shared `platform/tenant_billing/` service — same as billing.

```python
# subscriptions/webhooks.py (inside handle_invoice_paid)
from apps.platform.tenant_billing.services import TenantBillingService

TenantBillingService.accumulate_revenue(
    tenant_id=subscription.tenant_id,
    amount_micros=amount_paid_micros,
    source="subscriptions",
)
```

The `TenantBillingPeriod` model accumulates revenue from all sources. End of month, one platform fee invoice covers everything:

```
TenantBillingPeriod:
  total_revenue_micros: $10,000  (from billing wallet top-ups: $4,000 + subscription renewals: $6,000)
  platform_fee_micros: $100      (1% of total)
```

---

## Event Bus Integration

### Events Subscriptions Emits

None currently. Subscriptions doesn't need to notify other products of lifecycle changes (no other product reacts to subscription events).

If needed in the future (e.g. metering adjusts tracking when a subscription is canceled), events can be added without changing existing products:

```python
# Future — only if needed
event_bus.emit("subscription.canceled", {
    "tenant_id": str(tenant.id),
    "customer_id": str(customer.id),
    "plan_id": str(plan.id),
})
```

### Events Subscriptions Consumes

Optionally subscribes to `usage.recorded` for analytics — showing usage alongside subscription data in a unified dashboard. This is a side effect, not on the critical path.

```python
# subscriptions/apps.py
class SubscriptionsConfig(AppConfig):
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

```python
# subscriptions/handlers.py
def handle_usage_recorded(data):
    """Track usage metrics alongside subscription data for unified analytics."""
    # Store or aggregate for dashboard purposes
    # This is optional — only relevant if tenant also has metering
    pass  # Implementation depends on analytics requirements
```

---

## Directory Structure

```
apps/
  subscriptions/
    plans/
      models.py               # Plan, PlanPrice
      services.py             # PlanService (create, import, sync, archive)
    subscriptions/
      models.py               # Subscription, SubscriptionEvent
      services.py             # SubscriptionService (subscribe, upgrade, cancel)
    stripe/
      services.py             # Stripe subscription API wrapper
      sync.py                 # Import/sync existing Stripe plans
    handlers.py               # Event bus handlers (usage.recorded for analytics)
    api/
      endpoints.py            # /subscriptions/* endpoints
      schemas.py              # Request/response schemas
      webhooks.py             # Stripe subscription webhooks
    apps.py                   # SubscriptionsConfig.ready() — event subscriptions
    tasks.py                  # Async tasks (if needed for retries, sync jobs)
```

---

## SDK Support

```python
# ubb-sdk/ubb/subscriptions.py

class SubscriptionsClient:
    def __init__(self, api_key, base_url, timeout=10.0):
        ...

    # Plans
    def create_plan(self, name, prices, description=None, metadata=None) -> Plan:
        """Create a plan (creates in Stripe on tenant's Connected Account)."""

    def list_plans(self, status="active") -> list[Plan]:
        """List tenant's plans."""

    def import_plans(self, stripe_product_ids=None) -> list[Plan]:
        """Import existing plans from Stripe."""

    def archive_plan(self, plan_id) -> Plan:
        """Archive a plan."""

    # Subscriptions
    def subscribe(self, customer_id, plan_id, price_id=None, trial_days=None) -> Subscription:
        """Subscribe a customer to a plan."""

    def get_subscription(self, customer_id) -> Subscription:
        """Get customer's current subscription."""

    def change_plan(self, customer_id, plan_id, price_id=None) -> Subscription:
        """Upgrade or downgrade a customer's plan."""

    def cancel(self, customer_id, at_period_end=True) -> Subscription:
        """Cancel a customer's subscription."""

    def get_events(self, customer_id, cursor=None, limit=20) -> PaginatedResponse:
        """Get subscription event history."""
```

```python
# UBBClient integration
class UBBClient:
    def __init__(self, api_key, base_url, metering=True, billing=False, subscriptions=False):
        self.metering = MeteringClient(...) if metering else None
        self.billing = BillingClient(...) if billing else None
        self.subscriptions = SubscriptionsClient(...) if subscriptions else None
```

---

## Tenant Configuration

```python
# Adding subscriptions to tenant access
tenant.products = ["metering", "subscriptions"]
tenant.save()  # cache invalidated automatically

# Subscriptions-only tenant
tenant.products = ["subscriptions"]
```

API access enforced via existing `ProductAccess("subscriptions")` mechanism.

---

## Decisions Log

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Stripe relationship | Management layer, not replacement | Don't replicate what Stripe does well. We orchestrate, Stripe collects. |
| Plan creation | Create via UBB API OR import from Stripe | Supports both new tenants and tenants migrating from direct Stripe usage. |
| Webhook endpoint | Separate from billing's webhook | Each product owns its webhooks completely. Clean extraction if needed later. |
| Platform fees | Shared `platform/tenant_billing/` | One invoice covers all revenue sources. No per-product invoicing. |
| One active subscription per customer | DB-level constraint | Simplifies logic. Historical canceled subscriptions preserved for audit. |
| Subscription events emitted | None initially | No other product currently needs to react. Can add later without changes. |
| Usage integration | Optional via event bus | If tenant has both metering + subscriptions, usage data available for analytics. Side effect only. |
