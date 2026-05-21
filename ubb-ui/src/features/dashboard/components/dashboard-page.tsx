import { lazy, Suspense, useState } from "react";
import { PageHeader } from "@/components/shared/page-header";
import { Skeleton } from "@/components/ui/skeleton";
import {
  useDashboardStats,
  useDashboardCharts,
  useDashboardCustomers,
} from "../api/queries";
import type { TimeRange } from "../api/types";
import { CHART_TERRACOTTA } from "../lib/chart-colors";
import { BreakdownCard } from "./breakdown-card";
import { CustomerTable } from "./customer-table";
import { GettingStarted } from "./getting-started";
import { ScopeBar } from "./scope-bar";
import { StatsGrid } from "./stats-grid";

const RevenueChart = lazy(() =>
  import("./revenue-chart").then((m) => ({ default: m.RevenueChart })),
);
const CostBreakdownChart = lazy(() =>
  import("./cost-breakdown-chart").then((m) => ({ default: m.CostBreakdownChart })),
);

export function DashboardPage() {
  const [timeRange, setTimeRange] = useState<TimeRange>("30d");

  const statsQuery    = useDashboardStats(timeRange);
  const chartsQuery   = useDashboardCharts(timeRange);
  const customersQuery = useDashboardCustomers(timeRange);

  const statsLoading     = statsQuery.isLoading    || !statsQuery.data;
  const chartsLoading    = chartsQuery.isLoading   || !chartsQuery.data;
  const customersLoading = customersQuery.isLoading || !customersQuery.data;

  return (
    <div className="space-y-7 px-10 pt-8 pb-20">
      <PageHeader
        title="Dashboard"
        description="Profitability overview across all products and customers."
      />

      <GettingStarted />

      <ScopeBar timeRange={timeRange} onTimeRangeChange={setTimeRange} />

      {/* Stats — independent loading */}
      {statsLoading ? (
        <div className="grid grid-cols-5 gap-3.5">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-[120px] rounded-md" />
          ))}
        </div>
      ) : (
        <StatsGrid
          stats={statsQuery.data!}
          sparklines={statsQuery.data!.sparklines}
        />
      )}

      {/* Revenue + margin chart — independent loading */}
      <Suspense fallback={<Skeleton className="h-[280px] w-full rounded-md" />}>
        {chartsLoading ? (
          <Skeleton className="h-[280px] w-full rounded-md" />
        ) : (
          <RevenueChart data={chartsQuery.data!.revenueTimeSeries} />
        )}
      </Suspense>

      {/* Cost breakdown charts — independent loading */}
      <div className="grid grid-cols-2 gap-4">
        <Suspense fallback={<Skeleton className="h-[220px] w-full rounded-md" />}>
          {chartsLoading ? (
            <Skeleton className="h-[220px] w-full rounded-md" />
          ) : (
            <CostBreakdownChart
              title="Cost by group"
              series={chartsQuery.data!.costByGroup.series}
              data={chartsQuery.data!.costByGroup.data}
            />
          )}
        </Suspense>
        <Suspense fallback={<Skeleton className="h-[220px] w-full rounded-md" />}>
          {chartsLoading ? (
            <Skeleton className="h-[220px] w-full rounded-md" />
          ) : (
            <CostBreakdownChart
              title="Cost by pricing card"
              series={chartsQuery.data!.costByCard.series}
              data={chartsQuery.data!.costByCard.data}
            />
          )}
        </Suspense>
      </div>

      {/* Group breakdowns — independent loading */}
      <div className="grid grid-cols-2 gap-4">
        {chartsLoading ? (
          <>
            <Skeleton className="h-[180px] rounded-md" />
            <Skeleton className="h-[180px] rounded-md" />
          </>
        ) : (
          <>
            <BreakdownCard
              title="Revenue by group"
              items={chartsQuery.data!.revenueByGroup}
            />
            <BreakdownCard
              title="Margin by group"
              items={chartsQuery.data!.marginByGroup}
              barColor={CHART_TERRACOTTA}
            />
          </>
        )}
      </div>

      {/* Customer table — independent loading */}
      {customersLoading ? (
        <Skeleton className="h-[340px] rounded-md" />
      ) : (
        <CustomerTable customers={customersQuery.data!.customers} />
      )}
    </div>
  );
}
