# Referrals Product Design

## Overview

`apps/referrals/` is the fourth product domain in UBB, sitting alongside metering, billing, and subscriptions. It provides a generic, tenant-configurable referral system where customers can refer new customers and earn rewards based on the referred customer's usage.

Tenants enable it via `products: ["metering", "referrals"]` (or any combination). The referral system is fully decoupled from billing — it tracks attribution and calculates earnings, but never handles payouts directly. Any billing system (UBB's own `apps/billing/` or an external one) can integrate via the event bus.

## Reward Types

Tenants choose one of three reward models when configuring their program:

- **Flat fee**: one-time payout of a fixed amount when the referred customer's first qualifying event occurs.
- **Revenue share**: referrer earns a percentage of the referred customer's total spend, accumulated on every usage event within the reward window.
- **Profit share**: referrer earns a percentage of profit (customer spend minus tenant's raw cost), accumulated on every usage event within the reward window.

## Domain Models

### ReferralProgram

Tenant-level configuration. One active program per tenant.

| Field | Type | Notes |
|---|---|---|
| tenant | FK(Tenant) | |
| reward_type | CharField | `flat_fee`, `revenue_share`, `profit_share` |
| reward_value | BigIntegerField / DecimalField | Micros for flat_fee, decimal percentage (e.g. 0.50) for share types |
| attribution_window_days | IntegerField | How long a referral link stays valid (e.g. 30) |
| reward_window_days | IntegerField, nullable | How long referrer earns from a referral. Null = forever |
| max_reward_micros | BigIntegerField, nullable | Optional cap on total earnings per referral |
| estimated_cost_percentage | DecimalField, nullable | Fallback for profit-share when `raw_cost_micros` not on usage events |
| status | CharField | `active`, `paused`, `deactivated` |

### Referrer

A customer registered as a referrer. Separate entity with FK to Customer (not nullable now, but designed so it could become nullable to support non-customer affiliates later).

| Field | Type | Notes |
|---|---|---|
| tenant | FK(Tenant) | |
| customer | FK(Customer) | |
| referral_code | CharField, unique | Auto-generated, e.g. `REF-abc123` |
| referral_link_token | CharField, unique | Token for link-based tracking |
| is_active | BooleanField | |

### Referral

A single attribution event: "Referrer X brought in Customer Y."

Snapshots the reward config at creation time so existing referrals are protected from retroactive program changes.

| Field | Type | Notes |
|---|---|---|
| tenant | FK(Tenant) | |
| referrer | FK(Referrer) | |
| referred_customer | FK(Customer) | |
| referral_code_used | CharField | The code or link token used |
| attributed_at | DateTimeField | |
| reward_window_ends_at | DateTimeField, nullable | Calculated from program config. Null = no expiry |
| status | CharField | `active`, `expired`, `revoked` |
| snapshot_reward_type | CharField | Frozen from program at creation |
| snapshot_reward_value | DecimalField | Frozen from program at creation |
| snapshot_max_reward_micros | BigIntegerField, nullable | Frozen from program at creation |
| snapshot_estimated_cost_percentage | DecimalField, nullable | Frozen from program at creation |
| flat_fee_paid | BooleanField | For flat_fee type: whether the one-time reward has been issued |

### ReferralRewardAccumulator

Running total of earnings per referral. Updated in real-time via event bus using `F()` expressions (same pattern as `CustomerCostAccumulator` in subscriptions).

| Field | Type | Notes |
|---|---|---|
| referral | FK(Referral), unique | One accumulator per referral |
| total_earned_micros | BigIntegerField | Running reward total |
| total_referred_spend_micros | BigIntegerField | Total spend by referred customer |
| event_count | IntegerField | Number of events counted |

### ReferralRewardLedger

Immutable log of reward entries, written by the batch reconciliation job.

| Field | Type | Notes |
|---|---|---|
| referral | FK(Referral) | |
| period_start | DateField | |
| period_end | DateField | |
| referred_spend_micros | BigIntegerField | |
| raw_cost_micros | BigIntegerField | Tenant's cost (actual or estimated) |
| reward_micros | BigIntegerField | |
| calculation_method | CharField | `actual_cost`, `estimated_cost`, `flat_fee` |

## Event Flow

### Attribution

1. Referrer shares their code (`REF-abc123`) or link (containing `referral_link_token`)
2. New customer signs up on the tenant's app
3. Tenant's app calls `POST /api/v1/referrals/attribute` with customer_id and code/link_token
4. UBB validates the code, checks attribution window (for links), creates the `Referral` record with snapshotted reward config, creates the `ReferralRewardAccumulator`
5. Emits `referral.created` event

### Real-time reward accumulation

1. `usage.recorded` fires on the event bus
2. Referrals handler checks: is this customer a referred customer with an active, non-expired referral?
3. If yes, calculate reward increment:
   - **Flat fee**: if `flat_fee_paid` is false, increment by `snapshot_reward_value`, set `flat_fee_paid = True`
   - **Revenue share**: `reward = cost_micros * snapshot_reward_value`
   - **Profit share**: if `raw_cost_micros` is present on the event, `profit = cost_micros - raw_cost_micros`, `reward = profit * snapshot_reward_value`. If `raw_cost_micros` is absent, use `snapshot_estimated_cost_percentage` as fallback: `estimated_cost = cost_micros * estimated_cost_percentage`, `profit = cost_micros - estimated_cost`. If neither is available, skip and defer to batch. If profit is negative, reward is zero.
4. Check `max_reward_micros` cap: if `accumulator.total_earned_micros + reward > max_reward_micros`, clamp to remaining amount
5. Increment `ReferralRewardAccumulator` using `F()` expressions
6. Emit `referral.reward_earned` event

### Batch reconciliation (daily Celery task)

- Sweeps all active referrals
- Recalculates from source usage data for the period
- Writes `ReferralRewardLedger` entries
- Corrects any drift in the accumulator
- Marks referrals past `reward_window_ends_at` as `expired`
- Emits `referral.expired` for newly expired referrals

## API Endpoints

All under `/api/v1/referrals/`, protected by `ApiKeyAuth` + `ProductAccess("referrals")`.

### Program management

| Method | Path | Description |
|---|---|---|
| POST | `/program` | Create a new referral program |
| GET | `/program` | Get current active program |
| PATCH | `/program` | Update program config (changes apply to new referrals only) |
| DELETE | `/program` | Deactivate program (existing referrals continue earning) |
| POST | `/program/reactivate` | Reactivate a deactivated program |

### Referrer management

| Method | Path | Description |
|---|---|---|
| POST | `/referrers` | Register a customer as a referrer (generates code + link token) |
| GET | `/referrers/{customer_id}` | Get referrer details, code, link token |
| GET | `/referrers` | List all referrers for the tenant |

### Attribution

| Method | Path | Description |
|---|---|---|
| POST | `/attribute` | Attribute a new customer to a referrer (customer_id + code or link_token) |

### Reward data

| Method | Path | Description |
|---|---|---|
| GET | `/referrers/{customer_id}/earnings` | Total earnings for a referrer, with optional period filtering |
| GET | `/referrers/{customer_id}/referrals` | List customers this referrer has brought in, with per-referral earnings |
| GET | `/referrals/{referral_id}/ledger` | Detailed reward ledger entries for a specific referral |

### Revocation

| Method | Path | Description |
|---|---|---|
| DELETE | `/referrals/{referral_id}` | Revoke a specific referral (fraud, etc.) |

### Tenant-level analytics

| Method | Path | Description |
|---|---|---|
| GET | `/analytics/summary` | Total referrals, total rewards earned, top referrers, conversion metrics |
| GET | `/analytics/earnings` | Breakdown of reward payouts across referrers for a period |

## Events Emitted

| Event | Data | Description |
|---|---|---|
| `referral.created` | referral_id, referrer_id, referred_customer_id, tenant_id | New customer attributed |
| `referral.reward_earned` | referral_id, referrer_id, reward_micros, total_earned_micros, tenant_id | Reward increment calculated |
| `referral.expired` | referral_id, referrer_id, total_earned_micros, tenant_id | Reward window ended |

External systems (including UBB billing) can listen to these to trigger payouts, wallet credits, notifications, etc.

## File Structure

```
apps/referrals/
├── __init__.py
├── apps.py                    # label="referrals"
├── models.py                  # ReferralProgram, Referrer, Referral
├── handlers.py                # EventBus handler for usage.recorded
├── tasks.py                   # Daily reconciliation + expiry tasks
├── api/
│   ├── __init__.py
│   ├── endpoints.py           # All API routes
│   ├── schemas.py             # Request/response schemas
│   └── webhooks.py            # Future: external webhook handling
├── rewards/
│   ├── __init__.py
│   ├── models.py              # ReferralRewardAccumulator, ReferralRewardLedger
│   ├── services.py            # Reward calculation logic (flat/revenue/profit)
│   └── reconciliation.py      # Batch reconciliation logic
├── tests/
│   ├── __init__.py
│   ├── test_models.py
│   ├── test_endpoints.py
│   ├── test_handlers.py
│   ├── test_rewards.py
│   ├── test_reconciliation.py
│   └── test_product_isolation.py
└── migrations/
```

## Integration Points

- **Listens to**: `usage.recorded` (accumulates rewards for referred customers)
- **Emits**: `referral.created`, `referral.reward_earned`, `referral.expired`
- **Never imports from**: `apps/billing/`, `apps/subscriptions/`
- **Only imports from**: `apps/platform/` (tenants, customers)
- **URL mount**: `path("api/v1/referrals/", referrals_api.urls)` in `config/urls.py`
- **SDK**: `ReferralsClient` added to `UBBClient`

## Key Design Decisions

1. **Referrers are always customers (for now)**: FK to Customer is non-nullable. Modeled as a separate `Referrer` entity so adding non-customer affiliates later is just making the FK nullable.
2. **Reward config snapshotted on referral creation**: program changes only affect new referrals. Protects referrers from retroactive changes.
3. **Profit-share uses `raw_cost_micros` from usage events when available, falls back to `estimated_cost_percentage` from program config**: gives tenants flexibility — pass actual costs per event or set a blanket estimate.
4. **Decoupled from billing**: referral system tracks and calculates, never pays out. Any billing system can integrate via events.
5. **Hybrid accumulation**: real-time `F()` increments for instant feedback, daily batch reconciliation for accuracy. Same pattern as subscriptions economics.
6. **Soft delete on programs**: deactivation stops new referrals but existing ones continue earning through their reward window.
