# ubb-sdk — Quick-start guide

> **Upgrading from v2.x?** v3.0 is a single coordinated breaking release
> (problem+json errors + a generated typed core). Read
> **[MIGRATION.md](./MIGRATION.md)** for every breaking edge, and
> **[CHANGELOG.md](./CHANGELOG.md)** for the release stamp.

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

### 1. Declare a cost book

Tell the engine what your supplier charges you (COGS). A **cost book** names one supplier and the
currency it bills you in; the rules inside it are what price your measurements.

```python
book = client.declare_cost_book(key="openai", provider_key="openai", currency="usd")
print(book.id)
```

The book arrives **empty** — UBB ships no catalogue, so it prices nothing until rules are published
into it. Rules are added by **publishing**, never by editing in place: you declare a draft of the
changes you want at `POST /api/v1/metering/pricing/books/{book_id}/publishes`, read its diff, and
publish it. The instant it takes effect can be stated, including a future one, so a rise agreed for
the first of next month is recorded once rather than remembered.

That surface is reachable through the generated core (`ubb._core`); the hand-written client wraps
the books themselves — `declare_cost_book`, `declare_pricing_book`, the two `withdraw_*` and the two
`list_*` — and does not yet wrap the publish surface.

> **⚠️ `update_rate_card`, `get_rate_card_history` and `bulk_create_rate_cards` are gone.** All
> three addressed flat paths this API has never published — they exist in no specification and in
> no router — so a call written against an older copy of this guide failed at runtime rather than
> returning the wrong answer. There is nothing to migrate off: there was never a working call to
> migrate. Declare a book and publish rules into it, as above.

### 2. Record a usage event

Supply `measurements` — the engine looks up the matching rules in your cost books and computes COGS
automatically.
Do **not** pass `provider_cost_micros` when you want the engine to price it.

```python
res = client.record_usage(
    customer_id="cust-uuid-here",
    idempotency_key="idem-abc-123",
    dimensions={"product_id": "search"},
    measurements={"input_tokens": 1000},
)

print(res.provider_cost_micros)          # COGS in micros, or None if UBB does not know it
print(res.costing_status)                # known | unresolved | not_applicable
print(res.uncosted_measurement_keys)     # measurement keys with no matching cost rule
```

> **⚠️ A cost UBB cannot work out is `None`, never `0`.** If `record_usage(...)` answers
> `costing_status == "unresolved"`, the event **was recorded** — your supplier already ran that
> call and already charged for it, so UBB never throws the record away — and
> `provider_cost_micros` is `None` rather than a number you could mistake for "free".
> `uncosted_measurement_keys` names the measurements that need a cost rate declared; add one and
> the cost resolves. `costing_status == "not_applicable"` is different again: that Event Type
> declares no cost at all, which is a design decision and not something to fix.
> An event that measures nothing at all is a marker event and is accepted — there is nothing to
> resolve a rule against, and nothing was claimed to have been consumed. Pass
> `provider_cost_micros` directly whenever the cost is known but the measurements are not.

`res.uncosted_measurement_keys` is your signal that a measurement was recorded with no cost rule —
publish one into a cost book for any measurement key you want costed. **This is not a refusal:**
earlier versions
could reject such a call with `422 pricing_error` under a tenant setting, and both the setting and
that error code are gone.

### 2b. Caller timestamps (backfill) and batch ingestion

Pass `recorded_at` (timezone-aware `datetime` or ISO-8601 string with offset) to timestamp the
event when it actually happened — e.g. replaying a day of events after an integration outage.
Omitted = server receive time. A **naive** datetime raises `ValueError` client-side before any
HTTP request.

```python
from datetime import datetime, timezone

client.record_usage(
    customer_id="cust-uuid-here",
    idempotency_key="idem-late-1",
    measurements={"input_tokens": 1000},
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
    {"customer_id": "cust-1", "idempotency_key": "k1",
     "measurements": {"input_tokens": 500}},
    {"customer_id": "cust-1", "idempotency_key": "k2",
     "measurements": {"input_tokens": 800},
     "recorded_at": "2026-06-01T12:00:00+00:00"},
])
print(batch.accepted, batch.rejected)
for item in batch.results:
    print(item.accepted, item.event_id if item.accepted else item.code)
```

> **Retry guidance:** on a network failure, retry the **whole batch**. Per-item idempotency
> keys guarantee a full replay returns the original event ids with zero new rows (a duplicate
> key *within* one batch resolves to the first item's event id).

### 2c. Start a unit of work, and declare how it ended

A unit of work — a workflow run, one piece of work for one customer — is registered with
`start_task` and closed by declaring its outcome. The start takes **your** idempotency key:
unique per customer, stable across retries, never minted on the line. Send the same key again
and you get the unit you already started (`task.replayed`) and nothing is created twice. The
answer is a handle; use it as a `with` block around the whole run, pass its `task_id` on every
usage event, and declare the ending inside the block with exactly one of three methods:

```python
from ubb import vocabulary

with client.start_task("cust-uuid-here", "nightly-42", task_type="transcode") as task:
    res = client.record_usage("cust-uuid-here", "idem-1", task_id=task.task_id,
                              measurements={"input_tokens": 1000})
    task.complete()      # delivered — the one ending that can create a charge
    # task.fail(vocabulary.OUTCOME_REASON_TIMEOUT, reason_detail="...")  — a reason is required
    # task.cancel()                                                       — a reason is optional
```

The block declares an ending only where its own control flow is evidence for one:

| The block | The handle does |
|---|---|
| ends after an explicit `complete()` / `fail()` / `cancel()` | nothing — the declaration stands |
| ends cleanly with **no** declaration | raises `TaskOutcomeRequired` and **leaves the work open** |
| an ordinary exception escapes it | declares `failed` with reason `execution_failed`, then re-raises it |
| `UBBStopRequested`, `KeyboardInterrupt`, any other `BaseException` | declares nothing; it propagates unchanged |

`TaskOutcomeRequired` is an ordinary `UBBError`, and it is wanted in production: UBB never
guesses an ending, because the forgiving answer and the answer that moves money are the same
word. It carries the handle, so `exc.task.complete()` still lands. `outcome_reason` values come
from `ubb.vocabulary.OUTCOME_REASON_VALUES` (`unspecified` is always available); the states a
unit can have ended in are `ubb.metering.TERMINAL_TASK_STATUSES`. Your own key-values — a
report id, an output location — are `metadata`, declared on the start; a completion takes no
payload. `get_task`, `list_tasks` and `list_subtasks` read the work back, and
`close_task(task_id, outcome)` is the primitive for closing by id from somewhere the handle
did not travel.

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

### 4. Cost breakdown across several grouping fields

Pass `dimensions` as a list to slice COGS by any combination of `product_id`,
`service_id`, `agent_id`, or any `tag:key` you tag events with. The response
includes a `breakdowns` dict keyed by grouping field, each value a list of
per-value rows. An `(unattributed)` bucket collects events with no value for
that field, so the rows always reconcile to `total_provider_cost_micros`.

> **The row's value key is `"grouping_field_value"`, the same property the
> declared `/margin/by-grouping-field` rows publish.** These analytics routes
> return an open dict, so the key is not in the schema and this SDK hands the
> rows to you as they arrive rather than renaming anything in flight — but the
> three rollups now agree on one word for a row's grouped value.
>
> **This key changed in the release that renamed it server-side.** It was
> previously the retired word the registry route dropped, and both moved
> together on purpose: a client that renamed the read on its own would have
> agreed with its own tests and disagreed with a running server.
>
> The request keyword `dimensions` has NOT moved — the registry route is
> already `/grouping-fields`, and the request property follows in the slice
> that owns it.

```python
analytics = client.usage_analytics(
    customer_id="cust-uuid-here",
    dimensions=["product_id", "service_id", "agent_id"],
)

for field, rows in analytics["breakdowns"].items():
    for row in rows:
        print(field, row["grouping_field_value"], row["total_provider_cost_micros"])
# field="product_id"  grouping_field_value="search"         total_provider_cost_micros=45000
# field="product_id"  grouping_field_value="(unattributed)" total_provider_cost_micros=3000
```

### 5. Time-series spend rollup

When you pass `group_by`, each bucket carries the grouped value under the same
wire key §4 describes, for the same reason — this is the second of the two open
analytics payloads. Omit `group_by` and the key is simply absent, which is why
the sample below reads it with `.get`.

```python
series = client.usage_timeseries(
    customer_id="cust-uuid-here",
    granularity="day",   # "hour" | "day"  (only these two values; others → 422)
    group_by="product_id",
)
for row in series["series"]:
    print(row["bucket"], row.get("grouping_field_value"), row["provider_cost_micros"])
```

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
plain non-expiring base money. Webhook events `credit_grant.expiring`
(7 days out, one-shot) and `credit_grant.expired` let you notify
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

- `unit_quantity`: the denominator — `1` means per-token; `1_000_000` means per-million-tokens.

The two that used to head this list — the one saying whether a rule held a supplier's cost or a
customer's price, and the one naming its arithmetic — are not parameters of this SDK any more. The
first is answered by *which book* a rule lives in: a cost book records what a supplier charges you,
a Pricing Book what you charge a customer, and they are separate entities on separate paths. The
second is `rate_structure` on a published change, `per_unit` or `fixed_component`.

## Canonical value names

`ubb.vocabulary` is **generated** from the UBB repository's vocabulary registry, so a
value the API can return is a value you can name instead of retyping:

```python
from ubb import vocabulary

if task.status == vocabulary.TASK_STATUS_COMPLETED:
    ...
```

It is a module rather than a star-export, so nothing lands in `ubb`'s top-level
namespace. Two names per value set, and the difference matters:

| Name | Means |
|---|---|
| `<CONCEPT>_VALUES` | A closed set — exactly these values, no more. |
| `<CONCEPT>_KNOWN_VALUES` | What UBB recognises **today**. |

`_KNOWN_VALUES` never decides a rejection. UBB's contract has open enums by design, so
a value that is not in the set is still legal and may arrive without a new SDK release
— `raise` on an unrecognised status and your integration breaks on the day UBB adds
one. Branch on the values you handle and let the rest fall through.

Do not edit the module: CI regenerates it and fails on any diff.

## Retries

All clients automatically retry transient failures: HTTP `429`, `502`, `503`, `504`,
plus timeouts and connection errors — with jittered exponential backoff (0.5s base,
doubling, ±25% jitter, capped at 10s). A server-supplied `Retry-After` header is
honored, capped at 30s. Every other 4xx (`400`/`403`/`404`/`405`/`409`/`410`/`422`)
is **never** retried. A spend stop rides a `200` — the event was recorded — so it is
never an error to retry, and the SDK never retries one: `record_usage` raises it as
`UBBStopRequested` only after the acknowledgement is back. Pass `max_retries=0` to
any client constructor to disable retries.

## Honouring a spend stop

`record_usage` **raises by default** when the acknowledgement says stop. The signal,
`UBBStopRequested`, derives from `BaseException` — not `Exception` and not
`UBBError` — for the reason `KeyboardInterrupt` does: your own `except Exception:`
around a provider loop cannot swallow the one signal that protects your customer's
money and carry on spending. The event **was recorded and charged**; the signal is
about the next call, never a failed submission, and it carries the whole
acknowledgement (`stop.result`) plus `event_id`, `idempotency_key`, `stop_scope`,
`stop_reason` and `task_id`. Catch it **once**, at the outermost boundary that can
honour its scope, and never resend the event:

```python
from ubb import UBBStopRequested

try:
    run_customer_work()                     # record_usage(...) inside, per call
except UBBStopRequested as stop:
    log.info("UBB requested a stop", extra={"scope": stop.stop_scope,
                                           "reason": stop.stop_reason,
                                           "event_id": stop.event_id})
    stop_dispatching_new_work(stop.stop_scope)   # "task", or the whole "customer"
```

Inside a `with client.start_task(...)` block the stop propagates the same way and the
block declares **nothing** — a stop is evidence of a stop, not of how the work ended — so
the handler above is also where you decide whether that unit of work is `cancel()`led or
`fail()`ed.

A bare `except:` or `except BaseException:` still catches it; that is accepted, the
objective being the common accidental failure rather than technical impossibility.
The rule for such a handler is the one Python already has for `KeyboardInterrupt`:
**re-raise anything outside `Exception` unless you are handling that specific named
signal** — a broad handler that swallows `BaseException` swallows the stop with it.
Every ordinary SDK failure stays an `Exception` under `UBBError`.

`record_usage(..., raise_on_stop=False)` returns the same acknowledgement with
`result.stop` set instead of raising. The one reason to choose it is recording work
that has **already** happened one call at a time, where a stop raised part-way would
leave the rest unrecorded — and `record_batch` is the better tool for that, because
it **never raises**: each item carries its own `stop` / `stop_reason` / `stop_scope`,
`result.stop` says whether any item asked for one, and `result.first_stop_index`
names the earliest that did. One stopped piece of work does not abandon the other
forty-nine.

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

# declare_pricing_book  → PricingBookOut     (what this tenant charges)
client.declare_pricing_book(*, key, name="", is_default=False)

# declare_cost_book  → CostBookOut           (what one supplier charges this tenant)
client.declare_cost_book(*, key, provider_key="", name="", currency=None, is_default=False)

# withdraw_pricing_book / withdraw_cost_book  → dict
client.withdraw_pricing_book(book_id)

# list_pricing_books / list_cost_books  → list[PricingBookOut] / list[CostBookOut]
client.list_pricing_books(cursor=None, limit=None)

# record_usage  → RecordUsageResponse
client.record_usage(customer_id: str, idempotency_key: str, *,
    provider_cost_micros=None, claimed_provider_cost_micros=None,
    provider="", event_type="", currency=None,
    dimensions=None, metadata=None, task_id=None, measurements=None,
    recorded_at=None, raise_on_stop=True)      # a stop verdict raises UBBStopRequested

# record_batch  → BatchResult  (results: list[BatchItemResult], accepted, rejected,
#                               stop, first_stop_index) — never raises
client.record_batch(events: list[dict])

# start_task  → StartedTask  (a context manager: complete() / fail(outcome_reason) / cancel();
#                             a clean exit with no declaration raises TaskOutcomeRequired)
client.start_task(customer_id: str, idempotency_key: str, *,
    task_type=None, parent_task_id=None, provider_cost_limit_micros=None,
    dimensions=None, external_task_id=None, metadata=None)

# close_task  → CloseTaskResponse  (the primitive the handle's three methods delegate to)
client.close_task(task_id: str, outcome: str, *, outcome_reason=None, reason_detail=None)

# get_task  → TaskDetailOut · list_tasks / list_subtasks  → PaginatedResponse[TaskOut]
client.get_task(task_id: str)
client.list_tasks(*, cursor=None, limit=None, customer_id=None, task_type=None, status=None)
client.list_subtasks(task_id: str, *, cursor=None, limit=None)

# usage_analytics  → dict  (pass dimensions=["product_id","service_id"] for breakdowns)
client.usage_analytics(*, start_date=None, end_date=None, customer_id=None, tag_key=None,
    dimensions=None, past_limit=None, stop_scope=None, episode_seq=None)

# usage_timeseries  → dict
client.usage_timeseries(*, granularity="day", start_date=None, end_date=None,
    customer_id=None, group_by=None)
```

## RecordUsageResponse fields

| Field | Meaning |
|---|---|
| `event_id` | Unique ID for this event |
| `provider_cost_micros` | COGS computed from your cost rules — `None` when UBB does not know it |
| `costing_status` | Whether that COGS is settled: `known` / `unresolved` / `not_applicable` |
| `uncosted_measurement_keys` | Measurements with no matching cost rule |
| `billed_cost_micros` | Amount charged to the customer wallet |
| `new_balance_micros` | Customer wallet balance after this event |
| `stop` / `stop_scope` / `stop_reason` | Spend-stop verdict (rides this 200 response; `record_usage` raises it as `UBBStopRequested` by default, carrying this whole object as `stop.result`) |

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
separate usage invoice. (Tenants can opt into consolidating usage onto the subscription
renewal — configured platform-side via the postpaid usage config, not the SDK.)

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
    per_seat_micros: int = 0, interval: str = "month")

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

## What this SDK reaches, and what it does not

`operation-coverage.yaml` lists every operation the API publishes and what this
SDK does about it — generated from `openapi/v1.json` and this package's source,
never hand-maintained (#204, ADR-0007 §4):

| | |
|---|---|
| `wrapped` | an ergonomic method calls it — the surface documented above |
| `generated_only` | no ergonomic method; reach it through `ubb._core` |
| `not_yet_wrapped` | not reachable through this SDK at all |

Today that is 78 wrapped and 56 `generated_only`, and the gap is deliberate
rather than a backlog: the eight `/api/v1/me/*` operations are the end-customer
widget surface and need a widget token rather than a tenant key, and the health
and readiness probes are for an orchestrator. A rise in the unwrapped count
needs a signed entry in `coverage-authorisations.yaml`, so a new operation
cannot arrive unwrapped by accident.

Regenerate with `python -m tools.sdk_operations --write` from the git root; CI
fails on a stale copy.

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
