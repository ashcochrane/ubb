# RateCard Container (Rate + RateCard two-level pricing) — Design

**Date:** 2026-07-03
**Status:** Proposal for discussion (no code yet) — v1
**Author:** Engineering

---

## 0. The reframe (read this first)

Today's `RateCard` model is misnamed. What UBB calls a `RateCard` is one metric's rate — `(provider, event_type, metric_name, dimensions)` → one pricing model + price, versioned on its own `lineage_id`. In every comparable product (Metronome, Stripe, Chargebee) a **"rate card" is the container** — a named sheet holding many rates, versioned and assigned to customers as a unit. UBB built the inner layer and gave it the outer layer's name.

This design introduces the missing container and fixes the naming:

- **`Rate`** = today's per-metric object (renamed, behavior unchanged).
- **`RateCard`** = the new container grouping many `Rate`s, versioned and assignable.

It buys three things we don't have: **atomic multi-metric repricing** (a customer is never priced on a mix of old and new rates), **per-customer assignment** ("put Acme on the Enterprise card" as one operation), and a **name that matches the concept.**

**Honest boundary:** this is a real rename plus a resolution-path change and a data migration of every existing rate. It is not a free relabel. The guarantee it delivers — "never on a mix" — comes almost entirely from doing a multi-rate reprice in one transaction; the container mostly tells us *which* rates to bump together and gives assignment + history a home.

## 1. Scope (phased)

**In this spec:**
- The `RateCard` container; `RateCard` → `Rate` rename.
- Atomic multi-metric repricing via a book-level **publish** operation.
- Per-customer **assignment** of a price book, with default-book fallback.

**Deferred to a later "contracts" phase (explicitly out of scope here):**
- Per-rate customer overrides *within* a shared book (today's customer-scoped single-rate override, generalized).
- Effective-dating / contract terms.
- Version-pinned grandfathering (keeping a customer on book v2 after v3 publishes). The schema leaves the seam for it (`book_version_*` columns) but phase 1 assignment always tracks the book's current version.

## 2. Confirmed decisions

These were proposed and approved (three were adopted as recommendations while the user was away and then confirmed):

1. **Book identity = named / flexible.** A `RateCard` is a named sheet (`key` = "gemini", "enterprise-2026") that *can* span providers and event_types. Conventionally one provider ("everything Gemini on one card"), but not enforced — this is what enables cross-provider enterprise bundles and per-customer assignment.
2. **Books are typed by `card_type` (cost | price).** Both cost and price books get atomic versioning. **Only price books are assignable** — cost cards are the provider cost basis, not something a customer is "put on."
3. **The rename is in scope** (`RateCard` → `Rate`; container takes the `RateCard` name), over the lower-risk `PricingBook`-container-without-rename alternative. The name is the point.
4. **The API reshape is a deliberate breaking change** (no compatibility shim for the old per-rate `/pricing/rate-cards` routes). Ships with a changelog / version note, same class as the `usage_mode` removal but larger.

## 3. Data model

```
RateCard (container)                       # was: PricingBook in discussion
  tenant           FK
  card_type        cost | price
  currency         3-char, pinned to tenant currency (CUR-1)
  key              slug, unique per (tenant, card_type)   e.g. "gemini"
  name             human label
  version          monotonic int, starts at 1, bumped on publish
  is_default       bool — the tenant's fallback book for this (card_type, provider, currency)

Rate (today's RateCard, renamed — all existing fields retained)
  rate_card              FK -> RateCard          # NEW: membership
  book_version_from      int                     # NEW: first book version this row is live in
  book_version_to        int | null              # NEW: null = live in current version
  provider, event_type, metric_name, dimensions, dimensions_hash
  pricing_model, rate_per_unit_micros, unit_quantity, fixed_micros, tiers
  lineage_id, valid_from, valid_to               # per-rate temporal versioning — UNCHANGED
  # NOTE: the `customer` FK leaves the default resolution path. Customer scoping
  # becomes "customer assigned to a customer-specific book" (§5, §6). The column
  # may remain physically during migration but is no longer consulted by _resolve_card.

RateCardAssignment                              # price books only
  tenant           FK
  customer         FK
  rate_card        FK -> RateCard (card_type = price)
  unique (tenant, customer, currency)           # one price book per customer per currency
```

Invariants:
- Exactly one `is_default` book per `(tenant, card_type, provider, currency)` — i.e. one default book *per provider* (the `provider = ""` bucket is just another provider value, holding no-provider rates). This is what makes "the tenant's standard Gemini card" a first-class object while still supporting per-customer bundles via assignment (§5).
- Every active `Rate` (`valid_to IS NULL`) belongs to exactly one `RateCard`.
- A `Rate`'s `card_type` is inherited from its `RateCard` (drop the redundant per-rate column, or keep it in sync — decide at implementation; single source of truth is the container).
- `PricingPeriodCounter` stays keyed on `lineage_id` — grouping does not touch tiered marginal continuity.

## 4. Versioning & atomic repricing (the core guarantee)

The existing resolver filters `valid_from <= as_of AND (valid_to IS NULL OR valid_to > as_of)`. **Time-based resolution already yields atomicity if a multi-rate reprice happens in a single transaction** — every superseded rate closes at the same instant `T` and every new rate opens at `T`, so an `as_of` before `T` sees all-old and an `as_of` at/after `T` sees all-new. There is no in-between.

The container supplies the **publish** operation that wraps the set:

```
publish(rate_card, changes):
  with transaction.atomic():
    T = now()
    for each changed rate:
      old.valid_to = T
      new = old.copy(apply change); new.valid_from >= T; new.lineage_id = old.lineage_id
      new.book_version_from = rate_card.version + 1
      old.book_version_to   = rate_card.version
    rate_card.version += 1
```

- **Concurrency:** a pricing call at `as_of = now()` executing while `publish` is mid-transaction cannot see partial state — the transaction is uncommitted. After commit it sees the whole new set.
- **History:** `book_version_from/to` make "book v3 = exactly these rate rows" queryable, and are the seam for version-pinned grandfathering in the contracts phase (resolution would pin `as_of`→version via the customer's assignment).
- **Resolution stays time-based in phase 1** — no rewrite of the hot path, only a book-membership scoping (§5).

This is the whole "never on a mix" guarantee. The container's job is to know *which* rates form the set.

## 5. Assignment & resolution

Today `_resolve_card` walks `owners = [customer.id, None]` per metric — a customer-scoped `Rate` row beats the tenant default, then dimension-specificity + `valid_from` break ties.

New model — assignment is at the **book** level, and the default/fallback book is keyed on the **event's provider**:

```
_resolve_card(tenant, customer, card_type, provider, event_type, metric, tags, currency, as_of):
  # 1. Customer's assigned book (one per customer, may span providers). Price books only.
  book = assigned_book(tenant, customer, card_type, currency)   # RateCardAssignment, else None
  if book is not None:
    rate = resolve_rate_within(book, provider, event_type, metric, tags, as_of)  # existing specificity + temporal logic, scoped to the book
    if rate is not None:
      return rate
  # 2. Fallback: the tenant's default book FOR THIS PROVIDER (is_default per (tenant, card_type, provider, currency)).
  default_book = default_book_for(tenant, card_type, provider, currency)
  return resolve_rate_within(default_book, provider, event_type, metric, tags, as_of)
```

- A customer with no assignment resolves straight to the provider's default book — so unassigned customers keep using the tenant's standard per-provider rates.
- If no default book exists for the event's provider (e.g. a provider that only appears inside a bundle), `resolve_rate_within` returns `None` → an uncosted metric, handled by the existing uncosted-metric path in `PricingService.price` (unchanged).
- A customer assigned to a spanning bundle ("Enterprise") uses it where it has a rate, and falls through to the provider's default book where it doesn't — assignment never has to be exhaustive.
- Customer override is now "assign the customer a different book," not "mint a customer-scoped rate row."
- `resolve_rate_within` is today's specificity (`len(dimensions)`) + temporal (`valid_from`) logic, byte-for-byte, only with the candidate set scoped to one book.
- Per-rate overrides *inside* a shared book = deferred contracts phase.

## 6. Migration / backfill

One data migration, run after the schema migration that adds `RateCard` / `RateCardAssignment` and the new `Rate` columns.

- **Tenant-default rates** (`customer IS NULL`): group into **one book per `(tenant, card_type, provider, currency)`**, named after the provider ("gemini"; the `provider = ""` bucket becomes a book named e.g. "default"), attach matching rates at `book_version_from = 1`, and mark each such book `is_default = true` for its `(tenant, card_type, provider, currency)`. This is the "everything Gemini on one card" outcome, and it is exactly the fallback target §5 resolves to for an unassigned customer.
- **Customer-scoped rates** (`customer NOT NULL`): create a per-`(customer, card_type)` book, attach that customer's rate rows, and create a `RateCardAssignment` (price books only). Cost-side customer-scoped rates — if any exist — attach to a customer cost book without an assignment (cost books aren't assignable); confirm whether any such rows exist before assuming.
- **Assertions in the migration:** row-count parity (every active rate lands in exactly one book); for a fixed `as_of`, a sampled set of `(customer, provider, event_type, metric)` prices identically pre- and post-migration. Fail the migration loudly on mismatch.
- **Reversibility:** books/assignments are derivable from rates; the reverse migration drops the containers and restores the `customer` FK path.

## 7. API surface

Breaking reshape (no shim):

- `GET/POST /pricing/rate-cards` → now **books** (list/create a container). Create-a-book-with-its-rates in one call reuses today's `batch` semantics.
- `GET/PUT /pricing/rate-cards/{id}/rates` (or `/pricing/rates`) → manage the `Rate`s inside a book.
- `POST /pricing/rate-cards/{id}/publish` → transactional reprice → new version (§4).
- `GET /pricing/rate-cards/{id}/versions` → version history.
- `POST /pricing/customers/{id}/assign` → assign a price book (§5).
- Ships with a changelog entry and an API version note.

## 8. Testing

Existing pricing suite is the regression net (must stay green through the rename). New tests:

- **Publish atomicity:** a price call issued against a book mid-reprice resolves to all-old or all-new, never mixed (transaction-boundary test).
- **Assignment resolution + default fallback:** assigned book wins; missing metric falls through to default book.
- **Migration parity:** every legacy active rate lands in exactly one book; prices identical pre/post for a fixed `as_of` across a sampled key set.
- **Tiered continuity across publish:** `compute_marginal` telescoping unbroken when a graduated/package rate is republished (lineage_id preserved).
- **Rename safety:** `_resolve_card`, endpoints, admin, serializers all reference the renamed models; no dangling `RateCard`-as-rate usage.

## 9. Risks & mitigations

- **Rename churn.** Use `SeparateDatabaseAndState` so physical table names stay stable (rename in Python without a destructive DB rename); keep the diff mechanical and reviewable.
- **Resolution regression.** The `_resolve_card` change is the highest-risk edit; migration parity tests + the full existing suite guard it. Keep the specificity/temporal logic byte-for-byte, only scoping the candidate set to a book.
- **Migration correctness.** Loud assertions + sampled price-equality; dry-run on a prod snapshot before applying.
- **Breaking API.** Deliberate; mitigated by changelog + version note, not a shim (per decision §2.4).

## 10. Open items to confirm at spec review

- Whether any **customer-scoped cost** rates exist today (affects the cost-side branch of the migration; a quick query settles it before we write the migration).
- Final route names for the rate-management sub-resource (`/rate-cards/{id}/rates` vs `/pricing/rates`).
- Whether to physically drop the `Rate.customer` column in this phase or leave it dormant until the contracts phase (functionally it leaves the resolution path regardless).

### 10.1 Ops note: prod parity check before applying `0012_backfill_books`

Before applying migration `0012` to staging/prod, run the parity probe to size
the backfill and confirm the customer-scoped-cost open item above (a nonzero
"cost customer-scoped" count means the cost-side branch of `_book_backfill`
needs a second look before rollout):

```bash
DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python manage.py shell -c "
from apps.metering.pricing.models import Rate
print('cost customer-scoped:', Rate.objects.filter(card_type='cost', customer__isnull=False).count())
print('active rates:', Rate.objects.filter(valid_to__isnull=True).count())
"
```

After `migrate`, confirm the count of orphaned (`rate_card IS NULL`) active
rates is zero:

```bash
DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python manage.py shell -c "
from apps.metering.pricing.models import Rate
print('orphaned active rates:', Rate.objects.filter(valid_to__isnull=True, rate_card__isnull=True).count())
"
```
