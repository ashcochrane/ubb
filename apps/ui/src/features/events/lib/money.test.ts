import { describe, expect, it } from "vitest";

import { formatEventMicros, formatSignedEventMicros } from "./money";

describe("formatEventMicros", () => {
  it("keeps 4-decimal precision for sub-unit amounts", () => {
    // 4,900 micros = $0.0049 — 2-decimal rounding would show $0.00.
    expect(formatEventMicros(4_900, "usd")).toBe("$0.0049");
    // 35,000 micros = $0.035 — 2-decimal rounding would show $0.04 (14% off).
    expect(formatEventMicros(35_000, "usd")).toBe("$0.0350");
    expect(formatEventMicros(187_500, "usd")).toBe("$0.1875");
  });

  it("uses standard 2-decimal formatting at and above one unit", () => {
    expect(formatEventMicros(1_000_000, "usd")).toBe("$1.00");
    expect(formatEventMicros(2_350_000, "usd")).toBe("$2.35");
  });

  it("renders zero as a plain 2-decimal zero", () => {
    expect(formatEventMicros(0, "usd")).toBe("$0.00");
  });

  it("respects the tenant currency", () => {
    expect(formatEventMicros(4_900, "eur")).toBe("€0.0049");
  });
});

describe("formatSignedEventMicros", () => {
  it("signs non-zero amounts in both precision ranges", () => {
    expect(formatSignedEventMicros(45_200, "usd")).toBe("+$0.0452");
    expect(formatSignedEventMicros(-45_200, "usd")).toBe("-$0.0452");
    expect(formatSignedEventMicros(1_250_000, "usd")).toBe("+$1.25");
  });

  it("leaves zero unsigned", () => {
    expect(formatSignedEventMicros(0, "usd")).toBe("$0.00");
  });
});
