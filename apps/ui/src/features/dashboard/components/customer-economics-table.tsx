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
import { formatMicros, formatPercent } from "@/lib/format";
import { cn } from "@/lib/utils";

import { useMarginCustomers } from "../api/queries";
import type { Window } from "../api/types";
import {
  customerEconomics,
  shortId,
  sortCustomers,
  type CustomerSortKey,
} from "../lib/economics";
import { HelpTip } from "./help-tip";
import { SectionEmpty } from "./section-empty";

const TOP_N = 10;

const METERED_TIP =
  "Meter-only workspace: revenue here is what usage billed at your prices, " +
  "and margin is billed minus provider cost.";

export interface CustomerEconomicsTableProps {
  window: Window;
  meterOnly: boolean;
  currency: string;
  className?: string;
}

export function CustomerEconomicsTable({
  window,
  meterOnly,
  currency,
  className,
}: CustomerEconomicsTableProps) {
  const query = useMarginCustomers(window);
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
      ) : query.data.customers.length === 0 ? (
        <SectionEmpty
          title="No customer usage in this window"
          description="Customer revenue, cost, and margin appear once usage is recorded."
          cta={{ label: "Go to customers", to: "/customers" }}
        />
      ) : (
        <EconomicsRows
          rows={sortCustomers(query.data.customers, meterOnly, sort)}
          total={query.data.customers.length}
          sort={sort}
          onSortChange={setSort}
          meterOnly={meterOnly}
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
  meterOnly,
  currency,
}: {
  rows: ReturnType<typeof sortCustomers>;
  total: number;
  sort: CustomerSortKey;
  onSortChange: (key: CustomerSortKey) => void;
  meterOnly: boolean;
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
                label={meterOnly ? "Usage billed" : "Revenue"}
                sortKey="revenue"
                sort={sort}
                onSortChange={onSortChange}
                help={meterOnly ? METERED_TIP : undefined}
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
            const view = customerEconomics(row, meterOnly);
            const negative = view.margin_micros < 0;
            return (
              <TableRow key={row.customer_id}>
                <TableCell>
                  <span className="inline-flex items-center gap-1.5">
                    {/* Margin list rows carry no external_id (contract gap) —
                        show the shortened customer UUID with a copy affordance. */}
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
                  {formatMicros(view.revenue_micros, currency)}
                </TableCell>
                <TableCell className="text-right text-text-secondary">
                  {formatMicros(row.provider_cost_micros, currency)}
                </TableCell>
                <TableCell
                  className={cn("text-right font-medium", negative && "text-destructive")}
                >
                  {formatMicros(view.margin_micros, currency)}
                </TableCell>
                <TableCell
                  className={cn("text-right", negative && "text-destructive")}
                >
                  {formatPercent(view.margin_pct)}
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
