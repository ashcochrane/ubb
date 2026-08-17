// The two renderings of a supplier cost that may not be there, as components.
//
// `@/lib/supplier-cost` decides what may be SAID; this decides what is drawn,
// and it sits here rather than in a feature because four features draw it: the
// event ledger, both past-limit reports and every chart tooltip. The rule was
// written once and then copied into five charts in its first draft, which is
// exactly the drift the module exists to prevent one layer down.

import { formatMicros } from "@/lib/format";
import { ABSENT_LABEL } from "@/lib/localisation";
import {
  COSTING_STATUS_EXPLANATIONS,
  costingStatusLabel,
  isPartial,
  marginBound,
  partialTotalNote,
  supplierCostTotal,
  type CostCompleteness,
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

// ---------------------------------------------------------------------------
// Chart tooltips

/** What bounding rule a plotted series obeys. */
export type SeriesRole =
  /** A supplier-cost total: a FLOOR wherever its point is partial. */
  | "supplier-cost"
  /** A margin or markup computed against one: a CEILING on the same terms. */
  | "margin"
  /** Billed cost, revenue, counts — NOT NULL at the column, always whole. */
  | "whole";

/** One entry Recharts hands a tooltip, plus the row it came from. */
export interface TooltipEntry {
  dataKey?: string | number;
  name?: string | number;
  value?: number | string;
  color?: string;
  payload?: Partial<CostCompleteness> & Record<string, unknown>;
}

/**
 * That point's own completeness, or nothing where the row carries none.
 *
 * Returns `null` rather than a zero count, and the distinction is the whole
 * point: a zero is the claim "this point left nothing out", and a row that
 * never carried the fact has not made that claim. The grouped timeseries pivot
 * is the live case — it sums billed cost and plots no supplier cost at all.
 */
function completenessOf(row: TooltipEntry["payload"]): CostCompleteness | null {
  const count = row?.unresolved_event_count;
  return typeof count === "number" ? { unresolved_event_count: count } : null;
}

/**
 * A chart tooltip that will not print a partial cost as a figure.
 *
 * A LINE CANNOT SAY "AT LEAST". A plotted position is a position, and no
 * formatter changes that — so the tooltip is where the bound has to appear,
 * because it is where a reader actually asks for the number. Each point is
 * bounded by its OWN count rather than by the window's: an unresolved cost
 * belongs to the day it fell in, and marking every day for one day's missing
 * supplier invoice is the caveat-on-everything this slice rejects.
 *
 * `roleOf` is keyed on the series' data key, never on its display name: the
 * name is copy and moves, the key is the contract.
 */
export function BoundedCostTooltip({
  active,
  payload,
  label,
  currency,
  labelFormatter,
  roleOf,
  footer,
}: {
  active?: boolean;
  payload?: TooltipEntry[];
  label?: string | number;
  currency: string;
  labelFormatter: (label: string | number | undefined) => string;
  roleOf: (dataKey: string) => SeriesRole;
  /** Extra line above the completeness note (the event count, typically). */
  footer?: (row: NonNullable<TooltipEntry["payload"]>) => string | null;
}) {
  if (!active || !payload || payload.length === 0) return null;
  const row = payload[0]?.payload;
  const completeness = completenessOf(row);
  const note = completeness
    ? partialTotalNote(completeness.unresolved_event_count)
    : null;
  const extra = row && footer ? footer(row) : null;

  return (
    <div className="rounded-md border border-border bg-bg-surface px-3 py-2 text-[11px] shadow-md">
      <div className="mb-1 font-medium text-text-primary">
        {labelFormatter(label)}
      </div>
      {payload.map((entry) => (
        <div
          key={String(entry.dataKey)}
          className="flex items-center justify-between gap-4 text-text-secondary"
        >
          <span className="inline-flex items-center gap-1.5">
            {entry.color !== undefined && (
              <span
                className="block h-[7px] w-[7px] rounded-full"
                style={{ backgroundColor: entry.color }}
              />
            )}
            {entry.name}
          </span>
          <span className="font-medium text-text-primary">
            {seriesAmount(entry, completeness, currency, roleOf)}
          </span>
        </div>
      ))}
      {(extra ?? note) && (
        <div className="mt-1 border-t border-border pt-1 text-text-muted">
          {extra}
          {extra && note && <br />}
          {note}
        </div>
      )}
    </div>
  );
}

/**
 * One tooltip row's amount, bounded by its point's completeness.
 *
 * A value Recharts hands over as a non-number is a value this chart cannot
 * draw, and it renders as the absent marker rather than as a zero — the same
 * rule the amounts obey, one level down. An earlier draft coalesced it to `0`,
 * which printed `$0.00` for a point whose value never arrived.
 */
function seriesAmount(
  entry: TooltipEntry,
  completeness: CostCompleteness | null,
  currency: string,
  roleOf: (dataKey: string) => SeriesRole,
): string {
  if (typeof entry.value !== "number") return ABSENT_LABEL;
  const role = roleOf(String(entry.dataKey));
  if (completeness === null || role === "whole" || !isPartial(completeness)) {
    return formatMicros(entry.value, currency);
  }
  return role === "supplier-cost"
    ? supplierCostTotal(entry.value, completeness, currency)
    : marginBound(entry.value, completeness, currency);
}
