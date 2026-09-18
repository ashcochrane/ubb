import * as React from "react";
import { Link } from "@tanstack/react-router";
import { ArrowRight } from "lucide-react";

import { ChartCard } from "@/components/shared/chart-card";
import { CopyButton } from "@/components/shared/copy-button";
import { ErrorCard } from "@/components/shared/error-card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { MarginShare, MeasureValue } from "@/components/shared/measure-value";
import { isNegative } from "@/lib/measure-state";
import { cn } from "@/lib/utils";

import { useCustomerEconomics } from "../api/queries";
import type { Window } from "../api/types";
import {
  shortId,
  sortCustomers,
  type CustomerSortKey,
} from "../lib/economics";
import { HelpTip } from "./help-tip";
import { SectionEmpty } from "./section-empty";

const TOP_N = 10;

// ⚠ THE METERED TIP IS GONE (#501), with the second reading of revenue it
// existed to name: the one economic query answers `customer_revenue` from one
// definition for every workspace, so there is nothing left to explain away.

export interface CustomerEconomicsTableProps {
  window: Window;
  currency: string;
  className?: string;
}

export function CustomerEconomicsTable({
  window,
  currency,
  className,
}: CustomerEconomicsTableProps) {
  const query = useCustomerEconomics(window);
  const [sort, setSort] = React.useState<CustomerSortKey>("revenue");

  return (
    <ChartCard
      title="Customer economics"
      className={className}
      actions={
        <Link
          to="/customers"
          className="inline-flex items-center gap-1 text-[12px] font-medium text-text-secondary transition-colors hover:text-text-primary"
        >
          View all customers
          <ArrowRight className="h-3 w-3" strokeWidth={1.5} />
        </Link>
      }
    >
      {query.isPending ? (
        <div className="space-y-2">
          {Array.from({ length: 6 }, (_, i) => (
            <Skeleton key={i} className="h-9 rounded" />
          ))}
        </div>
      ) : query.isError ? (
        <ErrorCard
          error={query.error}
          title="Couldn't load customer economics"
          onRetry={() => void query.refetch()}
        />
      ) : query.data.length === 0 ? (
        <SectionEmpty
          title="No customer usage in this window"
          description="Customer revenue, cost, and margin appear once usage is recorded."
          cta={{ label: "Go to customers", to: "/customers" }}
        />
      ) : (
        <EconomicsRows
          rows={sortCustomers(query.data, sort)}
          total={query.data.length}
          sort={sort}
          onSortChange={setSort}
          currency={currency}
        />
      )}
    </ChartCard>
  );
}

function SortHeader({
  label,
  sortKey,
  sort,
  onSortChange,
  help,
}: {
  label: string;
  sortKey: CustomerSortKey;
  sort: CustomerSortKey;
  onSortChange: (key: CustomerSortKey) => void;
  help?: string;
}) {
  const active = sort === sortKey;
  return (
    <span className="inline-flex items-center gap-1">
      <button
        type="button"
        onClick={() => onSortChange(sortKey)}
        aria-pressed={active}
        title={`Sort by ${label.toLowerCase()}`}
        className={cn(
          "transition-colors hover:text-text-primary",
          active ? "font-semibold text-text-primary" : "text-text-muted",
        )}
      >
        {label}
        {active ? " ↓" : ""}
      </button>
      {help && <HelpTip label={`About ${label.toLowerCase()}`} text={help} />}
    </span>
  );
}

function EconomicsRows({
  rows,
  total,
  sort,
  onSortChange,
  currency,
}: {
  rows: ReturnType<typeof sortCustomers>;
  total: number;
  sort: CustomerSortKey;
  onSortChange: (key: CustomerSortKey) => void;
  currency: string;
}) {
  const visible = rows.slice(0, TOP_N);
  return (
    <div className="overflow-x-auto">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Customer</TableHead>
            <TableHead className="text-right">
              <SortHeader
                label="Revenue"
                sortKey="revenue"
                sort={sort}
                onSortChange={onSortChange}
              />
            </TableHead>
            <TableHead className="text-right">COGS</TableHead>
            <TableHead className="text-right">
              <SortHeader
                label="Gross margin"
                sortKey="margin"
                sort={sort}
                onSortChange={onSortChange}
              />
            </TableHead>
            <TableHead className="text-right">
              <SortHeader
                label="Margin %"
                sortKey="margin_pct"
                sort={sort}
                onSortChange={onSortChange}
              />
            </TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {visible.map((row) => {
            // ⚠ A ROW MAY STATE NO MARGIN AT ALL, and an absence is not a loss:
            // it is neither negative nor zero, so it is styled as neither.
            const negative = isNegative(row.margin);
            return (
              <TableRow key={row.customer_id}>
                <TableCell>
                  <span className="inline-flex items-center gap-1.5">
                    {/* The customer axis groups by IDENTITY — a tenant's own
                        external id is its word for the same row and belongs to
                        the surface that renders it — so show the shortened UUID
                        with a copy affordance. */}
                    <Link
                      to="/customers/$customerId"
                      params={{ customerId: row.customer_id }}
                      title={row.customer_id}
                      className="font-mono text-[12px] text-text-primary underline-offset-2 hover:underline"
                    >
                      {shortId(row.customer_id)}
                    </Link>
                    <CopyButton value={row.customer_id} label="Copy customer ID" />
                  </span>
                </TableCell>
                <TableCell className="text-right font-medium">
                  <MeasureValue figure={row.revenue} currency={currency} />
                </TableCell>
                {/* Each customer's figures carry their OWN counts: an
                    unresolved cost belongs to the customer it was incurred
                    for, and a table that bounded every row on the window's
                    total would caveat nine rows for one customer's missing
                    invoice. */}
                <TableCell className="text-right text-text-secondary">
                  <MeasureValue figure={row.cost} currency={currency} />
                </TableCell>
                <TableCell
                  className={cn("text-right font-medium", negative && "text-destructive")}
                >
                  <MeasureValue figure={row.margin} currency={currency} />
                </TableCell>
                <TableCell
                  className={cn("text-right", negative && "text-destructive")}
                >
                  <MarginShare margin={row.margin} revenue={row.revenue} />
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
      {total > TOP_N && (
        <p className="mt-2 text-[11px] text-text-muted">
          Showing the top {TOP_N} of {total} customers — see all on the customers page.
        </p>
      )}
    </div>
  );
}
