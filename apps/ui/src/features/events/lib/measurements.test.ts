import { describe, expect, it } from "vitest";

import { MEASUREMENTS_STATUS_VALUES } from "@/lib/vocabulary";

import {
  MEASUREMENTS_STATUS_EXPLANATIONS,
  NO_QUANTITIES_RECORDED,
  measurementsStatusLabel,
} from "./measurements";

describe("measurement status wording", () => {
  it("takes each status's name from the catalogue, not from the console", () => {
    expect(measurementsStatusLabel("available")).toBe("Measurements available");
    expect(measurementsStatusLabel("pruned")).toBe(
      "Measurements no longer retained",
    );
    expect(measurementsStatusLabel("not_applicable")).toBe(
      "No measurements apply",
    );
  });

  it("explains every status the registry declares", () => {
    for (const status of MEASUREMENTS_STATUS_VALUES) {
      expect(MEASUREMENTS_STATUS_EXPLANATIONS[status].trim()).not.toBe("");
    }
    expect(Object.keys(MEASUREMENTS_STATUS_EXPLANATIONS).sort()).toEqual(
      [...MEASUREMENTS_STATUS_VALUES].sort(),
    );
  });

  // The three-way distinction has to survive into the words, or the field is
  // carried all the way to the surface and then collapsed there. Two states
  // that share an explanation are two states a reader cannot tell apart.
  it("gives the three states three different explanations", () => {
    const explanations = Object.values(MEASUREMENTS_STATUS_EXPLANATIONS);

    expect(new Set(explanations).size).toBe(explanations.length);
  });

  // The sentence a pruned payload must never get. It is a true thing to say
  // about a metered posting whose record is present and empty, and a false one
  // about a posting whose record was removed at its retention horizon — which
  // is why it is a named constant rather than a string literal in the renderer:
  // the assertion that it stays away from the pruned case needs something to
  // name.
  it("keeps the no-usage sentence out of every status explanation", () => {
    expect(NO_QUANTITIES_RECORDED.trim()).not.toBe("");
    for (const status of MEASUREMENTS_STATUS_VALUES) {
      expect(MEASUREMENTS_STATUS_EXPLANATIONS[status]).not.toBe(
        NO_QUANTITIES_RECORDED,
      );
    }
  });
});
