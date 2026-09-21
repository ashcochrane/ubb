// Pivot the timeseries rows into Recharts-ready data, respecting the
// monochrome chart discipline: at most 3 painted series — when a group-by
// produces more groups, the top two stay and the rest fold into "Other".
//
// ⚠ **EVERY PLOTTED NUMBER IS A FIGURE'S `statedValue`, AND THE FIGURE RIDES
// BESIDE IT (#510).** A bucket whose measure states no figure — past a
// retention horizon, or revenue a grouping could not place — is a GAP in its
// line, never a zero; and each row keeps the figures behind its numbers under
// `FIGURES_KEY`, keyed like the series, so the tooltip says each one as its
// state allows. The pivot used to carry an uncosted-event count beside the
// numbers for the tooltip to bound by; the figures carry their own counts now.

import {
  combineFigures,
  CUSTOMER_REVENUE,
  drawableMeasure,
  FIGURES_KEY,
  RECORDED_EVENTS,
  statedValue,
  SUPPLIER_COGS,
  type MeasureFigure,
} from "@/lib/economic-query";
import type { AnalyticsMeasure } from "@/lib/vocabulary";

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
  data: Array<Record<string, unknown>>;
  series: ChartSeries[];
  /** The measure the lines are drawn in — money for all but the count. */
  plotted: AnalyticsMeasure;
}

const SERIES_COLORS = [
  "var(--chart-1)",
  "var(--chart-2)",
  "var(--chart-3)",
] as const;

export const OTHER_LABEL = "Other";
const OTHER_KEY = "d:__other__";

function groupValueOf(point: TimeseriesPoint): string {
  return point.group_value ?? "(unattributed)";
}

/**
 * The measures a GROUPED question asks for, given what the chosen axis's
 * discovery entry declares it cannot answer.
 *
 * Revenue where the axis answers it, with the supplier cost beside it so the
 * chart has something true to draw where the revenue cannot be placed; the
 * count where the axis answers no money at all — which is the
 * measurement-concept rollup, whose records carry quantities and no cost lines
 * (`queries.py::MEASUREMENT_ROLLUP_UNSUPPORTED`). An axis answering none of
 * the three leaves the chart nothing to ask for, and says so.
 */
export function groupedMeasuresFor(
  unsupported: readonly { readonly measure: string }[],
): AnalyticsMeasure[] {
  const refused = new Set(unsupported.map((entry) => entry.measure));
  if (!refused.has(CUSTOMER_REVENUE)) {
    return refused.has(SUPPLIER_COGS)
      ? [CUSTOMER_REVENUE]
      : [SUPPLIER_COGS, CUSTOMER_REVENUE];
  }
  return refused.has(RECORDED_EVENTS) ? [] : [RECORDED_EVENTS];
}

/** A point's figure for one measure. */
function figureFor(point: TimeseriesPoint, measure: AnalyticsMeasure): MeasureFigure | null {
  if (measure === SUPPLIER_COGS) return point.cost;
  if (measure === RECORDED_EVENTS) return point.events;
  if (measure === CUSTOMER_REVENUE) return point.revenue;
  return point.margin;
}

export function pivotTimeseries(
  points: TimeseriesPoint[],
  grouped: boolean,
): PivotedTimeseries {
  if (!grouped) {
    return {
      plotted: CUSTOMER_REVENUE,
      data: points.map((point) => ({
        bucket: point.bucket,
        revenue: statedValue(point.revenue),
        provider: statedValue(point.cost),
        [FIGURES_KEY]: { revenue: point.revenue, provider: point.cost },
      })),
      // "Revenue", not "Billed": the measure is customer revenue from one
      // definition — subscriptions and supplied figures as well as billed
      // usage — and #501 renamed it everywhere else the query is drawn.
      series: [
        { key: "revenue", label: "Revenue", color: SERIES_COLORS[0] },
        { key: "provider", label: "Provider cost", color: SERIES_COLORS[1] },
      ],
    };
  }

  // `drawableMeasure` — the dashboard breakdown's rule too: revenue where every
  // row states it, the cost where it could not be placed at this grain, the
  // count where the axis answers no money.
  const plotted = drawableMeasure(points);

  // Rank groups by what they state across the window. A group stating nothing
  // ranks with nothing — the ranking only chooses which lines to paint; every
  // painted line still says its own state.
  const totals = new Map<string, number>();
  for (const point of points) {
    const value = groupValueOf(point);
    totals.set(value, (totals.get(value) ?? 0) + (statedValue(figureFor(point, plotted)) ?? 0));
  }
  const ranked = [...totals.entries()]
    .sort((a, b) => b[1] - a[1])
    .map(([value]) => value);

  // ≤3 groups: paint each. More: paint top 2 + fold the rest into Other.
  const foldToOther = ranked.length > 3;
  const painted = foldToOther ? ranked.slice(0, 2) : ranked;
  const paintedSet = new Set(painted);

  const series: ChartSeries[] = painted.map((value, index) => ({
    key: `d:${value}`,
    label: value,
    color: SERIES_COLORS[index] ?? SERIES_COLORS[2],
  }));
  if (foldToOther) {
    series.push({ key: OTHER_KEY, label: OTHER_LABEL, color: SERIES_COLORS[2] });
  }

  // Each bucket's figures per series, folded with their states. A series with
  // no row in a bucket is a measured zero there — no postings of that group
  // that day — which is `combineFigures` over no rows.
  const byBucket = new Map<string, Map<string, (MeasureFigure | null)[]>>();
  for (const point of points) {
    const bucket = byBucket.get(point.bucket) ?? new Map<string, (MeasureFigure | null)[]>();
    const value = groupValueOf(point);
    const key = paintedSet.has(value) ? `d:${value}` : OTHER_KEY;
    bucket.set(key, [...(bucket.get(key) ?? []), figureFor(point, plotted)]);
    byBucket.set(point.bucket, bucket);
  }

  const data = [...byBucket.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([bucket, figuresByKey]) => {
      const figures: Record<string, MeasureFigure> = {};
      const row: Record<string, unknown> = { bucket };
      for (const entry of series) {
        const folded = combineFigures(plotted, figuresByKey.get(entry.key) ?? []);
        figures[entry.key] = folded;
        row[entry.key] = statedValue(folded);
      }
      row[FIGURES_KEY] = figures;
      return row;
    });
  return { data, series, plotted };
}
