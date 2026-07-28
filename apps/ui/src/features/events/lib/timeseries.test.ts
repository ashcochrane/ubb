import { describe, expect, it } from "vitest";

import type { TimeseriesPoint } from "../api/types";
import { OTHER_LABEL, pivotTimeseries } from "./timeseries";

function point(
  bucket: string,
  billed: number,
  dimension?: string,
): TimeseriesPoint {
  const base: TimeseriesPoint = {
    bucket,
    billed_cost_micros: billed,
    provider_cost_micros: Math.round(billed * 0.8),
    markup_micros: Math.round(billed * 0.2),
    event_count: 1,
  };
  if (dimension !== undefined) base.dimension = dimension;
  return base;
}

describe("pivotTimeseries", () => {
  it("produces billed + provider series when not grouped", () => {
    const pivot = pivotTimeseries(
      [point("2026-07-01T00:00:00Z", 100), point("2026-07-02T00:00:00Z", 200)],
      false,
    );
    expect(pivot.series.map((s) => s.label)).toEqual([
      "Billed",
      "Provider cost",
    ]);
    expect(pivot.data).toHaveLength(2);
    expect(pivot.data[0]).toMatchObject({ billed: 100, provider: 80 });
  });

  it("paints every dimension when there are three or fewer", () => {
    const pivot = pivotTimeseries(
      [
        point("2026-07-01T00:00:00Z", 300, "openai"),
        point("2026-07-01T00:00:00Z", 200, "anthropic"),
        point("2026-07-01T00:00:00Z", 100, "mistral"),
      ],
      true,
    );
    expect(pivot.series.map((s) => s.label)).toEqual([
      "openai",
      "anthropic",
      "mistral",
    ]);
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
    expect(pivot.series.map((s) => s.label)).toEqual([
      "openai",
      "anthropic",
      OTHER_LABEL,
    ]);
    // Other aggregates the folded dimensions' billed cost.
    const row = pivot.data[0];
    expect(row).toBeDefined();
    expect(row?.["d:__other__"]).toBe(80);
  });

  it("fills missing series keys with zero so lines never break", () => {
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
});
