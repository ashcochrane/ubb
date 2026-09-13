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
// §9.4 names six scenarios and this module now holds all six by those
// names. `known_economics` is the ordinary case every existing fixture already
// is; slice 3 owns `unknown_cost` and `incomplete_total` and both arrive below;
// slice 4 owns `waived_revenue` and `pricing_not_applicable` and both are here
// too. `indeterminate_ceiling` is slice 6's: its STATE reached the wire in #452
// (`ceiling_status` on the acknowledgement and the unit read, slice 6 §3) and
// the scenario arrived with the console surface that renders it (#454, slice
// 6 §18), because a scenario with no consumer fails the reachability gate on
// the commit that adds it. It arrives as ONE composer over all four statuses
// rather than one for the indeterminate case, because the indeterminate case
// is only meaningful against the three it must render differently from — the
// measurement trio's argument, one concept over. Its second consumer arrived
// in #467: the Utilisation and headroom report composes its per-unit rows
// from the same composer, so the four statuses reach that report through the
// same amounts that fix them on the run page. The trio itself is a seventh
// the list does not name, which is the whole reason slice 2 owed a fixture at
// all.
//
// THE POOL'S STATUS PAIR arrived with #467's report as a composer inside the
// spend-controls feature's own mock, and moved here in #468 the day the
// customer's Billing tab became the second feature to render it — a fixture
// two features compose cannot live inside one of them. `spendPoolAssessment`
// takes what a pool is declared to be beside the durable pair it is measured
// over and derives the assessment the kernel derives, so no fixture on either
// surface can state a share or a refusal its own charges would not conclude.
//
// `pricing_not_applicable` IS TWO STATES RATHER THAN ONE, and it is the only
// entry on that list that is. The registry reads a `not_applicable_reason`
// under it and declares two mutually exclusive causes, so the scenario takes
// the reason as an argument and both of them are composable — see
// `priceNotApplicable` below for why fixing one would leave the other with no
// fixture for anything to render.
//
// THE RECEIPT WHOSE SUBJECT IS A CHARGE arrived in #425 (spec §29), the last
// arrival before the ceiling assessment above.
// `pricing_receipt_subject_type.charge` shipped with the value set and became
// producible by the backend in #418, when a delivered unit of work sold at one
// agreed price first projected onto a posting; until this commit nothing in
// the console composed one. `chargeReceipt` below is that composer, and it
// returns the record TOGETHER WITH the two amounts the record's totals fix,
// for the reason every scenario here returns a pair: a receipt saying the
// price was agreed at one figure beside a column saying another is a posting
// the backend cannot write.
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
  CeilingStatus,
  CostingStatus,
  MeasurementsStatus,
  NotApplicableReason,
  PricingMode,
  PricingReceiptSubjectType,
  PricingStatus,
  SpendPoolEnforceMode,
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

// ---------------------------------------------------------------------------
// `indeterminate_ceiling` — what a unit's ceiling assessment concluded, and
// the three columns it was concluded from (#454, slice 6 §3, §18).

/**
 * A unit of work's ceiling assessment, with the columns that fix it.
 *
 * SIX FIELDS TRAVEL TOGETHER because the backend derives the status rather
 * than storing it (ADR-0006 R4): `core/crossing.py` reads the pinned ceiling,
 * the known supplier total and the unresolved count off the row and concludes
 * one of the registry's four values, and the two figures beside the status are
 * computed over the KNOWN total in every evaluated state. A fixture that stated
 * a status beside totals the rule would conclude differently from would be
 * describing a row the backend cannot write — so the status is composed with
 * its terms and refused without them.
 *
 * ⚠ THE TWO FIGURES ARE NULL UNDER `not_applicable` AND A FLOOR UNDER
 * `indeterminate`. Nothing was evaluated in the first case, so there is no
 * share of anything to report; in the second the percentage can only rise and
 * the headroom only fall as unresolved costs settle. A reader that renders
 * either as a confident number — or the null as `$0.00` — has the defect this
 * module exists to make unwritable.
 */
export interface CeilingAssessmentScenario {
  readonly task_cogs_ceiling_micros: number | null;
  readonly total_provider_cost_micros: number;
  readonly unresolved_event_count: number;
  readonly ceiling_status: CeilingStatus;
  readonly ceiling_used_percentage: number | null;
  readonly ceiling_remaining_micros: number | null;
}

/** The terms an evaluated status is concluded from: a ceiling, and the total held against it. */
export interface CeilingTerms {
  readonly ceiling_micros: number;
  readonly cost: CostTotalScenario;
}

/**
 * The registry's decision rule, as `core/crossing.py::ceiling_status` applies
 * it (`spend-controls.yaml`, `ceiling_status.value_semantics`): no ceiling →
 * nothing evaluated; the known total at or over the line → reached, whatever
 * remains unresolved; below the line with something unresolved → cannot tell;
 * below with everything resolved → within. Kept beside the composer so the
 * composer can refuse a status the terms do not fix.
 */
function concludedStatus(ceiling: number | null, cost: CostTotalScenario): CeilingStatus {
  if (ceiling === null) return "not_applicable";
  if (cost.micros >= ceiling) return "ceiling_reached";
  if (cost.unresolved_event_count > 0) return "indeterminate";
  return "within_ceiling";
}

/**
 * Compose one ceiling assessment: the status a fixture means, and the terms
 * that fix it.
 *
 * The status comes FIRST and is required, on the not-applicable-reason
 * precedent (`priceNotApplicable`): a fixture says the state it means out
 * loud, rather than leaving a reader to work it out from three numbers. The
 * terms are the columns the kernel reads — under `not_applicable` there is no
 * ceiling to state, so the overload takes none; under the three evaluated
 * statuses the ceiling is required. The composer applies the registry's rule
 * to the terms and THROWS where it concludes something other than the status
 * asked for, so the contradiction fails the fixture rather than the page.
 *
 * The figures mirror the kernel's arithmetic exactly: a whole percent of the
 * ceiling the known total has used, rounded down so it never overstates and
 * running past 100 once the line is crossed; `null` for a ceiling of zero,
 * because a share of nothing is not a share (the compare still says such a
 * ceiling is reached); and headroom clamped at zero, because past the line
 * there is none and the percentage is what says by how much.
 */
export function ceilingAssessment(
  status: "not_applicable",
  terms: { readonly cost: CostTotalScenario },
): CeilingAssessmentScenario;
export function ceilingAssessment(
  status: Exclude<CeilingStatus, "not_applicable">,
  terms: CeilingTerms,
): CeilingAssessmentScenario;
export function ceilingAssessment(
  status: CeilingStatus,
  terms: { readonly ceiling_micros?: number; readonly cost: CostTotalScenario },
): CeilingAssessmentScenario {
  const ceiling = status === "not_applicable" ? null : (terms.ceiling_micros ?? null);
  const concluded = concludedStatus(ceiling, terms.cost);
  if (concluded !== status) {
    throw new Error(
      `ceilingAssessment("${status}") was handed terms the registry's rule concludes ` +
        `"${concluded}" from (ceiling ${ceiling}, known ${terms.cost.micros}, ` +
        `${terms.cost.unresolved_event_count} unresolved) — a row the backend cannot write`,
    );
  }
  const known = terms.cost.micros;
  return {
    task_cogs_ceiling_micros: ceiling,
    total_provider_cost_micros: known,
    unresolved_event_count: terms.cost.unresolved_event_count,
    ceiling_status: status,
    ceiling_used_percentage:
      ceiling === null || ceiling <= 0 ? null : Math.floor((known * 100) / ceiling),
    ceiling_remaining_micros: ceiling === null ? null : Math.max(ceiling - known, 0),
  };
}

// ---------------------------------------------------------------------------
// The customer-price total — `incomplete_total`'s price-side twin (#424).

/**
 * A total built over customer prices, and how many of them it had to skip.
 *
 * The price side of `CostTotalScenario`, and the first the console has had
 * to hold: a run's billed total (`TaskOut.total_billed_cost_micros`) arrives
 * beside `unpriced_event_count`, which counts the events whose price UBB
 * could not resolve — a `waived` price and a `not_applicable` one are NOT
 * counted, because neither is missing information. So non-zero means the
 * amount beside it is a floor, exactly as on the cost side, and a zero amount
 * beside a non-zero count is no amount at all.
 */
export interface PriceTotalScenario {
  readonly micros: number;
  readonly unpriced_event_count: number;
}

/** A billed total that left nothing out. */
export function completePriceTotal(micros: number): PriceTotalScenario {
  return { micros, unpriced_event_count: 0 };
}

/**
 * A billed total that left events out, and how many.
 *
 * Both arguments required and no default for the count, for the reason
 * `incompleteTotal` gives: a default of zero would be the silent completeness
 * claim this scenario exists to make impossible to write by accident.
 */
export function incompletePriceTotal(
  micros: number,
  unpricedEventCount: number,
): PriceTotalScenario {
  return { micros, unpriced_event_count: unpricedEventCount };
}

// ---------------------------------------------------------------------------
// The Customer Spend Pool's status pair — where one customer's known period
// charges stand against the pool that applies to them (#456 §13; composed
// here in #468, slice 6 §4, §18).

/**
 * What a pool is declared to be, and the durable basis it is measured over.
 *
 * The five declaration fields are the pool row's own; `known` is the
 * price-side total the drawdown has resolved for the period, beside the
 * count of postings it could not price — a floor wherever that count is
 * not zero, which is the whole reason the pair travels as a pair.
 */
export interface SpendPoolTerms {
  readonly period: string;
  readonly cap_micros: number;
  readonly enforce_mode: SpendPoolEnforceMode;
  readonly hard_stop_pct: number;
  readonly alert_levels: readonly number[];
  readonly known: PriceTotalScenario;
}

/**
 * The pair with the assessment the kernel derives over it — the shape the
 * status route publishes, every field required.
 *
 * ⚠ THE FOUR ASSESSED FIGURES ARE NULL OR FALSE WHERE NO POOL APPLIES, AND
 * A FLOOR WHERE THE PAIR IS. A pool with no amount is no pool, so there is
 * no share of anything to report; and where the known figure left a posting
 * unpriced, the share can only rise and the headroom only fall as it
 * resolves. A reader that renders the null as `0%` or the floor as a settled
 * number has the defect this module exists to make unwritable.
 */
export interface SpendPoolAssessmentScenario {
  readonly period: string;
  readonly cap_micros: number;
  readonly enforce_mode: SpendPoolEnforceMode;
  readonly known_period_charges_micros: number;
  readonly unresolved_posting_count: number;
  readonly used_percentage: number | null;
  readonly remaining_micros: number | null;
  readonly highest_threshold_reached: number | null;
  readonly blocking_occurred: boolean;
}

/**
 * Compose one pool's status pair, the way the kernel composes it
 * (`core.crossing.spend_pool_assessment`) over a known total that may be a
 * floor: a whole percent of the pool the known figure has used, rounded
 * down; headroom never below zero; the highest alert level the known figure
 * is at or over; and whether the start gate's own compare holds — only under
 * a blocking pool, at or over its stop line (`spend_pool_stop_line`: the
 * pool times its stop percentage, rounded down). A pool with no amount is no
 * pool — three nulls and false — as the kernel answers it.
 *
 * DERIVED, NEVER STATED. Unlike the ceiling assessment there is no status
 * word for a fixture to name and be refused on: the assessment IS the
 * arithmetic, so a fixture hands over the terms and takes what they fix. A
 * fixture cannot say a pool is untouched while its own charges say it
 * crossed, because it never gets to say either.
 */
export function spendPoolAssessment(terms: SpendPoolTerms): SpendPoolAssessmentScenario {
  const known = terms.known.micros;
  const basis = {
    period: terms.period,
    cap_micros: terms.cap_micros,
    enforce_mode: terms.enforce_mode,
    known_period_charges_micros: known,
    unresolved_posting_count: terms.known.unpriced_event_count,
  };
  if (terms.cap_micros <= 0) {
    return {
      ...basis,
      used_percentage: null,
      remaining_micros: null,
      highest_threshold_reached: null,
      blocking_occurred: false,
    };
  }
  const reached = terms.alert_levels.filter(
    (level) => known >= Math.floor((terms.cap_micros * level) / 100),
  );
  const stopLine = Math.floor((terms.cap_micros * terms.hard_stop_pct) / 100);
  return {
    ...basis,
    used_percentage: Math.floor((known * 100) / terms.cap_micros),
    remaining_micros: Math.max(terms.cap_micros - known, 0),
    highest_threshold_reached: reached.length === 0 ? null : Math.max(...reached),
    blocking_occurred: terms.enforce_mode === "blocking" && known >= stopLine,
  };
}

// ---------------------------------------------------------------------------
// The receipt whose subject is a Charge — `pricing_receipt_subject_type`'s
// second value, and the second economic state slice 5 makes reachable (#425).

/**
 * The shape a receipt written today declares — `receipts.RECEIPT_SCHEMA_VERSION`
 * on the backend. A fixture composing a record composes the current shape.
 */
export const RECEIPT_SCHEMA_VERSION = 1;

/** The engine that computed it — `pricing_service.PRICING_ENGINE_VERSION`. */
export const PRICING_ENGINE_VERSION = "2.1.0";

/**
 * The record a delivered unit of work's charge posting carries, as
 * `charge_projection.the_receipt_for` writes it. A type alias rather than an
 * interface so it stays assignable to the wire's untyped `pricing_receipt`.
 *
 * Everything that is EMPTY here is empty on purpose, and the emptiness is the
 * content: no supplier stands behind a Charge, so the costing section names no
 * method and holds no detail; the price was agreed before the work ran rather
 * than derived from anything, so the pricing section names no method either
 * and its detail carries exactly one thing — the regime that licenses that.
 * The backend refuses a charge receipt that does not say `fixed` there
 * (`receipts._validate_the_agreed_regime`), and refuses a settled amount with
 * no method on every OTHER subject: this is the one record shape where an
 * absent method is a fact rather than a hole.
 */
export type ChargeReceiptRecord = {
  readonly receipt_schema_version: typeof RECEIPT_SCHEMA_VERSION;
  readonly pricing_engine_version: string;
  readonly subject_type: Extract<PricingReceiptSubjectType, "charge">;
  /** The CHARGE's own id — never the posting the record is stored on. */
  readonly subject_id: string;
  /** When delivery was declared, which is when the revenue landed. */
  readonly effective_at: string;
  readonly currency: string;
  readonly costing: {
    readonly method: null;
    readonly status: Extract<CostingStatus, "known">;
    readonly detail: Record<string, never>;
  };
  readonly pricing: {
    readonly method: null;
    readonly status: Extract<PricingStatus, "known">;
    readonly detail: { readonly pricing_mode: Extract<PricingMode, "fixed"> };
  };
  readonly totals: {
    /** A settled nothing, never an unlearned one: no supplier is behind a Charge. */
    readonly provider_cost_micros: 0;
    readonly billed_cost_micros: number;
  };
  /**
   * Cross-reference ids and nothing else — both strings, because the book
   * version is half of an identity here (the `(line, version)` pair names the
   * one published record that answered) rather than a figure.
   */
  readonly provenance: {
    readonly agreed_price_line_id: string;
    readonly book_version: string;
  };
};

/**
 * A receipt whose subject is a Charge, and everything it fixes on the posting
 * that stores it.
 *
 * THE RECORD AND THE COLUMNS TRAVEL TOGETHER, for the reason every other
 * scenario here returns a pair: the projection writes `billed_cost_micros`
 * from the same `charge.amount_micros` the record's totals carry, a settled
 * zero beside a `known` costing status because a Charge has no supplier, and
 * the posting's own `effective_at` and `currency` from the same
 * `charged_at` and `currency` the record states. A fixture that composed the
 * record and then stated a price — or an instant, or a denomination — of its
 * own beside it would describe a posting whose receipt and whose columns
 * disagree, which is the shape the receipt exists to remove; so all of them
 * ride here and a consumer restates none.
 *
 * The receipt's method is null on BOTH sides and that rides here as a typed
 * fact, not a default: the posting's `pricing_method` is read out of the
 * record by the serialiser, so a charge posting never carries one.
 *
 * WHAT IT DOES NOT RETURN, and why. The posting's `kind` is `task_charge` and
 * its measurements are `measurementsNotApplicable()`; both are the consumer's
 * to write beside this, visibly, because the measurement state has its own
 * composer (slice 2's) and the reachability gate reads which composers a
 * consumer imports. A charge receipt on a posting calling itself
 * `metered_usage` is a payload the backend cannot produce — the mock's charge
 * builder writes the kind itself, and a test fixture states it.
 */
export interface ChargeReceiptScenario extends CustomerPriceScenario, SupplierCostScenario {
  readonly pricing_receipt: ChargeReceiptRecord;
  readonly pricing_receipt_subject_type: Extract<PricingReceiptSubjectType, "charge">;
  readonly pricing_method: null;
  /** When delivery was declared — the record's instant, and the posting's. */
  readonly effective_at: string;
  readonly currency: string;
  readonly billed_cost_micros: number;
  readonly pricing_status: Extract<PricingStatus, "known">;
  readonly not_applicable_reason: null;
  readonly provider_cost_micros: 0;
  readonly costing_status: Extract<CostingStatus, "known">;
  readonly unresolved_reason: null;
}

/**
 * The facts about one Charge that its receipt is composed from — the few a
 * projection can vary. A named shape so a fixture's seed can extend it and
 * hand itself straight to `chargeReceipt`, rather than restating six fields
 * under a second set of names.
 */
export interface ChargeTerms {
  /** The Charge the receipt explains. */
  readonly charge_id: string;
  /** The instant delivery was declared. */
  readonly charged_at: string;
  readonly currency: string;
  readonly agreed_price_micros: number;
  /** The Pricing Book line that answered, and the published version that held it. */
  readonly agreed_price_line_id: string;
  readonly book_version: number;
}

/**
 * Compose the receipt for one delivered unit of work sold at one agreed price.
 *
 * `book_version` is taken as the number the Pricing Book carries and written
 * as the string the record carries, which is what the projection does: it is
 * an identifier in the provenance section, and the section admits no other
 * leaf.
 */
export function chargeReceipt(terms: ChargeTerms): ChargeReceiptScenario {
  return {
    // The posting's two amounts, in the pairs `knownPrice(amount)` and
    // `knownCost(0)` return — spelled here with their literal types because
    // this scenario promises MORE than those two do: not merely a settled
    // price and a settled cost, but this price and a cost of exactly nothing.
    billed_cost_micros: terms.agreed_price_micros,
    pricing_status: "known",
    not_applicable_reason: null,
    provider_cost_micros: 0,
    costing_status: "known",
    unresolved_reason: null,
    pricing_method: null,
    effective_at: terms.charged_at,
    currency: terms.currency,
    pricing_receipt_subject_type: "charge",
    pricing_receipt: {
      receipt_schema_version: RECEIPT_SCHEMA_VERSION,
      pricing_engine_version: PRICING_ENGINE_VERSION,
      subject_type: "charge",
      subject_id: terms.charge_id,
      effective_at: terms.charged_at,
      currency: terms.currency,
      costing: { method: null, status: "known", detail: {} },
      pricing: { method: null, status: "known", detail: { pricing_mode: "fixed" } },
      totals: { provider_cost_micros: 0, billed_cost_micros: terms.agreed_price_micros },
      provenance: {
        agreed_price_line_id: terms.agreed_price_line_id,
        book_version: String(terms.book_version),
      },
    },
  };
}
