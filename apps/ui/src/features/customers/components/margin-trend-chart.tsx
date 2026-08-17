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
  BoundedCostTooltip,
  type SeriesRole,
} from "@/components/shared/supplier-cost";
import { formatCalendarDate, formatCostMicros } from "@/lib/format";

import type { MarginTrendPointOut } from "../api/types";

/** Which bounding rule each plotted series obeys (#330). */
function roleOf(dataKey: string): SeriesRole {
  if (dataKey === "provider_cost_micros") return "supplier-cost";
  if (dataKey === "gross_margin_micros") return "margin";
  // Usage billed is NOT NULL at the column and whole by construction.
  return "whole";
}

function periodLabel(label: string | number | undefined): string {
  return formatCalendarDate(String(label));
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
          <Tooltip
            content={
              <BoundedCostTooltip
                currency={currency}
                labelFormatter={periodLabel}
                roleOf={roleOf}
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
