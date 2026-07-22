import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import {
  Section,
  DetailGrid,
  DetailRow,
  QueryState,
  LoadingRows,
  ErrorInline,
} from "@/components/shared/data-states";
import { StatusBadge } from "@/components/shared/status-badge";
import { FormField } from "@/components/shared/form-field";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from "@/components/ui/table";
import { formatMicros, formatPercent, formatShortDate } from "@/lib/format";
import {
  useCustomerMargin,
  useMarginTrend,
  useRevenueProfile,
  useRevenueMode,
  usePutRevenueProfile,
  usePutRevenueMode,
} from "../api/queries";
import { revenueProfileSchema, type RevenueProfileValues } from "../lib/schema";

export function CustomerMarginTab({ customerId }: { customerId: string }) {
  const margin = useCustomerMargin(customerId);
  const trend = useMarginTrend(customerId);

  return (
    <div className="space-y-6">
      <Section title="Margin" description="Revenue and cost breakdown for the current period.">
        <QueryState query={margin}>
          {(m) => (
            <DetailGrid>
              <DetailRow label="Total revenue">{formatMicros(m.total_revenue_micros)}</DetailRow>
              <DetailRow label="Subscription revenue">{formatMicros(m.subscription_revenue_micros)}</DetailRow>
              <DetailRow label="Usage revenue">{formatMicros(m.usage_revenue_micros)}</DetailRow>
              <DetailRow label="Usage billed">{formatMicros(m.usage_billed_micros)}</DetailRow>
              <DetailRow label="Provider cost">{formatMicros(m.provider_cost_micros)}</DetailRow>
              <DetailRow label="Gross margin">
                {formatMicros(m.gross_margin_micros)}{" "}
                <span className="text-muted-foreground">({formatPercent(m.margin_percentage)})</span>
              </DetailRow>
            </DetailGrid>
          )}
        </QueryState>
      </Section>

      <RevenueModeForm customerId={customerId} />
      <RevenueProfileForm customerId={customerId} />

      <Section title="Margin trend" description="Recent periods.">
        {trend.isLoading ? (
          <LoadingRows rows={3} />
        ) : trend.isError ? (
          <ErrorInline error={trend.error} onRetry={() => trend.refetch()} />
        ) : trend.data && trend.data.points.length > 0 ? (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Period</TableHead>
                <TableHead className="text-right">Provider cost</TableHead>
                <TableHead className="text-right">Usage billed</TableHead>
                <TableHead className="text-right">Gross margin</TableHead>
                <TableHead className="text-right">Margin %</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {trend.data.points.map((p, i) => (
                <TableRow key={`${p.period_start}-${i}`}>
                  <TableCell>{formatShortDate(p.period_start)}</TableCell>
                  <TableCell className="text-right tabular-nums text-muted-foreground">{formatMicros(p.provider_cost_micros)}</TableCell>
                  <TableCell className="text-right tabular-nums">{formatMicros(p.usage_billed_micros)}</TableCell>
                  <TableCell className="text-right tabular-nums">{formatMicros(p.gross_margin_micros)}</TableCell>
                  <TableCell className="text-right tabular-nums">{formatPercent(p.margin_percentage)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        ) : (
          <p className="text-sm text-muted-foreground">No trend data yet.</p>
        )}
      </Section>
    </div>
  );
}

function RevenueModeForm({ customerId }: { customerId: string }) {
  const query = useRevenueMode(customerId);
  const save = usePutRevenueMode(customerId);
  const form = useForm<{ revenue_mode: string }>({
    values: query.data ? { revenue_mode: query.data.revenue_mode } : undefined,
    defaultValues: { revenue_mode: "" },
  });
  return (
    <Section
      title="Revenue mode"
      description="How subscription revenue is attributed for margin. Resolved mode shown when inherited."
    >
      {query.isLoading ? (
        <LoadingRows rows={1} />
      ) : query.isError ? (
        <ErrorInline error={query.error} onRetry={() => query.refetch()} />
      ) : (
        <form
          onSubmit={form.handleSubmit((v) => save.mutate({ revenue_mode: v.revenue_mode }))}
          className="flex items-end gap-3"
        >
          <FormField label="Revenue mode" className="flex-1">
            {(id) => <Input id={id} placeholder="e.g. attributed" {...form.register("revenue_mode")} />}
          </FormField>
          {query.data?.resolved && (
            <div className="pb-1.5 text-xs text-muted-foreground">
              Resolved: <StatusBadge value={query.data.resolved} tone="neutral" />
            </div>
          )}
          <Button type="submit" disabled={save.isPending}>Save</Button>
        </form>
      )}
    </Section>
  );
}

function RevenueProfileForm({ customerId }: { customerId: string }) {
  const query = useRevenueProfile(customerId);
  const save = usePutRevenueProfile(customerId);
  const form = useForm<RevenueProfileValues>({
    resolver: zodResolver(revenueProfileSchema),
    values: query.data
      ? {
          recurring_amount: (query.data.recurring_amount_micros ?? 0) / 1_000_000,
          interval: (query.data.interval === "year" ? "year" : "month") as RevenueProfileValues["interval"],
          currency: query.data.currency,
        }
      : undefined,
  });
  return (
    <Section
      title="Revenue profile"
      description="Manual recurring revenue used when subscription data isn't synced from Stripe."
    >
      {query.isLoading ? (
        <LoadingRows rows={2} />
      ) : query.isError ? (
        <ErrorInline error={query.error} onRetry={() => query.refetch()} />
      ) : (
        <form
          onSubmit={form.handleSubmit((v) =>
            save.mutate({
              recurring_amount_micros: Math.round(v.recurring_amount * 1_000_000),
              interval: v.interval,
              currency: v.currency || "usd",
            }),
          )}
          className="space-y-4"
        >
          <div className="grid gap-4 sm:grid-cols-3">
            <FormField label="Recurring amount (USD)" error={form.formState.errors.recurring_amount?.message}>
              {(id) => <Input id={id} type="number" min={0} step={0.01} {...form.register("recurring_amount", { valueAsNumber: true })} />}
            </FormField>
            <FormField label="Interval">
              {(id) => (
                <select id={id} className="h-8 w-full rounded-lg border border-input bg-transparent px-2.5 text-sm" {...form.register("interval")}>
                  <option value="month">Monthly</option>
                  <option value="year">Yearly</option>
                </select>
              )}
            </FormField>
            <FormField label="Currency">
              {(id) => <Input id={id} placeholder="usd" {...form.register("currency")} />}
            </FormField>
          </div>
          <Button type="submit" disabled={save.isPending}>
            {save.isPending ? "Saving…" : "Save revenue profile"}
          </Button>
        </form>
      )}
    </Section>
  );
}
