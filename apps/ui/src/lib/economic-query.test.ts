import { describe, expect, it } from "vitest";

import {
  combineFigures,
  CUSTOMER_REVENUE,
  figureOn,
  governingHorizon,
  GROSS_MARGIN,
  RECORDED_EVENTS,
  reachesPastHorizon,
  statedValue,
  SUPPLIER_COGS,
  type EconomicRow,
  type EconomicsAnswer,
  type MeasureFigure,
} from "./economic-query";

function row(measures: EconomicRow["measures"]): EconomicRow {
  return { grouping_field_value: [], grouping_field_value_status: [], measures };
}

function figure(over: Partial<MeasureFigure>): MeasureFigure {
  return {
    measure: SUPPLIER_COGS,
    status: "known",
    value: 0,
    unresolved_event_count: 0,
    unpriced_event_count: 0,
    available_from: null,
    ...over,
  };
}

describe("figureOn — one measure, with the state that says what it is worth", () => {
  const answered = row([
    { measure: "supplier_cogs", amount_micros: 4_000_000, status: "incomplete", unresolved_event_count: 3 },
    { measure: "customer_revenue", amount_micros: 9_000_000, status: "known", unpriced_event_count: 0 },
    { measure: "gross_margin", amount_micros: 5_000_000, status: "incomplete" },
    { measure: "recorded_events", event_count: 42, status: "known" },
  ]);

  it("carries each measure's own figure, state and count", () => {
    expect(figureOn(answered, SUPPLIER_COGS)).toEqual(
      figure({ status: "incomplete", value: 4_000_000, unresolved_event_count: 3 }),
    );
    expect(figureOn(answered, RECORDED_EVENTS)).toMatchObject({ status: "known", value: 42 });
  });

  // The margin's own entry carries no count: both of its sides' counts bound
  // it, in opposite directions, so the figure takes both from its siblings.
  it("gives the margin both sides' counts", () => {
    expect(figureOn(answered, GROSS_MARGIN)).toMatchObject({
      status: "incomplete",
      value: 5_000_000,
      unresolved_event_count: 3,
      unpriced_event_count: 0,
    });
  });

  it("keeps a missing figure null and carries the day the series can start", () => {
    const gone = row([
      {
        measure: "customer_revenue",
        amount_micros: null,
        unpriced_event_count: null,
        status: "unavailable_outside_retention_horizon",
        available_from: "2020-09-18",
      },
    ]);
    expect(figureOn(gone, CUSTOMER_REVENUE)).toEqual(
      figure({
        measure: CUSTOMER_REVENUE,
        status: "unavailable_outside_retention_horizon",
        value: null,
        available_from: "2020-09-18",
      }),
    );
  });

  it("answers null for a measure the row does not carry", () => {
    expect(figureOn(row([]), GROSS_MARGIN)).toBeNull();
    expect(figureOn(undefined, GROSS_MARGIN)).toBeNull();
  });
});

describe("statedValue — the figure only where the state states one", () => {
  it("states a known figure and an incomplete bound", () => {
    expect(statedValue(figure({ status: "known", value: 7 }))).toBe(7);
    expect(statedValue(figure({ status: "incomplete", value: 7 }))).toBe(7);
  });

  // ⚠ The coalesce this replaces answered 0 for every one of these.
  it.each([
    "unavailable_at_requested_grain",
    "unavailable_outside_retention_horizon",
    "not_applicable",
    "a_state_this_build_has_never_seen",
  ])("states nothing under %s, even where the wire carries a number", (status) => {
    expect(statedValue(figure({ status, value: 1_234 }))).toBeNull();
  });

  it("states nothing for a figure that is not there", () => {
    expect(statedValue(null)).toBeNull();
  });
});

describe("combineFigures — folding rows without laundering a state", () => {
  it("sums known figures into a known figure", () => {
    expect(
      combineFigures(SUPPLIER_COGS, [
        figure({ value: 2 }),
        figure({ value: 3 }),
      ]),
    ).toEqual(figure({ value: 5 }));
  });

  it("carries a bound and its counts through the sum", () => {
    expect(
      combineFigures(SUPPLIER_COGS, [
        figure({ value: 2 }),
        figure({ status: "incomplete", value: 3, unresolved_event_count: 4 }),
      ]),
    ).toEqual(figure({ status: "incomplete", value: 5, unresolved_event_count: 4 }));
  });

  // ⚠ The billing window summed its days: one day UBB could not attribute
  // made the window's revenue a partial figure presented as the whole.
  it("lets the worst state win, and states no figure under it", () => {
    const folded = combineFigures(CUSTOMER_REVENUE, [
      figure({ measure: CUSTOMER_REVENUE, value: 2 }),
      figure({ measure: CUSTOMER_REVENUE, status: "unavailable_at_requested_grain", value: 3 }),
    ]);
    expect(folded.status).toBe("unavailable_at_requested_grain");
    expect(statedValue(folded)).toBeNull();
  });

  it("ranks the retention horizon above the grain, as the query does", () => {
    const folded = combineFigures(CUSTOMER_REVENUE, [
      figure({ status: "unavailable_at_requested_grain", value: 3 }),
      figure({ status: "unavailable_outside_retention_horizon", value: null, available_from: "2020-09-18" }),
    ]);
    expect(folded).toMatchObject({
      status: "unavailable_outside_retention_horizon",
      value: null,
      available_from: "2020-09-18",
    });
  });

  it("carries a state it cannot rank as itself, and vouches for no sum", () => {
    const folded = combineFigures(SUPPLIER_COGS, [
      figure({ value: 2 }),
      figure({ status: "a_state_this_build_has_never_seen", value: 3 }),
    ]);
    expect(folded.status).toBe("a_state_this_build_has_never_seen");
    expect(statedValue(folded)).toBeNull();
  });

  it("treats a row that carried no figure as a gap in the sum, not a zero", () => {
    const folded = combineFigures(GROSS_MARGIN, [figure({ value: 2 }), null]);
    expect(statedValue(folded)).toBeNull();
  });

  // #537: a row whose state CAN state a figure and states none is a gap too.
  // Summed as zero, a margin fold of +100 beside a no-amount margin over a
  // cost of 50 would read 100 where the whole is 50 at most.
  it("treats an incomplete figure with no amount as a gap, never as zero", () => {
    const folded = combineFigures(GROSS_MARGIN, [
      figure({ measure: GROSS_MARGIN, value: 100 }),
      figure({ measure: GROSS_MARGIN, status: "incomplete", value: null, unpriced_event_count: 2 }),
    ]);
    expect(folded.status).toBe("incomplete");
    expect(statedValue(folded)).toBeNull();
    expect(folded.unpriced_event_count).toBe(2);
  });

  it("is a measured zero over no rows at all", () => {
    expect(combineFigures(SUPPLIER_COGS, [])).toEqual(figure({ value: 0 }));
  });
});

describe("the horizon that governs an answer", () => {
  const answer = (over: Partial<EconomicsAnswer>): EconomicsAnswer => ({
    period_start: "2026-05-01",
    period_end: "2026-07-31",
    group_by: [],
    bucket: "day",
    basis: "recorded",
    economic_data_available_from: "2020-09-18",
    measurement_data_available_from: "2026-06-01",
    rows: [],
    context: [],
    ...over,
  });

  it("is the economic horizon for a money question", () => {
    expect(governingHorizon(answer({}))).toBe("2020-09-18");
    expect(reachesPastHorizon(answer({}))).toBe(false);
  });

  // Only a measurement-concept grouping reads the records the shorter clock
  // prunes, so only it is governed by that clock (#500).
  it("is the measurement horizon for a grouping by what was measured", () => {
    const measured = answer({ group_by: ["rollup:measurement_concept"] });
    expect(governingHorizon(measured)).toBe("2026-06-01");
    expect(reachesPastHorizon(measured)).toBe(true);
  });

  it("is not moved by the other rollup", () => {
    expect(governingHorizon(answer({ group_by: ["rollup:event_category"] }))).toBe(
      "2020-09-18",
    );
  });
});
