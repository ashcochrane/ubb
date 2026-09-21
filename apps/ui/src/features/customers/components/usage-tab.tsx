import * as React from "react";
import { Link } from "@tanstack/react-router";
import { ArrowUpRight } from "lucide-react";

import { ChartCard } from "@/components/shared/chart-card";
import { EmptyState } from "@/components/shared/empty-state";
import { ErrorCard } from "@/components/shared/error-card";
import { StatCard } from "@/components/shared/stat-card";
import { buttonVariants } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useTenantCurrency } from "@/hooks/use-tenant-config";
import type { DateRange } from "@/lib/date-range";
import {
  MeasureValue,
  RetentionHorizonNote,
  RevenueContext,
} from "@/components/shared/measure-value";
import { figureNote, isNegative, noFigureNote } from "@/lib/measure-state";
import { cn } from "@/lib/utils";

import { useUsageAnalytics, useUsageTimeseries } from "../api/queries";

const UsageTimeseriesChart = React.lazy(() => import("./usage-timeseries-chart"));

export function UsageTab({
  customerId,
  range,
  stopsAndBreaches,
}: {
  customerId: string;
  range: DateRange;
  /**
   * Stops and breaches, filtered to this customer — the spend-controls
   * feature's component, injected by the route (#466). One rendering, two
   * hosts: the Spend controls tab renders it tenant-wide and this tab renders
   * the same component with the customer fixed. It is injected rather than
   * imported because a feature may not import another's components; a tab
   * missing its injection renders nothing in the section's place rather than
   * a second copy of the report.
   */
  stopsAndBreaches?: React.ReactNode;
}) {
  const currency = useTenantCurrency();
  const analytics = useUsageAnalytics(customerId, range);
  const timeseries = useUsageTimeseries(customerId, range);

  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        {/* Typed router Link (SPA navigation) — eventsSearchSchema accepts customer_id. */}
        <Link
          to="/events"
          search={{ customer_id: customerId }}
          className={buttonVariants({ variant: "outline", size: "sm" })}
        >
          Open in events ledger <ArrowUpRight data-icon="inline-end" />
        </Link>
      </div>

      {analytics.isLoading ? (
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          {Array.from({ length: 4 }, (_, index) => (
            <Skeleton key={index} className="h-24 w-full" />
          ))}
        </div>
      ) : analytics.isError ? (
        <ErrorCard error={analytics.error} onRetry={() => void analytics.refetch()} />
      ) : analytics.data ? (
        // ⚠ THESE CARDS WERE THE CONSOLE'S LAST "?? 0" ON A MEASURE (#510).
        // The margin card rendered a margin UBB would not state as "$0.00",
        // and the event card a count that did not arrive as "0"; both now draw
        // the figure as its state allows. The labels are the events strip's —
        // #501 retired "Markup margin" there as naming neither thing, and the
        // same measure on this tab kept the retired name.
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <StatCard
            label="Events"
            value={<MeasureValue figure={analytics.data.events} currency={currency} />}
            variant="raised"
          />
          <StatCard
            label="Revenue"
            value={<MeasureValue figure={analytics.data.revenue} currency={currency} />}
            variant="raised"
            subtitle={figureNote(analytics.data.revenue, currency)}
          />
          <StatCard
            label="Provider cost"
            value={<MeasureValue figure={analytics.data.cost} currency={currency} />}
            variant="raised"
            subtitle={figureNote(analytics.data.cost, currency)}
          />
          <StatCard
            label="Gross margin"
            value={
              <span className={cn(isNegative(analytics.data.margin) && "text-danger-dark")}>
                <MeasureValue figure={analytics.data.margin} currency={currency} />
              </span>
            }
            variant="raised"
            subtitle={
              noFigureNote(analytics.data.margin, currency) ?? "Revenue minus provider cost"
            }
          />
        </div>
      ) : null}

      <ChartCard title="Daily spend">
        {timeseries.isLoading ? (
          <Skeleton className="h-56 w-full" />
        ) : timeseries.isError ? (
          <ErrorCard error={timeseries.error} onRetry={() => void timeseries.refetch()} />
        ) : !timeseries.data || timeseries.data.points.length === 0 ? (
          timeseries.data && timeseries.data.held_from !== null ? (
            <RetentionHorizonNote caveats={timeseries.data} />
          ) : (
            <EmptyState
              title="No usage in this window"
              description="Recorded events will chart here by day."
            />
          )
        ) : (
          <>
            <React.Suspense fallback={<Skeleton className="h-56 w-full" />}>
              <UsageTimeseriesChart
                points={timeseries.data.points}
                currency={currency}
              />
            </React.Suspense>
            <RevenueContext context={timeseries.data.context} currency={currency} />
            <RetentionHorizonNote caveats={timeseries.data} />
          </>
        )}
      </ChartCard>

      {stopsAndBreaches}
    </div>
  );
}
