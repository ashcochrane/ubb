# Pricing API Changelog

No repo-wide `CHANGELOG.md` convention exists yet (checked `git log` for prior
changelog commits and searched `docs/` — neither turned up anything). This
file starts a per-surface changelog for the `/api/v1/metering/pricing/*`
routes; follow-on breaking changes to this surface should be appended here.

## 2026-07-15 — Tiered pricing removed (BREAKING, ADR-0003)

The `graduated` and `package` pricing models are **deleted end to end** — not
gated (`docs/adr/0003-mvp-launches-without-tiered-pricing.md`; decided in
issue #22, executed via issue #30). The MVP launches with `per_unit` and
`flat` only; every arrival-time estimate now equals the settled price by
construction (the only remaining accept-vs-settle difference is rate-card
config drift).

- **`POST /pricing/rate-cards/{book_id}/rates`** — `pricing_model` accepts
  only `per_unit`/`flat` (anything else → 422); the `tiers` field is removed
  from `RateIn`, `RateChangeIn` (publish), and `RateOut`.
- **`POST /pricing/rate-cards/{book_id}/publish`** — validates
  `pricing_model` against the narrowed choices (ValueError → 422, whole
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

`/pricing/rate-cards` used to manage flat, per-metric rate cards directly.
It now manages **books** (`RateCard` containers) that group many per-metric
**rates** (`Rate`, the renamed old `RateCard` model). This is a deliberate
breaking change with no compatibility shim (per design §2.4 / §9 "Breaking
API" risk note) — it enables atomic multi-metric repricing and per-customer
book assignment, which a flat per-rate model could not express safely.

### What changed

- **`POST/GET /pricing/rate-cards`** now creates/lists **books**, not rates.
  - Request body is `BookIn` (`card_type`, `provider_key`, `key`, `name`,
    `currency`, `is_default`) instead of the old flat rate payload.
  - Response shape is `BookOut` (`id`, `card_type`, `provider_key`, `key`,
    `name`, `currency`, `version`, `is_default`) — **`RateCardOut` is gone**,
    replaced by `BookOut` for books and a repurposed `RateOut` for rates.
- **Rates now live under a book**, created via:
  - `POST /pricing/rate-cards/{book_id}/rates` — body `RateIn` (`metric_name`,
    `provider`, `event_type`, `dimensions`, `pricing_model`,
    `rate_per_unit_micros`, `unit_quantity`, `fixed_micros`, `tiers`,
    `product_id`). `card_type` and `currency` are no longer accepted here —
    they are inherited from the parent book (single source of truth).
  - `GET /pricing/rate-cards/{book_id}/rates` — lists rates in the book.
    Active-only by default. `?include_history=true` returns every version
    (superseded rows carry `valid_to`); `?as_of=<datetime>` returns the
    version active at that instant. Response is `list[RateOut]`, where
    `RateOut` now includes `rate_card_id` and drops the old `customer_id`.
- **New: `POST /pricing/rate-cards/{book_id}/publish`** — atomic multi-metric
  reprice. Body `PublishIn` (`changes: list[RateChangeIn]`), one entry per
  metric to reprice, matched by `(metric_name, provider, event_type,
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
  `(customer, currency)`; `card_type` is implicitly `"price"` (only price
  books are assignable — cost books are not customer-scoped). Resolution
  (`PricingService._resolve_card`) now consults the customer's assigned book
  first, falling back to the tenant's per-provider default book
  (`RateCard.is_default=True`) for any metric the assigned book lacks.
- **Removed endpoints:**
  - The old flat `POST /pricing/rate-cards` create-a-rate-directly semantics
    (superseded by book create + `add_rate`).
  - `PUT /pricing/rate-cards/{id}` (flat update/soft-version) — no
    replacement; use `publish` for atomic repricing.
  - `POST /pricing/rate-cards/batch` (bulk create) — no direct replacement;
    call `add_rate` per metric under a book, or use `publish` to change many
    metrics in one book atomically.
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
  (table `ubb_rate_card_container`; fields `tenant`, `card_type`,
  `provider_key`, `currency`, `key`, `name`, `version`, `is_default`) and
  `RateCardAssignment` (table `ubb_rate_card_assignment`; one row per
  `(tenant, customer, currency)`), plus new columns on `Rate`: `rate_card`
  (FK, nullable), `book_version_from` (default 1), `book_version_to`
  (nullable).
- `0012_backfill_books.py` — data migration
  (`apps/metering/pricing/migrations/_book_backfill.py`) that groups every
  existing active `Rate` into a book: default (customer-less) rates go into
  one `is_default` book per `(tenant, card_type, provider, currency)`;
  customer-scoped price rates go into a per-`(customer, currency)` book
  (spanning providers) plus a `RateCardAssignment`. A second pass attaches
  historical (superseded) rate versions to the same book as their active
  lineage sibling, or a fresh book if the whole lineage is superseded.
  Reversible (`backwards` clears `rate_card` FKs and deletes the created
  books/assignments).
- `0013_rate_book_unique_constraint.py` — replaces `Rate`'s old
  tenant/customer-scoped active-rate uniqueness constraints with a single
  book-scoped constraint, `uq_rate_active_in_book` on
  `(rate_card, provider, event_type, metric_name, dimensions_hash,
  currency)` where `valid_to IS NULL`. This is what makes the "assigned book
  shadows the default book for the same metric" behavior legal at the DB
  level — the old constraints would have collided on two `customer=NULL`
  rows for the same metric in different books.

**Prod backfill parity probe (from the design doc's Task 3 ops note, §10.1):**
before applying `0012` to staging/prod, run:
```bash
DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python manage.py shell -c "
from apps.metering.pricing.models import Rate
print('cost customer-scoped:', Rate.objects.filter(card_type='cost', customer__isnull=False).count())
print('active rates:', Rate.objects.filter(valid_to__isnull=True).count())
"
```
A nonzero "cost customer-scoped" count means the cost-side branch of
`_book_backfill` needs a second look before rollout (the design's open
item: whether customer-scoped cost rates exist was unresolved at spec
review). After `migrate`, confirm zero orphans:
```bash
DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python manage.py shell -c "
from apps.metering.pricing.models import Rate
print('orphaned active rates:', Rate.objects.filter(valid_to__isnull=True, rate_card__isnull=True).count())
"
```

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
