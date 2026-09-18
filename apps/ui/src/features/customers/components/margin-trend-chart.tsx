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

import type { TrendPoint } from "../api/types";

/** The plotted series, by the data key each point and its figure share. The
 *  tooltip says each as its own state allows — the margin as incomplete where
 *  the cost side is, whatever the revenue beside it reads (§15). */
const SERIES: readonly TooltipSeries[] = [
  { key: "gross_margin_micros", name: "Gross margin", color: "var(--chart-1)" },
  { key: "provider_cost_micros", name: "Provider cost", color: "var(--chart-2)" },
  { key: "revenue_micros", name: "Revenue", color: "var(--chart-3)" },
];

function periodLabel(label: string | number | undefined): string {
  return formatCalendarDate(String(label));
}

export default function MarginTrendChart({
  points,
  currency,
}: {
  points: TrendPoint[];
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
          <Tooltip
            filterNull={false}
            content={
              <MeasureTooltip
                series={SERIES}
                currency={currency}
                labelFormatter={periodLabel}
              />
            }
          />
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
            dataKey="revenue_micros"
            name="Revenue"
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
