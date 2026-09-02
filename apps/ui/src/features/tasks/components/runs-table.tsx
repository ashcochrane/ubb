import { Link } from "@tanstack/react-router";

import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { formatDate, formatEventCount, shortId } from "@/lib/format";
import { ABSENT_LABEL, tenantDefinedLabel } from "@/lib/localisation";

import type { RunRow } from "../api/types";
import { readCustomerPrice, readSupplierCost, soldAtOnePrice } from "../lib/runs";
import { CustomerPriceReadingView, SupplierCostReadingView } from "./amount-reading";
import { RunStatusBadge } from "./run-status-badge";

/**
 * Top-level runs, newest first, one row each — a sibling of the kinds table
 * and not the front door (#424, spec §25 Q2).
 *
 * Every row is a LINK to the run's own page, and its kind is a link to the
 * kind's. The totals are READINGS rather than numbers: a figure, a floor, an
 * unknown or a not-applicable, each drawn as itself (see `../lib/runs`).
 */
export function RunsTable({
  runs,
  currency,
  meteringOnly,
}: {
  runs: readonly RunRow[];
  currency: string;
  /** The workspace meters usage and does not bill customers through UBB. */
  meteringOnly: boolean;
}) {
  return (
    <div className="overflow-x-auto">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Run</TableHead>
            <TableHead>Kind of work</TableHead>
            <TableHead>State</TableHead>
            <TableHead>Started</TableHead>
            <TableHead className="text-right">Events</TableHead>
            <TableHead className="text-right">Supplier cost</TableHead>
            <TableHead className="text-right">Customer price</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {runs.map((run) => (
            <TableRow key={run.task_id} data-status={run.status}>
              <TableCell>
                <Link
                  to="/tasks/runs/$taskId"
                  params={{ taskId: run.task_id }}
                  className="font-mono text-[12px] font-medium text-text-primary underline-offset-2 hover:underline"
                >
                  {shortId(run.task_id)}
                </Link>
              </TableCell>
              <TableCell>
                {run.task_type ? (
                  <Link
                    to="/tasks/kinds/$key"
                    params={{ key: run.task_type }}
                    className="font-mono text-[12px] text-text-primary underline-offset-2 hover:underline"
                  >
                    {tenantDefinedLabel(run.task_type)}
                  </Link>
                ) : (
                  ABSENT_LABEL
                )}
              </TableCell>
              <TableCell>
                <RunStatusBadge status={run.status} />
              </TableCell>
              <TableCell className="text-[12px]">{formatDate(run.created_at)}</TableCell>
              <TableCell className="text-right text-[12px]">
                {formatEventCount(run.event_count)}
              </TableCell>
              <TableCell className="text-right text-[12px]">
                <SupplierCostReadingView reading={readSupplierCost(run)} currency={currency} />
              </TableCell>
              <TableCell className="text-right text-[12px]">
                <CustomerPriceReadingView
                  reading={readCustomerPrice(run, {
                    meteringOnly,
                    soldAtOnePrice: soldAtOnePrice(run),
                  })}
                  currency={currency}
                />
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
