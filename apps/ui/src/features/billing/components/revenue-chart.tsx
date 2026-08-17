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
  BoundedCostTooltip,
  type SeriesRole,
} from "@/components/shared/supplier-cost";
import { formatCostMicros, formatShortDate } from "@/lib/format";

import type { RevenueDailyRow } from "../api/types";

interface ChartRow extends RevenueDailyRow {
  markup_micros: number;
}

const SERIES: { key: keyof ChartRow; label: string; color: string }[] = [
  { key: "billed_cost_micros", label: "Billed", color: "var(--chart-1)" },
  { key: "provider_cost_micros", label: "Provider cost", color: "var(--chart-2)" },
  { key: "markup_micros", label: "Markup", color: "var(--chart-3)" },
];

/** Which bounding rule each plotted series obeys (#330). */
function roleOf(dataKey: string): SeriesRole {
  if (dataKey === "provider_cost_micros") return "supplier-cost";
  if (dataKey === "markup_micros") return "margin";
  // Billed is NOT NULL at the column and whole by construction.
  return "whole";
}

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
  const chartData: ChartRow[] = data.map((row) => ({
    ...row,
    markup_micros: row.billed_cost_micros - row.provider_cost_micros,
  }));

  return (
    <div className="h-[240px] w-full" aria-label="Daily revenue chart">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={chartData} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
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
            content={
              <BoundedCostTooltip
                currency={currency}
                labelFormatter={dayLabel}
                roleOf={roleOf}
              />
            }
            cursor={{ stroke: "var(--chart-grid)" }}
          />
          {SERIES.map((series) => (
            <Line
              key={series.key}
              type="monotone"
              dataKey={series.key}
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
