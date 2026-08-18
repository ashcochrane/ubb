// Guards the billing fixture against the failure mode in #225: a revenue span
// written as absolute dates goes stale the moment the calendar leaves it, the
// month-to-date default then selects no rows, and the revenue section swaps its
// tiles and legend for an empty state — taking "Provider cost" with them. The
// symptom was a permanently red UI-tests gate that no commit had caused.
//
// Every assertion here is about the fixture's relationship to the *default*
// window, never about a literal date, so none of it can rot the same way.

import { afterEach, describe, expect, it, vi } from "vitest";

import { resolveRange } from "@/lib/date-range";

import {
  UNRESOLVED_TODAY,
  buildDailyRows,
  buildUsageInvoices,
  rowsInRange,
} from "./mock-data";

// Clocks chosen for the edges that break span arithmetic. The first of a month
// matters most: it is the narrowest month-to-date window there is (one day), so
// a fixture that merely ends "recently" still fails it.
const CLOCKS = [
  "2026-08-01T00:00:00Z", // first of a month — window is a single day
  "2026-08-06T13:45:00Z", // mid-month
  "2026-12-31T23:59:59Z", // last day of a year
  "2028-02-29T12:00:00Z", // leap day
  "2031-03-01T00:00:00Z", // far enough out to catch a re-pinned span
];

describe("buildDailyRows", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it("intersects the default window on the day the suite happens to run", () => {
    // Window resolved *before* the rows: should the run straddle UTC midnight,
    // rows built a day later still cover the window's end. The other order can
    // miss by a day, and a gate that flakes once a month is a gate nobody
    // believes.
    const window = resolveRange({});

    expect(rowsInRange(buildDailyRows(), window)).not.toHaveLength(0);
  });

  it.each(CLOCKS)("intersects the default window when today is %s", (clock) => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date(clock));

    // Built *after* the clock is pinned, and via the builder rather than the
    // provider's rows: mock.ts materialises its array once at module load, so a
    // test reading that array sees the real clock and passes for the wrong
    // reason.
    const rows = buildDailyRows();

    expect(rowsInRange(rows, resolveRange({}))).not.toHaveLength(0);
  });

  it("keeps the row shape the revenue chart and tiles read", () => {
    const rows = buildDailyRows();
    const first = rows[0];

    expect(first).toBeDefined();
    expect(first).toEqual({
      day: expect.stringMatching(/^\d{4}-\d{2}-\d{2}$/),
      provider_cost_micros: expect.any(Number),
      billed_cost_micros: expect.any(Number),
      event_count: expect.any(Number),
      unresolved_event_count: expect.any(Number),
      unpriced_event_count: expect.any(Number),
    });
  });

  // #330: the console has to be able to show a PARTIAL total in mock mode, and
  // the day it is partial on has to be one the default window always selects.
  // Every clock above resolves a month-to-date window ending today, including
  // the one where that window is a single day — so putting the uncosted events
  // on today is the only placement this fixture's own span arithmetic keeps
  // reachable.
  it.each(CLOCKS)(
    "leaves the default window's total incomplete when today is %s",
    (clock) => {
      vi.useFakeTimers();
      vi.setSystemTime(new Date(clock));

      const selected = rowsInRange(buildDailyRows(), resolveRange({}));
      const unresolved = selected.reduce(
        (sum, row) => sum + row.unresolved_event_count,
        0,
      );

      expect(unresolved).toBe(UNRESOLVED_TODAY);
    },
  );

  it("leaves every day but today complete, so a per-day read is testable", () => {
    const rows = buildDailyRows();
    const partial = rows.filter((row) => row.unresolved_event_count > 0);

    expect(partial).toHaveLength(1);
    expect(partial[0]).toBe(rows[rows.length - 1]);
  });

  it("keeps the narrative: contiguous days, every one billed above provider cost", () => {
    const rows = buildDailyRows();

    for (const [i, row] of rows.entries()) {
      expect(row.billed_cost_micros).toBeGreaterThan(row.provider_cost_micros);
      const previous = rows[i - 1];
      if (previous) {
        expect(Date.parse(row.day) - Date.parse(previous.day)).toBe(86_400_000);
      }
    }

    const provider = rows.reduce((sum, row) => sum + row.provider_cost_micros, 0);
    const billed = rows.reduce((sum, row) => sum + row.billed_cost_micros, 0);
    expect(billed / provider).toBeGreaterThan(1.2);
    expect(billed / provider).toBeLessThan(1.4);
  });

  it("is stable across calls, so charts do not jitter between renders", () => {
    // Pinned so the two calls cannot land either side of UTC midnight.
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-08-06T13:45:00Z"));

    expect(buildDailyRows()).toEqual(buildDailyRows());
  });
});

describe("buildUsageInvoices", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it.each(CLOCKS)("bills this month and last month when today is %s", (clock) => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date(clock));

    const now = new Date(clock);
    const first = (monthsAgo: number) =>
      new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth() - monthsAgo, 1))
        .toISOString()
        .slice(0, 10);

    const periods = new Set(buildUsageInvoices().map((invoice) => invoice.period_start));

    expect([...periods].sort()).toEqual([first(1), first(0)]);
  });

  it("keeps the story: last month pushed, this month still closing", () => {
    const invoices = buildUsageInvoices();
    const periods = [...new Set(invoices.map((i) => i.period_start))].sort();
    const [previous, current] = periods;

    const statuses = (period: string | undefined) =>
      new Set(invoices.filter((i) => i.period_start === period).map((i) => i.status));

    // The closed period has reached Stripe (one customer permanently failed);
    // the open one is still working through the push queue.
    expect(statuses(previous)).toEqual(new Set(["pushed", "failed_permanent"]));
    expect(statuses(current)).toEqual(new Set(["pushing", "pending", "failed", "skipped"]));
  });
});
