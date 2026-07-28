// Pivot the timeseries rows into Recharts-ready data, respecting the
// monochrome chart discipline: at most 3 painted series — when a group-by
// produces more dimensions, the top two stay and the rest fold into "Other".

import type { TimeseriesPoint } from "../api/types";

export interface ChartSeries {
  /** Data key inside each pivoted row. */
  key: string;
  /** Legend/tooltip label — the entity itself, never a rank. */
  label: string;
  /** Chart color token (var(--chart-N)). */
  color: string;
}

export interface PivotedTimeseries {
  data: Array<Record<string, number | string>>;
  series: ChartSeries[];
}

const SERIES_COLORS = [
  "var(--chart-1)",
  "var(--chart-2)",
  "var(--chart-3)",
] as const;

export const OTHER_LABEL = "Other";
const OTHER_KEY = "d:__other__";

function dimensionOf(point: TimeseriesPoint): string {
  return point.dimension ?? "(unattributed)";
}

export function pivotTimeseries(
  points: TimeseriesPoint[],
  grouped: boolean,
): PivotedTimeseries {
  if (!grouped) {
    return {
      data: points.map((point) => ({
        bucket: point.bucket,
        billed: point.billed_cost_micros,
        provider: point.provider_cost_micros,
      })),
      series: [
        { key: "billed", label: "Billed", color: SERIES_COLORS[0] },
        { key: "provider", label: "Provider cost", color: SERIES_COLORS[1] },
      ],
    };
  }

  // Rank dimensions by total billed cost across the window.
  const totals = new Map<string, number>();
  for (const point of points) {
    const dim = dimensionOf(point);
    totals.set(dim, (totals.get(dim) ?? 0) + point.billed_cost_micros);
  }
  const ranked = [...totals.entries()]
    .sort((a, b) => b[1] - a[1])
    .map(([dim]) => dim);

  // ≤3 dimensions: paint each. More: paint top 2 + fold the rest into Other.
  const foldToOther = ranked.length > 3;
  const painted = foldToOther ? ranked.slice(0, 2) : ranked;
  const paintedSet = new Set(painted);

  const series: ChartSeries[] = painted.map((dim, index) => ({
    key: `d:${dim}`,
    label: dim,
    color: SERIES_COLORS[index] ?? SERIES_COLORS[2],
  }));
  if (foldToOther) {
    series.push({ key: OTHER_KEY, label: OTHER_LABEL, color: SERIES_COLORS[2] });
  }

  const byBucket = new Map<string, Record<string, number | string>>();
  for (const point of points) {
    let row = byBucket.get(point.bucket);
    if (!row) {
      row = { bucket: point.bucket };
      for (const entry of series) row[entry.key] = 0;
      byBucket.set(point.bucket, row);
    }
    const dim = dimensionOf(point);
    const key = paintedSet.has(dim) ? `d:${dim}` : OTHER_KEY;
    const current = row[key];
    row[key] =
      (typeof current === "number" ? current : 0) + point.billed_cost_micros;
  }

  const data = [...byBucket.values()].sort((a, b) =>
    String(a.bucket).localeCompare(String(b.bucket)),
  );
  return { data, series };
}
