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

import { formatCostMicros, formatMicros, formatShortDate } from "@/lib/format";
import {
  marginBound,
  partialTotalNote,
  supplierCostTotal,
} from "@/lib/supplier-cost";

import type { RevenueDailyRow } from "../api/types";

interface ChartRow extends RevenueDailyRow {
  markup_micros: number;
}

const SERIES: { key: keyof ChartRow; label: string; color: string }[] = [
  { key: "billed_cost_micros", label: "Billed", color: "var(--chart-1)" },
  { key: "provider_cost_micros", label: "Provider cost", color: "var(--chart-2)" },
  { key: "markup_micros", label: "Markup", color: "var(--chart-3)" },
];

/**
 * One tooltip row's amount, bounded by the DAY'S own completeness.
 *
 * The plotted line is a position and cannot say "at least"; the tooltip is
 * where the reader asks for the number, so it is where the number has to be
 * honest. Keyed on the series' data key — display copy moves, keys do not.
 */
function seriesAmount(
  key: keyof ChartRow,
  micros: number,
  point: ChartRow,
  currency: string,
): string {
  if (key === "provider_cost_micros") {
    return supplierCostTotal(micros, point, currency);
  }
  if (key === "markup_micros") return marginBound(micros, point, currency);
  // Billed is NOT NULL at the column and whole by construction.
  return formatMicros(micros, currency);
}

function RevenueTooltip({
  active,
  payload,
  label,
  currency,
}: {
  active?: boolean;
  payload?: {
    dataKey?: string | number;
    value?: number | string;
    payload?: ChartRow;
  }[];
  label?: string | number;
  currency: string;
}) {
  if (!active || !payload || payload.length === 0) return null;
  const row = new Map(payload.map((entry) => [String(entry.dataKey), entry.value]));
  const point = payload[0]?.payload;
  return (
    <div className="rounded-md border border-border bg-bg-surface px-3 py-2 text-[11px] shadow-md">
      <div className="mb-1 font-medium text-text-primary">
        {typeof label === "string" ? formatShortDate(label) : label}
      </div>
      {SERIES.map((series) => {
        const value = row.get(series.key);
        if (typeof value !== "number") return null;
        return (
          <div key={series.key} className="flex items-center justify-between gap-4">
            <span className="text-text-secondary">{series.label}</span>
            <span className="font-medium text-text-primary">
              {point
                ? seriesAmount(series.key, value, point, currency)
                : formatMicros(value, currency)}
            </span>
          </div>
        );
      })}
      {point && partialTotalNote(point.unresolved_event_count) && (
        <div className="mt-1 border-t border-border pt-1 text-text-muted">
          {partialTotalNote(point.unresolved_event_count)}
        </div>
      )}
    </div>
  );
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
            content={<RevenueTooltip currency={currency} />}
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
