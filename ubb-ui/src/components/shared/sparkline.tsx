import { useId } from "react";
import { Area, AreaChart, ResponsiveContainer } from "recharts";

export interface SparklineProps {
  data: number[];
  color: string;
  height?: number;
  className?: string;
}

export function Sparkline({ data, color, height = 32, className }: SparklineProps) {
  // useId must run before any conditional return — hooks order must be stable.
  const reactId = useId();
  if (data.length === 0) return null;

  const chartData = data.map((value, index) => ({ index, value }));
  // Per-instance id prevents SVG url(#id) collisions when two sparklines share a color.
  const gradientId = `spark-${reactId.replace(/:/g, "")}`;

  return (
    <div className={className} style={{ height, width: "100%" }}>
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={chartData} margin={{ top: 2, right: 0, bottom: 0, left: 0 }}>
          <defs>
            <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={color} stopOpacity={0.18} />
              <stop offset="100%" stopColor={color} stopOpacity={0} />
            </linearGradient>
          </defs>
          <Area
            type="monotone"
            dataKey="value"
            stroke={color}
            strokeWidth={1.5}
            fill={`url(#${gradientId})`}
            isAnimationActive={false}
            dot={false}
            activeDot={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
