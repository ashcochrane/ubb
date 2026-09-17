import { describe, expect, it } from "vitest";

import type { GroupingOption } from "./grouping-axis";
import {
  FIELD_KIND,
  ROLLUP_KIND,
  UBB_AXIS_TITLES,
  axisName,
  axisRequestWord,
  groupingKindOf,
  isGroupingAxis,
  rollupLabel,
} from "./grouping-axis";
import { ANALYTICS_GROUPING_KIND_VALUES, ANALYTICS_ROLLUP_VALUES }
  from "./vocabulary";

/**
 * One discovery-contract row, with only the fields a picker reads stated.
 *
 * ⚠ **THE OVERRIDES ARE DELIBERATELY UNTYPED, AND THAT IS WHAT LETS THE
 * UNFAMILIAR BRANCH BE TESTED AT ALL.** `analytics_rollup` is a CLOSED concept,
 * so the contract publishes a real `enum` and the generated type is a union of
 * the two values this build knows. A server ahead of this console can still
 * answer a third — the type is a statement about the spec that generated it,
 * not a guarantee about the wire — so the runtime branch is reachable and
 * `tsc` is precisely what would NOT catch its absence. Every other row in this
 * file is type-checked by being assigned into `GroupingOption` on return.
 */
function option(over: Record<string, unknown> = {}): GroupingOption {
  return {
    key: "field:provider",
    kind: "field",
    label: "",
    rollup: null,
    source_grain: "event",
    supported_surfaces: ["analytics"],
    unsupported_measures: [],
    max_cardinality: null,
    ...over,
  } as GroupingOption;
}

describe("the axis a discovery-contract row names", () => {
  it("words one of UBB's own axes, which arrive with no label of their own", () => {
    // The contract states the asymmetry as a rule: `label` carries the
    // TENANT's word and is empty where the wording is UBB's. So a reserved
    // axis is exactly the row that has none, and the console supplies it.
    expect(axisName(option({ key: "field:provider" }))).toEqual({
      kind: "worded",
      text: "Provider",
    });
    expect(axisName(option({ key: "field:task_type" }))).toEqual({
      kind: "worded",
      text: "Kind of work",
    });
  });

  it("renders a tenant's own axis as the tenant declared it, never as English", () => {
    // `model` is the tenant's word. Title-casing it to "Model" would overwrite
    // a name somebody else chose, which is a worse defect than inventing one
    // UBB never wrote down (ADR-0008 §4.3, and `@/lib/localisation` on why).
    expect(axisName(option({ key: "field:model", label: "model" }))).toEqual({
      kind: "tenant",
      text: "model",
    });
  });

  it("words a rollup from the catalogue rather than from its token", () => {
    expect(axisName(option({
      key: "rollup:event_category",
      kind: "rollup",
      rollup: "event_category",
    }))).toEqual({ kind: "worded", text: "Event Category" });
  });

  it("hands back an axis nobody has words for as the token, to be marked", () => {
    // A sixth reserved axis, or a rollup this console's catalogue predates.
    // Both render through the open-set helper at the call site; what this
    // function promises is that it never manufactures English for either.
    expect(axisName(option({ key: "field:federation_id" })))
      .toEqual({ kind: "unworded", text: "federation_id" });
    expect(axisName(option({
      key: "rollup:supplier_family",
      kind: "rollup",
      rollup: "supplier_family",
    }))).toEqual({ kind: "unworded", text: "supplier_family" });
  });

  it("reads the axis's own name back out of the request word", () => {
    expect(axisRequestWord({ kind: "field", name: "model" })).toBe("field:model");
    expect(axisRequestWord({ kind: "rollup", name: "event_category" }))
      .toBe("rollup:event_category");
  });
});

describe("what a request word has to look like before it is worth sending", () => {
  it("accepts a word whose prefix is one of the declared kinds", () => {
    for (const kind of ANALYTICS_GROUPING_KIND_VALUES) {
      expect(isGroupingAxis(`${kind}:anything`)).toBe(true);
      expect(groupingKindOf(`${kind}:anything`)).toBe(kind);
    }
  });

  it("refuses a bare axis name, which is what the retired vocabulary sent", () => {
    // The picker used to submit `provider`, and the call site prefixed it.
    // A URL still carrying that shape names no axis the server will accept.
    expect(isGroupingAxis("provider")).toBe(false);
    expect(isGroupingAxis("nonsense")).toBe(false);
    expect(groupingKindOf("provider")).toBeUndefined();
  });

  it("refuses a prefix the registry does not declare, and an empty name", () => {
    expect(isGroupingAxis("tag:model")).toBe(false);
    expect(isGroupingAxis("field:")).toBe(false);
    expect(isGroupingAxis("")).toBe(false);
  });
});

describe("the two value sets this console now holds by reference", () => {
  it("names both kinds and no third, so none is silently never offered", () => {
    // `FIELD_KIND`/`ROLLUP_KIND` are typed against the generated set, which
    // stops a MISSPELLING. What that cannot catch is a third kind arriving and
    // this module going on offering two — the server's own `queries.py` keeps
    // the same guard on the same set for the same reason.
    expect(new Set([FIELD_KIND, ROLLUP_KIND]))
      .toEqual(new Set(ANALYTICS_GROUPING_KIND_VALUES));
  });

  it("offers a word for every rollup the registry declares", () => {
    // The catalogue's coverage is G6's to prove; what is asserted here is that
    // this module reaches it for each declared value, so a rollup shipped
    // tomorrow renders words rather than a marked token.
    for (const rollup of ANALYTICS_ROLLUP_VALUES) {
      const text = rollupLabel(rollup);
      expect(text).not.toBe(rollup);
      expect(text.startsWith("[no label:")).toBe(false);
    }
  });

  it("words every axis UBB reserves, and reserves no word for one it does not", () => {
    // The five are the server's `RESERVED_KEYS`. A word here for an axis the
    // server never offers is dead copy; an axis with no word here renders as a
    // marked token, which is the open-set rule rather than a crash — so this
    // pins the set in both directions and the test above proves the fallback.
    expect(Object.keys(UBB_AXIS_TITLES).sort()).toEqual([
      "customer",
      "event_type",
      "provider",
      "subtask_type",
      "task_type",
    ]);
  });
});
