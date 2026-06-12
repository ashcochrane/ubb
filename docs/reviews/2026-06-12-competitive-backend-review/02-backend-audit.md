# Backend audit — 12 categories vs best practice for a usage-based billing vendor

**Date:** 2026-06-12
**Scope:** the UBB platform repo (branch `tl-changes-05-06-26`, working tree clean at audit time).
**Method:** synthesized from five structured code audits of this repo (every claim carries a file:line anchor into the tree as audited) plus competitor fact sheets sourced from vendor-published pages, all accessed 2026-06-12 (every competitor claim cites its URL inline). The "APIs & backend logic" category had no dedicated source audit; its evidence was gathered directly from the repo for this document and anchors were verified the same way. Where evidence is missing — in the repo or about a competitor — this document says so plainly rather than guessing.

**Severity vocabulary:** `blocker` (cannot responsibly take production money traffic), `major` (material gap vs what a billing vendor's customers assume), `moderate` (real but bounded), `minor` (hygiene).

---

## Table of contents

1. [Scorecard](#scorecard)
2. [APIs & backend logic](#1-apis--backend-logic)
3. [Database & storage](#2-database--storage)
4. [Auth & permissions](#3-auth--permissions)
5. [Hosting & deployment](#4-hosting--deployment)
6. [Cloud & compute](#5-cloud--compute)
7. [CI/CD & version control](#6-cicd--version-control)
8. [Security & RLS](#7-security--rls)
9. [Rate limiting](#8-rate-limiting)
10. [Caching & CDN](#9-caching--cdn)
11. [Load balancing & scaling](#10-load-balancing--scaling)
12. [Error tracking & logs](#11-error-tracking--logs)
13. [Availability & recovery](#12-availability--recovery)
14. [Consolidated prioritized action plan](#consolidated-prioritized-action-plan)

---

## Scorecard

| # | Category | Relevance to a billing vendor | Verdict | One-line state |
|---|----------|------------------------------|---------|----------------|
| 1 | APIs & backend logic | critical | **adequate** | Disciplined idempotent, typed-error API with unbounded dedup and a 34-day backfill window; ingestion is synchronous-priced only — no async/high-volume path. |
| 2 | Database & storage | critical | **adequate** | Micros-everywhere money, constraint-encoded invariants, real migration discipline; no partitioning, no backups, no warehouse export. |
| 3 | Auth & permissions | critical | **adequate** | Hashed bearer keys, next-request revocation, live/test isolation; no key scopes — every key carries full tenant power including money movement. |
| 4 | Hosting & deployment | critical | **weak** | No app container, no production server installed, no deploy pipeline; the only compose file runs Postgres+Redis and nothing else. |
| 5 | Cloud & compute | high | **weak** | Topology fully derivable from code with safe Celery defaults, but beat is an unprotected SPOF and observability is absent. |
| 6 | CI/CD & version control | critical | **weak** | A well-written CI workflow that has never executed; 221-commit branch-as-trunk with 46 commits existing only on one laptop; no deploy, scan, lint, or coverage stage. |
| 7 | Security & RLS | critical | **adequate** | Systematic app-level tenant scoping, real SSRF defense, signed+replay-bounded webhooks, no committed secrets; no RLS second line, no dependency scanning, no compliance artifacts. |
| 8 | Rate limiting | high | **weak** | The only limiter guards the *optional* pre-check path; the ingest chokepoints, API keys, and IPs are entirely unthrottled. |
| 9 | Caching & CDN | high | **adequate** | Redis-as-cache-not-ledger discipline with engineered fail-open everywhere — undone by one unguarded `cache.set` on the auth hot path. |
| 10 | Load balancing & scaling | high | **weak** | Replica-safe stateless web tier with nothing to run replicas on; per-event synchronous pricing caps throughput orders of magnitude below competitor claims. |
| 11 | Error tracking & logs | critical | **weak** | Strong structured/redacting/correlated logging that terminates in an unwatched stdout; zero error tracking, metrics, or paging. |
| 12 | Availability & recovery | critical | **weak** | A genuine outbox + reconcile self-healing lattice built on top of zero backups, three single points of failure, and log-only alerting. |

The pattern across the table is consistent: **the domain layer (money correctness, idempotency, tenant isolation, self-healing) is unusually strong for this stage; the operational layer (deploy, observe, back up, scale, throttle) is largely absent.** The competitors compared below are weakest where UBB is strong and strong where UBB is weak.

---

## 1. APIs & backend logic

**Relevance: critical. Verdict: adequate.**

*(No dedicated source audit existed for this category; the following anchors were gathered and verified directly from the repo for this document.)*

### What exists

- **Single + batch ingestion endpoints** with typed request schemas: `POST /api/v1/metering/usage` (ubb-platform/api/v1/metering_endpoints.py:42-103) and `POST /usage/batch` accepting 1–100 items (`UsageBatchRequest` with `min_length=1, max_length=100`, ubb-platform/api/v1/schemas.py:56-57; endpoint at metering_endpoints.py:184-205).
- **Idempotency is DB-enforced and replay-first:** `record_usage` checks `(tenant, customer, idempotency_key)` before any validation and returns the original event on replay — explicitly *before* effective_at validation so a whole-batch retry succeeds even if the backfill window has since aged past the timestamp (ubb-platform/apps/metering/usage/services/usage_service.py:122-128). A raced duplicate insert is caught via IntegrityError and resolved back to the existing event (usage_service.py:187-197). The dedup window is **unbounded** (a permanent unique constraint, not a TTL).
- **Batch semantics are deliberate and documented in code:** each item runs as an independent atomic commit ("deliberately NOT one mega-transaction, which would hold Run/counter locks for the whole batch"), always HTTP 200 with positionally aligned per-item results and `succeeded`/`failed` counts; per-item error bodies mirror the single endpoint byte-for-byte (metering_endpoints.py:106-205).
- **Typed error envelopes** rather than bare 500s: `hard_stop_exceeded` (429, with run-kill side effect), `run_not_active` (409), `pricing_error` (422), typed `EffectiveAtError` codes (422), generic validation (422) (metering_endpoints.py:72-100).
- **Backfill window is first-class and tenant-configurable:** `Tenant.backfill_window_days` defaults to **34 days**, clean-validated to 0–60 with the 60-day cap reasoned against the reconcile horizon (ubb-platform/apps/platform/tenants/models.py:60-64,110-113); past-dated `effective_at` outside the window raises `effective_at_too_old` (usage_service.py:37,59-61).
- **Money mutation endpoints carry body-level idempotency keys:** withdraw, debit, credit, grant all require/accept `idempotency_key` (schemas.py:140-199), backed by the wallet partial-unique constraint (see §2).
- **Input validation at the edge:** cost fields bounded `ge=0, le=999_999_999_999`, `usage_metrics` values validated non-negative, currency pinned to the tenant's single currency at a documented choke point (schemas.py:30-44; usage_service.py:135-147), cursor pagination with clamped limits (metering_endpoints.py:208-230).
- **Pricing runs inside the ingest transaction** with versioned rate cards priced `as_of=effective_at` and tier ladders advanced under a row lock inside a savepoint so raced duplicates roll back the ladder advance (usage_service.py:156-186).

### Competitor evidence

- **Metronome:** `/ingest` accepts 1–100 events per request; `transaction_id` is the idempotency key with a **34-day dedup window**; backdating up to 34 days "will immediately impact live customer spend" (https://docs.metronome.com/api-reference/usage/ingest-events). A separate `Idempotency-Key` header on POSTs is cached ≥24h, replays the original result, and 409s on same-key-different-params — "even if a request returns an HTTP 500 error" (https://docs.metronome.com/developer-resources/use-api/idempotency/). Invoice finalization has a 24h default grace period for late events (https://docs.metronome.com/guides/get-started/core-concepts/how-invoicing-works).
- **Orb:** 500 events per batch by default; per-event `idempotency_key` deduplicated within the account grace period; event `properties` allow primitives only (https://docs.withorb.com/events-and-metrics/event-ingestion; https://docs.withorb.com/quickstart/ingest). General-API `Idempotency-Key` header valid 48h with an `Idempotent-Replayed: true` response header and 409 on conflicting reuse (https://docs.withorb.com/api-reference/idempotency). Backfills are "always audit-safe" — originals archived, never overwritten or deleted (https://docs.withorb.com/guides/events-and-metrics/reporting-errors).
- **Lago:** `POST /events/batch` accepts up to 100 events, rejects the whole batch if any item fails structural validation, and processes asynchronously (https://getlago.com/docs/api-reference/events/batch; whole-batch rejection per https://getlago.com/docs/guide/events/ingesting-usage). Idempotency keyed on `transaction_id` across REST/Kafka/S3 channels — with the caveat that the ClickHouse pipeline *overwrites* on identical `transaction_id + timestamp` (https://getlago.com/docs/guide/events/ingesting-usage).
- **Stripe Billing Meters:** idempotency via the `identifier` field (auto-generated if omitted); timestamps accepted within the past 35 calendar days and max 5 minutes future (https://docs.stripe.com/billing/subscriptions/usage-based/recording-usage-api).
- **OpenMeter:** ingestion in CloudEvents format (https://github.com/openmeterio/openmeter).

**Where UBB stands:** batch size (100) matches Metronome and Lago, below Orb's 500. The 34-day default backfill window matches Metronome's exactly and is tenant-tunable (0–60 days), versus Stripe's documented 35-day window (no configurability documented). The unbounded DB-constraint dedup is *stronger* than every competitor's TTL'd window. UBB's per-item-isolated batch (partial success, positionally aligned results) is a better failure contract than Lago's all-or-nothing batch. What every competitor has that UBB lacks: an asynchronous, decoupled ingest pipeline (Lago processes events async even in OSS; Metronome/Orb ingest at 100k–250k+ events/s — see §10) and a general-purpose `Idempotency-Key` *header* convention covering all POST mutations uniformly rather than per-endpoint body fields.

### Gaps

| Gap | Severity |
|---|---|
| Ingestion is synchronous-priced-in-transaction only: every event costs ~9–13 DB round trips before the HTTP response (see §10), and the batch endpoint runs items sequentially in one request — batch makes latency 100× worse, not throughput better (metering_endpoints.py:201-202). No async accept-then-price path exists. | major |
| `RecordUsageRequest.metadata` is an unbounded dict (schemas.py:29) and `usage_metrics` has no key-count bound (schemas.py:32) — see §2 for the storage consequence. | moderate |
| No general `Idempotency-Key` header convention for non-ingest POSTs; idempotency is per-endpoint body fields, and read-modify endpoints without a body key (e.g. config PUTs) rely on last-write-wins. | minor |

### Actions

1. Build the async ingest path (accept + persist raw, price in workers under the same idempotency keys) before any high-volume tenant — this is the same action as §10's throughput gap.
2. Bound `metadata` and `usage_metrics` in the pydantic schema (see §2 action).
3. Document the idempotency contract (unbounded window, replay-wins semantics) in the public API docs — it is genuinely stronger than Metronome/Orb's and currently invisible to evaluators.

*(A future-timestamp cap was initially listed as a gap here; fact-checking found it already exists — `_FUTURE_SKEW = 5 minutes` at usage_service.py:19 with `effective_at_in_future` raised at :54-58, matching Stripe's documented posture.)*

---

## 2. Database & storage

**Relevance: critical. Verdict: adequate.**

### What exists

- **Postgres-first config:** `DATABASES` via dj_database_url with `CONN_MAX_AGE=600` and `CONN_HEALTH_CHECKS=True` (ubb-platform/config/settings.py:81-87); psycopg[binary]>=3.2 + Django 6.0 (ubb-platform/requirements.txt:3-4); `USE_TZ=True`/UTC (settings.py:98-100); postgres:16 in docker-compose.yml:2-3 and CI services (.github/workflows/ci.yml:38-39).
- **Money is BigInteger micros everywhere it is an amount:** `Wallet.balance_micros`, `WalletTransaction.amount_micros` + `balance_after_micros` (ubb-platform/apps/billing/wallets/models.py:26,46-47), CreditGrant granted/remaining/expired/voided micros (wallets/models.py:124-127), `UsageEvent.provider_cost_micros`/`billed_cost_micros` (ubb-platform/apps/metering/usage/models.py:30-31), invoice totals/residuals (ubb-platform/apps/billing/invoicing/models.py:67,92,96). DecimalField appears only for rates/percentages, never amounts.
- **Constraints genuinely encode the money invariants:** partial-unique `uq_wallet_txn_idempotency` on (wallet, idempotency_key) WHERE key IS NOT NULL — *this constraint is the exactly-once guarantee for credits/debits* (wallets/models.py:60-64); `uq_usage_event_idempotency_v2` (usage/models.py:48-51); CheckConstraints bounding grant remaining/refunds (wallets/models.py:148-152,192-200); state-machine partial uniques for open periods, pending top-ups, invoice-per-period, sandbox shape (ubb-platform/apps/billing/tenant_billing/models.py:47-51; topups/models.py:59-63; invoicing/models.py:106-107; tenants/models.py:84-90).
- **Soft-delete done carefully:** `SoftDeleteMixin` with undelete-only policy (ubb-platform/core/soft_delete.py:12-61); the Customer unique key is soft-delete-aware (customers/models.py:39-43); `lock_for_billing` restores a soft-deleted wallet rather than violating the OneToOne (ubb-platform/apps/billing/locking.py:26-38).
- **Index discipline incl. opclass awareness:** composite indexes on UsageEvent (usage/models.py:53-60); the tags GIN index was deliberately swapped from `jsonb_path_ops` to `jsonb_ops` (because `has_key` compiles to `?`) via CREATE/DROP INDEX CONCURRENTLY with `atomic=False`, a real reverse migration, and an INVALID-index recovery runbook (usage/migrations/0022_swap_tags_gin_to_jsonb_ops.py:1-87), with a test asserting the old index is gone (apps/metering/tests/test_analytics_scale.py:303-318).
- **Migration discipline:** 104 migrations across 14 apps; CI enforces `makemigrations --check --dry-run` (.github/workflows/ci.yml:88-90); data migrations ship RunPython backfills with explicit reverses (tenants/0012; wallets/0004; usage/0018, 0020).
- **Operational-table lifecycle is beat-scheduled:** outbox prune 30d/90d with failed never auto-deleted (ubb-platform/apps/platform/events/tasks.py:136-152); Stripe webhook events 90d/180d via PK-range batched deletes to avoid long locks (ubb-platform/apps/billing/stripe/tasks.py:11-43); delivery attempts 30d/90d (events/tasks_webhook_cleanup.py:13-29).
- **UsageEvent is immutable by code** (save raises on update, delete raises — usage/models.py:66-72) and is never pruned; no PARTITION anywhere in the apps.
- **JSONB bounded where it was designed:** tags validated at the choke point (≤50 keys, key regex, string values ≤256 chars — usage_service.py:77-94); `pricing_provenance` is platform-constructed and bounded; `line_snapshot` is frozen at first push claim (invoicing/models.py:88-91).
- **Backup/PITR: nothing in the repo** — repo-wide grep for pg_dump/PITR/pgbouncer/wal-g/pgbackrest/backup returns zero matches; the only deployment artifact is a docker-compose with one named volume (docker-compose.yml:12-13,22-23). **Read replicas/warehouse export: nothing** — no DATABASE_ROUTERS, no CDC, no S3/Snowflake/BigQuery sync.

### Competitor evidence

- **Lago's *default* self-host stack ships partition-aware Postgres:** `db = getlago/postgres-partman:15.0-alpine` in the canonical docker-compose (https://github.com/getlago/lago/blob/main/docker-compose.yml), and its at-scale events engine is ClickHouse fed by Kafka, with Postgres retained for transactional data (https://github.com/getlago/lago/wiki/Using-Clickhouse-to-scale-an-events-engine).
- **OpenMeter** runs Postgres for billing plus ClickHouse for real-time usage aggregation and Kafka for event streaming as its baseline architecture (https://github.com/openmeterio/openmeter).
- **Orb** commits to never overwriting or permanently deleting ingested usage data — backfilled originals are archived and remain queryable (https://docs.withorb.com/guides/events-and-metrics/reporting-errors). Metronome's status page lists "Data Export" as a first-class product component (https://status.metronome.com).

The pattern: every competitor treats the event store as a partitioned/append-only, analytically exportable stream, separate in kind from the transactional store. UBB stores events in one monolithic, ever-growing OLTP heap.

### Gaps

| Gap | Severity |
|---|---|
| **UsageEvent growth is unbounded with no partitioning, archival, or retention story.** At 100 events/s: ~3.15B rows/year; with ~0.5–1 KB/row and ~18 indexes on the table (8 single-column db_index fields at usage/models.py:17-43, FK auto-indexes, 4 composite indexes, unique constraint, GIN, PK), roughly 2–4+ TB/year in one heap. Partitioning cannot be retrofitted without a full rewrite. | major |
| **No backup/PITR posture anywhere** — the wallet ledger IS customer money; reconcile jobs repair drift vs Stripe but cannot repair a lost Postgres. | major (escalated to blocker in §12) |
| **No warehouse export, no read-replica routing** — analytics tag-grouping endpoints (api/v1/metering_endpoints.py:398-431) run on the OLTP primary serving the ingest hot path. | major |
| `UsageEvent.metadata` unbounded JSONField (schemas.py:29) and `usage_metrics` unbounded keys (schemas.py:32), unlike the tightly bounded tags — a misbehaving SDK can store megabytes per event in the hottest table. | moderate |
| `DATABASES` silently falls back to `sqlite:///db.sqlite3` (settings.py:82-84) while GIN migrations are vendor-guarded no-ops on SQLite — a misconfigured prod deploy boots quietly with missing indexes instead of failing loudly. | moderate |
| Index over-provisioning on the insert hot path: ~18 indexes on ubb_usage_event, several redundant (standalone idempotency_key index duplicates the unique constraint; single-column attribution indexes overlap the composite — usage/models.py:18,23-29,56-57). | moderate |
| Large-table backfills unbatched: usage/0020 and 0018 do full-table UPDATEs in atomic migrations; wallets/0004 loops row-by-row; cleanup_outbox uses one unbatched delete (events/tasks.py:142-152) while the Stripe cleanup correctly batches — the discipline exists but is inconsistent. | minor |
| Only usage/0022 builds indexes CONCURRENTLY; other index adds on the usage table are plain transactional CREATE INDEX. | minor |

### Actions

1. Adopt monthly range partitioning on ubb_usage_event (declarative + pg_partman, keyed on effective_at) **before meaningful data accrues**; detach-and-archive closed partitions past the reconcile horizon to object storage as Parquet.
2. Run on managed Postgres with PITR (or wal-g/pgbackrest + WAL archiving); write and rehearse a restore runbook that ends with re-running `reconcile_topups_with_stripe`/`reconcile_usage_drawdowns` to converge with Stripe.
3. Ship periodic Parquet export of UsageEvent (+ ledger + invoices) keyed by (tenant, day) as the v1 warehouse-sync feature; later CDC + a read-replica router for analytics endpoints.
4. Cap `metadata` serialized size (~16 KB) and bound `usage_metrics` keys in the schema, mirroring `validate_tags`.
5. Raise ImproperlyConfigured when `DATABASE_URL` is unset and `DEBUG=False`.
6. After a load test, drop `idx_scan=0` indexes via the established CONCURRENTLY pattern; make CONCURRENTLY + `atomic=False` the standing rule for event-scale tables; batch all backfills/cleanups by PK range.

---

## 3. Auth & permissions

**Relevance: critical. Verdict: adequate.**

### What exists

- **API key auth:** django-ninja HttpBearer (ubb-platform/core/auth.py:9-20); `TenantApiKey.verify_key` SHA-256-hashes the bearer token and does a per-request unique-indexed DB lookup with `select_related('tenant')`, filtered on key and tenant both active (ubb-platform/apps/platform/tenants/models.py:177-194). No caching ⇒ revocation/rotation effective on the very next request.
- **Live/test prefixes are enforced, not cosmetic:** `ubb_live_`/`ubb_test_` + `secrets.token_urlsafe(32)` (256-bit entropy) at mint (models.py:166-167); verify re-asserts prefix mode == `tenant.is_sandbox` (models.py:192-193), so a crafted test key can never resolve onto a live tenant.
- **Self-serve key lifecycle:** mint returns the raw key once; rotate is atomic mint-successor+deactivate-old; revoke refuses to kill the tenant's last active key (409) under `select_for_update` (ubb-platform/api/v1/tenant_endpoints.py:183-282).
- **Widget auth:** HS256 JWT per-tenant secret (`token_urlsafe(48)`), 15-min default expiry, safe two-step decode, issuer pinning; `rotate_widget_secret` invalidates all outstanding tokens (ubb-platform/core/widget_auth.py; tenants/models.py:117,127-130).
- **No unauthenticated business endpoint:** all 12 NinjaAPI routers instantiate with `auth=ApiKeyAuth()` (or WidgetJWTAuth); only Stripe webhooks and the Connect OAuth callback are key-less, gated by signature/state nonce (api/v1/webhooks.py:43-52; connect_endpoints.py:45-69).
- `last_used_at` buffered in Redis and flushed by beat every 5 min (core/auth.py:19; core/tasks.py:12-31).

### Competitor evidence

- **Metronome** supports token scoping by access level (read-only), environment (sandbox-only), and endpoint — though scope adjustment requires contacting a Metronome representative rather than self-serve (https://docs.metronome.com/api-reference/authentication).
- **Orb** documents plain bearer keys created self-serve, with **no fine-grained key scopes documented** on the pages fetched (https://docs.withorb.com/api-reference) — UBB is at parity with Orb here, behind Metronome.
- **Lago** lists bearer-token auth with no scope model on the API intro page (https://getlago.com/docs/api-reference/intro).
- **Sandbox parity:** Metronome ships a Sandbox environment auto-wired to Stripe test mode (https://docs.metronome.com/integrations/invoice-integrations/stripe); Orb has a distinct Test Mode with separate keys (https://docs.withorb.com/quickstart/ingest); **Lago has no test mode at all** — its docs recommend running two accounts or mixing cloud+OSS as a workaround (https://getlago.com/docs/guide/integration-testing). UBB's sandbox-as-sibling-tenant with `ubb_test_` keys (tenants/models.py:65-68,84-90) is ahead of Lago and structurally comparable to Metronome/Orb.

### Gaps

| Gap | Severity |
|---|---|
| **No authorization granularity below a tenant-wide key.** TenantApiKey has no scopes, roles, or read-only class (models.py:133-141); ProductAccess (core/auth.py:23-34) gates on the *tenant's* products, not the key. A leaked CI key grants withdraw, refund, grant-credit, and key rotation. Scoped keys are table stakes for a public billing API (cf. Metronome's read-only/per-endpoint scopes, https://docs.metronome.com/api-reference/authentication). | major |
| Keys stored as unsalted single-round SHA-256 (models.py:168,180). Fine against brute force at 256-bit entropy, but no pepper boundary: a stolen DB can validate separately-leaked keys offline. | minor |
| No API to fetch or rotate `widget_secret` — `rotate_widget_secret` is reachable only via admin/ORM, so a tenant cannot self-rotate on a leak. | minor |

### Actions

1. Add a scopes field (or RestrictedKey model) enforced in ApiKeyAuth; ship ingest-only and read-only key classes at minimum; bind withdraw/refund/grant to an explicit write-money scope.
2. Switch key hashing to HMAC-SHA256 with a SECRET_KEY-derived pepper (no UX change).
3. Add an authenticated fetch-once/rotate endpoint for the widget secret.

---

## 4. Hosting & deployment

**Relevance: critical. Verdict: weak.**

### What exists

- **docker-compose.yml:1-23 is the ONLY deployment artifact in the repo and it is dev-only:** postgres:16 + redis:7 with hardcoded `ubb/ubb` credentials and NO app/worker/beat service. Globs for `**/Dockerfile*`, Procfile, `*.tf`, helm/, k8s/ return nothing.
- **No production server installable:** neither ubb-platform/requirements.txt:1-14 nor requirements.lock.txt contains gunicorn/uvicorn/daphne/whitenoise; wsgi.py/asgi.py exist but only the dev server is installable. Test deps are mixed into the runtime requirement set.
- **Settings ARE prod-aware in places:** SECRET_KEY required at import (settings.py:12), DEBUG defaults False (settings.py:14), ALLOWED_HOSTS enforced when DEBUG=False (settings.py:18-20), and a real non-DEBUG security block: SSL redirect + proxy header, 1y HSTS w/ preload, secure cookies (settings.py:320-327), nosniff/X-Frame-DENY/referrer-policy always on (settings.py:316-318).
- **Static files incomplete:** STATIC_URL only (settings.py:102), no STATIC_ROOT, no whitenoise — yet Django admin is mounted (config/urls.py:22), so admin static is unservable at DEBUG=False.
- The shipped env template is a dev profile (`SECRET_KEY=change-me`, `DEBUG=True` — ubb-platform/.env.example:11-12); no production env contract or secret-management story.
- Deploy-aware migrations exist in two places: usage/0022's CONCURRENTLY + recovery runbook, and invoicing/0006_residual_ledger.py:15-18's explicit "quiesce billing workers" DEPLOY NOTE.

### Competitor evidence

- **Lago's canonical self-host compose defines the entire running system:** migrate, api, api-worker, api-clock, front, pdf (Gotenberg), db (postgres-partman), redis — images pinned at v1.48.1, with commented-out dedicated workers for events/PDFs/billing/webhooks (https://github.com/getlago/lago/blob/main/docker-compose.yml; https://getlago.com/docs/guide/lago-self-hosted/docker). The docs even flag that the bundled db "is intended for local trials" and production should bring managed Postgres/Redis.
- Metronome and Orb are SaaS-only (no self-host/BYOC found on any first-party page: https://docs.metronome.com/integrations/invoice-integrations/stripe; https://www.withorb.com/security) — so for them deployment is internal. For a vendor at UBB's stage, Lago's compose is the relevant bar: a stranger can run the whole product with one command. UBB's compose runs the dependencies and none of the product.

### Gaps

| Gap | Severity |
|---|---|
| **No application container image** — no Dockerfile, no Procfile, no IaC; the Django app, the 8-queue worker, and beat exist only as code someone must hand-run. Reproducible builds are the floor for rollback, scaling, and DR. | **blocker** |
| No production app server or static path: gunicorn/whitenoise absent; STATIC_ROOT undefined — at DEBUG=False the app cannot be served correctly today. | major |
| No deploy pipeline of any kind; the migration sequencing the code itself demands (invoicing/0006) has no enforcement point. | major |
| `DATABASE_URL` silently falls back to SQLite (settings.py:82-86) — a misconfigured prod worker would happily write billing data into a local file instead of crashing. | moderate |
| No production env template or secrets handling — `load_dotenv()` at import (settings.py:4-6) implies plaintext .env for Stripe live keys. | moderate |

### Actions

1. Multi-stage Dockerfile, one image, three entrypoints (gunicorn web / celery worker -Q all 8 queues / celery beat); extend compose for parity; publish the image from CI.
2. Pin gunicorn + whitenoise; add STATIC_ROOT + collectstatic to the build.
3. Add a release workflow: build → gated migrate (respecting quiesce notes) → deploy with health gating on `/api/v1/ready`.
4. Mirror the SECRET_KEY fail-fast pattern for DATABASE_URL when DEBUG=False.
5. Document the prod env contract (SECRET_KEY, DATABASE_URL, REDIS_URL, ALLOWED_HOSTS, STRIPE_*, CORS) and a secret-manager home for it.

---

## 5. Cloud & compute

**Relevance: high. Verdict: weak.**

### What exists

- **The process topology is fully derivable from code:** 1 web (WSGI) + ≥1 Celery worker consuming 8 explicitly declared queues (ubb-platform/config/settings.py:134-143) + exactly one beat driving 25 schedule entries (settings.py:147-254). Every task decorator pins `queue=` explicitly (verified by grep); a bare `celery worker` consumes all 8 because CELERY_TASK_QUEUES is set.
- **Celery safety defaults are configured, not just claimed:** acks_late, reject_on_worker_lost, prefetch 1, 600s/300s time limits, max-tasks-per-child 1000 (settings.py:124-130) — a worker crash means redelivery, not loss.
- **Health endpoints do real checks:** GET /api/v1/health liveness stub; GET /api/v1/ready runs `connection.ensure_connection()` + raw Redis ping, 503 with per-check detail on failure (ubb-platform/api/v1/endpoints.py:11-38, mounted at config/urls.py:40).
- **The web tier is stateless:** no FileField/MEDIA, JSON-to-console logging only, DB sessions used only by admin, contextvar request context (core/middleware.py:19-36), Celery correlation-id propagation via signals (config/celery.py:14-31).
- One Redis serves cache + broker + result backend off one URL (settings.py:107-118); conn_max_age=600 with no pooler anywhere.

### Competitor evidence / best-practice framing

No competitor publishes their internal compute topology, so this category is judged against general best practice. The observable proxy is operational maturity: Orb publishes per-component 90-day uptime (API 99.96%, Ingest 99.99%, Webhooks 99.96% — https://status.withorb.com) and Metronome runs a public component status page (https://status.metronome.com) — both imply monitored, redundant compute. UBB has no equivalent posture (no monitoring at all, §11).

### Gaps

| Gap | Severity |
|---|---|
| **Redis is a hard dependency of EVERY authenticated request:** core/auth.py:19 performs an unguarded `cache.set` inside `authenticate()`, and Django's RedisCache propagates connection errors (the installed backend's only except is `ValueError`). A Redis outage 500s the entire API at auth — before the deliberately fail-open gate/budget code ever runs. One-line availability bug. | major |
| **Beat is doubly exposed:** no protection against running two (default PersistentScheduler, local file), and — verified worse — no protection *for* the one: dual-beat is largely benign for correctness (skip_locked + status-CAS claims throughout: events/tasks.py:53-61; tenant_billing/tasks.py:133-144; postpaid_service.py:114), but a *dead* beat silently stops the outbox sweep and the entire reconcile lattice with no alarm. | major |
| **No observability stack:** zero matches for sentry/prometheus/statsd/datadog/opentelemetry; /ready checks DB+Redis but not worker liveness or queue depth; dead letters end at `logger.critical` with "Extend with Slack/PagerDuty as needed" (events/tasks.py:29-43). | major |
| No process supervision or ops runbook — start order, drain procedure, and the migration-quiesce rule exist only in code comments. | moderate |

### Actions

1. Wrap the auth `cache.set` (and the dispatch-gate cache calls at events/dispatch.py:18-33) in try/except; add a regression test patching cache.set to raise.
2. Adopt RedBeat (Redis-locked single-active beat) + a beat heartbeat key alerted on staleness.
3. Add Sentry + a metrics exporter (queue depth, outbox backlog, dead-letter count); page on `outbox.dead_letter`, wallet drift, drawdown repair spikes.
4. Ship systemd units / compose services for the three roles plus a one-page ops doc.

---

## 6. CI/CD & version control

**Relevance: critical. Verdict: weak.**

### What exists

- **A single, well-written CI workflow** (.github/workflows/ci.yml): postgres:16/redis:7 services with health checks (ci.yml:37-59), Python 3.13 with lockfile-keyed pip cache (ci.yml:72-76), locked install + editable SDK (ci.yml:78-82), four gates: `manage.py check`, `makemigrations --check --dry-run`, platform pytest, SDK pytest (ci.yml:84-98). Triggers on push + PR (ci.yml:29-31).
- **Lockfile discipline is real:** ubb-platform/requirements.lock.txt is a pinned freeze with regeneration instructions; the SDK has its own pinned chain.
- **The test suite is a genuine asset:** 1427 platform tests + 281 SDK tests collected (verified by `pytest --collect-only`), running against real Postgres+Redis. An autouse Stripe network guard monkeypatches the Stripe transport to raise on any un-mocked call (ubb-platform/conftest.py:45-69), with one opt-in live module gated on `UBB_STRIPE_LIVE_TEST`. Five files do real threaded concurrency tests on Postgres (e.g. apps/billing/tests/test_concurrency_races.py; apps/metering/pricing/tests/test_tier_ladder_concurrency.py).
- **Commit quality is high** (conventional-commit subjects with rationale throughout).
- **Measured VC state:** branch is 221 commits ahead of main, 0 behind; main has 17 commits, last touched 2026-03-11; `git tag` is empty; remote is github.com/ashcochrane/ubb.

### Competitor evidence / best-practice framing

No competitor fact sheet covers CI internals; the relevant best-practice bar is unremarkable and well known: trunk-based or short-lived branches, CI required on a protected default branch, supply-chain scanning, and a release pipeline. UBB currently meets none of these *in operation*, despite having the workflow file.

### Gaps

| Gap | Severity |
|---|---|
| **CI has never actually run.** The workflow file was added in local HEAD commit 699fb98 — one of **46 commits that exist only on this machine** (`git rev-list --count origin/tl-changes-05-06-26..tl-changes-05-06-26` = 46; `git ls-tree origin/... .github/` returns nothing). All 221 branch commits were made without any CI gate, and ~the entire recent program of money-handling code has a single-disk bus factor. | **blocker** |
| 221-commit unmerged branch used as de-facto trunk; main frozen since 2026-03-11; no tags or releases. Merge is trivially safe today (0 behind) and gets costlier weekly. | major |
| No deploy stage, no deployable artifact, no staging environment (overlaps §4). | major |
| No security scanning or dependency automation: no pip-audit/bandit/CodeQL job, no dependabot.yml. | major |
| No lint/format/type-check anywhere (no ruff/mypy/pre-commit configs; pytest.ini is 2 lines) — and the SDK ships `py.typed` (ubb-sdk/pyproject.toml:16) with no type checker verifying it. | moderate |
| No coverage measurement or ratchet. | moderate |
| No SDK release pipeline: pyproject declares 2.0.0 with no build/publish workflow, no tag, no PyPI story — `pip install -e ./ubb-sdk` is not distribution. | moderate |
| Workflow nits: push+PR double-runs, no concurrency cancel group, no timeout-minutes. | minor |

### Actions

1. **Push the branch today**; watch the first Actions run go green on a clean runner; make push-after-every-session the norm.
2. Merge/fast-forward to main now while behind-count is 0; tag (v0.x); switch to short-lived branches + PRs with required CI; add CODEOWNERS + PR template.
3. Add pip-audit + CodeQL workflows + Dependabot (weekly, grouped) on both lockfiles.
4. Add ruff + mypy (django-stubs) as a parallel job; run mypy on the SDK.
5. Add pytest-cov with a recorded baseline and ratchet-only threshold.
6. Tag-triggered SDK build/publish via PyPI trusted publishing (TestPyPI first).

---

## 7. Security & RLS

**Relevance: critical. Verdict: adequate.**

### What exists

- **Tenant isolation is systematic application-level FK scoping:** every business query filters on `request.auth.tenant` (e.g. metering_endpoints.py:50; tenant_endpoints.py:49,89); me_api scopes to the widget customer; pooled-seat leakage is explicitly blocked (me_endpoints.py:334-339,420-427). No tenant-crossing raw SQL in production paths (cursor()/raw() appear only in tests/scripts).
- **Inbound Stripe webhooks:** `stripe.Webhook.construct_event` signature verification with the built-in 300s tolerance (api/v1/webhooks.py:71; subscriptions endpoints.py:198), plus DB-row dedup with CAS-guarded retry (webhooks.py:81-126). Live/test isolation: separate test endpoint requiring its own secret, `reject_for_mode()`, and `livemode_filter()` binding event.account lookups to `is_sandbox` (invoice_routing.py:22-54).
- **Outbound webhook SSRF defense is real and the IP pinning actually pins:** validate_webhook_url rejects non-https/localhost/private/loopback/link-local/reserved and returns the first validated IP; `_PinnedIPBackend.connect_tcp` swaps the hostname for that IP while TLS SNI/cert verification keeps the original hostname; URL re-validated at delivery time, closing the DNS-rebinding window (core/url_validation.py; events/webhooks.py:19-68,171-181).
- **Outbound signing has a replay-bounded v2:** `compute_signature_v2` over `{ts}.{body}` as X-UBB-Signature-V2 (webhooks.py:87-102,150-159); the SDK enforces a 300s tolerance and supports rotation candidates (ubb-sdk/ubb/webhooks.py:39-94).
- **Prod Django hardening correct** (see §4 anchors); bearer APIs correctly CSRF-exempt; webhooks signature-verified.
- **No committed secrets** (git grep for sk_live_/whsec_/AKIA/PRIVATE KEY: nothing); **logs redact PII/secrets** via RedactingFilter (core/logging.py:19-25).

### Competitor evidence

- **Compliance is where every competitor is ahead, and UBB has nothing:** Metronome shows SOC 1 Type 2 + SOC 2 Type 2 (https://metronome.com/company/security); Orb runs an annual third-party SOC-2 Type II audit, pentests, and a SafeBase trust center with downloadable reports (https://www.withorb.com/security; https://security.withorb.com/); Lago has SOC 2 Type 2 for its hosted version and a trust center (https://getlago.com/docs/guide/security/soc; https://www.getlago.com/security). The UBB repo contains no compliance artifact, pentest report, or trust posture of any kind — expected at this stage, but it is a sales-blocking gap the moment a real tenant asks.
- Note: none of Metronome/Orb/Lago document Postgres RLS either (internal architecture isn't published); the RLS comparison below is against best practice for money systems, not against verified competitor behavior.

### Gaps

| Gap | Severity |
|---|---|
| **No Postgres RLS and no automated tenant-scoping test.** Isolation is app-FK-only; the AST boundary test (apps/platform/tests/test_product_boundaries.py) enforces import boundaries, not tenant filtering. One missing `.filter(tenant=...)` in a future endpoint silently cross-leaks financial data with no second line of defense. | moderate |
| Legacy body-only webhook signature (X-UBB-Signature, no timestamp binding) still emitted on every delivery — a captured delivery replays forever for receivers verifying the legacy header. | moderate |
| SSRF validation misses non-global shared ranges: 100.64.0.0/10 (CGNAT) passes (verified: not private, not global, not flagged in url_validation.py:45). | moderate |
| No dependency-security automation in CI (overlaps §6). | moderate |
| OpenAPI/Swagger docs served unauthenticated for all 12 routers (django-ninja defaults; no docs_url=None passed anywhere) — full API surface publicly enumerable in production. | minor |

### Actions

1. Either add RLS keyed on a session GUC set from `request.auth.tenant` in middleware (higher assurance), or at minimum a systematic test walking every endpoint/queryset asserting tenant scoping.
2. Set a sunset date for the legacy webhook signature; make legacy emission opt-in; default new configs v2-only.
3. Invert the SSRF check to require `ip.is_global` (subsumes private/CGNAT/reserved).
4. Pass `docs_url=None` (or a staff-only decorator) in production.
5. Start the compliance runway (SOC 2 readiness, pentest, trust page) — every competitor leads with this.

---

## 8. Rate limiting

**Relevance: high. Verdict: weak.**

### What exists

- **One real limiter:** per-customer fixed-window RPM in `RiskService.check` — key `ratelimit:{customer.id}:rpm`, threshold `RiskConfig.max_requests_per_minute` (default 60), 60s window, TTL-preserving incr (ubb-platform/apps/billing/gating/services/risk_service.py:21-33). It degrades gracefully (try/except skips limiting on Redis failure).
- **Coarse input caps:** usage batch 1–100 items (schemas.py:57), rate-card batch ≤100, analytics dimensions ≤6, list limits clamped ≤100.

### Competitor evidence

Every competitor publishes (or enforces) limits at the **ingest** chokepoint:

- **Lago:** default **500 requests/sec per organization** on POST /events and /events/batch, with 429s carrying `x-ratelimit-remaining`/`x-ratelimit-reset` headers (https://getlago.com/docs/guide/events/ingesting-usage).
- **Stripe meters:** 1,000 calls/sec per account live mode on v1 meter_events; the v2 stream does 10k events/sec standard, 200k via sales; sandbox calls count toward the sandbox global rate limit — 25 req/s (https://docs.stripe.com/billing/subscriptions/usage-based/recording-usage-api; limit figure per https://docs.stripe.com/rate-limits).
- **Orb:** test mode hard-limited to 2,000 events/min and 10 req/s — explicitly "to ensure test mode workloads do not affect live mode availability"; production advisory threshold of 10,000 events/min before contacting the team (https://docs.withorb.com/events-and-metrics/event-ingestion; quoted test-mode rationale from https://docs.withorb.com/quickstart/ingest).
- **Metronome:** documents 429 + exponential-backoff behavior on ingest, with no public numeric cap (https://docs.metronome.com/connect-metronome/send-usage-events/).

UBB, by contrast, rate-limits a path callers can simply not call, and its sandbox tenants share the same (non-existent) ingest limits as live.

### Gaps

| Gap | Severity |
|---|---|
| **The RPM limiter is only invoked on POST /billing/pre-check (billing_endpoints.py:259) — an optional advisory call.** The actual chokepoints POST /metering/usage and /usage/batch do not call RiskService at all (confirmed: no RiskService/cache.incr in apps/metering). A client that skips pre-check has zero rate limiting on ingestion — the DoS and runaway-cost vector on a public billing API. | major |
| **No global, per-API-key, or per-IP throttle anywhere.** No NinjaAPI passes `throttle=`; no NINJA_DEFAULT_THROTTLE_RATES. Invalid-key probing (each = an unthrottled DB lookup), webhook-endpoint flooding, and whole-tenant abuse across customers are all unthrottled. | major |
| The limiter and the broader gate default fail-open (RiskConfig.gate_fail_closed=False, BudgetConfig.fail_closed=False) — an attacker who can degrade Redis removes all rate/budget enforcement silently. | moderate |
| `max_concurrent_requests` (RiskConfig, default 10) is defined but NEVER enforced — dead configuration giving operators false assurance. | moderate |
| RiskConfig only manageable via Django admin — no tenant-facing API; every tenant runs the hard-coded 60 rpm. | minor |

### Actions

1. Enforce limiting at record_usage and /usage/batch themselves (batch counts *items*, not requests).
2. Add a global per-API-key throttle and a per-IP throttle (django-ninja `throttle=` or edge layer), including the unauthenticated webhook endpoints; return rate-limit headers like Lago's (https://getlago.com/docs/guide/events/ingesting-usage).
3. Alert loudly when the limiter degrades; consider fail-closed defaults for hard money caps.
4. Implement or delete `max_concurrent_requests`.
5. Expose RiskConfig via tenant API with plan-based defaults; give sandbox tenants deliberately lower limits (Orb's pattern).

---

## 9. Caching & CDN

**Relevance: high. Verdict: adequate.**

### What exists

- **CDN: correctly absent** — JSON API backend, no static/media pipeline beyond admin (settings.py:102).
- **One Redis, four roles:** Django cache, Celery broker, Celery results, /ready probe (settings.py:110-118; api/v1/endpoints.py:24-32).
- **Complete cache usage map:** budget spend counters with 62-day TTL and rebuild-on-miss that deliberately avoids double-count (apps/billing/gating/services/budget_service.py:10,41-65); per-seat fixed-window rate limit (risk_service.py:22-31); tenant-products dispatch gate with 300s TTL + write-through invalidation (events/dispatch.py:15-34; tenants/models.py:125); API-key last-used write-behind buffer flushed by beat (core/auth.py:19; core/tasks.py:12-31).
- **Redis-death behavior is explicitly engineered for the gating paths:** rate limiting fails open; budget check fails open by default with explicit fail-closed opt-in returning `budget_unavailable`; the post-drawdown counter increment is fully fail-open with an hourly Postgres rebuild (risk_service.py:32-33; budget_service.py:72-83,126-153). Tests exercise Redis-failure paths (gating/tests/test_risk_service.py:102).
- **Counters are caches, not ledgers:** durable budget truth is the Postgres UsageEvent aggregate; idempotency is Postgres constraints; all mutual exclusion is `select_for_update` with a documented canonical lock order — zero Redis locks (apps/billing/locking.py:1-11).
- **Celery-on-Redis death story:** domain events live in a Postgres transactional outbox swept every minute, so delivery resumes from durable state (events/models.py:15-39; settings.py:180-183).
- Test hygiene acknowledges the shared-DB hazard: tests run on Redis DB 15 so `cache.clear()` can't flush broker data (ubb-platform/conftest.py:1-42).

### Competitor evidence / best-practice framing

No competitor publishes cache internals; this category is judged on best practice. The "Redis is a cache, Postgres is the ledger" discipline here is exactly right and worth crediting — the failure is a single inconsistency, not the design.

### Gaps

| Gap | Severity |
|---|---|
| **The auth hot path does an UNGUARDED `cache.set` on every authenticated request (core/auth.py:19).** Django's RedisCache propagates connection errors, so a Redis outage turns every authenticated call — including record_usage — into a 500, despite verify_key being pure Postgres. This single line converts Redis from a designed degrade-gracefully dependency into a hard SPOF for the metering API; a Redis blip means dropped usage events = lost revenue data. (Same issue: unguarded `cache.delete` in Tenant.save, tenants/models.py:125.) | major |
| Cache + broker + results share one Redis logical DB (settings.py:107-118). The workloads need contradictory configs (broker: noeviction; cache: LRU); an accidental prod `cache.clear()` wipes in-flight billing tasks. The conftest comment proves the team knows. | moderate |
| CELERY_RESULT_BACKEND configured but nothing ever reads a result (no AsyncResult/.get anywhere) and task_ignore_result unset — pure memory churn on the broker instance. | minor |
| Rate limiter is non-atomic get→incr fixed window (risk_service.py:24-31) — can overshoot under race and permits ~2× at window boundaries; acceptable for an advisory fail-open gate, but approximate. | minor |
| Hot per-request config reads (RiskConfig, BudgetConfig, wallet balance) are uncached primary-DB queries; only tenant products get the 5-min cache treatment. Fine at launch volume. | minor |

### Actions

1. try/except the auth `cache.set` and Tenant.save `cache.delete` (matching the pattern three lines away in the gating services); regression-test with a raising cache.
2. Split cache vs broker into separate logical DBs (separate env vars), document `noeviction` for the broker, preferably two instances.
3. Set `CELERY_TASK_IGNORE_RESULT = True` until something consumes results.
4. If the limit ever becomes contractual, switch to INCR-first or sliding window; otherwise document best-effort.
5. When p99 gate latency matters, add 30–60s cached reads for Risk/BudgetConfig mirroring the tenant_products pattern.

---

## 10. Load balancing & scaling

**Relevance: high. Verdict: weak.**

### What exists

- **The hot path is fully characterized:** a typical single-metric tiered record_usage costs ~9–13 sequential DB round trips in one transaction — key lookup, customer 404, idempotency pre-check, billing-owner resolution, rate-card resolve per metric per side, tier ladder advance (exists + savepoint create + SELECT FOR UPDATE + UPDATE), UsageEvent INSERT, OutboxEvent INSERT — plus 2 Redis ops (anchors: tenants/models.py:182; metering_endpoints.py:50; usage_service.py:122-132; pricing_service.py:69-72,98-100,144-146; tier_counter_service.py:52-65; usage_service.py:176; outbox.py:26; core/auth.py:19).
- **Serialization points verified:** the per-(tenant, customer, lineage, calendar-month) `PricingPeriodCounter` row lock is held from tier_counter_service.py:62 until the **outer** transaction commits — the event insert and outbox insert execute under it (usage_service.py:156-220); multi-metric deadlock prevented by sorted lock order (pricing_service.py:143-144); wallet money movement is deliberately OFF the hot path, serialized per billing owner asynchronously in the outbox handler (apps/billing/handlers.py:49-50 via locking.py:26-39).
- **Reasoned capacity class:** order of 100–300 record_usage rps for one web instance against one Postgres with traffic spread across customers; a single hot (customer, lineage, month) tier ladder is hard-capped at one lock-holder at a time — order of 100–200 events/s for that customer/metric regardless of replica count.
- **Web-tier horizontal scaling is safe by construction:** stateless requests, DB-keyed idempotency makes cross-replica retries return the original event, and the batch endpoint deliberately runs items as independent transactions (metering_endpoints.py:184-205).
- **There is no LB, autoscale, replica, or capacity configuration anywhere in the repo** — gunicorn isn't even installed.

### Competitor evidence

- **Metronome:** first-party claim of "100,000 events per second without requiring pre-aggregation or rollups" (https://docs.metronome.com/api-reference/usage/ingest-events); a partner case study claims billions of events/day (https://www.confluent.io/customers/metronome/ — partner-published, medium confidence).
- **Orb:** "250,000+ events/second" and "billions of events/day with hosted streaming aggregation" on the pricing page (https://www.withorb.com/pricing); the *standard* ingestion API is separately described as "designed to scale to tens of millions of events per day" (https://docs.withorb.com/events-and-metrics/event-ingestion).
- **Lago:** scales its events engine by moving ingestion to Kafka → ClickHouse while keeping Postgres transactional (https://github.com/getlago/lago/wiki/Using-Clickhouse-to-scale-an-events-engine); REST ingest default-limited to 500 req/s per org, with Kafka/Kinesis/S3 connectors exempt from REST limits (https://getlago.com/docs/guide/events/ingesting-usage).

Honest framing: UBB's reasoned ~100–300 rps is two to three orders of magnitude below Metronome/Orb's headline claims. Those claims are for streaming pipelines UBB does not need on day one — but Orb's "tens of millions of events/day" for its *standard* API (~hundreds/s sustained) is the credible near-term bar, and UBB is at or below its bottom edge with no path documented past it.

### Gaps

| Gap | Severity |
|---|---|
| No horizontal scaling story in any artifact: zero LB/replica/autoscale config, no sizing, no gunicorn settings. The code is replica-safe; nothing lets anyone run two replicas. | major |
| No high-throughput ingest mode: every event is a synchronous priced transaction; batch is sequential (latency 100× single, throughput unchanged). | major |
| Tier-counter lock window wider than necessary: the row lock spans counter UPDATE + event insert + outbox insert + commit — the structural per-customer ceiling. | moderate |
| No connection pooler: conn_max_age=600 per process with no pgbouncer — connection exhaustion is the first thing web scaling hits. | moderate |
| No tenant-level throttling, so one tenant can saturate the shared DB for all (overlaps §8). | moderate |

### Actions

1. Containerize → N stateless replicas behind any L7 LB with `/api/v1/ready` as health check; load-test and document rps-per-replica.
2. Build the async ingest path (accept-and-persist fast, price in workers under the same idempotency keys) — the single biggest competitiveness item in this category.
3. Collapse the tier-counter read-modify-write to `UPDATE ... RETURNING`; consider sharded counters for hot keys.
4. Add pgbouncer (transaction pooling) before running more than a couple of replicas.
5. Per-API-key token-bucket throttling for noisy-neighbor isolation.

---

## 11. Error tracking & logs

**Relevance: critical. Verdict: weak.**

### What exists

- **A real structured-logging stack, stronger than typical for this stage:** correlation-ID contextvar + CorrelationIdFilter + RedactingFilter + JsonFormatter emitting timestamp/level/logger/correlation_id/message/data/exception (ubb-platform/core/logging.py:15,59-64,67-95,98-126). The `extra={"data": {...}}` convention is documented and followed (113 of 124 logging calls in non-test source).
- **PII redaction exists and is tested:** REDACT_KEYS covers email/phone/card/ip/etc., substring matching covers secret/token/api_key/password, an email regex scrubs messages and exception traces (logging.py:19-26,32,55-56,92,111-114); tests pin that stripe keys and emails redact while amounts and Stripe customer IDs are deliberately preserved (core/tests/test_logging.py:33-59).
- **Correlation IDs are end-to-end:** middleware validates/accepts/echoes X-Correlation-ID (core/middleware.py:19-36); Celery propagation via signals (config/celery.py:14-31); outbox events persist it and the dead-letter alert carries it (outbox.py:21-22; events/tasks.py:40).
- **A consistent dotted event-name taxonomy forms a ready-made alert table:** CRITICAL `outbox.dead_letter`; ERROR including `billing.usage_push_failed_permanent`, `postpaid.snapshot_divergence`, `ledger.usage_deduction_amount_mismatch`, `wallet.drawdown_repair_spike` (threshold-gated), `pricing.tier_rerate_drift`, Stripe top-up reconciliation mismatches; WARNING including webhook delivery failures and `wallet.drawdown_repaired` (anchors throughout apps/billing and apps/platform — e.g. events/tasks.py:31; postpaid_service.py:94,156,254; handlers.py:57; wallets/tasks.py:146,170-171).
- **Runbook-shaped management commands with guard rails:** `reprocess_webhook` refuses non-failed events; `repush_usage_invoice` documents --rebill-void and refuses statuses where repush would double-bill (apps/billing/stripe/management/commands/reprocess_webhook.py:6-33; invoicing/management/commands/repush_usage_invoice.py:7-36).
- **Correction to one source audit:** the claim that no /health or /ready endpoints exist is **wrong** — both exist with real DB+Redis checks (ubb-platform/api/v1/endpoints.py:11-38) and are mounted at config/urls.py:40. The valid residue of that finding is the absence of *metrics* and a *beat heartbeat*, covered below.

### Competitor evidence / best-practice framing

Competitors don't publish their internal observability, but its outward shadow is visible: Orb's public status page reports per-component 90-day uptime to four significant figures and a resolved-in-90-minutes incident timeline (https://status.withorb.com); Metronome runs a public component status page (https://status.metronome.com). You cannot operate either without real error tracking, metrics, and paging. UBB has none of the three.

### Gaps

| Gap | Severity |
|---|---|
| **Zero error-tracking, metrics, or paging infrastructure.** No observability package in either lockfile (grep for sentry/rollbar/otel/prometheus/statsd/datadog: only a stale planning doc). Every tripwire above — including `logger.critical("outbox.dead_letter")` — is a JSON line on the stdout of a process nobody watches; detection latency in production is effectively never. This platform moves money asynchronously; this is the failure mode that costs real dollars. | **blocker** |
| **Logger-name misconfiguration silently drops INFO-level ops telemetry:** ten modules log to `ubb.events`/`ubb.billing`/`ubb.webhooks` (e.g. events/tasks.py:18; postpaid_service.py:13; events/webhooks.py:14) but LOGGING configures only apps/core/api/django.request/stripe/celery (settings.py:287-295), so `ubb.*` resolves through the root logger at WARNING — `outbox.sweep`, `outbox.cleanup`, `postpaid.residual_carried` and friends vanish without error. WARNING+ still emits, so the loud tripwires survive. | major |
| No log aggregation or retention: console StreamHandler only (settings.py:281-285); logs evaporate with the terminal — billing-dispute forensics by correlation_id is impossible. | major |
| No metrics and no beat heartbeat: a dead beat (the platform's worst silent failure — money simply stops moving) is undetectable; no counters on the dotted event names. | major |
| No alerting policy mapping event severity to human response; no channel wired. | major |
| No ops runbook docs: remediation tooling exists but nothing links `postpaid.stripe_invoice_unusable` at 2am to the diagnosis query and fix command. | moderate |
| Redaction blind spot: scalar non-dict extras outside the `data` convention pass unredacted (logging.py:86-89); only the console handler attaches the filter. | minor |

### Actions

1. Add sentry-sdk (Django+Celery integrations); use the existing dotted event names as fingerprints — hours of work given the discipline already in place.
2. Add an `ubb` logger entry at INFO to LOGGING (one line) or normalize to `getLogger(__name__)`; test that every logger name in source resolves to a configured logger.
3. Ship stdout to a hosted aggregator (Loki/Datadog/CloudWatch) with 30–90 day retention — drop-in given the JsonFormatter.
4. Add a beat heartbeat (Redis key refreshed by a beat task, alerted on staleness) + counters on event names so rules like "outbox.dead_letter > 0" exist.
5. Write the one-page severity→response policy and wire it (CRITICAL pages; ERROR same-day; WARNING weekly).
6. Create docs/runbooks/ keyed by ERROR/CRITICAL event name: meaning, log query, invariant at risk, exact repair command.

---

## 12. Availability & recovery

**Relevance: critical. Verdict: weak.**

### What exists

The recovery *design* is the strongest part of this codebase and deserves explicit credit:

- **Transactional outbox with belt-and-suspenders delivery:** events written in the same transaction as the domain change (events/outbox.py:26-35), dispatched on_commit AND re-dispatched by a minutely sweep that reclaims stuck rows after 5 min (events/tasks.py:84-121), bounded retries (backoff 30s→2h, ~2h43m horizon) and dead-letter logging (tasks.py:20,29-43). Broker loss is survivable because Postgres rows, not broker messages, are the source of truth.
- **A real, self-healing reconcile lattice** (each verified in source, all beat-scheduled in settings.py:147-254): `reconcile_usage_drawdowns` repairs dead-lettered wallet debits exactly-once via the `usage_deduction:{event_id}` key + anti-join column, with GRACE=6h deliberately exceeding the retry horizon and a repair-spike alert (wallets/tasks.py:99-171); `reconcile_topups_with_stripe` re-credits lost PaymentIntent successes from Stripe with a 4-day lookback exceeding Stripe's ~3-day webhook retry (connectors/stripe/tasks.py:117-174); `reconcile_invoice_payment_status` repairs missed invoice webhooks along the same legal-transition table as the fast path (invoicing/tasks.py:146-207); `reconcile_postpaid_usage` bounded to terminal failed_permanent inside Stripe's 24h idempotency window (postpaid_service.py:126-134); `reconcile_wallet_balances` is a full ledger-vs-balance drift detector (wallets/tasks.py:10-96). **Stripe-down degrades and converges rather than losing money state.**
- **Redis-down graceful degradation exists in the spend-control layer as designed** (risk_service.py:32-33; budget_service.py:73-83,126-153) — defeated at the auth layer, see gaps.
- **Inbound webhooks crash-safe** (signature + DB dedup + CAS retry + 500-for-retryable so Stripe redelivers ~3 days; hourly pollers backstop beyond that — api/v1/webhooks.py:66-176).
- **Celery loss semantics defensive:** acks_late + reject_on_worker_lost; money tasks bound Stripe retries and never hold DB locks across Stripe calls (two-phase claim, tenant_billing/tasks.py:122-182); stale pending top-ups expire after 30 min (topups/tasks.py:10-29).
- Accurate readiness reporting (api/v1/endpoints.py:16-38); honest migration posture (0022 CONCURRENTLY runbook; 0006 quiesce note).

### Competitor evidence

- **Orb** publishes per-component 90-day uptime: API 99.96%, Ingest 99.99%, Webhooks 99.96%, Invoicing 100.0% (https://status.withorb.com), and sells enterprise SLAs "in MSA" (https://www.withorb.com/pricing).
- **Lago** claims "99.9% historical uptime" with enterprise SLAs on its security page (https://www.getlago.com/security).
- **Metronome** runs a public status page but publishes no uptime percentages (https://status.metronome.com).

UBB cannot currently make *any* availability statement: there is no deployment, no monitoring, and no backup from which to state an RPO.

### Gaps

| Gap | Severity |
|---|---|
| **Backups, PITR, DR, RPO/RTO: nothing exists and nothing is documented.** The single docker-compose Postgres volume (docker-compose.yml:12-13) is the only copy of the UsageEvent and WalletTransaction ledgers. Stripe can reconstruct top-up/invoice state (the lattice proves it), but usage events and the wallet ledger exist ONLY in this one Postgres — effective RPO is "everything". The single largest distance-to-best-practice item in this audit. | **blocker** |
| **Three SPOFs with no HA story:** one Postgres, one Redis carrying cache+broker+results (settings.py:107-118), one beat. Beat-down silently stops the sweep and the entire reconcile lattice — the self-healing design assumes its repair jobs run, and nothing detects that they aren't. | major |
| **The fail-open architecture is defeated by one unguarded Redis write** (core/auth.py:19 — same finding as §5/§9): a Redis outage 500s all API traffic at auth; the verified fail-open gate code never executes. Secondarily, unguarded cache calls in dispatch gating (events/dispatch.py:18-33) push handlers into the DLQ path during an outage (recoverable, but noisy). | major |
| All failure alerting terminates in logs nobody is paged on (overlaps §11) — the GRACE/lookback windows only bound repair *after* someone keeps the system running. | major |
| Broker non-durability: compose redis:7 has no volume and no AOF (docker-compose.yml:15-20) — queued tasks vanish on restart. The lattice reduces this from loss to delay for swept paths, but the durability posture is accidental (dev compose), not chosen. | moderate |
| No rolling-deploy machinery to honor the migration constraints the code itself documents (invoicing/0006's quiesce requirement has no enforcement point). | moderate |

### Actions

1. Managed Postgres with automated backups + PITR (target RPO ≤5 min), multi-AZ standby, and a **rehearsed** restore runbook ending in lattice re-convergence — before any production tenant.
2. Redis replica/sentinel or split cache-vs-broker; RedBeat + heartbeat for beat; alert on worker/beat staleness.
3. Guard the two best-effort cache call sites, then chaos-test record_usage with Redis stopped to verify the documented degradation end-to-end.
4. Enable AOF + persistent volume for any non-dev Redis; keep the standing rule "every async effect must have a reconcile twin" and document which tasks are sweep-covered.
5. Wire dead-letter/drift/spike alerts to a pager; add a daily "lattice ran" heartbeat.
6. Encode the migration policy (CONCURRENTLY for hot-table indexes; worker-drain step for data migrations) in the release pipeline.

---

## Consolidated prioritized action plan

The unifying observation: **UBB's domain layer is competitive — constraint-encoded money invariants, unbounded DB-enforced idempotency, a genuine self-healing reconcile lattice, disciplined structured logging, and tested concurrency safety are things competitors claim and UBB demonstrably has in code.** None of it is reachable, observable, or recoverable in production today. The plan below sequences the operational layer to catch up; nothing in the blocker tier is architecturally hard.

### Tier 0 — Blockers (do before anything else; none are large)

1. **Push the branch and run CI to green on a clean runner** (§6). 46 commits of money-handling code exist on one disk; the CI workflow has never executed. Then merge to main (currently a zero-conflict fast-forward), tag, enable branch protection.
2. **Backups/PITR for Postgres** (§2, §12). Managed Postgres or wal-g + WAL archiving; rehearsed restore runbook ending in `reconcile_topups_with_stripe`/`reconcile_usage_drawdowns` re-convergence. The wallet ledger and usage events currently have an RPO of "everything".
3. **A deployable artifact** (§4). Multi-stage Dockerfile (web/worker/beat entrypoints), gunicorn + whitenoise + STATIC_ROOT, compose parity, image published from CI.
4. **Error tracking + paging** (§11). sentry-sdk with Django+Celery integrations, the dotted event names as fingerprints, and a wired severity→response policy. Hours of work given the logging discipline already in place.

### Tier 1 — Majors (the week after)

5. **Guard the unguarded auth-path `cache.set`** (core/auth.py:19) and the dispatch-gate/Tenant.save cache calls — the one-line bug that independently surfaced in three audits (§5, §9, §12) and converts Redis into a hard SPOF for the whole API. Add the raising-cache regression test, then chaos-test Redis-down.
6. **Rate-limit the ingest chokepoints** (record_usage + batch counting items) plus per-API-key and per-IP throttles, including unauthenticated endpoints (§8). Lago publishes 500 req/s/org with rate-limit headers (https://getlago.com/docs/guide/events/ingesting-usage); UBB's ingest is currently unthrottled.
7. **Partition ubb_usage_event before data accrues** (§2) — monthly range partitions + pg_partman; retrofitting later is a full-table rewrite.
8. **Beat HA + heartbeat, Redis role split, broker AOF** (§5, §9, §12). The reconcile lattice is only as alive as the one beat process nobody monitors.
9. **Scoped API keys** (§3) — ingest-only and read-only classes; money endpoints behind an explicit scope. Metronome already ships read-only/per-endpoint scopes (https://docs.metronome.com/api-reference/authentication).
10. **Fix the `ubb.*` logger config + ship logs to an aggregator** (§11) — INFO-level ops telemetry is currently dropped silently, and what does emit evaporates.
11. **Security scanning in CI** (§6, §7): pip-audit + Dependabot + CodeQL on both lockfiles.
12. **Async/high-throughput ingest path** (§1, §10) — the largest single competitiveness gap vs Metronome's 100k eps (https://docs.metronome.com/api-reference/usage/ingest-events) and Orb's 250k+ eps (https://www.withorb.com/pricing). Accept-and-persist fast, price in workers under the same idempotency keys.

### Tier 2 — Moderates (next month)

13. DATABASE_URL fail-fast when DEBUG=False (§2, §4) — trivial, prevents silent SQLite split-brain.
14. RLS (or at minimum a systematic tenant-scoping test) as the second isolation line (§7).
15. Warehouse export of UsageEvent/ledger/invoices as Parquet — competitors treat data export as a product component (https://status.metronome.com) (§2).
16. Legacy webhook signature sunset; SSRF check inverted to require `ip.is_global`; docs_url off in prod (§7).
17. Cap `metadata`/`usage_metrics` sizes (§1, §2). *(The future-timestamp bound originally listed here already exists — `_FUTURE_SKEW` at usage_service.py:19.)*
18. pgbouncer before multi-replica; tier-counter `UPDATE ... RETURNING`; index audit + drop redundants CONCURRENTLY (§2, §10).
19. ruff + mypy (SDK ships py.typed unverified) + pytest-cov ratchet; SDK publish pipeline (§6).
20. Implement-or-delete `max_concurrent_requests`; tenant-facing RiskConfig API (§8).
21. docs/runbooks/ keyed by ERROR/CRITICAL event names; ops one-pager for the three-process topology (§5, §11).
22. Begin the compliance runway (SOC 2 readiness, pentest, trust page) — Metronome (https://metronome.com/company/security), Orb (https://security.withorb.com/), and Lago (https://getlago.com/docs/guide/security/soc) all lead with it; it is the first question any serious tenant asks a billing vendor.
