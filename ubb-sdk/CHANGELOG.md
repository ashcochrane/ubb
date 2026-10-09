# Changelog

All notable changes to `ubb-sdk`. This project follows [semantic versioning](https://semver.org);
each release is stamped with the exact committed API-contract revision it was
generated against (`ubb.__spec_revision__`).

## 3.0.0

**The coordinated v3.0 release (#85).** One breaking cut carrying the generated
typed core (#84) and the RFC 9457 problem+json error model (#78) together — the
one integrating tenant migrates exactly once. **No compatibility shim.**

Full upgrade guide, covering every breaking edge: **[MIGRATION.md](./MIGRATION.md)**.

_Release date is set at tag time; publishing is gated on operator↔tenant
coordination recorded on issue #85 (see MIGRATION.md → Release checklist)._

**Spec-revision stamp** (verifiable on the release):

| Stamp | Value |
|---|---|
| `ubb.__version__` | `3.0.0` |
| `ubb.__spec_revision__` | `b2d65899f8ce35fbd243d7c86244a85d69ab74cc4a1006e4e15bd8d270702af1` |
| `ubb.__spec_version__` | `v1` |
| Generator | `openapi-python-client==0.29.0` |

The `__spec_revision__` is the sha256 of the committed `openapi/v1.json`; CI
regenerates the core from that spec and fails on any drift, so the stamp cannot
disagree with the shipped bytes.

### Breaking

- **Error model → problem+json + typed exceptions.** Every error is RFC 9457
  `application/problem+json` with a stable snake_case `code`. The SDK maps each
  to a per-code exception under a status-family parent (`ConflictError`,
  `UnprocessableEntityError`, …), all subclassing `UBBAPIError`.
  `UBBAPIError.code` is new. Several conditions changed HTTP status (withdraw
  insufficient-balance and would-overdraw `400→409`; duplicate creates
  `422→409`; grant-expiry / webhook validation `400→422`). See MIGRATION.md §1.
- **Cursor envelope on every list.** `PaginatedResponse[T]` (`data`,
  `next_cursor`, `has_more`); lists take `cursor`/`limit`, not `offset`. Bare
  arrays and `{invoices}` / `{grants}` wrappers are gone. `/me/grants` ordering
  changed to the creation keyset. See MIGRATION.md §2.
- **One verdict field set for batch/async ingest.**
  `BatchResult.succeeded/failed → accepted/rejected`;
  `BatchItemResult.ok/error → accepted/code (+detail)`. See MIGRATION.md §3.
- **Generated DTOs replace the nine hand dataclasses.** `record_usage` returns
  `RecordUsageResponse` — `balance_after_micros` is removed, use
  `new_balance_micros`. `UsageEventOut.id` is now `uuid.UUID` (was `str`). See
  MIGRATION.md §4.
- **The last untyped 200s are typed (#98)** — top-up / withdraw / refund /
  transactions / auto-top-up and the margin surface now return generated
  models (`TopUpCheckoutResponse`, `WithdrawResponse`, `RefundResponse`,
  `WalletTransactionOut`, `StatusResponse`); the corresponding hand
  result types are retired. `WalletTransactionOut.id` is `uuid.UUID` (was
  `str`). See MIGRATION.md §4. **The margin surface's three generated models —
  `CustomerMarginOut`, `GroupingFieldMarginRow`, `MarginTrendPointOut` — were
  typed by this change and then deleted outright in the same unreleased
  version**, with the routes that produced them; see MIGRATION.md §16.
- **`idempotency_key` now required on top-ups** (tenant + widget). See
  MIGRATION.md §5.
- **Single versioned API.** All routes under `/api/v1/…`; per-mount
  `docs`/`openapi.json` and API-roots removed (`base_url` unchanged). See
  MIGRATION.md §5.
- **The spend stop raises by default, and the signal cannot be swallowed by
  `except Exception:` (#421, #179 §1).** `record_usage(..., raise_on_stop)`
  now defaults to `True`; the signal is `UBBStopRequested`, which derives from
  `BaseException` (not `Exception`, not `UBBError`) and carries the whole
  acknowledgement as `stop.result` beside `event_id`, `idempotency_key`,
  `stop_scope`, `stop_reason` and `task_id`. The event was recorded and
  charged — never resend it. The old `UBBStoppedError` (an `Exception` under
  `UBBError`, raised only on opt-in) is gone: its name said the thing the
  signal must never say, and its base let a tenant catch-all eat it.
  `raise_on_stop=False` returns the ack with `result.stop` set, as before.
  `record_batch` still never raises; each `BatchItemResult` now carries its
  own `stop` / `stop_reason` / `stop_scope`, and `BatchResult` derives `stop`
  and `first_stop_index` from them. (v3.0 has not shipped, so this is part of
  the one coordinated cut rather than a second release.) See README →
  *Honouring a spend stop*.
- **What a stop does is a named value: `stop_behavior="raise"` (the default)
  or `"return"` (#574).** It replaces the boolean `raise_on_stop` on
  `MeteringClient.record_usage` and `UBBClient.record_usage` — **this entry
  supersedes the keyword named in the #421 entry above.** The boolean is
  removed, not aliased, so a call still passing it is a `TypeError`. The two
  values are `ubb.vocabulary.STOP_BEHAVIOR_RAISE` / `STOP_BEHAVIOR_RETURN`,
  which the client now holds by reference; any other value raises
  `UBBValidationError` before anything is sent. Behaviour is unchanged for
  both: `"raise"` raises `UBBStopRequested` carrying the acknowledgement,
  after the event was recorded, and `"return"` hands that acknowledgement
  back with `result.stop` set. `record_batch` still takes no such keyword and
  never raises for a stop. See MIGRATION.md §20.
- **A naive `recorded_at` raises `UBBValidationError`, not `ValueError`
  (#574).** A `datetime` with no offset is still refused before any request,
  on `record_usage` and on every item of `record_batch`, but inside the SDK's
  own family: `except UBBError:` now catches it, and `except ValueError:` no
  longer does. It was the one refusal the recording calls made outside
  `UBBError`. See MIGRATION.md §20.

### Added

- Registry-derived per-code exception hierarchy (`ConflictError`,
  `InsufficientBalanceError`, …) — catch a family or one exact code.
- Generated transport + DTO core (`ubb._core`), sync and async, produced from
  the committed spec under the CI ratchet (#84).
- `ubb.__version__` on the public surface, paired with the existing
  `ubb.__spec_revision__` / `ubb.__spec_version__` so a build is self-describing.
- Open-world tolerance: unknown fields land in `additional_properties`, response
  enums parse as plain `str` — a pinned client never crashes on a newly added
  field or enum value (ADR-003).
- **A unit of work is started and closed from the client (#422).**
  `start_task(customer_id, idempotency_key, ...)` registers work through
  `POST /api/v1/tasks` — the key is required and yours — and answers with a
  `StartedTask`: a context manager around the run whose `complete()` /
  `fail(outcome_reason)` / `cancel()` declare how it ended over the one close
  route. A clean exit with no declaration raises `TaskOutcomeRequired` (an
  ordinary `UBBError`) and leaves the work **open**; an ordinary exception
  declares `failed` with reason `execution_failed` and re-raises; a spend
  stop, an interrupt or any other `BaseException` propagates with nothing
  declared. `get_task`, `list_tasks` and `list_subtasks` wrap the three
  reads. The lifecycle's states and outcomes are named through
  `ubb.vocabulary` (`TASK_STATUS_*`, `TASK_OUTCOME_*`, `OUTCOME_REASON_*`),
  and `ubb.metering.TERMINAL_TASK_STATUSES` is the set of states a unit can
  have ended in. (The `start_task` that stood on `UBBClient` before #410
  wrapped a flag on the affordability call, which is gone; this one is
  written against the route that registers work.)
- **A stop says which bound was reached, and the client names the bounds
  (#457).** `stop_reason` — on the acknowledgement, on each batch item and
  on `UBBStopRequested` — carries one of the registry's seven `reason_code`
  values: the unit's own COGS ceiling at either altitude
  (`task_cogs_ceiling`; `stop_scope` says which), the customer's spend pool
  (`customer_spend_pool`), the wallet's hard floor (`hard_floor`), a silence
  window (`silence_window`), the absolute deadline (`absolute_deadline`) or a
  parent's end (`parent_killed`, `parent_expired`) — plus `task_not_active`,
  a verdict on a late event rather than a bound. Reach the constants by
  module (`from ubb import vocabulary`, then `vocabulary.REASON_CODE_*`);
  `ubb.metering.STOP_REASON_CODES` is everything an acknowledgement's
  `stop_reason` can say that UBB produces — the seven plus the verdict — so
  an integrator branches on a constant and never on a string. The set is open:
  the value stays a plain string on the wire, an unknown one still travels,
  and the client validates nothing. The three words the ack used to send
  for these stops are gone: the two altitude-specific ceiling words
  collapsed onto the one ceiling word with the altitude in `stop_scope`, and
  the one customer-wide word split into the pool's and the floor's — and the
  server's stored rows were migrated, so no reader needs a legacy map.
- **A supplier cost read off the provider's response has its own keyword
  (#570).** `record_usage(..., provider_response_cost_micros=...)` — on
  `UBBClient` too, and as a key of a `record_batch` event — carries the cost
  you obtained from the provider's response, where your Event Type's last
  publication declares a `provider_response` reported-cost mapping.
  `provider_cost_micros` stays the cost you supply directly, for a
  `caller_supplied` mapping. The route admits each only for its own source,
  never both on one event, and refuses anything else with a 422 naming the
  keyword that is admissible; the client holds no rule of its own. Either way
  the cost comes back as `result.provider_cost_micros`, the one supplier cost
  UBB resolved.
- **A stop says how it was applied and what it was measured on (#569).**
  `trigger_source`, `stop_bound_micros` and `stop_measured_micros` ride the
  acknowledgement, every `record_batch` item (`BatchItemResult`, typed — the
  batch's items are parsed through their generated model now) and
  `UBBStopRequested` (properties over `result`): the mechanism that applied
  the stop (`usage_ingest`, `enforcement_patrol`, `charge_projection`; never
  the cause, which is `stop_reason`), the bound `stop_reason` names as it
  stood when the stop was established, and the amount measured against it
  then. Each is `None` where it does not apply — never `0` for that; a zero
  floor is a real `0`. A replay of an `idempotency_key` now answers exactly
  what the original acknowledgement said, its stop included, rather than the
  customer's stop as it stands at the retry.

### Retained (not shims)

- `UBBConflictError` alias for `ConflictError`; `verify_webhook_legacy`
  (webhook-secret rotation, a product feature); `credit()` (base-money
  primitive). None dual-runs the old contract — see MIGRATION.md §7.

### Known gaps

- A few billing/margin endpoints remain untyped in the committed spec and still
  return raw `dict`s (#98).

  `MeteringClient.update_rate_card` / `get_rate_card_history` /
  `bulk_create_rate_cards` were listed here as dead against a v3.0 server. They
  are **no longer a gap**: all three are deleted, with the `RateCard` type they
  returned, so this release ships no method that cannot resolve. Books and
  publishes are what a caller reaches for instead — see MIGRATION.md §7.
  (v3.0 has not shipped, so this is part of the one coordinated cut rather than
  a second release.)
