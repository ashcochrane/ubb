# ADR-0005: Grouping fields are declared, bounded, and slot-bound

**Status:** accepted — superseded in part (see below)
**Date:** 2026-07-27
**Rewritten:** 2026-08-12, under the canonical noun (#283, slice 2 of #155)
**Design:** the 2026-07-27 unified-model design and its plan, under `docs/plans/` — frozen history,
and they still spell the noun this ADR has since renamed

## What is superseded, and by what

This is a living document, so it is rewritten rather than left to contradict the tree. It is
superseded on three points and stands on the rest:

- **Its central noun.** ADR-0006 renamed it. The registry, its two records and its columns are all
  spelled *grouping field* now, on every surface. The word it replaced is recorded in the retirement
  table (`domain-vocabulary/concepts/retired.yaml`), which exists so that living documents do not
  have to carry retired spellings in order to stay legible.
- **Its selector invariant** (invariant 7 below). ADR-0008 replaces it rather than deleting it: #145
  removed the record it originally named, and the agreement it encodes now runs against `Posting`.
  It is live today and dissolves in slice 4, which rebuilds the rate entity, the rate book and the
  selector list together.
- **Its migration note.** ADR-0007 §1 turns that warning into a rule with a check behind it, which
  is the whole reason the note existed.

## Context

UBB had three mechanisms for "what axis is this spend on" — named columns, one open JSONB bag, and a
per-rate JSONB bag — with two different matching semantics on a single query, an unbounded keyspace
that forced the rate cache to bypass itself on any event carrying one, and a write contract that
returned fields it could not accept.

## Decision

One per-tenant `GroupingField` registry is the sole vocabulary for analytics grouping and rate
selection. Four reserved keys (`provider`, `event_type`, `task_type`, `subtask_type`) plus ten
tenant slots (`grouping_field_1`..`grouping_field_10`) exist as columns on `Posting`, `Task` and
`Rate`. In a `Rate`, `""` is a wildcard and the most-pinned match wins.

**Ten slots, not six** (#276). The widening is not about migration cost: adding a nullable column to
a modern Postgres table is a catalog write. It is about demand having nowhere else to go — #273
closed the free-form grouping escape hatch, so grouping demand now arrives as a declaration or it
does not arrive. The expensive part of a slot was its index, and the ten carry none: no query
selects rows by one slot, every read of a slot groups by it inside a tenant and a time window, so
the six per-slot indexes went in the same change that added the four columns.

**Invariants** (enforced by `apps/platform/tests/test_grouping_field_invariants.py`, which drives
every refusal at every slot rather than at a representative one):

1. `GroupingField.slot` is immutable. Re-slotting would silently change the meaning of every
   historical row in that column.
2. `GroupingField.scope` is immutable. Changing it changes inheritance, so old and new rows would
   disagree about where a value came from.
3. `max_cardinality` may be raised, never lowered.
4. Retirement blocks new values; it never removes a record from the slot map, and never sweeps the
   values already admitted under it, so historical rows stay groupable *and* still resolve.
5. Correlation identifiers (`task_id`, `subtask_id`, `request_id`, `idempotency_key`,
   `customer_id`, `event_id`) can never be declared as grouping fields. They are filter parameters;
   grouping by one builds a bucket per occurrence.
6. Reserved keys can never be bound to a tenant slot.
7. Every `Rate.SELECTORS` name exists as a `Posting` column — one vocabulary, both sides. Superseded
   in the sense above: re-pointed at `Posting` by #269 and dissolving in slice 4, not deleted.
8. A slot outside the declared vocabulary is refused (#276). A stored slot *is* a column name, so a
   declaration bound to a slot that does not exist stores fine, accepts values fine, answers 200
   fine — and attributes every one of them to nothing. The tenant would find out when a chart was
   missing a column.

**9. The ranking rule is two-level: book tier dominates rate specificity.**

"Among matching rates, the most-pinned wins" (design D3) is true **only within a single book**.
`PricingService._resolve_card` walks book tiers in a fixed order — the customer's assigned book,
then the provider-specific default book, then the provider-agnostic (`""`) default book — and
returns the first tier that yields *any* match at all (`pricing_service.py::_resolve_card`).
Specificity ranking (`_resolve_rate_within`) only ever compares rates that were already fetched from
the *one* book a tier selected; it never compares across books.

The practical consequence: a rate in the `""` book pinning `task_type` + `grouping_field_1`
(specificity 2) loses to a rate in the `openai` book pinning only `provider` (specificity 1),
whenever both would otherwise match the same event, because the `openai` book is tried first and its
match short-circuits the walk before the `""` book's more specific override is ever queried. A
tenant's narrow override in the `""` book is therefore silently shadowed by any provider-book rate
on the same measurement key — not a bug, but a sharp edge worth knowing before writing overrides.
Pinned by `test_grouping_field_invariants.py::test_book_tier_dominates_rate_specificity`.

**D8's `key` is renameable in principle, but there is no rename path.** The design doc (D8) declares
`key` a mutable display label — "the slot is identity" — but `DimensionService.declare` never
implements a rename: it looks an existing record up **by key**, so a genuinely new key always takes
the create branch, not an update-in-place. There is no `PATCH`/`PUT` verb, no service method, no
anything that says "keep this slot's history, just call it something else now." Attempting to
*simulate* a rename by declaring a fresh key bound to a slot an old key still holds hits the
same-slot collision Important-4 (final-fixes wave, 2026-07-27) fixed: previously an uncaught
`IntegrityError` on `uq_dimension_def_slot` (500), now a `DimensionError` (422) — loud and correct,
but still a rejection, not a rename. A real rename path is unbuilt work, not a design gap covered by
an existing invariant. (The service class, the error class and the two constraint names still carry
the old noun; the constraints deliberately, because renaming one is a drop-and-create of a
load-bearing unique index, which ADR-0007 §1 refuses.)

## Consequences

- **The open bag is never a pricing selector, and never groupable.** The registry is the only thing
  a `Rate` can select on. #273 folded the second bag into the surviving one, which is filterable and
  readable but never a grouping axis — an unbounded free-text keyspace that can become a chart is
  one that can drive an invoice line label. Three ad-hoc label reads predate that rule and survive
  it: `?tag_key=`/`?tag_value=` filtering on `/analytics/usage`, `tag_key` on the margin breakdown,
  and `usage_line_item_group_by="tag:<key>"` driving postpaid invoice line labels
  (`apps/metering/queries.py:get_customer_billed_breakdown`). Those three names are spelled here as
  the wire spells
  them today; slice 7 owns renaming them, and renaming them here first would make this document
  disagree with a running server.
- **A bounded keyspace lets `CardCache` key on the full selector tuple**, so events carrying a
  grouping value are cacheable for the first time. The bypass that used to fire whenever a slot was
  pinned is gone. What bounds the key is the per-slot cardinality cap, not the number of slots —
  which is why widening to ten changed nothing about this argument.
- **Ten columns, six published.** The rate write surface publishes six slot properties, mapped onto
  the first six columns by `api/v1/schemas.py:SLOT_PROPERTY_COLUMNS`. A rate pinned on slots seven
  through ten can therefore be written server-side and never repriced through the API — a reprice
  body leaves those four at `""`, which matches a rate that leaves them unpinned. That gap arrived
  with #276 and leaves with slice 4, which rebuilds all three of these schemas; it is held to that
  extent by `api/v1/tests/test_grouping_values_on_the_contract.py`, which fails if the published set
  ever overstates what the contract actually carries.
- **An eleventh tenant axis requires a migration.** Deliberate, and cheap in itself; what a slot
  costs is the discipline of declaring it, not the column.
- `Task.task_type` is immutable for the same reason `Task.parent` is — `accumulate_cost` reads it
  without a lock.
- Rate resolution has two independent ranking layers (book tier, then selector specificity) rather
  than one flat ranking over every candidate rate. A tenant authoring narrow overrides in the `""`
  book must also author them in whichever provider book would otherwise match, or the override never
  fires. The publish-time tooling does not warn on this today — a candidate for a future
  "ambiguous/shadowed override" lint alongside the specificity-tie warning the design doc flags.
- **Migration note — superseded.** This ADR used to warn that
  `apps/metering/usage/migrations/0028_remove_usageevent_idx_usage_attribution_and_more.py`
  implemented a column move as `AddField` + `RemoveField` rather than `RenameField`, and that
  replaying it against populated tables would drop the data it appeared to move. ADR-0007 §1 is now
  the rule — a migration that renames or moves a column carries its data — and it is backed by a
  check rather than by a note, which is what a note in this position was never going to achieve.

## Deferred findings tracked against this ADR

Minor findings surfaced during review and out of scope for the task that raised them, recorded here
so they don't vanish silently. Each was re-checked against the tree when this ADR was rewritten.

- `DimensionService.admit`'s and `.declare`'s `scope` argument is not validated against
  `SCOPE_CHOICES` — an unrecognized scope string is stored rather than rejected at the door, and
  Django's `choices` is not a database constraint.
- `TaskType.key` is a `SlugField` on the model but `TaskTypeIn.key` is a plain `str` in the API
  schema, so slug format is enforced nowhere on the write path.
- `TaskTypeIn.required_dimensions` caps its list at six entries while ten slots can be declared, so
  a tenant that declares seven or more cannot require them all. The cap predates #276's widening and
  was not moved with it; it is stated here rather than changed, because the field's name is slice
  7's to retire and the two edits belong together.
- The SDK's hand-written `MeteringClient.create_rate_card` still posts the pre-reshape rate shape.
  The call 422s loudly rather than landing a wrong rate, because `BookIn.key` is a required field
  the method never sends — so the ship gate is that an SDK caller cannot create a book-scoped rate
  at all today, not that a quietly wrong one lands. Rebuilding the SDK's pricing surface for the
  book/rate/publish/assign shape is real debt, and slice 4 owns it.
