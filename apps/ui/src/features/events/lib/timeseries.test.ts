import { describe, expect, it } from "vitest";

import {
  CUSTOMER_REVENUE,
  FIGURES_KEY,
  GROSS_MARGIN,
  RECORDED_EVENTS,
  SUPPLIER_COGS,
  type MeasureFigure,
} from "@/lib/economic-query";
import type { AnalyticsMeasure } from "@/lib/vocabulary";

import { asTimeseriesPoints, type TimeseriesPoint } from "../api/types";
import { groupedMeasuresFor, OTHER_LABEL, pivotTimeseries } from "./timeseries";

function fig(
  measure: AnalyticsMeasure,
  value: number | null,
  status = "known",
  counts: Partial<Pick<MeasureFigure, "unresolved_event_count">> = {},
): MeasureFigure {
  return {
    measure,
    status,
    value,
    unresolved_event_count: counts.unresolved_event_count ?? 0,
    unpriced_event_count: 0,
    available_from: null,
  };
}

function point(
  bucket: string,
  billed: number,
  groupValue?: string,
  unresolvedEventCount = 0,
): TimeseriesPoint {
  const base: TimeseriesPoint = {
    bucket,
    revenue: fig(CUSTOMER_REVENUE, billed),
    cost: fig(SUPPLIER_COGS, Math.round(billed * 0.8), unresolvedEventCount ? "incomplete" : "known", {
      unresolved_event_count: unresolvedEventCount,
    }),
    margin: fig(GROSS_MARGIN, Math.round(billed * 0.2)),
    events: fig(RECORDED_EVENTS, 1),
  };
  if (groupValue !== undefined) base.group_value = groupValue;
  return base;
}

describe("pivotTimeseries", () => {
  it("produces revenue + provider series when not grouped", () => {
    const pivot = pivotTimeseries(
      [point("2026-07-01T00:00:00Z", 100), point("2026-07-02T00:00:00Z", 200)],
      false,
    );
    expect(pivot.series.map((s) => s.label)).toEqual(["Revenue", "Provider cost"]);
    expect(pivot.data).toHaveLength(2);
    expect(pivot.data[0]).toMatchObject({ revenue: 100, provider: 80 });
  });

  // The provider series is a FLOOR wherever its bucket holds uncosted events,
  // and the tooltip is the only place a line chart can say so — so the figure,
  // with its count, has to survive the pivot rather than being dropped with the
  // rest of the row. Carried, never plotted: no series names the key.
  it("carries each bucket's own figures, counts and all, when not grouped", () => {
    const pivot = pivotTimeseries(
      [point("2026-07-01T00:00:00Z", 100, undefined, 2), point("2026-07-02T00:00:00Z", 200)],
      false,
    );

    const figures = pivot.data[0]?.[FIGURES_KEY] as Record<string, MeasureFigure>;
    expect(figures["provider"]).toMatchObject({ status: "incomplete", unresolved_event_count: 2 });
    expect(pivot.series.map((s) => s.key)).not.toContain(FIGURES_KEY);
  });

  // ⚠ A BUCKET PAST THE HORIZON IS A GAP, NEVER A ZERO (#510). The narrowing
  // coalesced its null figures to 0, and the line dropped to the floor on
  // exactly the days UBB could say nothing about.
  it("plots a bucket whose figures are not stated as a gap", () => {
    const gone: TimeseriesPoint = {
      bucket: "2020-09-16T00:00:00Z",
      revenue: fig(CUSTOMER_REVENUE, null, "unavailable_outside_retention_horizon"),
      cost: fig(SUPPLIER_COGS, null, "unavailable_outside_retention_horizon"),
      margin: fig(GROSS_MARGIN, null, "unavailable_outside_retention_horizon"),
      events: fig(RECORDED_EVENTS, null, "unavailable_outside_retention_horizon"),
    };
    const pivot = pivotTimeseries([gone, point("2026-07-02T00:00:00Z", 200)], false);
    expect(pivot.data[0]).toMatchObject({ revenue: null, provider: null });
    expect(pivot.data[0]?.["revenue"]).not.toBe(0);
  });

  it("paints every group when there are three or fewer", () => {
    const pivot = pivotTimeseries(
      [
        point("2026-07-01T00:00:00Z", 300, "openai"),
        point("2026-07-01T00:00:00Z", 200, "anthropic"),
        point("2026-07-01T00:00:00Z", 100, "mistral"),
      ],
      true,
    );
    expect(pivot.series.map((s) => s.label)).toEqual(["openai", "anthropic", "mistral"]);
    expect(pivot.plotted).toBe(CUSTOMER_REVENUE);
  });

  it("caps painted series at 3 by folding the tail into Other", () => {
    const pivot = pivotTimeseries(
      [
        point("2026-07-01T00:00:00Z", 500, "openai"),
        point("2026-07-01T00:00:00Z", 400, "anthropic"),
        point("2026-07-01T00:00:00Z", 50, "mistral"),
        point("2026-07-01T00:00:00Z", 30, "cohere"),
      ],
      true,
    );
    expect(pivot.series).toHaveLength(3);
    expect(pivot.series.map((s) => s.label)).toEqual(["openai", "anthropic", OTHER_LABEL]);
    // Other folds the tail's revenue, with its state.
    expect(pivot.data[0]?.["d:__other__"]).toBe(80);
  });

  // A group with no row in a bucket had no postings that day: a measured zero,
  // which is what folding no figures at all answers — so lines never break
  // for a real absence of work.
  it("fills a group missing from a bucket with a measured zero", () => {
    const pivot = pivotTimeseries(
      [
        point("2026-07-01T00:00:00Z", 100, "openai"),
        point("2026-07-02T00:00:00Z", 200, "anthropic"),
      ],
      true,
    );
    expect(pivot.data[0]?.["d:anthropic"]).toBe(0);
    expect(pivot.data[1]?.["d:openai"]).toBe(0);
  });

  // ⚠ Grouped by a supplier, revenue a grouping cannot place reads as the
  // state on every row: the lines draw the supplier cost instead, and never the
  // placed PART of the revenue as though it were the whole.
  it("draws the cost where the revenue cannot be placed at this grain", () => {
    const grain = (bucket: string, group: string, revenue: number, cost: number): TimeseriesPoint => ({
      bucket,
      revenue: fig(CUSTOMER_REVENUE, revenue, "unavailable_at_requested_grain"),
      cost: fig(SUPPLIER_COGS, cost),
      margin: fig(GROSS_MARGIN, null, "unavailable_at_requested_grain"),
      events: null,
      group_value: group,
    });
    const pivot = pivotTimeseries(
      [grain("2026-07-01T00:00:00Z", "openai", 900, 70), grain("2026-07-01T00:00:00Z", "anthropic", 800, 60)],
      true,
    );
    expect(pivot.plotted).toBe(SUPPLIER_COGS);
    expect(pivot.data[0]).toMatchObject({ "d:openai": 70, "d:anthropic": 60 });
  });

  // On the measurement-concept rollup the rows carry no money at all — the axis
  // answers only the count — so that is what the lines are.
  it("draws the count on an axis that answers no money", () => {
    const counted: TimeseriesPoint = {
      bucket: "2026-07-01T00:00:00Z",
      revenue: null,
      cost: null,
      margin: null,
      events: fig(RECORDED_EVENTS, 4),
      group_value: "tokens",
    };
    const pivot = pivotTimeseries([counted], true);
    expect(pivot.plotted).toBe(RECORDED_EVENTS);
    expect(pivot.data[0]?.["d:tokens"]).toBe(4);
  });

  // The grouped value arrives inside a row the contract types as
  // `additionalProperties: true`, under a key the BACKEND owns. This fixture is
  // a literal transcript of a backend response. It fails the moment the
  // console's read stops matching what the server writes. #312 is the commit
  // that updated it — deliberately, alongside the backend's own rename, which
  // is the pairing this test exists to force.
  it("paints a verbatim backend response by its grouped value", () => {
    const fromBackend = {
      period_start: "2026-07-01",
      period_end: "2026-07-01",
      group_by: ["field:provider"],
      bucket: "day",
      basis: "recorded",
      economic_data_available_from: "2020-07-01",
      measurement_data_available_from: "2026-01-01",
      rows: [
        {
          bucket_start: "2026-07-01T00:00:00Z",
          grouping_field_value: ["openai"],
          grouping_field_value_status: ["recorded"],
          measures: [
            { measure: "supplier_cogs", amount_micros: 80, status: "known", unresolved_event_count: 0 },
            { measure: "customer_revenue", amount_micros: 100, status: "known", unpriced_event_count: 0 },
            { measure: "gross_margin", amount_micros: 20, status: "known" },
          ],
        },
      ],
      context: [],
    } as unknown as Parameters<typeof asTimeseriesPoints>[0];

    const { points } = asTimeseriesPoints(fromBackend);
    expect(points[0]?.group_value).toBe("openai");

    const pivot = pivotTimeseries(points, true);
    expect(pivot.series.map((s) => s.label)).toEqual(["openai"]);
    expect(pivot.data[0]?.["d:openai"]).toBe(100);
  });
});

describe("groupedMeasuresFor — asking an axis only what it answers", () => {
  it("asks an ordinary axis for revenue and the cost beside it", () => {
    expect(groupedMeasuresFor([])).toEqual([SUPPLIER_COGS, CUSTOMER_REVENUE]);
  });

  // ⚠ The measurement-concept rollup refuses all three money measures; asking
  // it for them was a 422, and a chart that could never render the pruned
  // stretch it exists to show.
  it("asks the measurement-concept rollup for the count alone", () => {
    expect(
      groupedMeasuresFor([
        { measure: "supplier_cogs" },
        { measure: "customer_revenue" },
        { measure: "gross_margin" },
      ]),
    ).toEqual([RECORDED_EVENTS]);
  });

  it("asks for revenue alone where only the cost is refused", () => {
    expect(groupedMeasuresFor([{ measure: "supplier_cogs" }])).toEqual([CUSTOMER_REVENUE]);
  });
});
