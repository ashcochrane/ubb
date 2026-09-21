import { describe, expect, it } from "vitest";

import {
  CUSTOMER_REVENUE,
  GROSS_MARGIN,
  RECORDED_EVENTS,
  SUPPLIER_COGS,
  type MeasureFigure,
} from "./economic-query";
import {
  isNegative,
  MEASURE_STATUS_EXPLANATIONS,
  measureStatusLabel,
  readingText,
  readMeasure,
  readShare,
  revenueContextNote,
} from "./measure-state";
import { MEASURE_STATUS_VALUES } from "./vocabulary";

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

const text = (f: MeasureFigure | null) => readingText(readMeasure(f, "usd"));

describe("every state has the catalogue's word and a sentence", () => {
  it.each(MEASURE_STATUS_VALUES)("%s", (status) => {
    expect(measureStatusLabel(status)).not.toMatch(/^\[no label/);
    expect(MEASURE_STATUS_EXPLANATIONS[status].length).toBeGreaterThan(20);
  });
});

describe("known — the amount", () => {
  it("renders money as money and a count as a count", () => {
    expect(text(figure({ value: 4_200_000 }))).toBe("$4.20");
    expect(text(figure({ measure: RECORDED_EVENTS, value: 1_500 }))).toBe("1.5k");
  });

  // A genuine zero stays a genuine zero, and a real loss stays visible.
  it("renders a known zero and a known loss as themselves", () => {
    expect(text(figure({ measure: CUSTOMER_REVENUE, value: 0 }))).toBe("$0.00");
    expect(text(figure({ measure: GROSS_MARGIN, value: -3_000_000 }))).toBe("-$3.00");
    expect(isNegative(figure({ measure: GROSS_MARGIN, value: -3_000_000 }))).toBe(true);
  });
});

describe("incomplete — a bound with its count, never a total", () => {
  it("renders an incomplete cost as a floor, with its count", () => {
    const reading = readMeasure(
      figure({ status: "incomplete", value: 4_200_000, unresolved_event_count: 3 }),
      "usd",
    );
    expect(readingText(reading)).toBe("at least $4.20");
    expect(reading.kind === "bound" && reading.note).toMatch(/^3 events have a supplier cost/);
  });

  it("renders an incomplete revenue as a floor, with the unpriced count", () => {
    const reading = readMeasure(
      figure({
        measure: CUSTOMER_REVENUE,
        status: "incomplete",
        value: 9_000_000,
        unpriced_event_count: 2,
      }),
      "usd",
    );
    expect(readingText(reading)).toBe("at least $9.00");
    expect(reading.kind === "bound" && reading.note).toMatch(/^2 events have a customer price/);
  });

  // A floor of nothing printed as "at least $0.00" reads as "free".
  it("states no amount for a floor of zero", () => {
    expect(
      text(figure({ status: "incomplete", value: 0, unresolved_event_count: 1 })),
    ).toBe("—");
  });

  // #537: where no piece of a row's revenue resolved, the query sends no amount
  // on the revenue or the margin. There is no total to have left anything out
  // of and no figure for the truth to be above, so the sentence says neither.
  it.each([CUSTOMER_REVENUE, GROSS_MARGIN] as const)(
    "states no amount, no total and no direction for %s where nothing resolved",
    (measure) => {
      const reading = readMeasure(
        figure({ measure, status: "incomplete", value: null, unpriced_event_count: 2 }),
        "usd",
      );
      expect(readingText(reading)).toBe("—");
      const note = reading.kind === "bound" ? reading.note : null;
      expect(note).toMatch(/^No (revenue|margin) can be stated/);
      expect(note).toContain("2 events have a customer price UBB could not resolve");
      expect(note).not.toMatch(/total|higher|lower/);
    },
  );

  // The guard on the case above: a revenue floor of ZERO is an amount — a free
  // service beside an unpriced one — and keeps the note that says what the
  // total left out.
  it("keeps the left-out note where a zero floor IS an amount", () => {
    const reading = readMeasure(
      figure({ measure: CUSTOMER_REVENUE, status: "incomplete", value: 0, unpriced_event_count: 1 }),
      "usd",
    );
    expect(readingText(reading)).toBe("—");
    expect(reading.kind === "bound" && reading.note).toMatch(/left out of this total/);
  });

  // ⚠ §15: the cost side incomplete makes the margin incomplete whatever the
  // revenue side says, and an uncosted event can only LOWER it.
  it("bounds a margin from above where only the cost side is short", () => {
    expect(
      text(
        figure({
          measure: GROSS_MARGIN,
          status: "incomplete",
          value: 5_000_000,
          unresolved_event_count: 3,
        }),
      ),
    ).toBe("at most $5.00");
  });

  it("bounds a margin from below where only the revenue side is short", () => {
    expect(
      text(
        figure({
          measure: GROSS_MARGIN,
          status: "incomplete",
          value: 5_000_000,
          unpriced_event_count: 2,
        }),
      ),
    ).toBe("at least $5.00");
  });

  it("bounds a margin in neither direction where both are, and says so", () => {
    const shown = text(
      figure({
        measure: GROSS_MARGIN,
        status: "incomplete",
        value: 5_000_000,
        unresolved_event_count: 3,
        unpriced_event_count: 2,
      }),
    );
    expect(shown).toBe("$5.00 (Incomplete)");
  });
});

describe("the three states that state no figure — never a currency zero", () => {
  // Each of these arrives with a number on the wire in at least one shape (the
  // placed part of a revenue), or a null the old coalesce made 0.
  it.each([
    ["unavailable_at_requested_grain", 3_000_000, "Unavailable at this grain"],
    ["unavailable_at_requested_grain", null, "Unavailable at this grain"],
    ["not_applicable", null, "Not applicable"],
    ["not_applicable", 0, "Not applicable"],
  ])("%s with %s renders as the state", (status, value, word) => {
    const shown = text(figure({ measure: CUSTOMER_REVENUE, status, value }));
    expect(shown).toBe(word);
    expect(shown).not.toMatch(/\$|0\.00/);
  });

  it("renders out-of-horizon with the day its series can start", () => {
    const reading = readMeasure(
      figure({
        status: "unavailable_outside_retention_horizon",
        value: null,
        available_from: "2020-09-18",
      }),
      "usd",
    );
    expect(readingText(reading)).toBe("Outside retention horizon");
    expect(reading.kind === "state" && reading.note).toBe(
      "UBB holds these records from Sep 18, 2020. The stretch before that is no longer held, so there is no figure for it — not a zero.",
    );
  });

  // ⚠ Not applicable must never render as known and never as within-anything.
  it("never reads not-applicable as known or as within anything", () => {
    const shown = text(figure({ status: "not_applicable", value: 0 }));
    expect(shown).not.toMatch(/known|within/i);
  });
});

describe("a state this build has never seen", () => {
  it("is the token, and vouches for no figure", () => {
    const reading = readMeasure(
      figure({ status: "estimated_by_a_later_server", value: 4_200_000 }),
      "usd",
    );
    expect(reading).toEqual({ kind: "unfamiliar", status: "estimated_by_a_later_server" });
    expect(readingText(reading)).toBe("estimated_by_a_later_server");
  });
});

describe("a figure that is not there", () => {
  it("is the absent marker and nothing else", () => {
    expect(readMeasure(null, "usd")).toEqual({ kind: "absent" });
    expect(readingText(readMeasure(null, "usd"))).toBe("—");
  });
});

describe("readShare — the margin as a share of revenue", () => {
  const revenue = (over: Partial<MeasureFigure> = {}) =>
    figure({ measure: CUSTOMER_REVENUE, value: 10_000_000, ...over });
  const margin = (over: Partial<MeasureFigure> = {}) =>
    figure({ measure: GROSS_MARGIN, value: 2_500_000, ...over });

  it("states a share of two known figures", () => {
    expect(readingText(readShare(margin(), revenue()))).toBe("25%");
  });

  // ⚠ The old percentage answered 0 for a margin UBB would not state, and the
  // customer list printed it: "0.0%" beside a dash.
  it("carries the margin's own state where it states no figure", () => {
    expect(
      readingText(
        readShare(margin({ status: "unavailable_at_requested_grain", value: null }), revenue()),
      ),
    ).toBe("Unavailable at this grain");
  });

  it("states no share of nothing", () => {
    expect(readingText(readShare(margin({ value: 0 }), revenue({ value: 0 })))).toBe("—");
  });

  it("bounds the share the way the margin is bounded", () => {
    expect(
      readingText(
        readShare(
          margin({ status: "incomplete", unresolved_event_count: 1 }),
          revenue(),
        ),
      ),
    ).toBe("at most 25%");
  });
});

describe("revenueContextNote — the coarser figure, on the finer chart", () => {
  it("names the money, where it comes from, and where it can be placed", () => {
    expect(
      revenueContextNote(
        [
          {
            source: "subscription",
            customer_id: "c1",
            amount_micros: 1_000_000_000,
            window_start: "2026-07-01",
            window_end: "2026-07-31",
            attributable_axes: ["customer"],
            attributable_bucket: "month",
          },
          {
            source: "tenant_supplied",
            customer_id: "c2",
            amount_micros: 250_000_000,
            window_start: "2026-07-01",
            window_end: "2026-07-31",
            attributable_axes: ["customer"],
            attributable_bucket: "day",
          },
        ],
        "usd",
      ),
    ).toBe(
      "$1,250.00 of revenue from subscriptions and figures you supplied can only be placed by customer, per month — so no margin is drawn at this grain.",
    );
  });

  it("names a source it does not know by its token", () => {
    expect(
      revenueContextNote(
        [
          {
            source: "a_later_source",
            customer_id: "c1",
            amount_micros: 5_000_000,
            window_start: "2026-07-01",
            window_end: "2026-07-31",
            attributable_axes: [],
            attributable_bucket: "month",
          },
        ],
        "usd",
      ),
    ).toBe(
      "$5.00 of revenue from a_later_source can only be placed on the whole window, per month — so no margin is drawn at this grain.",
    );
  });

  it("says nothing where there is no context", () => {
    expect(revenueContextNote([], "usd")).toBeNull();
  });
});
