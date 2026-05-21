# Billing Config Extraction Design

**Date:** 2026-03-10
**Status:** Approved
**Scope:** Priority 2 from architecture audit — extract billing-specific fields from platform shared kernel models into billing-owned config models, establish query interfaces for all cross-module reads.

## Problem

The platform shared kernel models (`Tenant`, `Customer`) carry billing-specific fields:

**On Tenant:**
- `stripe_customer_id` (tenant as UBB's customer for platform fee invoicing)
- `platform_fee_percentage`
- `min_balance_micros`
- `run_cost_limit_micros`
- `hard_stop_balance_micros`

**On Customer:**
- `min_balance_micros`

This couples every product to billing's schema. Any billing config change requires a migration on shared tables. Platform services (`RunService`) read billing config directly, creating reverse dependencies that block extraction. Cross-module reads happen via direct field access on model instances, making integration points invisible.

## Principles

- **No product-specific state on shared kernel models.** Tenant and Customer carry only platform identity.
- **Every cross-module read goes through a query interface.** Named functions in `queries.py` files that could be replaced with HTTP calls when extracted.
- **Lazy creation.** Config models are created on first access via `get_or_create`, matching the existing wallet pattern.
- **One-way dependencies.** Products depend on platform. Platform never imports from products. The API layer orchestrates.

## Design

### New Models

**`BillingTenantConfig`** in `apps/billing/tenant_billing/models.py`:

```python
class BillingTenantConfig(BaseModel):
    tenant = models.OneToOneField("tenants.Tenant", on_delete=models.CASCADE,
                                   related_name="billing_config")
    stripe_customer_id = models.CharField(max_length=255, blank=True, default="")
    platform_fee_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=1.00)
    min_balance_micros = models.BigIntegerField(default=0)
    run_cost_limit_micros = models.BigIntegerField(null=True, blank=True)
    hard_stop_balance_micros = models.BigIntegerField(null=True, blank=True)

    class Meta:
        db_table = "ubb_billing_tenant_config"
```

**`CustomerBillingProfile`** in `apps/billing/wallets/models.py`:

```python
class CustomerBillingProfile(BaseModel):
    customer = models.OneToOneField("customers.Customer", on_delete=models.CASCADE,
                                     related_name="billing_profile")
    min_balance_micros = models.BigIntegerField(null=True, blank=True)

    class Meta:
        db_table = "ubb_customer_billing_profile"
```

Both lazily created via `get_or_create` when billing code first needs them. Sensible defaults mean a fresh config row works out of the box.

### Query Interfaces

**`apps/platform/queries.py`** (new — platform's published read contract):

```python
def get_tenant_stripe_account(tenant_id) -> Optional[str]:
    """Returns the tenant's Stripe connected account ID, or None if not set."""

def get_customer_stripe_id(customer_id) -> Optional[str]:
    """Returns the customer's Stripe customer ID, or None if not set."""

def get_customers_by_stripe_id(tenant_id) -> dict[str, str]:
    """Returns {stripe_customer_id: customer_id} for all customers with Stripe IDs.
    Used by subscription sync to match Stripe subscriptions to platform customers."""
```

**`apps/billing/queries.py`** (new — billing's published read contract):

```python
def get_billing_config(tenant_id) -> BillingTenantConfig:
    """Returns billing config for a tenant. Lazily creates with defaults if missing."""

def get_customer_min_balance(customer_id, tenant_id) -> int:
    """Returns the effective min balance: customer override -> tenant default -> 0."""

def get_customer_balance(customer_id) -> int:
    """Returns wallet balance, or 0 if no wallet exists."""
```

**`apps/subscriptions/queries.py`** (new — subscriptions' published read contract):

```python
def get_customer_economics(tenant_id, customer_id, period_start, period_end):
    """Returns CustomerEconomics or None."""

def get_economics_summary(tenant_id, period_start, period_end):
    """Returns aggregated economics for all customers."""

def get_customer_subscription(tenant_id, customer_id):
    """Returns latest StripeSubscription or None."""
```

### RunService Parameter Change

`RunService.create_run()` adds explicit `cost_limit_micros` and `hard_stop_balance_micros` parameters instead of reading from `tenant`:

```python
# Before:
def create_run(tenant, customer, balance_snapshot_micros, metadata=None, external_run_id=""):
    return Run.objects.create(
        ...
        cost_limit_micros=tenant.run_cost_limit_micros,
        hard_stop_balance_micros=tenant.hard_stop_balance_micros,
    )

# After:
def create_run(tenant, customer, balance_snapshot_micros,
               cost_limit_micros=None, hard_stop_balance_micros=None,
               metadata=None, external_run_id=""):
    return Run.objects.create(
        ...
        cost_limit_micros=cost_limit_micros,
        hard_stop_balance_micros=hard_stop_balance_micros,
    )
```

The single caller (`RiskService.check()`) reads from `BillingTenantConfig` and passes values in.

### Customer.get_min_balance() Removal

`Customer.get_min_balance()` is deleted from `apps/platform/customers/models.py`. Billing code calls `billing/queries.py:get_customer_min_balance()` instead.

### Fields Staying on Platform

`Tenant.stripe_connected_account_id` and `Customer.stripe_customer_id` remain on platform models — they are external identity mappings used by multiple products. All product code accesses them through `platform/queries.py`, not direct field reads.

## Consumer Migration Table

### Fields moving to BillingTenantConfig

| File | Current Read | After |
|---|---|---|
| `billing/stripe/services/stripe_service.py:125,139,148` | `tenant.stripe_customer_id` | `get_billing_config(tenant.id).stripe_customer_id` |
| `billing/tenant_billing/services.py:109` | `tenant.platform_fee_percentage` | `get_billing_config(tenant.id).platform_fee_percentage` |
| `platform/runs/services.py:45-46` | `tenant.run_cost_limit_micros`, `tenant.hard_stop_balance_micros` | Removed — passed as parameters by caller |
| `billing/gating/services/risk_service.py:48-54` | reads `tenant.*` indirectly via RunService | Calls `get_billing_config()`, passes values to `RunService.create_run()` |

### Fields moving to CustomerBillingProfile

| File | Current Read | After |
|---|---|---|
| `platform/customers/models.py:38-42` | `self.min_balance_micros`, `self.tenant.min_balance_micros` | **Delete** `get_min_balance()` entirely |
| `billing/handlers.py:55` | `customer.get_min_balance()` | `get_customer_min_balance(customer.id, tenant.id)` |

### Fields staying on platform (behind query interface)

| File | Current Read | After |
|---|---|---|
| `billing/connectors/stripe/stripe_api.py:26,39,53,59,70` | `customer.stripe_customer_id`, `customer.tenant.stripe_connected_account_id` | `get_customer_stripe_id()`, `get_tenant_stripe_account()` |
| `billing/connectors/stripe/receipts.py:29,37,48` | same | same query interface calls |
| `billing/connectors/stripe/tasks.py:156` | `attempt.customer.tenant.stripe_connected_account_id` | `get_tenant_stripe_account()` |
| `billing/connectors/stripe/handlers.py:26` | `tenant.stripe_connected_account_id` | `get_tenant_stripe_account()` |
| `api/v1/billing_endpoints.py:142,144` | `tenant.stripe_connected_account_id`, `customer.stripe_customer_id` | query interface calls |
| `api/v1/me_endpoints.py:139,140` | same | same |
| `subscriptions/stripe/sync.py:25,33,43` | `tenant.stripe_connected_account_id`, `c.stripe_customer_id` | `get_tenant_stripe_account()`, `get_customers_by_stripe_id()` |
| `api/v1/platform_endpoints.py:36` | `customer.stripe_customer_id` | `get_customer_stripe_id()` |

### Seed command

| File | After |
|---|---|
| `platform/tenants/management/commands/seed_dev_data.py` | Also creates `BillingTenantConfig` with `stripe_customer_id` |

## Migration Strategy

### Phase 1: Create new models + data migration (this PR)

- Schema migration in `tenant_billing/` adds `BillingTenantConfig` table.
- Schema migration in `wallets/` adds `CustomerBillingProfile` table.
- Data migration copies values from existing Tenant/Customer fields into new models.

### Phase 2: Switch all reads (this PR)

All 14 production files updated per the consumer table. Old fields still exist but are no longer read by production code.

### Phase 3: Remove old fields (separate follow-up PR)

Deferred. Drops columns from Tenant and Customer after production verification.

Fields to remove:
- `Tenant.stripe_customer_id`
- `Tenant.platform_fee_percentage`
- `Tenant.min_balance_micros`
- `Tenant.run_cost_limit_micros`
- `Tenant.hard_stop_balance_micros`
- `Customer.min_balance_micros`

Fields staying: `Tenant.stripe_connected_account_id`, `Customer.stripe_customer_id` (platform identity).

## Test Impact

- `runs/tests/test_services.py` — passes limits to `create_run()` instead of setting on Tenant
- `billing/gating/tests/test_risk_service.py` — creates `BillingTenantConfig` and `CustomerBillingProfile`
- `billing/tenant_billing/tests/test_tasks.py` — creates `BillingTenantConfig` with `platform_fee_percentage`
- Webhook/endpoint tests setting Stripe IDs — unchanged (fields stay on platform)

## Scope Summary

- 2 new models in existing apps
- 3 new query interface files
- 14 production files updated
- 1 method deleted (`Customer.get_min_balance()`)
- 1 signature changed (`RunService.create_run()`)
- ~5 test files updated
- 3 migrations (2 schema + 1 data)
- Phase 3 deferred to follow-up PR
