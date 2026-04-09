import { useState } from "react";
import { PageHeader } from "@/components/shared/page-header";
import { Skeleton } from "@/components/ui/skeleton";
import { useDashboard } from "../api/queries";
import type { TimeRange } from "../api/types";
import { ScopeBar } from "./scope-bar";
import { StatsGrid } from "./stats-grid";
import { RevenueChart } from "./revenue-chart";
import { CostBreakdownChart } from "./cost-breakdown-chart";
import { BreakdownCard } from "./breakdown-card";
import { CustomerTable } from "./customer-table";

export function DashboardPage() {
  const { data, isLoading } = useDashboard();
  const [timeRange, setTimeRange] = useState<TimeRange>("30d");

  if (isLoading || !data) {
    return (
      <div className="space-y-5">
        <PageHeader title="Dashboard" />
        <Skeleton className="h-20 rounded-xl" />
        <div className="grid grid-cols-5 gap-2">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-20 rounded-xl" />
          ))}
        </div>
        <Skeleton className="h-60 rounded-xl" />
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <PageHeader
        title="Dashboard"
        description="Profitability overview across all products and customers."
      />

      <ScopeBar timeRange={timeRange} onTimeRangeChange={setTimeRange} />

      <StatsGrid stats={data.stats} />

      <RevenueChart data={data.revenueTimeSeries} />

      <div className="grid grid-cols-2 gap-4">
        <CostBreakdownChart
          title="Cost by product"
          series={data.costByProduct.series}
          data={data.costByProduct.data}
        />
        <CostBreakdownChart
          title="Cost by pricing card"
          series={data.costByCard.series}
          data={data.costByCard.data}
        />
      </div>

      <div className="grid grid-cols-2 gap-4">
        <BreakdownCard
          title="Revenue by product"
          items={data.revenueByProduct}
        />
        <BreakdownCard
          title="Margin by product"
          items={data.marginByProduct}
          barColor="#5DCAA5"
        />
      </div>

      {/* Customer profitability */}
      <div>
        <div className="mb-2 flex items-center justify-between">
          <span className="text-[13px] font-semibold">Customer profitability</span>
          <button className="rounded-lg border border-border px-3 py-1 text-[11px] text-muted-foreground hover:bg-accent">
            Export table
          </button>
        </div>
        <CustomerTable customers={data.customers} />
      </div>
    </div>
  );
}
