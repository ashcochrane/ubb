// Lazy-loaded (React.lazy) Recharts line chart for the revenue window.
// Monochrome discipline: chart tokens only, 2px lines, no dots, tooltip
// always, axis text in text tokens.

import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import {
  MeasureTooltip,
  type TooltipSeries,
} from "@/components/shared/measure-value";
import { formatCostMicros, formatShortDate } from "@/lib/format";

import type { RevenueDailyRow } from "../api/types";

/** The plotted series, by the data key each row and its figure share. The
 *  margin is the query's own measure, never recomputed here (#510). */
const SERIES = [
  { key: "revenue_micros", name: "Revenue", color: "var(--chart-1)" },
  { key: "provider_cost_micros", name: "Provider cost", color: "var(--chart-2)" },
  { key: "margin_micros", name: "Gross margin", color: "var(--chart-3)" },
] as const satisfies readonly (TooltipSeries & { key: keyof RevenueDailyRow })[];

function dayLabel(label: string | number | undefined): string {
  return typeof label === "string" ? formatShortDate(label) : String(label ?? "");
}

export default function RevenueChart({
  data,
  currency,
}: {
  data: RevenueDailyRow[];
  currency: string;
}) {
  return (
    <div className="h-[240px] w-full" aria-label="Daily revenue chart">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
          <CartesianGrid stroke="var(--chart-grid)" vertical={false} />
          <XAxis
            dataKey="day"
            tickFormatter={formatShortDate}
            tick={{ fill: "var(--color-text-muted)", fontSize: 11 }}
            tickLine={false}
            axisLine={{ stroke: "var(--chart-grid)" }}
            minTickGap={32}
          />
          <YAxis
            tickFormatter={(value: number) => formatCostMicros(value, currency)}
            tick={{ fill: "var(--color-text-muted)", fontSize: 11 }}
            tickLine={false}
            axisLine={false}
            width={64}
          />
          <Tooltip
            filterNull={false}
            content={
              <MeasureTooltip
                series={SERIES}
                currency={currency}
                labelFormatter={dayLabel}
              />
            }
            cursor={{ stroke: "var(--chart-grid)" }}
          />
          {SERIES.map((series) => (
            <Line
              key={series.key}
              type="monotone"
              dataKey={series.key}
              name={series.name}
              stroke={series.color}
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
