import { useMemo, useState } from "react";
import { Link } from "@tanstack/react-router";
import { ArrowUpDown } from "lucide-react";
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from "@/components/ui/table";
import { QueryState } from "@/components/shared/data-states";
import { formatMicros, formatPercent, truncateId } from "@/lib/format";
import { useMarginCustomers } from "../api/queries";
import type { CustomerMarginRow, DateRange } from "../api/types";

export function CustomersTab({
  range,
  currency,
}: {
  range: DateRange;
  currency: string;
}) {
  const query = useMarginCustomers(range);
  const [sortDesc, setSortDesc] = useState(true);

  const rows = useMemo(() => {
    const list: CustomerMarginRow[] = query.data?.customers ?? [];
    return [...list].sort((a, b) =>
      sortDesc
        ? b.margin_percentage - a.margin_percentage
        : a.margin_percentage - b.margin_percentage,
    );
  }, [query.data, sortDesc]);

  return (
    <QueryState
      query={query}
      isEmpty={(data) => data.customers.length === 0}
      empty={{
        title: "No customer margins for this period",
        description: "Adjust the date range to see per-customer unit economics.",
      }}
    >
      {() => (
        <div className="rounded-xl bg-card ring-1 ring-foreground/10">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Customer</TableHead>
                <TableHead className="text-right">Subscription</TableHead>
                <TableHead className="text-right">Usage revenue</TableHead>
                <TableHead className="text-right">Provider cost</TableHead>
                <TableHead className="text-right">Gross margin</TableHead>
                <TableHead className="text-right">
                  <button
                    type="button"
                    onClick={() => setSortDesc((v) => !v)}
                    className="ml-auto inline-flex items-center gap-1 hover:text-foreground"
                    aria-label="Sort by margin percentage"
                  >
                    Margin %
                    <ArrowUpDown className="size-3.5 text-muted-foreground" />
                  </button>
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((row) => (
                <TableRow key={row.customer_id}>
                  <TableCell className="font-mono text-xs">
                    <Link
                      to="/customers/$customerId"
                      params={{ customerId: row.customer_id }}
                      className="hover:underline"
                    >
                      {truncateId(row.customer_id)}
                    </Link>
                  </TableCell>
                  <TableCell className="text-right">
                    {formatMicros(row.subscription_revenue_micros, currency)}
                  </TableCell>
                  <TableCell className="text-right">
                    {formatMicros(row.usage_revenue_micros, currency)}
                  </TableCell>
                  <TableCell className="text-right text-muted-foreground">
                    {formatMicros(row.provider_cost_micros, currency)}
                  </TableCell>
                  <TableCell className="text-right">
                    {formatMicros(row.gross_margin_micros, currency)}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {formatPercent(row.margin_percentage)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </QueryState>
  );
}
