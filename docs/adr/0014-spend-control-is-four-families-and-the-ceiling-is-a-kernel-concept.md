# ADR-0014: Spend control is four families, each in its home — and the Ceiling is a kernel concept

**Status:** accepted
**Date:** 2026-09-14
**Decision records:** `docs/plans/2026-08-01-spend-limits-decision.md` (#150 §2, §7, §11–§12, §15) —
the four families, at-or-above, the pool's mode-independence, the cap's deletion, all kept ·
`docs/plans/2026-08-03-vocabulary-lock-decision.md` (#154 §3.4) — the families' nouns and the
fields' names, kept **except the two time bounds' spellings, which this ADR supersedes** ·
`docs/plans/2026-07-30-task-lifecycle-placement-decision.md` (#141 §4.4, §4.5, §6.2, §6.4, §7) —
the placement this ADR records as built · `docs/plans/2026-07-30-fixed-price-task-economics-decision.md`
(#139 §4.1) — the prepaid reservation, built unchanged · `docs/plans/2026-08-03-analytics-realignment-decision.md`
(#153 §14) — the two reports' names and shapes · the slice-6 specification on #188 (§1–§6, §13–§15,
§21), where every ruling below was argued before it was built
**Supersedes:** #154 §3.4's table row for the Ceiling family's concrete fields — *"One unit of
work | **Ceiling** | `task_cogs_ceiling_micros` · `task_silence_ceiling_seconds` ·
`task_duration_ceiling_seconds`"* — for the two time bounds only. The first of the three was built
as named (#453); the other two keep the names slice 5 published, and §3 says why. Everything else
in #154 §3.4 stands.
**Companion:** `docs/architecture/2026-06-12-adr-001-product-boundaries.md` is the import rule the
one channel in §1 obeys; ADR-0011 §1 is why the money-shaped half of a start is conditioned inside
the call and why a root prefix carries no product gate — the reasoning the reports inherit in §5;
ADR-0006 §5 is the payload the family and the control ride on; ADR-0007 §3 is the rule that makes
§3's departure the right call; ADR-0013 is the Charge the pool counts once

## Context

Until slice 6, one word named four different things — a bound on one unit of work, a bound on a
customer's charges over a period, a wallet floor, and a rate of new work — and #154 §3.4 removed it
from the field vocabulary for exactly that reason. What the tree did with those four was never
decided in one place. The unit's bound was compared in three implementations that disagreed at the
line (strict in the recording lane, at-or-above in the patrol and the analytics count). Its two
tenant-default rungs sat on billing's risk row although #141 §6.2 and §7 had moved them to the
kernel and no slice had done it. The customer-wide stop was one word for two controls, told apart
by the owner's tenant billing mode. The per-minute bound on new work ran inside billing's money
verdict, which the composition layer asks only where a tenant has a wallet — so a tenant that does
not bill through UBB had no bound on admission at all, the opposite of what #141 §4.5 lists as
universal, and asking the advisory question consumed the allowance it asked about. The prepaid
reservation #139 §4.1 decided was unbuilt and unowned, with a column waiting for it. And the two
reports #153 §14 named did not exist, while the report they replace coalesced an absent cost to
zero money.

Each of those is a placement question, and a placement is hard to reverse: a control built for one
posture, a predicate that lives in one product, a name on a published route. This is the record.

## Decision

**Spend control is four families. Each lives where its subject lives, the pure predicates live in
the kernel's shared package, and a billing-side control reaches a kernel-state kill through the one
channel the patrol already used. The Ceiling's two time bounds keep the names slice 5 published.
The prepaid reservation is Wallet policy and its release travels by hook. The two reports live at
their own root prefix.**

---

### 1. Four families, and where each lives

| Family | `control_family` | Home | What lives there |
|---|---|---|---|
| **Ceiling** | `ceiling` | **kernel** | the declaration on the kind of work (a figure or `uncapped: true`, one and never neither or both — a CHECK); the pin on the unit; the compare in the work service; the assessment derived on the row; **the two tenant-default rungs on the tenant model**, beside the tenant's silence and deadline rungs, having left billing's risk row (#453) |
| **Customer spend pool** | `customer_spend_pool` | **billing** | the pool row (renamed, #456), its two counters at two declared levels, its crossing, the threshold event; the kill through the kernel's `TaskService.kill_and_announce` (#459) |
| **Wallet policy** | `wallet_policy` | **billing** | the two floors on the customer's billing profile and the tenant's billing configuration, resolved in billing's read contract; the signal ledger; the reservation (§4) |
| **Admission control** | `admission_control` | **kernel** | a bound on how fast work may enter is a property of the unit of work's admission, consulted by the composition layer for **every** tenant, after the claim and before the money; its one setting moved to the tenant row with it (#462). It says nothing about supplier cost and is never spend protection; a close is never subject to it |

**The one channel.** A billing-side control that must stop kernel-state work — the pool — imports
`TaskService.kill_and_announce` and passes the reason, the mechanism (`pool_crossing`) and the
control's id, exactly as the patrol does (ADR-001 rule 1: a product imports the kernel). **The
kernel never asks billing anything** (rule 2). No new cross-product channel was created and the
ADR-001 matrix did not grow. `control_family` is stamped by the kernel from the one reason→family
map in `core/controls.py` — derivable, because the unit's COGS ceiling and both time bounds are the
Ceiling's, the pool's reason is the pool's, the hard floor's is the Wallet policy's, and a cascade
inherits its parent's — while `control_id` is passed by the caller, because for a pool or a floor
it is a billing row the kernel cannot know. Billing's signal ledger keys its lines by the same
four-value column, so the two sides cannot disagree about which control a word names.

**One refusal vocabulary.** The start's refusals are the registry's `affordability_reason`,
produced by constant from `core.vocabulary` on both sides of the boundary — two by the kernel's
work service (the shape of the work), three by the kernel's admission check (the rate and the two
standings), the rest by billing's money verdict — and the advisory question is a read at the Read
floor, `GET /billing/customers/{id}/affordability`, that registers nothing and consumes no
admission (#463).

**What is deliberately not here.** The per-owner cap on work already running is deleted, not
narrowed and not moved (#455, #150 §12.5): it bounded a count of work already running, which
converts to no amount of money, and its existence invited the belief that UBB closes a blind window
it cannot see into.

### 2. The Ceiling is a kernel concept, and its predicates live in the shared package

A unit of work is a kernel concept (ADR-0011); a bound on one is too, and a tenant that does not
bill through UBB still gets it. The pure predicates — the floor's, the pool's stop line, the
ceiling's compare and the four-way `ceiling_status` derivation — are one module with no ORM and no
Redis, `core/crossing.py`, importable by kernel and product alike, and the work service, the
patrol, the utilisation query and the pool service all import it (#452). Three consequences that
are the point:

- **At or above, everywhere.** The line itself stops. A known total at the ceiling is
  `ceiling_reached`, whatever remains unresolved, and no later resolution softens it (#150 §4,
  #158 §12.3).
- **The assessment is derived on the row and never stored** (ADR-0006 R4): `not_applicable`,
  `ceiling_reached`, `indeterminate`, `within_ceiling`, from three columns the row already holds,
  through the same predicate the crossing uses; the query form and the property agree by test.
- **Declaring a ceiling is the opt-in.** The compare, the kill, the ack's verdict and the patrol's
  sweep run for every tenant whatever its enforcement switch says (#150 §11.2); the switch governs
  the customer-wide family only.

### 3. The two time bounds keep slice 5's names — a departure from #154 §3.4

#154 §3.4, resolved in `docs/plans/2026-08-03-vocabulary-lock-decision.md`, gave the Ceiling family
three concrete fields, and its row reads, verbatim:

> One unit of work | **Ceiling** | `task_cogs_ceiling_micros` · `task_silence_ceiling_seconds` ·
> `task_duration_ceiling_seconds`

The first is built as named: the supplier-cost ceiling is `task_cogs_ceiling_micros` on the
declaration and, on ADR-0012's precedent of one concept at two scopes, the same name on the unit
(#453); the strings it replaced spelled retired words and were the exact strings #153 §18 called a
naming debt. **The other two are not built as named, and this is the departure.** The fact #154
lacked when it was written: **slice 5 published the two time bounds before this slice ran** — as
`silence_window_seconds` and `absolute_deadline_seconds` on the declaration routes (#412), with the
tenant's rungs beside them. ADR-0007 §3 refuses to break a published name a second time to repair a
first, and ADR-0011's Consequences say the programme means it: a rename now would spend a break on
a spelling. The registry's `ceiling_basis: time` still describes both — a basis is a property of the
concept, not a substring of a column — and neither spells a retired word. Their stops are
`silence_window` and `absolute_deadline`, the latter coined by the registry in slice 6 (#457) to
replace this backend's own spelling, and both carry `control_family: ceiling` with
`ceiling_basis: time` (#458). A reader holding #154 §3.4 beside this ADR reads the row's first
field as built and its second and third as superseded here.

### 4. The prepaid reservation is Wallet policy, and its release travels by hook

What #139 §4.1 decided is built unchanged (#461): at a prepaid customer's start of a kind of work
sold at one agreed price, a durable reservation row keyed on the unit is written for the pinned
price, in the start's own transaction and under the owner's billing lock; **affordability is
`balance − open reservations`**, tested against the tenant's own hard and soft floors and never a
new threshold; prepaid only, by decision; event-priced work reserves nothing. It is a wallet WRITE
at a start and it lands in the billing service the composition layer already calls for the money
verdict — not in billing's read contract, whose write-shaped holds #141 §6.4 said must not be
widened.

**The release travels kernel → billing by a platform hook, never by a kernel import.** Every
terminal transition — delivered, failed, cancelled, killed, expired, and each of the three cascades
— is a kernel state change, and the kernel may not call billing. So the kernel gained a
terminal-transition listener registry on the seat-roster precedent (channel 4 of `CLAUDE.md`'s
list; #460), synchronous and inside the flip's own transaction, **a notification and never a veto**
(#141 §6.4): a listener runs under its own savepoint and an exception is caught and logged rather
than allowed to roll a kernel fact back on a product's bug. Billing registers the release in
`WalletsConfig.ready()`, and an hourly sweep releases whatever a failed listener left behind. The
delivered close releases on the hook and the Charge's drawdown lands shortly after through the
outbox — the same brief window every metered event has between recording and drawdown.

### 5. The two reports live at their own prefix

Stops and breaches and Utilisation and headroom are two reads at `/api/v1/spend-controls/`, **no
product gate**, on ADR-0011 §1's reasoning: a unit of work's stops mean something for every
tenant, and a family a tenant lacks returns no rows (#465). Both responses are typed rows — the
report they replaced was a `list[dict]`, which is why a console reader once coalesced an absent
cost to zero money — and neither coerces a null to zero: an indeterminate ceiling is never a
breach, a pool row is explained by the Charge that crossed it and that Charge's posting, and the
aggregate utilisation is computed per unit and then across every unit, with the indeterminate
count published beside it. Slice 7 inherits both unchanged (#153 §8.3 keeps them outside its
one-query collapse).

---

## What proves it

Every rule above is behavioural except §3, which is documentary — what holds it is this file and
the frozen row quoted in it; the tests beside §3 hold that the published names are the ones this
ADR says they are. Where a test asserts less than the sentence beside it, the row says so.

| Rule | Test |
|---|---|
| §1 — the kernel stamps the family from the one map, a cascade names no family of its own, and admission control maps from no reason | `ubb-platform/core/tests/test_controls.py` — `test_the_units_own_ceiling_and_both_time_bounds_are_the_ceilings`, `test_the_pools_stop_is_the_pools_and_the_floors_is_the_wallet_policys`, `test_a_cascades_reason_names_no_family_of_its_own`, `test_admission_control_stops_nothing_and_so_no_reason_maps_to_it` |
| §1 — the flip records the family and the id beside the cause; the cascade copies the parent's | `ubb-platform/apps/platform/work/tests/test_a_stop_names_the_control_that_fired.py` — `test_a_kill_records_family_and_id_beside_the_cause`, `test_the_cascade_copies_the_parents_family_and_id`, `test_a_cascades_word_passed_to_a_flip_directly_is_refused` |
| §1 — through the routes, the pool names the pool row, the floor names the row that carried it, and a ceiling stop names the declaration | `ubb-platform/api/v1/tests/test_every_stop_names_the_control_that_fired.py` — `test_the_pool_names_the_pool_row`, `test_the_wallet_floor_names_the_row_that_carried_it`, `test_a_cogs_ceiling_stop_under_a_declared_kind`, `test_contained_work_killed_with_its_parent_records_the_parents_family_and_id` |
| §1 — the pool's stop reaches `killed` through the kernel's channel, for prepaid as for postpaid (one case run under both postures), at two declared levels, counting each Charge once | `ubb-platform/apps/billing/gating/tests/test_a_blocking_pool_stops_prepaid_work_as_it_stops_postpaid.py` — `test_a_blocking_pool_stops_active_work_and_refuses_the_next_start`, `test_the_tenant_default_reaches_a_seat_and_never_a_business`, `test_the_business_level_stops_every_seats_work_and_refuses_each`, `test_a_delivered_fixed_price_unit_moves_its_pool_by_its_agreed_price_once` |
| §1 — the signal ledger keys by family and line, holds the four families by reference, and the flag lifts only when every line has cleared | `ubb-platform/apps/billing/gating/tests/test_stop_signal_ledger.py` — `test_one_row_per_line_at_the_database`, `test_the_ledger_holds_the_four_families_by_reference`, `test_the_stop_flag_lifts_only_when_both_lines_have_cleared` |
| §1 — admission control runs for a tenant with a wallet regime and for one that does not bill through UBB (the same cases run under both), a close is never subject to it, and the rate answers before the standing — the *before the money* ordering is held only as this observable word order, not as a call order | `ubb-platform/api/v1/tests/test_admission_control_runs_for_every_start.py` — `test_a_new_top_level_start_over_the_window_is_a_429_with_the_retry_information`, `test_a_close_is_never_subject_to_it`, `test_a_usage_report_is_always_accepted`, `test_a_customer_both_stopped_and_over_the_rate_is_told_about_the_rate_first` |
| §1 — the rate bound left billing's risk row for the tenant row, and the migration says why | `ubb-platform/apps/billing/gating/tests/test_the_rate_bound_leaves_the_risk_row.py` — `test_a_bound_travels_at_its_figure`, `test_the_migration_carries_then_removes_and_says_why` |
| §1 — every refusal a start answers with is one registry vocabulary, by constant identity, from both sides of the boundary | `ubb-platform/api/v1/tests/test_a_start_is_refused_from_one_vocabulary.py` — `test_by_the_wallet`, `test_by_the_pool`, `test_by_the_throttle`, `test_by_the_shape_of_the_work`, `test_by_the_customers_standing` |
| §1 — the affordability question answers at the Read floor, registers nothing and consumes no admission | `ubb-platform/api/v1/tests/test_the_affordability_question.py` — `test_it_answers_at_the_read_floor`, `test_it_registers_nothing`, `test_asking_twice_moves_no_admission_window`, `test_available_is_the_balance_less_open_reservations` |
| §1 — work already running never refuses a start (eleven consecutive starts admitted where the deleted column's default was ten); no test names the column's absence, the migration `gating/0012` removed it and the sweep is what holds its word gone | `ubb-platform/api/v1/tests/test_a_start_claims_its_key.py` — `test_work_already_running_never_refuses_a_start` |
| §2 — no production module compares the two columns outside the one permitted site (an AST walk; it proves no second compare exists, not that each lane calls the predicate) | `ubb-platform/apps/platform/tests/test_the_ceiling_is_compared_in_one_place.py` — `test_the_ceiling_is_compared_only_where_the_predicate_lives`, `test_the_gate_reads_both_columns_off_the_model`, `test_the_walk_sees_each_spelling_it_was_built_against` |
| §2 — at or above, and the four answers | `ubb-platform/core/tests/test_crossing.py` — `test_at_or_above_the_line_is_reached`, `test_no_ceiling_is_never_reached`, `test_known_at_or_above_is_reached_whatever_remains_unresolved`, `test_known_below_with_something_unresolved_is_indeterminate`, `test_known_below_with_nothing_unresolved_is_within`, `test_every_answer_is_one_of_the_registrys_four` |
| §2 — the assessment is derived on the row (the query form selects exactly the rows the property calls reached); *never stored* is held by there being no column for a reader to find, and no test names the column's absence | `ubb-platform/apps/platform/work/tests/test_models.py` — `TheRowAssessesItsOwnCeilingTest`: `test_the_query_form_selects_exactly_the_rows_the_property_calls_reached`, `test_the_model_holds_the_registrys_whole_set_by_reference` |
| §2 — the recording lane stops exactly on the line and not one under; the ack and the unit read carry the assessment | `ubb-platform/apps/platform/work/tests/test_services.py` — `test_accumulate_cost_exactly_on_the_ceiling_is_a_crossing`, `test_accumulate_cost_one_under_the_ceiling_is_not_a_crossing`; `ubb-platform/api/v1/tests/test_one_rule_pins.py` — `test_known_at_the_ceiling_is_reached_and_stopped_whatever_remains_unresolved`, `test_the_unit_read_carries_the_same_assessment` |
| §2 — declaring is the opt-in: an `off` tenant's ceiling is repaired by the patrol's beat and nothing else of the beat runs for it | `ubb-platform/apps/billing/gating/tests/test_patrol_pins.py` — `test_an_off_tenants_ceiling_is_repaired_by_the_beat_and_nothing_else_is`, `test_a_crashed_ceiling_kill_on_an_off_tenant_is_retried_by_the_beat` |
| §2 — a declaration states a figure or `uncapped`, one and never neither or both, at the database | `ubb-platform/apps/platform/work/tests/test_a_kind_of_work_declares_its_ceiling_or_declares_itself_uncapped.py` — `test_an_insert_stating_neither_is_refused_at_the_database`, `test_an_insert_stating_both_is_refused_at_the_database`, `test_a_figure_becomes_uncapped_when_both_columns_move_together` |
| §2 — the two default rungs are on the tenant model and absent from billing's risk row, and reach only work with no declared kind | `ubb-platform/api/v1/tests/test_one_rule_pins.py` — `test_retired_config_fields_are_gone`, `test_the_tenant_default_applies_absent_an_explicit_ceiling`, `test_a_declared_kind_ignores_the_tenant_default_entirely` |
| §3 — the declaration route's field set is pinned whole (nine fields; this ADR names four of them) and carries the two time bounds under these names; the bounds are declared on the kind of work and resolved on the same ladder; their stops are words the registry knows, carried as the Ceiling's on the `time` basis | `ubb-platform/api/v1/tests/test_task_type_registry.py` — `test_the_declaration_carries_exactly_these_fields`; `ubb-platform/apps/platform/work/tests/test_the_windows_belong_to_the_kind_of_work.py` — `test_the_declared_kind_of_work_wins`, `test_a_kind_of_work_may_declare_that_it_has_no_silence_window`, `test_a_kind_of_work_cannot_declare_a_zero_deadline`, `test_the_silence_windows_stop_is_a_word_the_registry_knows`, `test_the_deadlines_stop_is_a_word_the_registry_knows`; `ubb-platform/api/v1/tests/test_every_stop_names_the_control_that_fired.py` — `test_a_silence_window_stop`, `test_an_absolute_deadline_stop` |
| §4 — one reservation row for the pinned price; a start that would leave the available amount past a floor is refused and rolled back whole; event-priced and postpaid starts reserve nothing | `ubb-platform/api/v1/tests/test_a_prepaid_start_reserves_the_agreed_price.py` — `test_one_reservation_row_for_the_pinned_price`, `test_a_start_that_would_leave_available_past_the_hard_floor_is_refused`, `test_the_refused_start_is_rolled_back_whole`, `test_a_top_level_start_that_would_leave_available_past_the_soft_floor_is_refused`, `test_an_event_priced_start_reserves_nothing`, `test_a_postpaid_start_of_a_fixed_price_kind_reserves_nothing` |
| §4 — every terminal path releases it, the backstop repairs what a failed listener left | `ubb-platform/api/v1/tests/test_every_terminal_path_releases_the_reservation.py` — `test_a_declared_delivery`, `test_a_declared_failure`, `test_a_declared_cancellation`, `test_the_recording_lanes_kill`, `test_the_pools_kill`, `test_the_patrols_kill`, `test_an_expiry_on_the_silence_window`, `test_an_expiry_on_the_absolute_deadline`, `test_the_crash_sweepers_unannounced_expiry`, `test_a_close_withdraws_the_contained_work`, `test_a_kill_reaches_down`, `test_an_expiry_reaches_down`, `test_a_listener_that_failed_is_repaired_by_the_sweep` |
| §4 — by hook and never a veto: billing's release is registered at app ready, a raising listener un-terminates nothing, a database error leaves the transaction usable, and every function that writes a terminal status notifies | `ubb-platform/apps/platform/work/tests/test_every_terminal_path_reaches_the_listeners.py` — `test_billings_reservation_release_is_registered_at_app_ready`, `test_an_exception_does_not_un_terminate_the_unit`, `test_a_database_error_leaves_the_transaction_usable`, `test_every_function_that_writes_a_status_notifies` |
| §4 — under concurrency, exactly as many starts succeed as the balance affords | `ubb-platform/api/v1/tests/test_concurrent_prepaid_starts_reserve_only_what_the_balance_affords.py` — `test_three_starts_against_a_balance_that_affords_two`, `test_the_control_three_starts_against_a_balance_that_affords_three` |
| §5 — both reads answer at the prefix for a tenant that does not bill through UBB, a billing tenant, and a tenant that does not meter, while the gated report beside them refuses the last | `ubb-platform/api/v1/tests/test_spend_control_reports.py` — `test_a_metering_only_tenant_gets_ceiling_rows_and_empty_money_families`, `test_a_billing_tenant_reaches_both`, `test_a_tenant_that_does_not_meter_reaches_both_while_the_gated_report_refuses_it` |
| §5 — an indeterminate ceiling is never a breach, a pool row is explained by its Charge and that Charge's posting, the aggregate is per unit then across every unit, a null is never coerced to zero, and the window is bounded and echoed | same module — `test_an_indeterminate_ceiling_is_never_a_breach_and_an_expiry_is_neither`, `test_a_pool_row_is_explained_by_its_charge_and_that_charges_posting`, `test_the_average_is_per_unit_then_across_every_unit`, `test_a_null_is_never_coerced_to_zero`, `test_the_window_is_bounded_and_echoed` |

## Consequences

- **A control is built for every posture it reaches, or it is not built.** Three of this slice's
  rulings extend a mechanism to a posture it never served — the pool's stop to prepaid, admission
  control to a tenant without a wallet regime, the release across every terminal path including
  each cascade — and every gate stays green on a slice that builds each for the old posture alone.
  The proof rows above run the same cases under both postures for that reason, and a later control
  is held to the same shape.
- **The placement is spent.** A later slice that wants a family somewhere else, or a predicate
  back inside a product, is asking to re-open a placement three decision documents and this ADR
  agree on; the compare lives in `core/crossing.py` and nowhere else, and the walker in §2's first
  row is what turns that sentence into a red test.
- **The departure in §3 is the second the programme has recorded** (ADR-0011's from #141 §3 was
  the first), and both have the same shape: a frozen document decided a name before the surface
  existed, a slice published a different one, and the later slice keeps the published name rather
  than break it twice. The ratchet's rule — name the frozen file, quote the row, state the evidence
  — is held by `tests/contracts/test_adr_proof_tables.py`.
- **What this slice did not build, named so its absence is not read as a decision**: a
  compensating Charge's path to the rails, which must decrement the pool it compensates on both
  counters and in the durable basis (#472, stated at the pool service until then); and the
  console's word for the enforcement-mode posture and the tenant's revenue posture, which slice 8
  owns.
