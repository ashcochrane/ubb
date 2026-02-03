# UBB Platform Redesign

## Overview

Redesign of UBB's billing model to support the following flow:

1. End-user tops up their account (pays tenant via Stripe Connect)
2. Money goes 100% to tenant's Stripe Connected Account (Stripe fees are tenant's cost)
3. End-user makes API calls through tenant's product
4. Tenant calls UBB for pre-check gating and usage recording
5. UBB prices usage (provider cost + tenant markup), debits customer wallet
6. UBB invoices tenant monthly for platform fees based on usage volume

UBB never holds end-user funds. The wallet is an accounting ledger. Money flows through the tenant's Stripe Connected Account.

## Money Flows

### Top-up (UBB takes nothing)

```
End-user pays $20 via Stripe Checkout (on tenant's Connected Account)
  -> Stripe takes 2.9% + $0.30 = $0.88 (tenant's cost)
  -> Tenant receives $19.12
  -> UBB webhook fires -> credits wallet ledger $20
  -> UBB creates Invoice as paid receipt
```

### Usage (wallet debit)

```
End-user -> Tenant API
Tenant -> UBB: POST /pre-check (can they afford it?)
UBB -> checks wallet balance -> yes/no
Tenant executes request (e.g. Gemini call)
Tenant -> UBB: POST /usage (raw metrics)
UBB -> prices it (ProviderRate + TenantMarkup)
UBB -> debits wallet, records UsageEvent
UBB -> if balance below auto-topup threshold, trigger charge
UBB -> returns cost + new balance
```

### Platform fee (monthly)

```
UBB calculates: sum(billed_cost_micros) for all usage events in period
Platform fee: tenant.platform_fee_percentage x total_usage_cost
UBB invoices tenant directly via Stripe
```

## Data Model Changes

### Remove

- `BillingPeriod` - no period-based end-user invoicing

### Modify

**`Invoice`** - simplify to a top-up receipt:

| Field | Type | Notes |
|-------|------|-------|
| tenant | FK | |
| customer | FK | |
| top_up_attempt | OneToOne | Replaces billing_period link |
| stripe_invoice_id | str | |
| total_amount_micros | bigint | |
| status | enum | draft / finalized / paid / void |
| finalized_at | datetime | nullable |
| paid_at | datetime | nullable |

**`Tenant`** - add widget support:

| Field | Type | Notes |
|-------|------|-------|
| + widget_secret | str | Auto-generated, rotatable. Used for JWT signing |

**`UsageEvent`** - add group keys:

| Field | Type | Notes |
|-------|------|-------|
| + group_keys | JSONField | Nullable. GIN indexed for containment queries |

`group_keys` constraints:
- Max 10 keys per event
- Key names: lowercase alphanumeric + underscores, max 64 chars
- Values: strings only, max 256 chars
- Validated at write time, queryable at read time only

### Add

**`TenantBillingPeriod`**:

| Field | Type | Notes |
|-------|------|-------|
| tenant | FK | |
| period_start | date | |
| period_end | date | |
| status | enum | open / closed / invoiced |
| total_usage_cost_micros | bigint | Sum of billed_cost_micros in period |
| event_count | int | |
| platform_fee_micros | bigint | total_usage_cost_micros x fee percentage |

**`TenantInvoice`**:

| Field | Type | Notes |
|-------|------|-------|
| tenant | FK | |
| billing_period | OneToOne | |
| stripe_invoice_id | str | |
| total_amount_micros | bigint | The platform fee amount |
| status | enum | draft / finalized / paid / void / uncollectible |
| finalized_at | datetime | nullable |
| paid_at | datetime | nullable |

### Unchanged

- `Tenant` (except widget_secret addition), `TenantApiKey`
- `Customer`, `Wallet`, `WalletTransaction`
- `UsageEvent` (except group_keys addition), `ProviderRate`, `TenantMarkup`
- `RiskConfig`, `StripeWebhookEvent`
- `Refund`
- `AutoTopUpConfig`, `TopUpAttempt`

## API Endpoints

### Unchanged

- `POST /pre-check` - balance gating
- `POST /usage` - record usage event
- `POST /customers` - create customer
- `GET /customers/{id}/balance` - wallet balance
- `GET /customers/{id}/usage` - paginated usage events
- `GET /customers/{id}/transactions` - paginated wallet transactions
- `POST /customers/{id}/top-up` - manual top-up
- `PUT /customers/{id}/auto-top-up` - configure auto top-up
- `POST /customers/{id}/withdraw` - withdraw from wallet
- `POST /customers/{id}/refund` - refund usage event
- `POST /webhooks/stripe` - webhook handler
- `GET /health`, `GET /ready`

### Modified

Usage endpoints gain `group_key` / `group_value` query params for filtering.

### New: Tenant Dashboard

Authenticated by tenant API key.

```
GET /tenant/billing-periods         - list TenantBillingPeriods
GET /tenant/billing-periods/{id}    - detail with usage breakdown by customer/provider/event_type
GET /tenant/invoices                - list TenantInvoices (platform fee invoices)
GET /tenant/analytics/usage         - usage breakdown by provider, event_type, customer
                                      supports date range, grouping (daily/weekly/monthly)
GET /tenant/analytics/revenue       - revenue breakdown: provider_cost vs billed_cost vs markup
                                      spending trends over time
```

### New: Widget Endpoints

Authenticated by JWT signed with tenant's widget_secret.

```
GET  /widget/balance         - { balance_micros, currency }
GET  /widget/transactions    - paginated top-ups and usage deductions
POST /widget/top-up          - creates Stripe Checkout session, returns checkout_url
GET  /widget/invoices        - paginated list of top-up receipts
```

Widget is headless API only. No pre-built UI components. Tenants build their own frontend.

## Authentication

### Tenant API Key (existing)

Used for: all existing endpoints + tenant dashboard endpoints.

Bearer token, verified via SHA256 hash lookup.

### Widget JWT (new)

Used for: widget endpoints only.

JWT structure:
```json
{
  "sub": "customer_uuid",
  "tid": "tenant_uuid",
  "exp": 1700000000,
  "iss": "ubb"
}
```

- Signed with `tenant.widget_secret` using HS256
- 15-minute expiry
- UBB verifies by looking up tenant from `tid`, checking signature against stored `widget_secret`

SDK helper:
```python
UBBClient.create_widget_token(customer_id: str, expires_in: int = 900) -> str
```

## Celery Tasks

### Remove

- `generate_weekly_invoices` - replaced by receipt-per-topup model

### Unchanged

- `expire_stale_topup_attempts` (every 5 min)
- `reconcile_wallet_balances` (hourly)
- `cleanup_webhook_events` (daily 3am UTC)
- `charge_auto_topup_task` (triggered on low balance)

### New

**`generate_topup_receipt_invoice`** (triggered after checkout.session.completed webhook):
- Creates Stripe Invoice on tenant's Connected Account as a paid receipt
- Saves to Invoice model linked to TopUpAttempt

**`close_tenant_billing_period`** (monthly, 1st of month 00:00 UTC):
- Closes open TenantBillingPeriod for each tenant
- Calculates platform_fee_micros
- Opens new period for current month

**`generate_tenant_platform_invoice`** (monthly, 1st of month 01:00 UTC):
- Creates Stripe Invoice for each closed TenantBillingPeriod without a TenantInvoice
- Billed directly to tenant (not via Connected Account)

**`accumulate_tenant_usage`** (triggered per usage event):
- Atomic UPDATE on current open TenantBillingPeriod
- Increments total_usage_cost_micros and event_count

### Celery Queues

- `ubb_topups` - top-up related tasks (unchanged)
- `ubb_webhooks` - webhook processing (unchanged)
- `ubb_invoicing` - receipt invoices + tenant platform invoices
- `ubb_billing` (new) - tenant billing period management

### Beat Schedule

- Every 5 min: `expire_stale_topup_attempts`
- Hourly: `reconcile_wallet_balances`
- Daily 3am UTC: `cleanup_webhook_events`
- 1st of month 00:00 UTC: `close_tenant_billing_period`
- 1st of month 01:00 UTC: `generate_tenant_platform_invoice`

## SDK Changes

- Add `create_widget_token(customer_id: str, expires_in: int = 900) -> str`
- All existing methods unchanged
