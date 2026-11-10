ENGINEERING HANDOFF — CURRENT CODE SNAPSHOT — NOT ADMISSION EVIDENCE

# 01 — What UBB is now

Anchored to `origin/main` = `1bf0c0ca772410fa5aa721f733736f5f83e66760` (verified current on 2026-11-02 14:34 NZST).
Everything below was derived from that commit's code, schema, contract, SDK, tests and a local run of the stack;
planning documents were used only to explain *why*. Where a sentence rests on a document rather than on code, it
says so. Detail and citations are in `02-TECHNICAL-SYSTEM-MAP.md`; the verification procedure and the next steps are
in `03-ASH-VALIDATION-AND-NEXT-STEPS.md`.

## In one paragraph

UBB is a usage-metering, pricing, spend-control and margin service that sits between an AI application and Stripe.
A tenant (the client business) declares what it meters (Event Types), what its suppliers charge (cost books), what it
charges its own customers (pricing books, a default markup, agreed prices for fixed-price work), and the limits it
wants enforced (ceilings on units of work, spend pools, wallet floors). The client's software then sends one HTTP
call per usage event. UBB prices it synchronously, records an immutable economic posting with a signed-off "pricing
receipt" explaining the amount, rolls it into the unit of work it belongs to, decides on the spot whether anything
must stop, and answers with an acknowledgement that carries the cost, the price and the stop verdict. Everything
downstream (webhooks, cost accumulators, reports, reconciliation) is driven by a transactional outbox and Celery.
Stripe is still the billing engine for tenants that choose a payment rail; the first external client uses the
`external` billing mode, in which UBB meters and reports and moves no money at all.

## The major capabilities that actually exist (all exercised by code, tests or the local run)

- **Usage recording.** `POST /api/v1/metering/usage` (and a batch of up to 100). Quantities travel as exact decimal
  text (floats and JSON numbers are refused); a caller may report the supplier's cost in micros; a caller may never
  state the customer price. Idempotency is a client-supplied key, enforced by a database unique constraint; a replay
  returns the original acknowledgement unchanged.
- **Event Types.** A tenant-declared vocabulary of what it meters: a supplier, declared quantities with units, and
  where the supplier's cost is read from. Declarations are drafts until published; recording reads only the last
  publication. An event naming a type nobody published is still recorded, with its cost and price honestly marked
  unresolved, and the name is held for later resolution.
- **Pricing.** Cost books (supplier rates) and pricing books (customer rates) hold rules selected by up to fourteen
  selectors and ranked by specificity; a tenant default markup is the last rung; fixed-price kinds of work carry an
  agreed price. Every change to a book is a dated publish, never an edit. Every posting carries a pricing receipt
  (schema 2, engine 3.0.0) that explains the amount down to the rule ids. Money is integer micros, USD only; there is
  no FX.
- **Tasks and Subtasks.** A unit of work is a kernel concept: started with a client key, fed by usage events that
  name it, closed by the client with a declared outcome, or stopped by UBB (killed on a ceiling, expired on silence
  or deadline). Status transitions, the stop facts and the expiry snapshot are guarded by PostgreSQL triggers.
  Delivered fixed-price work is charged once.
- **Spend control.** Four families: unit ceilings (always on), admission control (a per-customer start rate limit),
  customer spend pools, and wallet policy (hard and soft floors, prepaid only). Ceilings are decided synchronously on
  the recording path and the kill runs on commit; customer-wide stops are driven through a stop-signal ledger, a Redis
  live counter when the tenant opts into `enforcing`, and hourly reconciles and a patrol as backstops.
- **Billing modes.** `external` (meter only; the default), `prepaid` (wallet, credit grants, Stripe top-ups, auto
  top-up) and `postpaid` (monthly usage pushed to the customer's Stripe subscription as line items). A money mode
  requires an enabled payment-rail activation; that rule is held by a database trigger as well as by the model.
- **Plans, subscriptions, referrals.** A plan catalog (access fee, per-seat fee, a pricing book) realised as Stripe
  Prices; subscribe, seats, cancel, pause, resume driven through Stripe; a referrals product that accrues rewards
  from referred customers' usage. All three gate on products the first external client will not have enabled.
- **Reporting.** One economic query (supplier cost, customer revenue, gross margin, recorded events) with declared
  grouping fields; spend-control reports (stops and breaches, utilisation and headroom); task analytics; the tenant
  audit feed; and the end-customer usage summary (#561) at `GET /api/v1/me/economics`, read with a short-lived widget
  token signed by the tenant's widget secret.
- **Webhooks.** 37 event types in the contract, delivered to tenant-registered public HTTPS endpoints only (private
  and loopback addresses are refused at registration and again at send time), signed with a timestamped HMAC
  (`X-UBB-Signature-V2`), retried through the outbox backoff.
- **API.** One `/api/v1` surface: 160 operations on 123 paths, described by the committed `openapi/v1.json`, which
  is byte-identical to what the running code generates and is the baseline the breaking-change gate measures against.
- **SDK v4.** `ubb-sdk` 4.0.0, Python 3.10+, synchronous `httpx`, a hand-written shell over a generated core stamped
  with the spec's SHA-256. It is delivered as a reproducibly built wheel, not from PyPI.
- **Code Builder.** The server resolves a tenant's selection of Event Types and kinds of work into an "Integration
  Blueprint" (stored by fingerprint); a TypeScript renderer turns it into a Python module or a shell file; a verify
  route runs the generated calls in a throwaway tenant. The renderer runs only in the console.
- **Console.** A React tenant console (`apps/ui`) with pages for events, tasks, customers, pricing, spend controls,
  webhooks, developers (API keys, sandbox, Code Builder) and settings. It runs in mock mode by default and has no
  production deployment.
- **Operator surface.** Django admin, for tenant creation and inspection. No API route creates a tenant.

## The primary client integration model

1. An operator creates the tenant (admin or Django shell) and mints the first API key with
   `TenantApiKey.create_key`; the raw key is shown once and only its SHA-256 is stored.
2. The client calls `/api/v1` with `Authorization: Bearer ubb_live_…` (a `ubb_test_` key always routes to the
   tenant's sandbox sibling). Keys default to the admin role; member users may instead sign in through Clerk when it
   is configured.
3. The client creates its customers (`POST /api/v1/platform/customers`), optionally declares and publishes Event
   Types and prices, then sends usage events (directly or through `UBBClient.record_usage`) and, where its work has a
   lifecycle, starts and closes Tasks.
4. The acknowledgement is the primary verdict channel: cost, price, receipt, and a `stop` flag with its reason and
   scope. The SDK raises `UBBStopRequested` on a stop by default.
5. Webhooks are a supplementary push channel; the read endpoints (single event, customer usage, task, reports,
   `/me/economics`) are the readback channel.

## How usage enters UBB and what UBB does with it (derived from the code path, confirmed by the local run)

```
client → POST /api/v1/metering/usage (API key or SDK v4)
      → ApiKeyAuth (SHA-256 lookup, role floor, product gate)
      → replay check on (tenant, customer, idempotency_key)
      → admit: last published Event Type declaration, supplier, cost field, quantities, grouping values
      → one transaction: price (ladder → receipt) → Posting + PostingMeasurement
           → hold any undeclared name → roll into the Task → live counter (if enforcing)
           → StopAcknowledgement → stop context → outbox row `usage.recorded`
      → on commit: outbox doorbell (Celery) and any ceiling kill
      → 200 acknowledgement (event_id, costing/pricing status, receipt, stop verdict)
worker → process_single_event → handlers: webhook delivery, cost accumulator, (billing drawdown if `billing`)
beat   → minutely outbox sweep, 5-minute task sweepers, hourly reconciles, daily prune and snapshots
client → GET /metering/usage/{event_id} · GET /metering/customers/{id}/usage · GET /tasks/{id}
      → GET /me/economics with a widget token (#561) · webhook POST to a public https endpoint
```

In the local run on this commit: a reported supplier cost of 1,000,000 micros under a published Event Type and a 20%
default markup produced `costing_status: known`, `pricing_status: known`, `billed_cost_micros: 1200000`, a receipt
with schema 2 and engine 3.0.0; the replay returned the same `event_id`; the single-event and customer-usage reads
returned it; `/me/economics` reported one recorded event and 1,200,000 micros of revenue, both `known`, and refused
the tenant API key; three outbox rows were processed with zero retries; a Task started, accumulated one event, was
closed as delivered and read back `completed`.

## Tasks and Subtasks: the control model

- A Task is started with the client's own idempotency key; a Subtask is the same call with `parent_task_id`
  (one level only, and it must share its parent's pricing regime, held by a trigger).
- At start UBB resolves the policy that will apply: the ceiling (task type rung, tenant default, or the caller's
  lower cap), the expiry windows (silence and absolute deadline), and for fixed-price kinds the agreed price. The
  windows the start promised are frozen on the row; the sweepers re-read the live windows each run.
- Usage events naming the Task roll into its totals under row locks, parent before child. A crossing of the
  ceiling is decided there; the kill (and the cascade to contained work) runs on commit in its own transaction and
  announces itself as `task.killed` or `subtask.killed`.
- The client closes with `delivered`, `failed` or `cancelled`; only the call that wins the transition writes the
  charge for delivered fixed-price work. A conflicting close is 409.
- Silent work expires: every 15 minutes abandoned work older than an hour is expired without announcement; every 5
  minutes, for `enforcing` tenants, stale work is expired and announced.

## Pricing, costing and economic recording

A posting records two independent facts: the supplier cost (`known`, `unresolved` with a reason, or
`not_applicable`) and the customer price (`known`, `waived`, `unknown` with a reason, or `not_applicable`). An
amount is never a zero standing in for "unknown"; the allowed combinations are database check constraints. Late
resolution (a published declaration, a resolution run) goes through two single-purpose "doors" that may only move a
fact from unresolved to known once, and a trigger refuses any other change. Measurements are kept beside the posting
and released by a daily prune after the retention horizon (400 days by default); the economic row outlives them.

## Limits, stops and enforcement

- The ceiling and admission control run for every tenant.
- The customer-wide families (pool, wallet policy) run only when `enforcement_mode = enforcing` (default `off`).
- `external` tenants have no wallet, so no wallet floor can fire for them (fixed in this commit: F3). The one
  residual place that still asks the old question is noted as a discrepancy in `02`.
- A stop is cooperative: usage after a stop is still recorded and priced; the ack says `stop: true` with
  `stop_scope` of the task or the customer, and the client is expected to stop sending work for that scope.

## External billing mode

`external` means the tenant bills its customers elsewhere and UBB only meters. No wallet is created, no drawdown,
no top-up, no postpaid push, no platform-fee period accrues for a metering-only tenant, and the payment-rail
guard does not apply. Stripe's live webhook receivers refuse every request when no signing secret is configured
(fixed in this commit: F5), so a deployment with no Stripe secret is safe.

## Background processing and persistence

- PostgreSQL 16: 20 Django apps with migrations, a fresh initial set of 44 migrations (26 project, 18 Django
  contrib) that applies cleanly and idempotently to an empty database; 21 PostgreSQL triggers carry the declared
  transition rules; about 110 model constraints.
- Redis 7: the Django cache (API-key last-used buffer, tenant products, admission counters), the Celery broker and
  result backend, and the enforcement live counters, all on one `REDIS_URL`.
- Celery 5.6: one app, nine named queues, a thirty-entry beat schedule; the web process now loads the same app so
  that on-commit doorbells reach the broker (fixed in this commit: F1 and F2).

## What is deliberately NOT part of the first external-client launch

- Any payment rail: no prepaid wallet, no postpaid push, no Stripe secret, no plans or subscriptions, no referrals.
- The console: not built into an image, not deployed, mock mode by default; the Code Builder therefore has no
  production surface of its own (its generated code is ordinary SDK or curl calls).
- An embeddable usage widget, a TypeScript SDK, a CLI, a PyPI release: none exist.
- The customer-wide SLO legs (`customer.stopped`, `customer.stop_cleared`) are carried to a future rail activation;
  the applicable stop webhooks for admission are `task.killed` and `subtask.killed`.
- Public-HTTPS webhook receipt timing cannot be demonstrated on a laptop; it is a production measurement.

## What changed conceptually since you last saw it

The repository you remember was a billing-flavoured metering API with ad-hoc rate cards, floating-point quantities,
money sometimes recorded as zero when unknown, a `meter_only` mode, and nearly three hundred migrations of history.
The current code is the outcome of a re-model (ADRs 0006 through 0026) whose load-bearing ideas are:

1. **Declared vocabulary.** What a tenant meters (Event Types, quantities, suppliers), how it groups (grouping
   fields) and how it sells work (task types) are declared and published, never inferred from traffic. A
   machine-readable domain registry (`domain-vocabulary/`) generates the vocabulary constants in the platform, the
   SDK, the console and the spec, and CI gates keep them in step.
2. **Exact and honest economics.** Quantities are exact text; money is integer micros; an unknown cost or price is
   recorded as unknown with a reason, never as zero; every amount has a receipt; a correction is a further publish.
3. **Facts the database defends.** Transition classes (frozen, set-once, resolve-once) are declared per column and
   enforced by PostgreSQL triggers, with a gate that proves each rule can fail.
4. **The unit of work at the kernel.** Tasks, their outcomes, ceilings and expiry are a platform concept that
   metering, billing and spend control realise but none owns.
5. **Four control families and two enforcement positions**, with `external` replacing `meter_only` and the wallet
   policy applying only where a wallet exists.
6. **One contract, generated consumers.** `openapi/v1.json` is the truth; the SDK core, the console client, the
   error-code exceptions and the known-value metadata are generated from it; the breaking gate measures against the
   `api-v1-cutover` tag; the SDK restarted its line at 4.0.0.
7. **A clean start.** The cutover (W6) replaced the migration history with a fresh initial set, reset the audit
   ledger and the suppression files, and cut the release tags. Nothing has ever been deployed; the only databases
   that hold the old history are developers' own, which must be dropped and re-created.
8. **The product boundary rule** is unchanged and still CI-enforced: four products on a kernel, communicating only
   through outbox events, `queries.py` read contracts, `ports.py` and platform hooks.
