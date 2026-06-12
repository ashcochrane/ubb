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
> In strict mode, events with `units > 0` but **no `usage_metrics`** are also rejected (no metric
> name means no rate card can be matched); pass `provider_cost_micros` directly if the cost is
> known, or set `units=0` for zero-cost marker events.

`res.uncosted_metrics` is your signal that a metric was recorded but has no cost card — add a
card for any metric you want tracked.

### 2b. Caller timestamps (backfill) and batch ingestion

Pass `recorded_at` (timezone-aware `datetime` or ISO-8601 string with offset) to timestamp the
event when it actually happened — e.g. replaying a day of events after an integration outage.
Omitted = server receive time. A **naive** datetime raises `ValueError` client-side before any
HTTP request.

```python
from datetime import datetime, timezone

client.record_usage(
    customer_id="cust-uuid-here",
    request_id="req-late-1",
    idempotency_key="idem-late-1",
    usage_metrics={"input_tokens": 1000},
    recorded_at=datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc),
)
```

Backfill is bounded by the tenant's **backfill window** (default **34 days**, configurable
0–60; 0 disables backfill entirely). Rejections are typed 422 errors:

| 422 code | Meaning |
|---|---|
| `effective_at_naive` | timestamp has no timezone offset |
| `effective_at_in_future` | more than 5 minutes ahead of server time |
| `effective_at_too_old` | older than the tenant's backfill window |
| `billing_period_closed` | that month's usage invoice already touched Stripe |

`record_batch` posts up to 100 events in one request. Items are **independent** — each commits
(or fails) on its own, and the call always returns HTTP 200 with per-item results aligned to
your input order:

```python
batch = client.record_batch([
    {"customer_id": "cust-1", "request_id": "r1", "idempotency_key": "k1",
     "usage_metrics": {"input_tokens": 500}},
    {"customer_id": "cust-1", "request_id": "r2", "idempotency_key": "k2",
     "usage_metrics": {"input_tokens": 800},
     "recorded_at": "2026-06-01T12:00:00+00:00"},
])
print(batch.succeeded, batch.failed)
for item in batch.results:
    print(item.ok, item.event_id or item.error)
```

> **Retry guidance:** on a network failure, retry the **whole batch**. Per-item idempotency
> keys guarantee a full replay returns the original event ids with zero new rows (a duplicate
> key *within* one batch resolves to the first item's event id).

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

### 6. Tiered pricing (graduated + package price cards)

Price cards (`card_type="price"`) support `pricing_model="graduated"` (a per-period
ladder of rate bands) and `"package"` (per-block pricing, e.g. $5 per 1,000 calls,
any partial block rounds up). Cost cards stay `per_unit`/`flat`.

```python
card = client.create_rate_card(
    card_type="price",
    metric_name="api_calls",
    pricing_model="graduated",
    tiers=[
        # first 10,000 calls at $0.01/call, the rest at $0.005/call
        {"up_to": 10_000, "rate_per_unit_micros": 10_000, "unit_quantity": 1},
        {"up_to": None,   "rate_per_unit_micros": 5_000,  "unit_quantity": 1},
    ],
)
```

Each tier may also carry `flat_micros` (charged once, when the period's usage first
enters that band). The last tier must have `up_to=None` (unbounded).

> **Billed amounts are MARGINAL.** Every event is billed as the difference between the
> period's cumulative charge before and after the event — so an event can legitimately
> bill **0** inside an already-purchased package block, and the event that crosses a
> graduated band boundary is billed across both bands. The sum of all event amounts in
> a period is exact: it always equals the tier formula applied to the period total.

`pricing_model="package"` uses the card's scalar fields instead of `tiers`:
`rate_per_unit_micros` = price per block, `unit_quantity` = block size,
`fixed_micros` = one-time period fee.

## Expiring credit grants (paid vs promo)

Prepaid wallets support **credit grant lots** on top of the plain balance:
`kind="paid"` (real money — withdrawable) or `kind="promo"` (bonus credit —
spendable on usage but **never withdrawable**). Lots can expire; expired
remainder is debited from the balance automatically (lazily at spend time and
by an hourly sweeper). Usage consumes the soonest-expiring lot first (promo
before paid on ties), then non-expiring lots, then the base balance.

Usage **refunds are lot-aware**: refunding a usage charge restores the lots
that funded it — promo money goes back into the promo lot, so it stays
non-withdrawable; it never converts to cash via a refund. Only the
base-funded share of the charge (plus shares from lots that have since
expired or been voided) comes back as plain base credit.

```python
from ubb.billing import BillingClient

billing = BillingClient(api_key="ubb_live_...")

# Give a customer $10 of promo credit that expires in 30 days.
grant = billing.create_grant(
    customer_id=customer.id,            # platform customer UUID
    kind="promo",
    amount_micros=10_000_000,           # $10.00
    expires_in_days=30,                 # or expires_at="2026-07-01T00:00:00Z"
    idempotency_key="welcome-bonus-cust-42",   # REQUIRED — retries are safe
    description="Welcome bonus",
)
# grant.remaining_micros == 10_000_000, grant.status == "active"

# Inspect lots and the balance breakdown.
page = billing.list_grants(customer_id=customer.id, status="active")
bal = billing.get_balance(customer_id=customer.id)
# bal.promo_micros        — active promo remaining (not withdrawable)
# bal.expiring_micros     — total remaining that has an expiry date
# bal.next_expiry_at      — soonest expiry (ISO-8601) or None

# Revoke an unused grant (debits its remaining; never below zero).
billing.void_grant(customer_id=customer.id, grant_id=grant.id)
```

Paid top-ups (checkout + auto-top-up) create `paid` lots automatically; they
never expire unless the customer's billing profile sets
`topup_grant_expiry_days`. The legacy `credit()` call is untouched — it adds
plain non-expiring base money. Webhook events `billing.credit_grant_expiring`
(7 days out, one-shot) and `billing.credit_grant_expired` let you notify
customers.

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
- `pricing_model`: `"per_unit"` (rate × quantity / unit_quantity), `"flat"` (fixed charge per
  event), `"graduated"` (per-period rate bands — price cards only), or `"package"`
  (per-block, rounds up — price cards only).
- `unit_quantity`: the denominator — `1` means per-token; `1_000_000` means per-million-tokens.

## Retries

All clients automatically retry transient failures: HTTP `429`, `502`, `503`, `504`,
plus timeouts and connection errors — with jittered exponential backoff (0.5s base,
doubling, ±25% jitter, capped at 10s). A server-supplied `Retry-After` header is
honored, capped at 30s. Hard-stop 429s (`UBBHardStopError`), `UBBRunNotActiveError`,
and all other 4xx errors are **never** retried. Pass `max_retries=0` to any client
constructor to disable retries.

## Verifying webhooks

UBB signs every outgoing webhook delivery. Verify with the v2 (timestamped)
header — it bounds replay: a captured delivery stops verifying once its signed
timestamp falls outside your tolerance window (default 300s).

- `X-UBB-Signature-V2: t=<unix-seconds>,v1=<hexdigest>` where
  `hexdigest = HMAC-SHA256(secret, f"{t}.{raw_body}")` — **verify this one.**
- `X-UBB-Signature: <hexdigest>` over the raw body only — the legacy scheme,
  still sent during the deprecation window. It has **no timestamp binding**, so
  a captured delivery replays forever; only verify it via
  `verify_webhook_legacy` while migrating, then switch to v2.

Always pass the **raw request body bytes** — verify before parsing JSON.

```python
# Flask
from flask import Flask, request, abort
from ubb import verify_webhook, UBBWebhookVerificationError

app = Flask(__name__)
WEBHOOK_SECRET = "..."  # the secret you registered on the webhook config

@app.post("/ubb/webhook")
def ubb_webhook():
    try:
        event = verify_webhook(
            request.get_data(),                          # RAW bytes
            request.headers.get("X-UBB-Signature-V2", ""),
            WEBHOOK_SECRET,
            tolerance=300,                               # seconds (default)
        )
    except UBBWebhookVerificationError:
        abort(400)
    if event["event_type"] == "usage.recorded":
        ...  # handle event["data"]
    return "", 200
```

```python
# FastAPI
from fastapi import FastAPI, Header, HTTPException, Request
from ubb import verify_webhook, UBBWebhookVerificationError

app = FastAPI()

@app.post("/ubb/webhook")
async def ubb_webhook(request: Request,
                      x_ubb_signature_v2: str = Header(default="")):
    try:
        event = verify_webhook(await request.body(), x_ubb_signature_v2,
                               WEBHOOK_SECRET)
    except UBBWebhookVerificationError:
        raise HTTPException(status_code=400, detail="bad signature")
    ...
    return {"ok": True}
```

`verify_webhook` raises `UBBWebhookVerificationError` on a bad signature, a
stale/future timestamp, or a malformed header, and returns the parsed payload
dict on success. Deliveries also carry `livemode` (false for sandbox tenants)
inside the payload.

## Verified method signatures

```python
# MeteringClient.__init__
MeteringClient(api_key: str, base_url: str = "http://localhost:8001", timeout: float = 10.0,
    max_retries: int = 3)

# create_rate_card  → RateCard
client.create_rate_card(*, card_type, metric_name, provider="", event_type="",
    dimensions=None, pricing_model="per_unit", rate_per_unit_micros=0,
    unit_quantity=1_000_000, fixed_micros=0, tiers=None, currency="usd",
    product_id="", customer_id=None)

# record_usage  → RecordUsageResult
client.record_usage(customer_id: str, request_id: str, idempotency_key: str, *,
    provider_cost_micros=None, billed_cost_micros=None, units=None,
    provider="", event_type="", currency=None, tags=None,
    product_id="", metadata=None, run_id=None, usage_metrics=None,
    recorded_at=None)

# record_batch  → BatchResult  (results: list[BatchItemResult], succeeded, failed)
client.record_batch(events: list[dict])

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

### Step 4b — Change plan pricing (versioned)

Stripe Prices are immutable, so a fee edit on an already-provisioned plan creates a NEW
versioned Price on the same Product and repoints the plan at it. New subscribers get the
new price automatically; **existing subscriptions are grandfathered on their old price**
unless you pass `migrate_existing=True` (each active subscription item is repointed
without proration).

```python
plan = client.update_plan("pro-monthly", per_seat_micros=6_000_000)
# {"key": "pro-monthly", ..., "per_seat_micros": 6000000, "pricing_version": 2}

# Move existing subscribers onto the new price too (no proration):
plan = client.update_plan("pro-monthly", per_seat_micros=6_000_000, migrate_existing=True)
```

### Step 4c — Cancel / pause / resume

```python
client.cancel_subscription("org-42")                        # at period end (default)
client.cancel_subscription("org-42", at_period_end=False)   # immediately

client.pause_subscription("org-42")    # collection voided; Stripe keeps status "active"
client.resume_subscription("org-42")   # clears a pause AND any pending at-period-end cancel
# each returns {"subscription_id", "status", "cancel_at_period_end", "paused"}
```

> **Non-goals:** trials and coupons are deliberately not wrapped — Stripe owns those
> levers (use `trial_period_days` / Coupons directly on your connected account).

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

# update_plan  → dict  (plan fields + pricing_version)
client.update_plan(key: str, *, access_fee_micros: int | None = None,
    per_seat_micros: int | None = None, migrate_existing: bool = False)

# cancel_subscription / pause_subscription / resume_subscription  → dict
#   (keys: subscription_id, status, cancel_at_period_end, paused)
client.cancel_subscription(external_id: str, at_period_end: bool = True)
client.pause_subscription(external_id: str)
client.resume_subscription(external_id: str)

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
