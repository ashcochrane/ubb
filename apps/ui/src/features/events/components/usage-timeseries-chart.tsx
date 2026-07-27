// The Recharts line chart for the daily cost timeseries. Lazily imported by
// the chart card, so this module (and Recharts) stays out of the main bundle.

import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { formatCostMicros, formatMicros, formatShortDate } from "@/lib/format";

import type { ChartSeries } from "../lib/timeseries";

/**
 * Buckets arrive as day-truncated UTC datetimes ("2026-07-01T00:00:00Z").
 * Slice to the bare calendar date so formatShortDate routes through its
 * UTC path — otherwise viewers west of Greenwich see the previous day.
 */
function bucketLabel(value: unknown): string {
  return formatShortDate(String(value).slice(0, 10));
}

export default function UsageTimeseriesChart({
  data,
  series,
  currency,
}: {
  data: Array<Record<string, number | string>>;
  series: ChartSeries[];
  currency: string;
}) {
  return (
    <div className="h-[260px] w-full">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 6, right: 8, bottom: 0, left: 0 }}>
          <CartesianGrid stroke="var(--chart-grid)" vertical={false} />
          <XAxis
            dataKey="bucket"
            tickFormatter={bucketLabel}
            tick={{ fill: "var(--color-text-muted)", fontSize: 11 }}
            tickLine={false}
            axisLine={false}
            minTickGap={28}
          />
          <YAxis
            tickFormatter={(value) =>
              formatCostMicros(typeof value === "number" ? value : 0, currency)
            }
            tick={{ fill: "var(--color-text-muted)", fontSize: 11 }}
            tickLine={false}
            axisLine={false}
            width={64}
          />
          <Tooltip
            formatter={(value, name) => [
              formatMicros(typeof value === "number" ? value : 0, currency),
              typeof name === "string" ? name : "",
            ]}
            labelFormatter={bucketLabel}
            contentStyle={{
              background: "var(--color-bg-surface)",
              border: "1px solid var(--color-border)",
              borderRadius: 8,
              fontSize: 12,
            }}
          />
          {series.map((entry) => (
            <Line
              key={entry.key}
              type="monotone"
              dataKey={entry.key}
              name={entry.label}
              stroke={entry.color}
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 3 }}
              isAnimationActive={false}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
