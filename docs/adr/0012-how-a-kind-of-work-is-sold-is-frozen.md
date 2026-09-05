# ADR-0012: How a kind of work is sold is frozen — a change is a retirement and a new declaration

**Status:** accepted
**Date:** 2026-09-03
**Decision records:** `docs/plans/2026-07-30-fixed-price-task-economics-decision.md` (#139 §2) —
what an agreed price means, kept whole · `docs/plans/2026-08-02-charging-modes-decision.md` (#151
§17–§18) — the refusal code, the open question this ADR closes, and the parent/child rule that
document called *"the weakest enforcement in the document and it guards a money-shaped rule"* ·
`docs/plans/2026-08-04-code-builder-inputs-decision.md` (#156 §14.2) — which narrowed the question
and deliberately left it open · the slice-5 specification on #187 (§9–§10), where the ruling is
argued
**Companion:** ADR-0007 §2 owns the mutability classes this ADR declares into; ADR-0009 is the other
place a tenant most wants to take a declaration back, and reaches the same answer by a different
road — a further record, never an edit; ADR-0011 is where the registry this declaration lives on is
mounted, and why

## Context

A kind of work declares how it is sold: `pricing_mode` is `event_priced` — each event priced as it
arrives — or `fixed` — one agreed price for the whole delivered unit of work. `fixed` **replaces**
metered revenue for that unit; it is not a fee on top and not a floor, markup never applies to it,
the cost side is entirely unchanged, and it prices a whole unit of work only. The regime is declared
on the kind of work and **snapshotted onto each unit of work at start**.

#151 §18 left one thing open about it: *"Nothing decides how a Task Type's [pricing regime] may
change over time. … flipping a live kind of work from `event_priced` to `fixed` changes the revenue
shape of every future job of that kind with no effective-dating and no publish record. #148 gave
pricing rules a publish; this declaration has nothing equivalent."* (The bracketed words carry the
registry's spelling for the field name that document used, and the ellipsis stands for a sentence
about retire-never-delete that §1 below takes up.) #156 §14.2 sharpened it: Event Types now have a
publish and Task Types still do not, and **whether that is one mechanism generalised or two is
undecided**.

Three shapes were available: a publish record for the declaration (the Pricing Book's shape), a
draft-and-published state (the Event Type's shape), or a mutability class with the database behind
it.

## Decision

**`TaskType.pricing_mode` is declared FROZEN under ADR-0007 §2 — no transition after insert,
enforced by the database. Changing how a kind of work is sold means retiring that kind of work and
declaring a replacement. No third publish mechanism is minted.**

---

### 1. Why frozen, and not a publish record

Four reasons, in order of weight.

1. **The risk a publish record addresses is already addressed twice over.** The regime is
   snapshotted onto the unit of work at start, so no in-flight or historical unit can change. What
   remains is *future* work of that kind — and retire-and-redeclare gives that a record for free:
   two rows, each with its own retirement instant, which is exactly the *when did this change, and
   to what* a publish record exists to answer.
2. **ADR-0007 §2 requires every column to be declared into exactly one mutability class, with the
   database enforcing it** — *"never asserted in a docstring"*. FROZEN is the class that fits. A
   publish record is an application-level convention over a mutable column, and the ADR's whole
   point is that this is the weaker instrument.
3. **#156 §14.2's question is genuinely open and this slice cannot honestly close it.** Minting a
   third publish shape here would answer *"one mechanism generalised, or two?"* by shipping a
   third — a public surface the programme may later fold into whichever answer it gives, which is
   exactly the provisional public shape ADR-0007 §3 refuses, because repairing it would cost a
   second break of a published name.
4. **It matches the write floor already in place.** The declaration surface is Admin-only
   throughout, on the ruling that a declaration decides how usage is costed and is therefore a
   pricing-rule change. Freezing the money-shaped half of that declaration is consistent, not novel.

Retirement had to be built, because it did not exist: `retired_at` had been on the model since the
registry's first migration with no writer anywhere, so the path this ruling leans on was
unreachable. Retire, never delete (inherited from #138): the row stays readable because work already
done under it still refers to it, and the instant is stamped only when the state actually changes,
so re-sending an already-retired declaration does not slide its retirement forward.

### 2. What the database keeps, and what the route adds

A `BEFORE UPDATE` trigger on `ubb_task_type` (`trg_task_type_declared_transitions`, installed by
`work/migrations/0021_a_kind_of_work_declares_how_it_is_sold.py`) refuses any statement that moves
the column, whichever door the write came through — `save()`, `QuerySet.update()`, raw SQL. Its
`WHEN` clause is load-bearing rather than an optimisation: the registry's write surface is an
idempotent whole-collection `PUT` that writes every column on every call, so a rule that fired on
equal values would refuse a tenant re-sending the declaration it already made.

The route answers `409 pricing_mode_frozen` — its own code and its own status, because the request
is well formed and what refuses it is the state of a row that already exists, and because the route
already answers `validation_error` for two unrelated things. That answer is the **courtesy, not the
enforcement**: deleting it leaves the trigger refusing the move and three cases answering 500 rather
than 409. It is raised inside the transaction, so a body declaring three new kinds of work and
re-selling a fourth does not half-apply.

**Saying nothing about the regime is not declaring per-event.** Omitting the field on a declaration
that already exists leaves the regime alone; a *new* declaration that names none is `event_priced`,
the column's own default, because every declaration made before the field existed was made when
per-event was the only regime there was. A client written before the field existed would otherwise
re-sell every `fixed` kind of work per event on its next `PUT`, be refused by the frozen rule for a
word it never used, and be locked out of ever revising that kind of work's ceiling or windows again.

### 3. Contained work is sold the way its container is

Contained work inherits its parent's regime, and a start naming a kind of work that disagrees is
refused. The invariant compares **two rows**, so no column `CHECK` can express it, and it is a rule
about who may be *born*: a `BEFORE INSERT` trigger on `ubb_task`
(`trg_task_containment_shares_the_pricing_regime`) refuses the row before it exists, through the
three doors a row is born by — `objects.create()`, a bare `save()`, and an `INSERT` around the ORM.
`TaskService.create_task` holds the same rule first, so a caller gets a refusal that carries both
regimes as attributes and names the containing one in its sentence, instead of an `IntegrityError`.

What a mixed tree would cost, and why the rule refuses both directions: a per-event step under a
parent sold at one agreed price adds metered revenue to a unit whose revenue that price was supposed
to *replace*; an agreed-price step under a per-event parent puts revenue at a level nothing reports
at. Either way the answer is a number nobody can explain.

Two refusals sit beside this one at the start and are this ADR's to record. **Only a whole unit of
work carries an agreed price** — a work-level price line written against a contained kind of work
refuses the start with `fixed_task_price_on_contained_work`, unconditionally, because it is a
mistake in the tenant's own book whatever they bill. **A `fixed` kind of work with no resolvable
price refuses the start** with `fixed_task_price_unresolved` — and for a tenant that does not bill
through UBB *that* refusal is inert: the declaration is recorded, a price that does resolve is still
pinned so their margin reporting has a revenue number, and the refusal becomes live the day they
enable billing. That is the posture trap #151 §18 named, and the console says so beside the control
rather than leaving the tenant to discover it on their end customer's work.

### 4. What this ADR does not decide

Whether the Pricing Book Publish and the Event Type's draft-and-published state are one mechanism
or two. That stays #156 §14.2's, untouched: slice 5 did not need to answer it in order to close
#151 §18, and this ADR records that it did not.

---

## What proves it

Every rule above is behavioural and every one is asserted — at the database through every door,
and at the route a tenant calls.

| Rule | Test |
|---|---|
| §2 — the database refuses a regime change through every door, in both directions, even when it rides along with a permitted change; a re-declaration of the same regime is free; everything else about a kind of work still moves | `ubb-platform/apps/platform/work/tests/test_a_kind_of_work_declares_how_it_is_sold.py` — `TheRegimeIsFrozenTest`: `test_per_event_cannot_become_one_agreed_price`, `test_one_agreed_price_cannot_become_per_event`, `test_the_regime_cannot_ride_along_with_a_permitted_change`, `test_re_declaring_the_same_regime_is_not_a_change`, and the control `test_everything_else_about_a_kind_of_work_still_moves` |
| §2 — the declaration and the rule are one claim, under the name this ADR addresses | same module — `TheRegimeIsDeclaredIntoATransitionClassTest`: `test_the_column_declares_frozen`, `test_the_database_defends_what_the_model_declares`, `test_the_rule_is_installed_under_the_name_this_module_addresses` |
| §2 — the route's 409, and a refused change leaves the rest of the body unwritten | `ubb-platform/api/v1/tests/test_task_type_registry.py` — `test_changing_how_a_kind_of_work_is_sold_is_refused`, `test_a_refused_regime_change_leaves_the_rest_of_the_body_unwritten` |
| §2 — saying nothing is not declaring per-event | same module — `test_omitting_the_regime_keeps_it_rather_than_re_selling_per_event`, `test_a_new_kind_of_work_that_names_no_regime_is_event_priced` |
| §1 — retire-and-redeclare leaves both rows readable, and a retirement instant never slides | same module — `test_retiring_and_declaring_a_replacement_leaves_both_rows`, `test_a_retired_kind_of_work_is_still_readable`, `test_re_retiring_does_not_move_the_instant` |
| §1 and §4 — no third publish mechanism: exactly two operations, exactly these fields | same module — `test_the_registry_publishes_exactly_two_operations`, `test_the_declaration_carries_exactly_these_fields` |
| §3 — a mixed tree cannot be born, through every door, in either direction, and no row survives the refusal; the rule admits what it should; the service's refusal carries both regimes and names the containing one; gutting the rule is measured rather than argued | `ubb-platform/apps/platform/work/tests/test_containment_shares_the_pricing_regime.py` — `TheDatabaseRefusesAMixedTreeTest`, `TheRuleAdmitsEverythingItShouldTest`, `TheServiceGivesTheRefusalASentenceTest`, `AGreenBoardOverAGuttedRuleIsMeasuredRatherThanArguedTest` |
| §3 — over the wire: a differing regime is refused naming both; only a whole unit carries a price; a priced kind with no price refuses the start; and for a tenant that does not bill the unresolved refusal is inert until they enable billing while the contained-work refusal is live all the same | `ubb-platform/api/v1/tests/test_an_agreed_price_is_pinned_before_the_work_runs.py` — `test_a_differing_regime_is_refused_and_names_both`, `test_a_line_against_a_contained_kind_of_work_is_refused`, `test_the_start_is_refused_with_the_named_code`, `test_enabling_billing_turns_the_declaration_into_a_refusal`, `test_the_contained_work_refusal_is_live_for_them_all_the_same` |

## Consequences

- **A tenant who mis-declares creates a new key, and a key change is an integration change for
  them.** Stated rather than hidden, and said in the console at declaration time, beside the
  control (#423), rather than at the moment the tenant discovers the field is read-only.
- **A listing of a tenant's kinds of work shows the retired ones**, each with the instant it stopped
  being offered. That is the history a publish record would otherwise have held, and it is not
  clutter to be filtered out.
- **For a tenant that does not bill through UBB the two regimes are behaviourally identical at the
  start gate**, and the declaration is inert — until they enable billing. What the regime does for
  them anyway is ADR-0013 §4's: a delivered unit of work sold at one agreed price still produces a
  Charge, as a recorded revenue and margin fact.
- **The declaration's three bounds stay mutable by design.** The COGS ceiling, the silence window
  and the absolute deadline are revised in place; a rule that froze the whole declaration would be a
  worse defect than the one this ADR stops, which is why the frozen test module's control case
  exists.
