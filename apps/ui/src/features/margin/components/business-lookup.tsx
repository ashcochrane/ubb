import { useState, type FormEvent } from "react";
import { Search } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from "@/components/ui/table";
import { FormField } from "@/components/shared/form-field";
import {
  Section,
  DetailGrid,
  DetailRow,
  LoadingRows,
  ErrorInline,
} from "@/components/shared/data-states";
import { StatusBadge } from "@/components/shared/status-badge";
import {
  formatMicros,
  formatPercent,
  formatEventCount,
  truncateId,
} from "@/lib/format";
import { useBusinessMargin } from "../api/queries";

export function BusinessLookup({ currency }: { currency: string }) {
  const [input, setInput] = useState("");
  const [submitted, setSubmitted] = useState("");
  const query = useBusinessMargin(submitted);

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    setSubmitted(input.trim());
  };

  return (
    <Section
      title="Business margin lookup"
      description="Inspect a single business's totals and per-seat unit economics by external id."
    >
      <form onSubmit={onSubmit} className="mb-4 flex items-end gap-3">
        <FormField label="External id" className="max-w-xs flex-1">
          {(id) => (
            <Input
              id={id}
              placeholder="e.g. acme-co"
              value={input}
              onChange={(e) => setInput(e.target.value)}
            />
          )}
        </FormField>
        <Button type="submit" disabled={!input.trim()}>
          <Search />
          Look up
        </Button>
      </form>

      {!submitted ? null : query.isLoading ? (
        <LoadingRows rows={3} />
      ) : query.isError ? (
        <ErrorInline error={query.error} onRetry={query.refetch} />
      ) : query.data ? (
        <div className="space-y-4">
          <DetailGrid>
            <DetailRow label="Business id">
              <span className="font-mono text-xs">
                {truncateId(query.data.business_id)}
              </span>
            </DetailRow>
            <DetailRow label="External id">
              {query.data.external_id}
            </DetailRow>
            <DetailRow label="Subscription revenue">
              {formatMicros(
                query.data.totals.subscription_revenue_micros,
                currency,
              )}
            </DetailRow>
            <DetailRow label="Usage revenue">
              {formatMicros(query.data.totals.usage_revenue_micros, currency)}
            </DetailRow>
            <DetailRow label="Provider cost">
              {formatMicros(query.data.totals.provider_cost_micros, currency)}
            </DetailRow>
            <DetailRow label="Total revenue">
              {formatMicros(query.data.totals.total_revenue_micros, currency)}
            </DetailRow>
            <DetailRow label="Gross margin">
              {formatMicros(query.data.totals.gross_margin_micros, currency)}
            </DetailRow>
            <DetailRow label="Events">
              {formatEventCount(query.data.totals.event_count)}
            </DetailRow>
          </DetailGrid>

          {query.data.seats.length > 0 && (
            <div className="rounded-xl bg-card ring-1 ring-foreground/10">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Seat</TableHead>
                    <TableHead>Revenue mode</TableHead>
                    <TableHead className="text-right">Total revenue</TableHead>
                    <TableHead className="text-right">Provider cost</TableHead>
                    <TableHead className="text-right">Gross margin</TableHead>
                    <TableHead className="text-right">Margin %</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {query.data.seats.map((seat) => (
                    <TableRow key={seat.customer_id}>
                      <TableCell className="font-mono text-xs">
                        {truncateId(seat.customer_id)}
                      </TableCell>
                      <TableCell>
                        <StatusBadge value={seat.revenue_mode} />
                      </TableCell>
                      <TableCell className="text-right">
                        {formatMicros(seat.total_revenue_micros, currency)}
                      </TableCell>
                      <TableCell className="text-right text-muted-foreground">
                        {formatMicros(seat.provider_cost_micros, currency)}
                      </TableCell>
                      <TableCell className="text-right">
                        {formatMicros(seat.gross_margin_micros, currency)}
                      </TableCell>
                      <TableCell className="text-right tabular-nums">
                        {formatPercent(seat.margin_percentage)}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </div>
      ) : null}
    </Section>
  );
}
