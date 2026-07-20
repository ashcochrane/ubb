# Spec-as-truth toolchain for Django Ninja (wayfinder #61)

**Date:** 2026-07-20 · **Status:** research (feeds a decision session — no decision is made here)
**Question:** twelve NinjaAPI mounts under `/api/v1/*` each generate their own OpenAPI document at
runtime; none is checked in, none is CI-enforced. What toolchain would make ONE versioned OpenAPI
spec the single source of truth — and can generated clients live up to the hand-built SDK and the
React UI?

---

## What the evidence favours (recommendation-shaped summary)

**A two-step path: merge-then-gate now, single-API refactor as the follow-up.** Nothing found
argues for waiting, and one prior blocker turned out to be already gone.

1. **Make the artifact exist first (post-hoc merge, Option B).** Ninja's
   `manage.py export_openapi_schema --api <dotted> --sorted` exports each mount offline; a
   small owned management command merges the twelve dicts and — unlike Ninja itself, whose
   source carries literal `TODO: check if unique` comments on both component schemas and
   security schemes — **fails loudly on name collisions**. Commit the merged document; CI
   regenerates and `git diff --exit-code`s it. This touches zero runtime behaviour and can land
   this week. (Redocly `join` exists but is officially "experimental".)
2. **Gate breaking changes with oasdiff** (`breaking --fail-on ERR` + the official GitHub
   Action): Apache-2.0, weekly releases, 207 checks, OpenAPI 3.1 GA — the only gate that
   matches Ninja's 3.1.0 output. Optic is dead (archived, absorbed into Atlassian); Java
   openapi-diff has no 3.1. Optional third leg: schemathesis v4 in-process under pytest-django
   (`from_wsgi`, no server) to catch the app lying about the spec — no first-party
   django-ninja recipe exists, so budget assembly time.
3. **Then do the single-`NinjaAPI` refactor (Option A) as the structural end-state** — Ninja
   1.6.0's "Idempotent Routers" (routers mountable on multiple APIs, per-mount auth/tags)
   removed the historical blocker and allows a gradual, both-shapes-live migration. Two
   prerequisites either way: rename the **seven duplicated Schema class names** (silent
   overwrite hazard in any unification) and sweep `reverse()` namespaces. Landing A deletes
   the merge script from step 1.
4. **TypeScript: finish what the UI branch already started.** `feat/ubb-ui-dashboard` already
   uses openapi-typescript 7 + openapi-fetch + TanStack Query and has an `api:check` drift
   script — extend it from five mounts to the one committed artifact (offline, no dev server),
   wire `--check` into CI, and optionally add openapi-react-query (1 kB) or orval (if generated
   TanStack hooks + MSW mocks are wanted). openapi-generator's TS variants are disqualified
   (no union-type support).
5. **Python: pin the hand-built SDK to the spec rather than replace it.** No OSS generator
   reproduces `ubb-sdk`'s value layer (exception hierarchy, retry policy, stop-verdict
   semantics, webhook HMAC) — and the commercial one that does (Stainless) stopped taking
   customers after the Anthropic acquisition. Either wrap a generated attrs/httpx core
   (openapi-python-client — 3.1-capable, active) under the existing ergonomics, or cheaper:
   CI-contract-test `ubb-sdk` against the committed spec. Precondition for *any* typed-error
   payoff: declare error Schemas — today 26 declarations type 4xx responses as bare `dict`.
6. **Put the 31 webhook event payloads in the same document** via OpenAPI 3.1's `webhooks`
   keyword through `NinjaAPI(openapi_extra=...)` (verified merge path in Ninja source) — the
   catalog/schemas drift class of bug becomes a diffable, gateable change. Redoc renders it;
   don't expect client codegen to consume it yet.
7. **Deprecation levers**: per-operation `deprecated=True` (Ninja supports it natively) +
   `Deprecation` (RFC 9745, now a Proposed Standard, `@<unix-ts>` format) and `Sunset`
   (RFC 8594) headers from a tiny middleware driven off the same metadata.

Honest trade-offs: the merge script is a custom artifact to own until Option A lands; the
twelve runtime documents remain the operational truth during step 1 (the committed artifact is
one step removed); oasdiff's 3.1 support has two known gaps (`$dynamicRef`,
`components.pathItems` — neither used here); openapi-python-client is still 0.x with breaking
minors; and the single-API refactor changes `reverse()` wiring and produces one shared docs UI,
which is a product decision (one public doc surface) as much as a technical one.

---

## Repo ground truth (verified in this worktree, branch of origin/main)

- **Twelve NinjaAPI instances**, all mounted in `ubb-platform/config/urls.py`: `me_api`,
  `tenant_api`, `sandbox_api`, `metering_api`, `billing_api`, `subscriptions_api`, `margin_api`,
  `referrals_api`, `webhook_api` (webhook *config* CRUD), `platform_api`, `connect_api`, and the
  root `api`. Each is constructed with its own `urls_namespace` (`ubb_metering_v1`, …). Eleven use
  `auth=ApiKeyAuth()`; `me_api` uses `auth=WidgetJWTAuth()` — both classes subclass Ninja's
  `HttpBearer` (`core/auth.py`, `core/widget_auth.py`), so both emit `{type: http, scheme:
  bearer}` security schemes under distinct names. None sets `title`, `version`,
  `servers`, or `docs_url` — so every mount serves a default Swagger UI at
  `/api/v1/<ns>/docs` and a document titled "NinjaAPI 1.0.0" at `/api/v1/<ns>/openapi.json`.
- **Pinned Ninja:** `requirements.txt` says `django-ninja>=1.3`; `requirements.lock.txt` pins
  **django-ninja==1.6.2** (with pydantic 2.13.4, Django 6.0). Facts below about Ninja behaviour
  were verified directly against the installed 1.6.2 source in `ubb-platform/.venv`.
- **Response typing is uneven** (~115 endpoints across the twelve mounts): 56 declare a single
  response Schema, 30 declare a per-status dict (`response={201: CustomerResponse, 409: dict,
  422: dict}`), and ~29 declare nothing. **26 of the 30 multi-status declarations type at least
  one status as bare `dict`** — almost always the 4xx branch. Whatever codegen is chosen, error
  responses are currently *undocumented free-form objects* in the generated schema; typed error
  models in a generated client require first declaring error Schemas in the app.
- **Seven Schema class names are defined twice** in different API modules (`BalanceResponse`,
  `TenantInvoiceOut`, `TenantInvoiceListResponse`, `TenantBillingPeriodOut`,
  `TenantBillingPeriodListResponse`, `SubscriptionInvoiceOut`, `UsageInvoiceOut` — e.g.
  `BalanceResponse` in both `api/v1/me_endpoints.py` and `api/v1/schemas.py`). This is the
  concrete collision hazard for any unification (see Leg 1).
- **No per-API customisation to migrate:** grep finds no `api.exception_handler`, custom parser,
  or renderer registered on any of the twelve instances — consolidation is cleaner than feared.
- **Hand-built Python SDK** (`ubb-sdk/ubb/`): sync httpx transport, frozen dataclasses in
  `types.py` (incl. a generic cursor-style `PaginatedResponse[T]` with `data`/`next_cursor`/
  `has_more`), a real exception hierarchy in `exceptions.py` (`UBBError` → `UBBAuthError`,
  `UBBAPIError` (+`retry_after`), `UBBValidationError`, `UBBConnectionError`, `UBBConflictError`,
  `UBBStoppedError` for the one-rule stop verdict, `UBBWebhookVerificationError`), retry with
  exponential backoff + jitter + Retry-After handling in `retry.py`, and HMAC webhook signature
  verification (`X-UBB-Signature-V2`, timestamp tolerance) in `webhooks.py`. This is the bar
  codegen has to clear — or be wrapped under.
- **The UI already prototypes the whole Leg-4 pattern** on branch `origin/feat/ubb-ui-dashboard`
  (`ubb-ui/`): React 19 + TanStack Query 5.90 + TanStack Router 1.166, **openapi-typescript
  7.13** + **openapi-fetch 0.17**, MSW mocks. `scripts/generate-api.sh` curls
  `/api/v1/{ns}/openapi.json` from a *running dev server* for five of the twelve mounts
  (`platform`, `metering`, `billing`, `tenant`, `me`), strips the mount prefix (baseUrl carries
  it), commits the JSON snapshots + generated `.ts`, and `package.json` has
  `api:check = regen && git diff --exit-code src/api/schemas src/api/generated` — the drift gate
  already exists in embryo, minus CI wiring, minus seven mounts, and with a live-server
  dependency that `manage.py export_openapi_schema` would remove.
- **Webhook event catalog:** `apps/platform/events/catalog.py` lists **31**
  webhook-deliverable event types; `apps/platform/events/schemas.py` holds frozen payload
  dataclasses — 32 classes = all 31 catalog types plus internal-only `customer.deleted`.
  Currently aligned (after one past drift incident), but nothing generates a public artifact
  from them: tenants get no machine-readable payload contract at all today.

## Leg 1 — One spec from twelve mounts

### What Ninja 1.6.2 gives you natively (verified in source, installed copy + GitHub)

- **Maintenance**: v1.6.2 published 2026-03-18 (v1.6.0 2026-03-12, v1.5.3 2026-01-10) —
  active, steady cadence ([releases](https://github.com/vitalik/django-ninja/releases),
  dates cross-checked on [PyPI](https://pypi.org/project/django-ninja/#history)). The lock file
  already pins the latest release.
- **`api.get_openapi_schema(*, path_prefix=None, path_params=None)`** is public and returns
  `OpenAPISchema`, a **`dict` subclass**; the document is **OpenAPI 3.1.0**
  ([ninja/openapi/schema.py](https://github.com/vitalik/django-ninja/blob/master/ninja/openapi/schema.py)).
- **`manage.py export_openapi_schema`** exports offline (no server): `--api <dotted.path>`,
  `--output`, `--indent`, `--sorted`, `--ensure-ascii`. Auto-detection only works for an API
  mounted at exactly `/api/` — this repo's mounts always need `--api`, and the command does ONE
  instance per invocation ([source](https://github.com/vitalik/django-ninja/blob/master/ninja/management/commands/export_openapi_schema.py),
  [#1302](https://github.com/vitalik/django-ninja/issues/1302)).
- **operationId** = `(module + "_" + view_func_name).replace(".", "_")`, overridable per
  operation. On collision Ninja only prints a stderr warning and writes the duplicate anyway
  ([ninja/main.py](https://github.com/vitalik/django-ninja/blob/master/ninja/main.py),
  [schema.py](https://github.com/vitalik/django-ninja/blob/master/ninja/openapi/schema.py)).
  Because IDs embed the module path, the twelve mounts' IDs are near-guaranteed unique — but
  nothing *enforces* it.
- **securitySchemes**: scheme name = the auth class's `__name__`, body from `openapi_*` attrs
  (`APIKeyHeader` → `{"type": "apiKey", "in": "header", "name": <param_name>}`, `HttpBearer` →
  `{"type": "http", "scheme": "bearer"}`). The source carries a literal `# TODO: check if
  unique` — same-name schemes **silently overwrite**. For this repo that is benign: eleven
  mounts share the one `ApiKeyAuth` class (identical name + body → merges cleanly) and
  `WidgetJWTAuth` is distinct. The hazard is only two *different* classes sharing a name.
- **Per-operation `deprecated=True`** renders into the document (operation.py / schema.py, and
  [docs](https://django-ninja.dev/reference/operations-parameters/)).
- **`openapi_extra` on NinjaAPI merges arbitrary top-level keys** into the emitted document
  (`for k, v in api.openapi_extra.items(): if k not in self: self[k] = v`) — the door for a
  `webhooks` section (side-note B). `title`, `version`, `description`, `servers` also exist —
  all currently left at defaults in this repo.

### Option A — refactor to one NinjaAPI + `add_router`

**Ninja 1.6.0 removed the historical blocker**: "Idempotent Routers — Routers are now reusable
and can be mounted to multiple APIs or multiple times within the same API", with per-mount
auth/tags/throttle isolation ([v1.6.0 release notes](https://github.com/vitalik/django-ninja/releases/tag/v1.6.0));
the old one-API-per-router `ConfigError` is gone. That enables a **gradual** migration: convert
each product's `NinjaAPI` into a `Router`, mount all twelve on one versioned
`NinjaAPI(title="UBB API", version=...)` with per-router `auth=` (the 11/1 ApiKey/JWT split maps
directly) and per-router `tags=` — while temporarily leaving the old per-product mounts alive,
since 1.6 allows a router on multiple APIs simultaneously.

What breaks / must be handled (all verified against ninja/main.py):

1. **`reverse()` namespaces**: twelve `urls_namespace`s collapse to one; every
   reverse-by-namespace call must be updated, and same-named URL names across products now
   shadow each other — 1.6's `url_name_prefix` on `add_router` exists precisely for this.
2. **Component schema names**: Ninja names `components.schemas` entries after the Schema class
   name, and the source admits `# TODO: check if schema["definitions"] are unique` — duplicates
   **silently overwrite**. This repo has seven duplicated class names (ground truth above), so
   the refactor requires renaming/merging those seven pairs first (or the document will quietly
   document the wrong shape for one of each pair).
3. **Per-instance config unifies**: one docs UI, one `/openapi.json`, one exception-handler set,
   one renderer/parser, one title/version. This repo registers no custom handlers/parsers, so
   the real work is (1) and (2).

### Option B — post-hoc programmatic merge of twelve documents

- Each `get_openapi_schema()` is a plain dict → a ~50-line Python management command can union
  `paths` (mount-prefixed via `path_prefix`), `components.schemas`, `components.securitySchemes`
  and write one document. Collision surfaces are exactly: schema names (the same seven
  duplicates — but a merge script can *detect and fail* rather than silently overwrite, which
  is better than Ninja's own in-API behaviour), operationIds (module-prefixed, near-safe), tags,
  and securityScheme names (safe here).
- **Redocly CLI `join`** ([docs](https://redocly.com/docs/cli/commands/join)) merges "OpenAPI
  3.x" files, disambiguating collisions via `--prefix-components-with-info-prop` /
  `--prefix-tags-with-*` options — but Redocly labels join "**an experimental feature … may go
  through major changes**" (their warning, verbatim). Redocly CLI itself is MIT, very active
  (v2.39.0, 2026-07-13; supports 3.0/3.1/3.2) ([repo](https://github.com/Redocly/redocly-cli)).
- **openapi-merge-cli** ([repo](https://github.com/robertmassaioli/openapi-merge)) offers
  per-input dispute prefixes but historically targeted OpenAPI 3.0; its 3.1 support is
  **unverified** — a risky bet given Ninja emits 3.1.

**Trade-off honestly stated**: Option B is a day of work and touches zero runtime behaviour
(URLs, namespaces, auth all stay); its cost is a custom script to own forever and twelve
runtime documents that remain the operational truth (the merged artifact is one step removed).
Option A is the structurally honest end-state (one runtime document, one docs UI, one
title/version — the thing tenants integrate against actually exists at one URL) but requires
the namespace/url_name sweep and the seven schema renames, and it changes production URL
wiring. The 1.6 idempotent-router change makes A cheap enough to do incrementally — B first as
the artifact for CI, A as the follow-up that deletes the merge script, is a coherent sequence.

## Leg 2 — CI enforcement: making the checked-in spec the truth

### The drift gate (generate-and-diff)

The standard recipe, confirmed across sources: regenerate the spec deterministically in CI,
compare to the committed file, fail on mismatch.

- Ninja ships the offline generator: `manage.py export_openapi_schema` with `--api <dotted.path>`,
  `--output`, `--indent`, `--sorted` (passes `sort_keys` to `json.dumps`), `--ensure-ascii`
  ([source](https://github.com/vitalik/django-ninja/blob/master/ninja/management/commands/export_openapi_schema.py),
  verified against the installed 1.6.2 copy in `.venv`). No dev server needed — unlike the UI
  branch's current curl-based `generate-api.sh`.
- Pitfalls reported in the wild, all avoidable here: key-order nondeterminism (always export
  `--sorted` with fixed `--indent`); the command auto-resolves only an API mounted at `/api/`,
  so with this repo's mounts `--api` must always be passed explicitly
  ([ninja #1302](https://github.com/vitalik/django-ninja/issues/1302)); environment-dependent
  `servers` blocks leaking into the artifact; operationId churn breaking downstream clients
  (pin ID generation, don't post-process).

### The breaking-change gate

- **oasdiff — the evidence favourite.** Go CLI, Apache-2.0 (LICENSE unchanged since 2021 — the
  Tufin→independent-org move was organizational, not legal; oasdiff.com is an open-core hosted
  layer on top). Active: v1.23.0 released 2026-07-10 on a weekly cadence, ~1.3k stars
  ([releases](https://github.com/oasdiff/oasdiff/releases)). `oasdiff breaking --fail-on
  ERR|WARN|INFO` exits 1 at/above the chosen severity; 207 documented checks; suppression files
  for accepted breaks ([docs](https://github.com/oasdiff/oasdiff/blob/main/docs/BREAKING-CHANGES.md)).
  **Official GitHub Action** ([oasdiff/oasdiff-action](https://github.com/oasdiff/oasdiff-action),
  v0.1.6 2026-07-10) with `breaking` (PR comments + `fail-on`), `changelog`, `diff`
  (`fail-on-diff` — usable as the drift gate itself), `validate`. **OpenAPI 3.1 GA since
  v1.15.0** (matters — Ninja 1.x emits 3.1.0); known gaps: `$dynamicRef` unresolved,
  `components.pathItems` dropped ([OPENAPI-31.md](https://github.com/oasdiff/oasdiff/blob/main/docs/OPENAPI-31.md)).
- **OpenAPITools/openapi-diff** (Java): alive but slow (2.1.7, 2026-01-26); **3.0 only — 3.1 is
  an open discussion** ([#380](https://github.com/OpenAPITools/openapi-diff/discussions/380));
  JVM dependency in CI. Weaker fit.
- **Optic**: **dead** — repo archived 2026-01-12, "Optic Labs is now part of Atlassian"
  ([repo](https://github.com/opticdev/optic)). Do not adopt.
- **pb33f openapi-changes** ([repo](https://github.com/pb33f/openapi-changes), v0.2.10
  2026-07-01, Apache-2.0, supports 3.0/3.1/3.2, git-native): good human-readable
  changelog/HTML reports as a *supplement*; oasdiff has the richer gating rule set.

### Contract tests against the running app

- **schemathesis**: v4.24.0 released 2026-07-19 ([PyPI](https://pypi.org/project/schemathesis/)),
  MIT, 3.5k stars, README users incl. Spotify/WordPress/JetBrains/Red Hat. Property-based tests
  from the schema (5xx, response-conformance, validation-bypass, stateful checks). Runs
  **in-process** with no live server: `schemathesis.openapi.from_wsgi("/api/v1/...openapi.json",
  app)` + `@schema.parametrize()` under pytest
  ([guide](https://schemathesis.readthedocs.io/en/stable/guides/python-apps/)) — Django's
  `get_wsgi_application()` is plain WSGI and Django motivated the WSGI support
  ([#31](https://github.com/schemathesis/schemathesis/issues/31)), but **no first-party
  django-ninja example exists** — the pytest-django recipe would be assembled here. OpenAPI 3.1
  supported. Note: schemathesis is *not* a drift gate — it never compares two spec files; it
  catches the implementation lying about the spec. Complement, not substitute.

### Prior art for "the spec is a generated, checked-in artifact"

- **Zalando guidelines**: API-first MUSTs — spec before code, single self-contained document,
  no compatibility breaks ([rules #100/#101/#192/#106](https://opensource.zalando.com/restful-api-guidelines/)).
- **Stripe** ([stripe/openapi](https://github.com/stripe/openapi)): committed spec generated by
  a closed-source generator, updated near-continuously (v2344 on 2026-07-15), never hand-edited.
- **GitHub** ([github/rest-api-description](https://github.com/github/rest-api-description)):
  auto-updated from the source of truth that also powers contract tests; **PRs editing the spec
  directly are refused** — the generator owns the file.
- FastAPI's own docs show export-then-preprocess before client generation
  ([generate-clients](https://fastapi.tiangolo.com/advanced/generate-clients/)); the
  commit-and-verify vs CI-artifact vs auto-commit trade-off is laid out in
  [Doctave's guide](https://www.doctave.com/blog/python-export-fastapi-openapi-spec).

## Leg 3 — Codegen quality, Python: can it match `ubb-sdk`?

Short answer: **not head-on — but it doesn't need to.** Neither OSS generator produces the
ergonomic layer that is `ubb-sdk`'s actual value (exception hierarchy, retry policy, stop-verdict
semantics, webhook HMAC); both can produce the *transport + DTO* layer underneath it.

### openapi-python-client (the natural fit for this stack)

- **Maturity**: v0.29.0 (2026-05-30), roughly monthly-to-quarterly cadence, ~2k stars, active —
  but still **0.x**, and minor versions carry breaks (0.29.0 dropped Py3.10)
  ([releases](https://github.com/openapi-generators/openapi-python-client/releases)).
- **Output style**: models are **attrs classes** (`@_attrs_define`), *not* dataclasses — close
  in spirit to the SDK's frozen dataclasses but not identical
  ([model template](https://github.com/openapi-generators/openapi-python-client/blob/main/openapi_python_client/templates/model.py.jinja)).
  **httpx, sync + async both generated**: each operation gets `sync` / `sync_detailed` /
  `asyncio` / `asyncio_detailed`, modules grouped by OpenAPI tag. (The hand-built SDK is
  sync-only httpx — codegen would add async for free.)
- **Error responses**: no exception hierarchy. Documented 4xx schemas become **typed models
  returned in a Union**; only *undocumented* statuses raise, via `errors.UnexpectedStatus`
  when `raise_on_unexpected_status=True`
  ([endpoint template](https://github.com/openapi-generators/openapi-python-client/blob/main/openapi_python_client/templates/endpoint_module.py.jinja),
  [errors template](https://github.com/openapi-generators/openapi-python-client/blob/main/openapi_python_client/templates/errors.py.jinja)).
  The `UBBError` hierarchy stays hand-written on top. NB: this repo's 4xx responses are mostly
  bare `dict` today (ground truth) — the generated error Unions would be `Any`-shaped until the
  app declares error Schemas.
- **Enums**: Python `Enum` by default, `literal_enums: true` for `Literal[...]`; 3.1 `const` →
  `Literal`. No unknown-member-tolerant "open enum" mode found (absence-of-docs verification).
- **Templates**: `--custom-template-path` is full Jinja override (plus `post_hooks`,
  `class_overrides`) but the README calls it "a beta-level feature… undocumented and unstable"
  ([README](https://github.com/openapi-generators/openapi-python-client)).
- **OpenAPI 3.1 supported** since v0.17.0 (matters: Ninja emits 3.1.0)
  ([CHANGELOG](https://github.com/openapi-generators/openapi-python-client/blob/main/CHANGELOG.md)).

### openapi-generator (python)

- v7.24.0 (2026-07-20), monthly cadence
  ([releases](https://github.com/OpenAPITools/openapi-generator/releases)). The `python`
  generator is STABLE: pydantic-v2 models, urllib3 default (asyncio/httpx selectable), heavier
  deps (pycryptodome, pem)
  ([generator docs](https://openapi-generator.tech/docs/generators/python/),
  [sample requirements](https://github.com/OpenAPITools/openapi-generator/blob/master/samples/openapi3/client/petstore/python/requirements.txt)).
- **It does generate an exception hierarchy** — `ApiException.from_response()` maps
  400/401/403/404/409/422/5xx to typed exception subclasses
  ([sample exceptions.py](https://github.com/OpenAPITools/openapi-generator/blob/master/samples/openapi3/client/petstore/python/petstore_api/exceptions.py))
  — the closest analogue to `UBBError`, though status-generic (declared 4xx schemas aren't
  deserialized into the exception).
- **Enums are closed and raise `ValueError` on unknown values** in pydantic validators
  ([sample model](https://github.com/OpenAPITools/openapi-generator/blob/master/samples/openapi3/client/petstore/python/petstore_api/models/pet.py))
  — a server-side enum addition breaks deployed clients until regen. Bad property for a
  billing API that evolves additively.
- **3.1 is still partial**: the umbrella issue
  [#14943](https://github.com/OpenAPITools/openapi-generator/issues/14943) remains open; no
  formal "3.1 supported" statement. Risky against Ninja's 3.1 output.

### The wrap-the-generated-core pattern (what the industry actually does)

- FastAPI's official docs describe exactly this: export → preprocess operationIds → generate →
  wrap ([generate-clients](https://fastapi.tiangolo.com/advanced/generate-clients/)).
- openapi-python-client's generated client exposes the seams for the wrap: `httpx_args`, event
  hooks, `get_httpx_client()` / `set_httpx_client()` — retry policy arrives as an
  `httpx.HTTPTransport(retries=…)` or event hooks you inject (retries were explicitly punted to
  client customization — [#118](https://github.com/openapi-generators/openapi-python-client/issues/118)).
  **Pagination helpers, webhook HMAC verification, and exception mapping are generated by
  neither OSS tool** — they remain the hand-written thin layer, i.e. exactly the parts of
  `ubb-sdk` worth keeping (`retry.py`, `webhooks.py`, `exceptions.py`, `PaginatedResponse`
  iteration).
- The commercial benchmark: OpenAI's Python SDK is "generated from our OpenAPI specification
  with Stainless" *including* retries, auto-pagination, typed errors
  ([openai-python README](https://github.com/openai/openai-python)); Anthropic's SDK likewise
  carries Stainless generation stamps
  ([_client.py](https://github.com/anthropics/anthropic-sdk-python/blob/main/src/anthropic/_client.py)).
  But **Stainless was acquired by Anthropic 2026-05-18 and its hosted SDK generator is winding
  down — no new signups** ([announcement](https://www.anthropic.com/news/anthropic-acquires-stainless)).
  Remaining commercial options: **Speakeasy** (free ≤250 ops/language; Business $720/mo/language
  — [pricing](https://www.speakeasy.com/pricing)) and **Fern** (Apache-2.0 CLI + paid hosted
  platform — [repo](https://github.com/fern-api/fern)).
- **Verdict for this repo**: a generated core cannot express `UBBStoppedError`'s one-rule
  semantics (a stop verdict riding a 200) or the micros validation — those are domain, not
  transport. The realistic end-state is *contract-locked, not generated*: keep `ubb-sdk` as the
  ergonomic layer, and use the spec to **pin it** — either wrap a generated attrs/httpx core
  beneath it, or (cheaper) contract-test the existing SDK's dataclasses/paths against the
  checked-in spec in CI so SDK drift fails the build the same way UI drift does.

## Leg 4 — Codegen quality, TypeScript: what the UI consumes

The UI branch already chose the front-runner stack (ground truth above), so Leg 4 is mostly
"finish what's started":

- **openapi-typescript** v7.13.0: **types only, zero runtime**, OpenAPI 3.0+3.1
  ([openapi-ts.dev](https://openapi-ts.dev/introduction)). Companions: **openapi-fetch** v0.17.0
  (~6 kB typed fetch client — already in `ubb-ui/package.json`) and **openapi-react-query**
  v0.5.4 (1 kB `useQuery`/`useMutation`/`useSuspenseQuery`/`useInfiniteQuery` + `queryOptions`,
  peer `@tanstack/react-query ^5.80` — matches the UI's 5.90)
  ([docs](https://openapi-ts.dev/openapi-react-query/)). `queryOptions` composes with TanStack
  Router loaders' `ensureQueryData` (inference from both APIs' shapes, not a doc claim). Both
  companions are 0.x.
- **orval** v8.22.0 (2026-07-14, 6.3k stars, MIT, active): generates TanStack Query hooks
  directly, plus axios/fetch clients, **Zod schemas**, **MSW mocks** with Faker
  ([orval.dev](https://orval.dev/), [repo](https://github.com/orval-labs/orval)). Heavier but
  richer: the MSW-mock generation is genuinely attractive since the UI already uses MSW. The
  trade-off vs openapi-react-query is generated-hook surface area vs a 1 kB wrapper over
  hand-rolled query options.
- **openapi-generator TS variants**: `typescript-fetch` docs admit **no
  `allOf`/`anyOf`/`oneOf`/union support**
  ([docs](https://openapi-generator.tech/docs/generators/typescript-fetch/)) — disqualifying
  for a modern TS SPA against a 3.1 spec.
- **Drift protection**: openapi-typescript ships a first-class **`--check` flag** ("check that
  the generated types are up-to-date") purpose-built for CI
  ([CLI docs](https://openapi-ts.dev/cli)); the generic fallback is the UI branch's existing
  `api:check` = regen + `git diff --exit-code`. Either way the mechanism is the same: spec
  changes regenerate `schema.ts`, and any incompatibility surfaces as ordinary `tsc` errors in
  UI code — the compiler is the enforcement.

What changes with a unified spec: `generate-api.sh` stops curling five separate
`openapi.json`s from a live dev server and stripping prefixes; it consumes the one committed
artifact offline (via `export_openapi_schema` output), covers all twelve mounts instead of
five, and the prefix-stripping hack disappears if the client's `baseUrl` is `/` (or stays,
applied once).

## Side-note A — OpenAPI-native versioning/deprecation levers

- **`deprecated: true`** exists at three levels of the 3.1.0 spec
  ([spec](https://spec.openapis.org/oas/v3.1.0.html)): Operation ("Consumers SHOULD refrain
  from usage"), Parameter ("SHOULD be transitioned out of usage"), and Schema property (via
  JSON Schema 2020-12 §9.3 — "MAY mean the property is going to be removed in the future",
  [json-schema.org](https://json-schema.org/draft/2020-12/json-schema-validation)). Ninja
  exposes the operation-level flag directly (`@api.get(..., deprecated=True)`); parameter/schema
  levels flow through pydantic field config or `openapi_extra`.
- **Sunset header — RFC 8594** (Informational, 2019): `Sunset: <HTTP-date>` announces when a
  resource is expected to become unresponsive; a hint, not a guarantee; pairs with a `sunset`
  link relation for migration docs ([RFC 8594](https://www.rfc-editor.org/rfc/rfc8594)).
- **Deprecation header — RFC 9745 is now a published Proposed Standard** (2025 — it graduated
  from draft-ietf-httpapi-deprecation-header): value is a Structured-Fields **Date**, e.g.
  `Deprecation: @1688169599` (unix timestamp, *not* an HTTP-date); a past date means already
  deprecated; Sunset MUST NOT be earlier than Deprecation
  ([RFC 9745](https://www.rfc-editor.org/rfc/rfc9745)).
- Ninja has no built-in for either header — a small middleware/decorator driven off the same
  metadata that sets `deprecated: true` would keep document and wire behaviour in lockstep.
  oasdiff, for what it's worth, treats removing a *deprecated-with-sunset* operation more
  leniently in its breaking rules — deprecation-in-spec is machine-enforceable, prose isn't.

## Side-note B — outbound webhook events via the OpenAPI 3.1 `webhooks` keyword

- The 3.1 top-level `webhooks` keyword is a map of name → Path Item describing "requests
  initiated other than by an API call" that the consumer MAY implement — exactly the outbound
  tenant-webhook case. A document is valid with *only* webhooks (paths is not required)
  ([spec](https://spec.openapis.org/oas/v3.1.0.html)).
- Fit for this repo: the 31 catalog types → 31 named webhook entries, each referencing a payload
  schema in `components.schemas`. The payload dataclasses in
  `apps/platform/events/schemas.py` are frozen, additive-only dataclasses — mechanically
  convertible to JSON Schema (`dataclasses.fields()` walk, or mirror as pydantic models). A
  small generator plus `NinjaAPI(openapi_extra={"webhooks": ...})` (verified: `openapi_extra`
  merges top-level keys into the emitted document) puts the event contract *in the same
  CI-gated artifact* — the catalog/schemas drift that already happened once becomes a diffable,
  gateable change. It also closes today's gap that tenants get **no machine-readable payload
  contract at all** for webhooks.
- Tooling reality check: Redoc renders `webhooks` natively — "Redocly renders the webhook in
  the sidebar navigation with a badge named 'Event'"
  ([reference](https://redocly.com/learn/openapi/openapi-visual-reference/webhooks)); Swagger UI
  v5 renders them but has had webhook-specific rendering bugs (e.g. examples pulled from the
  wrong place — [#9937](https://github.com/swagger-api/swagger-ui/issues/9937), closed). Codegen
  consumption of `webhooks` is uneven and largely unverified — openapi-generator's 3.1 umbrella
  issue [#14943](https://github.com/OpenAPITools/openapi-generator/issues/14943) is still open —
  but types-only TS generation types the referenced schemas regardless. So: put webhooks in the
  document for docs + diff-gating value; do not count on client codegen consuming them yet.

---

## Method note

Researched 2026-07-20 against primary sources: tool repos/docs/release pages and RFCs fetched
live (URLs inline above); Django Ninja behaviour verified directly against the installed
django-ninja 1.6.2 source in `ubb-platform/.venv` (openapi/schema.py, main.py, router.py,
security/, management/commands/export_openapi_schema.py); repo claims verified against this
worktree (branched from origin/main) plus `origin/feat/ubb-ui-dashboard` for the UI facts.
Claims that could not be fully verified are flagged inline (openapi-merge-cli 3.1 support,
per-generator `webhooks` codegen coverage, openapi-python-client's lack of an open-enum mode,
the openapi-react-query ↔ TanStack Router pairing inference).
