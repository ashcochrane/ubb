ENGINEERING HANDOFF — CURRENT CODE SNAPSHOT — NOT ADMISSION EVIDENCE

# R10-ASH-HANDOFF — index and evidence record

A code-grounded engineering handoff for Ash, written from the current repository and executable evidence. It is
not W7, not a W7 preparation pass, and not admission evidence. **No product code was changed.** No PR was opened or
merged, the W7 brief was not edited, no launch input was filled, nothing touched production, and no settled
architecture decision was reopened.

| File | Read it for |
|---|---|
| `01-WHAT-UBB-IS-NOW.md` | the plain-English overview: what exists, how a client integrates, the end-to-end sequence, what changed conceptually, what is not in the first launch |
| `02-TECHNICAL-SYSTEM-MAP.md` | the detailed reference by subsystem with `path :: Symbol (lines)` citations, verification labels, the data-flow walkthroughs, and the one `HANDOFF DISCREPANCY` |
| `03-ASH-VALIDATION-AND-NEXT-STEPS.md` | where the programme stands, the safe local verification procedure, what is needed from Ash (inputs 1, 2, 3, 7), and the W7 sequence at a high level |

## Exact commit inspected

- `origin/main` = `1bf0c0ca772410fa5aa721f733736f5f83e66760` — "W7 readiness-fix PR (pre-FINAL): F1+F2 Celery
  wiring, F3 external wallet applicability, F5 Stripe fail-closed, F6 accumulator concurrency (#624)".
- Verified current by `git fetch origin main` + `git rev-parse origin/main` at **2026-11-02 14:34 NZST**.
- Inspected in a dedicated git worktree checked out at that exact commit
  (`.claude/worktrees/r10-ash-handoff-inspect`, branch `worktree-r10-ash-handoff-inspect`, never committed to).
  `git status` at the end: clean; the only untracked file was a gitignored `.env` copied in for local runs.
- Tags present and unchanged: `api-v1-cutover` and `sdk-v4.0.0` at `c2eb35ff`; `api-v1-launch` at `ac6ca816`.

## When

2026-11-02, 14:34–15:40 NZST (03:34–04:40 UTC), on the developer's Windows 11 machine (Docker 29.5.2, PostgreSQL
16.14 and Redis 7.4.9 containers, Python 3.13.14 virtualenv from `ubb-platform/requirements.lock.txt`).

## How the maps were made

Five read-only mapping passes (subagents) walked the tree by functional area (platform kernel and infrastructure;
metering; billing and controls; API, contracts, CI and tooling; SDK, Code Builder and console) and returned
citations with line numbers. I spot-checked their load-bearing claims by opening the files myself (the residual
"not postpaid?" sites, the logging configuration, the outbox backoff, the error-registry import, the lock file,
the console routes, `config/__init__.py`, the beat-schedule test body) and ran the commands below. Planning and
prep-pass documents (`R10-W7-DELIVERY-PROMPT.md`, `R10-W7-PREP/`, `R10-CONDUCTOR.md`, `R10-W7-INFRA-FACTS-CHECKLIST.md`)
were read for *why* and for the programme state, never as proof of implementation.

## Commands and tests actually run (all non-destructive; all against the worktree at `1bf0c0ca`)

| # | Command (from `ubb-platform/` unless stated) | Result |
|---|---|---|
| 1 | `git fetch origin main; git rev-parse origin/main` | `1bf0c0ca…` — anchor confirmed |
| 2 | `manage.py check` | System check identified no issues |
| 3 | `manage.py makemigrations --check --dry-run` **against the shared developer DB `ubb`** | **failed**: `InconsistentMigrationHistory: wallets.0001_initial is applied before its dependency work.0001_initial` — the developer database predates the W6 squash; expected and documented in `CLAUDE.md` ("drop and re-create"). Not a product defect. |
| 4 | `CREATE DATABASE ubb_ash_handoff` (fresh), then `manage.py migrate` | 44 migrations applied (26 project + 18 contrib) |
| 5 | `manage.py migrate` again | No migrations to apply |
| 6 | `manage.py makemigrations --check --dry-run` (fresh DB) | No changes detected |
| 7 | `scripts/export_openapi.py` then `git status -- openapi/` | 123 paths, 37 webhook event types written; **byte-identical** to the committed `openapi/v1.json`; SHA-256 `f9e2cabcc276be46bf28267b57f4cacb3be981de2a30e3cb8b55a4a680c89d92` = the SDK's `SPEC_SHA256` stamp |
| 8 | `python -m tools.gates` (repo root) | 27 gates, 27 installed and proven to run, 0 owed, 3 deferred obligations; migration ledger 0 entries; permanent exceptions 3 |
| 9 | `python -m tools.forbidden_terms` | retired terms on a living surface: 0 |
| 10 | `python -m tools.vocabulary --write` | 4 generated artefacts already up to date; tree still clean |
| 11 | `pytest apps/platform/tests/test_product_boundaries.py` | 11 passed |
| 12 | `pytest tests/contracts` (repo root; `DJANGO_SETTINGS_MODULE` unset) | 845 passed (4:37) |
| 13 | `pytest` in `ubb-sdk/` | 471 passed, 63 subtests (6:09); `ubb.__version__` 4.0.0, `__spec_revision__` as in #7 |
| 14 | `pytest apps/platform/tests/test_beat_schedule.py apps/billing/gating/tests/test_mode_pins.py api/v1/tests/test_webhooks.py apps/subscriptions/tests/test_webhook_endpoint.py apps/subscriptions/tests/test_handlers.py` (the F1/F2/F3/F5/F6 regression files) | 78 passed |
| 15 | `pytest api/v1/tests` (chunk A) | 2,384 passed, 685 subtests (7:28) |
| 16 | `pytest apps/platform core` (chunk B) | 1,725 passed, **1 failed** (see "Failures and uncertainties" §1), 951 subtests (2:06) |
| 17 | re-run of the one chunk-B failure after stopping my local worker | 1 passed |
| 18 | `pytest apps/billing apps/metering apps/subscriptions apps/referrals` (chunk C) | 2,275 passed, 3 skipped, 2,202 subtests (3:38) |
| 19 | Local stack: `manage.py runserver 127.0.0.1:8011 --noreload`, `celery -A config worker --pool=solo -l INFO`, `celery -A config beat -l INFO --schedule <tmp>` against `ubb_ash_handoff` and Redis index `/5` | `/api/v1/health` 200; `/api/v1/ready` `{"database":"ok","redis":"ok"}`; worker consumed the nine `ubb_*` queues and registered both F2 tasks; beat dispatched `sweep-outbox` every minute and `flush_api_key_last_used` at the 5-minute mark (the key's `last_used_at` became set) |
| 20 | Django-shell bootstrap: `Tenant(name=…).save()` (defaults `external`, `["metering"]`, `off`) + `TenantApiKey.create_key` | one tenant, one `ubb_live_` key; raw key and widget secret written only to the job's temporary directory, deleted at the end |
| 21 | Golden-path probe (SDK v4 + raw HTTP), 22 checks | **21 passed**; the 1 "failure" was my own script reading `event_id` instead of `id` on the usage-list items (confirmed by a raw read: the event is listed). Product-side every check passed: tenant config and no-rail status; customer created; provider, Event Type (draft → mapping → published rev 1), default markup 20%; usage ack `costing known 1,000,000 / pricing known 1,200,000 / margin_over_cost / stop false`, receipt schema 2 engine 3.0.0; replay same `event_id`; single-event read with `measurements_status available`; `/me/economics` `recorded_events {1, known}`, `customer_revenue {1,200,000, known}`; tenant key on `/me/economics` → 401; Task start → usage under it (`task_total_billed_cost_micros 600000`) → `complete()` → `GET /tasks/{id}` `completed`, `recorded_events 1`; webhook config with `http://127.0.0.1:9/hook` → 422 "must use https scheme", `https://localhost/hook` → 422; audit feed 10 records |
| 22 | Direct database reads after the probe | 3 postings (`metered_usage`, known/known, receipts with all ten top-level keys), 3 stop acknowledgements (`stop false`), task row `completed` with frozen windows 21600/900, 3 `usage.recorded` outbox rows `processed` with `retry_count 0`, handler checkpoints `platform.webhook_delivery.usage.recorded` ×3 and `subscriptions.cost_accumulator` ×3, cost accumulators matching the postings, 0 webhook configs/attempts, 44 migrations |

Not run in this session (covered by CI, needs pnpm/Docker): console typecheck/vitest, `apps/codegen` suites, the
Docker-backed Code Builder execution suite, the non-gating Schemathesis `conformance` job.

## Failures and uncertainties (nothing hidden)

1. **Chunk B, one failure: `test_beat_schedule.py::test_the_web_import_path_binds_shared_tasks_to_the_configured_app`.**
   The test spawns a fresh interpreter inheriting the shell environment, rings the outbox doorbell, and reads the
   message back from the `ubb_events` list on that environment's broker. My local Celery worker was still running
   on the same Redis index (`/5`) for the first minutes of the chunk and consumed the message first. The same test
   passed in run #14 (before the stack existed) and in run #17 (after the stack was stopped). Verdict: a test-
   environment interaction I caused, not a product defect. Worth knowing for Ash: run the platform suite with no
   worker consuming the environment's `REDIS_URL`.
2. **`makemigrations --check` on the shared developer database** failed for the documented post-squash reason (run #3);
   it passes on a fresh database (run #6). The owner's local `ubb` database still predates the squash.
3. **Port mapping on this machine** differs from the committed compose file (containers on 5432/6379 instead of
   5433/6380). A local quirk, not a repository fact.
4. **Worker and beat per-task log lines never reached the log files** because the `ubb.*` loggers are not configured
   (they inherit root WARNING). Dispatch was proven from durable state instead (outbox rows, checkpoints, beat's
   schedule store, `last_used_at`). This is an observation for the log-drain design, not a blocker.
5. **Not verified here:** the production image and its three roles by digest (no Dockerfile in the repository; the
   prep pass proved a draft locally); HTTPS/proxy behaviour under `DEBUG=False`; public-HTTPS webhook receipt and
   its timing; SLO 1/2/3; any payment behaviour; the console and renderer suites.
6. **Scope of "CODE VERIFIED":** most citations in `02` were produced by read-only mapping passes and a subset was
   re-opened by me; a line number could be off by a few lines if a pass mis-counted, but every cited symbol and file
   exists at this commit.

## `HANDOFF DISCREPANCY` (one; flagged, not fixed)

The F3 ruling says every wallet leg asks `holds_a_wallet` (true for `prepaid` only). Two sites still ask "not
postpaid?": `apps/billing/gating/services/risk_service.py :: RiskService.check (253)` and `reserve_agreed_price (347)`,
plus the manual-debit floor check `apps/billing/wallets/operations.py (242)`. They run only when the tenant has the
`billing` product (`api/v1/task_endpoints.py (125, 263-269)`), which an `external` tenant may enable through
`PATCH /tenant/config`. For `external` + `billing`, a start is floor-tested against a zero balance and a start of
fixed-price work lazily creates a Wallet and refuses with `insufficient_funds`. Unreachable for the ruled first
tenant (`products = ["metering"]`); reachable through the client's own admin key. Needs an owner ruling (product
fix, or an explicit accepted limitation). Details: `02-TECHNICAL-SYSTEM-MAP.md` §12.

Minor observations recorded in `02` that are **not** launch blockers: the outbox dead-letter horizon comment
(~2h43m) overstates the real ~42.5 minutes; `CLAUDE.md` still names the deleted `metering_async` product;
`.env.example` lists three unread names and omits `ALLOWED_HOSTS`; the SDK README's install line and `UBBClient`
signature are stale; `apps/codegen/README.md` says SDK v3 / catalogue v9; the lock file has no WSGI server (the
deployment-files PR adds one).

## Statement

No product code, test, migration, contract, SDK, console or documentation file in the repository was changed.
The only files created are the four in this folder. Local artefacts I created for the run (the database
`ubb_ash_handoff`, the pytest test database, Redis index `/5`, the credentials file and logs in the job's
temporary directory) were removed at the end of the session; the inspection worktree was left for the session's
exit prompt.
