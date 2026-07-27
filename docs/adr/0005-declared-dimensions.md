# ADR-0005: Dimensions are declared, bounded, and slot-bound

**Status:** accepted
**Date:** 2026-07-27
**Design:** `docs/plans/2026-07-27-unified-dimension-model-design.md`

## Context

UBB had three mechanisms for "what axis is this spend on" — named columns, `tags` JSONB, and
`Rate.dimensions` JSONB — with two different matching semantics on a single query, an
unbounded keyspace that forced the rate cache to bypass itself on any dimension-bearing
event, and a write contract that returned fields it could not accept.

## Decision

One per-tenant `DimensionDef` registry is the sole vocabulary for analytics grouping and
rate selection. Four reserved keys (`provider`, `event_type`, `task_type`, `subtask_type`)
plus six tenant slots (`dim1`..`dim6`) exist as indexed columns on both `UsageEvent` and
`Rate`. In a `Rate`, `""` is a wildcard and the most-pinned match wins.

**Invariants (enforced by `apps/platform/tests/test_dimension_invariants.py`):**

1. `DimensionDef.slot` is immutable. Re-slotting would silently change the meaning of every
   historical row in that column.
2. `DimensionDef.scope` is immutable. Changing it changes inheritance, so old and new rows
   would disagree about where a value came from.
3. `max_cardinality` may be raised, never lowered.
4. Retirement blocks new values; it never removes a def from the slot map, so historical
   rows stay groupable.
5. Correlation identifiers (`task_id`, `subtask_id`, `request_id`, `idempotency_key`,
   `customer_id`, `event_id`) can never be declared as dimensions. They are filter
   parameters; grouping by one builds a bucket per occurrence.
6. Reserved keys can never be bound to a tenant slot.
7. Every `Rate.SELECTORS` name exists as a `UsageEvent` column — one vocabulary, both sides.

**8. The ranking rule is two-level: book tier dominates rate specificity.**

"Among matching rates, the most-pinned wins" (design D3) is true **only within a single
book**. `PricingService._resolve_card` walks book tiers in a fixed order — the customer's
assigned book, then the provider-specific default book, then the provider-agnostic (`""`)
default book — and returns the first tier that yields *any* match at all
(`pricing_service.py::_resolve_card`). Specificity ranking (`_resolve_rate_within`) only ever
compares rates that were already fetched from the *one* book a tier selected; it never
compares across books.

The practical consequence: a rate in the `""` book pinning `task_type` + `dim1` (specificity
2) loses to a rate in the `openai` book pinning only `provider` (specificity 1), whenever
both would otherwise match the same event, because the `openai` book is tried first and its
match short-circuits the walk before the `""` book's more specific override is ever queried.
A tenant's narrowly-dimensioned override in the `""` book is therefore silently shadowed by
any provider-book rate on the same metric — not a bug, but a sharp edge worth knowing before
writing overrides. Pinned by
`test_dimension_invariants.py::test_book_tier_dominates_rate_specificity`.

## Consequences

- `tags` becomes what its docstring always claimed: free-form labels, never grouped, never
  priced.
- A bounded keyspace lets `CardCache` key on dimensions, so dimension-bearing events are
  cacheable for the first time.
- A seventh tenant axis requires a migration. Deliberate: six is generous, and adding
  columns later is the expensive move.
- `Task.task_type` is immutable for the same reason `Task.parent` is — `accumulate_cost`
  reads it without a lock.
- Rate resolution has two independent ranking layers (book tier, then selector specificity)
  rather than one flat ranking over every candidate rate. A tenant authoring narrow
  overrides in the `""` book must also author them in whichever provider book would
  otherwise match, or the override never fires. The publish-time tooling does not warn on
  this today — a candidate for a future "ambiguous/shadowed override" lint alongside the
  specificity-tie warning the design doc already flags.
- **Migration note:** `apps/metering/usage/migrations/0028_remove_usageevent_idx_usage_attribution_and_more.py`
  (Task 8) implements the `product_id`/`service_id`/`agent_id` → `dim1`/`dim2`/`dim3` move as
  separate `AddField` + `RemoveField` operations, not `RenameField`. This was fine
  pre-launch (no seeded data to preserve), but it means replaying this migration against a
  database that already has rows loses whatever was in `product_id`/`service_id`/`agent_id` —
  it does not carry that data into the new `dim1`/`dim2`/`dim3` columns. Anyone tempted to
  reuse this migration's pattern against a live dataset should use `RenameField` (or a data
  migration) instead.

## Deferred findings tracked against this ADR

Minor findings surfaced during review and out of scope for this task's edits, recorded here
so they don't vanish silently (see task-17 report for full triage):

- `DimensionService.admit`'s `scope` argument is not validated against `SCOPE_CHOICES` — an
  unrecognized scope string is accepted rather than rejected at the door.
- `TaskType.key` is a `SlugField` on the model but `TaskTypeIn.key` is a plain `str` in the
  API schema, so slug format is enforced nowhere on the write path.
- The SDK's hand-written pricing methods still POST the pre-reshape `dimensions=`/
  `product_id` shape when creating a rate. Pydantic silently drops unknown fields, so an
  SDK-created rate lands with all-wildcard selectors instead of erroring — the failure mode
  changed from loud (415/422) to silent (a rate that matches everything). Fixing the SDK's
  pricing surface for the new selector shape is real debt, out of scope here.
