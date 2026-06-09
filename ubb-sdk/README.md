# ubb-sdk — Journey 1: Cost Attribution

Get per-customer COGS in under 20 lines.

## Install

```bash
pip install ubb-sdk
```

## Quickstart

```python
from ubb.metering import MeteringClient

client = MeteringClient(api_key="ubb_live_...", base_url="http://localhost:8001")
```

### 1. Create a cost rate card

Tell the engine what each metric costs you (COGS). `rate_per_unit_micros=2, unit_quantity=1`
means 2 micros per token ($0.000002/token).

```python
card = client.create_rate_card(
    card_type="cost",
    metric_name="input_tokens",
    pricing_model="per_unit",
    rate_per_unit_micros=2,
    unit_quantity=1,
)
print(card.id)
```

### 2. Record a usage event

Supply `usage_metrics` — the engine looks up matching cost cards and computes COGS automatically.
Do **not** pass `provider_cost_micros` when you want the engine to price it.

```python
res = client.record_usage(
    customer_id="cust-uuid-here",
    request_id="req-abc-123",
    idempotency_key="idem-abc-123",
    product_id="search",
    usage_metrics={"input_tokens": 1000},
)

print(res.provider_cost_micros)   # computed COGS in micros (e.g. 2000 = $0.002)
print(res.uncosted_metrics)       # list of metric names with no matching cost card
```

`res.uncosted_metrics` is your signal that a metric was recorded but has no cost card — add a
card for any metric you want tracked.

### 3. Read per-customer cost analytics

```python
analytics = client.usage_analytics(customer_id="cust-uuid-here")

print(analytics["total_provider_cost_micros"])   # total COGS for this customer

for row in analytics["by_product"]:
    print(row["product_id"], row["total_provider_cost_micros"])

# Add a tag breakdown (e.g. tag events with {"agent": "gpt-4o"})
analytics = client.usage_analytics(customer_id="cust-uuid-here", tag_key="agent")
for row in analytics["by_tag"]:
    print(row)
```

## Money representation

All amounts are integer **micros**: `1_000_000 micros = $1.00`. This avoids floating-point
rounding in billing math.

| Constant | USD |
|---|---|
| `2` | $0.000002 |
| `2_000` | $0.002 |
| `1_000_000` | $1.00 |

## Key parameters

- `card_type`: `"cost"` (COGS you pay the provider) or `"price"` (what you charge customers).
- `pricing_model`: `"per_unit"` (rate × quantity / unit_quantity) or `"flat"` (fixed charge per event).
- `unit_quantity`: the denominator — `1` means per-token; `1_000_000` means per-million-tokens.

## Verified method signatures

```python
# MeteringClient.__init__
MeteringClient(api_key: str, base_url: str = "http://localhost:8001", timeout: float = 10.0)

# create_rate_card  → RateCard
client.create_rate_card(*, card_type, metric_name, provider="", event_type="",
    dimensions=None, pricing_model="per_unit", rate_per_unit_micros=0,
    unit_quantity=1_000_000, fixed_micros=0, currency="usd",
    product_id="", customer_id=None)

# record_usage  → RecordUsageResult
client.record_usage(customer_id: str, request_id: str, idempotency_key: str, *,
    provider_cost_micros=None, billed_cost_micros=None, units=None,
    provider="", event_type="", currency=None, tags=None,
    product_id="", metadata=None, run_id=None, usage_metrics=None)

# usage_analytics  → dict
client.usage_analytics(*, start_date=None, end_date=None, customer_id=None, tag_key=None)
```

## RecordUsageResult fields

| Field | Meaning |
|---|---|
| `event_id` | Unique ID for this event |
| `provider_cost_micros` | COGS computed from rate cards |
| `uncosted_metrics` | Metrics with no matching cost card |
| `billed_cost_micros` | Amount charged to the customer wallet |
| `balance_after_micros` | Customer wallet balance after this event |

## Running the dev server

```bash
cd ubb-platform
python manage.py seed_dev_data --stripe-account acct_test
python manage.py runserver 8001
```
