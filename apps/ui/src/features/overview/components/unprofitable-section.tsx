import { Link } from "@tanstack/react-router";
import { Section, QueryState } from "@/components/shared/data-states";
import { StatusBadge } from "@/components/shared/status-badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { formatMicros, formatPercent, truncateId } from "@/lib/format";
import { useUnprofitable } from "../api/queries";
import { ViewLink } from "./stat-grid";

export function UnprofitableSection({ currency }: { currency: string }) {
  const query = useUnprofitable();
  return (
    <Section
      title="Unprofitable customers"
      description="Customers whose costs exceed their revenue."
      actions={<ViewLink to="/customers">View customers</ViewLink>}
    >
      <QueryState
        query={query}
        empty={{ title: "All customers profitable", description: "No customer is running at a negative margin." }}
        isEmpty={(d) => d.customers.length === 0}
      >
        {(d) => (
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Customer</TableHead>
                  <TableHead className="text-right">Gross margin</TableHead>
                  <TableHead className="text-right">Margin %</TableHead>
                  <TableHead className="text-right">Status</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {d.customers.slice(0, 5).map((row) => (
                  <TableRow key={row.customer_id}>
                    <TableCell>
                      <Link
                        to="/customers/$customerId"
                        params={{ customerId: row.customer_id }}
                        className="font-medium underline-offset-2 hover:underline"
                      >
                        {truncateId(row.external_id)}
                      </Link>
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {formatMicros(row.gross_margin_micros, currency)}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {formatPercent(row.margin_percentage)}
                    </TableCell>
                    <TableCell className="text-right">
                      <StatusBadge value="Unprofitable" tone="danger" />
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </QueryState>
    </Section>
  );
}
