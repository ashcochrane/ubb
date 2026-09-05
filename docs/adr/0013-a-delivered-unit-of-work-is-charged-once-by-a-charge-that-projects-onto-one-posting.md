# ADR-0013: A delivered unit of work is charged once — by a Charge that projects onto one posting

**Status:** accepted
**Date:** 2026-09-03
**Decision records:** `docs/plans/2026-07-30-fixed-price-task-economics-decision.md` (#139 §2–§4) —
an agreed price replaces metered revenue, non-delivery never charges, and the charge is a
first-class record; its §4.3 named the posting discriminator by a word the registry has since
retired · `docs/plans/2026-07-30-task-lifecycle-decision.md` (#140 §2–§3) — the six states and who
writes each · `docs/plans/2026-08-03-posting-and-measurement-split-decision.md` (#165 §7.3) — a
correction is its own record projected onto the same rail, never a mutation of the original · the
slice-5 specification on #187 (§2, §9, §11–§14)
**Companion:** ADR-0010 is the same shape read from the other side — a Resolution Run's projected
adjustment is a decision record UBB does *not* act on, while the Charge is a decision record UBB
does act on, through a posting that is its projection; ADR-0007 §2 is the class every economic
column of a Charge is declared into; ADR-0012 is the declaration that decides whether a unit of work
is sold this way at all

## Context

Everything here rests on two properties of the lifecycle, and they are stated first because every
money decision below keys on them:

- **I1 — `completed` means the tenant declared delivery, and nothing else writes it.**
- **I2 — `killed` means UBB stopped the work on a spend signal, and nothing tenant-declared lands
  there.**

Before slice 5 the crash sweeper wrote `completed` and stamped a marker in metadata, so a charge
keyed on that state would have billed for work a client died in the middle of. Both sweepers now
write `expired` — *nobody ever told UBB how this ended* — and under this ADR that means delivered
work that can never be charged, which is the honest answer and a visible one. Terminal to anything
is never permitted, so neither invariant can be undone by a later write.

Given I1, the charge switch has one input: an explicit close declaring delivery. Two records could
then have been the canonical record of what that delivery is owed, and both were rejected.

- **The price pinned on the unit of work at start.** It is the *determination* — which price
  applies — and not the charge: the unit's row is mutable, it carries no currency at all, and a
  determination must be able to exist and never become a charge, which is every ending but delivery
  and is ordinary. One-to-zero-or-one, with different lifetimes.
- **A system-generated posting.** It buys every money path for free, and it was refused because a
  posting is immutable *and* undeletable, so a wrong one could never be corrected — permanent, by
  construction.

## Decision

**A first-class, immutable `Charge` is canonical. It is written once, on the winning transition into
`completed`, for both tenant postures. It projects onto exactly one posting marked `task_charge`,
and every other posting under that unit of work is `not_applicable` — never zero.**

---

### 1. Only a declared delivery earns a Charge, and it is earned once

Failed, cancelled, killed and expired produce nothing — including a unit of work that ran up real
supplier cost, where exposure is bounded by the COGS ceiling the tenant chose rather than recovered
by charging for it anyway. The write hangs off the **winning transition** (`TaskService._flip`
reports which call won) and lands in the **same transaction** as the state change. An outbox event
was not taken: a crash between the transition and the charge would lose revenue for delivered work
with nothing to replay from. The kernel does not call the charge writer and must not (ADR-001); the
composition layer puts the two together, as it already does at the start gate.

**Its idempotency key is derived from the work, never caller-supplied.** The unit of work is already
a unique identity within its tenant and customer, and a caller does not supply amounts or keys the
system can derive. Belt and braces beside that, each holding a different failure: a partial
uniqueness on the charge table (`uq_charge_one_original_per_unit_of_work`) makes a second original
charge a database error rather than a double charge — the guard that would hold if two closes ever
both won their own read; and the projected posting takes this row's key, so the posting table's own
uniqueness refuses a second projection of one charge.

A replay of the close reports **the original's** `charge_created` beside `replayed: true` — a
retrying caller asking *did my close bill this?* must not be told `false` for work that was charged.
A close contradicting the state the unit is in is refused with 409 naming the real state; a delivery
declared on killed work must never answer 200, because under a Charge that is silent revenue loss
whose first symptom is a month-end number, and letting the late delivery win would make ignoring the
stop signal free.

### 2. What the Charge carries, and that none of it moves

The unit of work, the amount, **its own currency**, the line that answered and the book version that
held it, the resolution instant and the charge instant, the derived key, and the ten Grouping Field
values the work carried. The book version is pinned at start beside the amount and the line and
copied off the row, because a Pricing Book's counter steps on every publish and reading it at close
would record the version the book has reached *since*.

**Dated at delivery**, so delivered work is always billable. Dating back to the start would keep
cost and revenue in one period, but a unit starting at 23:58 on the 31st and closing after the
month's push had claimed the period would become unbillable for delivered work — a failure in the
worst direction. The accepted consequence is that a unit crossing a month boundary has its cost
in the earlier period and its revenue in the later one; the start instant on the row is what keeps
unit-level margin exact regardless.

**Every economic column is FROZEN** (ADR-0007 §2) and a `BEFORE UPDATE` trigger
(`trg_charge_declared_transitions`) holds all of them across `save()`, `QuerySet.update()` and raw
SQL. One rule answering for that many columns diffs the old row against the new over a named set and
**names the columns that moved**, so *something refused this* stays evidence on a table that will
carry a second mechanism one day. **A correction is a compensating record, never an edit**: another
row of the same table naming the one it corrects, carrying the negation and its own reason, so the
original still says what UBB originally charged — the property an edit destroys. A correction of a
correction is refused, and an original is never negative.

### 3. The Charge projects onto exactly one posting

The posting carries `kind = task_charge`, the amount as customer revenue, a supplier cost of zero
that is **settled** rather than `NULL` (there is nothing to resolve; the supplier work the unit
really burned is on the metered postings beside it), no measurement record at all, no Event Type
and no provider, the Grouping Fields the Charge froze, and the instant delivery was declared.

Three reasons it is a projection and not *a posting with a flag*, each a property of the tree:

1. **Re-derivability.** A wrong posting can be rebuilt from the Charge it came from; a wrong
   canonical event would be permanent.
2. **The platform-fee effect is explicit.** UBB's own fee is a percentage of the period total every
   metered posting accumulates into, and the projection reaches it by the same route — so *is
   fixed-price revenue inside UBB's fee basis?* has one answer, and it is measured on the basis
   rather than inferred from the fee formula.
3. **Catalogue compatibility.** The row says what it is in its own column instead of impersonating
   a tenant Event Type, which would be unrecognised at the catalogue and quarantined.

Grouping Field inheritance is what makes this nearly free: the ten slots already reach every posting
from its unit of work, so *margin by region* nets this revenue against the same unit's COGS in the
same bucket with no new code and no second analytics path.

**The money key is preserved rather than replaced.** The posting's id is the exactly-once key every
money path already uses, and that is sound because the chain *unit of work → Charge → posting →
deduction* is 1:1 at every hop; the amount-mismatch guard on the drawdown still fires. **A posting
is born one kind or the other and is never converted**: `Posting.kind` is FROZEN, held by a fourth
trigger on `ubb_posting`, because re-pointing it would move a whole row between the two populations
every kind-filtered read separates with every amount still correct and both totals wrong.
`posting_kind()` is the one function that answers the kind, and `measurements_status` reads it
first — a charge posting is `not_applicable`, never `pruned`, which would tell an end customer that
detail was removed on schedule when there never was any.

**A compensating Charge is refused at the projection, as a named residual.** The rails act only on
a positive billed amount, so a negative posting would look like a reversal and move nothing;
correcting a charge on the rails needs a refund path rather than a negative posting, and
`charge_service.compensate` has no route either, because a correction needs an operator surface and
a record of who acted. Nobody owns that path yet, and the refusal is loud so a later ticket has to
delete an assertion that says why not.

### 4. It fires for a tenant that does not bill through UBB too

Map constraint 2 has two realizations, and a slice that built one had built half. For a tenant that
bills through UBB the Charge is a real billable record like any other; for one that meters only it
is a **recorded revenue and margin fact** — the projection is what puts that number where the
margin report reads it, and nothing is collected. **No gate in the repository can ask for this
half**, because no gate can tell a correct declaration from a wrong one, which is why it has its own
test class in each of the three modules below and why the charge writer lives in `pricing` rather
than `billing`: a module inside a product a metering-only tenant does not have could not produce the
first realization at all.

### 5. The postings under a fixed-price unit of work are not applicable, never zero

Every metered posting under a unit of work sold at one agreed price carries `pricing_status =
not_applicable` with `not_applicable_reason = fixed_task_pricing`: the customer revenue for those
events is the agreed price, and none of it is theirs. The price ladder is not consulted for such an
event at all; the cost side resolves exactly as it does under any other regime. **Zero is refused
at the database** — `ck_posting_pricing_status_agrees_with_the_price` admits four combinations of
status, amount and reason and refuses the other twelve, `not_applicable` beside an amount of `0`
among them — so *never zero* is a property of the table rather than a convention.

**A finer declared quantity multiplies these postings rather than zero-revenue ones.** Sixty
per-minute postings under a fixed-price unit are sixty cost-only postings, sixty receipts and sixty
retention obligations, every one of them `not_applicable`; for a fine-grained tenant this becomes
the most common pricing status in the system, and the unit's own count of unpriced events counts
none of them.

**Posture wins the tie.** A tenant that does not bill through UBB records `tenant_not_billing` on
those postings even though, since §4, the Charge the more specific value would point at does exist.
The reason answers *why no customer revenue arises*, and for that tenant none does anywhere, for a
reason unrelated to how the work was sold — so `fixed_task_pricing` would send a reader to look for
a bill nobody raises, while now being half true, which is worse than plainly wrong. The regime
decides the status; the posture only decides the reason.

**The receipt whose subject is the Charge** names no `pricing_method` on either amount — the price
was agreed, not derived, and there is no supplier behind a Charge — carries the regime by value so a
reader can tell *agreed* from *somebody forgot to record how it was derived*, and names the Charge
as its subject rather than the posting it is stored on. **The price was promised; the cost is
observed**: a unit's revenue is pinned at start and every supplier cost under it resolves at its own
posting's instant, so one unit's revenue and its COGS resolve against different instants, which
looks like a defect on a single receipt without that sentence.

---

## What proves it

Every rule above is behavioural and every one is asserted, most of them through the route a tenant
actually calls. The premise is asserted in the kernel; the money is asserted in metering and at the
database.

| Rule | Test |
|---|---|
| Premise — `completed` is written only by an explicit close, `killed` only by UBB, both sweepers write `expired`, and terminal to anything is never permitted | `ubb-platform/apps/platform/work/tests/test_lifecycle_states.py` — `CompletedMeansTheTenantDeclaredDeliveryTest` (including `test_no_writer_in_this_service_reaches_it_but_the_close`), `KilledMeansUbbStoppedItOnASpendSignalTest`, `BothSweepersWriteExpiredTest`, `TerminalToAnythingIsNeverPermittedTest` |
| §1 — one close declaring delivery earns one Charge; a second identical close earns nothing and reports the original's answer; per-event work and contained work are charged nothing | `ubb-platform/api/v1/tests/test_a_delivered_unit_of_work_is_charged_once.py` — `test_a_close_declaring_delivery_creates_one_charge`, `test_a_second_identical_close_creates_no_second_charge`, `test_a_replay_reports_the_answer_the_original_gave`, `test_work_sold_per_event_is_charged_nothing`, `test_contained_work_under_a_priced_parent_is_charged_nothing` |
| §1 — no other ending charges, even one that burned real supplier cost; a contradicting close is refused and charges nothing | same module — `test_a_declared_failure_charges_nothing`, `test_a_declared_cancellation_charges_nothing`, `test_work_ubb_killed_on_its_ceiling_charges_nothing`, `test_work_nobody_ever_explained_charges_nothing`, `test_a_failure_that_burned_real_supplier_cost_still_charges_nothing`, `test_a_delivery_declared_on_killed_work_is_refused_and_charges_nothing`; and `ubb-platform/api/v1/tests/test_task_lifecycle_endpoints.py` — `test_a_delivery_declared_on_a_unit_ubb_killed_is_refused`, `test_no_outcome_can_close_a_unit_ubb_stopped` |
| §1 — a second original charge for one unit of work is a database error, which is what would hold if two closes both won their own read; a correction is not refused by that rule; the derived key is unique within the tenant and two tenants never collide | `ubb-platform/apps/metering/pricing/tests/test_a_charge_is_written_once_and_never_edited.py` — `ExactlyOneOriginalChargePerPieceOfWorkTest` |
| §2 — what the Charge carries: its own currency, the line and the book version that answered rather than the one in force now, both instants, a key derived from the work, the Grouping Field snapshot; dated at delivery, and a month boundary still nets its own margin | charged-once module — `test_the_charge_carries_its_own_currency`, `test_the_charge_names_the_line_that_answered_and_its_book_version`, `test_the_book_version_is_the_one_that_answered_not_the_one_in_force_now`, `test_the_charge_carries_both_instants`, `test_the_idempotency_key_is_derived_from_the_work`, `test_the_charge_snapshots_the_grouping_values_the_work_carried`, `test_the_charge_is_dated_at_delivery_and_not_at_the_start`, `test_work_crossing_a_month_boundary_still_nets_its_own_margin` |
| §2 — every economic column is frozen through every door and the rule names what moved; a correction is a compensating record and the original still says what UBB charged; the declaration is what the database defends | written-once module — `EveryEconomicColumnOfAChargeIsFrozenTest`, `ACorrectionIsACompensatingRecordTest`, `TheDeclarationIsWhatTheDatabaseDefendsTest` |
| §3 — one posting, every field named above, and no other ending projects anything | `ubb-platform/api/v1/tests/test_the_charge_reaches_the_rails_as_one_marked_posting.py` — `test_a_delivered_priced_unit_of_work_produces_one_charge_posting`, `test_the_posting_carries_the_amount_as_customer_revenue`, `test_the_posting_carries_a_settled_supplier_cost_of_nothing`, `test_the_posting_has_no_measurement_record_at_all`, `test_the_posting_names_no_event_type_and_no_provider`, `test_the_posting_inherits_the_grouping_values_the_work_carried`, `test_no_other_ending_projects_anything` |
| §3 — the one function answers `task_charge` and a metered posting beside it still reads as metered; a charge posting is not applicable rather than pruned, and the status is derived with no column storing it | projection module — `test_a_charge_posting_reads_as_a_charge_through_the_one_function`, `test_a_metered_posting_beside_it_still_reads_as_metered`, `test_a_charge_posting_is_not_applicable_rather_than_pruned`; and `ubb-platform/api/v1/tests/test_the_postings_under_an_agreed_price_are_not_applicable.py` — `test_a_charge_posting_reads_as_not_applicable`, `test_the_status_is_derived_and_no_column_stores_it` |
| §3 — the platform fee is charged on the projection, measured on the basis; the posting's id is still the money key, a replay debits nothing further, and a duplicate projection is a database error | projection module — `test_the_fee_basis_moves_by_the_agreed_price`, `test_the_basis_holds_both_kinds_and_the_projection_is_one_of_them`, `test_the_wallet_is_debited_once_under_the_postings_own_id`, `test_replaying_the_handler_debits_nothing_further`, `test_a_duplicate_projection_is_a_database_error` |
| §3 — a posting is born one kind and never converted, the closed set is held at the database, and the rule is the fourth trigger on the table | `ubb-platform/apps/metering/usage/tests/test_a_postings_kind_is_settled_at_birth.py` — `AKindIsNeverConvertedTest`, `TheClosedSetIsHeldAtTheDatabaseTest`, `TheRuleIsHeldByAFourthTriggerOnThisTableTest` |
| §3 — a compensating charge is refused at the projection, and the rails would have ignored it | projection module — `test_a_correction_is_refused_at_the_projection`, `test_the_rails_would_have_ignored_it_anyway` |
| §4 — a tenant that does not bill through UBB is charged with no wallet in sight, the charge is a record rather than a collection, the projection is written, the revenue reaches the margin report, and nothing is collected | charged-once module — `test_a_delivered_piece_of_work_is_charged_with_no_wallet_in_sight`, `test_the_charge_is_a_record_rather_than_a_collection`; projection module — `test_the_projection_is_written_with_no_wallet_in_sight`, `test_the_revenue_reaches_the_margin_report`, `test_nothing_is_collected_for_it` |
| §5 — not applicable and never zero; cost-only; per-event work unaffected; the reason is the one slice 4 coined; no price rule is consulted; a fine grain multiplies these; the unit counts none as unpriced | not-applicable module — `test_a_metered_posting_carries_no_customer_price_at_all`, `test_it_is_not_a_zero_and_the_database_is_what_says_so` (the end-to-end reading: `None`, not `0`), `test_the_supplier_work_is_still_costed`, `test_work_priced_per_event_is_unaffected`, `test_the_reason_is_the_one_slice_4_coined_for_this_case`, `test_no_price_rule_is_consulted_at_all`, `test_a_finely_declared_quantity_multiplies_these_and_not_zeroes`, `test_the_piece_of_work_counts_none_of_them_as_unpriced` |
| §5 — the database is what refuses a zero beside `not_applicable`: the whole sixteen-combination space, four admitted and twelve refused by name, on `INSERT` and as literal SQL | `ubb-platform/apps/metering/usage/tests/test_a_price_ubb_cannot_resolve_stops_being_zero.py` — `EveryIllegalCombinationIsRefusedByTheDatabaseTest`: `test_the_twelve_illegal_combinations_are_each_refused`, `test_the_derived_set_is_the_whole_space_minus_the_legal_four`, `test_an_illegal_combination_written_as_literal_sql_is_refused`, and the control `test_the_orm_can_insert_a_legal_combination` |
| §5 — posture wins the tie, and the Charge the other reason would point at does exist | not-applicable module — `test_the_posture_reason_is_recorded_and_not_the_regimes`, `test_the_charge_the_more_specific_reason_would_point_at_does_exist`; the rule on its own, over all four combinations: `ubb-platform/apps/metering/pricing/tests/test_why_a_price_does_not_apply.py` — `test_the_reason_recorded_for_each_combination`, `test_posture_beats_the_jobs_regime_where_they_disagree` |
| §5 — the receipt whose subject is the Charge: subject, no method, regime by value, no supplier work and no measured quantity, a valid receipt | not-applicable module — `test_the_projection_carries_a_receipt_whose_subject_is_the_charge`, `test_the_subject_is_the_charge_and_not_the_row_it_is_stored_on`, `test_the_price_is_the_agreed_one_and_names_no_method`, `test_it_carries_the_regime_by_value`, `test_it_records_no_supplier_work_and_no_measured_quantity`, `test_the_stored_record_is_a_valid_receipt` |
| §5 — the price was promised and the cost is observed | `ubb-platform/api/v1/tests/test_an_agreed_price_is_pinned_before_the_work_runs.py` — `test_costs_float_while_the_agreed_price_stays_at_the_start_instant` |
| Consequence — a charge posting never inflates a unit's event count; monetary totals include both kinds | `ubb-platform/api/v1/tests/test_the_kind_discriminator_pins.py` — `test_delivering_priced_work_leaves_the_event_count_where_it_was`, `test_the_revenue_total_holds_the_agreed_price_and_the_metered_sale`, `test_the_margin_nets_the_agreed_price_against_the_work_it_cost` |

## Consequences

- **What counts a charge posting and what does not is decided by the economic field each measure
  is about.** It is real revenue, so every monetary total includes it or a tenant under-reports what
  they sold; it is not a reported event, so every count of events excludes it or a per-event average
  gains a denominator nobody billed. Those are G14's pins 2 and 4, written by slice 5; pins 1 and 3
  — the `recorded_events` measure, and the provider and measurement analytics excluding
  `task_charge` — are **slice 7's**, and the manifest row is owed to slice 7 with them.
- **A compensating Charge has no path to the rails and no route.** Correcting a charge that has
  already been drawn down needs a refund path and an operator surface. Nobody owns that yet, and §3
  says so rather than leaving it to be discovered.
- **The month-boundary skew is accepted.** Cost in the earlier period, revenue in the later one,
  bounded by the absolute deadline; unit-level margin stays exact because the Charge carries the
  start instant.
- **Two values the registry published before anything could produce them are now reachable** —
  `measurements_status.not_applicable` and `pricing_receipt_subject_type.charge`. Neither was ever a
  ledger debt: both shipped whole because a closed set may not publish two values now and a third
  later, and what was missing was only the mechanism.
- **For a fine-grained tenant `not_applicable` is the most common pricing status in the system.**
  Every surface that renders a price has to render that state as a reason and never as an amount,
  which is the console's obligation and not this ADR's.
