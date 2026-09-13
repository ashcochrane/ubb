// Utilisation and headroom as this feature reads and words it (#467; slice 6
// §3, §14; Testing Decisions claims 13 and 15).
//
// UTILISATION IS INFORMATION, AND ENFORCEMENT IS BINARY (#150 §9; spec §3).
// A ceiling either stopped a unit of work or it did not; there is no warning
// event, no threshold and no amber state in v1, and this surface says so by
// rendering nothing of the kind (#152 §4). What it renders is how much of
// each ceiling the work used and what headroom it left — per unit, then in
// aggregate — and how often UBB could not tell, which is a count that has no
// other home anywhere.
//
// THE AGGREGATE IS READ THE WAY EACH ROW IS READ. The route computes the
// average per unit and then across every unit (#150 §9.3), and an
// `indeterminate` unit contributes its own floor, so the average utilisation
// is itself a floor and the average headroom a most wherever the
// indeterminate count is not zero — "at least" / "at most", the same words
// `@/lib/ceiling` puts on one row, and never "under". Every average is null
// where no unit contributes, and a null renders as an absence, never as zero
// (#155 §9.2).
//
// THE POOL AND THE WALLET ANSWER DIFFERENT QUESTIONS (#151 §11.3; spec §4),
// and the pool's pair renders here beside a sentence saying so, because a
// reader who sees a pool at its line and a balance that could pay for a
// hundred more starts has been shown two true things about two different
// bounds.

import { readCeiling, type CeilingReading } from "@/lib/ceiling";
import { formatMicros } from "@/lib/format";
import { AT_LEAST, AT_MOST } from "@/lib/supplier-cost";
import { readTotal, type TotalReading } from "@/lib/total-reading";

import type {
  CeilingUtilisationRow,
  CustomerSpendPoolStatus,
  UtilisationAndHeadroom,
} from "../api/types";

// ---------------------------------------------------------------------------
// One row

/**
 * A row's assessment through the console's one reader of one. The report's
 * row spells the unresolved count `final_unresolved_event_count` — the
 * count as the unit ended — where the unit reads spell it bare; the
 * reading is the same.
 */
export function readUnitCeiling(row: CeilingUtilisationRow): CeilingReading {
  return readCeiling({
    task_cogs_ceiling_micros: row.task_cogs_ceiling_micros,
    ceiling_status: row.ceiling_status,
    ceiling_used_percentage: row.ceiling_used_percentage,
    ceiling_remaining_micros: row.ceiling_remaining_micros,
    unresolved_event_count: row.final_unresolved_event_count,
  });
}

/** The known supplier cost the unit ended on, beside how many costs it could not include. */
export function readKnownCost(row: CeilingUtilisationRow): TotalReading {
  return readTotal(row.final_provider_cost_micros, row.final_unresolved_event_count);
}

/** Whether a unit is contained work, off the one fact that says so. */
export function containedUnit(row: CeilingUtilisationRow): boolean {
  return row.parent_task_id != null;
}

// ---------------------------------------------------------------------------
// The aggregate

/** Whether any unit the aggregate is over was indeterminate — the fact that makes its averages bounds. */
function anyIndeterminate(report: UtilisationAndHeadroom): boolean {
  return report.indeterminate_count > 0;
}

/**
 * The average final utilisation, or nothing where no unit had a ceiling.
 * A floor wherever an indeterminate unit contributed its own floor to it.
 *
 * The four nullable aggregate fields are optional on the generated type —
 * the schema does not list them as required — so each is read with `==
 * null`: absent and null are the same absence, and neither is a zero.
 */
export function describeAverageUtilisation(report: UtilisationAndHeadroom): string | null {
  if (report.average_final_utilisation_percentage == null) return null;
  const share = `${report.average_final_utilisation_percentage}%`;
  return anyIndeterminate(report) ? `${AT_LEAST} ${share}` : share;
}

/** The average unused headroom, or nothing where no unit had a ceiling; a most on the same terms. */
export function describeAverageHeadroom(
  report: UtilisationAndHeadroom,
  currency: string,
): string | null {
  if (report.average_unused_headroom_micros == null) return null;
  const amount = formatMicros(report.average_unused_headroom_micros, currency);
  return anyIndeterminate(report) ? `${AT_MOST} ${amount}` : amount;
}

/**
 * A count of the work listed and its share: "2 of 6 · 33%". The share is
 * the route's, rounded down, and is left out where the route sent none.
 */
export function describeShare(
  count: number,
  share: number | null | undefined,
  unitCount: number,
): string {
  const counted = `${count.toLocaleString()} of ${unitCount.toLocaleString()}`;
  return share == null ? counted : `${counted} · ${share}%`;
}

// ---------------------------------------------------------------------------
// The pool's status pair

/** The customer's known period charges, beside how many postings the figure could not price. */
export function readPoolCharges(pool: CustomerSpendPoolStatus): TotalReading {
  return readTotal(pool.known_period_charges_micros, pool.unresolved_posting_count);
}

/** The share of the pool the known charges have used — a floor wherever the pair is. */
export function describePoolUtilisation(pool: CustomerSpendPoolStatus): string | null {
  if (pool.used_percentage === null) return null;
  const share = `${pool.used_percentage}%`;
  return pool.unresolved_posting_count > 0 ? `${AT_LEAST} ${share}` : share;
}

/**
 * The headroom left under the pool — a most wherever the pair is a floor.
 * A zero past the line is SETTLED: the kernel clamps the headroom at
 * nothing, and a posting it could not price can only lower a figure that
 * is already at its floor, so it renders as the zero it is, not as a most.
 */
export function describePoolHeadroom(pool: CustomerSpendPoolStatus, currency: string): string | null {
  if (pool.remaining_micros === null) return null;
  const amount = formatMicros(pool.remaining_micros, currency);
  const bounded = pool.unresolved_posting_count > 0 && pool.remaining_micros > 0;
  return bounded ? `${AT_MOST} ${amount}` : amount;
}

// ---------------------------------------------------------------------------
// The console's sentences beside the figures — copy, not catalogue content
// (ADR-0008 §4.5).

export const AVERAGED_PER_UNIT =
  "Averaged per unit of work, then across every unit that had a ceiling, so one chatty unit weighs exactly one.";

export const INDETERMINATE_HAS_NO_OTHER_HOME =
  "Work that completed with a supplier cost still unresolved, so UBB could not tell whether it stayed inside its ceiling. Nothing else counts this.";

export const REACHED_MEANS =
  "Work whose known supplier cost reached its ceiling and was stopped there.";

export const NOT_APPLICABLE_MEANS =
  "Work with no ceiling to evaluate: its kind is declared uncapped, or nothing declares one.";

export const NO_COMPLETED_WORK =
  "No unit of work completed in this window, so there is nothing to measure against a ceiling.";

export const STARTS_REFUSED =
  "The known charges are at or over the pool's stop line, so new starts for this customer are being refused.";

export const POOL_AND_WALLET_DIFFER =
  "The pool answers a different question from the wallet's affordability. The pool asks how much of one period's charges a customer has used against the bound declared for them; affordability asks whether their balance, less what is reserved, can pay for the next start. A large balance beside a small pool is coherent.";
