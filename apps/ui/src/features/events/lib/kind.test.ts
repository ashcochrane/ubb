import { describe, expect, it } from "vitest";

import { USAGE_EVENT_KIND_VALUES } from "@/lib/vocabulary";

import { usageEventKindLabel } from "./kind";

describe("the words for which kind of posting this is", () => {
  it("are the catalogue's, not the console's", () => {
    expect(usageEventKindLabel("metered_usage")).toBe("Metered usage");
    expect(usageEventKindLabel("task_charge")).toBe("Task charge");
  });

  // Every kind the registry declares has words, and the two are different
  // words: a charge posting and a metered one rendered under one name would
  // be the discriminator carried all the way to the surface and collapsed
  // there.
  it("give every kind the registry declares its own name", () => {
    const names = USAGE_EVENT_KIND_VALUES.map((kind) => usageEventKindLabel(kind));

    for (const name of names) expect(name).not.toMatch(/^\[no label/);
    expect(new Set(names).size).toBe(USAGE_EVENT_KIND_VALUES.length);
  });

  it("render a kind the registry has never seen as itself, never humanised", () => {
    expect(usageEventKindLabel("some_future_kind")).toBe("some_future_kind");
  });
});
