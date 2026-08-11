# Django patterns

The house patterns for this Django project (`ubb-platform/`, `config/settings.py`, Celery, Django
Ninja). These are the mechanisms the product boundaries (`../architecture/2026-06-12-adr-001-product-boundaries.md`)
are built on — use them rather than reaching across a boundary directly.

## Transactional outbox (the default cross-product channel)

- Emit domain events with `apps.platform.events.outbox.write_event(...)` **inside the same
  `transaction.atomic()` block** as the change that produced them. If the transaction commits the
  event is guaranteed; if it rolls back the event never existed. Never emit an event as a side effect
  outside the transaction.
- **Register handlers in `AppConfig.ready()`** via the registry, keyed by event type, with a stable
  handler name and a `requires_product` gate:

  ```python
  # apps/referrals/apps.py
  def ready(self):
      from apps.platform.events.registry import handler_registry
      from apps.referrals.handlers import handle_usage_recorded_referrals
      handler_registry.register(
          "usage.recorded", "referrals.reward_accumulator",
          handle_usage_recorded_referrals, requires_product="referrals",
      )
  ```

- Handlers are **idempotent** — dispatch is at-least-once and a per-(event, handler) checkpoint
  makes redelivery a no-op. Write handlers that tolerate being called twice.
- **Event schemas are additive-only** (`apps/platform/events/schemas.py`): a new field needs a
  default; a breaking change means a new event class, not an edited one.

## Synchronous reactions: the platform hooks registry

When a product must react to a platform lifecycle change **in the same transaction** (e.g. a
seat-roster change pushing a new Stripe quantity), the platform kernel cannot import the product
(rule 2). Instead the product registers a listener on `apps/platform/customers/hooks.py`, and the
push is deferred to `transaction.on_commit` so it binds to the roster change's own commit. Use this
only for genuinely synchronous needs; everything tolerant of latency goes on the outbox.

## Locking & concurrency

- Take row locks with `select_for_update` in the canonical global order (Run → Wallet → Customer →
  TopUpAttempt → Invoice → Posting; `core/locking.py`). Wallet mutations go through
  `lock_for_billing`, which also lazily creates the wallet in the tenant currency.
- The serialization points that matter (e.g. wallet drawdown) row-lock a single counter row and
  advance it **inside the caller's event-insert transaction** — don't split the lock and the write
  across transactions.

## Caching & invalidation

Hot-path resolves (rate cards, markups) use an in-process L1 cache fronted by a per-tenant Redis
**version key** (`ubb:cardver:{tenant}`, `ubb:markupver:{tenant}`). Writes bump the version key **at
the model layer** (in the model's `save`/`delete`), so a stale cache can't survive a write. If you
add a cached resolve, invalidate the same way — bump a version key on write, never trust a TTL alone
for correctness. Always keep a live-ORM fallback so caching never under-holds money.

## Celery

Async work and periodic safety nets are Celery tasks/beats: the outbox `sweep`, the run `reaper`,
AR/cost-accumulator `reconcile_*` jobs, postpaid period close. Broker/result backend are Redis
(`config/celery.py`). These reconcilers are the belt-and-suspenders backstop — the durable ledger /
`Posting` rows remain the source of truth they repair toward, never a cache.

## API

The HTTP layer is **Django Ninja** under `api/v1` and per-product `apps/*/api` — this is the
composition layer, so it may import any product. Keep business logic in product services; endpoints
wire and validate.

## Declared transition classes

- **A model holding economic facts declares, per column, what may happen to it** — ADR-0007 §2's
  four classes (`FROZEN`, `RESOLVE_ONCE`, `SET_ONCE`, `PRUNABLE`), spelled from `core/transitions.py`
  in a `transition_classes = {field_name: CLASS}` mapping beside the fields. The point is answering
  "what is allowed to happen to this?" before the column ships.
- **A record whose whole lifecycle is one rule declares `RECORD_RULE` instead**, which is *not* a
  fifth class — it is the absence of a per-column one, said out loud, with the rule itself written in
  the model's docstring. `PostingMeasurement` is the first (insert once, never update, delete only at
  or after its horizon).
- **Declaring is not enforcing.** The database enforcement is gate G19, `owned_by_slice_3`; until it
  lands, a `DATABASE_DEFENDED` class would be a promise nothing keeps.
  `apps/platform/tests/test_transition_class_declarations.py` is what holds that line.

## Migrations

- `makemigrations` for every model change; commit the migration with the change. CI runs against a
  fresh DB, so a missing migration fails there.
- **A column that moves to another table carries its data** (ADR-0007 §1). The autodetector emits the
  `RemoveField` *before* the `CreateModel`, which is an add-plus-remove that empties what it claims to
  move — hand-order it create → `RunPython` → remove, and give the `RunPython` a real reverse that a
  test actually runs. See `usage/migrations/0031_the_measurements_become_a_child_record.py`.
- **Migration numbers must not collide.** ADR-001 records a fork whose rival pricing schema carried
  colliding migration numbers on top of the live RateCard engine — never merge migrations that
  renumber onto shipped ones; rebase them to follow the current head.
