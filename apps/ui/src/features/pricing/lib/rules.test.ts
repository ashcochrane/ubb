import { describe, expect, it } from "vitest";

import type { GroupingFieldDef, Rule } from "../api/types";
import { pinnableGroupingFields, pinnedSelectors, rateStructureLabel } from "./rules";

/**
 * Ten declared slots, which is the count ruling 15 made reachable (#366).
 *
 * ⚠ **A SIX-ENTRY REGISTRY WOULD MAKE EVERY ASSERTION BELOW PASS AND PROVE
 * NOTHING.** The gap the ruling closed was a published list that named six of
 * the ten selectors a rule can pin, so a rule pinned on the seventh was
 * writable server-side and unreachable through the API. A console test whose
 * fixture stopped at six would be testing the world as it was before the fix.
 */
const DECLARED: GroupingFieldDef[] = [
  "model",
  "region",
  "environment",
  "team",
  "workflow",
  "channel",
  "tier",
  "deployment",
  "pipeline",
  "cohort",
].map((key, index) => ({
  key,
  slot: `grouping_field_${index + 1}`,
  scope: "usage_event",
  max_cardinality: 200,
  retired: false,
}));

function ruleWith(pins: Partial<Rule>): Rule {
  return {
    id: "rule-1",
    book_id: "book-1",
    lineage_id: "lineage-1",
    measurement_key: "gpt4o_input_tokens",
    provider: "",
    event_type: "",
    task_type: "",
    subtask_type: "",
    grouping_field_1: "",
    grouping_field_2: "",
    grouping_field_3: "",
    grouping_field_4: "",
    grouping_field_5: "",
    grouping_field_6: "",
    grouping_field_7: "",
    grouping_field_8: "",
    grouping_field_9: "",
    grouping_field_10: "",
    rate_structure: "per_unit",
    rate_per_unit_micros: 1_000_000,
    unit_quantity: 1_000_000,
    fixed_micros: 0,
    currency: "usd",
    valid_from: "2026-06-01T00:00:00Z",
    valid_to: null,
    ...pins,
  };
}

describe("what a rule pins", () => {
  it("reads every one of the ten slots, not the six the contract used to name", () => {
    // The seventh and the tenth specifically: those are inside the four that
    // had no published property, so a reader built against the old contract
    // would show neither.
    const rule = ruleWith({ grouping_field_7: "premium", grouping_field_10: "eu" });

    expect(pinnedSelectors(rule, DECLARED)).toEqual([
      { key: "tier", value: "premium" },
      { key: "cohort", value: "eu" },
    ]);
  });

  // ⚠ THE TENANT'S OWN WORD, NEVER THE SLOT NUMBER (#277's ruling, one feature
  // over). "grouping_field_7" is console English for a position the tenant
  // never chose; "tier" is what they declared, and it is the only thing on the
  // screen they can act on.
  it("labels a pin with the key the tenant declared", () => {
    const pins = pinnedSelectors(ruleWith({ grouping_field_1: "gpt-4o" }), DECLARED);

    expect(pins).toEqual([{ key: "model", value: "gpt-4o" }]);
    expect(JSON.stringify(pins)).not.toContain("grouping_field");
  });

  it("puts the named selectors ahead of the tenant's own", () => {
    const rule = ruleWith({
      provider: "openai",
      event_type: "chat.completion",
      grouping_field_1: "gpt-4o",
    });

    expect(pinnedSelectors(rule, DECLARED).map((pin) => pin.key)).toEqual([
      "provider",
      "event type",
      "model",
    ]);
  });

  it("says nothing at all for a rule that pins nothing", () => {
    expect(pinnedSelectors(ruleWith({}), DECLARED)).toEqual([]);
  });

  // ⚠ A RETIRED DECLARATION STILL RENDERS ON A RULE THAT PINS IT. A tenant who
  // has stopped using a grouping field must not be able to write new rules
  // against it, and must still be able to read the rules they wrote when they
  // did — so the two questions get two functions rather than one filter.
  it("keeps a retired field readable while refusing it to the editor", () => {
    const withRetired: GroupingFieldDef[] = DECLARED.map((field) =>
      field.key === "tier" ? { ...field, retired: true } : field,
    );
    const rule = ruleWith({ grouping_field_7: "premium" });

    expect(pinnedSelectors(rule, withRetired)).toEqual([
      { key: "tier", value: "premium" },
    ]);
    expect(pinnableGroupingFields(withRetired).map((field) => field.key)).not.toContain(
      "tier",
    );
    expect(pinnableGroupingFields(withRetired)).toHaveLength(9);
  });

  it("offers nothing to pin for a tenant who has declared nothing", () => {
    expect(pinnedSelectors(ruleWith({ grouping_field_1: "gpt-4o" }), [])).toEqual([]);
    expect(pinnableGroupingFields([])).toEqual([]);
  });
});

describe("the arithmetic shape's wording", () => {
  it("comes from the catalogue rather than from a map beside the values", () => {
    expect(rateStructureLabel("per_unit")).toBe("Per unit");
    expect(rateStructureLabel("fixed_component")).toBe("Fixed component");
  });
});
