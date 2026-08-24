# ADR-0010: Putting a resolution right produces a projection — UBB never builds a second money path

**Status:** accepted
**Date:** 2026-08-23
**Decision records:** `docs/plans/2026-07-31-provider-supplied-cost-decision.md` (#146 §11) ·
`docs/plans/2026-07-31-markup-and-price-precedence-decision.md` (#147 §14) ·
`docs/plans/2026-07-31-pricing-versions-decision.md` (#148 §7.3, §17) ·
`docs/plans/2026-08-03-posting-and-measurement-split-decision.md` (#165 §7.3) — the four frozen
records that each describe a recovery mechanism
**Companion:** `docs/architecture/positioning.md` states the Stripe boundary; this ADR is the one
place a slice came close to crossing it, and the argument that stopped it

## Context

UBB records amounts it cannot always resolve at the time. A supplier cost may never arrive; a
customer price may have no rule behind it yet. Both leave a `NULL` beside a status that says the
field was never resolved, and both need a way to be put right later.

**Four separate decision records each described a mechanism for that, and not one of them owned
building it.** #146 §11's unresolved-cost queue. #147 §14's customer adjustment, which that document
calls *"the largest unbuilt thing this document depends on"*. #148 §7.3's remediation. #165 §7.3's
refund-and-adjustment-as-projected-decision. #148 §17 names the failure in advance: *"Three tickets
are each about to invent their own queue, actor model and authorization rule… Whoever owns the
remediation queue should own all three."*

**That shape — work described in four places and owned in none — has cost this programme twice.** It
is why this is an ADR and not four sections of a slice. The risk is not that recovery gets built
badly; it is that the fourth mechanism gets built *separately*, by someone reading one of the four
records, and that the one it most resembles is the one that moves money.

Because three of the four are the same act — completing a `NULL` beside a status that says the field
was never resolved — and **the fourth is not**. #147 §14's customer adjustment is the only one that
moves money, and both #147 §7.3 and #148 §7.3 forbid moving it automatically.

## Decision

**One mechanism and one output. A Resolution Run completes what was never resolved; its money-facing
result is a projected adjustment, and no UBB surface acts on that projection.**

---

### 1. There is one mechanism, and its scope is a construction rather than a check

A **Resolution Run** covers all three recovery paths that do not move money, because all three are
one act. Its candidate set is built from the status pairs themselves — each pair names the one status
meaning *not learned* — so a run reaches only postings whose own status says they were never
resolved.

**There is no flag to set correctly and no predicate to evaluate, and therefore no way for a run to
touch a number that already exists.** Take the selector away entirely and that property survives,
because it was never the selector doing it. This is #148 §7.4's *"a check where remediation is a
construction"*, and it is the reason a run needs no undo: it cannot overwrite an answer, only supply
a missing one.

Two rules fall out of the construction rather than being added to it:

- **`waived` is never a candidate.** It is not the pairs' unresolved status, so it is not in the set.
  A waived charge is a decision somebody made; `unknown` is information UBB does not have. What
  waiving has cost is reported as money elsewhere — a misconfiguration losing a tenant money should
  be visible as money — but it is reported, never repaired.
- **Nothing is backdated.** A run re-resolves each posting at **the posting's own instant**, so a rule
  written today does not reach a posting from July. What a run can therefore recover is narrower than
  it sounds: only configuration that carries no effective moment of its own — the markup rung, a
  Plan, an Event Type's declarations. A backdated rate is the one input that would break historical
  accuracy, and no surface accepts one.

### 2. The output is a projection, and UBB does not act on it

**A Resolution Run does not build a money-moving surface.** It produces a **projected adjustment**:
what recovering this filter would be worth, per customer, with the receipts behind it. The tenant then
acts through the money path UBB already has.

**Two arguments, and the first is the boundary this repository is built on.** Stripe owns the billing
engine — invoicing, credit notes, refunds, collection — which UBB drives as a control plane and never
reimplements. A new UBB-owned adjustment surface *is* reimplementation, and `CLAUDE.md`'s golden rule
forbids it. The second: #165 §7.3 had already ruled the shape, and it is not a money path. A
correction gets *"their own canonical decision record, projected onto the same rail — never a mutation
of the original Charge and never a direct edit of a historical total."* **A projected adjustment is
that decision record.** The unbuilt thing was the record, not a second money path.

**A projection read as an instruction is the failure mode**, so the qualification is said in the
product's own words rather than left in a comment, and it is said **twice, in two places that reach
two different readers**:

- **In the published contract**, on the operation and on its response schema — *"A projection and not
  an instruction: reading it moves no money, creates no invoice, credit note, charge or refund, and
  UBB will not bill your customer for it."* That is what a client integrating against the spec reads
  before they ever call it.
- **In the response body itself**, as a `basis` field built from
  `apps/metering/queries.py:PROJECTED_ADJUSTMENT_BASIS`. That is what travels *with* the number, to
  the reader who never opened the spec — and it is the one that survives being pasted into a
  spreadsheet.

The duplication is deliberate: a qualification that lives only in the contract is a qualification the
number can be separated from.

### 3. Who may run one, and why the floor is as high as it goes

**The ADMIN role floor**, and the argument rather than the guess — #148 §17 called `role_floor(ADMIN)`
*"the obvious guess and a guess is not a decision"*. A run writes money-adjacent numbers into closed
periods' reporting; under the receipt's sealing rule the completion is **irreversible**, and there is
no second act to undo one with; and it produces a customer-facing money figure. **Irreversible plus
money-adjacent is the highest floor UBB has.** It is recorded as a registered audit action carrying
its actor and its selector.

**A run declares a selector, and the console offers a filter rather than a button.** Not for
convenience: a tenant onboarding in August who backfills July has postings unresolved for two
different causes, and *"everything it matches"* would apply one repair to postings needing another.
The selector is three axes — a date range, a customer, an Event Type — the same axes the rule ladder
selects on. **It does not accept an arbitrary predicate**, because a predicate is exactly the check
§1's construction refuses.

### 4. A run is idempotent by construction, and no refusal may sit above it

Everything a run completes leaves the candidate set the moment it completes, so running the same
selector again reaches whatever the first run could not repair and nothing else.

**That is also why a guard may not be added above it.** Turning *"this selector has already been
run"* or *"there is nothing to do"* into an error would refuse the second call forever while every
acceptance criterion still read as satisfied. A refusal is a statement about work still to do. A run
that completes nothing answers with an outcome saying so.

---

## What proves it

| Rule | Test |
|---|---|
| §1 — membership is the status, and survives the selector being removed | `ubb-platform/apps/metering/pricing/tests/test_a_resolution_run_completes_what_was_never_resolved.py` — `MembershipIsTheStatusAndNotAFilterTest`, whose `test_a_posting_that_already_has_a_price_is_out_with_every_axis_removed` is the construction claim itself |
| §1 — `waived` is never completed, through every door | `AWaivedChargeIsNeverCompletedTest` |
| §1 — nothing is backdated, on any surface | `NoPathBackdatesARuleTest` |
| §2 — **a run moves no money** | `ARunMovesNoMoneyTest` — `test_no_invoice_charge_or_wallet_movement_results`, `test_nothing_reaches_stripe` |
| §2 — **none of the three read surfaces moves money either** | `ubb-platform/apps/metering/pricing/tests/test_what_a_recovery_would_be_worth.py` — `NoneOfTheThreeMovesMoneyTest`, including `test_the_projection_is_worth_something_so_the_absence_means_something`, which is the positive control that stops the absence being vacuous |
| §2 — the projection is the run with the writing taken out, measured rather than argued | `AProjectionIsTheRunWithTheWritingTakenOutTest` — `test_the_figure_is_what_a_run_then_actually_completes`, `test_reading_it_writes_nothing`, `test_no_run_record_is_created_by_projecting` |
| §3 — the ADMIN floor, every lower role refused at the route | `ubb-platform/api/v1/tests/test_a_resolution_run_is_executed_by_an_admin.py` — `OnlyAnAdminMayRunOneTest`, whose `test_a_refused_request_completes_nothing_and_records_nothing` is the half that stops the refusal being cosmetic |
| §3 — three axes and never a predicate | `TheSelectorIsThreeAxesAndNeverAPredicateTest` — `test_a_body_carrying_a_condition_of_its_own_is_refused`; and on the read side `TheThreeSurfacesFilterOnTheRunsOwnAxesTest` — `test_every_surface_offers_the_selectors_axes_and_no_others` |
| §4 — the second call answers an outcome, not a refusal | `RunningItTwiceIsNotAnErrorTest` — `test_the_second_call_answers_an_outcome_and_not_a_refusal`, `test_the_amount_the_first_run_wrote_is_not_touched_again` |

**Every rule in this ADR is backed by a test.** The one worth naming specifically is §2's: an
assertion that *nothing happened* is worthless without a control proving the thing under test did
anything at all, and `test_the_projection_is_worth_something_so_the_absence_means_something` is that
control. It is the reason the money claim is evidence rather than an empty query.

## Consequences

- **Recovering revenue is a two-step act with a human in the middle**, deliberately. UBB says what
  the recovery is worth and shows the receipts; a person decides whether to bill for it and does so
  through Stripe. That is slower than automatic back-billing and it is the point — #147 §7.3 and
  #148 §7.3 both forbid the automatic version.
- **A fifth recovery mechanism is now a decision that has to argue with this document.** That is the
  whole reason it exists: the failure was never a bad build, it was four descriptions and no owner.
- **The projection is a floor, and says so.** Postings it cannot value and postings beyond one pass
  are counted beside the figure rather than folded into it, so a reader is never shown a total that
  quietly excludes what it could not reach.
- **The ADMIN floor cannot be lowered without re-arguing irreversibility.** If a future change makes
  a completion reversible, the floor's argument changes and the floor may too. Until then it is the
  highest UBB has, on purpose.
