# Pricing API Changelog

No repo-wide `CHANGELOG.md` convention exists yet (checked `git log` for prior
changelog commits and searched `docs/` — neither turned up anything). This
file starts a per-surface changelog for the `/api/v1/metering/pricing/*`
routes; follow-on breaking changes to this surface should be appended here.

**On the names in dated entries.** The #155 re-model renames parts of this
surface slice by slice. Where a name has been RETIRED AND REPLACED, the entry
below carries the current one, so a reader is not sent to a spelling that
resolves to nothing; `domain-vocabulary/concepts/retired.yaml` — the retirement
table — records what each one replaced.

That is the whole of the claim, and it is narrower than it may read. An entry
may still name a field that a later change **deleted outright** rather than
renamed, and may still name one whose rename belongs to a slice that has not
run yet — in both cases the entry is recording what the surface was on its
date, which is what it is for. An entry's *facts* are never rewritten: what
changed, when, and why stay exactly as recorded.

## 2026-08-21 — Adding and retiring a rule become publishes (BREAKING)

Every change to a Pricing Book is a publish. The two routes that wrote a rule
**immediately** — one to add, one to retire — are deleted, and with them the
last unversioned act on a book (issue #367).

- **`POST /pricing/rate-cards/{book_id}/rates` — REMOVED.** A rule is opened by
  declaring the change and publishing it: `POST
  /pricing/rate-cards/{book_id}/publishes` with a change whose `kind` is `add`,
  then `POST /pricing/rate-cards/{book_id}/publishes/{publish_id}/publish`. The
  declaring body names a grouping slot by the key the tenant declared rather
  than by the column, and it can be dated forward; the deleted route could do
  neither. `RateIn` is removed from the contract with it.
- **`DELETE /pricing/rate-cards/{book_id}/rates/{rate_id}` — REMOVED.** A rule
  is retired the same way, with `kind` `retire`.
- **`GET /pricing/rate-cards/{book_id}/rates`** — a row no longer reports which
  KIND of book it belongs to. That was a copy of the book's own value, carried
  on the row and read by nothing; a client that wants it reads it off the book
  the rules were listed under, whose id is on every row.
- **What did NOT move.** The immediate reprice, `POST
  /pricing/rate-cards/{book_id}/publish`, is untouched. Reading a book's rules,
  their history and their state at an instant are untouched.
- **Model/migration** — the rule's table takes the name its own name asks for;
  migration `0027_the_rate_moves_to_the_table_named_for_a_rate.py` is a rename
  carrying its rows, both its database rules and every constraint on them.
- **SDK** — `MeteringClient.delete_rate` is removed. There was no wrapper for
  the other route.

## 2026-08-20 — The rate's arithmetic shape, and all ten grouping slots (BREAKING)

Two changes to the same three schemas, taken together because splitting them
would have broken the same properties twice (issue #366).

**The arithmetic shape takes its ratified name, values included.** The column
saying how a rule computes sat one character from `pricing_mode`, a declared
concept about which pricing regime governs a whole job — a pair ADR-0006 §3
calls a defect rather than a coincidence. It is `rate_structure` now, and its
values are `per_unit` / `fixed_component`. The values move with the name: a rule
that charged once regardless of quantity said `flat` and says `fixed_component`.

- **`POST /pricing/rate-cards/{book_id}/rates`**, **`POST
  /pricing/rate-cards/{book_id}/publish`**, **`GET
  /pricing/rate-cards/{book_id}/rates`** — the property is renamed on `RateIn`,
  `RateChangeIn` and `RateOut`. It is a `closed` registry concept, so the
  contract now publishes a real `enum` for it where it published a bare string.
- **`BookChangeIn` and `RuleTermsOut` gain it** — additive. A publish could not
  state a rule's arithmetic shape at all before this, so a rule set up as a
  per-unit charge could not be made a fixed component except through the
  immediate reprice route the publish act replaces.
- **Model/migration** — `Rate.rate_structure`, with `choices=` taken from
  `core.vocabulary` rather than hand-typed; migration
  `0026_the_rates_arithmetic_shape_takes_its_ratified_name.py` is a
  `RenameField` carrying its rows plus a reversible value conversion.

**All ten grouping slots are published, under the column names.** A rule can be
pinned on ten slots; the contract named six, as `dim1`..`dim6`. The other four
were unreachable rather than merely unnamed — a reprice body left them empty,
and empty is what matches a rule leaving a slot unpinned, so a rule pinned on
the seventh slot could be written server-side and matched by no publish body at
all.

- **`RateIn`, `RateChangeIn`, `RateOut`** — `dim1`..`dim6` become
  `grouping_field_1`..`grouping_field_10`. The join that mapped published names
  to columns is deleted rather than widened, so a body and the rule's own
  selector columns speak one vocabulary.
- The tenant-key-keyed form on a publish's change body (`grouping_fields`) is
  unchanged and is still the shape to prefer: it survives a key being rebound to
  another slot.

## 2026-07-15 — Tiered pricing removed (BREAKING, ADR-0003)

The `graduated` and `package` pricing models are **deleted end to end** — not
gated (`docs/adr/0003-mvp-launches-without-tiered-pricing.md`; decided in
issue #22, executed via issue #30). The MVP launches with `per_unit` and
`fixed_component` only; every arrival-time estimate now equals the settled price by
construction (the only remaining accept-vs-settle difference is rate-card
config drift).

- **`POST /pricing/rate-cards/{book_id}/rates`** — `rate_structure` accepts
  only `per_unit`/`fixed_component` (anything else → 422); the `tiers` field is removed
  from `RateIn`, `RateChangeIn` (publish), and `RateOut`.
- **`POST /pricing/rate-cards/{book_id}/publish`** — validates
  `rate_structure` against the narrowed choices (ValueError → 422, whole
  publish rolls back).
- **Model/migration** — `Rate.tiers` dropped; `PricingPeriodCounter` (the
  per-period tier ladder) deleted; migration
  `0014_delete_tiered_pricing.py` guards that no graduated/package rows
  exist before touching the schema (fails loudly otherwise).
- **Deleted machinery** — `TierCounterService` (ladder lock-and-advance),
  `TierMirror` (Redis accept-time ladder mirror), the estimation service's
  tiered never-under-hold branch, `tier_breakdown` provenance, and the
  monthly `verify_tier_rerate` tripwire task + its beat schedule.
- **SDK** — `create_rate_card(tiers=...)` parameter and `RateCard.tiers`
  dataclass field removed; README tiered-pricing section deleted.
- `month_bounds` moved from the deleted
  `apps/metering/pricing/services/tier_counter_service.py` to
  `core/time_windows.py` (still used by backfill period logic).

## 2026-07-03 — RateCard container reshape (BREAKING)

**Branch:** `feat/rate-card-container`. Design doc:
`ubb-platform/docs/plans/2026-07-03-rate-card-container-design.md`.
Implementation plan: `ubb-platform/docs/plans/2026-07-03-rate-card-container-plan.md`.

### Summary

`/pricing/rate-cards` used to manage flat, per-measurement rate cards directly.
It now manages **books** (`RateCard` containers) that group many per-measurement
**rates** (`Rate`, the renamed old `RateCard` model). This is a deliberate
breaking change with no compatibility shim (per design §2.4 / §9 "Breaking
API" risk note) — it enables atomic multi-measurement repricing and per-customer
book assignment, which a flat per-rate model could not express safely.

### What changed

> **Two names in this entry no longer resolve, and the header's rule applies to
> both.** The container this entry introduces carried **a kind field** telling a
> book of supplier costs from a book of customer prices; the split into a
> `PricingBook` and a `CostBook` replaced it with two entities rather than
> renaming it, so it is written as *the kind field* below. The rule's pointer at
> its container is `pricing_book` now. What this entry records — what changed on
> 2026-07-03, and why — is untouched.

- **`POST/GET /pricing/rate-cards`** now creates/lists **books**, not rates.
  - Request body is `BookIn` (the kind field, `provider_key`, `key`, `name`,
    `currency`, `is_default`) instead of the old flat rate payload.
  - Response shape is `BookOut` (`id`, the kind field, `provider_key`, `key`,
    `name`, `currency`, `version`, `is_default`) — **`RateCardOut` is gone**,
    replaced by `BookOut` for books and a repurposed `RateOut` for rates.
- **Rates now live under a book**, created via:
  - `POST /pricing/rate-cards/{book_id}/rates` — body `RateIn` (`measurement_key`,
    `provider`, `event_type`, `dimensions`, `rate_structure`,
    `rate_per_unit_micros`, `unit_quantity`, `fixed_micros`, `tiers`,
    `product_id`). The kind field and `currency` are no longer accepted here —
    they are inherited from the parent book (single source of truth).
  - `GET /pricing/rate-cards/{book_id}/rates` — lists rates in the book.
    Active-only by default. `?include_history=true` returns every version
    (superseded rows carry `valid_to`); `?as_of=<datetime>` returns the
    version active at that instant. Response is `list[RateOut]`, where
    `RateOut` now includes `rate_card_id` and drops the old `customer_id`.
- **New: `POST /pricing/rate-cards/{book_id}/publish`** — atomic
  multi-measurement reprice. Body `PublishIn` (`changes: list[RateChangeIn]`),
  one entry per measurement key to reprice, matched by
  `(measurement_key, provider, event_type,
  dimensions)`. Each change supersedes the matching active rate
  (`valid_to` stamped, `book_version_to = old book version`) and opens a new
  version (same `lineage_id` — required for tiered/marginal continuity via
  `PricingPeriodCounter` — `book_version_from = new book version`). The book's
  `version` increments once. All-or-nothing in one `transaction.atomic()`
  (`BookService.publish`, `apps/metering/pricing/services/book_service.py`):
  a change with no matching active rate raises and rolls back the whole
  publish, including the version bump. Returns `BookOut`.
- **New: `POST /pricing/customers/{customer_id}/rate-card`** — assign a price
  book to a customer. Body `AssignIn` (`rate_card_id`). One assignment per
  `(customer, currency)`; the kind field is implicitly `"price"` (only price
  books are assignable — cost books are not customer-scoped). Resolution
  (`PricingService._resolve_card`) now consults the customer's assigned book
  first, falling back to the tenant's per-provider default book
  (`RateCard.is_default=True`) for any measurement key the assigned book lacks.
- **Removed endpoints:**
  - The old flat `POST /pricing/rate-cards` create-a-rate-directly semantics
    (superseded by book create + `add_rate`).
  - `PUT /pricing/rate-cards/{id}` (flat update/soft-version) — no
    replacement; use `publish` for atomic repricing.
  - `POST /pricing/rate-cards/batch` (bulk create) — no direct replacement;
    call `add_rate` per measurement key under a book, or use `publish` to
    change many of them in one book atomically.
  - `GET /pricing/rate-cards/{lineage_id}/history` (flat per-lineage
    history) — replaced by `GET /pricing/rate-cards/{book_id}/rates
    ?include_history=true` (scoped to a book, not a lineage).
- **Removed schemas:** `RateCardIn`, `RateCardUpdateIn`, `RateCardBatchIn`
  (dead code once the flat endpoints they served were deleted — grepped for
  remaining references before removal). `RateCardOut` was repurposed/renamed
  to `RateOut` and now describes a rate row within a book, not a flat card.
- **Unchanged:** `GET/PUT /pricing/markup` and the per-customer markup
  endpoints; `DELETE /pricing/rate-cards/{card_id}` still soft-deletes an
  individual `Rate` row (note: despite the URL shape matching the book
  collection, this route operates on `Rate`, not `RateCard` — a
  pre-existing naming overlap in `metering_endpoints.py`, not something this
  reshape introduced but worth knowing when reading the route table).

### Data model / migrations

- `apps/metering/pricing/migrations/0010_rename_ratecard_to_rate.py` —
  state-only `SeparateDatabaseAndState` rename of the Python model `RateCard`
  → `Rate`. Table `ubb_rate_card` is unchanged (no destructive DB rename);
  this only frees the `RateCard` name for the new container.
- `0011_ratecard_container.py` — adds the new `RateCard` container model
  (table `ubb_rate_card_container`; fields `tenant`, the kind field,
  `provider_key`, `currency`, `key`, `name`, `version` and `is_default`) and
  `RateCardAssignment` (table `ubb_rate_card_assignment`; one row per
  `(tenant, customer, currency)`), plus new columns on `Rate`: `pricing_book`
  (FK, nullable), `book_version_from` (default 1), `book_version_to`
  (nullable).
- `0012_backfill_books.py` — data migration
  (`apps/metering/pricing/migrations/_book_backfill.py`) that groups every
  existing active `Rate` into a book: default (customer-less) rates go into
  one `is_default` book per `(tenant, kind, provider, currency)`;
  customer-scoped price rates go into a per-`(customer, currency)` book
  (spanning providers) plus a `RateCardAssignment`. A second pass attaches
  historical (superseded) rate versions to the same book as their active
  lineage sibling, or a fresh book if the whole lineage is superseded.
  Reversible (`backwards` clears `pricing_book` FKs and deletes the created
  books/assignments).
- `0013_rate_book_unique_constraint.py` — replaces `Rate`'s old
  tenant/customer-scoped active-rate uniqueness constraints with a single
  book-scoped constraint, `uq_rate_active_in_book` on
  `(pricing_book, provider, event_type, measurement_key, dimensions_hash,
  currency)` where `valid_to IS NULL`. This is what makes the "assigned book
  shadows the default book for the same measurement key" behavior legal at the
  DB level — the old constraints would have collided on two `customer=NULL`
  rows for the same measurement key in different books.

**Prod backfill parity probe (from the design doc's Task 3 ops note, §10.1) —
SPENT, and the two shell snippets are removed rather than rewritten.**

> ⚠ **This is the one place this file's own header rule is overridden, and it is
> said plainly rather than left for a reader to notice.** The header rules that
> an entry's *facts* — what changed, when, and why — are never rewritten. What
> is removed here is not a fact about 2026-07-03; it is an **instruction to a
> future operator**, and it is an instruction that can no longer be followed.
> The facts it carried are preserved in prose immediately below.

Before
applying `0012`, the probe counted two figures off `Rate`: how many cost rules
were scoped to a named customer (a nonzero count meant the cost-side branch of
`_book_backfill` needed a second look before rollout — the design's open item,
unresolved at spec review), and how many rules were active; after `migrate`, it
counted rules left active with no book, expecting zero.

Both snippets read columns that no longer exist — the kind field was deleted with
the split and the book pointer is `pricing_book` now — so neither runs, and
rewriting them to today's column names would produce instructions that execute
and answer a different question. **What they checked is recorded above; the
commands are not, because a runnable block that cannot run is worse than prose.**
Nothing is owed here: `0012` is a historical migration, and no environment is
waiting to have it applied.

### KNOWN FOLLOW-UP — must land before SDK consumers upgrade

The Python SDK (`ubb-sdk/ubb/metering.py`) has **not** been updated and still
calls the removed routes:
- `create_rate_card()` → `POST /pricing/rate-cards` with the old flat body
  (now creates a book with the wrong shape entirely).
- `update_rate_card()` → `PUT /pricing/rate-cards/{card_id}` (route removed).
- `get_rate_card_history()` → `GET /pricing/rate-cards/{lineage_id}/history`
  (route removed).
- `bulk_create_rate_cards()` → `POST /pricing/rate-cards/batch` (route
  removed).
- `list_rate_cards()` → `GET /pricing/rate-cards` (route still exists but
  now returns books, not rates — response shape mismatch).

Any SDK consumer that upgrades the platform without also getting an SDK
update will see these calls fail (404s on removed routes, and shape
mismatches on `list_rate_cards`/`create_rate_card`). The SDK needs new
`create_book`/`add_rate`/`publish_book`/`assign_book`/`list_book_rates`
methods mirroring the endpoints above before this ships to any environment
with live SDK consumers. Tracked as follow-up work, not part of this
reshape's task list.

### Verification (Task 7)

Full suite: 1525 passed, 27 failed, 3 skipped (pre-existing failures, all in
`apps/billing/invoicing/` and `apps/subscriptions/` — unrelated to this
pricing work, present before this branch). Zero failures in
`apps/metering/` or `api/v1/tests/`. `makemigrations --check --dry-run`
reports `No changes detected`. See
`.superpowers/sdd/task-7-report.md` for the full failing-test list.
