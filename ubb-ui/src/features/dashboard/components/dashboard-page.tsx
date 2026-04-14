import { lazy, Suspense, useState } from "react";
import { PageHeader } from "@/components/shared/page-header";
import { Skeleton } from "@/components/ui/skeleton";
import { useDashboard } from "../api/queries";
import type { TimeRange } from "../api/types";
import { CHART_TERRACOTTA } from "../lib/chart-colors";
import { BreakdownCard } from "./breakdown-card";
import { CustomerTable } from "./customer-table";
import { ScopeBar } from "./scope-bar";
import { StatsGrid } from "./stats-grid";

const RevenueChart = lazy(() =>
  import("./revenue-chart").then((m) => ({ default: m.RevenueChart })),
);
const CostBreakdownChart = lazy(() =>
  import("./cost-breakdown-chart").then((m) => ({ default: m.CostBreakdownChart })),
);

export function DashboardPage() {
  const { data, isLoading } = useDashboard();
  const [timeRange, setTimeRange] = useState<TimeRange>("30d");

  if (isLoading || !data) {
    return (
      <div className="space-y-7 px-10 pt-8 pb-20">
        <PageHeader title="Dashboard" />
        <Skeleton className="h-12 rounded-md" />
        <div className="grid grid-cols-5 gap-3.5">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-[120px] rounded-md" />
          ))}
        </div>
        <Skeleton className="h-[280px] rounded-md" />
        <div className="grid grid-cols-2 gap-4">
          <Skeleton className="h-[220px] rounded-md" />
          <Skeleton className="h-[220px] rounded-md" />
        </div>
        <div className="grid grid-cols-2 gap-4">
          <Skeleton className="h-[180px] rounded-md" />
          <Skeleton className="h-[180px] rounded-md" />
        </div>
        <Skeleton className="h-[340px] rounded-md" />
      </div>
    );
  }

  return (
    <div className="space-y-7 px-10 pt-8 pb-20">
      <PageHeader
        title="Dashboard"
        description="Profitability overview across all products and customers."
      />

      <ScopeBar timeRange={timeRange} onTimeRangeChange={setTimeRange} />

      <StatsGrid stats={data.stats} sparklines={data.sparklines} />

      <Suspense fallback={<Skeleton className="h-[280px] w-full rounded-md" />}>
        <RevenueChart data={data.revenueTimeSeries} />
      </Suspense>

      <div className="grid grid-cols-2 gap-4">
        <Suspense fallback={<Skeleton className="h-[220px] w-full rounded-md" />}>
          <CostBreakdownChart
            title="Cost by product"
            series={data.costByProduct.series}
            data={data.costByProduct.data}
          />
        </Suspense>
        <Suspense fallback={<Skeleton className="h-[220px] w-full rounded-md" />}>
          <CostBreakdownChart
            title="Cost by pricing card"
            series={data.costByCard.series}
            data={data.costByCard.data}
          />
        </Suspense>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <BreakdownCard title="Revenue by product" items={data.revenueByProduct} />
        <BreakdownCard
          title="Margin by product"
          items={data.marginByProduct}
          barColor={CHART_TERRACOTTA}
        />
      </div>

      <CustomerTable customers={data.customers} />
    </div>
  );
}
