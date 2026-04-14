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
import type { CostByProductPoint, CostSeries } from "../api/types";

interface CostBreakdownChartProps {
  title: string;
  series: CostSeries[];
  data: CostByProductPoint[];
}

export function CostBreakdownChart({ title, series, data }: CostBreakdownChartProps) {
  const [primary, ...rest] = series;

  return (
    <ChartCard
      title={title}
      legend={
        <ChartLegend
          variant="dot"
          items={series.map((s) => ({ label: s.label, color: s.color }))}
        />
      }
    >
      <div
        role="img"
        aria-label={`${title} over the selected time range`}
        className="h-[180px] w-full"
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
              width={48}
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
            {primary && (
              <Area
                type="monotone"
                dataKey={primary.key}
                name={primary.label}
                stroke={primary.color}
                fill={primary.color}
                fillOpacity={0.07}
                strokeWidth={1.8}
                isAnimationActive={false}
              />
            )}
            {rest.map((s) => (
              <Line
                key={s.key}
                type="monotone"
                dataKey={s.key}
                name={s.label}
                stroke={s.color}
                strokeWidth={1.5}
                dot={false}
                isAnimationActive={false}
              />
            ))}
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </ChartCard>
  );
}
