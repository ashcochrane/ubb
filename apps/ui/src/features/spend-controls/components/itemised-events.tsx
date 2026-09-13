// The events an episode itemises: the tipping event and every event that
// landed after the stop, in both denominations, with each amount's absence
// NAMED rather than dashed or zeroed. This is the one report where a zeroed
// unknown reads as exoneration — it itemises what overran a customer's own
// spend stop — so a price UBB could not resolve renders as its status and a
// cost UBB never learned as its status (#330, #351), never as `$0.00`.

import { Link } from "@tanstack/react-router";

import { CopyButton } from "@/components/shared/copy-button";
import { SupplierCostAmount } from "@/components/shared/supplier-cost";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  PRICING_STATUS_EXPLANATIONS,
  pricingStatusLabel,
  settledPriceMicros,
} from "@/lib/customer-price";
import { formatDate, formatEventMicros, shortId } from "@/lib/format";

import type { ItemisedEventRow } from "../api/types";

export function ItemisedEventsTable({
  events,
  currency,
}: {
  events: readonly ItemisedEventRow[];
  currency: string;
}) {
  return (
    <div className="overflow-x-auto">
      <Table>
        <TableHeader>
          <TableRow className="hover:bg-transparent">
            <TableHead className="text-[11px] text-text-muted">Event</TableHead>
            <TableHead className="text-[11px] text-text-muted">Effective at</TableHead>
            <TableHead className="text-[11px] text-text-muted">Arrival</TableHead>
            <TableHead className="text-[11px] text-text-muted">Charge</TableHead>
            <TableHead className="text-right text-[11px] text-text-muted">Billed</TableHead>
            <TableHead className="text-right text-[11px] text-text-muted">
              Provider cost
            </TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {events.map((row) => {
            const settled = settledPriceMicros(row);
            return (
              <TableRow key={row.event_id} className="hover:bg-transparent">
                <TableCell>
                  <Link
                    to="/events/$eventId"
                    params={{ eventId: row.event_id }}
                    // The customer id in the search keeps the receipt's Refund
                    // action available: the event body carries no owner id.
                    search={{ customer_id: row.customer_id }}
                    className="font-mono text-[12px] underline-offset-2 hover:underline"
                    title={row.event_id}
                  >
                    {shortId(row.event_id)}
                  </Link>
                </TableCell>
                <TableCell className="text-[12px]">{formatDate(row.effective_at)}</TableCell>
                <TableCell>
                  <Badge variant={row.arrived_after ? "secondary" : "outline"}>
                    {row.arrived_after ? "Landed after the stop" : "Tipping event"}
                  </Badge>
                </TableCell>
                {/* A delivered fixed-price unit's one posting projects a
                    Charge (ADR-0013); a metered event projects none, and a
                    dash is the right rendering for a value that does not
                    apply to the row. */}
                <TableCell>
                  {row.charge_id == null ? (
                    <span className="text-text-muted">—</span>
                  ) : (
                    <span className="inline-flex items-center gap-1 font-mono text-[12px]">
                      <span title={row.charge_id}>{shortId(row.charge_id)}</span>
                      <CopyButton value={row.charge_id} label="Copy charge id" />
                    </span>
                  )}
                </TableCell>
                {/* Three statuses null the price column and they do not mean
                    the same thing (#351): the status goes IN the cell, so an
                    unresolved price never reads as a charge of nothing. */}
                <TableCell
                  className="text-right text-[12px] tabular-nums"
                  data-pricing={row.pricing_status}
                >
                  {settled === null ? (
                    <span
                      className="text-text-muted"
                      title={PRICING_STATUS_EXPLANATIONS[row.pricing_status]}
                    >
                      {pricingStatusLabel(row.pricing_status)}
                    </span>
                  ) : (
                    formatEventMicros(settled, currency)
                  )}
                </TableCell>
                <TableCell className="text-right text-[12px] tabular-nums">
                  <SupplierCostAmount
                    micros={row.provider_cost_micros}
                    status={row.costing_status}
                    currency={currency}
                    format={formatEventMicros}
                  />
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}
