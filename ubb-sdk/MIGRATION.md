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
`InvalidRevenueModeError`, `NoCostCardsError`, `PricingError`,
`UnsupportedCurrencyError`, `ValidationError`, the three `EffectiveAt*Error`
(under `UnprocessableEntityError`); `FeatureNotEnabledError` (under
`ForbiddenError`); `InvalidCursorError` (under `BadRequestError`);
`RateLimitExceededError` (under `RateLimitError`). The full registry is
`openapi/error-codes.json`.

### Status-code moves you may be catching by number

The big-bang tightened HTTP semantics (400 = malformed only; 422 = semantic;
409 = conflict). If your v2.x code branches on `status_code`, re-check these:

| Condition | v2.x status | v3.0 status / exception |
|---|---|---|
| Withdraw with insufficient balance | `400` | `409` `InsufficientBalanceError` |
| Would overdraw the floor | `400` | `409` `WouldOverdrawError` |
| Duplicate create (plan / rate-card book / rate) | `422` | `409` `ConflictError` |
| Grant expiry validation | `400` | `422` |
| Webhook URL / event-type validation | `400` | `422` |
| Rate-limit (429) | 429 | `429` — now **always** carries a `Retry-After` header |

> **Note on "run not active" / hard-stop 429s.** There is no `UBBHardStopError`
> or `UBBRunNotActiveError` in v3. Under the one-rule contract a **spend stop
> rides a success (200) response**, not an error — read `result.stop` (or opt
> into `record_usage(..., raise_on_stop=True)` → `UBBStoppedError`). A 429 from
> usage ingestion is plain rate limiting and is safely retried (see §6).

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
  reports, past-limit, referrals earnings) are **not** paginated, but now refuse
  explicit date windows wider than **366 days** (hourly timeseries: **92**) with
  a `validation_error` (422).

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
| `get_customer_margin` | `CustomerMarginOut` (full body — adds `revenue_mode`, `usage_revenue_micros`, `total_revenue_micros`, `event_count`, `external_id`, `period`) |
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

## 7. Retained aliases — deliberately kept, **not** compatibility shims

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

### Do **not** use — dead methods slated for removal (#86)

`MeteringClient.update_rate_card`, `.get_rate_card_history`, and
`.bulk_create_rate_cards` call routes the big-bang removed. They are known-dead
against a v3.0 server and will be deleted in the launch sweep (#86). Use
`create_rate_card` (versioned rate cards supersede in place).

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
who had just paid. Read `PreCheckResponse.stop`/`.stop_reason` (already present) for
the real, wallet-wide stop verdict — there is no per-task floor to migrate to, because
there is no per-task floor anymore.

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

## Release checklist (operator)

v3.0 is a coordinated release with the one integrating tenant:

1. **Wrap green** — `openapi/v1.json` frozen; SDK suite green; contract ratchet
   (regen → zero diff) green. ✅ carried by #84 + this cut.
2. **Coordinate with the tenant** — walk them through this guide; confirm a
   migration window. **Record that conversation on issue #85** before shipping.
3. **Cut the release** — tag `v3.0.0` from `main` after merge; the tag's
   `ubb.__spec_revision__` is the verifiable spec stamp for the build.
