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
throws `BlueprintNotRenderable` for a document it cannot read — an unknown `schema_version` or
`renderer_contract_version`, a target with no renderer, an SDK major or an operation it is not
written for, or a token that breaks what the contract promises. ADR-0016 §7 and ADR-0017 §8 have
the lists.

## What an artifact is

A Blueprint is resolved for one target, and `render` writes that target's files.

For the `python_sdk` target (SDK v3):

| `kind` | `path` | What it is |
|---|---|---|
| `module` | `ubb_integration.py` | Every value the Blueprint resolved that running code needs. Dropped in, never edited, replaced whole on regeneration. |
| `call_site` | `call_sites/<name>.py` | One block per place a tenant's own code calls the module. **No generated value appears in one**: no string, number or bytes literal, only names. |
| `environment_example` | `.env.example` | `UBB_API_KEY=` and `UBB_BASE_URL=`, with nothing after the equals sign. Both are required: the renderer holds no default host (ADR-0016 §8). |
| `verify_script` | `verify_integration.py` | Checks the declared paths against a response the tenant's supplier really returned. Calls nothing. Holds the declared paths, so it is replaced with the module. |

For the `shell_http` target — **Shell / raw HTTP, requires curl and jq** — the same four kinds and
one more:

| `kind` | `path` | What it is |
|---|---|---|
| `module` | `ubb_integration.sh` | A runnable POSIX shell file, written to be **sourced**. It sets no shell option, never calls `exit`, and every variable it holds is spelled `UBB_…` or `_ubb_…`. |
| `call_site` | `call_sites/<name>.sh` | The same rule: no quoted text but a variable's expansion, and no number. |
| `environment_example` | `.env.example` | The same two empty assignments. |
| `verify_script` | `verify_integration.sh` | The same checks, in one jq program. Needs jq and not curl. Run, not sourced. |
| `request_preview` | `request_previews/<function>.http` | One per call: the method, the URL, the headers and the body, for reading. **Documentation**: it is not run, carries no readiness verdict, and never stands in for the module, whose header is where the verdict is. |

### How a shell file is called

ADR-0017 has the reasons. In short:

- **A runtime value is a `name=value` argument**, under exactly the name the Blueprint gives:
  `ubb_record_chat_completion customer_id="$customer_id" idempotency_key="$key" task_id="$task_id" response=response.json searches=2`.
  One left out, passed empty, or not the call's is refused with `UBB_EXIT_USAGE` before anything is
  sent. Inside the file a parameter is `_ubb_p_<name>` in shell and `$p_<name>` in jq, so a parameter
  named `PATH`, `IFS` or `then` is none of the things those words already mean.
- **What a call leaves behind is in a variable**, because a shell function returns only a status:
  `UBB_TASK_ID` after a start, `UBB_RESPONSE` after any call (the next call overwrites it),
  `UBB_STOP_REQUESTED` after a stop. They are results the file sets, not settings, and none is
  exported. A call that can meet a stop clears `UBB_STOP_REQUESTED` before it does anything else,
  so a stop is never an earlier call's. A function of the file is never called inside `$( )` or a
  pipeline.
- **A stop is the status `UBB_EXIT_STOP_REQUESTED` (20)**, returned by the record that was answered
  with one, with the stop's metadata in `UBB_STOP_REQUESTED` as one line of JSON. `ubb_run_task`
  is the boundary: it logs the stop and returns 20, never 0 — whether or not the work it ran
  returned the stop's status. Every other failure has another status: a named `sysexits.h` value
  for the file's own refusals (`UBB_EXIT_USAGE`, `UBB_EXIT_VALUE_REFUSED`, …), or curl's own for a
  request that failed.
- **The file declares no outcome of its own.** Work that returns a failure is not declared
  `failed`: a shell status is not evidence of how the work went, and a failed Task cannot be
  reopened. Its status is passed on as it is, and a Task with no outcome declared is left open and
  said to be on standard error. `ubb_close_task outcome=failed …` is how a failure is declared.
  (The Python target does declare `failed` where an exception leaves the block; an exception is
  evidence a status is not.)
- **There is no path for work that has already happened.** The Python target renders
  `backfill_<name>`; this one renders nothing for a backlog in v1. A tenant with one uses the
  Python target.
- **A response a path is read off is a file**: `response=` is the path of a file holding the
  supplier's JSON.
- **A supplier's cost is text**, converted to whole micros on its digits with no arithmetic on the
  amount, and written into the body by the shell: it is never a jq number.

Every jq program is read by jq from standard input, from a quoted heredoc
(`jq … --from-file /dev/stdin <<'UBB_JQ'`), in a function that is nothing but that program
(`_ubb_jq_…`). **No heredoc is ever opened inside `$( )`**: bash 3.2, which macOS ships, reads a
heredoc there as shell, and one backtick in a declared name would end the file. That is also what
decided against the other form the decision left open — the program as an argument,
`jq "$(cat <<'UBB_JQ' … )"`, which is inside a substitution by construction. Both forms are kept
as scripts and run by the suite: `tests/harness/heredoc_from_standard_input.sh` and
`tests/harness/heredoc_as_an_argument.sh`, the second with the bash 3.2 transcript at its head.

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
JSON, by attribute for a Python object; a shell file reads JSON and nothing else), and
`amount_representation` (the value is a supplier's cost, converted to whole micros once).
`pricing_mode` chooses one sentence of comment. The shell target acts on one more, because a shell
argument is always text: `value_type` on a keyed entry says its value is a number.

On the shell target a one-segment token named for a place in the operation's route (`task_id` in
`/api/v1/tasks/{task_id}/close`) fills that place and is not a key of the body. The routes are
written down in `src/shell/plan.ts` and typed against the committed contract: one the contract no
longer publishes for that operation stops compiling.

The three binding classes are shapes. A `platform_known` token is a literal. A `runtime_bound`
token is a required parameter named exactly as the Blueprint names it: a keyword parameter in
Python, a `name=value` argument in shell. A `secret_reference` is read from the environment:
`os.environ[...]` in Python, `$UBB_API_KEY` handed to curl on standard input in shell. A literal
with no configured value is written as a call that raises, naming the token.

## Comments

Two classes and no third. **Provenance** is generated from the Blueprint in one form,
`<name> = <json>[ · <qualifier> <json>]...` (`src/comments.ts`). **Contract** is a line of the
renderer catalogue (`src/catalogue.ts`), written exactly as it stands there. The catalogue is
closed and versioned: `CATALOGUE_VERSION`, with the whole of it pinned in
`tests/__snapshots__/catalogue.v4.json` — a file named for the version, so a change under an
unchanged number is a diff a reviewer reads. It is one catalogue for both targets, so both state
its version: adding the shell target's members made it version 2 for Python's files too,
rewording the shell file's refusal of an old jq made it version 3 (#582), and replacing one
diagnostic code's remediation with another's made it version 4 (#571).
Its symbols (`UBB_API_KEY`, `UBB_BASE_URL`, `stop_requested`, `UBB_EXIT_STOP_REQUESTED` = 20, and
the other statuses and names a shell file is made of) are the renderer's own and are not registry
concepts.

## Where things come from

- **The Blueprint's type** is generated from `openapi/v1.json` into `src/generated/` by
  `pnpm contract:types` on every typecheck. It is not committed.
- **The fixtures** under `fixtures/` are written by the platform, not by hand:
  `ubb-platform/api/v1/tests/test_the_renderers_fixtures_are_what_the_platform_answers.py` declares
  configuration through the tenant's routes, resolves each Blueprint through its route, and holds
  the committed file equal to the answer. A Blueprint is resolved for a target, so each branch is
  committed twice: `<branch>.json` for Python and `shell-<branch>.json` for shell, with
  `shell-unreadable-shape.json` the one branch only shell has. The same module writes the
  conversion cases (`reported-cost-cases.json`) and the currency table from the platform's own
  `to_micros`, `pin_currency` and `minor_units`. Each case carries two answers: `expected` for the
  amount as the value it is, and `expected_as_text` for the same amount handed over as its text,
  which is all a shell file holds. To regenerate after a deliberate change, run that module with
  `UBB_WRITE_CODEGEN_FIXTURES=1`, then `pnpm test:update` here and read the diff.
- **The snapshots** under `tests/__snapshots__/<branch>/` are the files exactly as rendered.

## Running it

From the git root:

```
pnpm --dir apps/codegen typecheck   # generates the Blueprint's types, then tsc -b
pnpm --dir apps/codegen lint
pnpm --dir apps/codegen test
```

The tests run what they render, and there is no skip: a machine that cannot run a target's files
fails that target's tests.

- **Python.** A Python interpreter with the SDK's dependencies installed
  (`pip install -e ./ubb-sdk`). The SDK itself is taken from this checkout. `UBB_CODEGEN_PYTHON`
  names the interpreter; unset, it is `python`.
- **Shell.** A POSIX `sh`, `bash`, `curl` (with `--fail-with-body`) and `jq`, and the same Python
  to run the harness and stand where UBB would. Every shell file is parsed and run under both `sh`
  and `bash`. CI's runner has all four and runs them directly.

  On a machine without them — **Windows above all**, where a Git Bash and a native `jq.exe` are not
  what a generated file is ever run in — run the shell tests in a container:

  ```
  docker build -t ubb-codegen-shell apps/codegen/tests/harness
  UBB_CODEGEN_SHELL_IMAGE=ubb-codegen-shell pnpm --dir apps/codegen test
  ```

  The harness is the same file either way; set, the variable only says where it runs. That image
  is Debian stable (dash, bash 5.2, jq 1.6, curl 7.88) and CI's runner is Ubuntu (jq 1.7, curl 8),
  so between them the suite sees two generations of each tool.

CI runs all three in the `codegen` job on every push and pull request, and
`tests/contracts/test_the_renderer_suite_is_enforced.py` holds the steps to being unconditional.

## Run against the real application

This package's suite runs what it renders against a local stand-in. The execution suite at the
git root, `tests/code_builder_execution/` (#582, its own CI job `code-builder-execution`), runs it
against the real application instead: a Blueprint resolved through the platform's route, rendered
here, written to disk unpatched, run as a customer runs it, and its records asserted. It renders
through `scripts/render.ts`, which reads a Blueprint on standard input and prints exactly what
`render` returns (`tests/render-script.test.ts` holds it to that):

```
node --experimental-strip-types apps/codegen/scripts/render.ts < blueprint.json
```

It lives outside `src/` because it reads a stream, which nothing under `src/` may.

Decisions and their reasons:
`docs/adr/0016-generated-integration-code-is-a-module-and-value-free-call-sites.md` (the package
and the Python target) and
`docs/adr/0017-a-generated-shell-file-is-sourced-and-a-stop-is-a-status.md` (the shell target).
