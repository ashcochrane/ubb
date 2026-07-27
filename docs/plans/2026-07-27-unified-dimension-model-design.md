# Unified Dimension Model — Design

**Date:** 2026-07-27
**Status:** proposed
**Supersedes in part:** `docs/plans/2026-06-09-wave2-cost-attribution-design.md` (the
`product_id`/`service_id`/`agent_id` triple and its reserved-tag lifting)

## Problem

UBB has grown **three separate mechanisms** for "what axis is this spend on", and they
disagree with each other:

1. **Named attribution columns** on `UsageEvent` — `provider`, `event_type`, `product_id`,
   `service_id`, `agent_id`. Indexed, groupable, exact-match.
2. **`tags` JSONB** — free-form, unindexed, undeclared, uncapped. Doubles as a *pricing
   selector* (`PricingService._dimensions_match`) despite its docstring claiming it is
   "free-form analytics labels".
3. **`Rate.dimensions` JSONB** — the rate's selector, matched against the event's `tags`
   by subset, with most-specific-wins ranking.

The consequences, each observed in the current code:

- **Two matching semantics on one query.** `_resolve_rate_within` matches `provider` and
  `event_type` by **exact equality including `""`** (`pricing_service.py:43`), so a rate with
  `provider=""` matches only events with no provider — it is *not* a fallback. Meanwhile
  `dimensions` matches by **subset**, where an absent key is a wildcard. A tenant cannot
  express "this rate applies to any provider" without writing one rate per provider.
- **The hot path defeats its own cache.** `CardCache.resolve` bypasses L1 entirely whenever
  `tags` is non-empty (`card_cache.py:67-73`), because an unbounded tag keyspace would
  poison a tag-less cache key. Dimension-bearing pricing therefore hits Postgres on every
  event — precisely the events a metering system has most of.
- **Undiscoverable write contract.** `service_id` and `agent_id` are returned as first-class
  fields (`schemas.py:164-165`, `224-225`) but cannot be *sent* — they are lifted from magic
  tag keys at `usage_service.py:258-259`. Nothing in `openapi/v1.json` says so.
- **No unit economics.** `Task` has no notion of what *kind* of job it is
  (`tasks/models.py:14-90`). Per-run costs are materialized on the row
  (`total_billed_cost_micros`, `total_provider_cost_micros`, `event_count`) and there is no
  read endpoint at all — the only task route in the API is `POST /tasks/{id}/close`. So
  "what does an invoice batch cost on average" is unanswerable, which is the number that
  sets a price.
- **Agent-shaped naming in a permanent contract.** `agent_id` is in the committed v1 spec
  (ADR-002). It is semantically inert — nothing in pricing, gating, or margin reads it — but
  it forces every non-agentic tenant to translate their vocabulary into ours.

## The core distinction

Two families of key, which must not share a mechanism:

| | **Dimension** | **Correlation id** |
|---|---|---|
| Cardinality | bounded, declared, capped | unbounded by construction |
| Example | `task_type=invoice_batch`, `region=eu-west-1` | `task_id`, `request_id`, `idempotency_key` |
| Query role | `GROUP BY` | `WHERE` |
| Cost curve | scales with distinct values | scales with selectivity (cheap) |
| Cacheable as a key | yes — that's what the cap buys | no |
| Pricing input | yes | never |

A *kind* of work is a dimension. An *instance* of work is a correlation id. `ocr` is a
dimension value; subtask `c11e…` is an instance. Both must exist; neither substitutes for
the other.

## Decisions

### D1 — One declared vocabulary per tenant

A `DimensionDef` registry is the **single** place a tenant declares a slicing axis. It
governs analytics grouping *and* rate selection — the same word list, so a tenant never
learns two vocabularies. Nothing may be grouped by, or priced on, that is not declared.

`provider`, `event_type`, `task_type`, and `subtask_type` are **reserved** dimension keys:
always present, never declared, never deleted.

### D2 — Physical storage is indexed slots, not JSONB

Dimensions live in named `CharField` columns on both `UsageEvent` and `Rate`, never in
JSONB. Both are on hot paths — rate resolution per metric per event, and analytics
`GROUP BY` over months — and a B-tree on a `CharField` beats JSONB extraction on both.
Empty `CharField`s cost ~1 byte per row in Postgres, so unused slots are close to free.

Ten selector columns on each of `UsageEvent` and `Rate`:

```
provider  event_type  task_type  subtask_type  dim1 dim2 dim3 dim4 dim5 dim6
```

`dim1..dim6` are the tenant's own axes, bound to declared keys by the registry.
`product_id`/`service_id`/`agent_id` are renamed to `dim1`/`dim2`/`dim3` — greenfield, so
this is a rename, not a data migration. The composite `idx_usage_attribution` is rebuilt on
the new names.

**Rejected:** a generic JSONB `dimensions` column with expression indexes per declared key.
It moves index management into runtime DDL, and every `GROUP BY` becomes a
`KeyTextTransform` — the exact cost we are removing from `dimensions=tag:region` today.

### D3 — `""` is a wildcard, everywhere, and specificity ranks matches

This is the unification that matters, and it is semantic rather than physical. One
algorithm for all ten selector columns:

- A rate's selector column set to `""` matches **any** event value for that column.
- A rate's selector column set to a value matches **only** that value.
- Among matching rates, the winner is the one with the **most non-empty selector columns**,
  tie-broken by latest `valid_from`.

`Rate.dimensions` and `Rate.dimensions_hash` are **deleted**. The uniqueness constraint
`uq_rate_active_in_book` moves from `(rate_card, provider, event_type, metric_name,
dimensions_hash, currency)` to the ten selector columns plus `metric_name` and `currency`.

`metric_name` keeps exact-match semantics with no wildcard: pricing is per-metric and a
rate that matches any metric is meaningless. This stays the one mandatory pivot — which is
why strict-coverage mode hard-fails on `units > 0` with no `usage_metrics`
(`pricing_service.py:111`).

### D4 — Cardinality is enforced on write, and that is what makes the cache sound

Each `DimensionDef` carries `max_cardinality`. A `DimensionValue` ledger records every
distinct `(tenant, key, value)` seen. A novel value beyond the cap is rejected at ingest
with `422 dimension_cardinality_exceeded`.

This is not defensive hygiene — it is the **enabling constraint for D5**. A bounded
keyspace is what makes a dimension-bearing cache key safe, which is what lets us delete
the `if tags:` cache bypass. It also yields `GET /dimensions/{key}/values` for free, which
is what a tenant's dashboard needs to build a filter dropdown.

### D5 — The rate cache keys on dimensions

`CardCache.resolve`'s L1 key becomes:

```python
(tenant_id, customer_id, card_type, metric, currency, dims_tuple)
```

where `dims_tuple` is the event's ten selector values in fixed order. Bounded by D4, so
the `if tags:` bypass at `card_cache.py:67` is deleted. Dimension-bearing events become
cacheable for the first time.

### D6 — Dimensions have a scope, and inherit downward

`DimensionDef.scope ∈ {task, subtask, event}` — the level at which the value is constant:

- `task` — set once at task start, inherited by **every** event in the tree, including
  events on subtasks.
- `subtask` — set at subtask start, inherited by that subtask's events.
- `event` — sent per event; varies call to call.

Inheritance resolves in `RecordingInput.gather` (`usage_service.py:230-265`) — the single
normalization seam both the sync and settle lanes already share (callers at lines 473 and
578). One implementation, two lanes, by construction.

This is also the honest answer to "will every event carry every dimension": the *caller*
need not send a dimension for the *row* to have it. It rides on the batched task read that
the accept path already performs through a 30s L1 cache
(`ingest_accept.py:150-175`, currently selecting `id, customer_id`) — inheritance adds
columns to an existing `.values()`, not a new query.

### D7 — `task_type` is a registry with behaviour, not a label

`TaskType` declares the tenant's work vocabulary and carries **policy**:

```
key · kind (task|subtask) · allowed_parent_types · default_provider_cost_limit_micros
· required_dimensions
```

Today a task's COGS ceiling comes from the per-call `provider_cost_limit_micros` or one
tenant-wide default (`RiskConfig.default_task_provider_cost_limit_micros`,
`gating/models.py:14`). Every kind of job therefore shares one ceiling — so a
`year_end_close` that legitimately costs 50× an `invoice_batch` forces you to either cap
both at the large number (no protection on the small one) or let the client declare its own
spending limit on every start call.

With `TaskType`, the ceiling is **server-side policy per kind of job**. A start call may
request lower, never higher.

`Task.task_type` is **immutable after creation**, for the same reason `Task.parent` is
(`tasks/models.py:36-38`): `accumulate_cost` reads it without a lock, and a re-typed task
would retroactively change what every already-settled event means.

### D8 — Registry mutability rules (the hard-to-reverse part)

- `DimensionDef.slot` — **immutable.** Re-slotting would silently change the meaning of
  every historical row in that column.
- `DimensionDef.scope` — **immutable.** Changing it changes inheritance, so old and new
  rows would disagree about where a value came from.
- `DimensionDef.key` — renameable. It is a display/API label; the slot is the identity.
- `max_cardinality` — raise only, never lower.
- Deletion — **retire, never delete.** A retired def stops accepting new values; existing
  rows keep their meaning and stay groupable.

D8 is the genuinely hard-to-reverse decision here and earns an ADR
(`docs/adr/0005-declared-dimensions.md`), enforced by a test in the manner ADR-001
establishes.

### D9 — Correlation ids are filter-only, structurally

`task_id` is accepted as a **query filter** on the usage list and analytics endpoints, and
never as a value in `dimensions=`. The API rejects `dimensions=task_id` with
`422 unknown_dimension` rather than building one bucket per run. The distinction is
enforced by the registry, not by documentation.

## Worked example

**Ridgeline**, document processing for accounting firms, `postpaid`, reselling AWS Textract
and OpenAI. Customer: Northwind Foods.

**Setup, once.** Declare two free axes (`region` scope=task → dim1, `model` scope=event →
dim2) and the work vocabulary (`invoice_batch` at a 5M micro COGS ceiling, with `ocr`,
`classify`, `validate` subtask types at their own ceilings).

**Runtime, per job.** Start the run (`task_type=invoice_batch`,
`dimensions={"region":"eu-west-1"}`) → task `8f3a`, ceiling 5M from the type. Start a step
(`parent_task_id=8f3a`, `subtask_type=ocr`) → subtask `c11e`, ceiling 2M. Meter pages
against `c11e`, sending only `provider`, `event_type`, `usage_metrics`, and
`dimensions={"model":"textract-v2"}`.

The settled row carries all ten columns: `provider=aws_textract`, `event_type=ocr_page`,
`task_type=invoice_batch` (inherited from `8f3a`), `subtask_type=ocr` (inherited from
`c11e`), `dim1=eu-west-1` (inherited from `8f3a`), `dim2=textract-v2` (sent).

**Reading.** `GET /tasks/8f3a` is the instance receipt off the existing rollups.
`?dimensions=subtask_type` says which step kind burns COGS.
`/margin/by-dimension?group_by=task_type` says which job kind is unprofitable.
`/analytics/tasks?group_by=task_type` gives run count, mean and p95 cost per run, and
limit-hit count — the unit economics that do not exist today.

## What this deletes

Simplification is most of the value:

- `Rate.dimensions`, `Rate.dimensions_hash`, and the `save()` hook that computes the hash
  (`pricing/models.py:69-70`, `99-101`)
- `PricingService._dimensions_match` (`pricing_service.py:31-36`)
- The `if tags:` cache bypass (`card_cache.py:67-73`)
- Reserved-tag lifting from `tags` (`usage_service.py:257-259`)
- `RESERVED_DIM_KEYS`, already dead (`usage/models.py:7`)
- The `provider: int` / `product: int` pseudo-flags on `/margin/by-dimension`
  (`margin_endpoints.py:87`), replaced by a real `group_by`

After this, `tags` means exactly one thing — free-form labels that are never grouped and
never priced — and its docstring becomes true.

## Constraints and known limits

- **Six tenant slots.** A seventh axis requires adding `dim7`. Adding columns later is the
  expensive move, so six is deliberately generous at the outset.
- **Ten-column uniqueness constraint** on `Rate` is wide. Acceptable: rates are
  low-cardinality config, not event data.
- **Specificity ties.** Two rates with the same non-empty count matching one event resolve
  by `valid_from` descending. Deterministic but arbitrary — the publish path should warn on
  ambiguous overlap rather than silently pick.
- **Cardinality races.** Two concurrent novel values at the cap boundary can both admit,
  overshooting by the number of concurrent writers. Accepted: the cap is a keyspace guard,
  not an invariant, so overshoot by a handful is harmless.

## Product boundary compliance

`DimensionDef`, `DimensionValue`, and `TaskType` are **platform** models
(`apps/platform/dimensions/`, `apps/platform/tasks/`): metering reads them for pricing and
analytics, billing reads `TaskType` for start-gate ceilings. Cross-product reads go through
`apps.platform.dimensions.queries`, never direct ORM. Per ADR-001 this keeps
`apps/billing` → `apps/metering` imports at zero; `test_product_boundaries.py` is the gate.
