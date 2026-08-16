// Lazy-loaded (React.lazy) so Recharts stays out of the main bundle.

import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { formatCalendarDate, formatCostMicros, formatMicros } from "@/lib/format";
import {
  marginBound,
  partialTotalNote,
  supplierCostTotal,
} from "@/lib/supplier-cost";

import type { MarginTrendPointOut } from "../api/types";

interface TipEntry {
  dataKey?: string | number;
  name?: string | number;
  value?: number | string;
  color?: string;
  payload?: MarginTrendPointOut;
}

/**
 * One tooltip row's amount, bounded by that PERIOD'S own completeness.
 *
 * A trend line is a sequence of positions and cannot say "at least"; the
 * tooltip is where the reader asks for a period's number, so it is where the
 * bound belongs. Keyed on `dataKey`, never on the display name.
 */
function seriesAmount(entry: TipEntry, currency: string): string {
  if (typeof entry.value !== "number") return String(entry.value ?? "");
  const point = entry.payload;
  if (!point) return formatMicros(entry.value, currency);
  if (entry.dataKey === "provider_cost_micros") {
    return supplierCostTotal(entry.value, point, currency);
  }
  if (entry.dataKey === "gross_margin_micros") {
    return marginBound(entry.value, point, currency);
  }
  // Usage billed is NOT NULL at the column and whole by construction.
  return formatMicros(entry.value, currency);
}

function TrendTooltip({
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
  const note = point ? partialTotalNote(point.unresolved_event_count) : null;
  return (
    <div className="rounded-md border border-border bg-bg-surface px-3 py-2 text-[11px] shadow-md">
      <div className="mb-1 font-medium text-text-primary">
        {formatCalendarDate(String(label))}
      </div>
      {payload.map((entry) => (
        <div
          key={String(entry.dataKey)}
          className="flex items-center justify-between gap-4 text-text-secondary"
        >
          <span>{entry.name}</span>
          <span className="font-medium text-text-primary">
            {seriesAmount(entry, currency)}
          </span>
        </div>
      ))}
      {note && (
        <div className="mt-1 border-t border-border pt-1 text-text-muted">
          {note}
        </div>
      )}
    </div>
  );
}

export default function MarginTrendChart({
  points,
  currency,
}: {
  points: MarginTrendPointOut[];
  currency: string;
}) {
  return (
    <div className="h-64 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={points} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
          <CartesianGrid stroke="var(--chart-grid)" vertical={false} />
          <XAxis
            dataKey="period_start"
            // period_start is a calendar date — format in UTC so the period
            // label never shifts a day for viewers west of Greenwich.
            tickFormatter={(value) => formatCalendarDate(String(value))}
            tick={{ fontSize: 11, fill: "var(--color-text-muted)" }}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            tickFormatter={(value) => formatCostMicros(Number(value), currency)}
            tick={{ fontSize: 11, fill: "var(--color-text-muted)" }}
            axisLine={false}
            tickLine={false}
            width={72}
          />
          <Tooltip content={<TrendTooltip currency={currency} />} />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          <Line
            dataKey="gross_margin_micros"
            name="Gross margin"
            stroke="var(--chart-1)"
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 3 }}
            isAnimationActive={false}
          />
          <Line
            dataKey="provider_cost_micros"
            name="Provider cost"
            stroke="var(--chart-2)"
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 3 }}
            isAnimationActive={false}
          />
          <Line
            dataKey="usage_billed_micros"
            name="Usage billed"
            stroke="var(--chart-3)"
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 3 }}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
