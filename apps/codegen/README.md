# ubb-codegen

Turns a resolved **Integration Blueprint** into the integration code a tenant drops in.

The server decides what a tenant's integration code must *mean* and answers it as a
`ResolvedIntegrationBlueprint` (`POST /api/v1/code-builder/blueprints`, ADR-0015). This package
decides how that is *expressed*. It is one function:

```ts
import { render } from "ubb-codegen";

const files = render(blueprint); // RenderedFile[]: { kind, path, contents }
```

`render` is pure. The same Blueprint is always the same files; it reads nothing but its argument
and imports nothing but its own modules, so it has no way to reach the console, a network, a
filesystem or a clock. `tsconfig.src.json` and `eslint.config.js` hold that: no DOM or Node types
are in scope under `src/`, and a non-relative import, `Date`, `fetch`, `process` and `Math.random`
are lint errors there.

It renders a Blueprint that is not ready, as files that say what is missing and refuse to run. It
throws `BlueprintNotRenderable` only for a document it cannot read: an unknown `schema_version` or
`renderer_contract_version`, a target with no renderer, or a token that breaks the contract.

## What an artifact is

For the `python_sdk` target (SDK v3), `render` returns:

| `kind` | `path` | What it is |
|---|---|---|
| `module` | `ubb_integration.py` | Every value the Blueprint resolved. Dropped in, never edited, replaced whole on regeneration. |
| `call_site` | `call_sites/<name>.py` | One block per place a tenant's own code calls the module. **No generated value appears in one.** |
| `environment_example` | `.env.example` | `UBB_API_KEY=` and `UBB_BASE_URL=`, with nothing after the equals sign. |
| `verify_script` | `verify_integration.py` | Checks the declared paths against a response the tenant's supplier really returned. Calls nothing. |

The `shell_http` target is not rendered yet; its two catalogue symbols are declared.

## The rule that places a token

A Blueprint call is a flat list of tokens (ADR-0015 §3). `src/tokens.ts` is the only place the
convention is read, and it never decodes a key:

1. `api_key`, a `secret_reference`, is the credential. It is what the client is built with, read
   from the environment by the name the Blueprint gives.
2. A **one-segment** name is a field the call's request publishes. It is an argument, passed under
   exactly that name.
3. For the two fields that hold an object of declared keys (`grouping_fields`, `measurements`),
   each one-segment token is one **key**, carried as its literal. The tokens named under the key
   follow it directly and share one `<field>.<segment>` prefix, read off the first of them; the one
   named exactly that prefix is the **value** under the key.
4. Every other token is a **declared fact**. It is never sent and never asked for. It is stated in
   a comment beside the value it is about.

Three facts change how a value is written, by the last segment of their name: `source_path` (the
value is read off the response by that path), `response_shape_representation` (by subscript for
JSON, by attribute for a Python object), and `amount_representation` (the value is a supplier's
cost, converted to whole micros once). `pricing_mode` chooses one sentence of comment.

The three binding classes are shapes: a `platform_known` token is a literal, a `runtime_bound`
token is a required keyword parameter named exactly as the Blueprint names it, and a
`secret_reference` is `os.environ[...]`. A literal with no configured value is written as a call
that raises, naming the token.

## Comments

Two classes and no third. **Provenance** is generated from the Blueprint in one form,
`<name> = <json>[ · <qualifier> <json>]...` (`src/comments.ts`). **Contract** is a line of the
renderer catalogue (`src/catalogue.ts`), written exactly as it stands there. The catalogue is
closed and versioned: `CATALOGUE_VERSION`, pinned whole by `tests/__snapshots__/catalogue.v1.json`.
Its symbols (`UBB_API_KEY`, `UBB_BASE_URL`, `stop_requested`, `UBB_EXIT_STOP_REQUESTED` = 20) are the
renderer's own and are not registry concepts.

## Where things come from

- **The Blueprint's type** is generated from `openapi/v1.json` into `src/generated/` by
  `pnpm contract:types` on every typecheck. It is not committed.
- **The fixtures** under `fixtures/` are written by the platform, not by hand:
  `ubb-platform/api/v1/tests/test_the_renderers_fixtures_are_what_the_platform_answers.py` declares
  configuration through the tenant's routes, resolves each Blueprint through its route, and holds
  the committed file equal to the answer. The same module writes the conversion cases
  (`reported-cost-cases.json`) and the currency table from the platform's own `to_micros`,
  `pin_currency` and `minor_units`. To regenerate after a deliberate change, run that module with
  `UBB_WRITE_CODEGEN_FIXTURES=1`, then `pnpm test:update` here and read the diff.
- **The snapshots** under `tests/__snapshots__/<branch>/` are the files exactly as rendered.

## Running it

From the git root:

```
pnpm --dir apps/codegen typecheck   # generates the Blueprint's types, then tsc -b
pnpm --dir apps/codegen lint
pnpm --dir apps/codegen test
```

The tests compile and run the Python they render, so they need a Python interpreter with the SDK's
dependencies installed (`pip install -e ./ubb-sdk`). The SDK itself is taken from this checkout.
`UBB_CODEGEN_PYTHON` names the interpreter; unset, it is `python`. There is no skip: without one,
the tests fail.

CI runs all three in the `contract` job on every push and pull request, and
`tests/contracts/test_the_renderer_suite_is_enforced.py` holds the steps to being unconditional.

Decisions and their reasons: `docs/adr/0016-generated-integration-code-is-a-module-and-value-free-call-sites.md`.
