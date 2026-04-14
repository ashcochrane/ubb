import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { ChartCard } from "@/components/shared/chart-card";
import { ChartLegend } from "@/components/shared/chart-legend";
import { formatDollars } from "@/lib/format";
import type { RevenueTimeSeries } from "../api/types";
import {
  CHART_MARGIN_DASH,
  CHART_RED,
  CHART_TERRACOTTA,
} from "../lib/chart-colors";

interface RevenueChartProps {
  data: RevenueTimeSeries[];
}

export function RevenueChart({ data }: RevenueChartProps) {
  return (
    <ChartCard
      title="Revenue and margin"
      legend={
        <ChartLegend
          variant="line"
          items={[
            { label: "Revenue", color: CHART_TERRACOTTA },
            { label: "API costs", color: CHART_RED },
            { label: "Margin", color: CHART_MARGIN_DASH, dashed: true },
          ]}
        />
      }
    >
      <div
        role="img"
        aria-label="Revenue, API costs, and margin over the selected time range"
        className="h-[240px] w-full"
      >
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" vertical={false} />
            <XAxis
              dataKey="label"
              tick={{ fontSize: 10, fill: "var(--color-text-muted)" }}
              tickLine={false}
              axisLine={false}
              interval="preserveStartEnd"
            />
            <YAxis
              tick={{ fontSize: 10, fill: "var(--color-text-muted)" }}
              tickLine={false}
              axisLine={false}
              tickFormatter={(v: number) => formatDollars(v)}
              width={56}
            />
            <Tooltip
              contentStyle={{
                fontSize: 11,
                borderRadius: 8,
                border: "1px solid var(--color-border)",
                background: "var(--color-card)",
              }}
              formatter={(value, name) => [
                value == null ? "—" : formatDollars(Number(value)),
                name,
              ]}
            />
            <Area
              type="monotone"
              dataKey="revenue"
              name="Revenue"
              stroke={CHART_TERRACOTTA}
              fill={CHART_TERRACOTTA}
              fillOpacity={0.07}
              strokeWidth={2}
              isAnimationActive={false}
            />
            <Area
              type="monotone"
              dataKey="apiCosts"
              name="API costs"
              stroke={CHART_RED}
              fill={CHART_RED}
              fillOpacity={0.05}
              strokeWidth={1.5}
              isAnimationActive={false}
            />
            <Line
              type="monotone"
              dataKey="margin"
              name="Margin"
              stroke={CHART_MARGIN_DASH}
              strokeWidth={1.5}
              strokeDasharray="5 3"
              dot={false}
              isAnimationActive={false}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </ChartCard>
  );
}
