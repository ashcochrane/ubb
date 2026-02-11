# Subscriptions Product Design

## Overview

The **Subscriptions** product provides subscription-based tenants with **unit economics visibility**. It syncs subscription revenue data from Stripe and combines it with usage cost data from our metering service to show per-customer profitability.

We do **not** replace or manage Stripe's subscription logic. Stripe remains the source of truth for subscriptions, invoicing, and payments. We complement Stripe by answering: "How much does each customer actually cost me vs what they pay?"

This product follows the lego block architecture defined in `docs/plans/2026-02-05-two-product-separation-design.md`.

---

## Strategic Context

### Core Value Proposition

Our core value is the **usage metering service** — accurately calculating API usage and associated costs at a per-customer level. All supported business models anchor around this capability.

We are no longer targeting customers who have their own usage metering system (e.g. Metronome). Usage metering is always the foundational layer.

### Customer Types

We support **two primary customer types**:

| Customer type | Products | What they get | Our revenue |
|---|---|---|---|
| Usage-based billing | `["metering", "billing"]` | Metering + prepaid wallets, Stripe Connect payments | 1% transaction fee |
| Subscription + visibility | `["metering", "subscriptions"]` | Metering + Stripe revenue sync, unit economics dashboard | Flat fee or % of subscription revenue |

**Usage-based billing customers** charge their end users based on API usage. Our platform measures usage, calculates cost, and supports billing via Stripe Connect. Our pricing scales directly with their usage — fully aligned with value creation.

**Subscription + visibility customers** charge their end users via subscriptions but want to understand the true unit economics of each customer. Stripe handles subscription billing; we complement Stripe by combining subscription revenue with our usage cost data.

### What We Do NOT Do

- We do not create or manage subscriptions in Stripe
- We do not handle subscription lifecycle (subscribe, upgrade, cancel)
- We do not replicate Stripe's invoicing or dunning
- The tenant manages their subscriptions in Stripe directly (or via their own integration)
- We do not support billing-only or subscriptions-only tenants — metering is always required

### What We Do

- **Pull** subscription revenue data from Stripe (per customer)
- **Calculate** API usage costs using our metering service (per customer)
- **Link** these two data sources together
- **Provide** a dashboard showing unit economics per customer:
  - Subscription revenue
  - API usage cost
  - Gross margin / profitability per customer

### Strategic Framing

In all cases:
- **Usage metering is the foundational layer** — always required
- Billing (usage-based or subscription-based) is either:
  - Fully enabled by us (usage billing with prepaid wallets), or
  - Integrated with Stripe (subscriptions with unit economics visibility)
- The long-term goal is to give tenants **clear visibility into per-customer unit economics**, regardless of how they bill their customers

---

## Architecture

### Where It Fits

```
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│   Metering   │  │   Billing    │  │Subscriptions │
│              │  │  (Wallets)   │  │              │
│ Tracks usage │  │ Prepaid      │  │ Stripe sync  │
│ Calculates   │  │ balances     │  │ Revenue data │
│ costs        │  │ Pay-as-you-go│  │ Unit econ.   │
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
- Subscriptions listens to `usage.recorded` events via the event bus to accumulate cost data for unit economics calculations.
- Metering is always required alongside subscriptions (`["metering", "subscriptions"]`).

---

## Data Model

### Synced Subscription Data (read-only mirror from Stripe)

```python
# subscriptions/models.py

class StripeSubscription(BaseModel):
    """Synced from Stripe — we don't manage this, we observe it."""
    tenant = ForeignKey(Tenant, on_delete=CASCADE, related_name="stripe_subscriptions")
    customer = ForeignKey(Customer, on_delete=CASCADE, related_name="stripe_subscriptions")
    stripe_subscription_id = CharField(max_length=255, unique=True)  # sub_xxx
    stripe_product_name = CharField(max_length=255)                  # "Pro Plan"
    status = CharField(max_length=20)         # active, past_due, canceled, etc.
    amount_micros = BigIntegerField()         # monthly/yearly amount in micros
    currency = CharField(max_length=3, default="usd")
    interval = CharField(max_length=10)       # month, year
    current_period_start = DateTimeField()
    current_period_end = DateTimeField()
    last_synced_at = DateTimeField()


class SubscriptionInvoice(BaseModel):
    """Synced from Stripe — tracks each paid invoice for revenue attribution."""
    tenant = ForeignKey(Tenant, on_delete=CASCADE)
    customer = ForeignKey(Customer, on_delete=CASCADE)
    stripe_subscription = ForeignKey(StripeSubscription, on_delete=CASCADE, related_name="invoices")
    stripe_invoice_id = CharField(max_length=255, unique=True)  # in_xxx
    amount_paid_micros = BigIntegerField()    # what the end-user actually paid
    currency = CharField(max_length=3, default="usd")
    period_start = DateTimeField()
    period_end = DateTimeField()
    paid_at = DateTimeField()
```

### Unit Economics (calculated by us)

```python
# subscriptions/economics/models.py

class CustomerEconomics(BaseModel):
    """Per-customer, per-period unit economics snapshot."""
    tenant = ForeignKey(Tenant, on_delete=CASCADE)
    customer = ForeignKey(Customer, on_delete=CASCADE)
    period_start = DateTimeField()            # start of calculation period
    period_end = DateTimeField()              # end of calculation period
    subscription_revenue_micros = BigIntegerField(default=0)  # from Stripe invoices
    usage_cost_micros = BigIntegerField(default=0)            # from metering
    gross_margin_micros = BigIntegerField(default=0)          # revenue - cost
    margin_percentage = DecimalField(max_digits=5, decimal_places=2, default=0)

    class Meta:
        unique_together = [("tenant", "customer", "period_start")]
```

### Key Design Decisions

- **`StripeSubscription` is a read-only mirror** — we sync from Stripe, never write to Stripe. The tenant manages subscriptions directly in Stripe.
- **`SubscriptionInvoice` tracks paid revenue** — each Stripe invoice payment is recorded for revenue attribution. This is how we know how much each customer pays.
- **`CustomerEconomics` is a calculated snapshot** — generated periodically (daily or end of period) by combining subscription revenue with metering cost data. This is the core value we provide.
- **No Plan/PlanPrice models** — we don't manage plans. We just observe what Stripe tells us.

---

## Stripe Integration

### Sync Flow

The tenant connects their Stripe account. We sync subscription data in two ways:

**1. Initial import (on connect):**

```
Tenant connects Stripe → POST /subscriptions/sync

Our API:
  1. List active subscriptions on tenant's Connected Account
     stripe.Subscription.list(
       status="active",
       stripe_account=tenant.stripe_connected_account_id,
       expand=["data.customer", "data.plan.product"]
     )

  2. For each subscription:
     - Match to a Customer via stripe_customer_id
     - Create/update StripeSubscription record
     - Fetch recent paid invoices
     - Create SubscriptionInvoice records

  3. Set last_synced_at
```

**2. Ongoing sync via webhooks:**

When a tenant enables subscriptions, we create a webhook endpoint:

```python
stripe.WebhookEndpoint.create(
    url="https://api.ubb.io/api/v1/subscriptions/webhooks/stripe",
    enabled_events=[
        "invoice.paid",                        # revenue event
        "customer.subscription.created",       # new subscription
        "customer.subscription.updated",       # status/plan changes
        "customer.subscription.deleted",       # cancellation
    ],
    connect=True,
)
```

### Webhook Handlers

```python
# subscriptions/api/webhooks.py

def handle_invoice_paid(event):
    """A subscription invoice was paid — record the revenue."""
    invoice = event.data.object
    if not invoice.subscription:
        return  # not a subscription invoice

    stripe_sub = StripeSubscription.objects.get(
        stripe_subscription_id=invoice.subscription
    )

    SubscriptionInvoice.objects.create(
        tenant=stripe_sub.tenant,
        customer=stripe_sub.customer,
        stripe_subscription=stripe_sub,
        stripe_invoice_id=invoice.id,
        amount_paid_micros=invoice.amount_paid * 1000,  # cents to micros
        currency=invoice.currency,
        period_start=invoice.period_start,
        period_end=invoice.period_end,
        paid_at=invoice.status_transitions.paid_at,
    )

    # Accumulate platform fee (if % based pricing)
    tenant_billing_service.accumulate_revenue(
        tenant_id=stripe_sub.tenant_id,
        amount_micros=invoice.amount_paid * 1000,
        source="subscriptions",
    )


def handle_subscription_created(event):
    """New subscription — create local mirror."""
    stripe_sub = event.data.object
    customer = Customer.objects.get(
        stripe_customer_id=stripe_sub.customer,
        tenant__stripe_connected_account_id=event.account,
    )
    StripeSubscription.objects.create(
        tenant=customer.tenant,
        customer=customer,
        stripe_subscription_id=stripe_sub.id,
        stripe_product_name=stripe_sub.plan.product.name,
        status=stripe_sub.status,
        amount_micros=stripe_sub.plan.amount * 1000,
        currency=stripe_sub.plan.currency,
        interval=stripe_sub.plan.interval,
        current_period_start=stripe_sub.current_period_start,
        current_period_end=stripe_sub.current_period_end,
        last_synced_at=timezone.now(),
    )


def handle_subscription_updated(event):
    """Subscription changed (status, plan, etc.) — update mirror."""
    stripe_sub = event.data.object
    sub = StripeSubscription.objects.get(
        stripe_subscription_id=stripe_sub.id
    )
    sub.status = stripe_sub.status
    sub.current_period_start = stripe_sub.current_period_start
    sub.current_period_end = stripe_sub.current_period_end
    sub.last_synced_at = timezone.now()
    sub.save()


def handle_subscription_deleted(event):
    """Subscription canceled — update mirror."""
    stripe_sub = event.data.object
    sub = StripeSubscription.objects.get(
        stripe_subscription_id=stripe_sub.id
    )
    sub.status = "canceled"
    sub.last_synced_at = timezone.now()
    sub.save()
```

---

## Unit Economics Calculation

The core value of this product. Combines subscription revenue (from Stripe) with usage costs (from metering).

### How It Works

```
For each customer in a given period:

  Subscription Revenue = SUM(SubscriptionInvoice.amount_paid_micros)
    WHERE period overlaps AND customer matches

  Usage Cost = SUM(UsageEvent.cost_micros)
    WHERE effective_at in period AND customer matches
    (queried via metering's service interface — NOT a direct model import)

  Gross Margin = Revenue - Cost
  Margin % = (Margin / Revenue) * 100
```

### Implementation

```python
# subscriptions/economics/services.py

class EconomicsService:
    def calculate_customer_economics(
        self, tenant_id, customer_id, period_start, period_end
    ) -> CustomerEconomics:
        """Calculate unit economics for a single customer."""

        # Revenue from synced Stripe invoices (subscriptions product's own data)
        revenue = SubscriptionInvoice.objects.filter(
            tenant_id=tenant_id,
            customer_id=customer_id,
            period_start__gte=period_start,
            period_end__lte=period_end,
        ).aggregate(total=Sum("amount_paid_micros"))["total"] or 0

        # Usage cost from metering (via event bus accumulated data or API call)
        cost = self._get_usage_cost(tenant_id, customer_id, period_start, period_end)

        margin = revenue - cost
        margin_pct = (margin / revenue * 100) if revenue > 0 else 0

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

    def calculate_all_economics(self, tenant_id, period_start, period_end):
        """Calculate unit economics for all customers with active subscriptions."""
        customer_ids = StripeSubscription.objects.filter(
            tenant_id=tenant_id,
            status="active",
        ).values_list("customer_id", flat=True).distinct()

        results = []
        for customer_id in customer_ids:
            result = self.calculate_customer_economics(
                tenant_id, customer_id, period_start, period_end
            )
            results.append(result)
        return results
```

### How Usage Cost Data Gets Here

The subscriptions product needs usage cost per customer. Two approaches:

**Approach A — Event bus accumulation (recommended):**

Subscriptions subscribes to `usage.recorded` and accumulates costs internally:

```python
# subscriptions/handlers.py
def handle_usage_recorded(data):
    """Accumulate usage cost for unit economics calculation."""
    # Store in a lightweight accumulator table or update CustomerEconomics directly
    CustomerCostAccumulator.objects.filter(
        tenant_id=data["tenant_id"],
        customer_id=data["customer_id"],
        period=current_period(),
    ).update(
        total_cost_micros=F("total_cost_micros") + data["cost_micros"]
    )
```

This way subscriptions has its own copy of cost data — no cross-product import needed.

**Approach B — Read from metering API:**

The economics service calls metering's API at calculation time:

```python
def _get_usage_cost(self, tenant_id, customer_id, period_start, period_end):
    # Call metering's analytics endpoint
    response = httpx.get(
        f"{METERING_URL}/api/v1/metering/analytics/costs",
        params={...}
    )
    return response.json()["total_cost_micros"]
```

Approach A is preferred — it avoids runtime coupling and the data is already available when the dashboard is queried.

---

## API Surface

### Sync & Configuration (`/api/v1/subscriptions/`)

```
POST   /subscriptions/sync                         # Trigger full Stripe subscription sync
GET    /subscriptions/sync/status                   # Last sync status and timestamp
```

### Unit Economics Dashboard

```
GET    /subscriptions/economics                     # All customers — unit economics summary
GET    /subscriptions/economics/{customer_id}       # Single customer — detailed economics
GET    /subscriptions/economics/summary              # Aggregate: total revenue, total cost, avg margin
```

### Subscription Data (read-only, synced from Stripe)

```
GET    /subscriptions/customers/{id}/subscription   # Current subscription details
GET    /subscriptions/customers/{id}/invoices        # Subscription invoice history
```

### Webhooks

```
POST   /subscriptions/webhooks/stripe               # Stripe subscription webhook handler
```

All endpoints require `ProductAccess("subscriptions")`.

---

## Example Dashboard Output

```json
GET /subscriptions/economics

{
  "period": { "start": "2026-01-01", "end": "2026-01-31" },
  "customers": [
    {
      "customer_id": "cust-001",
      "external_id": "acme-corp",
      "plan": "Enterprise",
      "subscription_revenue_micros": 199_000_000,
      "usage_cost_micros": 47_200_000,
      "gross_margin_micros": 151_800_000,
      "margin_percentage": 76.28
    },
    {
      "customer_id": "cust-002",
      "external_id": "small-startup",
      "plan": "Pro",
      "subscription_revenue_micros": 49_000_000,
      "usage_cost_micros": 62_300_000,
      "gross_margin_micros": -13_300_000,
      "margin_percentage": -27.14
    }
  ],
  "summary": {
    "total_revenue_micros": 248_000_000,
    "total_cost_micros": 109_500_000,
    "total_margin_micros": 138_500_000,
    "avg_margin_percentage": 55.85,
    "unprofitable_customers": 1
  }
}
```

The second customer (small-startup) is **losing money** — they're costing more in API calls than they pay in subscription fees. This is the insight tenants can't get without combining metering + subscription data.

---

## Event Bus Integration

### Events Subscriptions Consumes

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

### Events Subscriptions Emits

None. This product observes and calculates — it doesn't trigger actions in other products.

---

## Directory Structure

```
apps/
  subscriptions/
    models.py                 # StripeSubscription, SubscriptionInvoice
    economics/
      models.py               # CustomerEconomics, CustomerCostAccumulator
      services.py             # EconomicsService (calculate unit economics)
    stripe/
      services.py             # Stripe API wrapper (list subscriptions, invoices)
      sync.py                 # Full sync logic (initial import)
    handlers.py               # Event bus handler (usage.recorded → accumulate costs)
    api/
      endpoints.py            # /subscriptions/* endpoints
      schemas.py              # Request/response schemas
      webhooks.py             # Stripe webhooks (invoice.paid, subscription events)
    apps.py                   # SubscriptionsConfig.ready() — event subscriptions
    tasks.py                  # Periodic economics calculation, sync retry
```

---

## SDK Support

```python
# ubb-sdk/ubb/subscriptions.py

class SubscriptionsClient:
    def __init__(self, api_key, base_url, timeout=10.0):
        ...

    def sync(self) -> SyncResult:
        """Trigger Stripe subscription sync."""

    def get_economics(self, period_start=None, period_end=None) -> EconomicsReport:
        """Get unit economics for all customers."""

    def get_customer_economics(self, customer_id, period_start=None, period_end=None) -> CustomerEconomics:
        """Get unit economics for a single customer."""

    def get_economics_summary(self, period_start=None, period_end=None) -> EconomicsSummary:
        """Get aggregate economics summary."""

    def get_subscription(self, customer_id) -> StripeSubscription:
        """Get customer's current subscription (synced from Stripe)."""

    def get_invoices(self, customer_id, cursor=None, limit=20) -> PaginatedResponse:
        """Get customer's subscription invoice history."""
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

## Platform Fee Accumulation

If the tenant is on percentage-based pricing, subscription revenue is accumulated into the shared `platform/tenant_billing/`:

```python
# subscriptions/api/webhooks.py (inside handle_invoice_paid)
from apps.platform.tenant_billing.services import TenantBillingService

TenantBillingService.accumulate_revenue(
    tenant_id=subscription.tenant_id,
    amount_micros=amount_paid_micros,
    source="subscriptions",
)
```

If the tenant is on flat-fee pricing, no accumulation needed — their fee is fixed regardless of subscription volume.

---

## Decisions Log

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Stripe relationship | Read-only sync, not management | Stripe handles subscriptions well. We complement, not compete. |
| Core value | Unit economics (revenue vs cost per customer) | This is the insight tenants can't get elsewhere — combining subscription revenue with usage costs. |
| Subscription data | Synced mirror, never written to Stripe | We observe, we don't manage. Tenant controls subscriptions directly in Stripe. |
| Usage cost data | Accumulated via event bus (recommended) | Avoids cross-product coupling. Subscriptions has its own copy of cost data. |
| Webhook endpoint | Separate from billing's webhook | Each product owns its webhooks. Clean extraction if needed. |
| Platform fees | Shared `platform/tenant_billing/` | One invoice covers all revenue sources. |
| No plan management | Intentionally omitted | We don't manage plans. We just observe what Stripe tells us about the tenant's subscriptions. |
