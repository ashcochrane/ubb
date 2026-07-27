import { describe, expect, it } from "vitest";
import { formatMicros, formatDate } from "./format";
import { formatDollars, formatSignedDollars, formatFileSize, formatRoundedDollars } from "./format";

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

describe("formatDate", () => {
  it("formats ISO date string", () => {
    const result = formatDate("2026-03-13T10:30:00Z");
    expect(result).toContain("Mar");
    expect(result).toContain("13");
    expect(result).toContain("2026");
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
