// What an invoice-line grouping choice means (#508; slice 7 §6, §11).
//
// THE DECISION LIVES HERE AND THE CARD ONLY RENDERS IT, which is why this file
// carries the cases: a Base UI select's options cannot be reliably chosen in
// jsdom, so a component test can prove the warning renders for the axis the
// form is ON but not that it follows every possible choice. Holding the rule in
// a pure function makes the second half provable, and makes the first half a
// rendering assertion rather than a re-test of the rule.

import { describe, expect, it } from "vitest";

import type { GroupingOption } from "@/lib/grouping-axis";
import { FIELD_KIND, ROLLUP_KIND } from "@/lib/grouping-axis";

import { cardinalityWarning, isRollup, ROLLUPS_ARE_PREFERRED } from "./invoice-lines";

/** A discovery-contract row, typed as the base so every property is checked. */
const BASE: GroupingOption = {
  key: "field:model",
  kind: FIELD_KIND,
  label: "model",
  rollup: null,
  source_grain: "event",
  supported_surfaces: ["analytics", "invoice_lines"],
  unsupported_measures: [],
  max_cardinality: null,
};

function option(over: Partial<GroupingOption>): GroupingOption {
  return { ...BASE, ...over };
}

describe("cardinalityWarning", () => {
  it("warns on a capped axis, naming the cap and preferring a rollup", () => {
    const warning = cardinalityWarning(option({ max_cardinality: 200 }));
    expect(warning).toContain("200");
    expect(warning).toContain("one line per distinct value");
    expect(warning).toContain(ROLLUPS_ARE_PREFERRED);
  });

  // ⚠ **THE CAP IS NOT A CEILING ON THE LINE COUNT, AND SAYING SO WOULD
  // REASSURE EXACTLY WHERE THE SERVER WARNS.** `invoice_line_cardinality_warning`
  // exists because the values actually recorded CAN exceed the declared
  // maximum — its own sentence is "has recorded more than {ceiling} distinct
  // values" — so a console promising the invoice "could run to 200 lines"
  // would be contradicting the warning it is there to anticipate.
  it("does not present the declared cap as a limit on the line count", () => {
    const warning = cardinalityWarning(option({ max_cardinality: 200 })) ?? "";
    expect(warning).toContain("nothing caps how many that is");
    expect(warning).not.toMatch(/could run to 200 lines/);
    expect(warning).not.toMatch(/at most 200/);
  });

  // ⚠ NOT AN OMISSION. UBB's own axes and the rollups carry no declared cap,
  // so there is no maximum to exceed and nothing honest to say — the row's own
  // `max_cardinality` decides, exactly as it does on the server, rather than
  // the console inventing a second rule that could disagree with it.
  it("says nothing about an axis with no declared maximum", () => {
    expect(cardinalityWarning(option({ max_cardinality: null }))).toBeNull();
    expect(
      cardinalityWarning(
        option({ key: "rollup:event_category", kind: ROLLUP_KIND, rollup: "event_category" }),
      ),
    ).toBeNull();
  });

  it("says nothing where no axis is chosen at all", () => {
    expect(cardinalityWarning(undefined)).toBeNull();
  });

  // It WARNS and never refuses: the cap is a keyspace bound the tenant set on
  // their own axis, not an invariant UBB may decline to bill against. A zero
  // cap is still a warning rather than a block.
  it("warns rather than refusing, even at a cap of zero", () => {
    expect(cardinalityWarning(option({ max_cardinality: 0 }))).toContain("0");
  });
});

describe("isRollup", () => {
  it("tells a join to a rollup apart from a column on the event", () => {
    expect(isRollup(option({ kind: ROLLUP_KIND }))).toBe(true);
    expect(isRollup(option({ kind: FIELD_KIND }))).toBe(false);
    expect(isRollup(undefined)).toBe(false);
  });
});
