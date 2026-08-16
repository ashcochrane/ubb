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
import { partialTotalNote, supplierCostTotal } from "@/lib/supplier-cost";

import { UNRESOLVED_COUNT_KEY, type ChartSeries } from "../lib/timeseries";

/** The one series in this chart that plots a SUPPLIER cost (ungrouped mode). */
const PROVIDER_SERIES_KEY = "provider";

type PivotedRow = Record<string, number | string>;

interface TipEntry {
  dataKey?: string | number;
  name?: string | number;
  value?: number | string;
  payload?: PivotedRow;
}

/**
 * The bucket's own uncosted-event count, or nothing where the pivot carries
 * none — which is the grouped mode, where no supplier cost is plotted at all.
 */
function bucketCompleteness(
  row: PivotedRow | undefined,
): { unresolved_event_count: number } | null {
  const count = row?.[UNRESOLVED_COUNT_KEY];
  return typeof count === "number" ? { unresolved_event_count: count } : null;
}

/**
 * One tooltip row's amount, bounded by that BUCKET'S own completeness.
 *
 * A plotted position cannot say "at least", so the tooltip is where the bound
 * has to appear. Billed cost is NOT NULL at the column and whole by
 * construction, and so is every grouped series, which sums billed.
 */
function seriesAmount(entry: TipEntry, currency: string): string {
  const micros = typeof entry.value === "number" ? entry.value : 0;
  const completeness = bucketCompleteness(entry.payload);
  if (entry.dataKey === PROVIDER_SERIES_KEY && completeness) {
    return supplierCostTotal(micros, completeness, currency);
  }
  return formatMicros(micros, currency);
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
  const completeness = bucketCompleteness(payload[0]?.payload);
  const note = completeness
    ? partialTotalNote(completeness.unresolved_event_count)
    : null;
  return (
    <div className="rounded-md border border-border bg-bg-surface px-3 py-2 text-[11px] shadow-md">
      <div className="mb-1 font-medium text-text-primary">
        {bucketLabel(label)}
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
          <Tooltip content={<SpendTooltip currency={currency} />} />
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
