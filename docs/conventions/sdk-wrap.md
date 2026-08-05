# The SDK wrap (#84 / decision #65 — generated core, hand shell)

The Python `ubb-sdk` never hand-types its API surface again. DTOs, enums, and
error classes are **generated from the committed contract and CI-diffed**; the
hand-written ergonomics survive as a thin shell over the generated core.

## The two layers

**Generated core — `ubb/_core/` + `ubb/_exceptions_generated.py`.** Produced by
`ubb-sdk/codegen/generate_core.py` (openapi-python-client, pinned exactly) from
`openapi/v1.json`, and `generate_exceptions.py` from `openapi/error-codes.json`.
Both are committed and ride the **same ratchet as the spec** (ADR-002): CI's
`contract` job regenerates and byte-diffs them, so hand edits are refused and a
spec/registry change that skips regeneration turns CI red. The generator version
is the only input — ruff post-hook disabled, newlines LF-normalized
(`.gitattributes`) — so any OS reproduces the committed bytes. See
`ubb-sdk/codegen/README.md`.

**Hand shell — everything else under `ubb/`, with the two named exceptions
below.** `UBBClient` and the product
sub-clients own what a generator can't express (#61): retry policy
(`retry.py`), webhook HMAC verification incl. two-signature rotation
(`webhooks.py`), stop-verdict-on-a-200 semantics, pagination, and the
problem+json → exception mapping (`_http.py`). Every response is parsed through
a **generated model** (`_models.from_wire`), so return types are never
hand-typed. `from_wire` normalizes the generator's `UNSET` sentinel to `None` so
absent optionals read as `None` — consumer call-sites keep their exact shape.

## Errors: catch a family or one exact code

The per-code hierarchy is generated from the registry: status-family parents
(`ConflictError`, `UnprocessableEntityError`, …) with per-code leaves
(`InsufficientBalanceError` under `ConflictError`). All extend `UBBAPIError`;
`UBBConflictError` remains an alias, `UBBAuthError` still owns 401, and the
client-side `UBBValidationError` is distinct from the server `ValidationError`.

```python
try:
    client.record_usage(...)
except InsufficientBalanceError:   # one exact registry code
    ...
except ConflictError:              # or the whole 409 family
    ...
```

## Open-world tolerance

Unknown fields land in a model's `additional_properties`; response enums are
bare strings (ADR-003 open enums), so a value minted after a client is pinned
parses as a plain `str`. A pinned client never crashes on tomorrow's field or
enum value. Pinned by `tests/test_generated_core.py`.

## Async

The generated core emits **async functions for free** (`asyncio` /
`asyncio_detailed` in `ubb/_core/api/`). The hand shell is **sync-only in this
build** — its ergonomics (retry with sleep, pagination, stop-verdict raising)
are synchronous, and the first tenant integrates synchronously. An async shell
can be added later against the already-generated async core with zero core
changes. (Facade-async decision, parked on #65, resolved here.)

## Spec-revision stamp

`ubb/_spec_revision.py` (generated, ratcheted) records the exact committed-spec
sha256 and version each build was cut from, exposed as `ubb.__spec_revision__`.

## Canonical vocabulary

`ubb/vocabulary.py` (generated, ratcheted) is the second exception to "hand
shell — everything else": a flat module of literals rendered from
`domain-vocabulary/` at the git root, so **a value the API can return is a
value the SDK can name** (#207). It carries no underscore prefix because it is
a *public* surface an integrator imports, and no `_generated` suffix because
there is nothing to re-export it through — a hand-written re-export layer would
be the second copy of every name it exists to abolish. The banner says it is
generated and a hand edit turns CI red, exactly as for the core above.

Not star-exported from `ubb/__init__.py`, deliberately: forty concepts' worth
of constants do not belong in the package's top-level namespace. Reach it by
module — `from ubb import vocabulary`.

It rides the same ratchet, via a different generator: `python -m
tools.vocabulary --write` at the git root, checked by the `contract`s job's
`Vocabulary generation gate` step and by `tests/contracts/`.

**`<CONCEPT>_KNOWN_VALUES` never decides a rejection.** ADR-0003's open enums
mean a value the registry has never seen is legal, so an SDK that raised on an
unrecognised status would break its callers the day UBB adds one. The suffix is
the warning: `_VALUES` is a closed set, `_KNOWN_VALUES` is what UBB recognises
today.

## Typed 200s everywhere — the gap is closed (#98)

Every operation whose 200 returns a JSON body declares a `response=` out-schema
in the platform, so the committed spec types all of them and the generated core
carries their DTOs — the last hand result types (`TopUpResult`,
`WithdrawResult`, `RefundResult`, `WalletTransaction`, `CustomerMargin`, …)
are retired. Pinned by `api/v1/tests/test_typed_200_pins.py`: a new endpoint
whose 200 carries no schema turns CI red. The rule when typing a response:
**document what the wire serves, never reshape it** — the schema's fields and
nullability come from reading the handler, not from what would be nice.
