import { describe, expect, it } from "vitest";

import { MOCK_CUSTOMER_ECONOMICS } from "../api/mock-data";
import { toCustomerRows } from "../api/types";
import { mockCustomerList } from "../api/mock-data";
import {
  filterMarginRows,
  microsToUnits,
  parseAlertLevels,
  shortId,
  sortMarginRows,
  suppliedPeriod,
  toMicros,
} from "./helpers";

describe("shortId", () => {
  it("shortens a UUID to its first segment", () => {
    expect(shortId("1f0c9c4e-8f2a-4a1e-9d3b-6a1f00000001")).toBe("1f0c9c4e…");
  });

  it("leaves non-dashed ids untouched", () => {
    expect(shortId("acme")).toBe("acme");
  });
});

describe("money conversion", () => {
  it("converts currency units to integer micros", () => {
    expect(toMicros("100")).toBe(100_000_000);
    expect(toMicros("0.35")).toBe(350_000);
  });

  it("round-trips micros back to units", () => {
    expect(microsToUnits(199_000_000)).toBe("199");
    expect(toMicros(microsToUnits(123_456_789))).toBe(123_456_789);
  });
});

//: The roster as the console receives it — one answer, narrowed once, so a
//: fixture here cannot describe a row no server produces.
const ROWS = toCustomerRows(
  mockCustomerList({ start_date: "2026-07-01", end_date: "2026-07-31" }),
);

describe("margin list sorting and filtering", () => {
  // ⚠ `listRowRevenueMicros` AND ITS TWO CASES ARE GONE (#501). They asserted
  // that a row's revenue was its subscription share plus its supplied share
  // plus its billed usage, because the list route published the three and no
  // total. The one economic query answers `customer_revenue` from one
  // definition and the row carries it, so there is no sum left to get wrong —
  // and the case that named the supplied share, which existed because a
  // three-way sum could not be told from a two-way one, has nothing to
  // distinguish.
  it("reads a row's own revenue total", () => {
    expect(ROWS).toHaveLength(MOCK_CUSTOMER_ECONOMICS.length);
    expect(ROWS[0]?.total_revenue_micros).toBe(MOCK_CUSTOMER_ECONOMICS[0]?.[1]);
  });

  it("sorts descending by the chosen measure", () => {
    const byRevenue = sortMarginRows(ROWS, "revenue");
    const revenues = byRevenue.map((row) => row.total_revenue_micros);
    expect(revenues).toEqual([...revenues].sort((a, b) => b - a));

    const byPct = sortMarginRows(ROWS, "margin_pct");
    const pcts = byPct.map((row) => row.margin_percentage);
    expect(pcts).toEqual([...pcts].sort((a, b) => b - a));
  });

  // ⚠ A ROW WITH NO MARGIN SORTS LAST RATHER THAN AS ZERO — the comparator
  // coercing would file a customer UBB cannot report on among the ones it can.
  it("files a customer with no margin last", () => {
    const withAGap = [
      ...ROWS,
      { ...ROWS[0]!, customer_id: "gap", gross_margin_micros: null },
    ];
    expect(
      sortMarginRows(withAGap, "margin").at(-1)?.customer_id,
    ).toBe("gap");
  });

  it("filters on customer_id substring, case-insensitively", () => {
    const hits = filterMarginRows(ROWS, "1F0C9C4E");
    expect(hits).toHaveLength(1);
    expect(filterMarginRows(ROWS, "")).toHaveLength(ROWS.length);
  });
});

describe("parseAlertLevels", () => {
  it("parses comma-separated percentages and drops junk", () => {
    expect(parseAlertLevels("50, 80,100")).toEqual([50, 80, 100]);
    expect(parseAlertLevels("abc, 50, -2, ")).toEqual([50]);
    expect(parseAlertLevels("")).toEqual([]);
  });
});

// The mid-period affordance's arithmetic (#508; slice 7 §9's ruling).
//
// #153 §19(f) recorded what retiring the recurring profile cost: the profile
// absorbed the *began on the fourteenth* semantics automatically, and per-period
// rows can only express it if the tenant enters the partial period correctly.
// This is the function that means they do not have to work it out — they say
// which month and which day they began, and the SPAN is derived.
describe("suppliedPeriod", () => {
  it("makes a whole month the month's own span", () => {
    expect(suppliedPeriod("2026-06", "")).toEqual({
      period_start: "2026-06-01",
      period_end: "2026-07-01",
      days: 30,
      partial: false,
      months: 1,
    });
  });

  // THE CASE THE AFFORDANCE EXISTS FOR, COVERED BY NAME. A customer that began
  // on the fourteenth of June earned over seventeen days, not thirty, and
  // nothing asks the tenant for that seventeen.
  it("derives the fourteenth-of-the-month case without the tenant computing it", () => {
    expect(suppliedPeriod("2026-06", "2026-06-14")).toEqual({
      period_start: "2026-06-14",
      period_end: "2026-07-01",
      days: 17,
      partial: true,
      months: 1,
    });
  });

  it("treats the first of the month as the whole month, not a partial one", () => {
    expect(suppliedPeriod("2026-06", "2026-06-01")).toEqual({
      period_start: "2026-06-01",
      period_end: "2026-07-01",
      days: 30,
      partial: false,
      months: 1,
    });
  });

  // The period end is EXCLUSIVE, so December's rolls into the next year. A
  // helper that incremented the month without the year would state a span
  // running backwards across every year boundary.
  it("rolls a December period into the next year", () => {
    expect(suppliedPeriod("2026-12", "2026-12-14")).toEqual({
      period_start: "2026-12-14",
      period_end: "2027-01-01",
      days: 18,
      partial: true,
      months: 1,
    });
  });

  it("counts February's own length rather than a nominal month", () => {
    expect(suppliedPeriod("2026-02", "")?.days).toBe(28);
    expect(suppliedPeriod("2028-02", "")?.days).toBe(29);
  });

  // ⚠ A FIGURE MAY COVER MORE THAN THE MONTH IT OPENS IN. §9 says the record
  // carries the period it actually covers, and a tenant invoicing quarterly
  // earned that money across three months — a form that could only say "one
  // month" would make them state three rows for one invoice, moving the
  // data-entry burden rather than removing it.
  it("runs a span across as many months as it covers", () => {
    expect(suppliedPeriod("2026-07", "", 3)).toEqual({
      period_start: "2026-07-01",
      period_end: "2026-10-01",
      days: 92,
      partial: false,
      months: 3,
    });
  });

  it("carries a part month at the head of a longer span", () => {
    expect(suppliedPeriod("2026-06", "2026-06-14", 3)).toEqual({
      period_start: "2026-06-14",
      period_end: "2026-09-01",
      days: 79,
      partial: true,
      months: 3,
    });
  });

  it("answers null for a span of no months at all", () => {
    expect(suppliedPeriod("2026-06", "", 0)).toBeNull();
    expect(suppliedPeriod("2026-06", "", 1.5)).toBeNull();
  });

  it("answers null for a day outside the month it names", () => {
    expect(suppliedPeriod("2026-06", "2026-07-14")).toBeNull();
    expect(suppliedPeriod("2026-06", "2026-05-31")).toBeNull();
  });

  it("answers null for a month it cannot read", () => {
    expect(suppliedPeriod("", "")).toBeNull();
    expect(suppliedPeriod("2026-13", "")).toBeNull();
  });
});
