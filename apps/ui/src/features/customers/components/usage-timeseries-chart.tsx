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

import {
  MeasureTooltip,
  type TooltipSeries,
} from "@/components/shared/measure-value";
import { formatCalendarDate, formatCostMicros } from "@/lib/format";

import type { TimeseriesPoint } from "../api/types";

/** Buckets are day-truncated UTC datetimes ("2026-07-10T00:00:00Z") — slice
 * to the calendar day and format in UTC so the day never shifts locally. */
function bucketDay(bucket: unknown): string {
  return formatCalendarDate(String(bucket).slice(0, 10));
}

/** The plotted series, by the data key each point and its figure share. */
const SERIES: readonly TooltipSeries[] = [
  { key: "revenue_micros", name: "Revenue", color: "var(--chart-1)" },
  { key: "provider_cost_micros", name: "Provider cost", color: "var(--chart-2)" },
];

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
          <Tooltip
            filterNull={false}
            content={
              <MeasureTooltip
                series={SERIES}
                currency={currency}
                labelFormatter={bucketDay}
              />
            }
          />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          {/* ⚠ THIS LINE READ `billed_cost_micros` UNTIL #510, a key the points
              stopped carrying when #501 moved the tab onto the one query and
              named the revenue `revenue_micros` — so the revenue line was not
              drawn at all, and nothing said so. */}
          <Line
            dataKey="revenue_micros"
            name="Revenue"
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
