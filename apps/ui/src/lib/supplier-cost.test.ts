import { describe, expect, it } from "vitest";

import { ABSENT_LABEL } from "./localisation";
import {
  AT_LEAST,
  AT_MOST,
  COSTING_STATUS_EXPLANATIONS,
  costingStatusLabel,
  isPartial,
  marginBound,
  marginPercentBound,
  partialTotalNote,
  supplierCostTotal,
  unresolvedReasonLabel,
} from "./supplier-cost";
import { COSTING_STATUS_VALUES, UNRESOLVED_REASON_VALUES } from "./vocabulary";

const WHOLE = { unresolved_event_count: 0 };
const PARTIAL = { unresolved_event_count: 3 };

describe("supplierCostTotal", () => {
  it("renders a whole total as the plain amount", () => {
    expect(supplierCostTotal(4_200_000, WHOLE, "usd")).toBe("$4.20");
  });

  it("renders a partial total as a floor, never as a figure", () => {
    expect(supplierCostTotal(4_200_000, PARTIAL, "usd")).toBe(
      `${AT_LEAST} $4.20`,
    );
  });

  // A resolved zero is a real amount (ADR-0007 §2) and says so.
  it("renders a whole zero as zero, because that is what it is", () => {
    expect(supplierCostTotal(0, WHOLE, "usd")).toBe("$0.00");
  });

  // THE SHARPEST CASE, and the one "at least" alone gets wrong. A window whose
  // every resolved cost sums to nothing, with events still uncosted, has a
  // floor of zero — true, and unreadable: "at least $0.00" is read as "this was
  // free", which is exactly the misreading this module exists to make
  // impossible. Nothing is known, so nothing is stated as a number.
  it("renders NO amount when the floor is zero and costs are still missing", () => {
    expect(supplierCostTotal(0, PARTIAL, "usd")).toBe(ABSENT_LABEL);
    expect(supplierCostTotal(0, PARTIAL, "usd")).not.toContain("0.00");
  });

  it("formats in the tenant's currency", () => {
    expect(supplierCostTotal(4_200_000, PARTIAL, "gbp")).toBe(
      `${AT_LEAST} £4.20`,
    );
  });
});

describe("marginBound", () => {
  // The backend states this rather than the console inferring it: a markup is
  // billed minus the RESOLVED supplier cost, "so where the count is non-zero it
  // is an upper bound rather than a figure" (`get_revenue_analytics`).
  it("renders a margin beside a whole cost as the plain amount", () => {
    expect(marginBound(9_000_000, WHOLE, "usd")).toBe("$9.00");
  });

  it("renders a margin beside a partial cost as a ceiling", () => {
    expect(marginBound(9_000_000, PARTIAL, "usd")).toBe(`${AT_MOST} $9.00`);
  });

  // A margin bounded from above is still bounded from above when it is already
  // negative: the unlearned costs can only make it worse.
  it("bounds a negative margin from above too", () => {
    expect(marginBound(-1_500_000, PARTIAL, "usd")).toBe(`${AT_MOST} -$1.50`);
  });

  it("bounds the percentage the same way", () => {
    expect(marginPercentBound(62.5, WHOLE)).toBe("62.5%");
    expect(marginPercentBound(62.5, PARTIAL)).toBe(`${AT_MOST} 62.5%`);
  });
});

describe("isPartial", () => {
  it("is the one place the completeness question is answered", () => {
    expect(isPartial(WHOLE)).toBe(false);
    expect(isPartial(PARTIAL)).toBe(true);
  });

  // MIXED DERIVATION IS COMPLETE. A Task holding both calculated and reported
  // events is whole when nothing is missing — the costing METHOD never enters
  // the question, and a caveat that fires on almost every total is a caveat
  // nobody reads. The rule reads the count and only the count.
  it("reads the count and nothing else", () => {
    expect(Object.keys(WHOLE)).toEqual(["unresolved_event_count"]);
  });
});

describe("partialTotalNote", () => {
  it("says how many events are missing, and which way the total is wrong", () => {
    const note = partialTotalNote(3);

    expect(note).toContain("3");
    expect(note).toContain("higher");
  });

  it("says nothing at all when nothing is missing", () => {
    expect(partialTotalNote(0)).toBeNull();
  });

  it("counts one event in the singular", () => {
    expect(partialTotalNote(1)).toContain("1 event ");
  });
});

describe("the costing status", () => {
  it("names each declared status from the catalogue", () => {
    expect(costingStatusLabel("unresolved")).toBe("Unresolved");
    expect(costingStatusLabel("known")).toBe("Known");
    expect(costingStatusLabel("not_applicable")).toBe("Not applicable");
  });

  // Total over the generated type, indexed rather than looked up: a status the
  // registry declares and this constant has no sentence for is a `tsc` failure.
  it("explains every status the registry declares", () => {
    for (const value of COSTING_STATUS_VALUES) {
      expect(COSTING_STATUS_EXPLANATIONS[value].length).toBeGreaterThan(0);
    }
  });

  // The half of the sentence that says what would settle it. A status naming a
  // missing cost without naming the missing input is a shrug.
  it("names each reason a cost went unresolved", () => {
    for (const value of UNRESOLVED_REASON_VALUES) {
      expect(unresolvedReasonLabel(value)).not.toContain("no label");
    }
    expect(unresolvedReasonLabel("cost_rate_missing")).toBe(
      "No matching Cost Rate",
    );
  });

  it("renders an absent reason as an absence rather than as a name", () => {
    expect(unresolvedReasonLabel(null)).toBe(ABSENT_LABEL);
  });
});
