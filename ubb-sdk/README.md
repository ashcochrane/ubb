# ubb-sdk — Quick-start guide

Two journeys covered here:
- **Journey 1** — Cost attribution: get per-customer COGS in under 20 lines (metering only, no Stripe required).
- **Journey 2** — Multi-axis billing: subscriptions + seats + usage, billed through Stripe Connect.

---

## Journey 1 — Cost attribution

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

> **⚠️ Uncosted metrics:** if `record_usage(...)` returns a non-empty `uncosted_metrics`, those
> metrics had **no matching cost rate-card and priced to $0** — your COGS is understated for them.
> Either add a cost card for the metric, or enable `require_cost_card_coverage` on the tenant to
> **hard-reject (422)** instead of silently pricing $0.

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

### 4. Multi-dimension cost breakdown

Pass `dimensions` as a list to slice COGS by any combination of `product_id`,
`service_id`, `agent_id`, or any `tag:key` you tag events with. The response
includes a `breakdowns` dict keyed by dimension name — each value is a list of
per-value rows. An `(unattributed)` bucket collects events that have no value
for that dimension, so the rows always reconcile to `total_provider_cost_micros`.

```python
analytics = client.usage_analytics(
    customer_id="cust-uuid-here",
    dimensions=["product_id", "service_id", "agent_id"],
)

for dim, rows in analytics["breakdowns"].items():
    for row in rows:
        print(dim, row["dimension"], row["total_provider_cost_micros"])
# dim="product_id"  dimension="search"         total_provider_cost_micros=45000
# dim="product_id"  dimension="(unattributed)" total_provider_cost_micros=3000
```

### 5. Time-series spend rollup

```python
series = client.usage_timeseries(
    customer_id="cust-uuid-here",
    granularity="day",   # "hour" | "day"  (only these two values; others → 422)
    group_by="product_id",
)
for row in series["series"]:
    print(row["bucket"], row.get("dimension"), row["provider_cost_micros"])
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

## Retries

All clients automatically retry transient failures: HTTP `429`, `502`, `503`, `504`,
plus timeouts and connection errors — with jittered exponential backoff (0.5s base,
doubling, ±25% jitter, capped at 10s). A server-supplied `Retry-After` header is
honored, capped at 30s. Hard-stop 429s (`UBBHardStopError`), `UBBRunNotActiveError`,
and all other 4xx errors are **never** retried. Pass `max_retries=0` to any client
constructor to disable retries.

## Verified method signatures

```python
# MeteringClient.__init__
MeteringClient(api_key: str, base_url: str = "http://localhost:8001", timeout: float = 10.0,
    max_retries: int = 3)

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

# usage_analytics  → dict  (pass dimensions=["product_id","service_id"] for breakdowns)
client.usage_analytics(*, start_date=None, end_date=None, customer_id=None, tag_key=None,
    dimensions=None)

# usage_timeseries  → dict
client.usage_timeseries(*, granularity="day", start_date=None, end_date=None,
    customer_id=None, group_by=None)
```

## RecordUsageResult fields

| Field | Meaning |
|---|---|
| `event_id` | Unique ID for this event |
| `provider_cost_micros` | COGS computed from rate cards |
| `uncosted_metrics` | Metrics with no matching cost card |
| `billed_cost_micros` | Amount charged to the customer wallet |
| `balance_after_micros` | Customer wallet balance after this event |

---

## Journey 2 — Multi-axis billing (subscriptions + seats + usage)

Journey 2 layers Stripe-backed subscription billing on top of J1 metering.  It requires
`billing_mode="postpaid"` (or `"prepaid"`) and `products=["metering","billing","subscriptions"]`
on the tenant, plus a connected Stripe account.

```python
from ubb.client import UBBClient

client = UBBClient(api_key="ubb_live_...", base_url="http://localhost:8001")
```

### Step 1 — Connect Stripe (one-time per tenant)

```python
# Get the OAuth redirect URL and send the tenant there
onboarding = client.start_connect_onboarding(return_url="https://yourapp.com/connect/callback")
print(onboarding["authorize_url"])   # redirect tenant to this URL

# After they return, confirm the connection is live
status = client.get_connect_status()
# {"account_id": "acct_...", "charges_enabled": true, "onboarded": true}
print(status)
```

> **Note:** in local development the server is seeded without a real Stripe account.
> Use `python manage.py seed_dev_data --stripe-account acct_test` (a placeholder ID) to
> create the tenant, then call `start_connect_onboarding` and complete the OAuth flow in
> your Stripe test environment before subscriptions will actually charge.

### Step 2 — Define a billing plan

```python
plan = client.create_plan(
    key="pro-monthly",
    name="Pro (monthly)",
    access_fee_micros=10_000_000,   # $10/month platform fee
    per_seat_micros=5_000_000,      # $5/seat/month
    interval="month",               # "month" | "year"
    usage_mode="invoice_item",      # usage is billed on its own standalone invoice, not appended here
)
print(plan["key"])   # "pro-monthly"
```

### Step 3 — Create a customer and subscribe

```python
# Create the end-customer (account_type defaults to "individual")
cust = client.create_customer(
    external_id="org-42",
    stripe_customer_id="cus_...",   # Stripe customer you already created
)

# Subscribe to the plan — access fee + initial seat count billed through Stripe
sub = client.subscribe_customer("org-42", plan_key="pro-monthly", seats=5)
# {"subscription_id": "sub_...", "amount_micros": 35000000, "quantity": 5}
print(sub)
```

### Step 4 — Change seat count

```python
result = client.set_seats("org-42", seats=8)
# {"seats": 8}
print(result)
```

### Step 5 — Usage events are the same as J1

Usage recorded via `client.record_usage(...)` is billed on its OWN standalone, auto-finalized
Stripe invoice at period close (a two-phase create-draft-then-pin flow). A postpaid customer
receives TWO Stripe invoices per period: the subscription renewal (access fee + seats) and a
separate usage invoice. `usage_mode` does not change this — usage is never appended to the
subscription invoice. (Consolidating both onto one bill is deferred, not shipped.)

### Step 6 — End-customer can view their own bills

These endpoints use a **widget JWT** (issued by `create_widget_token`) and return data
only for the authenticated customer (billing-owner only for consolidated invoices):

```
GET /api/v1/me/usage-invoices         # usage line items billed to this customer
GET /api/v1/me/subscription-invoices  # subscription invoices (access fee + seats)
GET /api/v1/me/balance                # wallet balance (prepaid customers)
```

### J2 verified method signatures

```python
# UBBClient.__init__
UBBClient(api_key: str, base_url: str = "http://localhost:8001", timeout: float = 10.0,
    max_retries: int = 3)

# start_connect_onboarding  → dict  (keys: authorize_url)
client.start_connect_onboarding(return_url: str = "")

# get_connect_status  → dict  (keys: account_id, charges_enabled, onboarded)
client.get_connect_status()

# create_plan  → dict
client.create_plan(key: str, name: str, *, access_fee_micros: int = 0,
    per_seat_micros: int = 0, interval: str = "month",
    usage_mode: str = "invoice_item")

# subscribe_customer  → dict  (keys: subscription_id, amount_micros, quantity)
client.subscribe_customer(external_id: str, plan_key: str, seats: int = 0)

# set_seats  → dict  (keys: seats)
client.set_seats(external_id: str, seats: int)

# create_customer  → CustomerResult
client.create_customer(external_id: str, stripe_customer_id: str = "",
    metadata: dict | None = None, account_type: str = "individual",
    parent_external_id: str = "", billing_topology: str = "")
```

---

## Running the dev server

```bash
cd ubb-platform
# Journey 1 only (no real Stripe account needed):
python manage.py seed_dev_data --stripe-account acct_test
# Journey 2: replace acct_test with your real Stripe Connected Account ID,
# then run start_connect_onboarding to complete OAuth before subscribing customers.
python manage.py runserver 8001
```
