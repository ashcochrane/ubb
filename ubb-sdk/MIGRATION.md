# Migrating to `ubb-sdk` v3.0

v3.0 is the **one coordinated breaking release** for the self-serve launch. The
generated typed core (#84) and the RFC 9457 problem+json error model (#78) —
plus the single-API restructure (#77) — land on your integration **together, in
one migration**. There is **no compatibility shim**: v3.0 speaks only the new
dialect, and you move once.

This guide covers **every breaking edge** you will hit. If a call in your v2.x
integration is not mentioned here, it is unchanged.

> **Not upgrading yet?** Pin `ubb-sdk<3` until you are ready to make the changes
> below. Once you upgrade, the old error dialects and list shapes are gone.

---

## 0. Verify what you installed

v3.0 is self-describing. From the installed package you can confirm both the SDK
release and the exact committed API contract it was generated against:

```python
import ubb

ubb.__version__         # "3.0.0"           — the SDK release
ubb.__spec_revision__   # sha256 of openapi/v1.json — the contract it was cut from
ubb.__spec_version__    # "v1"              — the contract document version
```

The `__spec_revision__` sha256 matches the `openapi/v1.json` committed in this
repo byte-for-byte; CI regenerates the core from that spec and fails on any
drift, so a v3.0 build can never disagree with its stamped contract. (Pinned by
`tests/test_release.py` and `tests/test_generated_core.py`.)

---

## 1. Errors: problem+json → a typed, per-code exception hierarchy

**The biggest change.** Every error response is now
`application/problem+json` (RFC 9457) carrying a **stable snake_case `code`**
from a checked-in registry (`openapi/error-codes.json`). The SDK maps each
response to a typed exception.

### What still works

- `except UBBAPIError:` still catches **every** API error — all typed
  exceptions subclass it. Existing broad handlers keep working.
- `UBBAPIError` instances now also carry `.code` (the stable registry code)
  alongside `.detail` (human prose — wording may change without notice) and
  `.status_code`.
- `except UBBConflictError:` still works — it is now an **alias** for
  `ConflictError` (see §7).
- 401 still raises `UBBAuthError`.

### What is new — catch a family or one exact code

Status-family parents group codes by HTTP status; per-code leaves sit under
their family. Catch broadly or narrowly with equal ease:

```python
from ubb import ConflictError, InsufficientBalanceError

try:
    billing.withdraw(customer_id=..., amount_micros=...)
except InsufficientBalanceError:   # one exact registry code (409 insufficient_balance)
    ...
except ConflictError:              # or the whole 409 family
    ...
```

Family parents: `BadRequestError` (400), `ForbiddenError` (403),
`NotFoundError` (404), `MethodNotAllowedError` (405), `ConflictError` (409),
`GoneError` (410), `UnprocessableEntityError` (422), `RateLimitError` (429),
`InternalServerError` (500), `ServiceUnavailableError` (503).

Per-code leaves include `InsufficientBalanceError`, `WouldOverdrawError`,
`CurrencyLockedError`, `LastActiveKeyError`, `LastActiveAdminError` (under
`ConflictError`); `BillingPeriodClosedError`, `InvalidConfigError`,
`UnsupportedCurrencyError`, `ValidationError`, the three `EffectiveAt*Error`
(under `UnprocessableEntityError`); `FeatureNotEnabledError` (under
`ForbiddenError`); `InvalidCursorError` (under `BadRequestError`);
`RateLimitExceededError` (under `RateLimitError`). The full registry is
`openapi/error-codes.json`.

**`PricingError` is gone, and it is not an alias.** It was raised when UBB could
not work out what a call had cost your supplier, and the refusal it named cannot
happen any more: the event is recorded, and the recording response says its cost
is unresolved and which declared quantities went uncosted. An `except
PricingError:` block therefore has nothing to catch — and because the class is
generated from the registry, the name does not exist to import either, so a
stale block fails at import with an `ImportError` rather than sitting there
never firing. **What to do instead: read `costing_status` on the 200.** It says
`known`, `unresolved` or `not_applicable`, and `uncosted_measurement_keys`
names the quantities that need a cost rate declared.

**`NoCostCardsError` is gone too, and so is the setting it guarded.** It was
raised when you tried to turn on `require_cost_card_coverage` — the strict mode
that made an uncostable event a 422 — without having declared any cost rates
yet. Both the setting and the refusal are deleted: strict mode was the wall
`PricingError` used to enforce, and with the wall gone there is nothing left to
arm. The tenant-config request and response schemas no longer carry the field,
and an `except NoCostCardsError:` block fails at import for the same reason as
above. `update_tenant_config()` has lost the keyword argument of the same name,
so a call still passing it raises `TypeError` before any request is sent —
deliberately, because the server now drops a body key it does not publish and
would otherwise answer 200 to a call that changed nothing. Drop the argument;
`get_tenant_config()` no longer returns the field either. **What to do instead:
nothing.** A tenant part-way through declaring their cost rates gets their
events recorded, with the gaps named on the 200.

The admission verdict `cost_coverage_required` goes with it. The start-gate
call no longer refuses a start because a spend ceiling was requested without
full cost coverage — that word can no longer appear in `reason`, and a limited
start is admitted whatever you have declared.

### Status-code moves you may be catching by number

The big-bang tightened HTTP semantics (400 = malformed only; 422 = semantic;
409 = conflict). If your v2.x code branches on `status_code`, re-check these:

| Condition | v2.x status | v3.0 status / exception |
|---|---|---|
| Withdraw with insufficient balance | `400` | `409` `InsufficientBalanceError` |
| Would overdraw the floor | `400` | `409` `WouldOverdrawError` |
| Duplicate create (plan / book / rule) | `422` | `409` `ConflictError` |
| Grant expiry validation | `400` | `422` |
| Webhook URL / event-type validation | `400` | `422` |
| Rate-limit (429) | 429 | `429` — now **always** carries a `Retry-After` header |

> **Note on "run not active" / hard-stop 429s.** There is no `UBBHardStopError`
> or `UBBRunNotActiveError` in v3. Under the one-rule contract a **spend stop
> rides a success (200) response**, not an error. `record_usage` **raises it by
> default** as `UBBStopRequested` — a `BaseException`, so a catch-all
> `except Exception:` cannot swallow it — carrying the acknowledgement; the
> event was recorded. `raise_on_stop=False` returns the ack with `result.stop`
> set instead, and `record_batch` never raises (the stop is reported per
> item). A 429 from a usage report is plain rate limiting and is safely
> retried (see §6).

---

## 2. Pagination: the cursor envelope, everywhere

Every entity list now returns the **cursor envelope** — no bare arrays, no
`{invoices: [...]}` wrappers, no `{grants: [...]}` caps. In the SDK this is
`PaginatedResponse[T]`:

```python
page = billing.list_grants(customer_id=cust.id, status="active")
page.data          # list[GrantOut]
page.next_cursor   # str | None — pass back as cursor= for the next page
page.has_more      # bool

# Walk all pages:
cursor = None
while True:
    page = client.list_transactions(customer_id=cust.id, cursor=cursor, limit=50)
    for row in page.data:
        ...
    if not page.has_more:
        break
    cursor = page.next_cursor
```

- Lists take a `cursor` (opaque keyset token) and `limit` (clamped to 1–100),
  **not** `offset`/`page`. A malformed cursor raises `InvalidCursorError` (400).
- `/me/grants` ordering changed from *soonest-expiring-first (capped 100)* to
  the standard creation keyset so the cursor is real — **sort by expiry
  client-side** if you relied on that ordering.
- **Computed reports** (usage/revenue analytics, timeseries, margin `_window`
  reports, the spend-control reports, referrals earnings) are **not**
  paginated, but now refuse explicit date windows wider than **366 days**
  (hourly timeseries: **92**) with a `validation_error` (422).

---

## 3. Batch & async ingest: one verdict field set

`record_batch` results were renamed to one shared verdict vocabulary. **These
are attribute renames — old names will `AttributeError`:**

| v2.x | v3.0 |
|---|---|
| `BatchResult.succeeded` | `BatchResult.accepted` |
| `BatchResult.failed` | `BatchResult.rejected` |
| `BatchItemResult.ok` | `BatchItemResult.accepted` |
| `BatchItemResult.error` | `BatchItemResult.code` (registry code) + `.detail` |

```python
batch = client.record_batch([...])
print(batch.accepted, batch.rejected)
for item in batch.results:
    print(item.accepted, item.event_id if item.accepted else item.code)
```

The 200-always contract is unchanged (the batch call itself never errors on a
rejected item). Async-ingest verdicts moved the same way (`reason` → `code`,
`detail` added); the per-item `rejected` bool was removed.

---

## 4. Typed return values: generated DTOs replace hand dataclasses

Endpoints the contract types now return **generated models** (attrs classes
under `ubb._core.models`, re-exported from `ubb`) instead of the nine
hand-written dataclasses, which are retired. Field names and meanings are
unchanged **except** the edges below. Absent optionals still read as `None`
(the generator's `UNSET` sentinel is normalized on the way out).

Breaking field/type edges:

- **`record_usage` → `RecordUsageResponse`.** The field
  `balance_after_micros` is **gone** — use **`new_balance_micros`**. (It was
  never in the committed contract; the retired v2 dataclass invented it.)
- **`UsageEventOut.id` is now `uuid.UUID`** (was `str`). Call `str(event.id)`
  if you need the string form.
- Unknown fields on any generated model land in `.additional_properties` and
  response enums parse as plain `str` — a v3.0 client **never crashes** on a
  field or enum value the API adds after you pinned (ADR-003 open-world).

### The last untyped 200s are typed (#98)

The billing money-movement calls and the margin surface are typed in the
committed contract now, so their returns are **generated models** too — the
small shell results (`TopUpResult`, `AutoTopUpResult`, `WithdrawResult`,
`RefundResult`, `WalletTransaction`, `CustomerMargin`, `DimensionMargin`,
`MarginTrendPoint`) are retired:

| Call | Now returns |
|---|---|
| `create_top_up` | `TopUpCheckoutResponse` |
| `configure_auto_top_up` | `StatusResponse` |
| `withdraw` | `WithdrawResponse` |
| `refund_usage` | `RefundResponse` |
| `get_transactions` | `PaginatedResponse[WalletTransactionOut]` |
| `get_customer_margin` | `CustomerMarginOut` (full body — adds `usage_revenue_micros`, `total_revenue_micros`, `event_count`, `external_id`, `period`) |
| `get_margin_by_grouping_field` (was `get_margin_by_dimension` — see §8) | `list[GroupingFieldMarginRow]` |
| `get_margin_trend` | `list[MarginTrendPointOut]` |

Attribute names are unchanged, so `result.checkout_url`-style call sites keep
working. One type edge: **`WalletTransactionOut.id` is `uuid.UUID`** (was
`str`) — call `str(txn.id)` if you need the string form. Methods documented as
returning raw `dict`s (`BillingClient.withdraw/refund`, `usage_analytics`,
`get_unprofitable_customers`, …) still do.

---

## 5. Idempotency & the single API path

- **Top-ups now require an `idempotency_key`** (tenant and widget): `create_top_up(...)`
  will not build a request without one. Replays are safe — the original attempt
  is re-used (checkout re-renders, no duplicate charge, no duplicate event).
- Webhook-config creates dedupe on `(tenant, url)` — a duplicate raises `409`
  `ConflictError`.
- The platform is now **one versioned API** mounted at `/api/v1/…` (#77). Your
  `base_url` is unchanged (still the host) — the SDK builds the `/api/v1/` paths.
  The **per-mount** `…/docs` and `…/openapi.json` endpoints and the per-mount
  API-roots are **gone**; there is one docs UI at `/api/v1/docs` and one schema
  at `/api/v1/openapi.json`. This only affects you if you fetched those directly.

---

## 6. Retry behavior (unchanged, restated for the new error model)

All clients auto-retry transient failures — HTTP `429`, `502`, `503`, `504`,
plus timeouts and connection errors — with jittered exponential backoff (0.5s
base, doubling, ±25% jitter, capped 10s); a server `Retry-After` is honored,
capped at 30s. **Every other 4xx** (400/403/404/405/409/410/422) is **never**
retried. Spend stops ride a 200 and are not errors. Pass `max_retries=0` to any
client constructor to disable retries.

---

## 7. Names kept on purpose, and names deleted outright

⚠ **This section was titled "Retained aliases" and now carries both halves.**
The number is unchanged, because a section number is a cross-reference and
`CHANGELOG.md` cites this one — but a deletion is not a retained alias, and
filing one under that title made the heading say the opposite of the
subsection beneath it (#373).

v3.0 has **no shim** that dual-runs the old and new contracts. Three names are
retained on purpose; none lets old-dialect calls survive:

- **`UBBConflictError`** — an alias for the new `ConflictError` (same class).
  It is a convenience name *within* the new hierarchy, not a bridge to the old
  error model.
- **`verify_webhook_legacy`** — verifies the body-only `X-UBB-Signature`
  header. This is the **webhook-secret rotation** window (a product feature),
  not a v3-migration bridge. Prefer `verify_webhook` (the timestamped v2
  signature). Unrelated to this migration.
- **`credit()`** — adds plain non-expiring base money to a wallet. A distinct
  money primitive from grant lots, unchanged by v3.

### Deleted — three methods that never worked

`MeteringClient.update_rate_card`, `.get_rate_card_history` and
`.bulk_create_rate_cards` are **gone**, along with the `RateCard` result type
the first two parsed into. They addressed flat paths that exist in no
specification and in no router, so no server has ever answered one — which is
why this is not a migration step. There is no v2 behaviour to move off and no
window in which both spellings worked: a call to any of the three failed at
runtime on the day it was written, and every test that appeared to cover them
patched the HTTP client, so the mock answered where the server never would.

What to use instead is not a renamed method, because the model changed. A rule
lives in a **book** — a cost book records what one supplier charges you, a
Pricing Book what you charge a customer — and every change to a book is a
**publish**: declare a draft at `POST
/api/v1/metering/pricing/books/{book_id}/publishes`, read its diff, publish it,
optionally dated forward. That replaces all three at once: versioning in place
becomes a publish, the lineage history becomes the book's publish records, and
the atomic batch becomes the publish itself, which is already all-or-nothing.

`declare_pricing_book`, `declare_cost_book`, the two `withdraw_*` and the two
`list_*` are the hand-written wrappers for the books; the publish surface is
reachable through the generated core.

---

## 8. Pooled-seat billing + the retired per-task floor (folded into v3.0, pre-live)

Further breaking edges landed on the same pre-live `openapi/v1.json` contract
v3.0 is cut from — since v3.0 hasn't shipped, these are **part of the one coordinated
cut**, not a second release. If you're integrating against v3.0 for the first time,
just read them as more of the same guide; if you already adapted to an earlier
pre-live snapshot, these are the delta.

> The `api-v1-launch` tag (2026-07-22) exists, but no tenant is integrated against v1
> yet, so these remain hand-coordinated pre-launch breaks rather than §4 deprecations.
> See `docs/api-compatibility.md` — from the first live tenant, removals get the full
> deprecate-then-remove cycle instead.

### The per-task floor snapshot is gone

`PreCheckResponse.floor_snapshot_micros` and `TenantConfigIn`/`TenantConfigOut`
`.default_task_floor_snapshot_micros` are **removed, no replacement field.** The
mechanism they backed — a snapshot of a tenant-wide constant, compared against the
balance frozen at task start — was deleted server-side in favor of the existing
customer-wide stop signal: it read a number that was never the customer's real
floor, and it couldn't see a mid-task top-up, so it could kill a task for a customer
who had just paid. There is no per-task floor to migrate to, because there is no
per-task floor anymore: the customer-wide stop is what a usage report's `stop` /
`stop_reason` announce. (The advisory call that carried this field is itself
replaced by the affordability question — section 10.)

### `enforce_mode` values renamed (field name unchanged)

Clean-cut rename on `BudgetConfigIn`/`BudgetConfigOut.enforce_mode` — same field,
new values, no alias:

| v2.x / earlier v3.0 pre-tag | v3.0 |
|---|---|
| `"advisory"` | `"alert_only"` |
| `"enforcing"` | `"blocking"` |

If you pass `enforce_mode` explicitly to `BillingClient.set_budget` /
`UBBClient.set_budget`, update the literal. If you rely on the SDK's default
(omitting the kwarg), no code change is needed — the default itself moved from
`"advisory"` to `"alert_only"` inside the SDK.

### Pooled-seat balance disclosure, and a 422 on writing floors to a seat

`BalanceResponse`, `CustomerBillingProfileOut`, and `PaginatedWalletTransactions` all
gained three new **required** fields:

```python
billing_owner_id: UUID
billing_owner_external_id: str
is_pooled_seat: bool
```

For a standalone customer, `billing_owner_id == customer_id` and `is_pooled_seat`
is `False`. For a customer that is a pooled seat under a business
(`billing_topology="pooled"`), these disclose the resolved billing owner — the
business whose wallet the balance/transactions/profile actually belong to. If you
maintain your own mock fixtures or hand-rolled response bodies for these three
calls, add the fields or construction will raise (`attrs`-required, no defaults).

`PUT .../billing-profile` now refuses with **`422` `InvalidConfigError`** when
`customer_id` names a pooled seat — overdraft/expiry floors are configured on the
billing owner, never the seat (writing to the seat's own row would be silently
ignored by the gate; writing to the owner's row instead would silently change
every sibling seat's policy). The error body's `extensions.billing_owner_external_id`
names the row to retry the call against. `GET .../billing-profile` is unaffected —
it already returns the effective (owner-resolved) profile.

There is no dedicated SDK wrapper for `GET`/`PUT .../billing-profile` in either
version — drop to the generated core (`ubb._core.models.CustomerBillingProfileOut`/
`In`) if you call it today.

### The margin breakdown takes a named axis, and the method is renamed with it

The margin breakdown route moved to **`GET /api/v1/margin/by-grouping-field`**, and
the two wrappers follow it: `MeteringClient.get_margin_by_dimension` and
`UBBClient.get_margin_by_dimension` are now
**`get_margin_by_grouping_field`**. Grep your integration for the old method
name — it is gone, not aliased, so the failure is an `AttributeError` at the
call site rather than a wrong answer.

The signature changes too, and this one is worth reading even if you only ever
passed `provider=True`:

| v2.x / earlier v3.0 pre-tag | v3.0 |
|---|---|
| `get_margin_by_dimension(provider=True)` | `get_margin_by_grouping_field()` — `provider` is the default |
| `get_margin_by_dimension(product=True)` | **no equivalent, because it never grouped by product** — name the axis you actually wanted, e.g. `get_margin_by_grouping_field(group_by="event_type")` |

**`product=True` never worked.** The boolean pseudo-flags were removed from the
route long before v3.0, and Django Ninja drops an unknown query parameter rather
than refusing it — so the call answered `200` with rows grouped by the axis
parameter's default, `provider`, whatever you passed. `provider=True` looked
correct for exactly the same reason it was doing nothing.

`group_by` now names the axis directly: the built-in `provider`, `event_type`,
`task_type`, `subtask_type`, or **any key you have declared in your Grouping
Field registry** — which is the reach the flags never had. An undeclared key
answers `422` `validation_error` naming the key, rather than silently grouping
by something else. The open-bag grouping parameter beside it is unchanged —
same keyword, same meaning — and still takes precedence over the axis when
both arrive.

Each row's value property is **`grouping_field_value`** on
`GroupingFieldMarginRow` — the value that was reported, a provider name or a
region. The axis is not repeated per row, because your request already named it.

---

## 9. The customer spend pool takes its name (slice 6, #456 — pre-live)

The per-customer spending bound is a **Customer Spend Pool** on every surface, and the
retired family word that used to name it leaves the routes, the schemas and the SDK
together. No alias, no short form: an abbreviation would be a second public name for
one concept.

The old paths are spelled with the retired word below as `{retired}` — the
repository refuses the word itself on every living surface, and this guide is one.

| earlier v3.0 pre-tag | v3.0 |
|---|---|
| `PUT`/`GET /api/v1/billing/{retired}` | `PUT`/`GET /api/v1/billing/customer-spend-pool` |
| `PUT`/`GET /api/v1/billing/customers/{id}/{retired}` | `…/customers/{id}/customer-spend-pool` |
| `GET …/customers/{id}/{retired}/status` | `GET …/customers/{id}/customer-spend-pool/status` |
| `BudgetConfigIn` / `BudgetConfigOut` / `BudgetStatusOut` | `CustomerSpendPoolIn` / `CustomerSpendPoolOut` / `CustomerSpendPoolStatusOut` |
| `BillingClient.set_budget` / `get_budget` / `get_budget_status` (and the `UBBClient` twins) | `set_customer_spend_pool` / `get_customer_spend_pool` / `get_customer_spend_pool_status` |

`enforce_mode` keeps its two values, `alert_only` and `blocking`, and the SDK's
default is now the generated constant `ubb.vocabulary.SPEND_POOL_ENFORCE_MODE_ALERT_ONLY`
rather than a literal of its own. The published document enumerates the pair on all
three schemas and on the threshold webhook's payload.

**The status read's shape is final and different.** `spend_micros` and `pct` are
gone. The read now carries the pool's basis as a pair — `known_period_charges_micros`
(the resolved period charges, a lower bound whenever the count beside it is not zero)
and `unresolved_posting_count` — beside `cap_micros`, `used_percentage` (a whole percent
over the known figure, `null` with no pool), `remaining_micros` (headroom, never below
zero, `null` with no pool), `highest_threshold_reached` (the largest of the pool's
`alert_levels` reached, `null` when none is) and `blocking_occurred` (the start gate's
own compare — `true` only under a `blocking` pool at or over its stop line). Section 8's
value-rename table above still describes the same field, under the schemas' old names.

---

## 10. The advisory call becomes the affordability question (slice 6, #463 — pre-live)

"Can this customer afford more work?" is a **read**: it registers nothing, moves no
admission window, and is never the last word (a start re-runs every check under its
own locks). It now has the shape of one. The retired call's name described a moment
in a sequence rather than the question it answers, and the repository refuses that
name on every living surface, so the old row below spells it `{retired}`.

| earlier v3.0 pre-tag | v3.0 |
|---|---|
| `POST /api/v1/billing/{retired}` with `{customer_id, parent_task_id}` in the body | `GET /api/v1/billing/customers/{customer_id}/affordability?parent_task_id=…` |
| the request schema, and the response schema named for the retired call | no request schema; `AffordabilityResponse` |
| `BillingClient.{retired}(customer_id, parent_task_id=None) -> dict` | `BillingClient.affordability(customer_id, parent_task_id=None) -> AffordabilityResponse` |
| `UBBClient.{retired}(...) -> ` a hand-written result with `allowed` **and** `can_proceed` | `UBBClient.affordability(...) -> AffordabilityResponse` (a passthrough) |

**What the answer carries.** `allowed`; `reason` — a value of the registry's open
`affordability_reason` vocabulary, so branch on `ubb.vocabulary.AFFORDABILITY_REASON_*`
and render a value you have not seen rather than fail on it; `balance_micros`; and
three figures that are new: `available_micros` (the balance less the agreed prices
reserved by work already started and not yet ended — the figure every floor is
tested against), `min_balance_micros` and `soft_min_balance_micros` (the hard and
soft floors as resolved for this customer, in the billing profile's orientation; the
soft floor is `null` where no wind-down line applies to the work asked about, and both
are `null` for a postpaid tenant). `can_proceed` is gone — it was a second name for
`allowed`.

**The facade no longer answers for a client without billing.** `UBBClient.{retired}`
returned "trivially allowed" when the billing product was off — a verdict the client
invented about a wallet the tenant does not have. `UBBClient.affordability` raises
`UBBError` like every other money-shaped call on the facade; the route refuses such a
tenant with a 403 for the same reason. A start needs no advisory question to be
admitted.

**Requires the billing product at the Read floor.** The retired call was floored at
Write; a read-only key can ask the question now.

---

## 11. Five webhook names move under their families, and the catalogue is closed (slice 6, #464 — pre-live)

Every event UBB publishes is named `<owner>.<state entered>` (ADR-0006 §5): the owner is
the resource whose lifecycle moved or the declared control family whose own state
changed — never the mechanism that fired. Five names predating that rule named the
mechanism, and the repository refuses those spellings on every living surface, so the
rows below spell them `{retired}` and say what each was.

| earlier v3.0 pre-tag | v3.0 |
|---|---|
| `{retired}` — the customer-wide stop, named for the mechanism that fired | `customer.stopped` |
| `{retired}` — its clearing half | `customer.stop_cleared` |
| `{retired}` — the soft floor crossed, named for the line | `wallet_policy.soft_floor_crossed` |
| `{retired}` — its clearing half | `wallet_policy.soft_floor_cleared` |
| `{retired}` — the pool's threshold, under the retired family word | `customer_spend_pool.threshold_reached` |

**Your subscriptions moved with them.** A stored subscription holding a retired name comes
out of the migration holding its successor, in the same position; a queued delivery is
renamed on its way to you; a delivered body keeps every field it had. Subscribing to a
retired name is refused at configuration with a `validation_error`, as any unpublished
name is.

**The catalogue is closed, and the contract says so.** `event_types` on the three
subscription schemas and `event_type` on a delivery now carry the registry's 37-member
`enum` (on a subscription, beside the `"*"` selector); the generated core types them
accordingly. What that buys you:

- `ubb.vocabulary.WEBHOOK_EVENT_TYPE_<OWNER>_<STATE>` — one constant per name, and
  `ubb.vocabulary.WEBHOOK_EVENT_TYPE_VALUES` for the whole set, reached by module
  (`from ubb import vocabulary`). Branch on `vocabulary.WEBHOOK_EVENT_TYPE_CUSTOMER_STOPPED`,
  never on a string you typed.
- `ubb.webhooks.EVENT_SELECTORS` — everything a subscription may name: the 37 plus the
  wildcard `ubb.webhooks.WILDCARD`.
- `ubb.webhooks.unpublished_event_types(event_types)` — the entries of a proposed
  subscription UBB does not publish, empty when the API would accept it. Ask it before the
  round trip; the API's answer is the same set as a 422.

**Classify by subscribing, not by parsing.** Which control fired and why travel as
`control_family`, `control_id` and `reason_code` on the body (§9, #458); a name no longer
carries a mechanism to split on, and `verify_webhook`'s parsed payload carries the name
under `event_type` exactly as before.

---

## 12. The two spend-control reports, and the reached count leaves the task analytics row (slice 6, #465 — pre-live)

**Two reads at a prefix of their own, gated on no product.** `GET /api/v1/spend-controls/stops-and-breaches`
answers what was spent past a stop and why — one typed row per control that fired and had an
enforcement consequence, discriminated by `control_family` (a Ceiling row per unit stopped on its
own ceiling, a Customer spend pool row per pool episode naming the Charge that crossed it and that
Charge's posting, a Wallet policy row per floor episode; a soft-floor row is a marker with no
events) — and `GET /api/v1/spend-controls/utilisation-and-headroom` answers how much of each ceiling
was used and how often it could not be evaluated, per completed unit and in aggregate. Both take
`customer_id`, `task_type`, `since`/`until` and (the first) `control_family` as filters; a window
left open is bounded to the 366 days ending now and echoed back.

- `client.spend_controls.stops_and_breaches(...)` and `client.spend_controls.utilisation_and_headroom(...)`
  — a handle on the facade, present whatever products the client holds, because the routes are.
  Every argument is an optional filter; pass `ubb.vocabulary.CONTROL_FAMILY_*` for the family.
- `ubb.StopsAndBreachesResponse` and `ubb.UtilisationAndHeadroomResponse` are the generated models;
  a row of the first is one of `CeilingEpisodeRow`, `CustomerSpendPoolEpisodeRow` or
  `WalletPolicyEpisodeRow` under `ubb._core.models`, told apart by `control_family`.
- Every average on the aggregate is `None` where no unit contributes — read it as unknown, never
  as zero; `crossed_*` on a Ceiling row is `None` where the kill's announcement no longer survives.

**`limit_hit_count` left `TaskAnalyticsRow`** (`GET /api/v1/metering/analytics/tasks`). The count
of work whose known total reached the ceiling is a fact about the ceiling as a spend control, and
it is Utilisation and headroom's `ceiling_reached_count` now. The generated
`ubb._core.models.task_analytics_row.TaskAnalyticsRow` no longer carries the attribute; a reader of
it moves to the report. The route post-dates the launch tag, so the removal is recorded here and
in the commit rather than in the break block.

---

## 13. The per-customer past-limit report retires (slice 6, #466 — pre-live)

**`GET /api/v1/customers/{customer_id}/past-limit-report` is gone, with `PastLimitReportResponse`.**
It answered one customer's stop episodes as an untyped `list[dict]`, under the field word the
registry retired (`control_family`'s `limit`) and the family words that preceded the four
families. Everything it answered is one filter away on the typed successor:

- `client.get_past_limit_report(customer_id, since=..., until=...)` and
  `MeteringClient.get_past_limit_report` are **deleted**. Call
  `client.spend_controls.stops_and_breaches(customer_id=customer_id, since=..., until=...)` — the
  same window, the same customer (its own work and its billing owner's customer-wide episodes),
  as typed rows told apart by `control_family`.
- `episodes[].family` (`floor_stop` / `soft_floor` / `task`) is `rows[].control_family`
  (`wallet_policy` with `soft_floor` false / true, `ceiling`); `episodes[].limit` is
  `rows[].reason_code`; `totals_per_limit` keyed by stop word is `totals[]` per family.
- `ubb._core.models.past_limit_report_response` and its two item models are gone from the
  generated core; the operation constant `API_V1_ENDPOINTS_PAST_LIMIT_REPORT` with them.

The route pre-dates the launch tag, so the removal is recorded in the break block
(`openapi/oasdiff-err-ignore.txt`) as a reviewed break.

---

## 14. The recurring revenue amount becomes per-period supplied revenue (slice 7, #496 — pre-live)

**`GET`/`PUT /api/v1/margin/customers/{customer_id}/revenue` are gone, with `RevenueProfileIn` and
`RevenueProfileOut`.** They read and wrote ONE recurring amount per customer: no period, no source
reference, and an accrual behind them that added the amount into the same response field as a
Stripe subscription — so a caller reading `subscription_revenue_micros` could not tell which kind
of money it was looking at.

- `MeteringClient.set_customer_revenue(customer_id, recurring_amount_micros, interval=..., ...)`
  and `MeteringClient.get_customer_revenue(customer_id)` are **deleted**. State the figure per
  period instead, through the generated client:
  `ubb._core.api.default.apps_subscriptions_api_margin_endpoints_record_supplied_revenue` (`POST`)
  and `..._get_supplied_revenue` (`GET`), against
  `/api/v1/margin/customers/{customer_id}/supplied-revenue`. Neither has a hand-written call in
  `ubb-sdk/ubb/` yet; the disposition manifest records both as `generated_only`.
- **One recurring amount becomes one record per period.** `recurring_amount_micros` is
  `amount_micros` for the period it covers; `effective_from`/`effective_to` become each record's
  own `period_start`/`period_end`, so **a customer that started mid-month is one record from the
  fourteenth to the month end** rather than an amount a proration had to guess at. Each record
  also carries `recognition_method` — `straight_line` is what the old accrual was doing unlabelled
  — and `source_reference`, your own handle for where the number came from, which is required.
- ⚠ **`interval` is gone and nothing is lost by it.** Nothing ever divided by it: a profile of X
  with `interval="year"` accrued X **per month**, the same as `"month"`. The periods say what the
  interval was trying to say, and they say it where it is checkable.
- **Every margin response now names the source of its revenue.** `supplied_revenue_micros` joins
  `subscription_revenue_micros` on `SeatMarginOut`, `CustomerMarginOut`, `CustomerMarginListRow`,
  `MarginSummaryOut`, `MarginTrendPointOut` and `BusinessMarginTotals`. Both are inside
  `total_revenue_micros`; neither is inside the other. **If you were reading
  `subscription_revenue_micros` to get a customer's whole revenue, read `total_revenue_micros`.**
- Existing amounts are carried by the platform's own data migration — one record per calendar
  month the amount applied to, with the source reference
  `ubb:carried-from-the-retired-recurring-amount`. An open-ended amount is carried up to the month
  the migration ran in and no further: a per-period record states a period, and the next one is
  yours to state.

The routes pre-date the launch tag, so the removals are recorded in the break block
(`openapi/oasdiff-err-ignore.txt`) as reviewed breaks.

---

## 15. The customer-level revenue switch is deleted, with no replacement (slice 7, #497 — pre-live)

**`GET`/`PUT /api/v1/margin/customers/{customer_id}/revenue-mode` are gone**, with the request and
response bodies they carried and the `invalid_revenue_mode` problem code (so
`InvalidRevenueModeError` is no longer raised and no longer exported).

- `MeteringClient.get_revenue_mode(customer_id)` and
  `MeteringClient.set_revenue_mode(customer_id, ...)` are **deleted, and nothing replaces them.**
  This is the one removal in this guide with no forwarding call, so it is worth saying why rather
  than just where.
- **The setting answered a question it had no business answering.** It decided, per customer,
  whether that customer's billed usage counted as revenue at all — defaulting to an answer derived
  from your workspace's billing mode. That turned *"UBB does not raise this customer's invoices"*
  into *"this customer produced no revenue"*, which is not the same statement. Whether a given
  posting carried customer revenue is already recorded on the posting: `pricing_status` is `known`,
  `waived`, `unknown` or `not_applicable`, and `not_applicable_reason` says which cause applies.
- **What changes in a response you already read.** For a customer the switch had resolved away from
  billed usage, `usage_revenue_micros` was `0` and `gross_margin_micros` was the negative of the
  supplier cost. Both now carry the figures that customer's own postings state.
  `usage_revenue_micros` and `usage_billed_micros` are consequently the same number on every margin
  response; both are kept for now, and the one economic query that replaces these routes is where
  the shape is settled.
- **The switch's own field is removed from `CustomerMarginOut` and `SeatMarginOut`.** It is named
  descriptively here rather than spelled, because the spelling is a retired term whose ledger entry
  this same change pays — after which the sweep refuses it on every living SDK file, this guide
  included. If you were branching on that field, the branch has no subject: there is one behaviour
  for every tenant.
- **If you bill your customers outside UBB and want a revenue figure UBB can report on**, state it
  with the per-period supplied revenue record in §14 — that is the supported way to supply revenue
  UBB cannot see, and it carries its own period, currency, recognition method and source reference.

The routes pre-date the launch tag, so the removals are recorded in the break block
(`openapi/oasdiff-err-ignore.txt`) as reviewed breaks.

---

## 16. Nine reports collapse into one economic query (slice 7, #501 — pre-live)

**Nine published reads are gone.** One query that is already on the contract answers all of them:
`GET /api/v1/metering/analytics/economics`, with `GET /api/v1/metering/analytics/grouping-options`
saying what may be asked of it.

| Gone | What it answered |
| --- | --- |
| `GET /api/v1/metering/analytics/usage` | supplier COGS, with per-customer and per-field breakdowns |
| `GET /api/v1/metering/analytics/usage/timeseries` | the same COGS bucketed by hour or day |
| `GET /api/v1/billing/analytics/revenue` | revenue, with a daily series |
| `GET /api/v1/margin/summary` | tenant-wide revenue, cost and margin |
| `GET /api/v1/margin/customers` | one row per customer |
| `GET /api/v1/margin/customers/{customer_id}` | one customer's totals |
| `GET /api/v1/margin/customers/{customer_id}/trend` | one customer's margin by month |
| `GET /api/v1/margin/by-grouping-field` | margin grouped by one declared field |
| `GET /api/v1/me/usage-summary` | an end customer's own usage, on the widget mount |

**Five hand-written calls go with them**, and nothing in this release replaces them:
`MeteringClient.usage_analytics`, `.usage_timeseries`, `.get_customer_margin`,
`.get_margin_by_grouping_field` and `.get_margin_trend`, together with the `UBBClient` delegates
for the last three and the DTOs `CustomerMarginOut`, `GroupingFieldMarginRow` and
`MarginTrendPointOut`. The generated core carries the replacement operation
(`api_v1_metering_endpoints_query_economics`); **the hand-written handle for it landed in the
very next SDK ticket** — see §17, which maps each of the five deleted calls onto the call that
answers it. This section maps questions onto a REQUEST, and is still the one to read if you
drive the route over raw HTTP.

**How the old questions are asked now.** The request is `measures` (one or more of `supplier_cogs`,
`customer_revenue`, `gross_margin`, `recorded_events`), `group_by` (zero or more axes, each
`field:<declared key>` or `rollup:<name>`), an optional `bucket` of `hour`, `day` or `month`, and
filters that narrow without grouping:

- **Tenant-wide totals** (`/margin/summary`, `/billing/analytics/revenue`) — no `group_by`, no
  `bucket`. One row.
- **One row per customer** (`/margin/customers`, the usage report's customer breakdown) —
  `group_by=field:customer_id`.
- **One customer** (`/margin/customers/{customer_id}`) — `customer_id=<id>` as a FILTER.
- **A trend** (`/margin/customers/{customer_id}/trend`, `/analytics/usage/timeseries`) — `bucket`,
  with `customer_id` if you want one customer's.
- **Grouped by a declared field** (`/margin/by-grouping-field`, the usage report's breakdowns) —
  `group_by=field:<key>`, whose legal values the discovery read lists for your tenant.

**Three things are worth knowing before you port a chart.**

- **The margin is subtracted at the bucket, never at a row.** Ask for `gross_margin` and you get it
  where it can be computed; where the grain makes it unattributable it is `null` rather than a
  number, because there is no such thing as a partial margin.
- **Every measure carries its own `status`** — `known`, `incomplete`,
  `unavailable_at_requested_grain`, `unavailable_outside_retention_horizon` or `not_applicable` —
  and its own completeness counts. A reader that takes the amount and drops the status publishes a
  floor as a total. The old reports had one completeness answer for a whole response; this has one
  per measure per row.
- **A row's grouped value is a LIST**, positional against the `group_by` you sent, which the
  response echoes back. Several axes at once is a thing the old reports could not do at all.

**What did NOT collapse, deliberately.**

- `GET /api/v1/metering/customers/{customer_id}/usage` still returns **paginated event rows**, at
  the same path, with the same response and the same pagination. It lists events; it is not a
  measure, and a query that returns measures cannot return it.

  ⚠ **Its two-part label filter is RENAMED, and this is the one breaking edge on a route that
  otherwise did not move.** The pair is now `metadata_key` / `metadata_value`, naming the bag it
  reads; it used to carry the analytics grouping word, which read as an *axis* over a bag that is
  deliberately never groupable. `MeteringClient.get_usage` spells the new pair, so a call passing
  the old keyword arguments raises `TypeError` — rename them and nothing else changes.

  ⚠ **If you call the route over raw HTTP, read this twice.** An unknown query parameter is
  **discarded, not rejected**, so a request still sending the old pair does not fail — it comes back
  **unfiltered**, with every posting for that customer rather than the ones you asked for. The page
  looks healthy and is simply wider than you wanted. Grep your callers for the old names rather than
  waiting for an error.
- The **unprofitable-customer count** still stands, on `GET /api/v1/margin/unprofitable` — an
  alerting surface reading the alerting record, which is a different question from "what did this
  cost and earn".
- The **business/seat margin tree** (`GET /api/v1/margin/business/{external_id}`), the two
  spend-control reports, the task cost-distribution report (`GET
  /api/v1/metering/analytics/tasks`), the supplied-revenue records and the referrals analytics
  routes are untouched.

**Two fields are gone and nothing reintroduces them**: the fused markup-margin figure, and the
breakdown block keyed by free-text labels. The first fused two questions into one number; the
second grouped on an unbounded keyspace, which ADR-0005 rules is never a grouping axis.

**One route is ADDED, on a ticket that removes nine**:
`GET /api/v1/platform/customers/{customer_id}` returns a customer's identity — the id UBB assigned
them, the id you gave them, the account type, the business a seat belongs to, and the status. One
customer's margin was the only read that mapped the two ids to each other, and the economic query
groups by identity and publishes no external id; the subscription lifecycle is addressed by the
external id while the metering and billing reads are addressed by the UUID, so a caller holding one
and needing the other needed somewhere to cross. No hand-written wrapper in this release, for the
same reason as above.

The routes pre-date the launch tag, so the removals are recorded in the break block
(`openapi/oasdiff-err-ignore.txt`) as reviewed breaks.

---

## 17. The one query gets its handle, and the grouping bag takes the registry's word (slice 7, #505 — pre-live)

### The five deleted calls, mapped onto the one that replaces them

`MeteringClient.query_economics()` is the handle §16 said was coming, with
`MeteringClient.grouping_options()` beside it saying what this tenant may ask of it. Both are
on `UBBClient` too.

| Gone (#501) | The call that answers it now |
| --- | --- |
| `.usage_analytics(...)` | `query_economics(measures=[ANALYTICS_MEASURE_SUPPLIER_COGS], group_by=[...])` |
| `.usage_timeseries(granularity="day")` | the same question with `bucket="day"` |
| `.get_customer_margin(customer_id)` | `query_economics(measures=[...], customer_id=...)` |
| `.get_margin_trend(customer_id)` | the same question with `bucket="month"` |
| `.get_margin_by_grouping_field(group_by="provider")` | `query_economics(..., group_by=[group_by_field("provider")])` |

⚠ **The window defaults to the CURRENT MONTH TO DATE, and every call it replaces defaulted to
all time.** A port that drops the dates does not fail — it answers `200` with no rows. Name
`start_date` and `end_date` unless the question really is about now; the answer echoes the
period it applied either way.

⚠ **`measures` is required and has no default**, at both layers, because it has none on the
wire: a default measure set is how a caller ends up aggregating three different things to draw
one line.

⚠ **Every measure carries its own state, and a figure read without it can be wrong in a way
that looks right.** Read one with `ubb.measure_on(row, name)`, which hands back the measure
rather than the number — `status` is `known`, `incomplete` (the figure is a BOUND), one of the
two `unavailable_*` states, or `not_applicable`. A margin that could not be attributed at the
grain you asked for has NO figure at all; a zero in `amount_micros` is a MEASURED zero.

Axis words are built with `ubb.group_by_field(key)` and `ubb.group_by_rollup(name)` rather
than typed, so a misspelled kind is a name error rather than a `422`. The four concepts'
constants are in `ubb.vocabulary` (`ANALYTICS_MEASURE_*`, `ANALYTICS_GROUPING_KIND_*`,
`ANALYTICS_ROLLUP_*`, `MEASURE_STATUS_*`).

### The declared grouping bag is renamed, at every layer

**The declared grouping bag's keyword is now `grouping_fields=`** on `record_usage` and
`start_task`, on both the metering client and `UBBClient`, and the request property behind it
moved with it. It is the keyword that carried the analytics grouping word — the one this
programme is retiring everywhere — and it is the only bag on either call that is not
`metadata`. You do not have to guess which: passing the old name raises `TypeError` and
**Python names it for you**. Rename it and nothing else changes.

⚠ **`record_batch` IS THE EXCEPTION, AND IT USED TO BE THE DANGEROUS ONE.** It takes
dicts rather than keyword arguments, so Python could not name anything and UBB drops a
body key it does not publish rather than refusing it — a batch item carrying the old
key recorded an event **attributed to nothing**, answered `200`, and said so nowhere,
a hundred at a time. **#505 closes that**: `record_batch` now raises
`UBBValidationError` before any HTTP for any key the recording request does not
publish, naming the item's index and listing the keys that are valid. The set is read
off the generated request model, so it cannot drift from the contract.

That is a behaviour change on its own account: a batch item carrying a key UBB used to
ignore — `product_id`, say — is now refused by the client instead of being silently
dropped by the server. Drop the key.

The word is the one **both responses have used since #277**: `RecordUsageResponse` and
`UsageEventDetailOut` have keyed this same object under `grouping_fields` all along, so until
now the contract published two spellings of one concept and a round trip read as a
translation. The registry's own declaration body and the kind-of-work declaration's
`required_dimensions` moved for the same reason — the latter is now
`required_grouping_fields` on `PUT /api/v1/task-types` and on what it answers with.

⚠ **If you call these routes over raw HTTP, read this twice.** A body key no schema declares
is **dropped, not rejected**, so a request still sending the old name gets a normal `200` with
an EMPTY grouping bag: the event is recorded and attributed to nothing, and no error says so.
Grep your callers for the old names rather than waiting for a failure.

### A unit of work's grouping values are keyed by YOUR word now

`TaskOut.grouping_fields` (`GET /api/v1/tasks`, `/tasks/{id}`, `/tasks/{id}/subtasks`) is
keyed by the key you declared, not by UBB's internal slot column — the shape the posting
reads have had since #277, and the one the field's own comment said the task read was being
moved to match. A value in a slot no live declaration names is **omitted** rather than
published under a column name you never chose.

### And one facade passthrough stops being lossy

`UBBClient.get_usage` accepted three parameters where `MeteringClient.get_usage` accepts
eight, and defaulted `limit` to 50 against the metering client's 20 — so one client answered
the same call two ways depending which object you held. The facade now forwards all eight and
pages the same way. **If you call `UBBClient.get_usage` without `limit`, you now get 20 rows
rather than 50**; pass `limit=50` to keep the old page size.

---

## 18. The invoice-line grouping takes the one vocabulary's name (slice 7, #531 — pre-live)

`GET`/`PUT /api/v1/billing/postpaid-config` publish the axis a postpaid customer's usage is split
into invoice lines by as **`group_by`**, on both the request and the response. The old property
was named after the invoice line it produced rather than after what it grouped, and since #503 its
VALUE was already one word of the grouping vocabulary (`field:<declared field>` or
`rollup:<axis>`) — so one setting was speaking two vocabularies, one in its key and one in its
value. `group_by` is the word the economic query already publishes.

**On the client, the keyword follows**: `set_postpaid_config(group_by=...)` on both
`BillingClient` and `UBBClient`, and `get_postpaid_config()` returns a dict keyed `group_by`.
Passing the old keyword raises `TypeError`, and Python names it for you. A positional first
argument keeps working.

⚠ **ONE AXIS, NOT A LIST — even though the economic query's `group_by` is a list.** An analytics
question may be grouped by several axes; an invoice line is grouped by exactly one. Send one word,
built with `ubb.group_by_field(key)` or `ubb.group_by_rollup(name)`; a list is refused with `422`.
Only an axis `MeteringClient.grouping_options()` lists as supported on invoice lines is accepted.

⚠ **AND ONE BEHAVIOUR CHANGE RIDES WITH THE RENAME: OMITTING THE GROUPING NO LONGER CLEARS IT.**
The PUT is partial — a field left out is kept as stored, an explicit `""` clears it — but the
wrapper used to default the grouping to `""`, so `set_postpaid_config(consolidate_with_subscription=True)`
also collapsed every invoice to a single line. It now defaults to `None` and sends nothing, the
same as the consolidation flag always did. **To clear the grouping, say so:**
`set_postpaid_config(group_by="")`.

⚠ **If you call this route over raw HTTP, read this twice.** A body key the request does not
publish is **dropped, not rejected** — so a PUT still sending the old name answers `200` and changes
NOTHING, and the response's `group_by` shows the axis that was already stored. Read it back rather
than trusting the status.

---

## Release checklist (operator)

v3.0 is a coordinated release with the one integrating tenant:

1. **Wrap green** — `openapi/v1.json` frozen; SDK suite green; contract ratchet
   (regen → zero diff) green. ✅ carried by #84 + this cut.
2. **Coordinate with the tenant** — walk them through this guide; confirm a
   migration window. **Record that conversation on issue #85** before shipping.
3. **Cut the release** — tag `v3.0.0` from `main` after merge; the tag's
   `ubb.__spec_revision__` is the verifiable spec stamp for the build.
