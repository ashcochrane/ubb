# SDK code generation (the wrap)

The SDK's typed surface is **generated, never hand-typed** (issue #84, decision
#65). Two artifacts are generated from the committed contract and committed
in-repo under the same ratchet as `openapi/v1.json` (ADR-002):

| Artifact | Generated from | By |
| --- | --- | --- |
| `ubb/_core/` — transport + DTO core (attrs models, per-op functions, sync **and** async) | `openapi/v1.json` | `generate_core.py` (openapi-python-client, pinned) |
| `ubb/_exceptions_generated.py` — per-code exception hierarchy | `openapi/error-codes.json` | `generate_exceptions.py` (stdlib only) |
| `ubb/_spec_revision.py` — the spec revision this build was cut from | `openapi/v1.json` | `generate_core.py` |

## Regenerating

After any change to the committed spec or error-code registry:

```
pip install -e 'ubb-sdk[codegen]'      # the pinned generator
python ubb-sdk/codegen/generate_core.py
python ubb-sdk/codegen/generate_exceptions.py
```

Output is deterministic — the pinned generator is the only input (the ruff
post-hook is disabled, newlines are LF-normalized), so the diff you commit is
exactly the surface change.

## The ratchet (CI `contract` job)

CI regenerates both artifacts and fails on any diff, so **hand edits to
`ubb/_core`, `ubb/_exceptions_generated.py`, or `ubb/_spec_revision.py` are
refused**, and a spec/registry change that skips regeneration turns CI red. This
is the same spec-as-truth ratchet the platform's `openapi/v1.json` already rides.

## The hand shell delegates to the generated core

Everything under `ubb/` *except* the three generated artifacts is the
hand-designed ergonomic shell (`UBBClient` + product sub-clients): retry policy,
webhook HMAC verification, stop-verdict semantics, and pagination. The shell
issues HTTP and maps errors, then returns **generated DTOs** — the models are
never hand-typed again. See `ubb/client.py` and `docs/conventions/` for the
delegation contract.

## Upgrading the generator

`openapi-python-client` is 0.x with breaking minors, so it is pinned **exactly**
(`pyproject.toml` `[project.optional-dependencies].codegen` and
`generate_core.py`). Bumping it is a deliberate PR: bump both pins, regenerate,
and review the (possibly large) diff to the generated core as a real change.
