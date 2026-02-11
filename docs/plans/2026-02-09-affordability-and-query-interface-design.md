# Affordability Pre-Check & Metering Query Interface Design

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Close the two remaining architecture gaps: (1) server-side pre-check ignores wallet balance, (2) billing and referrals import UsageEvent directly from metering.

**Architecture:** Add estimated_cost_micros to the billing pre-check so RiskService enforces affordability. Create a metering query interface (`apps/metering/queries.py`) that billing and referrals call instead of importing metering models directly. Synchronous cross-product reads go through query interfaces; asynchronous cross-product mutations go through the outbox pattern.

**Tech Stack:** Django 6.0, django-ninja, PostgreSQL

---

## Change 1: Affordability Pre-Check

### Problem

`PreCheckRequest` only accepts `customer_id`. `RiskService.check()` only checks customer status (suspended/closed) and rate limits. It never checks wallet balance against estimated cost. The SDK already sends `estimated_cost` but the server ignores it.

### Design

**Schema changes (`api/v1/schemas.py`):**

```python
class PreCheckRequest(Schema):
    customer_id: UUID
    estimated_cost_micros: int = Field(default=0, ge=0)

class PreCheckResponse(Schema):
    allowed: bool
    reason: Optional[str] = None
    balance_micros: Optional[int] = None
```

`estimated_cost_micros` defaults to 0 for backward compatibility.

**RiskService changes (`apps/billing/gating/services/risk_service.py`):**

After existing status + rate-limit checks, add affordability check:

```python
def check(customer, estimated_cost_micros=0):
    # ... existing status/rate-limit checks ...

    # Affordability check
    from apps.billing.wallets.models import Wallet
    try:
        wallet = Wallet.objects.get(customer=customer)
        balance = wallet.balance_micros
    except Wallet.DoesNotExist:
        balance = 0

    threshold = customer.get_arrears_threshold()
    if balance - estimated_cost_micros < -threshold:
        return {"allowed": False, "reason": "insufficient_funds", "balance_micros": balance}

    return {"allowed": True, "reason": None, "balance_micros": balance}
```

No `select_for_update()` needed. This is a read-only advisory check. The billing handler does the authoritative check with locking. The arrears threshold absorbs any race between pre-check and usage recording.

**Endpoint changes (`api/v1/billing_endpoints.py`):**

```python
@billing_api.post("/pre-check", response=PreCheckResponse)
def pre_check(request, payload: PreCheckRequest):
    _product_check(request)
    customer = get_object_or_404(Customer, id=payload.customer_id, tenant=request.auth.tenant)
    result = RiskService.check(customer, payload.estimated_cost_micros)
    return result
```

---

## Change 2: Metering Query Interface

### Problem

Two places import `UsageEvent` from metering, violating modular monolith boundaries:

1. `apps/billing/tenant_billing/services.py:107` — `reconcile_period()` queries UsageEvent for billing period totals
2. `apps/referrals/rewards/reconciliation.py:20` — `reconcile_referral()` queries UsageEvent for per-customer usage data

### Design Principle

In a modular monolith:
- **Mutations** cross boundaries via outbox events (maps to message broker in microservices)
- **Reads** cross boundaries via query interfaces (maps to REST/gRPC in microservices)

Direct model imports are never allowed across product boundaries.

### Design

**New file: `apps/metering/queries.py`**

```python
"""
Metering query interface for cross-product reads.

Other products call these functions instead of importing metering models.
If metering becomes a separate service, these become HTTP/gRPC calls.
"""

def get_period_totals(tenant_id, period_start, period_end):
    """Get aggregate usage totals for a tenant's billing period.

    Returns dict with total_cost_micros and event_count.
    """
    from apps.metering.usage.models import UsageEvent
    ...

def get_customer_usage_for_period(tenant_id, customer_id, period_start, period_end):
    """Get per-event usage data for a customer in a period.

    Returns list of dicts with billed_cost_micros, provider_cost_micros, cost_micros.
    Used by referrals reconciliation.
    """
    from apps.metering.usage.models import UsageEvent
    ...
```

**Consumer changes:**

`tenant_billing/services.py` replaces:
```python
from apps.metering.usage.models import UsageEvent
totals = UsageEvent.objects.filter(...).aggregate(...)
```
with:
```python
from apps.metering.queries import get_period_totals
totals = get_period_totals(tenant_id, period_start, period_end)
```

`referrals/reconciliation.py` replaces:
```python
from apps.metering.usage.models import UsageEvent
events = UsageEvent.objects.filter(...)
```
with:
```python
from apps.metering.queries import get_customer_usage_for_period
events = get_customer_usage_for_period(tenant_id, customer_id, start, end)
```

### Migration Path

If metering becomes a separate service:
```python
# apps/metering/queries.py — only this file changes
def get_period_totals(tenant_id, period_start, period_end):
    response = metering_client.get("/api/v1/metering/period-totals", ...)
    return response.json()
```

All consumers remain untouched.

---

## Boundary Rules (Post-Implementation)

| From | To | Allowed | Mechanism |
|---|---|---|---|
| Any product | Platform models | Yes | Direct import |
| Product A | Product B (mutation) | Yes | Outbox event |
| Product A | Product B (read) | Yes | Query interface |
| Product A | Product B (model) | No | Never |

After this work, zero cross-product model imports will remain in the codebase.
