import { Suspense, lazy } from "react";

import { toRevenueDailyRow } from "../api/types";
import { useRevenueAnalytics } from "../api/queries";
import { ChartLegend } from "@/components/shared/chart-legend";
import { DateRangePicker } from "@/components/shared/date-range-picker";
import { EmptyState } from "@/components/shared/empty-state";
import { ErrorCard } from "@/components/shared/error-card";
import { StatCard } from "@/components/shared/stat-card";
import { Skeleton } from "@/components/ui/skeleton";
import { useTenantCurrency } from "@/hooks/use-tenant-config";
import { DATE_RANGE_PRESETS, resolveRange, type DateRange } from "@/lib/date-range";
import { formatEventCount, formatMicros } from "@/lib/format";
import {
  marginBound,
  partialTotalNote,
  supplierCostTotal,
} from "@/lib/supplier-cost";
import { cn } from "@/lib/utils";

import { SectionCard } from "./section-card";

const RevenueChart = lazy(() => import("./revenue-chart"));

const LEGEND_ITEMS = [
  { label: "Billed", color: "var(--chart-1)" },
  { label: "Provider cost", color: "var(--chart-2)" },
  { label: "Markup", color: "var(--chart-3)" },
];

export function RevenueSection({
  range,
  onRangeChange,
}: {
  range: DateRange;
  onRangeChange: (next: DateRange) => void;
}) {
  const resolved = resolveRange(range);
  const currency = useTenantCurrency();
  const query = useRevenueAnalytics(resolved);

  return (
    <SectionCard
      title="Revenue"
      description="What customers were billed vs. what providers cost you, day by day."
      actions={<DateRangePicker value={resolved} onChange={onRangeChange} />}
    >
      {query.isLoading ? (
        <RevenueSkeleton />
      ) : query.isError ? (
        <ErrorCard error={query.error} onRetry={() => void query.refetch()} />
      ) : query.data ? (
        (() => {
          const daily = query.data.daily.map(toRevenueDailyRow);
          const eventTotal = daily.reduce((sum, row) => sum + row.event_count, 0);
          if (daily.length === 0) {
            return (
              <EmptyState
                title="No usage in this window"
                description="Nothing was billed between these dates. Try a wider window."
                action={{
                  label: "Show last 90 days",
                  onClick: () => {
                    const preset = DATE_RANGE_PRESETS.find((p) => p.key === "90d");
                    if (preset) onRangeChange(preset.range());
                  },
                }}
              />
            );
          }
          return (
            <div
              className={cn(
                "space-y-4 transition-opacity",
                query.isPlaceholderData && "opacity-60",
              )}
            >
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                <StatCard
                  label="Billed"
                  value={formatMicros(query.data.total_billed_cost_micros, currency)}
                  subtitle={`${formatEventCount(eventTotal)} events`}
                />
                <StatCard
                  label="Provider cost"
                  value={supplierCostTotal(
                    query.data.total_provider_cost_micros,
                    query.data,
                    currency,
                  )}
                  subtitle={
                    partialTotalNote(query.data.unresolved_event_count) ?? undefined
                  }
                />
                <StatCard
                  label="Markup"
                  value={marginBound(
                    query.data.total_markup_micros,
                    query.data,
                    currency,
                  )}
                  subtitle="Billed minus provider cost"
                />
              </div>
              <div className="flex justify-end">
                <ChartLegend items={LEGEND_ITEMS} variant="line" />
              </div>
              <Suspense fallback={<Skeleton className="h-[240px] w-full" />}>
                <RevenueChart data={daily} currency={currency} />
              </Suspense>
            </div>
          );
        })()
      ) : null}
    </SectionCard>
  );
}

function RevenueSkeleton() {
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <Skeleton className="h-16 w-full" />
        <Skeleton className="h-16 w-full" />
        <Skeleton className="h-16 w-full" />
      </div>
      <Skeleton className="h-[240px] w-full" />
    </div>
  );
}
