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
// THE POOL'S PAIR IS READ THROUGH `@/lib/spend-pool`. Its readers and the
// sentence keeping it apart from the wallet's affordability were written
// here in #467 and moved down a layer in #468, the day the customer's
// Billing tab became the second feature to render them; what stays here is
// the Ceiling's alone.

import { readCeiling, type CeilingReading } from "@/lib/ceiling";
import { amountAtMost, shareAtLeast } from "@/lib/supplier-cost";
import { readTotal, type TotalReading } from "@/lib/total-reading";

import type { CeilingUtilisationRow, UtilisationAndHeadroom } from "../api/types";

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
export function anyIndeterminate(report: UtilisationAndHeadroom): boolean {
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
  return shareAtLeast(report.average_final_utilisation_percentage, anyIndeterminate(report));
}

/** The average unused headroom, or nothing where no unit had a ceiling; a most on the same terms. */
export function describeAverageHeadroom(
  report: UtilisationAndHeadroom,
  currency: string,
): string | null {
  if (report.average_unused_headroom_micros == null) return null;
  return amountAtMost(report.average_unused_headroom_micros, currency, anyIndeterminate(report));
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
