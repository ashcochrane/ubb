import { Suspense, lazy } from "react";

import { useRevenueWindow } from "../api/queries";
import { ChartLegend } from "@/components/shared/chart-legend";
import { DateRangePicker } from "@/components/shared/date-range-picker";
import { EmptyState } from "@/components/shared/empty-state";
import { ErrorCard } from "@/components/shared/error-card";
import {
  MeasureValue,
  RetentionHorizonNote,
  RevenueContext,
} from "@/components/shared/measure-value";
import { StatCard } from "@/components/shared/stat-card";
import { Skeleton } from "@/components/ui/skeleton";
import { useTenantCurrency } from "@/hooks/use-tenant-config";
import { DATE_RANGE_PRESETS, resolveRange, type DateRange } from "@/lib/date-range";
import {
  figureNote,
  isNegative,
  noFigureNote,
  readingText,
  readMeasure,
} from "@/lib/measure-state";
import { revenueBasisNote } from "@/lib/supplied-revenue";
import { cn } from "@/lib/utils";

import { SectionCard } from "./section-card";

const RevenueChart = lazy(() => import("./revenue-chart"));

// The legend names what the lines plot. It read "Billed" and "Markup" after
// #501 renamed the lines and the cards to Revenue and Gross margin — the
// retired names on the one element that tells a reader which line is which.
const LEGEND_ITEMS = [
  { label: "Revenue", color: "var(--chart-1)" },
  { label: "Provider cost", color: "var(--chart-2)" },
  { label: "Gross margin", color: "var(--chart-3)" },
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
          const { daily } = query.data;
          if (daily.length === 0) {
            // ⚠ "NO USAGE" ONLY WHERE THE WINDOW IS INSIDE THE RECORDS IT
            // READS; past their horizon it is a stretch UBB no longer holds.
            if (query.data.held_from !== null) {
              return <RetentionHorizonNote caveats={query.data} />;
            }
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
                {/* ⚠ THE THREE TOTALS ARE FOLDED FROM THE DAYS WITH THEIR
                    STATES (#510): the worst day's state wins, so a window with
                    a day UBB no longer holds reads as that state rather than
                    as a smaller figure presented as whole. */}
                <StatCard
                  label="Revenue"
                  value={<MeasureValue figure={query.data.revenue} currency={currency} />}
                  subtitle={
                    figureNote(query.data.revenue, currency) ??
                    `${readingText(readMeasure(query.data.events, currency))} events`
                  }
                />
                <StatCard
                  label="Provider cost"
                  value={<MeasureValue figure={query.data.cost} currency={currency} />}
                  subtitle={figureNote(query.data.cost, currency)}
                />
                {/* ⚠ "MARKUP" WAS NEITHER A MARKUP NOR A MARGIN (#501) — it
                    was billed minus supplier cost over a window, published
                    under a name that suggested a rate. It is the gross-margin
                    measure now, drawn as its state allows. */}
                <StatCard
                  label="Gross margin"
                  value={
                    <span className={cn(isNegative(query.data.margin) && "text-destructive")}>
                      <MeasureValue figure={query.data.margin} currency={currency} />
                    </span>
                  }
                  subtitle={
                    noFigureNote(query.data.margin, currency) ?? "Revenue minus provider cost"
                  }
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
              <RevenueContext context={query.data.context} currency={currency} />
              <RetentionHorizonNote caveats={query.data} />
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
