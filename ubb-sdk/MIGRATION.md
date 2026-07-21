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

### Still-untyped endpoints (known gap, #98)

A few billing/margin endpoints leave their 200 body untyped in the committed
spec, so the SDK still returns **raw `dict`s** (or a small shell result):
top-up / withdraw / refund / transactions / auto-top-up and the margin surface.
`analytics = client.usage_analytics(...)` etc. remain dict-keyed. Typing these
platform-side is tracked in **#98**; when done they flow into the generated core
for free — no SDK change needed on your side.

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

## Release checklist (operator)

v3.0 is a coordinated release with the one integrating tenant:

1. **Wrap green** — `openapi/v1.json` frozen; SDK suite green; contract ratchet
   (regen → zero diff) green. ✅ carried by #84 + this cut.
2. **Coordinate with the tenant** — walk them through this guide; confirm a
   migration window. **Record that conversation on issue #85** before shipping.
3. **Cut the release** — tag `v3.0.0` from `main` after merge; the tag's
   `ubb.__spec_revision__` is the verifiable spec stamp for the build.
