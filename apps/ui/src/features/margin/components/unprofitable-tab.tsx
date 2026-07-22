import { useState } from "react";
import { Link } from "@tanstack/react-router";
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from "@/components/ui/table";
import { Input } from "@/components/ui/input";
import { StatusBadge } from "@/components/shared/status-badge";
import { QueryState } from "@/components/shared/data-states";
import { FormField } from "@/components/shared/form-field";
import { formatMicros, formatPercent } from "@/lib/format";
import { useUnprofitable } from "../api/queries";
import { currentPeriodStart } from "../lib/date-range";

export function UnprofitableTab({ currency }: { currency: string }) {
  const [periodStart, setPeriodStart] = useState(currentPeriodStart());
  const query = useUnprofitable(periodStart);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end gap-3">
        <FormField
          label="Period start"
          hint="Snapshot of customers below your margin threshold for this period."
          className="max-w-xs"
        >
          {(id) => (
            <Input
              id={id}
              type="date"
              className="w-[10.5rem]"
              value={periodStart}
              onChange={(e) => setPeriodStart(e.target.value)}
            />
          )}
        </FormField>
      </div>

      <QueryState
        query={query}
        isEmpty={(data) => data.customers.length === 0}
        empty={{
          title: "No unprofitable customers",
          description:
            "Every customer met your margin threshold for this period.",
        }}
      >
        {(data) => (
          <div className="rounded-xl bg-card ring-1 ring-foreground/10">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Customer</TableHead>
                  <TableHead className="text-right">Gross margin</TableHead>
                  <TableHead className="text-right">Margin %</TableHead>
                  <TableHead className="text-right">Flag</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.customers.map((row) => (
                  <TableRow key={row.customer_id}>
                    <TableCell>
                      <Link
                        to="/customers/$customerId"
                        params={{ customerId: row.customer_id }}
                        className="hover:underline"
                      >
                        <span className="font-medium">{row.external_id}</span>
                      </Link>
                    </TableCell>
                    <TableCell className="text-right">
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
    </div>
  );
}
