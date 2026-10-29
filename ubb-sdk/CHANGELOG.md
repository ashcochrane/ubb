# Changelog

All notable changes to `ubb-sdk`. This project follows [semantic versioning](https://semver.org);
each release is stamped with the exact committed API-contract revision it was
generated against (`ubb.__spec_revision__`).

## 4.0.0

**The SDK's first release, cut at the cutover (#190; ADR-0026).** The tree
carried the number 3.0.0 while the re-model was built, and nothing was ever
released or tagged under it; everything listed under 3.0.0 below, and every
pre-live edge in **[MIGRATION.md](./MIGRATION.md)** §8–§24, reaches a tenant for
the first time here. The major is 4 rather than 3 because the SDK's own surface
broke after the pre-release number was set — ADR-0003 §6 allows a major only
then, and ADR-0026 records the departure from its "v3.x at launch".

**The release is a tag and a wheel, and nothing publishes it** (R2, #190 spec
part 3 §9). The tag is `sdk-v4.0.0`, annotated, on the cutover's merge commit
on `main`. The wheel is built from a clean export of that tag by
`release/build_wheel.py` — the tag's own copy — twice, on Python 3.13, with
`SOURCE_DATE_EPOCH` set to the tagged commit's committer time, in a fresh
environment holding exactly the tag's lock, `release/build-requirements.txt`
(every package pinned and hashed, and no installer: the environment is created
without pip and filled from outside), with no outside Python, pip or setuptools
setting reaching it. The recipe refuses a dirty export, a tag on another
commit, another Python, a backend `pyproject.toml` requires outside the lock, an
environment that is not exactly the lock, and two builds that differ.

**Release stamp** (verifiable on the release):

| Stamp | Value |
|---|---|
| `ubb.__version__` | `4.0.0` |
| `ubb.__spec_revision__` | `f9e2cabcc276be46bf28267b57f4cacb3be981de2a30e3cb8b55a4a680c89d92` |
| `ubb.__spec_version__` | `v1` |
| Generator | `openapi-python-client==0.29.0` |
| Tag | `sdk-v4.0.0` |
| Wheel and its SHA-256 | `ubb_sdk-4.0.0-py3-none-any.whl`, `fdf9ae7688a9e5c632f83fb64347abc65de3e2f1db943b69f08edcb12ddf4d89` — built from `sdk-v4.0.0` at `c2eb35ff3431faf2985379b05b50031a59aa639c`, twice, one SHA-256, on Python 3.13.14 with the lock at SHA-256 `7bd4b746aa72c0852ecb5be1a171695ced7188e12c291e1e3fdd0f4b00ae9da0`, by the tag's recipe at SHA-256 `f6bbb0d39dd6aeeffb8f423727f7bfd45eabbb427e8c7bde8da5944cea4831c7` with `SOURCE_DATE_EPOCH` 1793263109; recorded by the cutover's second pull request (#190) |

### Changed

- **The version is 4.0.0** (`pyproject.toml`, `ubb.__version__`), and the
  Integration Blueprint's Python target names SDK major 4.
- **The build backend is pinned exactly** (`setuptools==80.9.0`), the one the
  release recipe builds with.
- **Every receipt states what it explains** (MIGRATION.md §26).
  `RecordUsageResponse.pricing_receipt_subject_type` and
  `UsageEventDetailOut.pricing_receipt_subject_type` are required and never
  null, and their generated enums are `RecordUsageResponsePricingReceiptSubjectType`
  and `UsageEventDetailOutPricingReceiptSubjectType` (each was `…Type0`, the
  generator's name for the non-null member of a nullable union). On
  `UsageBatchItemResponse` the field is required and nullable: null on a
  rejected item, beside its null receipt.

### Removed

- **`ubb.vocabulary` loses the audit action no record could ever carry**
  (MIGRATION.md §25): `AUDIT_ACTION_SYSTEM_PREPRODUCTION_MODEL_CUTOVER` and
  `AUDIT_ACTION_WITHHELD_VALUES` are deleted, and `AUDIT_ACTION_VALUES` no
  longer holds `'system.preproduction_model_cutover'`. The audit trail opens
  with no synthetic row (#190, ruled 2026-10-23, option (i); ADR-0026 §6), so
  the value was registered only to be refused, and the cutover deleted it with
  its exclusion.

No call or exception changed in this cut, and no model beyond the receipt's
subject above: the SDK was settled in R10-W5 (MIGRATION.md §24).

## 3.0.0 — the tree's pre-release number, never released

> **Not a release.** No tag and no wheel ever carried 3.0.0; the entry below is
> kept as the record of what the number described while the re-model was built,
> and every change in it shipped first in **4.0.0**. Its stamp table recorded a
> contract revision long since superseded (`b2d65899…`); the release stamp is
> 4.0.0's, above.

**The coordinated v3.0 release (#85).** One breaking cut carrying the generated
typed core (#84) and the RFC 9457 problem+json error model (#78) together — the
one integrating tenant migrates exactly once. **No compatibility shim.**

Full upgrade guide, covering every breaking edge: **[MIGRATION.md](./MIGRATION.md)**.

_Never tagged: the release this section planned is 4.0.0 (see above)._

**Spec-revision stamp** (as it stood when the number was set; superseded):

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
  then. Each is a required key whose value may be `None` — always on the
  wire, so the generated models refuse a body that omits one — and is `None`
  where it does not apply, never `0` for that; a zero floor is a real `0`.
  Both figures are signed: a hard floor's bound and the balance below it are
  negative. A replay of an `idempotency_key` now answers exactly
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
