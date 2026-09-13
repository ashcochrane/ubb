import { describe, expect, it } from "vitest";

import { formatSignedEventMicros } from "./money";

// `formatEventMicros` itself is held in `@/lib/format.test.ts` since #466.
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
