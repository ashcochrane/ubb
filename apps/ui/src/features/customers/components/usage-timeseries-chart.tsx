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
import { partialTotalNote, supplierCostTotal } from "@/lib/supplier-cost";

import type { TimeseriesPoint } from "../api/types";

/** Buckets are day-truncated UTC datetimes ("2026-07-10T00:00:00Z") — slice
 * to the calendar day and format in UTC so the day never shifts locally. */
function bucketDay(bucket: unknown): string {
  return formatCalendarDate(String(bucket).slice(0, 10));
}

interface TipEntry {
  dataKey?: string | number;
  name?: string | number;
  value?: number | string;
  payload?: TimeseriesPoint;
}

/**
 * One tooltip row's amount, bounded by that BUCKET'S own completeness.
 *
 * The plotted line is a position and cannot say "at least", so the number the
 * reader asks for is the one that has to. Keyed on `dataKey` rather than on the
 * series name, which is display copy.
 */
function seriesAmount(entry: TipEntry, currency: string): string {
  if (typeof entry.value !== "number") return String(entry.value ?? "");
  const point = entry.payload;
  if (point && entry.dataKey === "provider_cost_micros") {
    return supplierCostTotal(entry.value, point, currency);
  }
  // Billed is NOT NULL at the column and whole by construction.
  return formatMicros(entry.value, currency);
}

function SpendTooltip({
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
        {bucketDay(label)}
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

export default function UsageTimeseriesChart({
  points,
  currency,
}: {
  points: TimeseriesPoint[];
  currency: string;
}) {
  return (
    <div className="h-56 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={points} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
          <CartesianGrid stroke="var(--chart-grid)" vertical={false} />
          <XAxis
            dataKey="bucket"
            tickFormatter={bucketDay}
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
          <Tooltip content={<SpendTooltip currency={currency} />} />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          <Line
            dataKey="billed_cost_micros"
            name="Billed"
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
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
