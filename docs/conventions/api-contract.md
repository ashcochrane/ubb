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
`core.problems.ProblemOut`, and the document declares them under
`application/problem+json` — the media type the wire serves (#104: ninja
exports `response=` models under plain `application/json`; the one schema
seam in `api/v1/api.py` re-keys the problem envelopes, so the committed and
runtime documents both tell the truth; pinned by
`api/v1/tests/test_problem_media_type_pins.py`).

## Entity lists: one cursor envelope

Every entity list takes `cursor` + `limit` (clamped to [1, 100], default 50)
and answers:

```json
{"data": [...], "next_cursor": "<opaque-or-null>", "has_more": false}
```

Keyset cursoring (`core/pagination.py`, blessed as-is): descending
`(time_field, id)`, opaque base64 cursor, `next_cursor` present only when
`has_more`. A bad cursor is a 400 `invalid_cursor` problem. The `api/v1`
idiom (#115) is `api.v1.pagination.page(qs, cursor, limit,
serialize=<entity serializer>)`, which owns the envelope; `empty_page()` is
the no-container answer (missing wallet, gated caller). The response schema
is a **concrete subclass of `Paginated[T]`** (`class PaginatedRates(
Paginated[RateOut]): ...`) — the subclass pins the OpenAPI component name,
which must stay unique in the one document (ninja silently overwrites
duplicates) and stable across releases (renames break the spec and the
generated SDK). Each entity's row mapping is ONE named serializer function
declared beside its Out schema — never a second inline dict. The product
api mounts on the same document (`apps/referrals/api`,
`apps/subscriptions/api`, `apps/platform/events/api`) still hand-assemble
the envelope; they adopt this idiom as they are next touched. Bare arrays
and unwrapped lists are banned from the public surface; short config lists
wear the envelope too.

**Computed reports are not lists** (analytics, margin, trend series,
usage summary, the two spend-control reports): cursor-exempt
but **parameter-bounded** — explicit date windows are refused past 366 days
(hourly timeseries: 92) with `validation_error`. A report that lets the caller
leave the window open bounds it itself — the spend-control reports take the
366 days ending now — and echoes the window it applied, so the bound is never
silent (#465). **Default first, bound second, against the RESOLVED span**: the
reports written before #499 bound only when the caller sent BOTH dates, so an
open end escaped the ceiling entirely.

**How far back is a different number from how much per request, and a report
that publishes one owes the other** (#500). UBB keeps the economics for six
years and detailed measurement on a shorter platform clock; `core/retention.py`
owns both dates, one platform-wide each, with no per-tenant policy. *Six years
available* beside *at most 366 days per request, no pagination* is two numbers
that do not compose on their own, so a report reaching back past a horizon
states both: the horizons as response fields under their final names
(`economic_data_available_from`, `measurement_data_available_from`), published
whether or not anything was truncated, and the per-call bound in the same
description. **A measure whose stretch reaches past its horizon says so** —
`measure_status: unavailable_outside_retention_horizon` with `available_from`,
never a zero and never a partial total presented as a total.

Two boundaries of that rule, recorded here because they are the kind a later
report will meet again. **A remedy is only offered where a remedy exists**: the
economic query's `context` names the axes and bucket at which asking again would
produce a margin, and it is therefore absent where NO row of the answer could
state a figure — a coarser question about a released stretch is refused for the
same reason the first one was, so listing the money with that remedy beside it
would publish an instruction that cannot work. This is a boundary of the
"never silently drop" prohibition rather than an exception to it: under
truncation no figure is stated at all, so no total can be short. **And rows are
the groups the data produces**, so a GROUPED question over a wholly released
stretch has no rows to carry the state on — the groups that existed there are
exactly what the horizon no longer holds. The horizon fields are what say why
the series starts where it does; only the ungrouped, unbucketed question is
guaranteed a row. ⚠ A refusal is a problem+json body and carries no horizons, so
a caller whose window is refused for spanning too long learns the horizon from
its next successful answer rather than from the refusal.

## Usage verdicts: data, not errors

The 200-always doctrine stands: on the usage-recording surface a non-200 always
means "not recorded"; per-event verdicts ride the body as **data**, never
problem+json. #78 unified one verdict field set across three routes; slice 1
deleted the third (#236), so what follows is the surviving shape — the batch
route's items, against the single-call body they mirror:

- A **rejected** item is `accepted: false` with `code` (the rejection word,
  from the registry) and `detail` (prose), and the stop trio
  `stop`/`stop_reason`/`stop_scope` constant: nothing was recorded, so nothing
  can have stopped.
- An **accepted** item is `accepted: true` plus the single-call success body
  verbatim, its stop verdict included. It carries no `code` and no `detail` —
  there is nothing to report.
- Envelope counters: `accepted`/`rejected`.

Verdict words come from the same published document as the problem codes —
`openapi/error-codes.json`, its `verdicts` section: `ingest_rejections`
reference problem codes; `reason_codes`, `stop_scopes`, and
`affordability_reasons` are the vocabularies of the spend-control surface
(`apps/platform/work/reasons.py`, `RiskService`, the kernel's admission
check). **The verdicts block is a MIRROR that nothing generates**, so it is
pinned rather than derived: `reason_codes` mirrors the reason module — the
registry's seven known `reason_code` values plus the one UBB-produced verdict
that is not a bound (`task_not_active`) — and `affordability_reasons` mirrors
the registry's `affordability_reason` (the nine known values, produced by
constant on both sides of the product boundary; the affordability read and
the start's refusal both answer from it). The two pins are
`api/v1/tests/test_problem_contract.py`'s
`test_the_reason_codes_are_the_registrys_seven_plus_the_one_verdict` (#457)
and `test_the_affordability_reasons_are_the_registrys_nine` (#463), both
holding the block to `core.vocabulary` by set equality, so neither mirror can
drift. Any change to `reasons.ALL_REASONS` or to the registry's
`affordability_reason` known values opens that file, and the pin says so
before the console does.

## Idempotency is a domain concept

Mutations whose replay would move money or write usage carry a **required
`idempotency_key` body field backed by database uniqueness** (no
`Idempotency-Key` header in v1): debit, credit, withdraw, refund, grants
(create/void), top-ups (tenant + widget — `uq_topup_attempt_idempotency`),
all usage ingestion (Posting uniqueness at record/settle), and registering
a unit of work (`POST /tasks` — `uq_task_idempotency_key`, unique per
customer, claimed permanently; #410). A replay is a no-op returning the
original outcome, never a double effect, and the start says so with
`replayed: true`; a repeat that changes a pinned field is 409
`idempotency_key_conflict` naming the field. The close of a unit of work
carries no key and needs none — the unit's own identity is the key: an
identical repeat replays (`replayed: true`, the original's
`charge_created`), and one declaring a different outcome or reason is 409
naming the state the unit is really in (#409, #416). Entity creates dedupe
on natural identity or answer 409 `conflict` (customers, plans, rate-card
books, rates, webhook configs, referral attribution).

**Recording reads the Event Type's last publication (#605).** Draft changes do
not affect production recording. Production uses the Event Type's last
published declaration; changes take effect when they are published. Every
declaration fact recording consumes comes from that one read, and an Event
Type declared and never published is recorded as an undeclared key is.

**A usage replay is answered before anything about current configuration is
asked (#605).** On both recording routes the order is: resolve the customer
(and task) in this tenant, find an event already recorded under the tenant,
customer and `idempotency_key` — one lookup, `UsageService.replay`, shared by
the routes and `UsageService`'s own recording path — and return its original
acknowledgement;
only a new event meets the admissions (the Event Type's published declaration,
the Grouping Field registry). So a publication or a retired field since cannot
make an already-successful write unreplayable. No body is compared: a usage
repeat carrying different fields still answers the original, which is the
existing contract and not a pinned-field check like the start's.

## A supplier cost: one transport per source, one amount back (#570)

The recording request carries one supplier-cost field per reported-cost
source that reaches UBB on the call: `provider_cost_micros` (supplied
directly by the caller) and `provider_response_cost_micros` (obtained from
the provider's response; UBB cannot verify how, and admits it on the declared
source's word). Each is admitted only where the Event Type's last publication
declares that source, never both on one event, and is refused — a 422, or a
rejected batch item — anywhere else rather than dropped; the refusal names
the field that is admissible, or says neither is. Either lands in the one
supplier-cost column, and every response publishes it as
`provider_cost_micros`, the canonical resolved COGS: no response carries the
transport's name. A new way for a supplier cost to arrive gets a field of its
own — an existing field's published meaning is never widened to carry it.
Each field's meaning is its published description. Pinned by
`api/v1/tests/test_two_request_fields_each_with_one_meaning.py`.

## Vocabulary: the values a field may carry (#208)

Two vendor extensions are part of the published dialect. Both are
**generator-owned** — never hand-written into a schema.

| Extension | On | Means |
|---|---|---|
| `x-ubb-concept` | any string-shaped schema node | the UBB concept this field carries, named in `domain-vocabulary/` |
| `x-ubb-known-values` | an **open** concept's node | the values UBB recognises today. Documentation, never a constraint |

A field declares its concept and **nothing else** — the values arrive at export
time from `openapi/known-values.json`:

```python
status: str = Field(json_schema_extra={"x-ubb-concept": "task_status"})
```

**On a list field the marker goes on the ITEM**, because the concept names what
a member of the list *is*, not the array around it — and the applier refuses a
node that is not string-shaped, which an array is not. Declare the item once and
reuse it, so a field and its optional twin cannot drift:

```python
TenantProduct = Annotated[
    str, Field(json_schema_extra={"x-ubb-concept": "tenant_product"})]

products: list[TenantProduct]                 # renders items: {type: string, …}
products: Optional[list[TenantProduct]] = None  # anyOf[array|null]; same item
```

`json_schema_extra` renders metadata; it does not validate. A `closed` concept's
`enum` therefore documents the value set rather than enforcing it, and the
enforcement stays where the backend imports the same set from `core.vocabulary`
— which is the agreement #208 exists to make structural. Do not add a second
enforcement point (see the `Literal[...]` rule below).

An `open` concept keeps `type: string` and gets `x-ubb-known-values`; it is
**never** converted to an `enum`, because a value UBB has never seen is legal
(ADR-0003) and a schema enumerating the set would make UBB learning a new one a
breaking change. A `closed` concept gets a real `enum`. A concept whose values
the tenant owns gets neither, and a marker on one is refused.

**A nullable `closed` field marks the alias, never the `Optional`.** Write
`Optional[UnresolvedReason]`, so the marker lands in the STRING MEMBER of the
union django-ninja renders. Hoisting it on to the union node itself — which is
what `Annotated[Optional[str], Field(...)]` does — puts the generated `enum`
beside the `anyOf`, and JSON Schema reads keywords at one node **conjunctively**:
the field then admits `null` under `anyOf` and refuses it under `enum`, so the
document contradicts every response the server sends for an unset value.

Nothing else catches it. The wire body is unchanged, the export is clean (the
applier asks only whether the node is string-*shaped*, and a union with a string
member is), and `oasdiff` reads an added property either way — a document that
lies with a green board. `test_a_closed_concepts_marker_never_sits_on_a_nullable_union`
holds every advertised `closed` concept to this. The rule does not bind the
`open` kind: `x-ubb-known-values` is documentation and constrains nothing, so a
union node is an honest home for it.

**Never type a vocabulary field as `Literal[...]`.** That is a second copy of a
value set the registry owns, and for an open concept it is the silent closure
G4 exists to refuse. The gate accounts for every `enum` in the committed
document by JSON pointer, so a new one has to come past a reviewer.

The export **refuses** a marker whose concept the backend does not yet serve —
the contract states a value only where the backend already returns it. Full
rules, and the order they force on a slice, in
[`openapi/README.md`](../../openapi/README.md).

## A declared exact decimal is a canonical decimal string (#571)

Money crosses the wire as integer micros. A **declared quantity that may carry
a fraction** does not fit that shape, and a JSON number is the wrong one: most
clients parse it into a binary float, which gives 2**53 + 1 back as ...992.
So the first such field — a `constant` Measurement's `constant_value` — is
**a JSON string for both value types**, and the declared `value_type` gives
its meaning (owner ruling on #571, comment 6024142285):

- **Accepted**: `^(-?[0-9]+(\.[0-9]+)?)$` — base 10, an optional leading `-`,
  ASCII digits, and an optional fractional part with a digit on each side of
  the point. No exponent, no `+`, no whitespace, separators or locale
  formatting. A JSON number or flag is refused as the wrong representation.
- **Stored and answered** in ONE canonical form,
  `^(0|-?(0\.[0-9]*[1-9]|[1-9][0-9]*(\.[0-9]*[1-9])?))$`: no unnecessary
  leading zero, no trailing fractional zero or point, and `0` for every
  spelling of zero (`01.500` is `1.5`, `-0.000` is `0`). Canonical forms are
  what a publication compares, so a value re-declared in another spelling is
  not a revision.
- **The grammar is checked as text**, by a full match over ASCII `[0-9]`,
  never by asking a decimal parser whether the text is a number — Python's
  `Decimal` reads whitespace, underscores, other scripts' digits, `NaN`,
  `Infinity` and exponents. Nothing on the way rounds it and no precision
  limit is introduced. `apps/platform/event_types/exact_decimals.py` owns both
  grammars and the one function between them; the contract states both as a
  `pattern` on the string member, and a test holds the contract and the two
  patterns spelled above to that module.
- **The string is not evidence that the value is a string.** A generated
  integration emits a correctly typed exact literal for its target.

This is the precedent the exact recording representation of a Measurement
quantity (#603) weighs. It is **not** a decision for recording: the recording
request still carries whole numbers, and #603 decides what it carries.

## Adding a surface

1. Raise `Problem`s with registry codes; need a new code → add it to
   `openapi/error-codes.json` (sorted, LF) in the same change.
2. Lists go through `page()` + a concrete `Paginated[T]` subclass and a
   named per-entity serializer; reports get bounded parameters.
3. Regenerate the spec (`python scripts/export_openapi.py`) — the diff is
   the API review; the drift/breaking gates hold the rest.
4. Breaking the contract? Generate the suppression entries, never type them:
   `python openapi/contract_gate.py --baseline origin/main --emit` from the git root,
   paste the lines into the file each belongs in, and write the `#` comment
   block that says why. CI then re-checks the **cumulative** set against the
   `api-v1-launch` baseline — see [`openapi/README.md`](../../openapi/README.md).

## Conformance sweep (wanted, not gating — #87)

`ubb-platform/conformance/` fuzzes every operation of the committed spec
in-process (schemathesis over the WSGI app) and reports where the
implementation contradicts the document: undocumented statuses, documented
response-shape and content-type mismatches, and any error that breaks the
problem+json envelope above. "Contract" here = the operation's `responses` map **plus**
the registry's 4xx statuses, which are documented globally, not per-route;
5xx is always a finding. Excluded from the default suite; run it with
`python -m pytest conformance` (needs `pip install schemathesis`). CI runs
it as the non-blocking `conformance` job — findings land in the job
summary, never as a red X. Promoting it to a gate is a future decision.
