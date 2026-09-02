import { Link } from "@tanstack/react-router";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableFooter,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { formatEventCount, shortId } from "@/lib/format";
import { ABSENT_LABEL, tenantDefinedLabel } from "@/lib/localisation";

import type { RunRow } from "../api/types";
import {
  containedTotals,
  directlyOnRun,
  foldContainedWork,
  piecesOfContainedWork,
  readCustomerPrice,
  readSupplierCost,
  soldAtOnePrice,
  type PriceApplicability,
  type RunTotals,
} from "../lib/runs";
import { CustomerPriceReadingView, SupplierCostReadingView } from "./amount-reading";
import { RunStatusBadge } from "./run-status-badge";

/**
 * The work contained in one run, as a TWO-LEVEL TABLE WITH A ROLL-UP ROW —
 * never a tree widget (#424; #152 Q5, spec §25). The model is declared
 * contained kinds, explicit contained instances, and observed composition, and
 * a flat table is what keeps a run with many pieces inside it readable.
 *
 * ⚠ AT MOST `CONTAINED_ROWS_SHOWN_INLINE` ROWS RENDER; the rest fold into the
 * roll-up row, which says how many it folded and offers to show them all. The
 * bound is on rendering only: the roll-up TOTALS EVERY PIECE, folded or not,
 * because a roll-up that summed only the visible rows would be a wrong number
 * on a readable page. `contained-work-table.test.tsx` holds both halves.
 *
 * The customer price of contained work is decided by the run CONTAINING it —
 * contained work is sold the way the work containing it is sold, and never
 * pins a price of its own — so the run is what is asked, not the child.
 */
export function ContainedWorkTable({
  run,
  contained,
  currency,
  meteringOnly,
}: {
  /** The containing run: its own totals, and whether it was sold at one price. */
  run: RunTotals & Pick<RunRow, "agreed_price_micros">;
  /** Every piece of work contained in it — the whole list, never a page. */
  contained: readonly RunRow[];
  currency: string;
  meteringOnly: boolean;
}) {
  const [showAll, setShowAll] = useState(false);
  const applicability: PriceApplicability = { meteringOnly, soldAtOnePrice: soldAtOnePrice(run) };

  if (contained.length === 0) {
    return (
      <p className="text-[12px] text-text-secondary">
        Nothing is contained in this run: every event under it was reported against the run
        itself.
      </p>
    );
  }

  const { shown, folded } = foldContainedWork(contained, showAll);
  const totals = containedTotals(contained);
  const direct = directlyOnRun(run, totals);

  return (
    <div className="overflow-x-auto">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Contained work</TableHead>
            <TableHead>Kind of work</TableHead>
            <TableHead>State</TableHead>
            <TableHead className="text-right">Events</TableHead>
            <TableHead className="text-right">Supplier cost</TableHead>
            <TableHead className="text-right">Customer price</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {shown.map((row) => (
            <TableRow key={row.task_id} data-contained-row data-status={row.status}>
              <TableCell>
                <Link
                  to="/tasks/runs/$taskId"
                  params={{ taskId: row.task_id }}
                  className="font-mono text-[12px] text-text-primary underline-offset-2 hover:underline"
                >
                  {shortId(row.task_id)}
                </Link>
              </TableCell>
              <TableCell className="font-mono text-[12px]">
                {row.task_type ? tenantDefinedLabel(row.task_type) : ABSENT_LABEL}
              </TableCell>
              <TableCell>
                <RunStatusBadge status={row.status} />
              </TableCell>
              <TableCell className="text-right text-[12px]">
                {formatEventCount(row.event_count)}
              </TableCell>
              <TableCell className="text-right text-[12px]">
                <SupplierCostReadingView reading={readSupplierCost(row)} currency={currency} />
              </TableCell>
              <TableCell className="text-right text-[12px]">
                <CustomerPriceReadingView
                  reading={readCustomerPrice(row, applicability)}
                  currency={currency}
                />
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
        <TableFooter>
          <TableRow data-rollup-row>
            <TableCell colSpan={3}>
              <span className="text-[12px] font-medium">All contained work</span>
              <span className="block text-[11px] font-normal text-text-secondary">
                {piecesOfContainedWork(totals.count)}
                {folded > 0 ? `, ${folded.toLocaleString()} not shown` : ""}
              </span>
              {folded > 0 && (
                <Button
                  variant="link"
                  size="sm"
                  className="h-auto p-0 text-[12px]"
                  onClick={() => setShowAll(true)}
                >
                  Show all {totals.count.toLocaleString()}
                </Button>
              )}
            </TableCell>
            <TableCell className="text-right text-[12px]">
              {formatEventCount(totals.event_count)}
            </TableCell>
            <TableCell className="text-right text-[12px]">
              <SupplierCostReadingView reading={readSupplierCost(totals)} currency={currency} />
            </TableCell>
            <TableCell className="text-right text-[12px]">
              <CustomerPriceReadingView
                reading={readCustomerPrice(totals, applicability)}
                currency={currency}
              />
            </TableCell>
          </TableRow>
          {direct !== null && direct.event_count > 0 && (
            <TableRow data-direct-row>
              <TableCell colSpan={3}>
                <span className="text-[12px] font-medium">Reported against the run itself</span>
                <span className="block text-[11px] font-normal text-text-secondary">
                  Events attached to the run rather than to anything contained in it.
                </span>
              </TableCell>
              <TableCell className="text-right text-[12px]">
                {formatEventCount(direct.event_count)}
              </TableCell>
              <TableCell className="text-right text-[12px]">
                <SupplierCostReadingView reading={readSupplierCost(direct)} currency={currency} />
              </TableCell>
              <TableCell className="text-right text-[12px]">
                <CustomerPriceReadingView
                  reading={readCustomerPrice(direct, applicability)}
                  currency={currency}
                />
              </TableCell>
            </TableRow>
          )}
        </TableFooter>
      </Table>
    </div>
  );
}
