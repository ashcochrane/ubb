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
  formatCalendarDate,
  formatCostMicros,
  formatEventCount,
  formatMicros,
} from "@/lib/format";

import type { RevenueCostPoint } from "../lib/economics";

interface TipEntry {
  dataKey?: string | number;
  name?: string | number;
  value?: number | string;
  color?: string;
  payload?: RevenueCostPoint;
}

function ChartTip({
  active,
  payload,
  label,
  currency,
}: {
  active?: boolean;
  payload?: TipEntry[];
  label?: string | number;
  currency: string;
}) {
  if (!active || !payload || payload.length === 0) return null;
  const point = payload[0]?.payload;
  return (
    <div className="rounded-md border border-border bg-bg-surface px-3 py-2 text-[11px] shadow-md">
      <div className="mb-1 font-medium text-text-primary">
        {/* Day buckets are calendar dates (YYYY-MM-DD) — format in UTC so
            the day never shifts for viewers west of Greenwich. */}
        {typeof label === "string" ? formatCalendarDate(label) : label}
      </div>
      {payload.map((entry) => (
        <div
          key={String(entry.dataKey)}
          className="flex items-center justify-between gap-4 text-text-secondary"
        >
          <span className="inline-flex items-center gap-1.5">
            <span
              className="block h-[7px] w-[7px] rounded-full"
              style={{ backgroundColor: entry.color }}
            />
            {entry.name}
          </span>
          <span className="font-medium text-text-primary">
            {typeof entry.value === "number"
              ? formatMicros(entry.value, currency)
              : entry.value}
          </span>
        </div>
      ))}
      {point && (
        <div className="mt-1 border-t border-border pt-1 text-text-muted">
          {formatEventCount(point.event_count)} events
        </div>
      )}
    </div>
  );
}

export default function RevenueCostChart({
  points,
  showMargin,
  currency,
  billedLabel,
}: {
  points: RevenueCostPoint[];
  showMargin: boolean;
  currency: string;
  billedLabel: string;
}) {
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
            content={<ChartTip currency={currency} />}
            cursor={{ stroke: "var(--chart-grid)" }}
          />
          <Line
            dataKey="billed_micros"
            name={billedLabel}
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
