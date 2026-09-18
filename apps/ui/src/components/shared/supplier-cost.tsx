// A supplier cost that may not be there, drawn for ONE subject.
//
// `@/lib/supplier-cost` decides what may be SAID; this decides what is drawn,
// and it sits here rather than in a feature because two features draw it: the
// event ledger's cost column and Stops and breaches' itemised events.
//
// ⚠ THE CHART TOOLTIP THAT LIVED HERE IS GONE (#510). `BoundedCostTooltip`
// bounded each series by a ROLE — supplier cost a floor, margin a ceiling,
// revenue "whole at the column" — which stopped being true of revenue when
// #351 made a price nullable, and was never true of a measure of the one
// economic query, which carries its own state. Every economic chart now uses
// `MeasureTooltip` in `./measure-value`, which says each series as its figure's
// state allows.

import { formatMicros } from "@/lib/format";
import {
  COSTING_STATUS_EXPLANATIONS,
  costingStatusLabel,
} from "@/lib/supplier-cost";
import type { CostingStatus } from "@/lib/vocabulary";

/**
 * One subject's supplier cost, or the NAME of the state that explains its
 * absence.
 *
 * A bare dash is the right rendering for a value nobody asked about; it is the
 * wrong one here, because a supplier cost is absent for two opposite reasons —
 * UBB could not learn it, or the event's type never had one — and a column of
 * identical dashes hides which rows are the tenant's to act on. Zero is not an
 * option in either case (#320): it would say the supplier charged nothing.
 *
 * The full sentence belongs to a receipt, which has room for it. A table cell
 * has room for the name, and carries the sentence as its title.
 */
export function SupplierCostAmount({
  micros,
  status,
  currency,
  format = formatMicros,
}: {
  micros: number | null | undefined;
  /**
   * `null` where the row carried no status — an untyped response only. The
   * absence then renders as an absence and nothing is invented to name it.
   */
  status: CostingStatus | null | undefined;
  currency: string;
  /** Per-EVENT surfaces pass a formatter that keeps sub-cent precision. */
  format?: (micros: number, currency: string) => string;
}) {
  if (micros !== null && micros !== undefined) {
    return <>{format(micros, currency)}</>;
  }
  return (
    <span
      className="text-text-muted"
      title={status ? COSTING_STATUS_EXPLANATIONS[status] : undefined}
    >
      {costingStatusLabel(status)}
    </span>
  );
}
