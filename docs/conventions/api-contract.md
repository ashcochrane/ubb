# The API contract (#78 / #63 — one dialect everywhere)

Every route on the versioned surface (`/api/v1/`, the committed
`openapi/v1.json`) speaks one dialect. This document is the contract's prose;
the machine contract is the **code registry** checked in beside the spec
(`openapi/error-codes.json`) and the committed OpenAPI document itself
(ADR-002). Enforced in-suite by `api/v1/tests/test_problem_contract.py` and
per-route by each surface's own tests.

## Errors: RFC 9457 problem+json

Every error from every endpoint — including ops, sandbox, and the `/me`
widget surface — renders as `application/problem+json`:

```json
{
  "type": "https://ubb.dev/errors/would_overdraw",
  "title": "Would overdraw below the floor",
  "status": 409,
  "code": "would_overdraw",
  "detail": "debit would breach the overdraft floor; pass allow_negative=true to force",
  "floor_micros": 0,
  "balance_micros": 1000000
}
```

- **`code` is the contract.** Snake_case, from the registry's `problems`
  section; each code has exactly one status. Adding a code is compatible;
  renaming or removing one is breaking. Integrations branch on `code`, never
  on prose.
- **`title`/`detail` are prose, never contractual.** Wording may change
  without notice. `type` derives one-to-one from the code and exists only to
  link docs.
- **Extension members** (RFC 9457) carry structured context per code — e.g.
  `would_overdraw` adds `floor_micros`/`balance_micros`, `validation_error`
  adds `errors` (sanitized `{loc, msg, type}` items) on request-validation
  failures — the storage-constraint lane below carries `detail` only — the
  failing `/ready` adds `checks`. Extensions are open-world: clients must
  tolerate unknowns.
- **Status semantics** (#63): 400 malformed / bad cursor · 401 · 403 product
  gate or forbidden · 404 · 409 conflict with current state · 410 gone ·
  422 semantic validation · 429 always with `Retry-After` · 5xx as
  `internal_error`/`service_unavailable`, internals never leaked (tracebacks
  go to the server log, not the body).
- **Malformed UUID identifiers** (#102): a UUID-backed identifier that does
  not parse cannot name a resource — in a **path** it answers the same bare
  404 as a nonexistent one; in a **query param or body field** it is a 422
  `validation_error` like any other invalid input. Never a 5xx. Endpoints
  annotate such identifiers with `core.identifiers.UUIDIdentifier` (validates
  at the boundary, renders as a bare `string` in the document); the channel
  mapping lives in the central validation handler. Pinned by
  `api/v1/tests/test_uuid_identifier_pins.py`.
- **Storage-constraint violations** (#103): a doc-legal scalar that violates
  a database constraint — NUL bytes in text, integer overflow, over-long
  strings — surfaces as the driver's `DataError` and answers 422
  `validation_error` with a stable sanitized detail (the driver's message
  can name column types, so it goes to the server log, never the body).
  Only `DataError` takes this lane; every other database error stays a 500
  `internal_error`. The mapping is central (`api/v1/problems.py`), so it
  covers future fields too. Pinned by `api/v1/tests/test_data_error_pins.py`.

Mechanics: endpoints `raise core.problems.Problem(code, detail, extensions=,
headers=)` (products may raise it too — `core` is importable everywhere);
the central handlers in `api/v1/problems.py`, installed on the one NinjaAPI,
render everything — including stray `HttpError`s, request-validation
failures, `Http404`, auth failures, and unhandled exceptions. **No endpoint
builds an error body by hand.** An unregistered code refuses at raise time.
Where a route documents error statuses in its `response=` map, they point at
`core.problems.ProblemOut`.

## Entity lists: one cursor envelope

Every entity list takes `cursor` + `limit` (clamped to [1, 100], default 50)
and answers:

```json
{"data": [...], "next_cursor": "<opaque-or-null>", "has_more": false}
```

Keyset cursoring (`core/pagination.py`, blessed as-is): descending
`(time_field, id)`, opaque base64 cursor, `next_cursor` present only when
`has_more`. A bad cursor is a 400 `invalid_cursor` problem. The composition
layer's one idiom is `api.v1.pagination.paginate()`. Bare arrays and
unwrapped lists are banned from the public surface; short config lists wear
the envelope too.

**Computed reports are not lists** (analytics, margin, trend series,
past-limit report, usage summary): cursor-exempt but **parameter-bounded** —
explicit date windows are refused past 366 days (hourly timeseries: 92) with
`validation_error`.

## Ingest verdicts: data, not errors

The 200-always doctrine stands: on the usage-ingest surface a non-200 always
means "not recorded"; per-event verdicts ride the body as **data**, never
problem+json. Batch and async ingest speak **one verdict field set**:

- Shared core: `accepted` (bool), `code` (rejection word, null when
  accepted), `detail` (prose, null except sync-fallback rejections), and the
  stop trio `stop`/`stop_reason`/`stop_scope`.
- Batch extras: accepted items carry the full priced receipt (the single-call
  success body). Envelope counters: `accepted`/`rejected`.
- Async extras: `estimated_cost_micros`, `mode` (`async`/`sync_fallback`),
  `duplicate_suspect`, and `event_id` on accepted sync-fallback items.

Verdict words come from the same registry (`verdicts` section):
`ingest_rejections` reference problem codes; `stop_reasons`, `stop_scopes`,
and `pre_check_reasons` are the closed vocabularies of the spend-control
surface (`apps/platform/tasks/reasons.py`, `RiskService`).

## Idempotency is a domain concept

Mutations whose replay would move money or write usage carry a **required
`idempotency_key` body field backed by database uniqueness** (no
`Idempotency-Key` header in v1): debit, credit, withdraw, refund, grants
(create/void), top-ups (tenant + widget — `uq_topup_attempt_idempotency`),
and all usage ingestion (UsageEvent uniqueness at record/settle). A replay
is a no-op returning the original outcome, never a double effect. Entity
creates dedupe on natural identity or answer 409 `conflict` (customers,
plans, rate-card books, rates, webhook configs, referral attribution).

## Adding a surface

1. Raise `Problem`s with registry codes; need a new code → add it to
   `openapi/error-codes.json` (sorted, LF) in the same change.
2. Lists go through `paginate()` + a concrete `{data, next_cursor,
   has_more}` schema; reports get bounded parameters.
3. Regenerate the spec (`python scripts/export_openapi.py`) — the diff is
   the API review; the drift/breaking gates hold the rest.

## Conformance sweep (wanted, not gating — #87)

`ubb-platform/conformance/` fuzzes every operation of the committed spec
in-process (schemathesis over the WSGI app) and reports where the
implementation contradicts the document: undocumented statuses, documented
response-shape mismatches, and any error that breaks the problem+json
envelope above. "Contract" here = the operation's `responses` map **plus**
the registry's 4xx statuses, which are documented globally, not per-route;
5xx is always a finding. Excluded from the default suite; run it with
`python -m pytest conformance` (needs `pip install schemathesis`). CI runs
it as the non-blocking `conformance` job — findings land in the job
summary, never as a red X. Promoting it to a gate is a future decision.
