import { describe, expect, it } from "vitest";
import { formatMicros, formatDate } from "./format";

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
