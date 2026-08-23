# ADR-0009: A correction to a price is a further publish — the pricing diary never rewrites

**Status:** accepted
**Date:** 2026-08-23
**Decision record:** `docs/plans/2026-07-31-pricing-versions-decision.md` (#148) — the frozen evidence
and the versioning model this ADR keeps, except for its §6.5, which it replaces
**Amends:** #148 §6.5, whose cancellation mechanism this ADR rules unavailable, and #148's
one-pending-publish limit, which it lifts (§4)
**Companion:** ADR-0007 §2 owns *what a column may become*; this ADR is what that rule turns out to
mean for the one column a tenant most wants to take back

## Context

A tenant schedules a price change for a date and then changes their mind. The pricing-versions
decision wrote the obvious mechanism: **delete the rule versions whose effective moment is still in
the future, and reopen their predecessors** by clearing the `valid_to` that the scheduled publish
stamped on them.

That mechanism is not available, and the reason is a rule this repository had already adopted for
other reasons. `Rate.valid_to` is declared `SET_ONCE` — `NULL` to a value, once — and ADR-0007 §2
puts declared classes in the database rather than in a `save()` guard, so the refusal holds through
`QuerySet.update()` and raw SQL alike. Reopening a closed rule is a value-to-`NULL` write. The
trigger refuses it, and it has no way to ask the question that would make an exception safe: whether
the period that rule priced has already been reported.

So the decision was forced, and it was taken with two alternatives in front of it. **Both look
strictly better until you read the argument**, which is the reason this ADR exists rather than a
comment on the trigger. Neither is a bad idea; each is a good idea whose cost lands somewhere the
proposer is not looking.

## Decision

**A change of mind about a scheduled price is expressed as a further publish. Nothing is deleted and
no row is reopened.**

```
publish P1, effective T     rule A closed at T        (NULL -> value, once)
                            rule B opens  at T

the tenant reverses:
publish P2, effective T     rule B closed at T        (NULL -> value, once)
                            rule A' opens at T        (a NEW version of A's rule)
```

Every write is an `INSERT` or a once-only `NULL`-to-value close. No forbidden transition occurs.
Rule B's window `[T, T)` is empty, so it resolves for **no instant at all** — which is correct,
because it never took effect.

---

### 1. Re-deciding the column's mutability class was rejected, and here is what it costs

The proposal: make `valid_to` mutable, or carve a reopen-shaped exception into the trigger.

**What it costs is not the trigger. It is the two unique constraints that are partial on that
column.** `Rate` guarantees one active rule per identity per book with
`uq_rate_active_in_pricing_book` and `uq_rate_active_in_cost_book`, each conditioned on
`valid_to IS NULL`. That condition is what makes the guarantee a database fact: two rules cannot
both be live for the same quantity and selectors in the same book, because the index will not hold
two such rows.

A `valid_to` that may return to `NULL` is a `valid_to` that can put a second row back into the
partial index. The collision is then refused — but by an index the reopening code has to *know* it
must not collide with, which is to say the guarantee has moved from "the database will not allow it"
to "the service must get it right". **On a money-shaped constraint, that is the wrong direction of
travel**, and it is the direction ADR-0007 §2 was written to stop.

There is a second cost, smaller and more immediate: the trigger cannot distinguish a reopen that is
safe from one that is not, because *safe* means "the period this rule priced has not been reported
yet" and no such fact is on the row. An exception with no available predicate is an exception that
has to be granted unconditionally.

### 2. Deriving the boundary rather than storing it was rejected, and here is what it costs

The proposal: drop `valid_to` and compute each rule's end from the next version's `valid_from`.
Cancellation then becomes an ordinary `DELETE` of the pending row, because there is nothing to
reopen.

**Two costs, and the first is the same one.** A derived end cannot be a column, so it cannot be a
condition on a unique index; the "one active rule per identity per book" guarantee stops being an
index and becomes a service check. That is the §1 cost arrived at by a different road.

**The second is the hot path.** With a stored end, resolving a price at an instant is a range
predicate a partial index answers directly. With a derived end, "which version was live at `T`" is
*the latest version whose start is at or before `T` within its lineage* — a window function or a
correlated subquery, per lineage, on the path every recorded event runs through. #148's own model
put the boundary on the row precisely so that reading it would be cheap; deriving it trades a write
that happens when a tenant changes a price for a read that happens on every call.

### 3. The record is what makes this more than a workaround

Delete-and-reopen does not merely violate a constraint. **It erases the fact that the decision was
ever made.** After a cancellation-by-deletion, the book looks exactly as though the tenant had never
scheduled anything, and an auditor asking *who put this price in force, and who took it back* has
nothing to read.

A further publish leaves both acts on the record, each with its actor, its instant and its effective
instant, on `PricingBookPublish` rows that a trigger freezes **once published** — a draft is still an
intention and may change, but the moment it becomes the act that moved a price it stops being
editable, through `save()`, `QuerySet.update()` and raw SQL alike. That is not a consolation prize
for the mechanism being unavailable — it is the better outcome, and it is the reason this ADR states
the rule affirmatively rather than as a limitation.

**A Pricing Receipt written before the schedule survives it**, for the same reason. A receipt points
at the rule version it used; delete-and-reopen would destroy the row that pointer names. Under this
rule the pointed-at rule still exists and is still closed at the same instant, so a receipt written
last month still reproduces the amount it was written for.

### 4. Two consequences that follow from this rule and are part of it

- **The one-pending-publish limit is lifted.** #148 imposed it to avoid an ambiguity — which of two
  outstanding changes a cancellation cancels — and that ambiguity was a property of
  cancellation-by-deletion. With cancellation expressed as a further publish there is nothing
  ambiguous about a series: each publish closes what is live at its own effective instant. What
  replaces the limit is a narrower rule: **a publish is effective at or after the book's own latest
  scheduled boundary.** At it is accepted, which is exactly what makes the reversal above legal;
  before it is refused with a named code.
- **The forward horizon is a platform constant, not a tenant setting** —
  `core.scheduling.MAX_FORWARD_SCHEDULING_DAYS`, 366 rather than 365 so that a contract dated *"the
  same day next year"* fits across a leap year.

---

## What proves it

Every rule above except §2 is behavioural and every one of those is asserted, in
`ubb-platform/apps/metering/pricing/tests/test_a_scheduled_publish_is_reversed_by_a_further_publish.py`.
§2 is the exception and it is accounted for below the table rather than left to be noticed. The
classes map onto the sections:

| Rule | Test |
|---|---|
| A cancellation is a further publish, and the writes are an insert and a once-only close | `ACancellationIsAFurtherPublishTest` — `test_the_reversal_wrote_one_insert_and_one_null_to_value_close` |
| The reversed rule answers at no instant | `test_the_reversed_rules_window_is_empty`, `test_the_empty_window_resolves_for_no_instant` |
| §1 — the database is what refuses the rejected mechanism | `test_no_row_is_reopened_and_the_database_is_what_refuses_it`, and `TheDatabaseRefusesTheEarlierCaseRegardlessTest`, which drives the write #148 §6.5 would have made and measures the refusal rather than asserting it |
| §3 — the record is complete | `TheHistoryIsCompleteTest` — both publishes, with their actors and instants, **from the records alone** |
| §3 — a receipt written before the schedule survives | `AReceiptWrittenBeforeTheScheduleSurvivesTest` |
| §4 — a series composes, and the limit is gone | `ASeriesOfScheduledPublishesComposesTest` |
| §4 — at or after the latest boundary | `APublishSitsAtOrAfterTheBooksLatestBoundaryTest` |
| §4 — the horizon is a constant, and 366 is not an accident | `ubb-platform/core/tests/test_scheduling.py` |

**§2 is the one rule here that no test asserts, and that is stated rather than left to be noticed.**
It is a decision about a shape the tree does not have: there is no derived-boundary implementation
to drive, and a test that asserted `valid_to` exists would pass for reasons unrelated to the
argument. What holds §2 is this document. A future proposal to derive the boundary is a design
review, not a red test — which is precisely why the argument had to leave the ticket it was made in.

## Consequences

- **Undoing a scheduled change costs a second publish, not a delete.** A change and its reversal are
  two records where delete-and-reopen would have left none; change their mind again and it is three.
  Anything that lists a book's history therefore shows the reversals, which is the record being
  honest about what happened rather than clutter to be filtered out.
- **A discarded draft remains the cheap path.** A draft writes no rule and closes nothing, so a
  change of mind *before* publishing costs nothing at all and reaches none of the above. Most
  changes of mind should end there, and the surface is shaped to make that the default.
- **An empty window is a real state a reader may meet.** A rule version with `valid_from == valid_to`
  exists, resolves for nothing, and is not a defect. Anything that lists rule versions has to render
  it without claiming it was ever in force.
- **§1's argument binds any future partial index on a mutability-declared column.** The general form
  is: a unique constraint conditioned on a column's `NULL`-ness makes that column's declared class
  load-bearing for the constraint, not just for the column. Relaxing the class silently relaxes the
  constraint.
