ENGINEERING HANDOFF — CURRENT CODE SNAPSHOT — NOT ADMISSION EVIDENCE

# 02 — Technical system map

Commit: `origin/main` = `1bf0c0ca772410fa5aa721f733736f5f83e66760`. Paths are relative to the repository root
(`ubb/`); the Django project is `ubb-platform/`. Line numbers are from this commit.

**How to read the labels.** Every material claim is tagged:

- **CODE VERIFIED** — the cited file and symbol were opened at this commit (by me or by one of five read-only
  mapping passes I ran over the tree, whose citations I spot-checked).
- **TEST VERIFIED** — a test that pins the claim was executed in this session and passed (see `00-README.md` for the
  exact runs); or the claim was exercised by the local run of the stack.
- **CONTRACT VERIFIED** — read from the committed `openapi/v1.json` (regenerated in this session byte-identically).
- **DOCUMENTED INTENT ONLY** — stated in an ADR, a `CONTEXT.md` or a plan, not confirmed in code.
- **NOT VERIFIED** — could not be confirmed; stated so the gap is visible.

`HANDOFF DISCREPANCY` marks a place where the code contradicts the W7 brief or ruled intent. None was fixed.

---

## 1. Repository, runtime and languages

**CODE VERIFIED.**

| Area | Where | What |
|---|---|---|
| Django project | `ubb-platform/` | Django 6.0.6, django-ninja 1.6.2, pydantic 2.13.4, Celery 5.6.3, redis-py 8.0.0, psycopg 3.3.4, stripe 15.2.0, PyJWT 2.13.0 (`ubb-platform/requirements.lock.txt`, Python 3.13) |
| Python SDK | `ubb-sdk/` | `ubb-sdk` 4.0.0, import name `ubb`, Python ≥ 3.10, deps `httpx`, `PyJWT`, `attrs` (`ubb-sdk/pyproject.toml :: [project]` lines 9-20) |
| Console | `apps/ui/` | React 19, Vite 8, TypeScript 5.9, TanStack Router/Query, Tailwind 4, openapi-fetch, Clerk, vitest (`apps/ui/package.json`) |
| Code Builder renderer | `apps/codegen/` | `ubb-codegen` 0.1.0, TypeScript, consumed by the console as `workspace:*` |
| Contract | `openapi/` | `v1.json` (truth), `error-codes.json`, `known-values.json`, `contract_gate.py`, suppression files |
| Vocabulary registry | `domain-vocabulary/` | 11 concept YAML files; generates vocabulary modules in platform, SDK, console and the known-values metadata |
| Gates and tooling | `gates/`, `tools/`, `tests/` | ADR-0008 gate manifest G1–G27, migration ledger (at zero), Django-free checkers, root `tests/contracts` (845 tests) and `tests/code_builder_execution` |
| Local infra | `docker-compose.yml` | `postgres:16` and `redis:7` only, mapped to host 5433 and 6380; no app service |
| Node | root `package.json` | pnpm 10.28.2, workspaces `apps/*` |

**Entry points (CODE VERIFIED).** `ubb-platform/manage.py :: main (6-9)`; `config/wsgi.py (1-7)` →
`config.wsgi.application`; `config/asgi.py (1-7)`; `config/urls.py :: urlpatterns (12-24)` mounts `admin/`, five
plain Django views for inbound Stripe webhooks and the Connect callback, and `api/v1/` → `api.urls`.
`config/__init__.py (13)` imports the Celery app so every Django process binds `shared_task` to it (the F1 fix).

**What is absent (CODE VERIFIED, important for deployment).** No application `Dockerfile`, Procfile or platform
manifest anywhere in the tree (the seven Dockerfiles that exist are test harnesses under `tests/code_builder_execution/images/*`
and `apps/codegen/tests/harness/`). No gunicorn, uvicorn or whitenoise in the lock. No `STATIC_ROOT`, no
`collectstatic`. No build-info or version endpoint. No metrics, tracing or error-tracking library. The deployment
files are W7 step 1 and do not exist yet.

---

## 2. Django and API application structure

**CODE VERIFIED.** `ubb-platform/config/settings.py :: INSTALLED_APPS (22-53)` lists 21 UBB apps on top of Django's:

- Platform kernel (`apps/platform/`): `tenants`, `customers`, `plans`, `membership`, `events`, `audit`, `work`,
  `grouping_fields`, `event_types`, `code_builder`. `core/` is kernel plumbing and is **not** an installed app.
- Metering (`apps/metering/`): `usage`, `pricing`.
- Billing (`apps/billing/`): `wallets`, `topups`, `stripe`, `gating`, `invoicing`, `tenant_billing`,
  `connectors.stripe`.
- `subscriptions`, `referrals`.

**The product boundary rule (TEST VERIFIED).** Products talk only through outbox events, `queries.py` read
contracts, `ports.py` and platform hooks; `apps/platform/tests/test_product_boundaries.py` (an AST walker, 11 tests)
passed in this session. The composition layer `api/v1/` may import any product.

**API composition (CODE VERIFIED).** `api/v1/api.py :: api (69-80)` is one `NinjaAPI` (`title="UBB API"`,
`version="v1"`, default `auth=ApiKeyAuth()`, `openapi_extra={"webhooks": build_webhooks_section()}`).
`_ProblemDocumentingNinjaAPI (41-66)` swaps error media types to `application/problem+json`.
Nineteen routers are mounted at `api.py (88-142)`: `me/`, `tenant/`, `sandbox/`, `metering/`, `billing/`,
`subscriptions/`, `margin/`, `referrals/`, `webhooks/`, `platform/`, `connect/`, `audit/`, `spend-controls/`,
`code-builder/`, then plan, event-type, task, task-type and root routers at the root prefix. (The comment at
`config/urls.py:22` saying "twelve routers" is stale.)

**Middleware (CODE VERIFIED, `settings.py :: MIDDLEWARE (55-76)`).** Security → `core.middleware.CorrelationIdMiddleware`
(accepts a UUID `X-Correlation-ID` or mints one; echoes it; propagated into Celery headers by `config/celery.py (25-42)`)
→ `SunsetHeaderMiddleware` (inert: `api/v1/deprecation.py :: DEPRECATED_ROUTES (79)` is empty) →
`RequestActorMiddleware` → CORS → session/common/CSRF/auth/messages/X-Frame → `MethodNotAllowedProblemMiddleware`.

**Errors (CODE VERIFIED).** `api/v1/problems.py :: install_problem_handlers (109-190)` turns `Problem`,
`HttpError`, ninja validation errors, `DataError`, rail errors, 404 and any `Exception` (→ 500 `internal_error`,
traceback logged never returned) into RFC 9457 bodies. The code registry is `openapi/error-codes.json` (39 problem
codes, each with a fixed status, plus verdict sets), loaded **at import time** by `core/problems.py :: REGISTRY_PATH
(26-31)` from `<git root>/openapi/`. Consequence: the image must carry the repository's shape (`openapi/` beside
`ubb-platform/`), or the app cannot import.

**Versioning (CODE VERIFIED / CONTRACT VERIFIED).** Path version `/api/v1/` only; additive-only with a
deprecate-then-remove cycle (`docs/adr/0003-versioning-and-deprecation.md`); no operation is deprecated; the active
breaking-change baseline is the tag `api-v1-cutover` (= `c2eb35ff`), and `openapi/v1.json` is byte-identical between
that tag and this commit.

---

## 3. PostgreSQL persistence

**CODE VERIFIED.** `settings.py :: DATABASES (99-105)` = `dj_database_url.config(default="sqlite:///db.sqlite3",
conn_max_age=600)` with `CONN_HEALTH_CHECKS = True`; the schema uses `django.contrib.postgres` and plpgsql triggers,
so `DATABASE_URL` is required in practice. All ids are UUID primary keys (`core/models.py :: BaseModel (6-12)`).

**Migrations (CODE VERIFIED + TEST VERIFIED by execution).** 20 migration directories, 26 migration modules: one
generated `0001_initial` per app and a hand-written `0002_the_database_rules` in six apps (`tenants`, `event_types`,
`code_builder`, `work`, `metering/pricing`, `metering/usage`). On an empty PostgreSQL 16.14 database in this session:
`migrate` applied 44 migrations (26 project + 18 contrib), a second `migrate` had nothing to apply, and
`makemigrations --check --dry-run` reported no changes. The W6 squash (ADR-0026) deleted 287 historical migrations;
a developer database migrated before it cannot migrate forward and must be dropped (`CLAUDE.md` lines 50-55; I hit
exactly this on the shared dev database, see `00-README.md`).

**Database rules: 21 triggers, all `RunSQL` with a reverse, refusing with SQLSTATE 23000 (CODE VERIFIED):**

| Migration | Triggers |
|---|---|
| `apps/platform/tenants/migrations/0002_the_database_rules.py :: Migration (126-145)` | `trg_payment_rail_activation_declared_transitions`, `trg_payment_rail_activation_is_kept`, `trg_tenant_money_mode_needs_its_rail` (G27) |
| `apps/platform/event_types/migrations/0002_… (64-75)` | `trg_event_type_keeps_its_held_names` (deferred constraint trigger) |
| `apps/platform/code_builder/migrations/0002_… (60-71)` | `trg_blueprint_snapshot_declared_transitions` |
| `apps/platform/work/migrations/0002_… (213-232)` | `trg_task_type_declared_transitions`, `trg_task_containment_shares_the_pricing_regime`, `trg_task_declared_transitions` |
| `apps/metering/pricing/migrations/0002_… (228-259)` | `trg_rate_declared_transitions`, `trg_rate_names_a_declaration`, `trg_book_publish_declared_transitions`, `trg_resolution_run_is_never_edited`, `trg_charge_declared_transitions`, `trg_task_price_declared_transitions` |
| `apps/metering/usage/migrations/0002_… (506-542)` | `trg_posting_declared_transitions`, `trg_posting_price_transitions`, `trg_posting_receipt_sealing`, `trg_posting_kind_frozen`, `trg_posting_measurement_pruning`, `trg_posting_measurement_released_once`, `trg_stop_acknowledgement_is_insert_only` |

About 110 model-level check/unique constraints across 18 `0001_initial` files; no `RunPython` anywhere. Gate G20
(`gates/manifest.yaml (1031-1082)`) holds every future migration to "a rename carries its data".

**Main tables by subsystem** are listed in the sections below. Locking order is documented in
`core/locking.py (4-21)`: Task → Wallet → Customer → StopSignalState → TopUpAttempt → Invoice → Posting; row locks
are `select_for_update`, there are no advisory locks and no Redis locks.

---

## 4. Redis usage

**CODE VERIFIED.** One `REDIS_URL` (`settings.py:125`, default `redis://localhost:6379/1`) serves:

1. **Django cache** (`settings.py (128-133)`, `RedisCache`): the API-key last-used buffer (`core/auth.py :: ApiKeyAuth.authenticate (58)`
   writes `apikey_used:{pk}`; `core/tasks.py :: flush_api_key_last_used (12-31)` flushes it every 5 minutes —
   **TEST VERIFIED in the local run**: `last_used_at` was populated by the beat-driven flush); the tenant-products
   cache (`apps/platform/events/dispatch.py :: _tenant_has_product (15-34)`, invalidated by `Tenant.save`); the
   admission-control counters (`apps/platform/work/admission.py :: window_keys (112-116)`, `_count_a_start (157-199)`,
   fail-open when the store is unavailable).
2. **Celery broker and result backend** (`settings.py (135-148)`).
3. **Enforcement live counters** via a raw client (`apps/billing/gating/services/live_counter.py :: _client (189-191)`):
   keys `ubb:livebal:{owner}`, `ubb:livespend:{owner}:{YYYY-MM}`, `ubb:stop:{customer}`, `ubb:spend_pool:{customer}:{YYYY-MM}`,
   pub/sub `ubb:stopchan:{owner}` (no production subscriber found), five Lua scripts (`112-187`), 62-day TTL
   (`COUNTER_TTL_SECONDS`, 97). Active only when `flags.enforcing(tenant)` and maintenance is on; a Redis failure
   fails open (docstring 307-309).
4. **Readiness probe** `api/v1/endpoints.py :: ready (25-48)` pings it.

Tests move cache, broker and counters to DB `/15` (`ubb-platform/conftest.py :: pytest_configure (18-44)`), so a test run
flushes that index.

---

## 5. Celery app, worker and beat

**CODE VERIFIED.** `config/celery.py`: `app = Celery('ubb_platform')`, `config_from_object('django.conf:settings',
namespace='CELERY')`, `autodiscover_tasks()` (9-11); `app.conf.imports = ("core.tasks",
"apps.platform.events.tasks_webhook_cleanup")` (19-22, the F2 fix, because `core` is not an installed app and the
cleanup module is not named `tasks.py`). Settings (`settings.py (135-162)`): JSON only, UTC, `acks_late`,
`reject_on_worker_lost`, hard limit 600 s / soft 300 s, prefetch 1, 1000 tasks per child, **nine declared queues**
(`ubb_invoicing`, `ubb_webhooks`, `ubb_topups`, `ubb_billing`, `ubb_events`, `ubb_economics`, `ubb_subscriptions`,
`ubb_referrals`, `ubb_metering`); routing is per task via `@shared_task(queue=…)`, there is no `task_routes`
and no default-queue setting. Beat uses Celery's file-based `PersistentScheduler` (no django-celery-beat);
`CELERY_BEAT_SCHEDULE (166-294)` has **30 entries** (the vacuity-floor docstring in `test_beat_schedule.py:69-76`
still says 27). Full table: minutely `sweep_outbox`; every 5 minutes `expire_stale_topup_attempts`, `reap_stale_tasks`,
`flush_api_key_last_used`; every 15 minutes `close_abandoned_tasks`; hourly reconciles for wallets, grants,
reservations, tenant billing periods, receipts, spend-pool counters, live ledgers, subscription mirrors, postpaid
usage, usage drawdowns, cost accumulators, dirty-period resnapshots, invoice payment status, top-ups; daily cleanups
(outbox 04:00, Stripe webhook events 03:00, webhook delivery attempts 03:00, blueprint snapshots 04:30), the
measurement prune (03:15), economics snapshots (02:00), referrals (04:00, 05:00); monthly period closes and
platform-fee invoices on the 1st.

**TEST VERIFIED (this session).** `apps/platform/tests/test_beat_schedule.py` (incl. the two fresh-interpreter
F1/F2 pins at 349-372) passed. In the local run, a worker started with `celery -A config worker` consumed exactly
the nine queues and registered both F2 tasks by name; the web process's on-commit doorbell reached the broker (three
`usage.recorded` rows processed with `retry_count 0`, no `outbox.dispatch_failed`); beat's store recorded
`sweep-outbox` runs and the 5-minute flush wrote `last_used_at`.

**Worker and beat start commands are not in the repository** (NOT VERIFIED as a committed artefact; the prep pass's
draft used `celery -A config worker -l INFO -Q <nine queues>` and `celery -A config beat -l INFO --schedule <path>`).
Beat must be a singleton with a writable schedule path.

---

## 6. Usage and event ingestion

**CODE VERIFIED.** Router `api/v1/metering_endpoints.py :: metering_router (110)`, mounted at `metering/`, gated on
the `metering` product (`_product_check`, 112).

| Endpoint | Function | Notes |
|---|---|---|
| `POST /api/v1/metering/usage` | `record_usage (651-665)` → `record (668-688)` → `replay_or_record (549-613)` | always 200 when recorded; a non-200 means "not recorded" |
| `POST /api/v1/metering/usage/batch` | `record_usage_batch (691-713)` | 1–100 independent items, each in its own transaction (`record_sync_item (616-648)`); always 200 with per-item `accepted`/`code` |
| `GET /api/v1/metering/customers/{customer_id}/usage` | `get_usage (736-760)` | cursor paginated; items carry `id` (the ack calls it `event_id`) |
| `GET /api/v1/metering/usage/{event_id}` | `get_usage_event (763-846)` | full receipt plus derived `measurements_status` |

**Request (`api/v1/schemas.py :: RecordUsageRequest (310-437)`).** `customer_id`, `idempotency_key` (1–500 chars),
`event_type`, `provider`, `measurements: dict[str, DeclaredDecimal]` (strings only; `every_quantity_in_its_canonical_text
(364-380)`), three optional cost fields bounded at 999,999,999,999 micros, `grouping_fields`, `metadata` (the one open
bag; filterable, never priced), `effective_at`, `task_id`, `currency`. `refuse_a_caller_supplied_customer_price (402-437)`
rejects any body naming `billed_cost_micros`; other unknown keys are dropped.

**Validation (CODE VERIFIED).** Replay first: `apps/metering/usage/services/usage_service.py :: UsageService.replay
(857-905)` on (tenant, customer, key) backed by `uq_posting_idempotency` (`usage/models.py :: Posting.Meta (519-522)`);
a concurrent loser's `IntegrityError` becomes `RecordingConflict` and is answered by replay (536-544, 1014-1028).
`validate_effective_at (85-128)`: naive → refused; > 5 min future → refused; older than `tenant.backfill_window_days`
(default 34) → refused; invoiced month (`apps.billing.queries.is_usage_period_closed`) → refused. Quantities:
`apps/platform/event_types/exact_decimals.py :: canonical (64-88)`, `canonical_quantity (135-154)` refuse float, bool
and `Decimal`; arithmetic is integer `exact_parts (107-132)`. Admission against the last publication:
`metering_endpoints.py :: admit_provider (224-277)`, `admit_supplier_cost (280-374)`, `admit_quantities (502-532)`;
`apps/platform/grouping_fields/services.py :: GroupingFieldService.admit (119)` (writes new values under a cardinality
cap, in a separate commit). Currency: `core/currency_policy.py :: admit_currency (89-97)`, USD only.

**Persistence in one transaction (`UsageService.record_new_usage (927-1033)` → `_record_core (588-855)`, CODE VERIFIED):**
price (`PricingService.price`) → `Posting` → `PostingMeasurement` → hold undeclared names (`QuarantinedKey`) → roll into the
Task (`TaskService.accumulate_cost`) → live-counter debit (if enforcing) → `StopAcknowledgement` → stop context →
`BackfillDirtyPeriod` for closed months → `write_event(UsageRecorded)`; on commit: the outbox doorbell and
`_execute_kills (547-584)`.

**Response (`schemas.py :: RecordUsageResponse (972-1155)`, CONTRACT VERIFIED).** `event_id`, supplier cost
(`provider_cost_micros`, `costing_status`, `unresolved_reason`), customer price (`billed_cost_micros`,
`pricing_status`, `pricing_status_reason`, `not_applicable_reason`, `pricing_method`), task rollups, the stop block
(`stop`, `stop_reason`, `stop_scope`, `trigger_source`, `stop_bound_micros`, `stop_measured_micros`), ceiling block,
`stop_context`, canonical `measurements`, the typed `pricing_receipt` (required), `grouping_fields`.
`new_balance_micros` is always null.

**There is no asynchronous ingest path.** The `metering_async` product and the raw-ingest route were deleted in
slice 1 (CODE VERIFIED by absence: products are `metering | billing | referrals`, `core/vocabulary.py (2162-2166)`;
`metering_endpoints.py (115-124)`). `CLAUDE.md` still lists `metering_async` — a stale sentence, not a capability.

**TEST VERIFIED (local run).** One event with a reported cost of 1,000,000 micros under a published Event Type and
a 20% default markup → `costing_status known`, `pricing_status known`, `billed_cost_micros 1200000`,
`pricing_method margin_over_cost`, receipt schema 2 / engine 3.0.0 / subject `usage_event`; replay returned the same
`event_id`; both read endpoints returned it.

---

## 7. Event Types (kernel: `apps/platform/event_types/`)

**CODE VERIFIED.** Models in `event_types/models.py`: `EventType (632-1108)` (`key`, `provider` FK PROTECT,
`category`, `costing_method` `calculated|reported`, `declaration_status` `draft|published`, `published_revision`,
`published_declaration` JSON pin; constraints 769-796); `Measurement (1175-1565)` (`code`, `value_type`
`integer|decimal`, `unit`, `required_for_costing`, source kind/path, concept); `ReportedCostMapping (1566-1838)`
(`source_kind` `provider_response|caller_supplied|derived|constant`, `amount_representation`
`micros|minor_units|major_units_decimal`, exactly one of `currency`/`currency_path`); `Provider (509)`,
`EventCategory (591)`, `QuarantinedKey (1847+)` the held-name record with a `resolution` of `mapped|registered|dismissed`.

**Lifecycle.** `EventType.publish (961-1028)` locks, pins the declaration, bumps the revision, and after commit rings
`answer_after_the_publication_commits` (`quarantine.py (489-512)`) → Celery `answer_held_names`
(`event_types/tasks.py (22-32)`), with the Resolution Run as the retry. Recording reads only
`publication.py :: last_published_declaration (102-128)`. A held name has **no public remediation route**; it is
answered by a later publication or a Resolution Run (NOT a gap for launch; stated so it is not assumed).

**Routes (CONTRACT VERIFIED; `api/v1/event_type_endpoints.py`, root mount, metering-gated, writes ADMIN).**
`/providers` (GET, POST, PATCH `{key}`), `/event-categories` (GET, POST, DELETE), `/event-types` (GET, POST draft,
GET `{key}`, PATCH, POST `{key}/publish`), `/event-types/{key}/measurements[/{code}]` (GET, PUT, DELETE),
`/event-types/{key}/reported-cost-mapping` (GET, PUT, DELETE). **TEST VERIFIED (local run):** declare → map
(`caller_supplied`, `micros`, `usd`) → publish answered `declaration_status: published`, `published_revision: 1`;
the draft had advertised `publication_blockers: ["reported_cost_mapping"]` before the mapping existed.

**Undeclared names (CODE VERIFIED).** `pricing_service.py :: PricingService._compute (1058-1078)`: an event naming
a type nobody published is recorded with `costing_status unresolved` / `unresolved_reason event_type_not_declared`
and price `unknown` with the same reason; `_record_core` writes the `QuarantinedKey` (740-745). ADR-0022.

---

## 8. Tasks and Subtasks (kernel: `apps/platform/work/`)

**CODE VERIFIED.** `work/models.py :: TaskType (216-387)` (`key`, `kind` task|subtask, ceiling or `uncapped`,
silence window, absolute deadline, `pricing_mode` FROZEN, required grouping fields, `retired_at`) and
`Task (389-1006)`, table `ubb_task`: `parent` (one level), `task_type`, ten grouping slots, `status`
(`active|completed|failed|cancelled|killed|expired`, 62-69), totals and counters (471-511), start policy
(`balance_snapshot_micros`, `task_cogs_ceiling_micros`, `pricing_mode`), agreed price and provenance (580-622),
`last_event_at` heartbeat, `announce_outbox_id`, close facts (`outcome_reason`, `reason_detail`), **stop facts**
(`reason_code`, `trigger_source`, `control_family`, `control_id`, 719-722, SET_ONCE), **expiry snapshot**
(`start_absolute_deadline_seconds`, `start_silence_window_seconds`, 736-737, FROZEN), `idempotency_key`
(`uq_task_idempotency_key`), `completed_at`. `transition_classes (788-802)` declares the column rules the trigger
`trg_task_declared_transitions` enforces.

**Services (`work/services.py :: TaskService`, CODE VERIFIED).** Start: `api/v1/task_endpoints.py :: start (174-396)`
in one transaction — idempotency claim (`claimed_by`, 605), `admission.admit`, `RiskService.check` (only when the
tenant has the `billing` product, 263-269), `parent_for`, `resolve_start_policy`, `determine_the_agreed_price`,
`create_task (661-757)`, `reserve_agreed_price`. Accumulate: `accumulate_cost (759-949)` locks parent then child,
adds totals or counts unresolved/unpriced, stamps `last_event_at`, returns crossing verdicts. Terminal: `_flip
(1056-1154)` writes stop facts, notifies hooks, cascades (`_cascade`, 1198-1258); `kill_task`, `expire_task`,
`close_task (1406-1441)`; announcements via `_stop_and_announce (1310-1403)` in its own transaction — only the
winner writes `task.killed|subtask.killed|task.expired|subtask.expired` (`events/schemas.py :: terminal_stop_event`, 833).
Charges for delivered fixed-price work: `pricing/services/charge_service.py :: charge_for_delivered_work (61-125)`,
written only by the call that wins the close (`task_endpoints.py:608`).

**Routes (CONTRACT VERIFIED).** `POST /tasks` (a subtask is `parent_task_id`), `GET /tasks`, `GET /tasks/{id}`,
`GET /tasks/{id}/subtasks`, `POST /tasks/{id}/close` (`outcome` delivered|failed|cancelled); `PUT /task-types`,
`GET /task-types`. Refusals: 409 with an `affordability_reason`, 429 for the start rate limit, 409
`task_already_terminal` on a conflicting close.

**Sweepers (CODE VERIFIED, `work/tasks.py`).** `close_abandoned_tasks (96-179)` every 15 min expires silently work
older than an hour; `reap_stale_tasks (182-266)` every 5 min, enforcing tenants only, expires and announces with
`trigger_source=stale_reaper`. Both re-read live windows through `work/queries.py :: expiry_windows (130)`
(backstops 15 min silence, 6 h deadline, lines 37-38) while the Task row keeps the frozen start snapshot.

**TEST VERIFIED (local run).** Start → one usage event naming the task (ack `task_total_billed_cost_micros 600000`,
`ceiling_status not_applicable`) → `complete()` through the SDK context manager → `GET /tasks/{id}` `status completed`,
`recorded_events 1`; the row carried `start_absolute_deadline_seconds 21600` and `start_silence_window_seconds 900`.

---

## 9. Pricing and Pricing Receipts (`apps/metering/pricing/`)

**CODE VERIFIED.** Models (`pricing/models.py`): `TenantDefaultMarkup (31-99)` (`markup_micro_percent`, 1,000,000 =
1%, no default — UBB ships no catalogue); `Rate (235-709)` with 14 selectors (`SELECTORS`, 649-650), one measurement
(declared FK or `undeclared_measurement_key`), `pricing_method`, `rate_structure` `per_unit|fixed_component`,
`rate_per_unit_micros`/`unit_quantity`/`fixed_micros`, exactly one of `pricing_book`/`cost_book`, `valid_from` FROZEN,
`valid_to` SET_ONCE, eight constraints (501-597), `compute (670-709)`; `TaskPrice (712-927)` the agreed price;
`CostBook (1203-1295)`; `PricingBook (1297-1449)` (customer override books, one default); `PricingBookPublish
(1487-1693)` the dated draft/publish of changes; `Charge (929-1201)` every economic column FROZEN; `ResolutionRun
(1696-1871)`.

**Resolution (`pricing/services/pricing_service.py`).** `price (1460-1508)` → `resolve_price (1751-1855)` → `_compute
(863-1458)` → `receipts.build_receipt`. Book precedence `_selected_pricing_books (610-664)`: the customer's own override
book, then the plan's book, then the tenant default. Rank `(specificity, source, valid_from)` (106-136), no fall-through
between books; the markup rung only when no rule matched (1293-1313); fixed-price work is `not_applicable` with reason
`fixed_task_pricing`; a negative price is `unknown` with `negative_price_unsupported` (ADR-0020). Constants
`PRICING_ENGINE_VERSION = "3.0.0"` (90).

**Receipt (CODE VERIFIED / CONTRACT VERIFIED).** Not a table: the JSON column `Posting.pricing_receipt`
(`usage/models.py (358-359)`), built only by `pricing/receipts.py :: build_receipt (567-600)`,
`RECEIPT_SCHEMA_VERSION = 2 (257)`, top-level keys `receipt_schema_version`, `pricing_engine_version`, `subject_type`
(`usage_event|charge`), `subject_id`, `effective_at`, `currency`, `costing{method,status,detail}`,
`pricing{method,status,detail}`, `totals`, `provenance` (ids only). Sealed once complete by `trg_posting_receipt_sealing`.
Typed in the contract as `PricingReceipt (schemas.py 955-969)`.

**Late resolution doors (CODE VERIFIED).** `cost_settlement.py :: settle_provider_cost (91-185)` is one conditional
UPDATE; `price_resolution.py :: resolve_customer_price (142-246)` runs under the transaction-local mark
`ubb.price_door`, which `trg_posting_price_transitions` requires. Resolution Runs: `resolution_run.py :: execute
(229-294)`, at most 200 postings per run, route `POST /metering/pricing/resolution-runs`.

**Routes (CONTRACT VERIFIED, `metering_endpoints.py`).** Default markup GET/PUT/DELETE; pricing books and cost books
GET/POST/DELETE; a book's rates and agreed prices; publishes (declare, list, get, publish, discard); customer overrides
(declare, withdraw, inherited rule); resolution runs; unresolved queue, projected adjustment, waived loss; grouping
fields GET/PUT and values; grouping options; economics.

---

## 10. Costs, Charges and Postings (`apps/metering/usage/`)

**CODE VERIFIED.** `usage/models.py :: Posting (51-721)`, table `ubb_posting`, `kind` `metered_usage|task_charge`
(FROZEN); supplier cost (`provider_cost_micros`, `costing_status` `known|unresolved|not_applicable`,
`unresolved_reason`), customer price (`billed_cost_micros`, `pricing_status` `known|waived|unknown|not_applicable`,
`pricing_status_reason`), `claimed_provider_cost_micros` (FROZEN, never COGS), `effective_at`, `task_id`,
`pricing_receipt`, `stop_context`, ten grouping slots; check constraints
`ck_posting_costing_status_agrees_with_the_cost (553-566)` and `ck_posting_pricing_status_agrees_with_the_price (601-620)`;
`ck_posting_currency_usd`. `PostingMeasurement (724-862)` one-to-one with `measurements` JSON and `prunable_at`
(SET_ONCE); `StopAcknowledgement (865-973)` insert-only; `BackfillDirtyPeriod (976-1011)`; `Refund (1014-1035)`.

**Charges.** `charge_for_delivered_work` writes a `Charge` and `charge_projection.py :: project_the_charge (163-267)`
projects it onto one `task_charge` Posting with provider cost 0 known and the agreed amount known, plus a
`UsageRecorded` outbox event (ADR-0013). `compensate()` exists but no route calls it.

**Money (CODE VERIFIED).** Integer micros in `BigIntegerField`; the only cap is signed 64-bit (`core/money.py ::
MONEY_COLUMN_MAX/MIN (67-68)`); `round_charge (167-186)` nearest micro, ties away from zero, integer arithmetic. The
only `Decimal` in the economic path is `margin_percentage` in subscriptions. No FX (`core/currency_policy.py (1-32)`,
ADR-0023).

**Prune (CODE VERIFIED).** `usage/tasks.py :: prune_measurement_detail (11-16)` daily 03:15 → `usage/pruning.py ::
prune_measurements (179-224)`: horizon from `UBB_MEASUREMENT_RETENTION_DAYS` (default 400), batches of 1,000, run cap
100,000, sets `prunable_at = TransactionNow()` then deletes, never touches unresolved or unknown rows; logs
`measurement_prune.completed|failed`. ADR-0025.

---

## 11. Customer revenue and economics

**CODE VERIFIED.** Query time: `apps/metering/queries.py :: economics (2136)` is the one economic query; measures
`ECONOMIC_MEASURES (1834-1839)` = supplier COGS, customer revenue, gross margin, recorded events; margin computed per
row in `_margin (3030-3059)`, never per posting; per-measure `measure_status` (`known`, `incomplete`,
`unavailable_at_requested_grain`, `unavailable_outside_retention_horizon`; `MEASURE_STATES_WORST_LAST (1925-1962)`).
Route `GET /metering/analytics/economics` (`metering_endpoints.py :: query_economics (2326-2488)`), grouping by
declared grouping fields and rollups (`grouping_options (1623)`).

Stored: `apps/subscriptions/economics/models.py :: CustomerCostAccumulator (25-71)` (per customer per month; fed by
the outbox handler `subscriptions.cost_accumulator`, `apps/subscriptions/handlers.py :: handle_usage_recorded_subscriptions
(28-150)` — **TEST VERIFIED in the local run**: accumulators `posting_count 1` and `2` matched the postings;
F6's savepoint fix pinned by `test_handlers.py :: TestTwoRacingFirstEventsOfAPeriod`, passed), repaired hourly by
`reconcile_cost_accumulators`; `CustomerEconomics (74-173)` monthly snapshots (daily 02:00 and dirty-period
resnapshots); `TenantSuppliedRevenue` (`POST/GET /margin/customers/{id}/supplied-revenue`); `MarginThresholdConfig`
(`/margin/threshold`, `/margin/unprofitable`).

**The read contract.** `apps/metering/queries.py` exports period and customer totals as (amount, excluded-count)
pairs (`get_period_totals (246-304)`, `get_customer_cost_totals (402-432)`, …), invoice-line reads, backfill markers
(the one writing exception), recovery reads, stop-context reads, grouping vocabulary and economics; consumers are
listed in its docstring (18-46).

---

## 12. Spend controls: ceilings, pools, wallet policy, admission (ADR-0014)

**CODE VERIFIED.** Four `control_family` values (`apps/billing/gating/models.py (77-82)`). Enforcement switch
`Tenant.enforcement_mode` `off|enforcing` (default `off`, `tenants/models.py (336-339)`), read through
`apps/platform/tenants/flags.py :: enforcing (86-94)`; `off` disables only the customer-wide families (17-52).

- **Ceiling (kernel).** Rungs on `Tenant.default_task_cogs_ceiling_micros` / `default_subtask_cogs_ceiling_micros`
  and `TaskType`; resolved at start by `apps/billing/gating/services/risk_service.py :: RiskService.resolve_start_policy
  (64-184)`; decided synchronously in `TaskService.accumulate_cost`; killed on commit by `usage_service.py ::
  _execute_kills (547-584)`; hourly backstop `gating/patrol.py :: sweep_over_limit_tasks (225-280)`.
- **Admission control (kernel).** `work/admission.py :: admit (119-138)`, rate limit `Tenant.max_task_starts_per_minute`,
  counter in the cache, fail-open.
- **Customer spend pool.** `gating/models.py :: CustomerSpendPool (314-345)` (`cap_micros`, `enforce_mode`
  `alert_only|blocking`, `hard_stop_pct`, `alert_levels`, `fail_closed`); service
  `customer_spend_pool_service.py` (`check 172-200`, `signal_if_past 230-265`, `stop_active_work 268-292`,
  `record_usage_spend 359+`); crossing in `core/crossing.py :: past_spend_pool_stop (122-127)`.
- **Wallet policy.** Hard floor `CustomerBillingProfile.min_balance_micros` then `BillingTenantConfig.min_balance_micros`
  (default 0); soft floor; resolved by `apps/billing/queries.py :: get_customer_min_balance (49-51)`,
  `get_customer_soft_min_balance (63-85)`. Applies only where `holds_a_wallet(tenant)` (`flags.py (70-77)`, true for
  `prepaid` only; the F3 fix of this commit) at the live debit, resume, read, credit, reconcile, repair, owner selection
  and durable drawdown.

**The stop ledger (CODE VERIFIED).** `gating/services/stop_signal_service.py :: StopSignalService.drive_stop (256-334)`
→ `_open_line (210-238)` upserts `StopSignalState` (unique per owner/family/line, `episode_seq`), emits
`CustomerStopped` and `CustomerSuspended`, flips the Customer to `suspended`, and for the pool line kills active
work on commit; `drive_clear (336-366)` → `CustomerStopCleared`; `close_all_silently (386-407)` when enforcement is
switched off. Live lane: `queries.record_live_usage_debit (99-137)` → `LiveCounter.debit (276-432)`.

**`HANDOFF DISCREPANCY` (CODE VERIFIED, not fixed).** The F3 ruling and `flags.py`'s docstring say every wallet leg
now asks `holds_a_wallet`. Two sites still ask the old question:
`apps/billing/gating/services/risk_service.py :: RiskService.check (253)` — `on_the_wallet_lane = owner.tenant.billing_mode != "postpaid"`,
reading an absent wallet as balance 0 — and `reserve_agreed_price (347)` — `if tenant.billing_mode == "postpaid" or price is None`;
plus the manual-debit floor check `apps/billing/wallets/operations.py :: debit.prepare (242)`.
They are reached only when the tenant has the **`billing` product** (`task_endpoints.py :: _TENANT_HAS_A_WALLET (125)`,
`start (263-269)`), which an `external` tenant may enable through `PATCH /tenant/config` (allowed by `Tenant.clean`;
`apps/platform/tenants/tests/test_billing_mode.py:29`). For `external` + `billing`: a start is floor-tested against a
zero balance (admitted at the default floor of 0; a positive soft floor would refuse), and a start of a fixed-price
kind of work lazily creates a Wallet (`apps/billing/locking.py :: lock_for_billing (88-92)`) and refuses with
`insufficient_funds`. The F3 pins (`test_mode_pins.py (143-146, 181-185)`) use `products=("metering",)` and do not
cover this case. It does not affect an `external` tenant with the default products. Needs an owner ruling (fix in
product, or an explicit accepted limitation for the first tenant); recorded here, not patched.

---

## 13. Stop, kill and webhook flows

**CODE VERIFIED.** Ceiling kill: `accumulate_cost` verdict → `reasons.kill_plan (work/reasons.py 217)` →
on-commit `_execute_kills` → `TaskService.kill_and_announce (1261)` → `_stop_and_announce` (own transaction; Task
status `killed`, stop facts, `announce_outbox_id`; cascade; terminal-transition listeners incl. billing's
reservation release) → outbox `task.killed|subtask.killed` → `platform.webhook_delivery.*` handler. Customer-wide
stop: any lane → `drive_stop` → `customer.stopped` (+ `customer.suspended`), pool line also kills active work with
`trigger_source=pool_crossing`. What the client sees: the ack's stop block (precedence `_the_stop_it_acknowledges`,
`usage_service.py (355-407)`), persisted as `StopAcknowledgement` so a replay repeats it (ADR-0019); a 409/429 on
a refused start; the webhook.

**Webhook event types (CONTRACT VERIFIED, 37, `openapi/v1.json` `webhooks`).** `auto_top_up.requires_action`,
`credit_grant.expired|expiring`, `customer.deleted|stop_cleared|stopped|suspended|unprofitable`,
`customer_spend_pool.threshold_reached`, `invitation.created|revoked`, `member.activated`, `provider.cost_spike`,
`referral.created|expired|payout_due|reward_earned`, `refund.requested`, `sandbox.reset_completed`,
`subtask.expired|killed`, `task.expired|killed`, `tenant.api_key_created|revoked|rotated`, `top_up.requested`,
`usage.recorded|refunded`, `usage_invoice.push_failed_permanent|pushed`,
`wallet.balance_critical|balance_low|balance_overage`, `wallet_policy.soft_floor_cleared|soft_floor_crossed`,
`withdrawal.requested`. Built by `apps/platform/events/openapi.py :: build_webhooks_section (51)` from the 37 payload
schema classes in `events/schemas.py`.

---

## 14. `external` billing mode and what payment behaviour is absent

**CODE VERIFIED.** Values `external|prepaid|postpaid` (`domain-vocabulary/concepts/economics.yaml ::
customer_billing_mode (9-32)`; `meter_only` is a retired alias, 21-25; `core/vocabulary.py (697-716)`);
`Tenant.billing_mode` default `external` (`tenants/models.py (321-324)`); posture derived
`TENANT_POSTURE_OF (73-77)`: `external → metering_only`; `MONEY_MODES = {prepaid, postpaid} (83-85)`; `Tenant.clean
(539-566)` requires `billing` for a money mode and an enabled `PaymentRailActivation` (G27), also held by
`trg_tenant_money_mode_needs_its_rail`.

For `external`: no wallet (no drawdown `apps/billing/handlers.py:87`; no live balance or hard floor
`live_counter.py (352-389)`; no wallet reconcile or repair; no Tier-1 suspension), no auto top-up (only emitted by the
drawdown tail), no postpaid push (`invoicing/tasks.py :: close_postpaid_usage_periods (85-104)` filters `postpaid`),
no drawdown repair, no rail guard (`refuse_a_rail_operation_while_it_is_closed (193-211)` returns early), and with
only `metering` enabled no `TenantBillingPeriod`/platform-fee accrual. Still active: postings and acks, ceilings,
admission control, the pool leg under `enforcing`, the cost accumulator, `/me/economics`. Stripe's live inbound
receivers return 400 before any verification when `STRIPE_WEBHOOK_SECRET` is unset or blank
(`api/v1/webhooks.py :: stripe_webhook (47-63)`; `apps/subscriptions/api/endpoints.py (165-185)`), F5 —
**TEST VERIFIED** (`LiveReceiverFailsClosedTest`, `TestLiveSubscriptionsReceiverFailsClosed` passed). **TEST VERIFIED
(local run):** `GET /tenant/config` answered `billing_mode external`, `tenant_posture metering_only`,
`enforcement_mode off`; `GET /connect/status` `charges_enabled false`.

**Prepaid and postpaid (CODE VERIFIED, not exercised).** Wallet path: every change goes through
`apps/billing/wallets/operations.py :: _execute (146-218)`; `draw_down_usage (498-548)` on the outbox lane;
`WalletBalanceLow` → `connectors/stripe/handlers.py :: handle_balance_low_stripe (20-40)` → `charge_auto_top_up_task`.
Postpaid: `invoicing/services/postpaid_service.py :: push_customer_period (189-374)` (claim → Stripe → record) with
`repush_usage_invoice` as the operator retry. Stripe wrapper `apps/billing/stripe/services/stripe_service.py ::
stripe_call (81-143)` refuses an empty API key (fails closed).

---

## 15. Tenant and customer hierarchy

**CODE VERIFIED.** `Tenant (tenants/models.py 307-584)`, table `ubb_tenant`: `name`, Stripe ids, `platform_fee_percentage`,
`is_active`, `widget_secret` (generated on save with `secrets.token_urlsafe(48)`, 569-570; `rotate_widget_secret`, 581),
`products` (`metering` required; defaults to `["metering"]`), `billing_mode`, `default_currency` (USD-only constraint),
`enforcement_mode`, `live_counter_maintenance_enabled`, task windows and ceiling defaults, `max_task_starts_per_minute`,
`backfill_window_days` (0–60, default 34), `is_sandbox`, `parent_tenant` (the sandbox sibling; `uq_one_sandbox_per_parent`,
`ck_sandbox_iff_parent`). `PaymentRailActivation (214-286)`. Sandbox: `services/sandbox_service.py :: get_or_create_sandbox
(41-75)` copies products, mode and currency, never Stripe fields; `POST /sandbox/reset` wipes it asynchronously.

`Customer (customers/models.py 34-106)`, table `ubb_customer`: `tenant`, `external_id`, `stripe_customer_id`, `status`
`active|suspended|closed`, `account_type` `individual|business|seat`, `parent` (a seat's business), `billing_topology`
`pooled|allocated`, soft delete; `uq_customer_tenant_external` partial unique; `resolve_billing_owner (79-85)` (a pooled
seat bills to its business). Under a customer: Tasks (`ubb_task`) and Postings (`ubb_posting`); membership
(`membership/models.py :: Member (98-134)`, `Invitation (59-95)`); webhook configs; API keys.

**No API route creates a tenant** (CODE VERIFIED by absence; `api/v1/verification.py :: _Run._materialise (348)` creates
one only inside a rolled-back transaction). The admin registers `TenantAdmin` (`tenants/admin.py (11-15)`), and
`seed_dev_data` is the dev command (requires `--stripe-account`).

---

## 16. Authentication and API keys

**CODE VERIFIED.** `TenantApiKey (tenants/models.py 587-656)`, table `ubb_tenant_api_key`: `key_prefix` (first 16 chars),
`key_hash` (unsalted SHA-256, unique), `label`, `is_active`, `last_used_at`, `role` (default admin). `create_key
(611-637)` mints `ubb_live_`/`ubb_test_` + `secrets.token_urlsafe(32)`, routes a test key to the sandbox sibling, returns
`(obj, raw_key)` — the only place a raw key exists. `verify_key (639-656)` hashes, requires active key and tenant, and
refuses a mode mismatch. Header `Authorization: Bearer <token>` via `core/auth.py :: ApiKeyAuth (29-74)` (API key first,
then a Clerk member JWT through `core/clerk_auth.py :: verify_member_token (68-93)` when `CLERK_*` is configured;
inert otherwise); role floors `role_floor (90-129)`; product gating `ProductAccess (132-143)` → 403
`feature_not_enabled`. **TEST VERIFIED (local run):** a key minted by `create_key` authenticated every call; a
`ubb_live_` key was refused on the widget route (401).

Routes (CONTRACT VERIFIED): `GET/POST /tenant/api-keys`, `POST /tenant/api-keys/{id}/rotate`, `DELETE
/tenant/api-keys/{id}` (409 on the last active key), `POST/GET /tenant/sandbox`, invitations and members, `GET/PATCH
/tenant/config`. The raw key is returned once by create, rotate and sandbox. The admin's `TenantApiKeyAdmin (45-49)`
lists keys and cannot mint one.

**End-customer auth.** `core/widget_auth.py :: WidgetJWTAuth (65-87)`: HS256 signed with `Tenant.widget_secret`,
claims `sub` (customer id), `tid`, `iss="ubb"`, 900 s expiry (`create_widget_token (12-20)`, `verify_widget_token (23-59)`).
Used only by `me_router`. No route returns the widget secret; the operator hands it over.

---

## 17. SDK v4 (`ubb-sdk/`)

**CODE VERIFIED / TEST VERIFIED (471 tests passed this session; `ubb.__version__ == "4.0.0"`;
`ubb.__spec_revision__` equals the SHA-256 of `openapi/v1.json`, `f9e2cabc…9d92`).**

- Layout: generated core `ubb/_core/` (openapi-python-client 0.29.0: 458 models, 160 operation modules, sync and
  async), `ubb/_exceptions_generated.py` (from `error-codes.json`), `ubb/_spec_revision.py` (the stamp, written by
  `codegen/generate_core.py :: _write_spec_stamp (68-81)`), `ubb/_operations.py` and `ubb/vocabulary.py` (from
  `tools.sdk_operations` and `tools.vocabulary`). Hand-written shell: `client.py`, `metering.py`, `billing.py`,
  `subscriptions.py`, `referrals.py`, `spend_controls.py`, `webhooks.py`, `exceptions.py`, `types.py`, `retry.py`,
  `_http.py`, `_models.py`. The shell is synchronous and owns transport through `httpx`; it parses into generated
  models (`_models.py :: from_wire (118-136)`). CI regenerates the core and fails on any diff.
- `UBBClient.__init__ (client.py 59-101)`: `(api_key, base_url="http://localhost:8001", timeout=10.0,
  widget_secret=None, tenant_id=None, max_retries=3, metering=True, billing=False, subscriptions=False,
  referrals=False)`. **No environment variable is read**; `base_url` must be set explicitly in production.
- Retries (`retry.py :: request_with_retry (49-79)`): connection errors and 429/502/503/504, exponential with jitter
  capped at 10 s, `Retry-After` honoured up to 30 s, applied to every method including POST — safe because the server
  replays on the idempotency key.
- Usage: `MeteringClient.record_usage (metering.py 567-741)` — the caller supplies `idempotency_key` (the SDK never
  mints one), measurements as exact text (floats refused), `recorded_at` → `effective_at` (naive refused); a stop raises
  `UBBStopRequested` (a `BaseException`, `exceptions.py (143-228)`) unless `stop_behavior="return"`.
  `record_batch (743-840)` up to 100 items, per-item results, never raises on a stop.
- Tasks: `start_task (842-899)` → `StartedTask (326-525)`, a context manager with `complete()`, `fail()`, `cancel()`;
  a clean exit with nothing declared raises `TaskOutcomeRequired`; an escaping `Exception` declares `failed`.
  A subtask is `start_task(..., parent_task_id=…)`.
- Webhooks: `webhooks.py :: verify_webhook (85-140)` checks `X-UBB-Signature-V2` (HMAC-SHA256 over `"{t}.{body}"`,
  300 s tolerance, multiple `v1=` during rotation); `verify_webhook_legacy (143-163)`.
- Coverage (`ubb-sdk/operation-coverage.yaml`): 75 operations wrapped, 85 generated-only (incl. all `/me/*`, the Code
  Builder routes, webhook config CRUD, Event Type declaration, book publishes), 0 unaccounted; gaps are signed in
  `coverage-authorisations.yaml`.
- Release: `ubb-sdk/release/build_wheel.py` builds twice on Python 3.13 from an annotated `sdk-vX.Y.Z` tag and writes
  `<tag>.release.json`; nothing publishes to PyPI (`CHANGELOG.md:17`). The v4.0.0 wheel's SHA-256 is recorded in
  `CHANGELOG.md (38-46)` and in the project folder (`R10-W6-RELEASE/`).
- Docs: `ubb-sdk/README.md` (quick start says `pip install ubb-sdk`, which is not how it is delivered; its
  `UBBClient` signature at 692-694 is also stale), `MIGRATION.md`, `CHANGELOG.md`.

---

## 18. Code Builder and generated integration

**CODE VERIFIED.** Server: `api/v1/code_builder_endpoints.py` (metering-gated) — `POST /code-builder/blueprints`
`resolve_blueprint (71-113)` (READ; `draft_preview=true` needs ADMIN and stores nothing), `GET
/code-builder/blueprints/{fingerprint}` `get_blueprint (116-136)`, `POST …/{fingerprint}/verify` `verify_blueprint
(139-189)` (WRITE; runs in a rolled-back temporary tenant, `api/v1/verification.py :: verify (151)`). Resolution in
`api/v1/integration_blueprint.py :: resolve (675-733)`; `SCHEMA_VERSION = 1 (200)`, `RENDERER_CONTRACT_VERSION = 3
(227)`, `SDK_MAJOR_VERSION = {python_sdk: 4, shell_http: None} (236)`, at most 50 selected types. Input
`IntegrationBlueprintSelectionIn (schemas.py 5273-5299)`: `target` `python_sdk|shell_http`, `task_type`,
`event_types[]`, `subtask_types[]`. Output `ResolvedIntegrationBlueprint (5412-5444)` with a `sha256:` fingerprint,
`readiness` `scaffold|blocked|complete`, call tokens bound as `platform_known|runtime_bound|secret_reference`,
diagnostics with remediation requests. Storage: `apps/platform/code_builder/models.py :: BlueprintSnapshot (53-104)`,
unique per tenant and fingerprint, 30-day retention, pruned daily (`code_builder/tasks.py :: prune_blueprint_snapshots (20)`).

Renderer: `apps/codegen/src/render.ts :: render (70-89)` reads schema 1 / renderer contract 3;
`catalogue.ts :: CATALOGUE_VERSION = 10 (37)`; Python target files `ubb_integration.py`, `call_sites/*.py`,
`.env.example`, `verify_integration.py` (env `UBB_API_KEY`, `UBB_BASE_URL`, no default host); shell target
`ubb_integration.sh` (sourced), `call_sites/*.sh`, `request_previews/*.http`, exit status 20 for a stop. The
renderer runs in the console (`apps/ui/src/features/developers/…/code-builder-page.tsx`); nothing server-side renders
code. (`apps/codegen/README.md` is stale: it says SDK v3 and `catalogue.v9.json`.)

Tests: `api/v1/tests/test_the_integration_blueprint.py`, `test_verifying_a_blueprint.py`, renderer snapshot and
execution suites (`apps/codegen/tests/`, CI job `codegen`), and the Docker-backed execution suite
`tests/code_builder_execution/` (CI job `code-builder-execution`). **NOT VERIFIED in this session**: the TypeScript
renderer and execution suites were not run here (they need pnpm and Docker images; CI runs them).

---

## 19. Reporting and the #561 usage summary

**CODE VERIFIED / TEST VERIFIED (local run).** `GET /api/v1/me/economics` → `api/v1/me_endpoints.py ::
get_my_economics (461-499)`, `me_router` auth `WidgetJWTAuth` (35), metering-gated; no customer selector (scope from
the token's `sub`); computed by `api/v1/economic_question.py :: ask_the_economic_query (17-74)` with fixed
`WIDGET_MEASURES` = customer revenue and recorded events. Response `MeEconomicsOut (424-445)`: `period_start`,
`period_end`, `basis` (`recorded`), `currency`, `customer_revenue{amount_micros, status, available_from}`,
`recorded_events{count, status, available_from}`, `foreign_currency_subscription_count`. In the local run it answered
`recorded_events {count 1, status known}` and `customer_revenue {amount_micros 1200000, status known}` and refused
the tenant API key with 401. Pinned by `api/v1/tests/test_an_end_customer_reads_its_own_usage.py` (part of chunk A).
Other `/me/*` routes (balance, grants, transactions, top-up, invoices) gate on `billing`. **There is no embeddable
widget**; the console contains no `/me` consumer (its typed clients exclude `/api/v1/me/**`, `apps/ui/src/api/client.ts (47-48)`).

Other reports (CONTRACT VERIFIED): `GET /spend-controls/stops-and-breaches` and `/utilisation-and-headroom`
(`api/v1/spend_control_endpoints.py (416-468)`, ungated, window ≤ 366 days); `GET /metering/analytics/tasks`;
`GET /metering/analytics/economics`; `GET /audit/records` (`api/v1/audit_endpoints.py (61-81)`, cursor-paginated —
**TEST VERIFIED (local run)**: ten records naming the probe's acts); tenant billing periods and invoices; usage
invoices (billing product).

---

## 20. Console surfaces that genuinely exist (`apps/ui`)

**CODE VERIFIED.** Routes under `apps/ui/src/app/routes/_app/`: `/` (overview), `/events`, `/events/$eventId`,
`/tasks`, `/tasks/kinds/$key`, `/tasks/runs`, `/tasks/runs/$taskId`, `/customers`, `/customers/$customerId`,
`/pricing`, `/pricing/$bookId`, `/billing` (billing product), `/plans` (billing product), `/referrals`,
`/referrals/$customerId` (referrals product), `/spend-controls`, `/webhooks`, `/webhooks/$configId`, `/developers`
(API keys, sandbox, Code Builder card), `/developers/code-builder`, `/settings` (workspace, team, products, billing,
audit), `/sign-in`. Provider switch `VITE_API_PROVIDER=mock|api` (default `mock`, `src/lib/api-provider.ts (1-19)`);
`VITE_API_URL`; `VITE_CLERK_PUBLISHABLE_KEY` required in `api` mode; the Vite dev proxy targets `localhost:8000`.
Auth: the Clerk session JWT as a bearer; roles resolved client-side from `/tenant/members`, enforced server-side.
Generated client from `src/api/schema.json` (tracked; identical to `openapi/v1.json`) via `openapi-typescript`
(output gitignored). CI runs `pnpm ui:api:check`, typecheck and vitest (about 138 test files); **lint and `vite build`
are not run in CI**. **NOT VERIFIED in this session**: the console was not built or run here. It is a tenant console
("UBB Tenant Console", `apps/ui/README.md:1`); the only operator surface is Django admin.

---

## 21. Webhook delivery (outbound)

**CODE VERIFIED.** Models `apps/platform/events/webhook_models.py :: TenantWebhookConfig (7-73)` (`url`, `secret`
stored in plaintext, `retiring_secret` + expiry for rotation, `event_types` with `["*"]`, `is_active`; unique per
tenant and url) and `WebhookDeliveryAttempt (76-94)`. Routes `apps/platform/events/api/webhook_endpoints.py`:
create (secret ≥ 32 chars, event types required), list, delete, patch (secret not patchable), rotate-secret (1–168 h
overlap), deliveries. URL rule `core/url_validation.py :: validate_webhook_url (6-53)`: https only, literal loopback
hosts refused, DNS resolved and private/loopback/link-local/reserved addresses refused; applied at create, on a URL
change, and again at send time with the connection pinned to the validated IP (`events/webhooks.py :: _PinnedIPBackend
(45-77)`). **TEST VERIFIED (local run):** `http://127.0.0.1:9/hook` → 422 "Webhook URL must use https scheme";
`https://localhost/hook` → 422. Delivery `events/webhooks.py :: deliver_webhook (131-193)` → `_deliver_to_config
(196-302)`: 10 s timeout, envelope `event_type, event_id, tenant_id, timestamp, livemode, data`, headers
`X-UBB-Signature` (legacy, body only), `X-UBB-Signature-V2` (`t=…,v1=…`, one `v1` per active secret), `X-UBB-Event-Type`;
retryable failures (`httpx.HTTPError`, `OSError`, 5xx, 429) raise `WebhookDeliveryIncomplete` back into the outbox
backoff; 3xx/4xx are permanent. The HTTP call runs inside `process_single_event`'s transaction (an observation, not a
blocker). Cleanup daily (`tasks_webhook_cleanup.py (12-35)`: success after 30 days, failure after 90).

**Outbox (CODE VERIFIED).** `events/outbox.py :: write_event (43-62)` requires an open atomic block, writes
`OutboxEvent` (`events/models.py (17-44)`: status pending/processing/processed/failed, `retry_count`, `max_retries` 5,
`next_retry_at`, `correlation_id`) and registers an on-commit `_dispatch (25-40)` → `process_single_event.delay`.
`events/tasks.py :: process_single_event (53-88)` (queue `ubb_events`, `select_for_update(skip_locked=True)`, handlers
via `dispatch.py :: dispatch_to_handlers (37-82)` with product gating and `HandlerCheckpoint` per handler);
`sweep_outbox (91-139)` minutely re-dispatches ≤ 100 due pending rows and reclaims ≤ 50 stuck rows; `cleanup_outbox
(142-162)` deletes processed rows after 30 days, never failed ones; `alert_dead_letter (36-50)` logs CRITICAL
`outbox.dead_letter`. Note: with `max_retries = 5` the fifth failure dead-letters before the 7200 s step is used, so
the real horizon is about 42.5 minutes, not the "~2h43m" the comment at line 23 states (`RETRY_HORIZON` is read by
two repair jobs; an observation for Ash, not a launch blocker).

---

## 22. Configuration and secrets

**CODE VERIFIED (`config/settings.py`).** `load_dotenv()` at line 6 fills unset names from a `.env` if present (the
image must not carry one). `SECRET_KEY` required (12). `DEBUG` (14); `ALLOWED_HOSTS` required when `DEBUG` is false
(16-20). `DATABASE_URL` (via dj-database-url). `REDIS_URL` (125). `UBB_MEASUREMENT_RETENTION_DAYS` (319-320, default
400; non-integer stops start-up). `UBB_POSTPAID_PUSH_MAX_ATTEMPTS`, `UBB_POSTPAID_PUSH_MAX_AGE_HOURS` (306-307).
`UBB_MIN_BALANCE_DEFAULT`, `UBB_INVOICE_PERIOD_DAYS`, `UBB_PLATFORM_FEE_PERCENTAGE` (297-303) are read by nothing else.
Stripe (355-364): `STRIPE_SECRET_KEY`, `STRIPE_CONNECT_CLIENT_ID`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_TEST_SECRET_KEY`,
`STRIPE_TEST_WEBHOOK_SECRET`, `STRIPE_CONNECT_TEST_CLIENT_ID`. Clerk (379-382): `CLERK_ISSUER`, `CLERK_JWKS_URL`,
`CLERK_JWT_PUBLIC_KEY`, `CLERK_HS256_SECRET` (dev only; RS256 needs `cryptography`, which is not in the lock).
`CORS_ALLOWED_ORIGINS` (385-387). Security when `DEBUG` is false (390-401): SSL redirect, `SECURE_PROXY_SSL_HEADER
= X-Forwarded-Proto`, HSTS one year with preload, secure cookies — so a plain-HTTP health probe answers 301 unless the
proxy sets `X-Forwarded-Proto: https`. `.env.example` lists three names nothing reads (`UBB_ARREARS_DEFAULT_THRESHOLD`,
`UBB_TOPUP_SUCCESS_URL`, `UBB_TOPUP_CANCEL_URL`) and omits `ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS`,
`UBB_MEASUREMENT_RETENTION_DAYS`. Tenant webhook signing secrets and widget secrets are database data, not deployment
config.

**Logging (CODE VERIFIED, `settings.py :: LOGGING (326-352)`).** One console handler with `core.logging.JsonFormatter`
(fields `timestamp, level, logger, correlation_id, message, data, exception`) and a redacting filter; loggers `apps`,
`core`, `api`, `celery` at INFO, `django.request` and `stripe` at WARNING, root WARNING. **Twenty-two call sites log
under `ubb.*` names** (`ubb.events`, `ubb.webhooks`, `ubb.billing`, `ubb.auth`, `ubb.audit`), which are not configured
and therefore inherit root WARNING: their INFO lines (`outbox.sweep`, `outbox.cleanup`, `measurement_prune.completed`,
handler skips) are dropped; WARNING and CRITICAL (`outbox.dead_letter`, drift spikes) still reach the console. This
is why the local worker and beat logs in this session showed only their start-up banners. Alerting is log-only;
there is no metrics or tracing integration.

---

## 23. CI, contracts and codegen checks

**CODE VERIFIED (`.github/workflows/ci.yml`, the only workflow; `on: push` and `pull_request`).** Python 3.13, Node
22, pnpm 10.28.2, services `postgres:16` and `redis:7`, env `DEBUG=True` and dummy Stripe keys (so CI never
exercises the production security block or `ALLOWED_HOSTS`).

| Job (check name) | What it runs |
|---|---|
| `test` | lock install + `pip install -e ./ubb-sdk`; `manage.py check`; `makemigrations --check --dry-run`; platform pytest; SDK pytest |
| `contracts` | `tools.vocabulary --write` and `tools.sdk_operations --write` must leave a clean tree; `pytest tests/contracts`; `tools.gates ratchet`; `tools.sdk_operations ratchet` |
| `conformance` | Schemathesis fuzz of the platform against `v1.json`; **`continue-on-error: true` (non-gating)** |
| `contract` | drift gate (`scripts/export_openapi.py` + `git diff --exit-code`); SDK core and exceptions regeneration gates; oasdiff 1.23.0 breaking gate `openapi/contract_gate.py` against `api-v1-cutover`; `pnpm ui:api:check`; openapi-typescript smoke; console typecheck and vitest |
| `codegen` | `apps/codegen` typecheck, lint, test |
| `code-builder-execution` | Docker-backed execution of rendered integrations against a live server |

There is no deploy, release or image-build job and no `permissions:` block. The guard checks the W7 brief names
(`test`, `contracts`, `contract`, `codegen`, `code-builder-execution`) are these job ids. **Native required checks on
`main` are not configured** (the repository owner lacks admin; the merge guard `R10-merge-guard.py` in the project
folder substitutes under the W7 governance exception).

**Regeneration order after a surface change (CODE VERIFIED from `openapi/README.md` and CI):** `python -m
tools.vocabulary --write` (if the registry changed) → `ubb-platform/scripts/export_openapi.py` →
`ubb-sdk/codegen/generate_core.py` (+ `generate_exceptions.py` if error codes changed) → `python -m
tools.sdk_operations --write` → `pnpm ui:api:sync` → if breaking, `python openapi/contract_gate.py --baseline
origin/main --emit` into the suppression files (both are header-only at this commit).

**TEST VERIFIED (this session):** `manage.py check` clean; `makemigrations --check` no changes (fresh DB);
`export_openapi.py` byte-identical; `tools.gates` 27 gates installed, ledger 0, 3 deferred obligations (the human acts
O1–O3: audit, admission, rail activation); `tools.forbidden_terms` 0 retired terms on a living surface;
`tools.vocabulary --write` 4 artefacts already up to date; `tests/contracts` 845 passed; SDK 471 passed; boundary
test 11 passed; readiness regression files 78 passed. Platform chunks: see `00-README.md`.

---

## 24. Release identity and evidence tooling

**CODE VERIFIED.** In the repository: the SDK release recipe (`ubb-sdk/release/build_wheel.py`, `release_identity (206)`),
the spec stamp, and the tags `api-v1-cutover` / `sdk-v4.0.0` (both `c2eb35ff`) and `api-v1-launch` (`ac6ca816`, never
moved). **Nothing in the platform reports a release SHA or image digest** (no build-info endpoint, no `GIT_SHA` env;
`/api/v1/health` returns `{"status":"ok"}` only), and the W7 brief forbids adding one. The release-evidence tool is
project-folder tooling, not repository code: `C:\Users\tom_l\.claude\projects\C--Users-tom-l-git-ubb\R10-W7-RELEASE-EVIDENCE.py`
(`record <sha>` → `artifact … --image --docker` → `deploy … --web --worker --beat` → `verify …`), with the F8 fix
applied and re-validated there (`R10-W7-PREP/release-evidence-dryrun/`). `tools/verify_w6_release.py`, named in
earlier notes, lives in the project folder's `tools/`, not in the repository (CODE VERIFIED by `ls`).
ADR-0026 states the release-evidence shape and that nothing was ever deployed (`docs/adr/0026-…md` lines 15, 27).

---

## 25. Deployment runtime shape: one image, web + worker + beat + migration

**DOCUMENTED INTENT ONLY in the repository; demonstrated by the prep pass, not committed.** The W7 brief (§0.1, §0.5)
requires one OCI image built from the recorded SHA with label `org.opencontainers.image.revision=<sha>`, deployed by
digest as three long-running roles plus a one-off migration. The repository holds none of it. The prep pass's draft
(`R10-W7-PREP/image/Dockerfile`, never committed) established, on local Docker, the facts the real deployment files
must carry (`R10-W7-PREP/01-image-four-invocations.md` F9):

1. build context = a clean `git archive <sha> ubb-platform openapi` (the app reads `openapi/error-codes.json` from
   the repository root at import, so the image keeps the repository shape, e.g. `/srv/ubb/ubb-platform` beside
   `/srv/ubb/openapi`);
2. add a WSGI server at the image layer (the lock has none; the draft used `gunicorn==23.0.0` serving
   `config.wsgi:application`);
3. roles from the same digest: web (`gunicorn`), worker (`celery -A config worker -l INFO -Q <nine queues>`), beat
   (`celery -A config beat -l INFO --schedule <writable path>`, exactly one replica), migration (`python manage.py
   migrate --noinput`, one-off);
4. `DEBUG=False` turns on the HTTPS block: the health check must arrive with `X-Forwarded-Proto: https` or through
   the TLS proxy, and the proxy must preserve `Host` (an unlisted host answers 400);
5. warm-up: a gunicorn worker's first routed request costs 0.7–3 s locally;
6. logs are JSON from the app plus the access log, and Celery's plain text from worker and beat; the drain must take
   both;
7. no `.env` in the image; secrets only through the host's mechanism;
8. the minimal production set for an `external` tenant (names only): `SECRET_KEY`, `DATABASE_URL`, `REDIS_URL`,
   `ALLOWED_HOSTS`, `DEBUG=false`, `UBB_MEASUREMENT_RETENTION_DAYS=400`; no Stripe secret is needed now that F5 fails
   closed; no `CELERY_BROKER_URL` workaround now that F1 is fixed in the product.

The local run in this session used Django's `runserver`, which is explicitly not a production server; it proves the
application, not the image.

---

## Runtime/data-flow walkthrough

### One ordinary usage event (as implemented at this commit; CODE VERIFIED, exercised in the local run)

1. **Request and authentication.** `POST /api/v1/metering/usage` with `Authorization: Bearer ubb_live_…`.
   `core/auth.py :: ApiKeyAuth.authenticate (50-74)` hashes the token, loads the active key and tenant, sets
   `request.tenant`, buffers `apikey_used:{pk}` in Redis, sets the audit actor. `role_floor(WRITE)` and
   `ProductAccess("metering")` apply. `CorrelationIdMiddleware` has already stamped a correlation id.
2. **Validation.** Pydantic parses `RecordUsageRequest`: quantities must be canonical decimal text; a caller-stated
   price is refused. `record (668-688)` loads the Customer (and Task) in tenant scope (404 otherwise).
   `replay_or_record (549-613)`: replay on the idempotency key first; then the last published Event Type declaration,
   supplier admission, supplier-cost field admission, quantity admission against declared value types, grouping-field
   admission (new values written in a separate commit); `validate_effective_at`; USD only.
3. **Persistence and pricing (one transaction, `_record_core`).** `PricingService.price` resolves the supplier cost
   (reported or calculated from cost-book rules) and the customer price (override book → plan book → default book →
   markup rung), builds the receipt; `Posting` and `PostingMeasurement` are inserted (the database checks the
   amount/status pairs; the receipt is sealed once complete); an unrecognised name is held; if a Task is named,
   `accumulate_cost` locks parent then child and rolls the amounts up, returning any ceiling crossing; under
   `enforcing` the Redis live counter is debited; the `StopAcknowledgement` is written; `stop_context` is tagged;
   closed months are marked dirty; `write_event(UsageRecorded)` inserts the outbox row.
4. **Asynchronous processing.** On commit: `outbox._dispatch` enqueues `process_single_event` on `ubb_events`
   (reaches the broker because `config/__init__.py` loads the app in the web process); any kill plan runs
   `kill_and_announce` in its own transaction and writes `task.killed`/`subtask.killed`. The worker locks the row,
   runs the registered handlers under product gating — `platform.webhook_delivery.usage.recorded`,
   `subscriptions.cost_accumulator` (metering), `billing.wallet_deduction` (billing only), `referrals.reward_accumulator`
   (referrals only) — and checkpoints each. Failures back off 30 s → 2 m → 10 m → 30 m and dead-letter on the fifth.
   Beat's minutely `sweep_outbox` re-dispatches anything the doorbell missed.
5. **Controls.** The ceiling decision happened in step 3; customer-wide stops open through `drive_stop` on the live
   lane (sync, enforcing only), the durable lane (the billing handler, billing only) or the hourly reconcile/patrol.
6. **Webhook and result.** The response is the 200 acknowledgement with the receipt and the stop block; if the
   tenant registered a public https endpoint for `usage.recorded`, the worker POSTs the signed envelope and records a
   `WebhookDeliveryAttempt`.
7. **Client readback.** `GET /metering/usage/{event_id}` (receipt, `measurements_status`), `GET
   /metering/customers/{id}/usage`, `GET /tasks/{id}` (rollups), `GET /metering/analytics/economics`, `GET
   /spend-controls/…`, `GET /audit/records`; the end customer reads `GET /me/economics` with a widget token.

### One Task lifecycle (CODE VERIFIED, exercised in the local run)

1. `POST /tasks` with the client's idempotency key → `task_endpoints.py :: start (174-396)`: claim the key (a replay
   returns the same unit with `replayed: true`; a different description is 409), admission control, the wallet check
   only when the tenant has `billing`, parent resolution, start policy (ceiling rung, expiry windows → frozen snapshot
   on the row, pricing mode), agreed price for fixed-price kinds, `create_task`, reservation (prepaid only). Response:
   the task id, its ceiling and windows.
2. Usage events name `task_id`; each one's `accumulate_cost` updates `recorded_events`, totals or unresolved/unpriced
   counts, and `last_event_at`; a ceiling crossing kills the unit (and contained work) on commit and announces it.
3. `POST /tasks/{id}/close` with `outcome delivered|failed|cancelled` → `close_task (1406-1441)` → `_flip`: the
   winner writes the outcome, cascades `cancelled`/`parent_closed` to open subtasks, notifies terminal listeners (the
   reservation is released), and for delivered fixed-price work writes the `Charge`, projected onto one
   `task_charge` posting. A second close with the same outcome is a replay; a conflicting one is 409.
4. If the client never closes: `close_abandoned_tasks` (every 15 min) expires work silently after an hour of
   silence; for `enforcing` tenants `reap_stale_tasks` (every 5 min) expires and announces `task.expired` using the
   live windows.
5. Readback: `GET /tasks/{id}` (`status`, `recorded_events`, totals, `ceiling_status`, stop facts, windows),
   `GET /tasks/{id}/subtasks`, `GET /metering/analytics/tasks`.
