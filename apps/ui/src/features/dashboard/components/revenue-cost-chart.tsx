// Lazy-loaded (React.lazy) so Recharts stays out of the initial bundle —
// default export required.

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
import {
  formatCalendarDate,
  formatCostMicros,
  formatEventCount,
} from "@/lib/format";

import type { RevenueCostPoint } from "../api/types";

/** Day buckets are calendar dates (YYYY-MM-DD) — format in UTC so the day
 * never shifts for viewers west of Greenwich. */
function dayLabel(label: string | number | undefined): string {
  return typeof label === "string"
    ? formatCalendarDate(label)
    : String(label ?? "");
}

function eventCountLine(row: Record<string, unknown>): string | null {
  const count = row["event_count"];
  return typeof count === "number" ? `${formatEventCount(count)} events` : null;
}

export default function RevenueCostChart({
  points,
  showMargin,
  currency,
  revenueLabel,
}: {
  points: RevenueCostPoint[];
  showMargin: boolean;
  currency: string;
  revenueLabel: string;
}) {
  // Each series by the data key its point and its figure share — the key is
  // the contract, the name is copy.
  const series: TooltipSeries[] = [
    { key: "revenue_micros", name: revenueLabel, color: "var(--chart-1)" },
    { key: "provider_micros", name: "Provider cost", color: "var(--chart-2)" },
    ...(showMargin
      ? [{ key: "margin_micros", name: "Margin", color: "var(--chart-3)" }]
      : []),
  ];
  return (
    <div className="h-[280px] w-full">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={points} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid stroke="var(--chart-grid)" vertical={false} />
          <XAxis
            dataKey="day"
            tickFormatter={formatCalendarDate}
            tick={{ fontSize: 11, fill: "var(--color-text-muted)" }}
            tickLine={false}
            axisLine={false}
            minTickGap={28}
          />
          <YAxis
            tickFormatter={(value: number) => formatCostMicros(value, currency)}
            tick={{ fontSize: 11, fill: "var(--color-text-muted)" }}
            tickLine={false}
            axisLine={false}
            width={58}
          />
          <Tooltip
            filterNull={false}
            content={
              <MeasureTooltip
                series={series}
                currency={currency}
                labelFormatter={dayLabel}
                footer={eventCountLine}
              />
            }
            cursor={{ stroke: "var(--chart-grid)" }}
          />
          <Line
            dataKey="revenue_micros"
            name={revenueLabel}
            stroke="var(--chart-1)"
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 3 }}
            isAnimationActive={false}
          />
          <Line
            dataKey="provider_micros"
            name="Provider cost"
            stroke="var(--chart-2)"
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 3 }}
            isAnimationActive={false}
          />
          {showMargin && (
            <Line
              dataKey="margin_micros"
              name="Margin"
              stroke="var(--chart-3)"
              strokeWidth={2}
              strokeDasharray="4 3"
              dot={false}
              activeDot={{ r: 3 }}
              isAnimationActive={false}
            />
          )}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
