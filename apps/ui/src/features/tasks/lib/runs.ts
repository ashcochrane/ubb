// A run of a kind of work, as this feature reasons about one: how the list is
// narrowed, what a run's totals may be SAID to be when some of what they total
// was never learned, what its agreed price is worth, and how a run holding
// much contained work stays readable (#424; spec §7, §8, §25).
//
// THE WORDS FOR A RUN'S STATE ARE BOUND IN `@/lib/task-status`, not here: the
// events feature renders one too, and two features cannot share a binding that
// lives inside either. The one concept only this surface renders — the reason
// a caller gave for not delivering — is bound below.
//
// NO NUMBER NOBODY KNOWS RENDERS AS A ZERO AMOUNT (#424; #155 §9.2). A run's
// totals arrive as a figure beside a COUNT of what the figure could not
// include — `incompleteTotal` and `incompletePriceTotal` in
// `@/lib/economic-scenarios` — and the count is what says whether the figure
// is a figure, a floor, or nothing at all. That is the reading
// `@/lib/supplier-cost` gives every other total in the console; what is
// different here is the THIRD outcome. Elsewhere a total whose resolved part
// sums to nothing renders as an absence; on this surface it renders as
// UNKNOWN, in a word, because the runs list puts it in a column beside real
// zeros — a run that ran nothing — and beside amounts that do not apply, and a
// column of dashes could not tell a reader which of the three they were
// looking at. All three are distinct here, and none of them is `$0.00`.

import { z } from "zod";

import { pricingStatusLabel } from "@/lib/customer-price";
import { formatMicros } from "@/lib/format";
import { labelMap } from "@/lib/localisation";
import { AT_LEAST, partialTotalNote } from "@/lib/supplier-cost";
import {
  OUTCOME_REASON_LABEL_KEYS,
  TASK_STATUS_VALUES,
  type NotApplicableReason,
} from "@/lib/vocabulary";

import type { KindOfWork, RunRow } from "../api/types";

/** The catalogue's words for why a caller said the work did not deliver. */
export const outcomeReasonLabel = labelMap(OUTCOME_REASON_LABEL_KEYS);

// ---------------------------------------------------------------------------
// The list

/**
 * URL-backed state for the runs list, so a narrowed view is a link a colleague
 * can be sent — the events ledger's shape. `.catch` keeps a mangled URL from
 * crashing the route: a state the registry does not declare is no filter at
 * all rather than an error.
 */
export const runsSearchSchema = z.object({
  task_type: z.string().min(1).optional().catch(undefined),
  status: z.enum(TASK_STATUS_VALUES).optional().catch(undefined),
});

export type RunsSearch = z.infer<typeof runsSearchSchema>;

/**
 * The kinds a top-level run can be, for the list's filter: whole-work altitude
 * only, one entry per word, sorted. Retired kinds stay — their runs did
 * happen, and a filter that could not name them would hide history.
 */
export function kindKeysForRuns(kinds: readonly KindOfWork[]): string[] {
  const keys = new Set(kinds.filter((kind) => kind.kind === "task").map((kind) => kind.key));
  return [...keys].sort((a, b) => a.localeCompare(b));
}

// ---------------------------------------------------------------------------
// What a run's totals may be said to be

/**
 * The wording for a total none of whose parts UBB has learned.
 *
 * Console copy, and NOT the catalogue's `pricing_status.unknown` or
 * `costing_status.unresolved`, though the catalogue words both. Those are the
 * states of ONE posting; a total is not in a state. It is an amount beside a
 * COUNT of what it left out, with no registry value of its own for the
 * catalogue to word — `incompleteTotal` in `@/lib/economic-scenarios` makes
 * the same point, and `at least` beside it is copy of the same kind. The one
 * run-level reading this surface DOES take from the catalogue is the one that
 * is a registry value with a registry reason: a price that does not apply.
 */
export const UNKNOWN_TOTAL = "Unknown";

/** The five totals a run — or a roll-up over runs — carries, spelled as the wire spells them. */
export interface RunTotals {
  readonly event_count: number;
  readonly total_provider_cost_micros: number;
  readonly unresolved_event_count: number;
  readonly total_billed_cost_micros: number;
  readonly unpriced_event_count: number;
}

/**
 * A total and what it is worth as a statement — the shape both sides share.
 *
 * A union rather than a string, so a renderer branches on WHICH reading it
 * holds and cannot coalesce one into a number: `figure` is the amount, `floor`
 * is an amount the run cost — or will be charged — AT LEAST, and `unknown` is
 * no amount at all. `eventsLeftOut` is the count the total could not include,
 * whichever side's count that is.
 */
export type TotalReading =
  | { readonly kind: "figure"; readonly micros: number }
  | { readonly kind: "floor"; readonly micros: number; readonly eventsLeftOut: number }
  | { readonly kind: "unknown"; readonly eventsLeftOut: number };

/**
 * The decision both totals make, once.
 *
 *   nothing left out          → the figure
 *   left out, amount above 0  → a floor
 *   left out, amount at 0     → unknown: UBB knows no amount here
 *
 * A total whose parts all resolved to nothing, with nothing left out, is a
 * FIGURE of zero — a real zero, and it renders as one.
 */
function readTotal(micros: number, eventsLeftOut: number): TotalReading {
  if (eventsLeftOut <= 0) return { kind: "figure", micros };
  if (micros === 0) return { kind: "unknown", eventsLeftOut };
  return { kind: "floor", micros, eventsLeftOut };
}

export function describeTotal(reading: TotalReading, currency: string): string {
  switch (reading.kind) {
    case "figure":
      return formatMicros(reading.micros, currency);
    case "floor":
      return `${AT_LEAST} ${formatMicros(reading.micros, currency)}`;
    case "unknown":
      return UNKNOWN_TOTAL;
  }
}

function eventsHave(count: number): string {
  return `${count.toLocaleString()} ${count === 1 ? "event has" : "events have"}`;
}

// The supplier cost

export type SupplierCostReading = TotalReading;

/** Any row carrying a supplier-cost total beside the count it could not include. */
export interface SupplierCostTotal {
  readonly total_provider_cost_micros: number;
  readonly unresolved_event_count: number;
}

export function readSupplierCost(row: SupplierCostTotal): SupplierCostReading {
  return readTotal(row.total_provider_cost_micros, row.unresolved_event_count);
}

/** The sentence beside a supplier-cost reading, or nothing when the figure is whole. */
export function explainSupplierCost(reading: SupplierCostReading): string | null {
  switch (reading.kind) {
    case "figure":
      return null;
    case "floor":
      return partialTotalNote(reading.eventsLeftOut);
    case "unknown":
      return (
        `${eventsHave(reading.eventsLeftOut)} a supplier cost UBB has not learned, ` +
        `and no event under this run has one it has. The amount is missing, not zero.`
      );
  }
}

// The customer price

/**
 * The price-side reading, with the fourth outcome the supplier cost has no
 * counterpart for. `not_applicable` is decided by the SUBJECT before any
 * count is read, and it carries the registry's own reason
 * (`not_applicable_reason` in `@/lib/vocabulary`) so the renderer can say
 * which of two different things it means: revenue that sits on the run's own
 * agreed price, or revenue that exists nowhere because the workspace does not
 * bill.
 */
export type CustomerPriceReading =
  | TotalReading
  | { readonly kind: "not_applicable"; readonly reason: NotApplicableReason };

/** Any row carrying a customer-price total beside the count it could not include. */
export interface CustomerPriceTotal {
  readonly total_billed_cost_micros: number;
  readonly unpriced_event_count: number;
}

/**
 * The two facts about a run that decide whether a customer price applies at
 * all — both about the subject, neither about resolution.
 *
 * They mirror `apps/metering/pricing/applicability.py`, which decides the same
 * question for one posting and rules that POSTURE WINS THE TIE-BREAK: a
 * workspace that does not bill produces no customer revenue on any work,
 * whatever the regime, and naming the regime instead would send a reader to
 * look for a bill that is never raised. The same order is kept here so a run
 * and the receipts under it can never disagree about why there is no price.
 */
export interface PriceApplicability {
  /** The workspace meters usage and does not bill customers through UBB. */
  readonly meteringOnly: boolean;
  /** The run — or the run containing it — is sold at one agreed price. */
  readonly soldAtOnePrice: boolean;
}

/**
 * Whether a run is sold at one agreed price: it pinned one at start (#415),
 * and that pinned figure is the only wire-borne sign of the regime a run was
 * sold under.
 *
 * ⚠ ASK THE CONTAINING RUN, NEVER A PIECE OF CONTAINED WORK. Contained work
 * never pins a price of its own — one agreed price buys the whole unit of work
 * — so its own `agreed_price_micros` is null under either regime, and reading
 * it would answer "priced per event" for work whose revenue does not apply,
 * which then renders as `$0.00`. The run page resolves the containing run
 * before it reads anything (`run-detail-page.tsx`); the list holds only
 * top-level runs, for which the row is the run.
 */
export function soldAtOnePrice(run: Pick<RunRow, "agreed_price_micros">): boolean {
  return run.agreed_price_micros != null;
}

export function readCustomerPrice(
  row: CustomerPriceTotal,
  applicability: PriceApplicability,
): CustomerPriceReading {
  if (applicability.meteringOnly) return { kind: "not_applicable", reason: "tenant_not_billing" };
  if (applicability.soldAtOnePrice) {
    return { kind: "not_applicable", reason: "fixed_task_pricing" };
  }
  return readTotal(row.total_billed_cost_micros, row.unpriced_event_count);
}

export function describeCustomerPrice(reading: CustomerPriceReading, currency: string): string {
  // The registry's own word for the state every posting under the run is in
  // — this one is a value the catalogue words (see `UNKNOWN_TOTAL`).
  if (reading.kind === "not_applicable") return pricingStatusLabel("not_applicable");
  return describeTotal(reading, currency);
}

/** What a run's five totals are over. */
export const RUN_TOTALS_COVER =
  "Totals over every metered event under this run, including the work contained in it.";

/**
 * What they are NOT over, for a run sold at one agreed price (#425).
 *
 * The projection of a delivered run's Charge is a posting under the run — it
 * names the run as its task — that the run's own counters never accumulate:
 * `TaskService.accumulate_cost` runs on the metered recording path and on no
 * other, so the totals above leave out exactly the posting that carries the
 * run's revenue. "Every event under this run" was one posting short on the
 * one run where that posting is the money, and this sentence is the nearest
 * the tasks surface can get to it: the contract publishes no read of a run's
 * postings, so the posting itself renders on the events surface and nowhere
 * else.
 */
export const RUN_TOTALS_LEAVE_OUT_THE_CHARGE =
  "A run sold at one agreed price also carries that price as one charge posting once it delivers. These totals do not count it; the agreed price below does.";

/** The sentence under the totals: what they cover, and — where it applies — what they leave out. */
export function describeRunTotals(
  applicability: Pick<PriceApplicability, "soldAtOnePrice">,
): string {
  return applicability.soldAtOnePrice
    ? `${RUN_TOTALS_COVER} ${RUN_TOTALS_LEAVE_OUT_THE_CHARGE}`
    : RUN_TOTALS_COVER;
}

/**
 * Why a run generates no customer revenue of its own, said at the run rather
 * than at one event — console copy (ADR-0008 §4.5), total over the registry's
 * two reasons so a third would fail `tsc` rather than render nothing.
 */
export const RUN_PRICE_NOT_APPLICABLE = {
  fixed_task_pricing:
    "This run is sold at one agreed price, so no event under it carries a customer price of its own. What it earns is the agreed price, owed when it delivers.",
  tenant_not_billing:
    "This workspace meters usage and does not bill customers through UBB, so no customer price is resolved for anything it runs.",
} as const satisfies Record<NotApplicableReason, string>;

/** The sentence beside a customer-price reading, or nothing when the figure is whole. */
export function explainCustomerPrice(reading: CustomerPriceReading): string | null {
  switch (reading.kind) {
    case "figure":
      return null;
    case "floor":
      return (
        `${eventsHave(reading.eventsLeftOut)} a customer price UBB has not resolved. ` +
        `They are left out of this total, so the true figure is higher.`
      );
    case "unknown":
      return (
        `${eventsHave(reading.eventsLeftOut)} a customer price UBB has not resolved, ` +
        `and no event under this run has one it has. The amount is missing, not zero.`
      );
    case "not_applicable":
      return RUN_PRICE_NOT_APPLICABLE[reading.reason];
  }
}

// ---------------------------------------------------------------------------
// The agreed price

/**
 * What a run's pinned agreed price is worth, read off how the run ended.
 *
 * The price is the number the run was QUOTED and it does not move; whether it
 * is owed at all depends on the outcome (#416: exactly one Charge on delivery,
 * none on anything else). `completed` means the caller declared delivery and
 * nothing else does (#408), so it is the one state that makes the price owed.
 */
export type AgreedPriceReading =
  | { readonly kind: "owed"; readonly micros: number }
  | { readonly kind: "pending"; readonly micros: number }
  | { readonly kind: "not_owed"; readonly micros: number };

/** `null` where nothing was pinned: a run priced per event, or contained work. */
export function readAgreedPrice(
  run: Pick<RunRow, "agreed_price_micros" | "status">,
): AgreedPriceReading | null {
  if (run.agreed_price_micros == null) return null;
  const micros = run.agreed_price_micros;
  if (run.status === "completed") return { kind: "owed", micros };
  if (run.status === "active") return { kind: "pending", micros };
  return { kind: "not_owed", micros };
}

/**
 * The agreed price, said with what it is worth. For a workspace that meters
 * without billing a delivered run's Charge is recorded for the tenant's own
 * reporting and no customer is asked for it (#416, `applicability.py`), so
 * "owed" would be the wrong word there and the sentence says what is true.
 */
export function describeAgreedPrice(
  reading: AgreedPriceReading,
  currency: string,
  applicability: Pick<PriceApplicability, "meteringOnly">,
): string {
  const amount = formatMicros(reading.micros, currency);
  switch (reading.kind) {
    case "owed":
      return applicability.meteringOnly
        ? `${amount} — delivered. Recorded for your own reporting; this workspace does not bill through UBB.`
        : `${amount} — owed: the run delivered.`;
    case "pending":
      return applicability.meteringOnly
        ? `${amount} — recorded if the run delivers; this workspace does not bill through UBB.`
        : `${amount} — owed if the run delivers.`;
    case "not_owed":
      return `${amount} — not owed: the run did not deliver.`;
  }
}

// ---------------------------------------------------------------------------
// Contained work: the two-level table, and its roll-up

/**
 * How many rows of contained work render inline before the rest fold into the
 * roll-up row.
 *
 * ⚠ THE BOUND IS ON RENDERING ONLY (#424's ruling on the child-count bound
 * HANDOFF §5 left open): a run with many pieces of contained work stops being
 * readable as a flat list, so the table shows this many and folds the rest —
 * but the roll-up row ALWAYS totals every child, folded or not. A roll-up that
 * summed only the visible rows would be a wrong number on a readable page,
 * which is worse than an unreadable one. Twenty-five matches the only page
 * size this console already uses (the events ledger's mock page).
 */
export const CONTAINED_ROWS_SHOWN_INLINE = 25;

export interface FoldedContainedWork {
  /** The rows that render. */
  readonly shown: readonly RunRow[];
  /** How many did not, and are counted only in the roll-up. */
  readonly folded: number;
}

/** The rows to render, in the order they arrived, and how many were folded away. */
export function foldContainedWork(
  contained: readonly RunRow[],
  showAll: boolean,
): FoldedContainedWork {
  if (showAll || contained.length <= CONTAINED_ROWS_SHOWN_INLINE) {
    return { shown: contained, folded: 0 };
  }
  return {
    shown: contained.slice(0, CONTAINED_ROWS_SHOWN_INLINE),
    folded: contained.length - CONTAINED_ROWS_SHOWN_INLINE,
  };
}

/** The roll-up over contained work: how many pieces, and the five totals over ALL of them. */
export interface ContainedTotals extends RunTotals {
  readonly count: number;
}

/**
 * The totals over EVERY piece of contained work handed in.
 *
 * Takes the whole list on purpose, never a `FoldedContainedWork` — a caller
 * cannot hand this the rows it chose to show, because the shape it takes is
 * the list the detail route answered with. The counts of what each total
 * could not include add up like the money does, which is the rule the
 * accumulate primitive applies when it rolls a child into its parent.
 */
export function containedTotals(contained: readonly RunRow[]): ContainedTotals {
  const totals = {
    count: contained.length,
    event_count: 0,
    total_provider_cost_micros: 0,
    unresolved_event_count: 0,
    total_billed_cost_micros: 0,
    unpriced_event_count: 0,
  };
  for (const row of contained) {
    totals.event_count += row.event_count;
    totals.total_provider_cost_micros += row.total_provider_cost_micros;
    totals.unresolved_event_count += row.unresolved_event_count;
    totals.total_billed_cost_micros += row.total_billed_cost_micros;
    totals.unpriced_event_count += row.unpriced_event_count;
  }
  return totals;
}

/** "28 pieces of contained work" / "1 piece of contained work". */
export function piecesOfContainedWork(count: number): string {
  return `${count.toLocaleString()} ${count === 1 ? "piece" : "pieces"} of contained work`;
}
