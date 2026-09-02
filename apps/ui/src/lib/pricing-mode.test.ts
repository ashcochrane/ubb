import { describe, expect, it } from "vitest";

import { PRICING_MODE_VALUES } from "./vocabulary";
import { pricingModeLabel } from "./pricing-mode";

describe("the words for how a kind of work is sold", () => {
  it("are the catalogue's, not the console's", () => {
    expect(pricingModeLabel("event_priced")).toBe("Event priced");
    expect(pricingModeLabel("fixed")).toBe("Fixed price");
  });

  it("give every regime the registry declares its own name", () => {
    const names = PRICING_MODE_VALUES.map((mode) => pricingModeLabel(mode));

    for (const name of names) expect(name).not.toMatch(/^\[no label/);
    expect(new Set(names).size).toBe(PRICING_MODE_VALUES.length);
  });

  it("render a regime the registry has never seen as itself, never humanised", () => {
    expect(pricingModeLabel("some_future_regime")).toBe("some_future_regime");
  });
});
