ENGINEERING HANDOFF — CURRENT CODE SNAPSHOT — NOT ADMISSION EVIDENCE

# 03 — Validation procedure and next steps for Ash

Anchored to `origin/main` = `1bf0c0ca772410fa5aa721f733736f5f83e66760`. Every command below is labelled either
**safe local verification** (run it on a laptop against local containers; it changes nothing outside your machine)
or **production-only / do not run yet** (it belongs to W7 and must not be run until the launch inputs are real and
the brief is FINAL). Nothing here is admission evidence.

## Where the programme is now

- **The re-model is built and cut over.** Windows W1–W5 merged their grouped builds; W6 (PRs #622 and #623) was the
  pure cutover: a fresh migration set, the audit-ledger and suppression resets, the `api-v1-cutover` and
  `sdk-v4.0.0` tags on `c2eb35ff`, and a reproducibly built `ubb_sdk-4.0.0-py3-none-any.whl` whose SHA-256 is recorded
  in `ubb-sdk/CHANGELOG.md` and in the project folder (`R10-W6-RELEASE/`). The remaining-work register on #194 is
  fully ticked and #190/#194 are closed.
- **The W7 readiness-fix PR #624 is merged** (squash `1bf0c0ca`, 2026-11-02). It repaired exactly the five product
  defects the W7 preparation pass found and the owner and consultant ruled must be fixed before deployment:
  F1 (the web process never loaded the configured Celery app, so every on-commit dispatch failed and webhooks waited
  for the minutely sweep), F2 (two scheduled tasks were never registered by the worker), F3 (an `external` tenant
  under `enforcing` was stopped and permanently suspended by a wallet floor it does not have), F5 (the live Stripe
  webhook receivers accepted events signed with an empty secret), F6 (a first-insert race in the cost accumulator).
  Each carries regression tests; all of them passed in this session, and F1, F2 and F3 were additionally observed
  live on the local stack.
- **F8, the release-evidence tool's bypass** (re-running `record` erased the recorded artifact), is fixed and
  re-validated in the project-folder tool `R10-W7-RELEASE-EVIDENCE.py`; it is not repository code.
- **W7 remains PRE-LAUNCH — NOT FINAL.** The brief (`R10-W7-DELIVERY-PROMPT.md`) is complete and ruled; its seven
  launch inputs are blank; the only remaining blocker before FINAL is those inputs plus one factual review.
- **Nothing has been deployed to production, ever.** There is no server, no hosted database, no image, no registry,
  no deployment files in the repository (ADR-0026 states it; this session confirmed the absence in the tree).
- **No real tenant is admitted.** The only tenants that have ever existed are developers' local seeds and the ones
  test suites create and roll back. `docs/api-compatibility.md` still carries the dated "no tenant is live" note
  whose deletion is the repository's admission record (W7 step 14).
- **One code-versus-ruling gap was found and left unfixed** (`HANDOFF DISCREPANCY` in `02`, §12): the task-start
  gate and the manual-debit floor still ask "not postpaid?" instead of `holds_a_wallet`. It is unreachable for an
  `external` tenant with the default products, reachable if that tenant enables the `billing` product. It needs an
  owner ruling, not a quiet patch.

## How Ash can independently see that UBB works

All of this is **safe local verification**. It was performed in this session on Windows 11 with Docker 29.5,
Python 3.13.14 and the repository's locked dependencies; the exact outcomes are in `00-README.md`. Use a clean
clone at `1bf0c0ca` and a dedicated database name so you never touch a database another checkout uses.

### 0. Prerequisites

- Docker (for PostgreSQL 16 and Redis 7), Python 3.13, Node 22 and pnpm 10.28 (only if you want the console).
- A `.env` in `ubb-platform/` (copy `.env.example`; set `SECRET_KEY`, `DEBUG=True`, `DATABASE_URL`, `REDIS_URL`).
  The compose file maps PostgreSQL to host port **5433** and Redis to **6380**; `.env.example` matches. (On the
  developer machine used for this session the containers happened to be on 5432/6379; check `docker port`.)
- Do not put a real Stripe secret anywhere. No Stripe is needed for anything below.

```sh
git clone <repo> ubb && cd ubb && git checkout 1bf0c0ca772410fa5aa721f733736f5f83e66760
docker compose up -d                                   # postgres:16 (5433) and redis:7 (6380)
cd ubb-platform && python -m venv .venv && . .venv/bin/activate   # or .venv\Scripts\activate on Windows
pip install -r requirements.lock.txt && pip install -e ../ubb-sdk
cp .env.example .env   # then edit SECRET_KEY / DEBUG=True; keep the Stripe placeholders or blank them
```

### 1. Bring up PostgreSQL 16 and Redis 7, and confirm versions

```sh
docker exec ubb-postgres psql -U ubb -d postgres -tAc "select version()"     # PostgreSQL 16.x
docker exec ubb-redis redis-cli INFO server | grep redis_version               # 7.x
```

Create a dedicated database rather than reusing `ubb` (a database migrated before the W6 squash cannot migrate
forward; `CLAUDE.md` says to drop and re-create it):

```sh
docker exec ubb-postgres psql -U ubb -d postgres -c "CREATE DATABASE ubb_ash"
export DATABASE_URL=postgres://ubb:ubb@localhost:5433/ubb_ash
export REDIS_URL=redis://localhost:6380/5          # an index the dev stack (/1) and the tests (/15) do not use
```

### 2. Run migrations and the static checks

```sh
cd ubb-platform
python manage.py check                               # "System check identified no issues"
python manage.py migrate                             # 44 migrations on an empty database
python manage.py migrate                             # "No migrations to apply" (idempotent)
python manage.py makemigrations --check --dry-run    # "No changes detected"
python scripts/export_openapi.py && git -C .. status --short -- openapi/    # empty = spec byte-identical
cd .. && python -m tools.gates && python -m tools.forbidden_terms && python -m tools.vocabulary --write
```

Expected: 27 gates installed, 0 owed, migration ledger 0; 0 retired terms on a living surface; 4 generated
artefacts already up to date; `git status` clean.

### 3. Start the web process

```sh
cd ubb-platform && python manage.py runserver 127.0.0.1:8011 --noreload
curl -s http://127.0.0.1:8011/api/v1/health      # {"status":"ok"}
curl -s http://127.0.0.1:8011/api/v1/ready       # {"status":"ready","checks":{"database":"ok","redis":"ok"}}
```

`runserver` is a development server and proves the application, not the production image.

### 4. Start the Celery worker

```sh
cd ubb-platform && celery -A config worker -l INFO --pool=solo          # --pool=solo on Windows
```

The banner must list the nine `ubb_*` queues and the `[tasks]` block must include
`core.tasks.flush_api_key_last_used` and `apps.platform.events.tasks_webhook_cleanup.cleanup_webhook_delivery_attempts`
(the F2 fix). Note: per-task INFO lines from the `ubb.*` loggers are dropped by the logging configuration
(`02` §22), so the log is quiet after the banner; the proof of work is in the database (step 8).

### 5. Start Celery beat

```sh
cd ubb-platform && celery -A config beat -l INFO --schedule /tmp/celerybeat-schedule
```

Exactly one beat process. Its banner names the broker and the schedule file; it logs nothing more at INFO.

### 6. The smallest credible golden path

**6a. Create a tenant and mint a key (operator act; there is no API route for either).** From `ubb-platform/`
with the same environment, in `python manage.py shell`:

```python
from apps.platform.tenants.models import Tenant, TenantApiKey
t = Tenant(name="ash-local"); t.save()            # defaults: billing_mode='external', products=['metering'], enforcement 'off'
key_obj, raw_key = TenantApiKey.create_key(t, label="ash-local")
print(t.id, t.widget_secret, raw_key)             # raw_key is shown ONCE; only its SHA-256 is stored
```

Keep the three values in a local file outside the repository. In this session they lived in the job's temporary
directory and were never copied into the handoff.

**6b. Drive the path through SDK v4 and raw HTTP.** The script this session used is
`golden_path_probe.py` (job tmp; reproduce from the steps below). In order, with `UBBClient(api_key=raw_key,
base_url="http://127.0.0.1:8011", widget_secret=…, tenant_id=…)`:

1. `client.get_tenant_config()` → `billing_mode external`, `tenant_posture metering_only`, `enforcement_mode off`;
   `GET /api/v1/connect/status` → `charges_enabled false`.
2. `client.create_customer(external_id="ash-smoke-1")` → keep the returned UBB customer `id`.
3. Declare a supplier and a reported-cost Event Type and publish it (raw HTTP with the bearer key):
   `POST /api/v1/providers {"key":"openai"}`;
   `POST /api/v1/event-types {"key":"llm.call","costing_method":"reported","provider_key":"openai"}` (a draft, with
   `publication_blockers: ["reported_cost_mapping"]`);
   `PUT /api/v1/event-types/llm.call/reported-cost-mapping {"source_kind":"caller_supplied","amount_representation":"micros","currency":"usd"}`;
   `POST /api/v1/event-types/llm.call/publish` → `declaration_status published`, `published_revision 1`.
4. `PUT /api/v1/metering/pricing/default-markup {"markup_micro_percent": 20000000}` (20%).
5. **Send one controlled usage event:** `client.record_usage(customer_id, "ash-smoke-1-1", event_type="llm.call",
   provider="openai", provider_cost_micros=1_000_000)`.
   **Prove UBB processed it:** the acknowledgement must say `costing_status known`, `provider_cost_micros 1000000`,
   `pricing_status known`, `billed_cost_micros 1200000`, `pricing_method margin_over_cost`, `stop false`, and carry a
   `pricing_receipt` with `receipt_schema_version 2`, `pricing_engine_version "3.0.0"`, `subject_type usage_event`.
   Send the same call again: the same `event_id` comes back (replay).
6. **Read it back through supported client surfaces:** `client.get_usage(customer_id)` lists it (items carry `id`);
   `GET /api/v1/metering/usage/{event_id}` returns `idempotency_key`, `kind metered_usage`, both statuses and
   `measurements_status available`; `GET /api/v1/audit/records` lists the declarations and the customer creation.
7. **Prove the #561 summary:** `token = client.create_widget_token(customer_id)`, then
   `GET /api/v1/me/economics?start_date=<month start>&end_date=<today>` with `Authorization: Bearer <token>` →
   `recorded_events {count 1, status known}`, `customer_revenue {amount_micros 1200000, status known}`.
   Negative control: the same route with the tenant API key → 401.

### 7. A Task lifecycle (optional, exercised in this session)

```python
with client.start_task(customer_id, "ash-task-1") as task:
    client.record_usage(customer_id, "ash-smoke-1-2", event_type="llm.call", provider="openai",
                        provider_cost_micros=500_000, task_id=task.task_id)
    task.complete()
client.get_task(task.task_id)   # status completed, recorded_events 1, total_billed_cost_micros 600000
```

The acknowledgement under the task carries `task_id`, `task_total_billed_cost_micros 600000` and
`ceiling_status not_applicable` (no ceiling configured). The row holds the frozen expiry snapshot
(`start_absolute_deadline_seconds 21600`, `start_silence_window_seconds 900`).

### 8. Show that background dispatch is working

Read the database (any client; `psql` shown) a few seconds after step 6:

```sql
select event_type, status, retry_count from ubb_outbox_event order by created_at;   -- usage.recorded | processed | 0
select handler_name, count(*) from ubb_handler_checkpoint group by 1;               -- platform.webhook_delivery.usage.recorded, subscriptions.cost_accumulator
select posting_count, total_billed_cost_micros from ubb_customer_cost_accumulator;  -- matches the postings
select key_prefix, last_used_at from ubb_tenant_api_key;                            -- set within 5 minutes by beat's flush task (F2)
```

`retry_count 0` with status `processed` within seconds proves the web process's on-commit doorbell reached the
broker (F1). A populated `last_used_at` proves beat → worker → database for a scheduled task. The minutely outbox
sweep also appears in beat's schedule store (`total_run_count` on `sweep-outbox`).

### 9. What cannot faithfully be demonstrated locally

- **Public-HTTPS webhook receipt and its timing (SLO 2).** Registration refuses any non-public URL: in this session
  `http://127.0.0.1:9/hook` and `https://localhost/hook` both answered 422 ("Webhook URL must use https scheme" /
  private host). Delivery re-validates and pins the resolved public IP at send time. Receipt timing is measured only
  on the real host against a controlled public receiver on one clock (brief §0.2).
- **The production image, by digest, running web, worker, beat and the one-off migration.** The repository has no
  Dockerfile; the prep pass proved a draft image locally, and the real W7 re-derives it from the recorded SHA.
- **The HTTPS/proxy behaviour** (`DEBUG=False` turns on SSL redirect, HSTS, `X-Forwarded-Proto` trust and
  `ALLOWED_HOSTS`); CI and local runs use `DEBUG=True`.
- **SLO 1 (p99 ≤ 200 ms at batch sizes up to 100) and SLO 3 (the storm).** Local figures (~13 ms per batch item on
  a laptop) are not a measurement; the brief orders SLO 1 first on the real host and stops W7 on a miss.
- **Customer-wide stops** (`customer.stopped`, `customer.stop_cleared`) have no clean subject in `external` mode
  without the `billing` product; they are carried to a future rail activation. The applicable stop webhooks are
  `task.killed` and `subtask.killed` (require a ceiling and a published Event Type that admits a supplier cost).
- **Payment behaviour** (prepaid wallet, top-ups, postpaid push, plans, subscriptions): not part of the first
  launch and not exercised here.

### 10. Full test suites (safe local verification; one pytest at a time, each creates its own test database)

```sh
cd ubb-platform
python -m pytest apps/platform/tests/test_product_boundaries.py                 # 11 passed
python -m pytest api/v1/tests                                                   # 2,384 passed (7.5 min)
python -m pytest apps/platform core                                             # see 00-README.md
python -m pytest apps/billing apps/metering apps/subscriptions apps/referrals   # see 00-README.md
cd ../ubb-sdk && python -m pytest                                               # 471 passed
cd .. && python -m pytest tests/contracts                                       # 845 passed (unset DJANGO_SETTINGS_MODULE first)
```

The Schemathesis `conformance` suite is non-gating in CI and has one known local-only failure (an un-mocked Stripe
call guard on `POST /api/v1/subscriptions/sync`); the console (`pnpm --dir apps/ui typecheck && pnpm --dir apps/ui
test`), the renderer (`pnpm --dir apps/codegen test`) and the Docker-backed execution suite were not run in this
session and are covered by CI.

### Production-only / do not run yet

These are W7 steps; they need the real inputs, FINAL status, and the merge guard:

- `python R10-W7-RELEASE-EVIDENCE.py record <sha>` / `artifact` / `deploy` / `verify` (project folder).
- Building and pushing the release image; `docker run <image@sha256:…> python manage.py migrate` on the production
  database; starting web, worker and beat on the host.
- Creating the real first tenant in a one-off shell on the release image, minting its key with
  `TenantApiKey.create_key`, handing the key and the widget secret over out of band.
- Any SLO run against the deployed release; the acceptance audit; the two remaining PRs (deployment files;
  signed audit) and the docs-only admission-record PR.
- `seed_dev_data` on any production database (ruled out: it requires a Stripe account and is dev seeding).

## What we need from Ash now

The W7 brief stops at seven **launch inputs**. Four are infrastructure facts (the plain-English request is
`R10-W7-INFRA-FACTS-CHECKLIST.md`); three come from the delivery/business side. None may be a placeholder; W7 does
not launch while any is blank.

**Input 1 — hosting provider and the exact service.** The decision is *which named product will run one immutable
image as three always-on processes plus a one-off command*. The service must be able to: run one container image as
separate web, worker and scheduler processes; deploy by exact digest (`repo@sha256:…`) or give each deployment an
unchangeable release id that maps to a digest (a moving tag is not acceptable); show which digest each of the three
processes is actually running, so it can be read back before the client is switched on; run a one-off command from
the same image (the migration); provide managed PostgreSQL 16 and managed Redis 7 in the same region; hold secrets and
configuration in its own mechanism (never in a committed file); send application logs (JSON app lines plus Celery's
plain text) to a readable log drain; route alerts to a named destination; serve the web process over HTTPS behind a
proxy that sets `X-Forwarded-Proto` and preserves `Host`; allow outbound HTTPS (webhooks to the client); and offer, or
name, a container registry we can push to. Also needed from the host: Redis's eviction policy (the live counters and
cache share one instance) and how health checks reach the app (plain HTTP probes answer 301 under `DEBUG=False`).

**Input 2 — the exact region identifier** (the provider's own code, not a city), where the processes, the database
and Redis live together, and where the SLO receiver and runner will sit relative to them.

**Input 3 — the production account holder/project**: the organisation or person that owns the account, the
provider's account/organisation/project name or id, and the accountable person by name and role, written so an
auditor can identify it without guessing.

**Input 7 — the alert destination**: an exact email address, distribution list or existing provider notification
destination (plus its accountable watcher) for `live_counter.drift_spike` and the dormant prepaid
`wallet.drawdown_repair_spike`, configured through the host, never committed.

**Inputs 4, 5 and 6 come from the delivery/business side, not infrastructure:** the acceptance-audit signer (a named
person); the first real `external` client/tenant identity (never a test tenant); and the named human who accepted
the W7 governance exception and the admission risk (stating explicitly whether that is the same person as the
signer).

**The existing infrastructure requirements, restated:** one immutable image; separate web, worker and beat roles
(beat a singleton); one-off migration as an explicit release operation; deploy and identify by digest; managed
PostgreSQL 16; managed Redis 7; HTTPS inbound; outbound HTTPS; secrets management; logs and a log drain; alerting;
an appropriate container registry.

## What happens once those facts are supplied

The inputs are inserted exactly into the brief, one factual review flips STATUS to FINAL, and W7 launches in a fresh
session. Its sequence (brief §0.5), at a high level:

1. **Deployment files** — the deployment-files PR (Dockerfile keeping the repository shape, a WSGI server, the three
   role commands, the migration command) merges through the W7 merge guard; no product behaviour changes.
2. **Exact release** — record the release SHA and its green CI evidence; build the one image from that SHA with the
   revision label; push; record the digest.
3. **Production environment** — provision managed PostgreSQL 16 and Redis 7, secrets through the host, the log drain,
   alerting to Input 7; run the migration once from the image; start web, worker and beat from the same digest and
   record the host's release id and the three running digests.
4. **SLO 1 first** — p99 ≤ 200 ms including 100-item batches, after warming every web worker; a miss stops W7.
5. **SLO 2 and SLO 3** — `task.killed`/`subtask.killed` receipt timing at a controlled public receiver, and the
   external-mode storm profile; conditions recorded before each run.
6. **Acceptance audit** — the named signer's admission recommendation, with the governance-exception section and the
   named decision-maker; blockers versus accepted limitations ruled, never assumed.
7. **Final release verification** — live re-read of the deployed SHA, release id, target and the three digests;
   `ADMISSION RE-VERIFIED` or stop; the signed-audit PR merges; the re-verification is repeated as the first act of
   admission.
8. **First tenant** — created through the operator path on the release image (Django shell, model APIs, never raw
   SQL), its first key minted with `TenantApiKey.create_key`, key and widget secret handed over out of band,
   `billing_mode external` and no rail re-confirmed.
9. **Real-client golden path** — the client's own action → authoritative processing and persistence → readback on a
   supported surface → the #561 usage-summary proof (P2 if the client uses SDK v4, else P1; P3 where a Task lifecycle
   is representative; webhooks supplementary). The exact wheel is handed over with its SHA-256.
10. **Durable admission record** — a docs-only PR deletes the dated pre-admission note from
    `docs/api-compatibility.md`, and one comment on #540 records the tenant, the time, the re-verification, the
    release SHA and running digest, the golden-path result and the five-line report. W7 is complete only when that
    comment exists.
