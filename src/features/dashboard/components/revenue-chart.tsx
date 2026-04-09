// src/features/dashboard/components/revenue-chart.tsx
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import type { RevenueTimeSeries } from "../api/types";

interface RevenueChartProps {
  data: RevenueTimeSeries[];
}

export function RevenueChart({ data }: RevenueChartProps) {
  return (
    <div className="rounded-xl border border-border px-4 py-3.5">
      <div className="mb-1 text-[13px] font-semibold">Revenue and margin</div>
      <div className="mb-3 flex gap-3">
        <LegendItem color="#1D9E75" label="Revenue" />
        <LegendItem color="#E24B4A" label="API costs" />
        <LegendItem color="#639922" label="Margin" dashed />
      </div>
      <ResponsiveContainer width="100%" height={200}>
        <AreaChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" vertical={false} />
          <XAxis
            dataKey="label"
            tick={{ fontSize: 10, fill: "var(--color-muted-foreground)" }}
            tickLine={false}
            axisLine={false}
            interval="preserveStartEnd"
          />
          <YAxis
            tick={{ fontSize: 10, fill: "var(--color-muted-foreground)" }}
            tickLine={false}
            axisLine={false}
            tickFormatter={(v: number) => `$${v}`}
            width={50}
          />
          <Tooltip
            contentStyle={{
              fontSize: 11,
              borderRadius: 8,
              border: "1px solid var(--color-border)",
              background: "var(--color-card)",
            }}
            formatter={(value, name) => [`$${Number(value).toFixed(2)}`, name]}
          />
          <Area
            type="monotone"
            dataKey="revenue"
            name="Revenue"
            stroke="#1D9E75"
            fill="#1D9E75"
            fillOpacity={0.08}
            strokeWidth={1.5}
          />
          <Area
            type="monotone"
            dataKey="apiCosts"
            name="API costs"
            stroke="#E24B4A"
            fill="#E24B4A"
            fillOpacity={0.06}
            strokeWidth={1.5}
          />
          <Area
            type="monotone"
            dataKey="margin"
            name="Margin"
            stroke="#639922"
            fill="#639922"
            fillOpacity={0.06}
            strokeWidth={1.5}
            strokeDasharray="4 3"
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

function LegendItem({ color, label, dashed }: { color: string; label: string; dashed?: boolean }) {
  return (
    <div className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
      <div
        className="h-0.5 w-3"
        style={{
          backgroundColor: color,
          borderTop: dashed ? `1.5px dashed ${color}` : undefined,
          height: dashed ? 0 : 2,
        }}
      />
      {label}
    </div>
  );
}
