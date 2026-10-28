# ADR-0025: A report window is inclusive calendar dates read as one half-open interval, a measurement is released once by a daily prune, and an end customer reads its own usage

**Status:** accepted
**Date:** 2026-10-28
**Decision records:** #190 spec part 2 (W5) · the owner's rulings of 2026-10-28 on slice 8's window W5,
§0.3 points 1–17 and amendments §0.4 A–E · #190 comment `5785029955` (the measurement number and who
runs the prune) · #514's ruling (no pagination; consecutive windows) · #561's ruling (restore the
widget summary)
**Amends:** #165 §4 (`docs/plans/2026-08-03-posting-and-measurement-split-decision.md`) — *"UPDATE
never — no column of a measurement record is ever rewritten"* and *"The child needs no transition
classes, because it has no lifecycle"*. One column now has one: `prunable_at` is written once, by the
daily prune, in the same transaction that deletes the record. The evidence is ruling 8 and the delete
rule #354 installed: a record may go only at or after its `prunable_at`, the decision left that
column with *"no decision gives it a value"*, and #190 then chose an automatic daily job. A release
written at the moment of deletion is a FACT about the record, not a deadline stamped on it, so the
section's reason — no scheduled `UPDATE` against durable data — still holds of every other column,
and of the posting entirely.
**Companion:** ADR-0007 §2 (a column's class is enforced at the database) · ADR-0020 §6 (an amount
left out of a total moves it either way) · ADR-0023 (USD only) · ADR-0024 §2 (a closed value set has
one authority)

## Context

Five report routes take a pair of calendar dates, and before W5 they disagreed three ways: what
`end_date` means (inclusive on the economic query, the task analytics and the referral earnings,
exclusive on the two margin routes), what a lone date does (honoured, silently dropped, or an unbounded
read at the Read floor), and what no date means (the month to date, or all of history). No route's
description said which.

The API already published a shorter measurement horizon beside the six-year economic one, but nothing
enforced it: `prunable_at` was NULL on every record, nothing wrote it, and the published horizon was the
economic one because no clock ran. #190 ruled the number (400 days) and the job (automatic and daily).

The widget mount lost the end customer's usage summary when #501 collapsed nine reports into the one
economic query on the tenant mount. And the SDK handed back models whose `to_dict()` raised, because
`from_wire` turned every omitted field into `None` whatever its type.

## Decision

### 1. One calendar-date report window, converted once

Every report taking a pair of calendar dates resolves it through `core/report_windows.py`: both dates
inclusive, in UTC; a lone start runs to today and a lone end starts on the first of its own month;
none is the current UTC month to date; at most 366 calendar dates (92 for an hourly economic
question); a window that runs backwards is refused. The inclusive dates are converted ONCE, in
`ReportWindow.between`, to the half-open UTC interval `[start 00:00, (end + 1 day) 00:00)`, and every
query reads that interval — none adds its own day (amendment A). One description fragment states the
rule on every route, including that longer history is read through consecutive, non-overlapping
windows. The spend-control `since`/`until` and the pricing filters' `selected_*` are windows of
instants and stay out of scope (ruling 5); they say so on their own routes.

### 2. The measurement horizon is 400 days, a setting, and never silently six years

`UBB_MEASUREMENT_RETENTION_DAYS` defaults to 400 and the environment may override it. A settings
module that does not state it is refused rather than answered with the economic horizon. The
published `measurement_data_available_from` is the guaranteed current edge of fine detail — not the
literal oldest row, and not a promise of detailed year-over-year comparison.

### 3. A measurement is released once, by the prune, and deleted with its release

`PostingMeasurement.prunable_at` is SET_ONCE (`usage/0052`): NULL to an instant that has come, once,
through every door. The daily prune (`apps/metering/usage/pruning.py`) selects records older than the
CURRENT horizon — by event and by recording — whose postings are neither unresolved nor unknown,
filtering protected records in the query so that the `usage/0041` trigger is the backstop and never the
filter, and so that an old unresolved record never starves younger ones. Each batch's release, stamped
with the transaction's own clock, and its delete are one transaction. Bounded by
`PRUNE_BATCH_SIZE` (1,000) and `PRUNE_RUN_CAP` (100,000), and observable through one structured line per
run, a zero run included. A failed run is never reported as completed (the owner's review of #621):
the line is `measurement_prune.completed` only for a run that finished, and `measurement_prune.failed`,
at error, for one stopped by anything — counting only the batches that committed, with the skipped
count and the backlog null — and the error is raised on unchanged. The failed batch released and
deleted nothing, so the next run finishes the rest with nothing released or deleted twice.
`ix_measurement_recorded_at` serves the walk; its skipped count reads that
index alone and never joins the posting. Nothing here resolves a cost or a price (amendment B), and the
economic posting is never touched.

### 4. An end customer reads its own usage through a type the widget mount owns

`GET /me/economics` answers a widget token over the one economic query with `customer_revenue` and
`recorded_events` only, the basis and currency they are stated in, and the foreign-currency count. The
schema is the mount's own (amendment D), so nothing added to the tenant answer reaches it; the route
takes no customer parameter, a business reads its own usage without its seats', and the metering
product gates it.

### 5. An omitted SDK field is `None` only where its type admits null

`from_wire` normalises by the declared type at every depth: an omitted nullable field reads `None`, an
omitted non-nullable field stays `UNSET`, and a stated value — falsy or not — is never touched.

### 6. A public field's `enum` is what that field can return

The registry owns a closed concept's tokens; a field owns which of them it can return (the owner's
review of #621). A field that returns only part of its concept names that part with `a_field_of`
(`core/field_values.py`): the registry's generated constants, the concept marker kept, and
`x-ubb-field-values` beside it. The export (`tools/known_values/apply.py`) refuses a value the
concept does not occur with, a list that is the whole set, and an open concept, then writes the
field's `enum` from the registry in the registry's order; the `Literal` makes the response refuse
any other value. This is a placement constraint, not a second vocabulary authority, and no one-value
concept is created for it. So the business rollup's and the unprofitable list's `basis` publish
`recognised` alone and `/me/economics.basis` `recorded` alone; the end customer's revenue status
publishes `known`, `incomplete` and `unavailable_outside_retention_horizon`, and its count status
`known` and `unavailable_outside_retention_horizon`.

A value NO field can return is withheld by the registry instead, on #620's reachability rule:
`measure_status.not_applicable` has no writer — the one economic query refuses a measure that does
not apply before it builds a row — so `EconomicMeasureOut.status` publishes the query's four.

## What proves it

| Rule | Test |
|---|---|
| §1 | `ubb-platform/api/v1/tests/test_a_report_window_means_one_thing.py` — `EveryReportRouteReadsItsWindowOneWayTest`, `AnHourlyQuestionKeepsTheTighterCeilingTest`, `EveryReportRoutePublishesTheOneWindowDescriptionTest` |
| §2 | `ubb-platform/core/tests/test_retention.py` — `test_a_cleared_setting_is_refused_rather_than_answered_six_years`, `test_a_settings_module_that_never_declared_it_is_refused`, `test_absent_from_the_environment_it_is_400_days` |
| §3 — the release is SET_ONCE | `ubb-platform/apps/metering/usage/tests/test_the_measurement_horizon_is_enforced_daily.py` — `TheReleaseIsSetOnceTest` |
| §3 — the prune | `ubb-platform/apps/metering/usage/tests/test_the_measurement_horizon_is_enforced_daily.py` — `ThePruneReleasesWhatTheHorizonNoLongerCoversTest`, `AnOldUnresolvedRecordNeverStarvesYoungerOnesTest`, `TheRunIsBoundedAndSaysWhatItLeftTest`, `ReleaseAndDeleteAreOneUnitTest`, `EveryRunWritesOneStructuredLineTest`, `TheJobRunsEveryDayTest` |
| §3 — a failed run is never completed | `ubb-platform/apps/metering/usage/tests/test_the_measurement_horizon_is_enforced_daily.py` — `AFailedRunIsNeverReportedAsCompletedTest` |
| §3 — the delete rule beside it | `ubb-platform/apps/metering/usage/tests/test_a_measurement_is_pruned_only_when_it_may_be.py` — `TheReleaseIsTheOnlyDefendedColumnTest` |
| §4 | `ubb-platform/api/v1/tests/test_an_end_customer_reads_its_own_usage.py` — `TheTokenIsTheOnlyScopeTest`, `ABusinessReadsOnlyItsOwnUsageTest`, `OnlyTheTwoSafeMeasuresAreShownTest`, `RevenueKeepsItsTruthTest`, `TheMeteringProductGatesItTest` |
| §5 | `ubb-sdk/tests/test_a_parsed_answer_round_trips.py` — `EveryAffectedModelRoundTripsTest`, `OmittedNullAndFalsyAreThreeFactsTest` |
| §6 — the published enums | `tests/contracts/test_openapi_known_values.py` — `test_each_narrowed_field_publishes_exactly_what_it_can_return`, `test_only_these_fields_name_their_own_values`, `test_a_fields_own_values_are_refused_unless_they_narrow_the_set` |
| §6 — the response refuses the rest | `ubb-platform/core/tests/test_field_values.py` — `test_the_boundary_refuses_a_value_of_the_concept_the_field_cannot_return` |

## Consequences

- **Meanings change where shapes do not.** The margin routes read `end_date` as inclusive and echo the
  inclusive date; a lone date is honoured where it was dropped; the task analytics default to the month
  to date; 367 calendar dates are refused. No published shape moved for them, so no breaking-change
  gate sees them; the PR and `ubb-sdk/MIGRATION.md` §24 state each.
- **A measurement older than the horizon is gone after the next run** unless its posting is still
  waiting on a cost or a price. A shortened clock takes effect at the next run; a lengthened one cannot
  bring back what was released.
- **Six response enums name fewer values, and no response changes.** `oasdiff` does not read a
  narrowed response enum, so the PR and `ubb-sdk/MIGRATION.md` §24 state it: a generated client's
  branch for a value its field could never return no longer compiles.
- **Economically neutral** (amendment E). No amount for a given canonical window and set of source
  facts moved; `PRICING_ENGINE_VERSION` stays 3.0.0.
