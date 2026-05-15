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
import { formatCostMicros } from "@/lib/format";
import type { StackedSeries } from "../api/types";

// Client-side color palette — assigned by index, never from the API.
const COLOR_PALETTE = [
  "#4a7fa8",
  "#6a5aaa",
  "#b84848",
  "#a16a4a",
  "#b5ad9e",
  "#3a8050",
  "#9a8e80",
];

function paletteColor(index: number): string {
  return COLOR_PALETTE[index % COLOR_PALETTE.length]!;
}

interface CostBreakdownChartProps {
  title: string;
  series: StackedSeries["series"];
  data: StackedSeries["data"];
}

export function CostBreakdownChart({ title, series, data }: CostBreakdownChartProps) {
  const [primary, ...rest] = series;

  return (
    <ChartCard
      title={title}
      legend={
        <ChartLegend
          variant="dot"
          items={series.map((s, i) => ({ label: s.label, color: paletteColor(i) }))}
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
              dataKey="date"
              tick={{ fontSize: 10, fill: "var(--color-text-muted)" }}
              tickLine={false}
              axisLine={false}
              interval="preserveStartEnd"
            />
            <YAxis
              tick={{ fontSize: 10, fill: "var(--color-text-muted)" }}
              tickLine={false}
              axisLine={false}
              tickFormatter={(v: number) => formatCostMicros(v)}
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
                value == null ? "—" : formatCostMicros(Number(value)),
                name,
              ]}
            />
            {primary && (
              <Area
                type="monotone"
                dataKey={primary.key}
                name={primary.label}
                stroke={paletteColor(0)}
                fill={paletteColor(0)}
                fillOpacity={0.07}
                strokeWidth={1.8}
                isAnimationActive={false}
              />
            )}
            {rest.map((s, i) => (
              <Line
                key={s.key}
                type="monotone"
                dataKey={s.key}
                name={s.label}
                stroke={paletteColor(i + 1)}
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
