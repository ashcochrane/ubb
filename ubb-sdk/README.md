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
    grouping_fields={"product_id": "search"},
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

### 3. Read what the work cost, what it earned, and the difference

**The three cost-analytics reads this guide used to document are gone (#501), and so are six
other published reports.** One query answers all nine:

```
GET /api/v1/metering/analytics/economics
```

`MeteringClient` does **not** wrap it yet — the handle is the next SDK ticket's, and the generated
core already carries the operation — so the quick-start shows the request itself rather than a call
that does not exist. `MIGRATION.md` §16 maps every removed call onto it, question by question.

What you ask for:

| Parameter | What it does |
| --- | --- |
| `measures` | one or more of `supplier_cogs`, `customer_revenue`, `gross_margin`, `recorded_events` |
| `group_by` | zero or more axes, each `field:<declared key>` or `rollup:<name>` |
| `bucket` | `hour`, `day` or `month`; omit it and the whole period is one row |
| `start_date` / `end_date` | the period; omitting `start_date` means *the retention horizon*, not the beginning of time |
| `customer_id`, `event_type`, `task_type`, `task_id`, `where` | filters, which narrow without grouping |
| `basis` | `recorded` or `recognised` |

What comes back: `rows`, each carrying `grouping_field_value` — a LIST, positional against the
`group_by` you sent, which the response echoes back beside `bucket`, `period_start` and
`period_end` — and one entry per measure you asked for.

> **⚠ Every measure carries a `status`, and the amount alone is not the answer.** `known` means
> every input resolved. `incomplete` means the figure is a bound and the counts beside it say how
> far off it can be. `unavailable_at_requested_grain` means the figure could not be attributed this
> finely — a revenue figure is the part that *could* be placed, with the rest in the answer's
> `context`, and a margin is `null` outright, because there is no such thing as a partial margin.
> `unavailable_outside_retention_horizon` means the row reaches back past what UBB still holds, and
> `available_from` says the day that measure's series can start. `not_applicable` means the measure
> does not apply to this row at all. **A reader that takes the amount and drops the status will
> publish a floor as a total.**

Two horizons come back on every answer — `economic_data_available_from` and
`measurement_data_available_from` — because money and measurements are kept for different lengths
of time.

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
    grouping_fields=None, metadata=None, task_id=None, measurements=None,
    recorded_at=None, raise_on_stop=True)      # a stop verdict raises UBBStopRequested

# record_batch  → BatchResult  (results: list[BatchItemResult], accepted, rejected,
#                               stop, first_stop_index) — never raises
client.record_batch(events: list[dict])

# start_task  → StartedTask  (a context manager: complete() / fail(outcome_reason) / cancel();
#                             a clean exit with no declaration raises TaskOutcomeRequired)
client.start_task(customer_id: str, idempotency_key: str, *,
    task_type=None, parent_task_id=None, task_cogs_ceiling_micros=None,
    grouping_fields=None, external_task_id=None, metadata=None)

# close_task  → CloseTaskResponse  (the primitive the handle's three methods delegate to)
client.close_task(task_id: str, outcome: str, *, outcome_reason=None, reason_detail=None)

# get_task  → TaskDetailOut · list_tasks / list_subtasks  → PaginatedResponse[TaskOut]
client.get_task(task_id: str)
client.list_tasks(*, cursor=None, limit=None, customer_id=None, task_type=None, status=None)
client.list_subtasks(task_id: str, *, cursor=None, limit=None)

# ONE QUERY REPLACED NINE REPORTS (#501) AND NOW HAS A HANDLE (#505). Ask for
# measures, group by zero or more axes, bucket by hour/day/month; every filter
# composes with every grouping. `measures` is required and the window defaults
# to the CURRENT MONTH TO DATE — name the dates unless the question is about now.
#
# query_economics  -> EconomicsOut
client.query_economics(*, measures: list[str], group_by=None,
    start_date=None, end_date=None, bucket=None, basis=None,
    customer_id=None, event_type=None, task_type=None, task_id=None,
    include_subtasks=None, where=None,
    past_limit=None, stop_scope=None, episode_seq=None)

# grouping_options  -> list[GroupingOptionOut]   what THIS tenant may group by
client.grouping_options()

# Building an axis, and reading one measure WITH ITS STATE. A measure's figure
# is never the whole answer: `status` says whether it is a total, a bound, or
# absent — and a figure read without it can publish a floor as a total.
from ubb import group_by_field, group_by_rollup, measure_on, vocabulary

answer = client.query_economics(
    measures=[vocabulary.ANALYTICS_MEASURE_GROSS_MARGIN],
    group_by=[group_by_field("model")],
    start_date="2026-01-01", end_date="2026-01-31")
for row in answer.rows:
    margin = measure_on(row, vocabulary.ANALYTICS_MEASURE_GROSS_MARGIN)
    if margin is None:
        continue                      # this row did not carry that measure
    if str(margin.status) != vocabulary.MEASURE_STATUS_KNOWN:
        continue                      # a bound, or no figure at all
    print(row.grouping_field_value, margin.amount_micros)

# See MIGRATION.md §17 for the five deleted calls mapped onto this one.
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
