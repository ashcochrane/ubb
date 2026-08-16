// Business rollup — rendered only when GET /margin/business/{external_id}
// answers 200 (the customer is a business). A 404 (individual customer) hides
// the section silently; any OTHER failure renders a compact error with retry
// so the seats rollup can't vanish indistinguishably from "not a business".

import { Link } from "@tanstack/react-router";

import { CopyButton } from "@/components/shared/copy-button";
import { ErrorCard } from "@/components/shared/error-card";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useTenantCurrency } from "@/hooks/use-tenant-config";
import type { DateRange } from "@/lib/date-range";
import { formatEventCount, formatMicros } from "@/lib/format";
import { revenueModeLabel } from "@/lib/labels";
import {
  marginBound,
  marginPercentBound,
  supplierCostTotal,
} from "@/lib/supplier-cost";
import { cn } from "@/lib/utils";

import { useBusinessMargin } from "../api/queries";
import { shortId } from "../lib/helpers";

export function BusinessRollup({
  externalId,
  range,
}: {
  externalId: string;
  range: DateRange;
}) {
  const currency = useTenantCurrency();
  const query = useBusinessMargin(externalId, range);

  if (query.isLoading) return <Skeleton className="h-24 w-full" />;
  // The queryFn maps the EXPECTED 404 (individual customer) to null — hide
  // silently. Anything else is a real failure and must be visible.
  if (query.isError) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Business rollup — seats</CardTitle>
        </CardHeader>
        <CardContent>
          <ErrorCard
            error={query.error}
            onRetry={() => void query.refetch()}
            title="Couldn't load the seats rollup"
            className="py-4"
          />
        </CardContent>
      </Card>
    );
  }
  if (!query.data) return null;

  const { seats, totals } = query.data;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Business rollup — seats</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Seat</TableHead>
                <TableHead>Revenue mode</TableHead>
                <TableHead className="text-right">Events</TableHead>
                <TableHead className="text-right">Revenue</TableHead>
                <TableHead className="text-right">COGS</TableHead>
                <TableHead className="text-right">Gross margin</TableHead>
                <TableHead className="text-right">Margin %</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {seats.map((seat) => (
                <TableRow key={seat.customer_id}>
                  <TableCell>
                    <span className="flex items-center gap-1.5">
                      <Link
                        to="/customers/$customerId"
                        params={{ customerId: seat.customer_id }}
                        className="font-mono text-[12px] underline-offset-2 hover:underline"
                        title={seat.customer_id}
                      >
                        {shortId(seat.customer_id)}
                      </Link>
                      <CopyButton value={seat.customer_id} label="Copy seat ID" />
                    </span>
                  </TableCell>
                  <TableCell>{revenueModeLabel(seat.revenue_mode)}</TableCell>
                  <TableCell className="text-right tabular-nums">
                    {formatEventCount(seat.event_count)}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {formatMicros(seat.total_revenue_micros, currency)}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {supplierCostTotal(seat.provider_cost_micros, seat, currency)}
                  </TableCell>
                  <TableCell
                    className={cn(
                      "text-right tabular-nums",
                      seat.gross_margin_micros < 0 && "text-danger-dark",
                    )}
                  >
                    {marginBound(seat.gross_margin_micros, seat, currency)}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {marginPercentBound(seat.margin_percentage, seat)}
                  </TableCell>
                </TableRow>
              ))}
              <TableRow className="font-medium">
                <TableCell>Totals</TableCell>
                <TableCell />
                <TableCell className="text-right tabular-nums">
                  {formatEventCount(totals.event_count)}
                </TableCell>
                <TableCell className="text-right tabular-nums">
                  {formatMicros(totals.total_revenue_micros, currency)}
                </TableCell>
                {/* The totals row carries its own count rather than summing the
                    seats': a business's rollup is aggregated server-side over
                    the same postings, so re-deriving it here would be a second
                    definition of the one fact. */}
                <TableCell className="text-right tabular-nums">
                  {supplierCostTotal(totals.provider_cost_micros, totals, currency)}
                </TableCell>
                <TableCell
                  className={cn(
                    "text-right tabular-nums",
                    totals.gross_margin_micros < 0 && "text-danger-dark",
                  )}
                >
                  {marginBound(totals.gross_margin_micros, totals, currency)}
                </TableCell>
                {/* The totals shape carries no margin_percentage. */}
                <TableCell className="text-right text-text-muted">—</TableCell>
              </TableRow>
            </TableBody>
          </Table>
        </div>
      </CardContent>
    </Card>
  );
}
