// The console's canonical economic scenarios (#155 §9.4).
//
// One definition per economic STATE, composed into feature fixtures — never a
// whole page response copied into a ninth file. §9.4's reasoning: copying page
// responses is how nine files come to describe the same state differently, and
// the existing fixtures already flag that risk where they warn that two rosters
// are kept in sync by hand.
//
// WHY THIS MODULE EXISTS AT ALL, given that TypeScript already typechecks every
// fixture. §9.1: what the types prove is that the console can RECEIVE a state.
// What nothing proves is that it tells the truth about one — and the defects
// that get this wrong are ordinary and easy to write:
//
//     const displayed = amount ?? 0;
//
// So §9.2 makes it a standing obligation: any slice introducing or changing an
// economic state owes at least one representative fixture and at least one
// rendering assertion. Slice 2 is the first slice to owe one, which is why the
// module is created here — seeded with the one subject that slice introduces,
// not with §9.4's whole list. That subject arrives as THREE functions rather
// than one because `measurements_status` is a three-way distinction and the
// pruned case is only meaningful against the other two: an assertion that a
// pruned payload does not render as zero proves little until the rendering it
// must ALSO differ from is on the page beside it.
//
// THE SHAPE IS THE POINT, and it is worth saying plainly because the obvious
// alternative looks tidier. A scenario returns the ambiguous fact and the fact
// that DISAMBIGUATES IT as one object, so a fixture cannot take half.
//
// §9.4 names six scenarios and this module now holds five of them by those
// names. `known_economics` is the ordinary case every existing fixture already
// is; slice 3 owns `unknown_cost` and `incomplete_total` and both arrive below;
// slice 4 owns `waived_revenue` and `pricing_not_applicable` and both are here
// too. `indeterminate_ceiling` is slice 7's under §9.3, arriving with the slice
// that introduces its state. The measurement trio below is a seventh the list
// does not name, which is the whole reason slice 2 owed a fixture at all.
//
// `pricing_not_applicable` IS TWO STATES RATHER THAN ONE, and it is the only
// entry on that list that is. The registry reads a `not_applicable_reason`
// under it and declares two mutually exclusive causes, so the scenario takes
// the reason as an argument and both of them are composable — see
// `priceNotApplicable` below for why fixing one would leave the other with no
// fixture for anything to render.
//
// This module is fixture material, and it sits in `lib/` because the SET spans
// features even where a single scenario does not: §9.3 puts unresolved cost on
// margin, revenue on pricing, the indeterminate ceiling on spend control and
// the incomplete aggregate on analytics. The console's imports only flow down,
// so a fixture shared across features cannot live inside one of them.
//
// NOT because `measurements_status` itself is read in several places — it is
// read on the event receipt and nowhere else today. Analytics has its own,
// SEPARATE concept, `measure_status`, and the registry spends a long comment on
// exactly this near miss: one says whether a NUMBER is knowable at the grain
// asked for, the other whether the RECORD of what was measured is still there
// to read a number from. Do not merge them here on the strength of the names.

import type {
  CostingStatus,
  MeasurementsStatus,
  NotApplicableReason,
  PricingStatus,
  UnresolvedReason,
} from "@/lib/vocabulary";

/**
 * A posting's measured quantities, and what their absence would mean.
 *
 * The two fields travel together on purpose. An empty bag is produced by two of
 * the three declared states — `pruned` (the record existed and was removed at
 * its retention horizon) and `not_applicable` (the posting's kind never had
 * one) — so the bag alone cannot say which, and a reader that guesses reports a
 * payload that expired on schedule as a confident "no usage". That is the exact
 * defect `measurements_status` was coined to end
 * (`domain-vocabulary/concepts/economics.yaml`), and returning the pair as one
 * object is how a fixture is stopped from re-opening it.
 */
export interface MeasurementScenario {
  readonly measurements: Readonly<Record<string, number>>;
  readonly measurements_status: MeasurementsStatus;
}

/**
 * A metered posting whose measurement record is present and readable.
 *
 * The ordinary case, and the one every existing fixture is. Passing quantities
 * here rather than defaulting the status beside them is what keeps the ordinary
 * case saying so out loud.
 */
export function availableMeasurements(
  quantities: Readonly<Record<string, number>>,
): MeasurementScenario {
  return { measurements: { ...quantities }, measurements_status: "available" };
}

/**
 * A metered posting whose measurement detail has passed its retention horizon.
 *
 * The scenario this slice owes. A metered posting always had a measurement
 * record written in the same transaction as itself, so the absence is a removal
 * rather than an omission — and the customer looking at it must be told that,
 * not shown a zero.
 */
export function prunedMeasurements(): MeasurementScenario {
  return { measurements: {}, measurements_status: "pruned" };
}

/**
 * A posting that was never measured — a Task sold for one agreed price.
 *
 * Its bag is empty for a reason no retention horizon ever governed, which is
 * why the registry's decision rule reads the posting's KIND before it looks for
 * a measurement record at all — a posting that never had measurements is not a
 * posting that has lost them.
 */
export function measurementsNotApplicable(): MeasurementScenario {
  return { measurements: {}, measurements_status: "not_applicable" };
}

// ---------------------------------------------------------------------------
// `unknown_cost` — one posting's supplier cost, §9.4's name, slice 3's to own.

/**
 * One posting's supplier cost, and what its absence means.
 *
 * THE THREE FIELDS TRAVEL TOGETHER because the database refuses any other
 * combination of them: `ck_posting_costing_status_agrees_with_the_cost` admits
 * exactly a resolved amount with no reason, a NULL amount with a reason, and a
 * NULL amount with neither. A fixture that set the amount without the status
 * would be describing a row that cannot exist, and the console would then be
 * tested against a state it will never be sent.
 *
 * A NULL amount is TWO states, which is the whole reason the status is here: a
 * cost UBB could not learn, and a cost there was never going to be. A reader
 * that guesses tells a tenant their supplier charged nothing.
 */
export interface SupplierCostScenario {
  readonly provider_cost_micros: number | null;
  readonly costing_status: CostingStatus;
  readonly unresolved_reason: UnresolvedReason | null;
}

/** A posting whose supplier cost UBB knows. The ordinary case. */
export function knownCost(micros: number): SupplierCostScenario {
  return {
    provider_cost_micros: micros,
    costing_status: "known",
    unresolved_reason: null,
  };
}

/**
 * A posting whose supplier cost UBB could not settle, and the input that would.
 *
 * The scenario this slice owes, and the reason it takes an argument: a status
 * saying a cost is missing without saying WHAT would settle it is a shrug
 * rather than something a tenant can act on, so there is no way to compose this
 * state without choosing one.
 */
export function unknownCost(reason: UnresolvedReason): SupplierCostScenario {
  return {
    provider_cost_micros: null,
    costing_status: "unresolved",
    unresolved_reason: reason,
  };
}

/**
 * A posting whose Event Type declares no supplier cost at all.
 *
 * Its amount is absent for a reason no Cost Rate was ever going to supply,
 * which is why it is not counted as missing from any total — nothing about it
 * is. The same argument `measurementsNotApplicable` makes one field over.
 */
export function costNotApplicable(): SupplierCostScenario {
  return {
    provider_cost_micros: null,
    costing_status: "not_applicable",
    unresolved_reason: null,
  };
}

// ---------------------------------------------------------------------------
// The CUSTOMER PRICE, which went nullable one slice after the supplier cost.

/**
 * A posting's customer price and the status that says which reading applies.
 *
 * The price half of `SupplierCostScenario` above, added by #351 for the same
 * reason and under the same rule: the column went nullable, so an amount alone
 * can no longer say what it means.
 *
 * ⚠ A NULL AMOUNT IS THREE STATES HERE, NOT TWO. `unknown` is a price UBB does
 * not have, `waived` is a charge somebody decided not to pursue, and
 * `not_applicable` is a subject that generates no customer revenue at this
 * level. A reader that guesses tells a tenant they charged nothing — and only
 * the first of the three makes a total a floor.
 *
 * ⚠ AND THE THIRD FIELD IS WHY THE COUNT IS FOUR STATES AND FIVE ANSWERS.
 * `not_applicable` does not say WHY a subject generates no revenue, and the two
 * declared causes are not the same answer: one sends the reader to the Task's
 * own charge, the other says no Charge was ever created. The registry reads the
 * reason under that status and never on its own, so it travels here for the
 * same reason `unresolved_reason` travels with a supplier cost — a status
 * saying a price does not apply without saying why sends a reader looking for a
 * number nobody wrote.
 */
export interface CustomerPriceScenario {
  readonly billed_cost_micros: number | null;
  readonly pricing_status: PricingStatus;
  readonly not_applicable_reason: NotApplicableReason | null;
}

/** A posting whose customer price is settled. The ordinary case. */
export function knownPrice(micros: number): CustomerPriceScenario {
  return {
    billed_cost_micros: micros,
    pricing_status: "known",
    not_applicable_reason: null,
  };
}

/**
 * A posting whose customer price UBB could not resolve.
 *
 * The one of the three absences that is MISSING INFORMATION, and therefore the
 * only one a completeness count is about. Takes no argument: unlike an
 * unresolved supplier cost, there is no input to name — that is what `unknown`
 * means, and the reason `not_applicable` is the state that carries a cause.
 */
export function unknownPrice(): CustomerPriceScenario {
  return {
    billed_cost_micros: null,
    pricing_status: "unknown",
    not_applicable_reason: null,
  };
}

/**
 * A charge somebody decided not to pursue.
 *
 * Shares its column shape with `unknownPrice()` exactly, which is the point of
 * having both: the difference is a decision rather than a shape, it is reported
 * as a loss rather than queued, and only the status carries it. A fixture that
 * used one for the other would be indistinguishable at every assertion about
 * the amount.
 */
export function waivedPrice(): CustomerPriceScenario {
  return {
    billed_cost_micros: null,
    pricing_status: "waived",
    not_applicable_reason: null,
  };
}

/**
 * A posting that generates no customer revenue at this level at all.
 *
 * The price-side twin of `costNotApplicable()`: absent for a reason no Pricing
 * Rule was ever going to supply, so it is not counted as missing from any
 * total — nothing about it is.
 *
 * IT TAKES THE REASON, and that is a difference from its cost-side twin rather
 * than an inconsistency with it. A supplier cost that was never going to exist
 * has ONE cause — the Event Type declares none — so there is nothing to choose.
 * A customer price has TWO, and they are not the same answer: `fixed_task_pricing`
 * says the revenue is real and sits on the Task's own charge, so LOOK AT THE
 * TASK; `tenant_not_billing` says no Charge was created anywhere for this
 * tenant, so THERE IS NOTHING TO LOOK AT. A scenario that fixed one of them
 * would leave the other with no fixture for anything to render, which is
 * precisely the gap #155 §9.2 exists to close.
 *
 * The registry reads the reason ONLY under this status, which is why it is a
 * parameter here and `null` on the other three: a cause recorded beside an
 * absence that already has one of its own is the status said twice, and the day
 * the two disagree there is no way to tell which is right.
 */
export function priceNotApplicable(
  reason: NotApplicableReason,
): CustomerPriceScenario {
  return {
    billed_cost_micros: null,
    pricing_status: "not_applicable",
    not_applicable_reason: reason,
  };
}

// ---------------------------------------------------------------------------
// `incomplete_total` — an aggregate over those postings, §9.4's other name.

/**
 * A total built over supplier costs, and how many of them it had to skip.
 *
 * The aggregate face of the state above, and a separate scenario rather than a
 * derived one because a total is not a posting: it carries a COUNT, never a
 * status, and there is no fourth value of anything to look up. Non-zero means
 * the amount beside it is a floor.
 */
export interface CostTotalScenario {
  readonly micros: number;
  readonly unresolved_event_count: number;
}

/** A total that left nothing out. */
export function completeTotal(micros: number): CostTotalScenario {
  return { micros, unresolved_event_count: 0 };
}

/**
 * A total that left events out, and how many.
 *
 * Both arguments are required, and the count has no default, because a default
 * of zero here would be the silent completeness claim this scenario exists to
 * make impossible to write by accident.
 */
export function incompleteTotal(
  micros: number,
  unresolvedEventCount: number,
): CostTotalScenario {
  return { micros, unresolved_event_count: unresolvedEventCount };
}
