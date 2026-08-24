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

Hot-path resolves use an in-process L1 cache fronted by a per-tenant Redis **version key**. The
default rule: writes bump the version key **at the model layer** (in the model's `save`/`delete`), so
a stale cache can't survive a write. If you add a cached resolve, invalidate the same way — bump a
version key on write, never trust a TTL alone for correctness. Always keep a live-ORM fallback so
caching never under-holds money.

**The markup cache is the worked example** — `ubb:markupver:{tenant}`, bumped from
`TenantDefaultMarkup.save`/`delete`, so no write path can bypass invalidation.

**⚠ There is one exception and it is a better answer, not a lapse: a key that carries the instant it
answers for needs no invalidation at all** (#356). A pricing rule takes effect from a moment that may
be in the future, so bumping a version when the change is *published* invalidates at the wrong
moment, and invalidating at the boundary would need a job running at the effective instant — the one
thing forward-dated publishing exists to avoid. The rate cache's key therefore includes the as-of
instant: **a cached resolution answers for the instant it was computed for and for no other**, so
entries for instants before a new boundary stay correct forever and entries for instants after it
were never created. Its version key `ubb:cardver:{tenant}` still exists and is still read, but it
**has no writer at all** — deliberately, and on the record in
`apps/metering/pricing/services/card_cache.py`, which refuses to add one because a model-layer bump
would put publish-time invalidation straight back. Reach for this shape when what you are caching is
a function of time; reach for the version key when it is not.

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
  or after its horizon and only while its posting is not unresolved).
- ⚠ **A `RECORD_RULE` record is outside G19's statement, so nothing walks it and its rule owes its
  own tests.** G19 walks *field* transition classes; `RECORD_RULE` sits outside `DATABASE_DEFENDED`
  by construction, so no declaration on such a record is ever judged and a green board says nothing
  about whether its rule exists at all. `PostingMeasurement`'s `DELETE` condition (#354) is enforced
  by a **`BEFORE DELETE`** trigger in
  `usage/migrations/0041_a_measurement_is_pruned_only_when_it_may_be.py`, and its three doors are
  `delete()`, `QuerySet.delete()` and raw SQL rather than the `save()` / `QuerySet.update()` / raw
  SQL trio the bullets below use — a whole-record rule is about whether a row may cease to exist,
  not about whether a field may change. Its worked example
  is `usage/tests/test_a_measurement_is_pruned_only_when_it_may_be.py`, and **that module is the
  only thing that would notice the rule's absence**: it has no ledger entry and no manifest row.
- **A whole-record rule reaching another table's column reads it in the trigger, and a `DELETE` rule
  cannot see what else the transaction will do.** Django's collector deletes a child before its
  parent, so a `BEFORE DELETE` trigger on the child cannot tell *this row is being pruned* from
  *the whole parent is being discarded* — the row it would have to consult is still on disk. Where
  that distinction matters, say which case is exempt **positively, in the rule**, rather than by a
  session setting or a temporary drop; both are doors, and ADR-0007 §2's point is that a rule holds
  through every one. #354's is the sandbox tenant, and the tenant table's own `CHECK` is what stops
  the exemption being turned on.
- **Declaring is not enforcing, and a declaration must arrive with what keeps it.** The database
  enforcement is gate G19, **installed by slice 3** (#319) and enforced over the *declarations*
  rather than over a list of columns, so a column you declare is judged on the day you declare it; a
  `DATABASE_DEFENDED` class with nothing behind it is a promise nothing keeps.
  `apps/platform/tests/test_transition_class_declarations.py` is what holds
  that line, and since #318 it holds it from the other side: it walks every declaration in the tree
  and fails on any column the database does not actually defend. **The first pair
  (`Posting`, #318) is enforced by a `BEFORE UPDATE` trigger** installed alongside it in
  `usage/migrations/0037_a_cost_settles_once_and_the_table_holds_it.py` — a `CHECK` cannot see the
  previous row, so it can carry a column's legal values but never a transition rule. A model-level
  `save()` guard is not enforcement and is never shipped as one (ADR-0007 §2).
- **A second pair on the same table gets a second rule, in the same mechanism** — `Posting`'s
  customer price pair (#352), in
  `usage/migrations/0039_a_price_resolves_once_and_the_table_holds_it.py`. Another `BEFORE UPDATE`
  trigger with its own `WHEN` clause over its own columns, rather than a branch inside the first:
  the two govern disjoint columns, neither enters the other's function, and dropping either leaves
  the other standing. What is refused is a second *kind* of mechanism — a `CHECK` or a Postgres
  `RULE` holding one pair while a trigger holds the other, which is how two rules over sibling pairs
  come to disagree about one write. ⚠ **Once a table carries two, address every trigger BY NAME**:
  `pg_trigger` promises no order, so "the table's trigger" and any count are reading whichever row
  came back first. Assert the table's rules as an exact SET.
- ⚠ **A green G19 proves a declared column is NAMED by a rule, never that the rule HOLDS.** Its
  declaration check is a word-boundary search for the column over the concatenated trigger bodies on
  its table, so it goes green on a branch that refuses nothing (#325 measured this; #352 has it as a
  test). **Every declared pair therefore owes a behavioural trio** — a refusal per declared class
  **plus the one admitted move**, each driven through `save()`, `QuerySet.update()` and raw SQL. The
  admitted move is not optional: a trigger that refused every write would satisfy the refusals
  alone. `usage/tests/test_a_cost_settles_once.py` and `usage/tests/test_a_price_resolves_once.py`
  are the two worked examples.
- ⚠ **A `BEFORE` trigger runs ahead of the table's `CHECK` constraints**, so installing one turns
  every `UPDATE`-driven constraint test on that table into a test of the trigger. Drive constraint
  cases through `INSERT` (a `BEFORE UPDATE` trigger never fires on one), and make **every** refusal
  assert the MESSAGE — "something refused this" stops being evidence the moment a table has two
  mechanisms. #318 hit this for the cost pair and #352 hit it again for the price pair.
- **A rule that cannot fire on the hot statements owes a proof rather than a measurement.**
  ADR-0007's Consequences are about *per-insert and per-update* cost, so a `BEFORE DELETE` trigger
  pays zero on both by construction. Assert the statement mask out of `pg_trigger` — the `INSERT`
  and `UPDATE` bits **off** — which is a stronger claim than a benchmark reporting a small number
  and one that cannot drift (#354).
- **A new rule on a hot table owes a measurement, not an assumption** (ADR-0007's Consequences).
  `scripts/measure_posting_transition_cost.py` is the worked example: it asks for each rule **by
  name** rather than counting, installs and drops them together, times each permitted move
  separately, alternates the states per run and prints a **noise floor** — because the first version
  of it reported a trigger that made every statement faster.

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
