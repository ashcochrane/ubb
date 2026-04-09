// src/features/dashboard/components/stats-grid.tsx
import { cn } from "@/lib/utils";
import type { StatsData } from "../api/types";

interface StatsGridProps {
  stats: StatsData;
}

interface StatCardProps {
  label: string;
  value: string;
  change: string;
  positive: boolean;
  /** Apply green color to the value (e.g. for margin stats) */
  greenValue?: boolean;
}

function StatCard({ label, value, change, positive, greenValue }: StatCardProps) {
  return (
    <div className="rounded-lg bg-accent/50 px-3 py-2.5">
      <div className="text-[11px] text-muted-foreground">{label}</div>
      <div className={cn(
        "mt-1 text-[17px] font-semibold tracking-tight",
        greenValue && "text-[#3B6D11]",
      )}>
        {value}
      </div>
      <div className="mt-0.5 text-[10px] text-muted-foreground/60">
        {positive ? "+" : ""}{change}
      </div>
    </div>
  );
}

export function StatsGrid({ stats }: StatsGridProps) {
  return (
    <div className="grid grid-cols-5 gap-2">
      <StatCard
        label="Revenue"
        value={`$${stats.revenue.toLocaleString()}`}
        change={`${stats.revenuePrevChange}% vs prev`}
        positive={stats.revenuePrevChange > 0}
      />
      <StatCard
        label="API costs"
        value={`$${stats.apiCosts.toLocaleString()}`}
        change={`${stats.costsPrevChange}% vs prev`}
        positive={stats.costsPrevChange < 0}
      />
      <StatCard
        label="Gross margin"
        value={`$${stats.grossMargin.toLocaleString()}`}
        change={`${stats.marginPrevChange}% vs prev`}
        positive={stats.marginPrevChange > 0}
        greenValue
      />
      <StatCard
        label="Margin %"
        value={`${stats.marginPercentage}%`}
        change={`${stats.marginPctPrevChange}pp vs prev`}
        positive={stats.marginPctPrevChange > 0}
        greenValue
      />
      <StatCard
        label="Cost / $1 rev"
        value={`$${stats.costPerDollarRevenue}`}
        change={`${stats.costPerRevPrevChange}% vs prev`}
        positive={stats.costPerRevPrevChange < 0}
      />
    </div>
  );
}
