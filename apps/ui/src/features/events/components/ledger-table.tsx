// The event ledger table. Rows open the full receipt; events that landed
// past a stop carry a restrained "Stopped" indicator whose tooltip names the
// limits involved.

import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { formatDate } from "@/lib/format";
import { stopReasonLabel } from "@/lib/labels";
import {
  COSTING_STATUS_EXPLANATIONS,
  costingStatusLabel,
} from "@/lib/supplier-cost";

import { asStopContextEntries, type UsageEventRow } from "../api/types";
import { formatEventMicros } from "../lib/money";

function money(
  micros: number | null | undefined,
  currency: string,
): string {
  return micros === null || micros === undefined
    ? "—"
    : formatEventMicros(micros, currency);
}

/**
 * A row's supplier cost, or the NAME of the state that explains its absence.
 *
 * A bare dash is the right rendering for a value nobody asked about; it is the
 * wrong one here, because a supplier cost is absent for two opposite reasons —
 * UBB could not learn it, or the event's type never had one — and a column full
 * of identical dashes hides which rows are the tenant's to act on. Zero is not
 * an option in either case (#320): it would say the supplier charged nothing.
 *
 * The full sentence belongs to the receipt, which has room for it. This cell
 * has room for the name.
 */
function SupplierCost({ row, currency }: { row: UsageEventRow; currency: string }) {
  if (row.provider_cost_micros !== null && row.provider_cost_micros !== undefined) {
    return <>{formatEventMicros(row.provider_cost_micros, currency)}</>;
  }
  return (
    <span
      className="text-text-muted"
      title={COSTING_STATUS_EXPLANATIONS[row.costing_status]}
    >
      {costingStatusLabel(row.costing_status)}
    </span>
  );
}

function StoppedIndicator({ row }: { row: UsageEventRow }) {
  const entries = asStopContextEntries(row.stop_context);
  if (entries.length === 0) return null;
  const reasons = [...new Set(entries.map((entry) => stopReasonLabel(entry.limit)))];
  const isTipping = entries.some((entry) => !entry.arrived_after);
  return (
    <Tooltip>
      <TooltipTrigger
        onClick={(event) => event.stopPropagation()}
        className="cursor-default"
        aria-label="Stopped event details"
      >
        <Badge variant="outline">Stopped</Badge>
      </TooltipTrigger>
      <TooltipContent>
        <div className="space-y-0.5">
          {reasons.map((reason) => (
            <div key={reason}>{reason}</div>
          ))}
          <div className="text-[11px] opacity-80">
            {isTipping
              ? "This event tripped the limit."
              : "Arrived after the stop — still recorded and billed."}
          </div>
        </div>
      </TooltipContent>
    </Tooltip>
  );
}

export function LedgerTable({
  rows,
  currency,
  onOpen,
}: {
  rows: UsageEventRow[];
  currency: string;
  onOpen: (row: UsageEventRow) => void;
}) {
  return (
    <Table>
      <TableHeader>
        <TableRow className="hover:bg-transparent">
          <TableHead className="pl-3 text-[11px] text-text-muted">When</TableHead>
          <TableHead className="text-[11px] text-text-muted">Event type</TableHead>
          <TableHead className="text-[11px] text-text-muted">Provider</TableHead>
          <TableHead className="text-right text-[11px] text-text-muted">
            Billed
          </TableHead>
          <TableHead className="text-right text-[11px] text-text-muted">
            Provider cost
          </TableHead>
          <TableHead className="pr-3 text-[11px] text-text-muted" />
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map((row) => (
          <TableRow
            key={row.id}
            tabIndex={0}
            className="cursor-pointer"
            onClick={() => onOpen(row)}
            onKeyDown={(event) => {
              if (event.key === "Enter") onOpen(row);
            }}
          >
            <TableCell className="pl-3 text-[12px] text-text-secondary">
              {formatDate(row.effective_at)}
            </TableCell>
            <TableCell className="text-[13px]">
              {row.event_type === "" ? (
                <span className="text-text-muted">—</span>
              ) : (
                row.event_type
              )}
            </TableCell>
            <TableCell className="text-[13px]">
              {row.provider === "" ? (
                <span className="text-text-muted">—</span>
              ) : (
                row.provider
              )}
            </TableCell>
            <TableCell className="text-right text-[13px] tabular-nums">
              {money(row.billed_cost_micros, currency)}
            </TableCell>
            <TableCell className="text-right text-[13px] tabular-nums text-text-secondary">
              <SupplierCost row={row} currency={currency} />
            </TableCell>
            <TableCell className="pr-3 text-right">
              <StoppedIndicator row={row} />
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
