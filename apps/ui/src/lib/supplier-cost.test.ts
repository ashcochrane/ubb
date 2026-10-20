import { describe, expect, it } from "vitest";

import { ABSENT_LABEL } from "./localisation";
import {
  amountOver,
  COSTING_STATUS_EXPLANATIONS,
  costingStatusLabel,
  incompleteFigure,
  isPartial,
  marginOver,
  marginPercentOver,
  partialTotalNote,
  shareOver,
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

  // ⚠ MARKED, AND NEVER AS A BOUND (#603, ADR-0020 §6): a cost left out may
  // be negative, so the complete figure may be higher or lower than this.
  it("renders a partial total marked incomplete, never as a figure and never as a bound", () => {
    expect(supplierCostTotal(4_200_000, PARTIAL, "usd")).toBe("$4.20 (Incomplete)");
    expect(supplierCostTotal(4_200_000, PARTIAL, "usd")).not.toMatch(/at least|at most/);
  });

  it("renders a partial total whose resolved sum is negative, marked the same way", () => {
    expect(supplierCostTotal(-1_500_000, PARTIAL, "usd")).toBe("-$1.50 (Incomplete)");
  });

  // A resolved zero is a real amount (ADR-0007 §2) and says so.
  it("renders a whole zero as zero, because that is what it is", () => {
    expect(supplierCostTotal(0, WHOLE, "usd")).toBe("$0.00");
  });

  // THE SHARPEST CASE, and the one a mark alone gets wrong. A window whose
  // every resolved cost sums to nothing, with events still uncosted: "$0.00",
  // marked or not, is read as "this was free", which is exactly the misreading
  // this module exists to make impossible. No total is known, so nothing is
  // stated as a number.
  it("renders NO amount when the resolved sum is zero and costs are still missing", () => {
    expect(supplierCostTotal(0, PARTIAL, "usd")).toBe(ABSENT_LABEL);
    expect(supplierCostTotal(0, PARTIAL, "usd")).not.toContain("0.00");
  });

  it("formats in the tenant's currency", () => {
    expect(supplierCostTotal(4_200_000, PARTIAL, "gbp")).toBe("£4.20 (Incomplete)");
  });
});

describe("marginOver", () => {
  // The backend states this rather than the console inferring it: a markup is
  // billed minus the RESOLVED supplier cost, and the contract says so on the
  // measure itself: `EconomicMeasureOut.status` reads `incomplete` when the
  // figure is the sum of the inputs that resolved (#501; #603 retired the
  // bound it used to promise).
  it("renders a margin beside a whole cost as the plain amount", () => {
    expect(marginOver(9_000_000, WHOLE, "usd")).toBe("$9.00");
  });

  it("marks a margin beside a partial cost, and promises no direction", () => {
    expect(marginOver(9_000_000, PARTIAL, "usd")).toBe("$9.00 (Incomplete)");
    expect(marginOver(-1_500_000, PARTIAL, "usd")).toBe("-$1.50 (Incomplete)");
  });

  it("marks the percentage the same way", () => {
    expect(marginPercentOver(62.5, WHOLE)).toBe("62.5%");
    expect(marginPercentOver(62.5, PARTIAL)).toBe("62.5% (Incomplete)");
  });
});

describe("the one mark", () => {
  it("is the catalogue's word for an incomplete measure, and only where asked", () => {
    expect(incompleteFigure("$1.00", true)).toBe("$1.00 (Incomplete)");
    expect(incompleteFigure("$1.00", false)).toBe("$1.00");
    expect(shareOver(41, true)).toBe("41% (Incomplete)");
    expect(shareOver(41, false)).toBe("41%");
    expect(amountOver(1_760_000, "usd", true)).toBe("$1.76 (Incomplete)");
    expect(amountOver(1_760_000, "usd", false)).toBe("$1.76");
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
  it("says how many events are missing, and that the total is the sum of what resolved", () => {
    const note = partialTotalNote(3);

    expect(note).toContain("3");
    expect(note).toContain("not included");
    expect(note).not.toMatch(/higher|lower|at least|floor/);
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
