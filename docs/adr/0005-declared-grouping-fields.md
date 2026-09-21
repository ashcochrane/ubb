# ADR-0005: Grouping fields are declared, bounded, and slot-bound

**Status:** accepted — superseded in part
**Date:** 2026-07-27
**Superseded in part by:** ADR-0006 on its central noun · ADR-0008 on invariant 7 · ADR-0007 on its
Migration note · slice 5 (#407) on what a `Task` carries
**Rewritten:** 2026-08-12, under the canonical noun (#283, slice 2 of #155)
**Design:** the 2026-07-27 unified-model design and its plan, under `docs/plans/` — frozen history,
and they still spell the noun this ADR has since renamed

## What the four supersessions mean

Stated here because three of them are easy to read as deletions, and none is.

- **The central noun** was renamed, not dropped. The registry, its two records and its columns are
  all spelled *grouping field* now, on every surface. The word it replaced is recorded in the
  retirement table (`domain-vocabulary/concepts/retired.yaml`), which exists so that living
  documents need not carry retired spellings in order to stay legible.
- **Invariant 7 is replaced, not deleted.** #145 removed the record it originally named, but the
  agreement it encodes runs against `Posting` today and is enforced today. It dissolves in slice 4,
  which rebuilds the rate entity, the rate book and the selector list together.
- **The Migration note became a rule with a check behind it**, which is the whole reason the note
  existed — a note is what a future engineer reads after copying the pattern.
- **A `Task`'s second `*_type` column was collapsed, not removed from the model.** The declaration
  survives whole; it is carried in ONE column at either altitude, with `Task.parent` saying which.
  Nothing left the vocabulary: both keys are still reserved, still columns on `Posting` and `Rate`,
  and still selectors a rule may pin on. This is the one supersession that changes an arity rather
  than a name, which is why the Decision now spells out what it does not touch.

## Context

UBB had three mechanisms for "what axis is this spend on" — named columns, one open JSONB bag, and a
per-rate JSONB bag — with two different matching semantics on a single query, an unbounded keyspace
that forced the rate cache to bypass itself on any event carrying one, and a write contract that
returned fields it could not accept.

## Decision

One per-tenant `GroupingField` registry is the sole vocabulary for analytics grouping and rate
selection. Four reserved keys (`provider`, `event_type`, `task_type`, `subtask_type`) plus ten
tenant slots (`grouping_field_1`..`grouping_field_10`) exist as columns on `Posting` and `Rate` —
the fourteen selectors. ~~`Task` carries the ten slots and the two `*_type` keys, and no more~~
**SUPERSEDED by slice 5 (#407): a `Task` carries the ten slots and ONE `*_type` key.** It is still
where a task- or subtask-scoped value is set once and inherited downward, not a thing a rate matches
against. In a `Rate`, `""` is a wildcard and the most-pinned match wins.

**What that supersession does and does not touch.** The FOURTEEN SELECTORS ARE UNCHANGED — both
`*_type` keys are still columns on `Posting` and on `Rate`, both are still reserved keys, and a rule
still pins on either. What changed is one level up: a unit of work used to declare its kind in two
columns set exclusively, one for a whole unit and one for a contained one, and they are the same
declaration at two altitudes (#154 §3.1). One column carries it now and `Task.parent` says which
altitude the row is at, so the posting's two axes are filled from that one column read at two
heights — the root's kind on `task_type`, the leaf's on `subtask_type`. A reader coming here from a
`Rate` sees no difference; a reader coming here from a `Task` finds one column where this clause
promised two.

**Ten slots, not six** (#276). The widening is not about migration cost: adding a nullable column to
a modern Postgres table is a catalog write. It is about demand having nowhere else to go — #273
closed the free-form grouping escape hatch, so grouping demand now arrives as a declaration or it
does not arrive. The expensive part of a slot was its index, and the ten carry none: no query
selects rows *by* a slot — every read of one is a `GROUP BY` inside a tenant and a time window, and
the single predicate on a slot in the tree is a negation on a column whose commonest value is `""`,
which no btree index would serve. The columns that select the rows are `tenant`/`customer` and
`effective_at`, and those are what the surviving indexes lead with. So the six per-slot indexes and
the composite that led with two of them went in the same change that added the four columns.

**Invariants** (enforced by `apps/platform/tests/test_grouping_field_invariants.py`, which drives
every refusal at every slot rather than at a representative one):

1. `GroupingField.slot` is immutable. Re-slotting would silently change the meaning of every
   historical row in that column.
2. `GroupingField.scope` is immutable. Changing it changes inheritance, so old and new rows would
   disagree about where a value came from.
3. `max_cardinality` may be raised, never lowered.
4. Retirement blocks new values; it never removes a record from the slot map, and never sweeps the
   values already admitted under it, so historical rows stay groupable *and* still resolve.
5. Correlation identifiers (`task_id`, `subtask_id`, `idempotency_key`, `customer_id`, `event_id`)
   can never be declared as grouping fields. They are filter parameters; grouping by one builds a
   bucket per occurrence. Narrowed by slice 5 (#411), not weakened: the list held a sixth member, a
   second caller-supplied correlation value, and that FIELD was deleted from the recording request.
   The name is no longer one of UBB's, so a tenant binding that word to a slot collides with
   nothing, and the invariant now covers exactly the identifiers UBB still owns. `FORBIDDEN_KEYS`
   in `apps/platform/grouping_fields/models.py` is the enforcing copy and says the same.
6. Reserved keys can never be bound to a tenant slot.
7. Every `Rate.SELECTORS` name exists as a `Posting` column — one vocabulary, both sides. Superseded
   in the sense above: re-pointed at `Posting` by #269 and dissolving in slice 4, not deleted.

**8. ~~The ranking rule is two-level: book tier dominates rate specificity.~~ SUPERSEDED by slice 4
(#356): there is ONE ranking, and rate specificity dominates book tier.**

What this clause recorded was true when it was written and is the sharp edge slice 4 removes.
`PricingService._resolve_card` used to walk book tiers in a fixed order — the customer's assigned
book, then the provider-specific default book, then the provider-agnostic (`""`) default book — and
return the first tier that yielded *any* match at all, so specificity only ever compared rates
fetched from the one book a tier had selected. A rate in the `""` book pinning `task_type` +
`grouping_field_1` (specificity 2) therefore lost to a rate in the `openai` book pinning only
`provider` (specificity 1), and a tenant's narrow override was silently shadowed.

**The walk is gone.** The books in play are selected first — the customer's assigned book plus the
tenant's default book(s) for the event's provider — and then every matching rule in all of them
competes in one ranking: how specifically a rule names the event first, and where it came from only
as the tie-break inside a level. The argument for that order is the 2026-07-31 markup-and-price
precedence decision §5.2, and it is a consequence argument rather than a taste one: under book-major
ranking a customer's small blanket discount shadows every specific price the tenant configured, and
their only defence is to restate every specific rule inside every override.

**The rule is now stated in exactly one place in the tree** — `ladder_rank`, in
`apps/metering/pricing/services/pricing_service.py` — with the four rungs it produces and the
argument for the order. This clause is kept rather than deleted because clause numbers here are cited
from outside this document; what it records now is that the edge existed and where its replacement
lives. Pinned by `test_grouping_field_invariants.py::test_rate_specificity_dominates_book_tier` and
by `apps/metering/pricing/tests/test_the_price_ladder_resolves_as_of_an_instant.py`.

**9. A slot outside the declared vocabulary is refused** (#276). Numbered here rather than folded
into the list above, because the numbers are cited from outside this document and renumbering them
would silently re-point every reference. A stored slot *is* a column name, so a declaration bound to
a slot that does not exist stores fine, accepts values fine, answers 200 fine — and attributes every
one of them to nothing. The tenant would find out when a chart was missing a column. Pinned at every
slot by `test_a_slot_outside_the_vocabulary_is_refused`, with
`test_every_declared_slot_is_accepted` as its control — without that control, a typo in the
vocabulary check would refuse everything and every other test in the class would still pass, since
they all assert refusals.

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
  one that can drive an invoice line label. Three ad-hoc label reads predated that rule, and slice 7
  retired all three: the key/value pair filtering a customer's postings on `/customers/{id}/usage`
  names the bag it reads (`metadata_key` / `metadata_value`, #504); the key-driven `by_tag`
  breakdown on `/analytics/usage` and the margin breakdown died with those routes (#501); and the
  free-text key driving postpaid invoice line labels became one axis of the declared vocabulary,
  published as `group_by` (#503 behind the wire, #531 on it). This bullet named them as the wire
  spelled them until the wire moved, and #531 corrected it in place with its line count kept.
- **A bounded keyspace let `CardCache` key on the full selector tuple**, removing the bypass that
  used to fire whenever a slot was pinned. What bounds the key is the per-slot cardinality cap and
  not the number of slots, which is why widening to ten changed nothing about that argument. It is
  worth stating what this consequence is worth today: **nothing in production reads that cache.**
  Its one reader was the accept-time estimate deleted in #239, the recording path resolves against
  live ORM through `PricingService`, and only `invalidate` is still wired. The module is kept for
  the contract a future reader inherits (`card_cache.py`), and disposing of it is a later ticket's.
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
- ~~Rate resolution has two independent ranking layers (book tier, then selector specificity) rather
  than one flat ranking over every candidate rate.~~ **Superseded with clause 8 by slice 4 (#356):**
  there is one ranking over every candidate rule in the books in play, specificity-major. A tenant
  authoring a narrow override no longer has to restate it in whichever provider book would otherwise
  match — that requirement was the consequence the supersession exists to remove, and the
  "ambiguous/shadowed override" lint it wanted is no longer the shape of the problem. What survives
  as a real tie is two rules a tenant made equally specific from one source, which the ladder breaks
  on the later effective moment and does not claim to resolve further.
- **Migration note — superseded.** This ADR used to warn that
  `apps/metering/usage/migrations/0028_remove_usageevent_idx_usage_attribution_and_more.py`
  implemented a column move as `AddField` + `RemoveField` rather than `RenameField`, and that
  replaying it against populated tables would drop the data it appeared to move. ADR-0007 §1 is now
  the rule — a migration that renames or moves a column carries its data — and it is backed by a
  check rather than by a note, which is what a note in this position was never going to achieve.
- **A row's grouped VALUE is `grouping_field_value` on every rollup, and the AXIS is named by the
  request.** Three rollups group postings and put the grouped value on each row: the
  `/analytics/usage` breakdowns, the `/analytics/usage/timeseries` buckets, and
  `/margin/by-grouping-field`. Only the third DECLARES its rows (`GroupingFieldMarginRow`); the
  other two return `list[dict]`, so no schema, no drift gate and no breaking gate can hold them to
  anything, and the two of them were written independently of each other and of the declared one.
  #312 settled which vocabulary they belong to and made all three agree. The reading is the declared
  schema's own: *the value the row groups, not the axis it was grouped on* — the axis is already
  named by the request's `group_by` (or by the key of the `breakdowns` map), so repeating it per row
  would say the same thing once per row. **This is also why the two open rollups were slice 2's and
  not slice 7's**, which owned the analytics grouping *capability* and its request parameter: the
  registry retires the singular noun to `grouping_field_value` and the plural to
  `analytics_grouping_kind`, so a value was this slice's and an axis was that one's, and the row key
  holds a value. Nothing but a test asserting the whole row can hold that agreement, which is what
  `api/v1/tests/test_analytics_dimensions.py` DID for both open rollups until #501 deleted the
  rollups and the module with them (see the supersession note at the end of this section), and why
  the console's two narrowing constants and the SDK's samples had to move in the same commit rather
  than a later one.
  Both backend writers take the key from one constant (`apps/metering/queries.py`), so they cannot
  drift apart from each other; the two whole-row pins remain because a shared constant proves they
  AGREE and not that what they agree on is what the console narrows and the SDK documents.
  **One console file was renamed under another slice's name, deliberately.** The breakdown
  component's own FILENAME carried the retired noun, and the console importer ratchet pins that
  exact path — which made renaming it slice 7's by the letter, and left two console files unpayable
  while their entry was slice 2's. Leaving them would have failed the slice's landing condition for
  the reason #312 exists, so slice 2 renamed the file and edited the one pinned path, taking slice
  7's one-file entry to zero with it. That is the ledger's own rule rather than an exception to it:
  an owner slice may move earlier but never later, and #283 settled that an entry cannot outlive its
  debt whoever owns it. Slice 7 therefore never paid that file, and this sentence is why its ledger
  entry is not there to explain itself.

- **Superseded by slice 7 (#501): the three rollups are one, and it DECLARES its rows.** The two
  bullets above describe a surface that no longer exists. `/analytics/usage`, its `/timeseries`
  sibling and `/margin/by-grouping-field` are deleted, along with six other published reports, and
  what answers all nine is `GET /metering/analytics/economics` — whose rows are
  `EconomicRowOut`, a declared schema, so the drift gate and the breaking gate now hold the thing
  that two of the three were beyond the reach of. The agreement those bullets fought for is
  therefore no longer an agreement between independent writers; it is one writer, and the row key
  is still `grouping_field_value` for the reason they give.
  - **What changed about the key, and it is worth stating precisely:** it is now a LIST, positional
    against the request's own `group_by`, which the response echoes. The reading is unchanged — the
    value the row groups, not the axis it was grouped on — and the axis is still named by the
    request. What the one query added is that a reader can ask for several axes at once, which the
    three separate rollups could not do at all.
  - `api/v1/tests/test_analytics_dimensions.py` is deleted with the rollups it pinned. The whole-row
    pin it provided is not lost: `api/v1/tests/test_the_one_economic_query.py` asserts the declared
    row, and the schema itself is now the pin the open rollups never had.
  - **The second of the three ad-hoc label reads is gone too.** The key-driven `by_tag` breakdown
    died with the report. ⚠ **This bullet used to say the remaining two survived "exactly as the
    bullet describes them", and #504 and #531 between them made that false**: the filter pair on
    `/customers/{id}/usage` is now `metadata_key` / `metadata_value`, naming the bag it reads, and
    the invoice-line grouping parameter took the declared vocabulary behind the wire in #503 and the
    vocabulary's own name, `group_by`, on it in #531. Neither was ever an analytics grouping axis,
    which is why no route removal could clear either and both had to be renamed on a live surface.
    None of the three survives.

- **#503 (slice 7 §11) — the third ad-hoc label read is gone, and it is the one that mattered most.**
  The invoice-line grouping parameter now takes one axis of the declared vocabulary
  (`field:<declared field>` or `rollup:<axis>`), validated at the moment a tenant configures it
  against the same per-tenant discovery contract analytics reads. The bullet above calls an
  unbounded free-text keyspace driving an invoice line label the sharpest case of the rule this ADR
  exists to state — *"an unbounded free-text keyspace that can become a chart is one that can drive
  an invoice line label"* — and it was also **the only one of the three a paying customer reads**.
  Two things went with it: the open bag can no longer reach an invoice line at all, and the silent
  fall-through that grouped an unrecognised configuration by the first slot is a refusal.
  - **What the parameter is called on the wire did NOT change here.** The column beneath it did;
    the published request and response field kept their names for the phase that regenerates the
    contract and the SDK from the backend, which is the ordering §21 of that slice fixes, so this
    document went on disagreeing with no running server. ⚠ That phase closed without moving the
    field, and #531 renamed it on every surface at once — see the amendment below.
  - **The per-axis cardinality cap this ADR declares (D4) became a real control on one surface.** It
    was stored and read by nothing; the invoice surface now warns a tenant at CONFIGURATION time
    when the axis they chose has already recorded more distinct values than the maximum they
    declared for it. It warns rather than refuses, because D4 calls the cap *a keyspace guard, not
    an invariant* — and warning at invoice time would mean the first anyone hears of it is an
    invoice that has already reached a customer.
  - This note is appended rather than written into the bullets above because a published field
    description cites this file by LINE NUMBER (`EconomicRowOut`, `api/v1/schemas.py`), and editing
    above that line would silently move what it points at. That is a fair criticism of the citation
    rather than of the bullets, and re-pointing it is still left for the ticket that next has reason
    to regenerate that description. (#531 did correct the Consequences bullet in place, but kept its
    line count, so nothing the citation points at moved.)

- **Amended by slice 7 (#504): the first of the three ad-hoc label reads is renamed, and the
  Consequences bullet naming all three was then out of date by one.** That bullet said the three
  were *"spelled here as the wire spells them today"* and that *"slice 7 owns renaming them"*.
  Slice 7 had then renamed the first: the pair filtering a customer's postings on
  `/customers/{id}/usage` names the bag it reads (`metadata_key` / `metadata_value`) rather than
  reading as an axis over a bag this ADR keeps deliberately ungroupable. The route KEEPS its own
  contract — it is a filter surface and returns paginated event rows, which no parameter
  combination of the one economic query returns — so what moved is four lines of request
  vocabulary and the generated followers of it, and the path count did not change.
  - **The second and third are accounted for.** The second — the key-driven breakdown on the usage
    report and on the margin breakdown — **died with its routes** in #501 rather than being renamed,
    which is the one disposition that bullet did not anticipate. The third, the invoice-line one,
    took the declared grouping vocabulary BEHIND the wire in #503; its published field still spelled
    the retired word at this amendment, and was left to phase B2 by slice 7 §21's ruling that only
    one of the four surfaces can move independently.
  - **The bullet above was left standing here rather than rewritten**, for the reason the note above
    it gives: it sits above the line a published field description cites, and a re-wrap would move
    what that citation points at.

- **Amended by slice 7 (#531): the third ad-hoc label read is renamed ON the wire, and none of the
  three survives.** The postpaid configuration publishes its invoice-line axis as `group_by` on both
  `PostpaidConfigIn` and `PostpaidConfigOut` — the registry's own stated successor for every
  per-surface grouping parameter, and the word the one economic query already publishes. Phase B2
  had closed without moving it, which left one setting speaking two vocabularies: a key named after
  the invoice line it produced, carrying a value from the grouping vocabulary. The contract, the
  console and the SDK moved in one commit, because a renamed published field cannot move one
  surface at a time.
  - **It is ONE axis where the economic query's `group_by` is a list, and both are right.** An
    analytics question may be grouped by several axes; an invoice line is grouped by exactly one. A
    list here would publish a capability the invoicing path does not have and the server would have
    to refuse, so the published schema declares a string and a list is refused at the route. The
    stored column stays `invoice_line_grouping`; the route module maps between the two names, one
    function per direction.
  - **The Consequences bullet is corrected in place, with its line count kept**, so nothing above
    the line `EconomicRowOut`'s description cites has moved. The notes under #503 and #504 record
    why it was not corrected sooner: while the wire still spelled the old words, correcting this
    document first would have made it disagree with a running server.

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
- ~~The SDK's hand-written create-a-rule method still posts the pre-reshape rate shape.~~
  **Resolved (#368, and fully discharged in #373).** That method is gone: the container split into
  a Pricing Book and a cost book, which are declared separately, so the SDK declares each of them
  and the body that posted a flat rate has no route to post to. The remainder — three further
  methods calling routes that exist in no spec and no router — went in #373, together with the
  ledger's G17 entries that owned them, which is the only way they could go: each method named a
  constant generated from its own entry. **The G17 family is empty and this debt owes nothing.**
