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
  default; a breaking change means a new event class, not an edited one. Two admitted exceptions,
  each recorded at the field it applies to: a CLOSED vocabulary field may be required once a data
  migration has stamped every stored row and queued payload — where it has no honest default
  (#458's `control_family`), or where the owner has ruled the concept required wherever it is
  published (#603's `pricing_status_reason`, required AND nullable: its null is a value, never an
  absence, `events/0010`) — or with NO stamp, where the field's producers have always written it
  from the closed column it publishes, so no stored or queued payload can lack it and there is
  nothing to stamp (R10-W4, ADR-0024: the credit-grant pair's `kind`, `invitation.created`'s and
  `member.activated`'s `role`; each field names the producer it rests on); and while the pre-live
  lane is open (ADR-0007 §5) a rename may be made in
  place with its break recorded in the gate's block and its queued payloads migrated (#458's
  `reason` → `reason_code` on the customer stop pair; #464's five event NAMES moved under their
  families, with every stored subscription and queued row carried by `events/0009`) — and, in
  the same lane, a field that published `0` for "nothing applies" may widen in place to
  nullable, because ADR-0013 §5's *not applicable, never zero* is the field's meaning and the
  `0` was never a value (#610: `task_cogs_ceiling_micros` on the four terminal stops,
  `balance_micros` on the customer stop pair; nothing is deployed, so no queued payload is
  carried). A payload's TITLE is its class name, so renaming a class is a rename too (#554). Every
  class takes its `EVENT_TYPE` from `core.vocabulary` by reference — the catalogue gate reads
  the name through the registry's constant, and a literal or a name from anywhere else is
  refused (#464).

## Synchronous reactions: the platform hooks registry

When a product must react to a platform lifecycle change **in the same transaction** (e.g. a
seat-roster change pushing a new Stripe quantity), the platform kernel cannot import the product
(rule 2). Instead the product registers a listener on `apps/platform/customers/hooks.py`, and the
push is deferred to `transaction.on_commit` so it binds to the roster change's own commit. Use this
only for genuinely synchronous needs; everything tolerant of latency goes on the outbox.

**The terminal-transition listener registry** (`apps/platform/work/hooks.py`, #460) is the second
registry on this channel, on the roster one's shape: a product registers
`register_terminal_transition_listener(fn)` in its `AppConfig.ready()` (idempotent — `ready()`
can run more than once), and the kernel calls every listener synchronously, inside the flip's own
transaction, for every terminal transition of a unit of work — a close, a kill, an expiry, and
each of the three cascades — handing it the row and a `TerminalTransition` (the state entered,
what was recorded about why, and whether containment wrote it). Billing's one listener releases
the prepaid reservation (`apps/billing/wallets/reservations.py:release_on_terminal_transition`,
registered in `WalletsConfig.ready()`); a product that needs the outbox's latency tolerance
instead subscribes to the terminal stop events. **A listener is a notification and never a veto**
(#141 §6.4): the row is already written when it runs, and the one deliberate departure from the
roster registry is that an exception is CAUGHT under the listener's own savepoint and logged
(`work.terminal_listener_failed`) rather than propagated — a listener here does its work inside
the caller's transaction, so letting it raise would roll a kernel fact back on a product's bug.
What a failed listener owed is left undone on purpose, and the product that owed it owns the
backstop (for the reservation, an hourly sweep over terminal work still holding one). A walker in
`apps/platform/work/tests/test_every_terminal_path_reaches_the_listeners.py` holds that every
function writing a terminal status notifies, so a new terminal path cannot forget the channel.

**The replay consumer registry** (`apps/platform/event_types/hooks.py`, #473 row 1, #568) is the
third, on the same shape — `register_replay_consumer(fn)` in `AppConfig.ready()`, idempotent, every
consumer called synchronously inside the kernel act's own transaction — and **the deliberate
opposite of the terminal one: a consumer that raises VETOES the act.** The act is a tenant's decision
about a held name (a map, a register, or a publication declaring it), and the consumer's work — the
held event re-costed from its own moment (`resolution_run.replay_the_held_event`, registered in
`PricingConfig.ready()`) — is that decision's consequence, not a notification about it: a name
recorded as decided whose event was never re-costed would leave the period-close safeguard with
nothing looking at it again. So nothing catches there, and decision and replay land together or not
at all. ⚠ **A publication is not one of those decisions' transactions** (the consultant's review of
#618): publishing configuration and replaying history are different responsibilities, so
`EventType.publish` commits the declaration alone and the held names it answers are registered and
replayed AFTER it commits — a doorbell (`transaction.on_commit` → a Celery task, broker errors
logged and swallowed, as the outbox's) and every Resolution Run (the retry) — each name in a
transaction of its own, so one that is refused or breaks stays held while the rest are answered, and
the publication is never what is vetoed. Choose by asking whether the reaction is the fact's
consequence (veto, same transaction) or news about it (notification), and keep work that grows with
history out of a configuration write either way.

## Locking & concurrency

- Take row locks with `select_for_update` in the canonical global order (Run → Wallet → Customer →
  TopUpAttempt → Invoice → Posting; `core/locking.py`). Wallet mutations go through
  `lock_for_billing`, which also lazily creates the wallet in the tenant currency.
- The serialization points that matter (e.g. wallet drawdown) row-lock a single counter row and
  advance it **inside the caller's event-insert transaction** — don't split the lock and the write
  across transactions.

## Caching & invalidation

**No resolve on the hot path is cached today** (#556). The rate-card and markup caches were deleted
because nothing in production ever read them: their one reader, the accept-time estimate, went in
#239, and recording resolves against the live ORM through `PricingService`. If you add a cache,
these are the rules it inherits:

- **Invalidate at the model layer.** Front the in-process L1 with a per-tenant Redis **version key**
  bumped in the model's `save`/`delete`, so no write path can bypass it; never trust a TTL alone for
  correctness; keep a live-ORM fallback so caching never under-holds money. A route deleting through
  `QuerySet.delete()` never loads an instance and so never bumps — the deleted markup cache measured
  exactly that leak (#369).
- **⚠ A key that carries the instant it answers for needs no invalidation at all** (#356), and it is
  the better answer when what you cache is a function of time. A pricing rule takes effect from a
  moment that may be in the future, so bumping a version when the change is *published* invalidates
  at the wrong moment, and invalidating at the boundary would need a job running at the effective
  instant — the one thing forward-dated publishing exists to avoid. Keyed on the as-of instant, **a
  cached resolution answers for the instant it was computed for and for no other**. That holds only
  while nobody publishes a stale draft, and `core/scheduling.py` says why it cannot promise more.
  Reach for this shape when the value is a function of time; reach for the version key when it is
  not.

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
  the model's docstring. `PostingMeasurement` is the first (insert once, never update — except its
  release, below — delete only at or after its horizon and only while its posting is not unresolved).
  Since W5 one of its columns does have a class: `prunable_at` is `SET_ONCE`, the release fact the
  daily prune writes in the transaction that deletes the record
  (`trg_posting_measurement_released_once`, ADR-0025).
- ⚠ **A `RECORD_RULE` column is outside G19's statement, so nothing walks it and its rule owes its
  own tests.** G19 walks *field* transition classes; `RECORD_RULE` sits outside `DATABASE_DEFENDED`
  by construction, so no `RECORD_RULE` declaration is ever judged and a green board says nothing
  about whether the record's rule exists at all. `PostingMeasurement`'s `DELETE` condition (#354) is enforced
  by a **`BEFORE DELETE`** trigger, `trg_posting_measurement_pruning`, and its three doors are
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
- **⚠ The one rule that READS a session setting does so to name a writer, not to exempt a case, and
  it says so.** The price pair's admitted move (`unknown` to `known`) is admitted only on a statement
  `price_resolution.resolve_customer_price` marked (`trg_posting_price_transitions`, #557): the
  transaction-local setting `ubb.price_door`, set by `marked_as_the_price_door` around the door's one
  `UPDATE` and cleared after. The bullet above still holds for what it is about — a case a rule must
  hold through is stated positively in the rule. This is a different question with no positive
  statement available: Postgres cannot see which function issued a statement, so naming the one
  writer takes a mark. It is a guard against a second writer by ACCIDENT — any code can set the
  mark, and every setter goes through that one context manager, a search away — and it is not a
  security boundary. It covers the move, an `UPDATE`; an insert that arrives `known` is the
  recording path's own pricing, not a resolution.
- **Declaring is not enforcing, and a declaration must arrive with what keeps it.** The database
  enforcement is gate G19, **installed by slice 3** (#319) and enforced over the *declarations*
  rather than over a list of columns, so a column you declare is judged on the day you declare it; a
  `DATABASE_DEFENDED` class with nothing behind it is a promise nothing keeps.
  `apps/platform/tests/test_transition_class_declarations.py` is what holds
  that line, and since #318 it holds it from the other side: it walks every declaration in the tree
  and fails on any column the database does not actually defend. **The first pair
  (`Posting`, #318) is enforced by a `BEFORE UPDATE` trigger**, `trg_posting_declared_transitions`
  — a `CHECK` cannot see the
  previous row, so it can carry a column's legal values but never a transition rule. A model-level
  `save()` guard is not enforcement and is never shipped as one (ADR-0007 §2).
- **A second pair on the same table gets a second rule, in the same mechanism** — `Posting`'s
  customer price pair (#352), `trg_posting_price_transitions`. Another `BEFORE UPDATE`
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
- **A declaration table can carry a class too, and the same mechanism holds it** — `TaskType`'s
  pricing regime (#414, ADR-0012) is `FROZEN` under a `BEFORE UPDATE` trigger exactly as a posting's
  pairs are, with a `WHEN` clause that makes an idempotent re-declaration free. That clause is
  load-bearing rather than an optimisation: the registry's write surface is a whole-collection `PUT`
  that sends every column on every call, so a rule firing on equal values would refuse a tenant
  re-sending what it already declared. The route's own `409` is the courtesy, not the enforcement.
  Worked example: `apps/platform/work/tests/test_a_kind_of_work_declares_how_it_is_sold.py`
  (`TheRegimeIsFrozenTest`, whose control case is what stops a rule that refuses every update from
  passing).
- **A rule that compares two rows is a rule about who may be BORN, so it is a `BEFORE INSERT`
  trigger, and its three doors are the three ways a row is born.** A `CHECK` sees one row and can
  never read the parent; a mutability class governs what may happen to a row *after* it exists.
  Contained work sharing its container's pricing regime (#415) is the first: refused through
  `objects.create()`, a bare `save()` on the base class, and an `INSERT` around the ORM, with
  `TaskService.create_task` holding the same rule first so a caller gets a sentence naming both
  regimes rather than an `IntegrityError`. Worked example:
  `apps/platform/work/tests/test_containment_shares_the_pricing_regime.py`, whose last class
  replaces the rule's body in-process with one that still names the column and reads the parent's
  regime but refuses nothing — a mutant a control reading the function's source for the column name
  cannot tell from the shipped rule — and shows the mixed tree is then admitted at every door:
  *remove X and confirm*, run rather than asserted.
- **A whole-record declarer over many columns diffs the old row against the new over a NAMED set
  and names the columns that moved.** `Charge` (#416, ADR-0013) is the first: every economic column
  `FROZEN` under one rule, so *something refused this* stopped being unambiguous the day it landed,
  and every assertion about it names a column beside the class. Two things follow. A pointer is
  declared by its **column** (`task_id`, not `task`), because G19 searches a trigger body and a
  trigger says `NEW.task_id` — declaring the field name would be satisfiable only by a comment. And
  the column set is read **off the migration that installed the rule**, so the declaration on the
  model and the rule on the table are compared against one list rather than two copies that agree
  until somebody edits one. Worked example:
  `apps/metering/pricing/tests/test_a_charge_is_written_once_and_never_edited.py`. `Posting.kind`
  (#417) is the same class on a column with no admitted move at all, and the fourth trigger on that
  table: `usage/tests/test_a_postings_kind_is_settled_at_birth.py` shows what a `FROZEN` trio looks
  like when there is no admitted move to serve as the control — the columns and sibling rules the
  trigger must leave alone are asserted instead.

## Migrations

- `makemigrations` for every model change; commit the migration with the change. CI runs against a
  fresh DB, so a missing migration fails there.
- **The history starts at the cutover's fresh initial set** (#190, ADR-0026): one generated
  `0001_initial` per app, and in each app that owns a database rule a hand-written
  `0002_the_database_rules.py`. **Every trigger lives there**, one `RunSQL([install], [uninstall])` per
  rule — a list, because a plain string is split and comment-stripped by `sqlparse` — and the rules
  migration depends on the schema leaf of every app owning a table its SQL reads, never on an assumed
  `0001` (`apps/platform/tests/test_the_database_rules_are_carried.py` holds all of it). A new rule
  goes in a new migration after the fresh set, on the same pattern, with a behavioural refusal test.
- **Every migration after the fresh set is held by G20** (ADR-0007 §1;
  `tests/contracts/test_migrations_carry_their_data.py`): a rename is `RenameField` / `RenameModel`,
  never a drop and an add in the same or the next migration of an app; a `RemoveField` /
  `DeleteModel` states its reason in a module-level `DROPS = {...}`; a `RunPython` / `RunSQL` names a
  reverse or the module states `IRREVERSIBLE = "<reason>"`; and the commit that adds the first one
  moves `MIGRATIONS_SINCE_THE_CUTOVER`.
- **A column that moves to another table carries its data** (ADR-0007 §1). The autodetector emits the
  `RemoveField` *before* the `CreateModel`, which is an add-plus-remove that empties what it claims to
  move — hand-order it create → `RunPython` → remove, and give the `RunPython` a real reverse that a
  test actually runs. (The worked example, `usage/0031`'s move of the measurements into a child
  record, went with the cutover squash, #190.)
- **Migration numbers must not collide.** ADR-001 records a fork whose rival pricing schema carried
  colliding migration numbers on top of the live RateCard engine — never merge migrations that
  renumber onto shipped ones; rebase them to follow the current head.
