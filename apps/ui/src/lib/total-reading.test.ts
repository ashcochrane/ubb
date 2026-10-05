import { describe, expect, it } from "vitest";

import { describeTotal, eventsHave, readTotal, UNKNOWN_TOTAL } from "./total-reading";

describe("a total beside the count of what it left out", () => {
  it("is a figure when nothing is missing — including a real zero", () => {
    expect(readTotal(4_200_000, 0)).toEqual({ kind: "figure", micros: 4_200_000 });
    const zero = readTotal(0, 0);
    expect(zero).toEqual({ kind: "figure", micros: 0 });
    expect(describeTotal(zero, "usd")).toBe("$0.00");
  });

  it("is a floor when something is missing and the resolved part is above zero", () => {
    const floor = readTotal(900_000, 2);
    expect(floor).toEqual({ kind: "floor", micros: 900_000, eventsLeftOut: 2 });
    expect(describeTotal(floor, "usd")).toBe("at least $0.90");
  });

  // The third outcome, and the one a dash could not carry in a column beside
  // real zeros: nothing resolved and something left out is no amount at all.
  it("is unknown, never a zero, when nothing was ever resolved", () => {
    const unknown = readTotal(0, 3);
    expect(unknown).toEqual({ kind: "unknown", eventsLeftOut: 3 });
    expect(describeTotal(unknown, "usd")).toBe(UNKNOWN_TOTAL);
    expect(describeTotal(unknown, "usd")).not.toMatch(/\$/);
  });

  // One unit of work's running total is a few hundred micros in a Verify run
  // (#581); the default would write a known amount of that size as `$0.00`.
  it("writes the amount with the formatter it is handed, and an unknown with none", () => {
    const tenths = (micros: number) => `${micros / 100_000} tenths`;
    expect(describeTotal(readTotal(314, 0), "usd", tenths)).toBe("0.00314 tenths");
    expect(describeTotal(readTotal(300_000, 1), "usd", tenths)).toBe("at least 3 tenths");
    expect(describeTotal(readTotal(0, 1), "usd", tenths)).toBe(UNKNOWN_TOTAL);
  });

  it("puts the count in the subject of the sentence, singular and plural", () => {
    expect(eventsHave(1)).toBe("1 event has");
    expect(eventsHave(2)).toBe("2 events have");
  });
});
