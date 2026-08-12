import { describe, expect, it } from "vitest";

import {
  availableMeasurements,
  measurementsNotApplicable,
  prunedMeasurements,
} from "./economic-scenarios";
import { MEASUREMENTS_STATUS_VALUES } from "./vocabulary";

describe("measurement scenarios", () => {
  it("carries the recorded quantities, and says they can be read", () => {
    const scenario = availableMeasurements({
      input_tokens: 4200,
      output_tokens: 1730,
    });

    expect(scenario.measurements).toEqual({
      input_tokens: 4200,
      output_tokens: 1730,
    });
    expect(scenario.measurements_status).toBe("available");
  });

  it("says an empty bag is a REMOVAL when the detail was pruned", () => {
    const scenario = prunedMeasurements();

    expect(scenario.measurements).toEqual({});
    expect(scenario.measurements_status).toBe("pruned");
  });

  it("says an empty bag is an ABSENCE when the posting was never measured", () => {
    const scenario = measurementsNotApplicable();

    expect(scenario.measurements).toEqual({});
    expect(scenario.measurements_status).toBe("not_applicable");
  });

  // The property the module exists for. Two of the three states carry the same
  // empty bag, so the bag alone cannot say which one a fixture meant — that
  // ambiguity is the whole defect `measurements_status` was coined to end
  // (`domain-vocabulary/concepts/economics.yaml`). Binding the two facts into
  // one returned object is what stops a fixture author restating half of it.
  it("never yields a bag without the status that says what it means", () => {
    const scenarios = [
      availableMeasurements({ input_tokens: 1 }),
      prunedMeasurements(),
      measurementsNotApplicable(),
    ];

    for (const scenario of scenarios) {
      expect(Object.keys(scenario)).toEqual([
        "measurements",
        "measurements_status",
      ]);
    }
  });

  // Driven off the generated value list rather than a hand-written trio: the
  // registry declares `measurements_status` CLOSED and complete, so a value
  // arriving here with no scenario behind it is a state no console fixture can
  // represent — which is exactly the gap #155 §9.2 makes a slice pay for.
  it("covers every state the registry declares, one scenario each", () => {
    const produced = [
      availableMeasurements({}),
      prunedMeasurements(),
      measurementsNotApplicable(),
    ].map((scenario) => scenario.measurements_status);

    expect([...produced].sort()).toEqual([...MEASUREMENTS_STATUS_VALUES].sort());
  });

  it("hands each caller its own object, so one fixture cannot edit another", () => {
    const first = prunedMeasurements();
    const second = prunedMeasurements();

    expect(first).not.toBe(second);
    expect(first.measurements).not.toBe(second.measurements);
  });
});
