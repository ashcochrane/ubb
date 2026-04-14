import { StatCard } from "@/components/shared/stat-card";
import { Sparkline } from "@/components/shared/sparkline";
import type { SparklineSet, StatsData } from "../api/types";
import {
  CHART_GREEN,
  CHART_RED,
  CHART_STONE,
  CHART_TERRACOTTA,
} from "../lib/chart-colors";

interface StatsGridProps {
  stats: StatsData;
  sparklines: SparklineSet;
}

export function StatsGrid({ stats, sparklines }: StatsGridProps) {
  return (
    <div className="grid grid-cols-5 gap-3.5">
      <StatCard
        variant="raised"
        label="Revenue"
        value={`$${stats.revenue.toLocaleString()}`}
        trend={signedTrend(stats.revenuePrevChange)}
        trendLabel={signedPercent(stats.revenuePrevChange)}
        sparkline={<Sparkline data={sparklines.revenue} color={CHART_TERRACOTTA} />}
      />
      <StatCard
        variant="raised"
        label="API costs"
        // Inverted trend: costs going DOWN is good ("up" in UX terms).
        value={`$${stats.apiCosts.toLocaleString()}`}
        trend={signedTrend(-stats.costsPrevChange)}
        trendLabel={signedPercent(stats.costsPrevChange)}
        sparkline={<Sparkline data={sparklines.apiCosts} color={CHART_RED} />}
      />
      <StatCard
        variant="raised"
        label="Gross margin"
        value={`$${stats.grossMargin.toLocaleString()}`}
        trend={signedTrend(stats.marginPrevChange)}
        trendLabel={signedPercent(stats.marginPrevChange)}
        sparkline={<Sparkline data={sparklines.grossMargin} color={CHART_GREEN} />}
      />
      <StatCard
        variant="raised"
        label="Margin %"
        value={`${stats.marginPercentage}%`}
        trend={signedTrend(stats.marginPctPrevChange)}
        trendLabel={signedPoint(stats.marginPctPrevChange)}
        sparkline={<Sparkline data={sparklines.marginPct} color={CHART_TERRACOTTA} />}
      />
      <StatCard
        variant="raised"
        label="Cost / $1 rev"
        value={`$${stats.costPerDollarRevenue.toFixed(3)}`}
        trend={costPerRevTrend(stats.costPerRevPrevChange)}
        trendLabel={deadbandPercent(stats.costPerRevPrevChange)}
        sparkline={<Sparkline data={sparklines.costPerRev} color={CHART_STONE} />}
      />
    </div>
  );
}

// Trend label helpers. Each returns the human-readable "vs prev" suffix so the
// 5 call sites above stay short and symmetric.
function signedPercent(value: number): string {
  const sign = value > 0 ? "+" : "";
  return `${sign}${value}% vs prev`;
}

function signedPoint(value: number): string {
  const sign = value > 0 ? "+" : "";
  return `${sign}${value}pp vs prev`;
}

function deadbandPercent(value: number): string {
  return `±${Math.abs(value)}% vs prev`;
}

// Signed trend: exact zero is flat (not down).
function signedTrend(delta: number): "up" | "down" | "flat" {
  if (delta === 0) return "flat";
  return delta > 0 ? "up" : "down";
}

// Cost-per-revenue has a wider deadband: small changes render flat, not up/down.
function costPerRevTrend(delta: number): "up" | "down" | "flat" {
  if (Math.abs(delta) < 1) return "flat";
  return delta < 0 ? "up" : "down";
}
