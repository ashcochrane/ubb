import * as React from "react";

import { ChartCard } from "@/components/shared/chart-card";
import { EmptyState } from "@/components/shared/empty-state";
import { ErrorCard } from "@/components/shared/error-card";
import { StatCard } from "@/components/shared/stat-card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { useTenantCurrency } from "@/hooks/use-tenant-config";
import type { DateRange } from "@/lib/date-range";
import { formatEventCount, formatMicros, formatPercent } from "@/lib/format";
import { revenueModeLabel } from "@/lib/labels";
import { cn } from "@/lib/utils";

import { useMarginTrend } from "../api/queries";
import type { CustomerMarginOut } from "../api/types";
import { BusinessRollup } from "./business-rollup";
import { RevenuePanels } from "./revenue-panels";

const MarginTrendChart = React.lazy(() => import("./margin-trend-chart"));

export function OverviewTab({
  customerId,
  margin,
  range,
}: {
  customerId: string;
  margin: CustomerMarginOut;
  range: DateRange;
}) {
  const currency = useTenantCurrency();
  const [periods, setPeriods] = React.useState(6);
  const trend = useMarginTrend(customerId, periods);
  const negative = margin.gross_margin_micros < 0;

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatCard
          label="Total revenue"
          value={formatMicros(margin.total_revenue_micros, currency)}
          variant="raised"
          subtitle={`Resolved revenue mode: ${revenueModeLabel(margin.revenue_mode)}`}
        />
        <StatCard
          label="Provider cost (COGS)"
          value={formatMicros(margin.provider_cost_micros, currency)}
          variant="raised"
          subtitle={`${formatEventCount(margin.event_count)} events in window`}
        />
        <StatCard
          label="Gross margin"
          value={
            <span className={cn(negative && "text-danger-dark")}>
              {formatMicros(margin.gross_margin_micros, currency)}
            </span>
          }
          variant="raised"
          subtitle="Revenue minus provider cost"
        />
        <StatCard
          label="Margin %"
          value={
            <span className={cn(margin.margin_percentage < 0 && "text-danger-dark")}>
              {formatPercent(margin.margin_percentage)}
            </span>
          }
          variant="raised"
          subtitle={`${margin.period.start} → ${margin.period.end}`}
        />
      </div>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-3">
        <StatCard
          label="Subscription revenue"
          value={formatMicros(margin.subscription_revenue_micros, currency)}
        />
        <StatCard
          label="Usage billed"
          value={formatMicros(margin.usage_billed_micros, currency)}
        />
        <StatCard
          label="Usage counted as revenue"
          value={formatMicros(margin.usage_revenue_micros, currency)}
          subtitle={
            margin.revenue_mode === "metered_only"
              ? "Metered only — billed usage doesn't count as revenue"
              : undefined
          }
        />
      </div>

      <ChartCard
        title="Margin trend (closed monthly periods)"
        actions={
          <Select
            value={String(periods)}
            onValueChange={(value) => {
              if (value !== null) setPeriods(Number(value));
            }}
          >
            <SelectTrigger className="h-7 text-[12px]" aria-label="Trend periods">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="6">Last 6 periods</SelectItem>
              <SelectItem value="12">Last 12 periods</SelectItem>
            </SelectContent>
          </Select>
        }
      >
        {trend.isLoading ? (
          <Skeleton className="h-64 w-full" />
        ) : trend.isError ? (
          <ErrorCard error={trend.error} onRetry={() => void trend.refetch()} />
        ) : !trend.data || trend.data.points.length === 0 ? (
          <EmptyState
            title="No closed periods yet"
            description="The trend fills in as monthly economics periods close."
          />
        ) : (
          <React.Suspense fallback={<Skeleton className="h-64 w-full" />}>
            <MarginTrendChart points={trend.data.points} currency={currency} />
          </React.Suspense>
        )}
      </ChartCard>

      <RevenuePanels customerId={customerId} />

      <BusinessRollup externalId={margin.external_id} range={range} />
    </div>
  );
}
