# Load / soak / chaos harness for the ~500 events/s enforcement proof

**Date:** 2026-07-13 · **Ticket:** [#14](https://github.com/ashcochrane/ubb/issues/14) (parent map: #9, blocks #15)
**Question:** what harness should run the proof — load, soak, and chaos — for Django + Postgres +
Redis + Celery with an authenticated JSON batch-ingest endpoint at ~500 events/s sustained?

---

## Recommended harness

One primary recommendation per leg; evidence in the numbered sections below.

| Leg | Recommendation |
|---|---|
| **Load tool** | **Grafana k6**, `constant-arrival-rate` executor (open model), `check()` on the parsed per-item verdicts array + `thresholds` on `checks` rate / `http_req_duration p(99)` / `dropped_iterations`. Client-side p99 from k6; **server-side p99 truth from django-prometheus histograms** — assert on both. Locust is the sanctioned fallback if reusing Python payload builders outweighs the open-model loss. |
| **Soak approach** | **Synthetic generation — replay is impossible pre-launch** (GoReplay needs live traffic to capture). A k6 `ramping-arrival-rate` scenario whose `stages` are sampled from a diurnal sine curve (mean ≈ 500 events/s) plus scheduled burst stages, run as chained 2–3-day segments for ≥1 week, with the k6 "running large tests" generator-hygiene guidance applied. |
| **Chaos tooling** | **Toxiproxy** (compose service in front of Redis and Postgres; `down`/`timeout`/`latency` toxics flipped via its HTTP API) **+ Pumba or plain `docker kill`/`docker compose restart`** for Celery-worker kills and Postgres restarts. The harness owns the fault schedule and brackets every fault window with a tagged **Grafana region annotation**; Prometheus + node/postgres/redis/celery exporters + polling `GET /ops/ingest-health` are the observation base. Chaos Mesh / Litmus need Kubernetes — out of scope; AWS FIS only if the stack moves onto managed AWS services. |
| **Environment shape** | **Managed Postgres + managed Redis + two VMs** (app+Celery box, load-gen box), stood up with a thin Terraform module. Cheapest credible: DigitalOcean managed PG 8 GB + managed Valkey 1 GB + 2 droplets ≈ **$270/mo ≈ $63 for the proof week**. AWS equivalent (db.m7g.large + cache.t4g.medium + c7g.xlarge + m7g.large) ≈ **$360–375/mo ≈ $85–95/week**. Never a burstable (t4g) DB for the soak week. **Pin Redis `maxmemory-policy=noeviction`** — eviction silently deletes enforcement counters. |
| **Overshoot assertion** | Assert the **money bound from Postgres ground truth** (Σ accepted spend per owner vs. configured limit), with client-side verdicts as the cross-check; state the bound as *rate × fail-open window* during injected Redis outages. Prior art: Cloudflare's measured limiter overshoot, Google's published 30% quota error margin, Stripe's fail-open limiter, and Jepsen/TigerBeetle/FoundationDB's "assert the invariant while injecting the fault" discipline. |

---

## What the harness must drive (repo reality)

Grounding from `ubb-platform/api/v1/metering_endpoints.py`, `apps/billing/gating/services/hold_service.py`,
`apps/metering/usage/tasks.py`, `config/settings.py`, and `docker-compose.yml`:

- **Two ingest paths, both always-HTTP-200 with per-item verdicts.** `POST /usage/batch` (sync,
  1–100 independent items, per-item `{"ok": bool, "error": ...}`) and `POST /usage/ingest` (async
  accept: idempotency SETNX prefilter → estimate → pipelined Lua hold per owner → durable
  `RawIngestEvent` bulk append → per-item
  `{accepted, rejected, reason, stop, stop_reason, stop_scope, estimated_cost_micros, mode, duplicate_suspect}`).
  **Status-code-only tools are blind here** — a fully-rejected batch is still HTTP 200. The
  harness must parse the body and assert positionally against the batch it sent.
- **Auth** is an API-key header (`ApiKeyAuth`), plus the `metering_async` product flag for
  `/usage/ingest` (403 `feature_not_enabled` otherwise).
- **The money gate fails OPEN.** `HoldService.acquire` "NEVER raises: any error (Redis
  unreachable, etc.) fails OPEN — every item is held, unstopped", and the idempotency prefilter
  fails open too. So the chaos leg's Redis-down window is precisely where overshoot accrues by
  design — the proof's job is to *measure* that accrual and check it against the stated bound,
  not to show zero.
- **Settlement is Celery.** `settle_raw_events` (queue `ubb_metering`) settles raws exact; the
  on-commit dispatch is a fast path with a **10s beat sweep** as backstop. Killing Celery
  workers delays estimate→exact settlement (drift between live counters and durable truth), it
  must not lose events (`RawIngestEvent` is durable pre-response). Postgres restart hits the
  durability boundary itself: the endpoint 503s, releases holds, and unwinds fresh idem keys —
  the harness should assert the client retry after a 503 re-enters the gate.
- **Existing observation hook:** `GET /ops/ingest-health` (X-Ops-Token; settle-lag warn 120s,
  queue-depth warn 10000) — poll it throughout the run.
- **Enforcement modes** (`off`/`advisory`/`enforcing`): the proof runs in `enforcing`; an
  `advisory` control run is cheap and isolates gate overhead.
- **Current compose is minimal** (`postgres:16`, `redis:7`, host-run app/workers) — the harness
  environment must add the production-shaped pieces (§4).
- **Rate math:** 500 events/s at batch size 10–100 is only **5–50 HTTP req/s** — trivial for any
  generator; the hard part is assertions and measurement, not raw throughput.

---

## 1. Load tools: authenticated batch POST + per-item verdict assertions

### k6 (recommended)

- **Auth batch POST:** `http.post(url, JSON.stringify(batch), {headers: {"X-API-Key": ...}})`
  ([k6 http.post](https://grafana.com/docs/k6/latest/javascript-api/k6-http/post/)).
- **Per-item verdicts:** `Response.json()` parses and caches the body
  ([k6 Response](https://grafana.com/docs/k6/latest/javascript-api/k6-http/response/)); assert with
  `check()`:

  ```js
  check(res, {
    "every verdict as expected": (r) => r.json().results.every(
        (v, i) => v.accepted === expected[i].accepted),
    "counts align": (r) => r.json().accepted + r.json().rejected === batch.length,
  });
  ```

  Failed checks don't abort the run by themselves — bind them to a threshold
  (`thresholds: {checks: ["rate>0.999"]}`) to make the run pass/fail
  ([checks](https://grafana.com/docs/k6/latest/using-k6/checks/),
  [thresholds](https://grafana.com/docs/k6/latest/using-k6/thresholds/)).
- **Open model:** `constant-arrival-rate` / `ramping-arrival-rate` start iterations
  "independently of system response"
  ([constant-arrival-rate](https://grafana.com/docs/k6/latest/using-k6/scenarios/executors/constant-arrival-rate/),
  [open vs closed](https://grafana.com/docs/k6/latest/using-k6/scenarios/concepts/open-vs-closed/)) —
  the offered event rate holds when the SUT slows down, which matters most during fault windows.
  Caveat: k6 *drops* (does not delay) unsendable iterations — put `dropped_iterations` in a
  threshold so a silently-undershot run fails
  ([dropped iterations](https://grafana.com/docs/k6/latest/using-k6/scenarios/concepts/dropped-iterations/)).
- **p99:** client-side — `http_req_duration` = sending + waiting + receiving, measured in-process
  ([metrics reference](https://grafana.com/docs/k6/latest/using-k6/metrics/reference/)). Export to
  Prometheus via `-o experimental-prometheus-rw` (trend stats or native histograms)
  ([Prometheus remote write](https://grafana.com/docs/k6/latest/results-output/real-time/prometheus-remote-write/)).
- **Headroom:** a single instance is documented to ~300k req/s / 30–40k VUs
  ([running large tests](https://grafana.com/docs/k6/latest/testing-guides/running-large-tests/));
  we need 5–50 req/s. Note `discardResponseBodies` (their memory tip) is off the table globally —
  we must parse bodies — but at this rate it's irrelevant.

### Locust (Python-native fallback)

- Plain Python (`self.client.post("/usage/ingest", json=batch, headers=...)`) — can import the
  repo's existing payload builders/SDK directly
  ([locustfile docs](https://docs.locust.io/en/stable/writing-a-locustfile.html)).
- Per-item assertions via `catch_response=True` + `response.failure(...)` — full Python logic,
  the best assertion ergonomics of any tool (same docs page).
- **Closed model:** `constant_throughput(x)` waits so a task runs "*(at most)* X times per
  second" — it can only constrain, never guarantee, the rate; when the SUT stalls the offered
  load sags — the classic coordinated-omission failure mode
  ([wait_time docs](https://docs.locust.io/en/stable/writing-a-locustfile.html#wait-time-attribute)).
  Over-provision users so pacing rarely binds if using it.
- **p99 caveat:** Locust's percentiles are approximated twice — response times bucketed to ~2
  significant digits, live percentiles over a ~10s sliding window; the report header itself says
  "approximated" ([locust/stats.py](https://docs.locust.io/en/stable/_modules/locust/stats.html)).
  Treat as indicative; defer p99 truth to server-side histograms.
- Throughput is a non-issue: ~16k req/s per core with `FastHttpUser`
  ([increase performance](https://docs.locust.io/en/stable/increase-performance.html));
  distributed master/worker exists ([running distributed](https://docs.locust.io/en/stable/running-distributed.html)).

### Vegeta, wrk2, Gatling, Artillery

- **Vegeta:** true constant-rate open model and per-target headers/body files, but "success" is
  **status-code only** (2xx/3xx) — it would report 100% success while every item was rejected.
  Body capture (`-max-body` + `vegeta encode`) permits only offline post-hoc verdict checking
  ([Vegeta README](https://github.com/tsenart/vegeta)). Not the primary harness.
- **wrk2:** the canonical coordinated-omission-corrected generator — measures from the *intended*
  send time (its README demos p99 = 6ms uncorrected vs 1.27s corrected under a stall)
  ([wrk2 README](https://github.com/giltene/wrk2)). No practical per-item assertion path; use as
  a one-off cross-check that k6's client p99 isn't a measurement artifact.
- **Gatling:** open-model injection + strong JSON checks (`jsonPath`/`jmesPath`)
  ([injection](https://docs.gatling.io/concepts/injection/), [checks](https://docs.gatling.io/concepts/checks/)),
  but a JVM toolchain in a Python shop.
- **Artillery:** open arrival model in YAML + `expect` plugin (`hasProperty`/`jmespath`)
  ([test-script](https://www.artillery.io/docs/reference/test-script),
  [expect](https://www.artillery.io/docs/reference/extensions/expect)); positional
  zip-against-sent-batch assertions need a JS processor anyway — no advantage over k6 here.

### Server-side vs client-side p99

Every tool above measures latency **client-side**. The standard practice is a server-side
histogram compared against it: **django-prometheus** middleware exports
`django_http_requests_latency_seconds_by_view_method` (histogram, labeled by view/method,
buckets configurable via `PROMETHEUS_LATENCY_BUCKETS`)
([README](https://github.com/django-commons/django-prometheus),
[metrics.md](https://github.com/django-commons/django-prometheus/blob/master/documentation/metrics.md)).
The client−server delta isolates network + queueing in front of Django (gunicorn/nginx backlog),
which the server number cannot see. Why closed-model client percentiles lie: Gil Tene's
coordinated-omission analysis — a closed loop stops sampling exactly when the system is bad,
skewing percentiles by orders of magnitude
([How NOT to Measure Latency](https://www.infoq.com/presentations/latency-response-time/)).
Add histogram buckets around the SLO boundary and aggregate across gunicorn workers in PromQL.

---

## 2. Generating ≥1-week soak traffic with no production traffic

- **Replay is out.** GoReplay is "capturing and replaying **live** HTTP traffic" — it needs a
  running production to listen to ([GoReplay README](https://github.com/buger/goreplay)). A
  pre-launch product has nothing to capture; the soak must be synthetic.
- **The soak pattern is documented:** k6's soak-testing guide — average load held for an extended
  plateau, hunting "response time degradation, memory or other resource leaks, data saturation,
  and storage depletion", with backend monitoring called out as especially important
  ([k6 soak testing](https://grafana.com/docs/k6/latest/testing-guides/test-types/soak-testing/)).
  Its canonical durations top out at ~72h; a week is just a longer plateau — run it as chained
  2–3-day segments so a generator restart is a planned event, not an incident.
- **Shape:** `ramping-arrival-rate` `stages` sampled from a 24h sine (mean 500 events/s, e.g.
  ±40% amplitude, one stage per 30–60 min for 7 days) plus scheduled burst stages
  ([ramping-arrival-rate](https://grafana.com/docs/k6/latest/using-k6/scenarios/executors/ramping-arrival-rate/)).
  Locust's official `double_wave.py` custom `LoadTestShape` is the citable diurnal template if
  Locust is chosen ([custom load shapes](https://docs.locust.io/en/stable/custom-load-shape.html),
  [double_wave.py](https://github.com/locustio/locust/blob/master/examples/custom_shape/double_wave.py)).
- **Vary the payload mix, not just the rate:** rotate customers/runs/idempotency keys with a
  deliberate duplicate-replay fraction (exercises the SETNX prefilter), a backdated
  `effective_at` fraction (exercises the I9 prior-month skip), and run-capped runs that
  provably hit `cost_limit_exceeded` — the soak's job is to age exactly the paths the
  enforcement proof asserts on.
- **Generator hygiene for multi-day runs:** k6 documents ~1–5 MB/VU, fd-limit and port-range
  tuning, and keeping generator CPU <80%
  ([running large tests](https://grafana.com/docs/k6/latest/testing-guides/running-large-tests/)).
  Watch the generator box with node_exporter like any other component.
- **If generation outgrows one box** (it won't at 5–50 req/s): AWS's Distributed Load Testing
  solution runs k6/Locust/JMeter on Fargate on a schedule
  ([aws-solutions/distributed-load-testing-on-aws](https://github.com/aws-solutions/distributed-load-testing-on-aws)).

---

## 3. Chaos tooling: drop Redis, kill Celery workers, restart Postgres

### Fault injection

- **Toxiproxy** (Shopify) — a TCP proxy "made specifically to work in testing, CI and development
  environments, supporting deterministic tampering with connections"; toxics include `down`,
  `timeout` (blackhole: drops data, holds the connection), `latency`+jitter, `bandwidth`,
  `reset_peer`; controlled via HTTP API (port 8474), CLI, or client libraries incl. Python
  ([Toxiproxy README](https://github.com/Shopify/toxiproxy)). **Fit:** run as a compose service;
  point Django/Celery at `toxiproxy:6379→redis:6379` and `toxiproxy:5432→postgres:5432`. This
  gives *distinct, deterministic* Redis experiments — hard down (reset) vs blackhole (timeout) vs
  degraded (latency) — which matter here because `HoldService` fails open on error but a
  *slow* Redis instead stretches request latency. Same proxy trick covers Postgres network
  faults without touching the container.
- **Pumba** — chaos for Docker containers: kill/stop/pause/restart by name/`re2:` regex/label,
  with `--random` and `--interval` for recurring chaos, plus netem and stress-ng modes
  ([Pumba README](https://github.com/alexei-led/pumba)). **Fit:**
  `pumba --interval 4h kill re2:^celery-worker` covers worker kills. Plain
  `docker kill` / `docker compose restart postgres` driven by the harness script is equally
  legitimate for one-shot faults — pumba's value is targeting/randomization/recurrence.
- **Cloud-native:** Chaos Mesh is Kubernetes-CRD-based ([docs](https://chaos-mesh.org/docs/));
  LitmusChaos likewise needs a k8s control plane
  ([What is Litmus](https://docs.litmuschaos.io/docs/introduction/what-is-litmus)) — both out of
  scope for compose/VM. AWS FIS applies if components move to managed AWS: `aws:rds:reboot-db-instances`,
  `aws:elasticache:replicationgroup-interrupt-az-power`, ECS task kill/network actions, and
  SSM send-command for arbitrary on-VM faults
  ([FIS actions reference](https://docs.aws.amazon.com/fis/latest/userguide/fis-actions-reference.html)).
  Gremlin (commercial) does support plain hosts/Docker if a paid option is ever wanted
  ([compatibility](https://www.gremlin.com/docs/getting-started-compatibility)).

### Observation hooks

- **The harness is the source of truth for fault windows.** Toxiproxy and pumba are invoked by
  the harness/cron — neither has an event bus — so the harness timestamps every fault
  start/stop itself and **posts a tagged Grafana region annotation**
  (`POST /api/annotations` with `time`+`timeEnd`, tags like `["chaos","redis-down"]`), making
  fault windows overlay every dashboard
  ([Grafana annotations API](https://grafana.com/docs/grafana/latest/developers/http_api/annotations/)).
  (AWS FIS, if used, emits state changes to EventBridge instead:
  [FIS EventBridge](https://docs.aws.amazon.com/fis/latest/userguide/monitoring-eventbridge.html).)
- **Metrics base:** Prometheus + [node_exporter](https://github.com/prometheus/node_exporter) +
  [postgres_exporter](https://github.com/prometheus-community/postgres_exporter) +
  [redis_exporter](https://github.com/oliver006/redis_exporter) +
  [danihodovic/celery-exporter](https://github.com/danihodovic/celery-exporter) (broker-event
  based — `celery_queue_length`, `celery_worker_up`, task counters; no app changes; ships a
  Grafana dashboard), with django-prometheus (§1) for server-side latency and k6's
  Prometheus-RW output alongside. Flower is an optional live UI
  ([Flower Prometheus](https://flower.readthedocs.io/en/latest/prometheus-integration.html)).
- **Repo-native hook:** poll `GET /ops/ingest-health` (X-Ops-Token) on a 30s loop and record it —
  settle lag and raw-queue depth are exactly the metrics that should spike and recover around
  worker-kill windows.

### Minimum fault matrix for the proof

| Fault | Mechanism | What to watch |
|---|---|---|
| Redis hard down (30s / 5min) | toxiproxy `down` toxic | fail-open: verdicts all-held, overshoot accrual rate, recovery reconcile |
| Redis blackhole | toxiproxy `timeout` toxic | client timeouts vs fail-open path; p99 |
| Redis +50–500ms latency | toxiproxy `latency` toxic | ingest p99 (pipelined Lua holds are per-owner round trips) |
| Celery worker kill (repeat) | pumba / `docker kill` | settle lag, queue depth, no lost raws, exactly-once settle |
| Postgres restart | `docker compose restart postgres` | 503s + hold release + idem unwind; client retry re-enters gate |

---

## 4. Environment shapes and cost

(Prices date-checked 2026-07-13; AWS pages render prices via JS, so per-hour figures are from
the Vantage mirror of the AWS Price List API with the official pages as canonical.)

- **Shape A — AWS managed** (us-east-1, on-demand, single-AZ): RDS PostgreSQL **db.m7g.large**
  ~$0.168/hr ≈ $123/mo ([Vantage](https://instances.vantage.sh/aws/rds/db.m7g.large); canonical
  [RDS PG pricing](https://aws.amazon.com/rds/postgresql/pricing/)); ElastiCache
  **cache.t4g.medium** ~$0.065/hr ≈ $47/mo ([Vantage](https://instances.vantage.sh/aws/elasticache/cache.t4g.medium));
  EC2 **c7g.xlarge** (app+Celery) ~$0.145/hr ≈ $106/mo and **m7g.large** (load-gen+observability)
  ~$0.0816/hr ≈ $60/mo ([Vantage](https://instances.vantage.sh/aws/ec2/c7g.xlarge)); 200 GB gp3
  ≈ $23/mo. **Total ≈ $360–375/mo → ≈ $85–95 for the proof week.**
  **Do not use a burstable (t4g) DB instance for the soak** — a 24/7 week at 500 events/s drains
  CPU credits and silently changes the performance profile mid-proof.
- **Shape B — DigitalOcean managed** (official pages): Managed PostgreSQL 8 GB/4 vCPU
  **$122.10/mo** (140–280 GiB included), Managed Caching (Valkey) 1 GB **$15/mo**
  ([DO databases pricing](https://www.digitalocean.com/pricing/managed-databases)); CPU-Optimized
  8 GB droplet **$84/mo** + Basic 8 GB droplet **$48/mo**
  ([DO droplets](https://www.digitalocean.com/pricing/droplets)).
  **Total ≈ $270/mo → ≈ $63 for the proof week** (budget 4 GB-PG variant ≈ $148/mo ≈ $35/week,
  but its 120 GiB storage ceiling is tight against a week of rows).
- **Shape C — Hetzner self-managed:** post-2026-06-15 price rises gutted the CPX/CCX bargain
  ([price adjustment](https://docs.hetzner.com/general/infrastructure-and-availability/price-adjustment/));
  CX-line boxes are still ~€16–30/mo but you self-operate Postgres/Redis, which undercuts the
  managed-parity argument for a billing proof. Not recommended.
- **IaC:** a thin Terraform module (official
  [AWS provider](https://registry.terraform.io/providers/hashicorp/aws/latest/docs) or DO
  provider) is worth the ~day of setup: the proof environment must be reproducible and
  disposable — a chaos finding means fix-and-re-run. Full IaC ecosystems are overkill.
- **Storage sizing:** ~300M rows/week at ~150–350 B/row ≈ 45–105 GB heap, ×1.5–2.5 with
  indexes → provision **~100–250 GB**. gp3's included 3,000 IOPS / 125 MB/s baseline
  ([EBS pricing](https://aws.amazon.com/ebs/pricing/)) is adequate for 500 batched inserts/s.

### What "production-shaped minimally" means here

Citable frame: AWS Well-Architected REL12-BP03 — create a production-scale test environment on
demand rather than a scaled-down one that yields "inaccurate predictions of production behaviors"
([REL12-BP03](https://docs.aws.amazon.com/wellarchitected/latest/reliability-pillar/rel_testing_resiliency_test_non_functional.html));
k6's guidance to run in pre-production that resembles production with production-modeled data
([API load testing guide](https://grafana.com/docs/k6/latest/testing-guides/api-load-testing/)).
Translated to this stack, the minimal checklist:

1. Same major versions as the target production (postgres 16, redis 7 — as in the repo compose).
2. **Real network hop** app→Postgres and app→Redis (managed endpoints give this for free); the
   Lua-hold pipeline's round-trip cost is invisible on localhost.
3. Celery workers as separate processes on the app box; **load generator on its own box**.
4. **Pre-seeded data volume** (~week-scale row counts) so indexes, vacuum, and the analytics
   queries behave realistically; connection pooling as production will run it
   ([PgBouncer](https://www.pgbouncer.org/) or [RDS Proxy](https://aws.amazon.com/rds/proxy/)) —
   otherwise the proof measures connection-storm behavior, not the system.
5. **Redis parity is the money-critical one:** the official eviction doc — `noeviction` returns
   errors at `maxmemory`, while every `allkeys-*`/`volatile-*` policy **deletes keys**
   ([Redis key eviction](https://redis.io/docs/latest/develop/reference/eviction/)). The
   enforcement counters (`ubb:livebal:*`, `ubb:livespend:*`, `ubb:runcost:*`, `ubb:idem:*`) all
   carry TTLs, so a `volatile-*` policy makes them *eviction candidates*: an evicted counter
   re-seeds and the gate re-opens. Pin `maxmemory-policy=noeviction` explicitly (managed
   defaults historically differ — e.g. ElastiCache's `volatile-lru`) and size memory for the
   7-day idem-key TTL (the largest keyspace: one key per event, 7-day expiry).
6. TLS on (managed endpoints enforce it), `enforcement_mode=enforcing` on the proof tenant.

---

## 5. Prior art: measuring overshoot — asserting a money bound

The proof's assertion shape — *accepted spend may exceed the limit by at most B under load and
faults* — has strong, specific precedent:

- **Cloudflare** ("How we built rate limiting capable of scaling to millions of domains") is the
  canonical *measured overshoot* writeup: over 400M requests, their sliding-window approximation
  wrongly actioned **0.003%** of requests, averaged **6%** divergence from the true rate, and the
  worst false-negatives were **<15% above threshold** — an empirically stated, bounded error
  ([blog.cloudflare.com](https://blog.cloudflare.com/counting-things-a-lot-of-different-things/)).
- **Google Cloud Endpoints quotas** publish bounded overshoot *as a contract*: "the enforced
  quota limit is approximate, with a 30% margin of error"
  ([quotas overview](https://docs.cloud.google.com/endpoints/docs/openapi/quotas-overview)).
  AWS documents EC2 API throttling as a token bucket whose bucket size *is* the stated burst
  bound ([EC2 throttling](https://docs.aws.amazon.com/AWSEC2/latest/APIReference/throttling.html)).
  Precedent that "bounded, not zero" is the honest contract for distributed enforcement.
- **Stripe** ("Scaling your API with rate limiters") is the direct precedent for this repo's
  fail-open gate: "if Redis were to go down… any coding or operational errors would fail open
  and the API would still stay functional" ([stripe.com/blog/rate-limiters](https://stripe.com/blog/rate-limiters)).
  **GitHub's** sharded Redis limiter likewise documents Lua-for-atomicity plus a known,
  accepted overshoot from post-hoc increments
  ([github.blog](https://github.blog/engineering/infrastructure/how-we-scaled-github-api-sharded-replicated-rate-limiter-redis/)).
- **Metering vendors state exactly-once as bounded too:** OpenMeter dedups within a 32-day
  stream window ([usage deduplication](https://openmeter.io/blog/usage-deduplication),
  [consistent Kafka consumer](https://openmeter.io/blog/consistent-kafka-consumer)); Orb's
  idempotency-key dedup "is guaranteed only during the grace period window"
  ([Orb ingest docs](https://docs.withorb.com/quickstart/ingest)) — matching this repo's 7-day
  idem-key TTL as a bounded window, not an absolute.
- **Invariant-under-fault as a discipline:** Jepsen — inject partitions/crashes into real
  systems, check safety invariants (lost updates, lost committed writes)
  ([jepsen.io](https://jepsen.io/)); TigerBeetle's VOPR — a whole cluster of real code under
  simulated network/storage/process faults with thousands of assertions on *financial
  invariants* ([safety](https://docs.tigerbeetle.com/concepts/safety/),
  [VOPR](https://github.com/tigerbeetle/tigerbeetle/blob/main/docs/internals/vopr.md));
  FoundationDB's deterministic simulation ([testing](https://apple.github.io/foundationdb/testing.html)).
  The proof applies the same method — a money invariant checked continuously while faults run —
  with docker-compose-grade tooling.

### Applying it to this repo

- **Ground truth is Postgres, not the client.** Per proof tenant/owner, assert at end of run
  (after the hourly reconciles):
  `overshoot(owner) = max(0, Σ UsageEvent.billed_cost_micros − limit)` for prepaid balance /
  postpaid `min_balance`/threshold, and per-run
  `Σ event cost − cost_limit_micros` for capped runs. The k6-side per-item verdicts are the
  cross-check: count events *accepted after* the first `stop: true` / `hard_stop_exceeded`
  verdict — that count × estimate is the client-visible overshoot and should reconcile with the
  DB number.
- **State the bound before the run, in the fail-open currency.** With a fail-open gate the
  honest bound during a Redis outage is
  `B ≈ ingest_rate × mean_estimate × outage_window` (plus one reconcile interval of drift) —
  i.e. Cloudflare/Google-style "approximate with a stated margin", not zero. Steady-state
  (Redis healthy) the Lua check-and-reserve is atomic, so the expected steady-state overshoot
  is at most in-flight estimates (one batch per owner) — assert near-zero there, and the
  rate×window bound only inside annotated chaos windows.
- **Assert both directions:** overshoot (money admitted past the limit) and *over-restriction*
  (spend wrongly rejected while under the limit — Cloudflare counted false positives too);
  plus the drift metric: livespend/livebal counter vs durable Σ during and after fault windows
  (the MAX-merge reconcile should converge it within one cycle).

---

*Research for wayfinder ticket #14; produced from the three primary-source sweeps (load tools,
soak+chaos, environment+overshoot) on 2026-07-13. Frozen history per the repo ratchet — fold
lasting decisions into ADRs/conventions when the harness is actually built (#15).*
