import { afterAll, beforeAll, describe, expect, it, vi } from "vitest";
import {
  formatMicros,
  formatDate,
  formatShortDate,
  formatCalendarDate,
  formatPrice,
  formatCostMicros,
} from "./format";
import { formatDollars, formatSignedDollars, formatFileSize, formatRoundedDollars } from "./format";

// The date-drift regressions only reproduce west of UTC: a bare "2026-07-01"
// parses as UTC midnight, which naive local-zone formatting shows as Jun 30
// in the Americas. Pin the file to a west-of-UTC zone so the UTC-safe paths
// are actually exercised (Node resets its tz cache when process.env.TZ is set).
beforeAll(() => {
  vi.stubEnv("TZ", "America/New_York");
});
afterAll(() => {
  vi.unstubAllEnvs();
});

describe("formatMicros", () => {
  it("formats positive micros to dollars", () => {
    expect(formatMicros(1_500_000)).toBe("$1.50");
  });
  it("formats zero", () => {
    expect(formatMicros(0)).toBe("$0.00");
  });
  it("formats negative micros", () => {
    expect(formatMicros(-500_000)).toBe("-$0.50");
  });
});

describe("formatCalendarDate", () => {
  it("renders a bare calendar date without local-tz day shift", () => {
    // Guard: confirm the TZ pin took effect — naive local rendering of UTC
    // midnight must land on the previous day, or this regression test is inert.
    expect(
      new Intl.DateTimeFormat("en-US", { day: "numeric" }).format(new Date("2026-07-01")),
    ).toBe("30");
    expect(formatCalendarDate("2026-07-01")).toBe("Jul 1, 2026");
  });
  it("renders UTC-midnight day buckets on the correct day", () => {
    expect(formatCalendarDate("2026-07-01T00:00:00Z")).toBe("Jul 1, 2026");
  });
});

describe("formatDate", () => {
  it("formats ISO timestamps in the viewer's local zone", () => {
    const result = formatDate("2026-03-13T10:30:00Z");
    expect(result).toContain("Mar");
    expect(result).toContain("13");
    expect(result).toContain("2026");
  });
  it("routes bare YYYY-MM-DD input through the UTC calendar path (no time shown)", () => {
    expect(formatDate("2026-07-01")).toBe("Jul 1, 2026");
  });
});

describe("formatShortDate", () => {
  it("uses the same en-US order as formatDate", () => {
    expect(formatShortDate("2026-07-14T12:00:00Z")).toBe("Jul 14, 2026");
  });
  it("does not shift bare calendar dates for west-of-UTC viewers", () => {
    expect(formatShortDate("2026-07-01")).toBe("Jul 1, 2026");
  });
});

describe("formatPrice", () => {
  it("formats per-unit rates with quantity suffixes", () => {
    expect(formatPrice(2_500_000, 1_000)).toBe("$2.5 / 1K");
    expect(formatPrice(100, 1_000_000)).toBe("$0.0001 / 1M");
  });
  it("keeps sub-dollar precision without a suffix for unit quantity 1", () => {
    expect(formatPrice(35_000, 1)).toBe("$0.035");
  });
  it("uses the display unit when provided", () => {
    expect(formatPrice(35_000, 1, "per request")).toBe("$0.035 / request");
  });
  it("formats in the given currency (accepts lowercase API codes)", () => {
    expect(formatPrice(35_000, 1, undefined, "eur")).toBe("€0.035");
    expect(formatPrice(2_500_000, 1_000, undefined, "GBP")).toBe("£2.5 / 1K");
  });
});

describe("formatCostMicros", () => {
  it("formats large values as whole units", () => {
    expect(formatCostMicros(1_247_000_000)).toBe("$1,247");
  });
  it("formats zero", () => {
    expect(formatCostMicros(0)).toBe("$0");
  });
  it("keeps 4-decimal precision below one unit", () => {
    expect(formatCostMicros(14_800)).toBe("$0.0148");
  });
  it("formats in the given currency, including the sub-unit branch", () => {
    expect(formatCostMicros(1_247_000_000, "gbp")).toBe("£1,247");
    expect(formatCostMicros(14_800, "eur")).toBe("€0.0148");
  });
  it("formats negative values with a leading sign", () => {
    expect(formatCostMicros(-5_000_000)).toBe("-$5");
    expect(formatCostMicros(-500_000)).toBe("-$0.5000");
  });
});

describe("formatDollars", () => {
  it("formats whole dollars with thousands separators", () => {
    expect(formatDollars(1247)).toBe("$1,247");
    expect(formatDollars(0)).toBe("$0");
    expect(formatDollars(1_234_567)).toBe("$1,234,567");
  });
  it("formats with 2 decimals when fractional", () => {
    expect(formatDollars(12.5)).toBe("$12.50");
    expect(formatDollars(0.07)).toBe("$0.07");
  });
  it("formats negative fractional dollars", () => {
    expect(formatDollars(-12.5)).toBe("-$12.50");
  });
});

describe("formatRoundedDollars", () => {
  it("rounds to whole dollars with thousands separators", () => {
    expect(formatRoundedDollars(1247.89)).toBe("$1,248");
    expect(formatRoundedDollars(0)).toBe("$0");
  });
  it("rounds a fractional dollar input to the nearest whole dollar", () => {
    expect(formatDollars(0.5)).toBe("$0.50");
    expect(formatRoundedDollars(0.5)).toBe("$1");
  });
});

describe("formatSignedDollars", () => {
  it("prefixes positive with +", () => {
    expect(formatSignedDollars(25)).toBe("+$25");
  });
  it("prefixes negative with -", () => {
    expect(formatSignedDollars(-25)).toBe("-$25");
  });
  it("zero has no sign", () => {
    expect(formatSignedDollars(0)).toBe("$0");
  });
  it("prefixes fractional positive with + and preserves decimals", () => {
    expect(formatSignedDollars(12.5)).toBe("+$12.50");
  });
});

describe("formatFileSize", () => {
  it("formats bytes as MB", () => {
    expect(formatFileSize(1_500_000)).toBe("2 MB");
    expect(formatFileSize(0)).toBe("0 MB");
  });
  it("formats sub-MB as KB", () => {
    expect(formatFileSize(500)).toBe("1 KB");
  });
  it("returns 1 KB for sub-KB inputs", () => {
    expect(formatFileSize(1)).toBe("1 KB");
  });
});
