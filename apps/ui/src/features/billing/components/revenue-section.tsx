import { Suspense, lazy } from "react";

import { useRevenueWindow } from "../api/queries";
import { ChartLegend } from "@/components/shared/chart-legend";
import { DateRangePicker } from "@/components/shared/date-range-picker";
import { EmptyState } from "@/components/shared/empty-state";
import { ErrorCard } from "@/components/shared/error-card";
import { StatCard } from "@/components/shared/stat-card";
import { Skeleton } from "@/components/ui/skeleton";
import { useTenantCurrency } from "@/hooks/use-tenant-config";
import { DATE_RANGE_PRESETS, resolveRange, type DateRange } from "@/lib/date-range";
import { formatEventCount, formatMicros } from "@/lib/format";
import { revenueBasisNote } from "@/lib/supplied-revenue";
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
  const query = useRevenueWindow(resolved);

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
          const { daily, event_count: eventTotal } = query.data;
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
                  label="Revenue"
                  value={formatMicros(query.data.revenue_micros, currency)}
                  subtitle={`${formatEventCount(eventTotal)} events`}
                />
                <StatCard
                  label="Provider cost"
                  value={supplierCostTotal(
                    query.data.provider_cost_micros,
                    query.data,
                    currency,
                  )}
                  subtitle={
                    partialTotalNote(query.data.unresolved_event_count) ?? undefined
                  }
                />
                {/* ⚠ "MARKUP" WAS NEITHER A MARKUP NOR A MARGIN (#501) — it
                    was billed minus supplier cost over a window, published
                    under a name that suggested a rate. It is the gross-margin
                    measure now, and a window UBB cannot state one for renders
                    as an absence rather than as zero. */}
                <StatCard
                  label="Gross margin"
                  value={
                    query.data.margin_micros === null
                      ? "—"
                      : marginBound(query.data.margin_micros, query.data, currency)
                  }
                  subtitle="Revenue minus provider cost"
                />
              </div>
              <div className="flex justify-end">
                <ChartLegend items={LEGEND_ITEMS} variant="line" />
              </div>
              <Suspense fallback={<Skeleton className="h-[240px] w-full" />}>
                <RevenueChart data={daily} currency={currency} />
              </Suspense>
              {/* ⚠ **THE BILLED FIGURE INCLUDES WHAT TENANTS SUPPLIED, AND ONE
                  OF THE TWO VIEWS SPREADS IT (§5).** This window sums three
                  revenue sources, so it has no single source reference and no
                  single recognition method to show — what it owes instead is
                  the view it was drawn under, which the one economic query
                  states on every answer. Without it a tenant reading a day's
                  revenue cannot tell a figure earned that day from a slice of
                  one earned across a quarter. */}
              <p
                data-revenue-basis={query.data.basis}
                className="text-[11px] text-text-muted"
              >
                {revenueBasisNote(query.data.basis)}
              </p>
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
