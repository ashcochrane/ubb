import { describe, expect, it } from "vitest";

import { MOCK_KINDS } from "../api/mock-data";
import type { RunRow } from "../api/types";
import {
  CONTAINED_ROWS_SHOWN_INLINE,
  containedTotals,
  describeAgreedPrice,
  describeCustomerPrice,
  describeSupplierCost,
  directlyOnRun,
  explainCustomerPrice,
  explainSupplierCost,
  foldContainedWork,
  kindKeysForRuns,
  readAgreedPrice,
  readCustomerPrice,
  readSupplierCost,
  runsSearchSchema,
  soldAtOnePrice,
  UNKNOWN_TOTAL,
} from "./runs";

const BILLS = { meteringOnly: false, soldAtOnePrice: false } as const;

function row(overrides: Partial<RunRow> = {}): RunRow {
  return {
    task_id: "00000000-0000-4000-8000-000000000000",
    task_type: "document-summary",
    status: "completed",
    total_provider_cost_micros: 0,
    unresolved_event_count: 0,
    total_billed_cost_micros: 0,
    unpriced_event_count: 0,
    event_count: 0,
    created_at: "2026-09-01T00:00:00Z",
    ...overrides,
  };
}

describe("a supplier-cost total", () => {
  it("is a figure when nothing is missing — including a real zero", () => {
    expect(readSupplierCost({ total_provider_cost_micros: 4_200_000, unresolved_event_count: 0 })).toEqual({
      kind: "figure",
      micros: 4_200_000,
    });
    const zero = readSupplierCost({ total_provider_cost_micros: 0, unresolved_event_count: 0 });
    expect(zero).toEqual({ kind: "figure", micros: 0 });
    expect(describeSupplierCost(zero, "usd")).toBe("$0.00");
    expect(explainSupplierCost(zero)).toBeNull();
  });

  it("is a floor when something is missing and the resolved part is above zero", () => {
    const floor = readSupplierCost({ total_provider_cost_micros: 900_000, unresolved_event_count: 2 });
    expect(floor).toEqual({ kind: "floor", micros: 900_000, unresolvedEventCount: 2 });
    expect(describeSupplierCost(floor, "usd")).toBe("at least $0.90");
    expect(explainSupplierCost(floor)).toMatch(/2 events have a supplier cost UBB has not learned/);
  });

  it("is unknown, never a zero, when nothing under the run was ever costed", () => {
    const unknown = readSupplierCost({ total_provider_cost_micros: 0, unresolved_event_count: 3 });
    expect(unknown).toEqual({ kind: "unknown", unresolvedEventCount: 3 });
    expect(describeSupplierCost(unknown, "usd")).toBe(UNKNOWN_TOTAL);
    expect(describeSupplierCost(unknown, "usd")).not.toMatch(/\$/);
    expect(explainSupplierCost(unknown)).toMatch(/missing, not zero/);
  });
});

describe("a customer-price total", () => {
  it("reads figure, floor and unknown off the counts the way the supplier cost does", () => {
    expect(readCustomerPrice({ total_billed_cost_micros: 620_000, unpriced_event_count: 0 }, BILLS)).toEqual({
      kind: "figure",
      micros: 620_000,
    });
    expect(readCustomerPrice({ total_billed_cost_micros: 620_000, unpriced_event_count: 1 }, BILLS)).toEqual({
      kind: "floor",
      micros: 620_000,
      unpricedEventCount: 1,
    });
    const unknown = readCustomerPrice({ total_billed_cost_micros: 0, unpriced_event_count: 3 }, BILLS);
    expect(unknown).toEqual({ kind: "unknown", unpricedEventCount: 3 });
    expect(describeCustomerPrice(unknown, "usd")).toBe(UNKNOWN_TOTAL);
    expect(explainCustomerPrice(unknown)).toMatch(/missing, not zero/);
  });

  it("does not apply to a run sold at one agreed price, whatever its counts say", () => {
    const reading = readCustomerPrice(
      { total_billed_cost_micros: 0, unpriced_event_count: 0 },
      { meteringOnly: false, soldAtOnePrice: true },
    );
    expect(reading).toEqual({ kind: "not_applicable", reason: "fixed_task_pricing" });
    expect(describeCustomerPrice(reading, "usd")).toBe("Not applicable");
    expect(explainCustomerPrice(reading)).toMatch(/sold at one agreed price/);
  });

  it("lets the workspace's posture win the tie-break, as the backend's applicability rule does", () => {
    // Both facts true at once: a metering-only workspace running work sold at
    // one price. The reason is the posture's, never the regime's.
    const reading = readCustomerPrice(
      { total_billed_cost_micros: 0, unpriced_event_count: 0 },
      { meteringOnly: true, soldAtOnePrice: true },
    );
    expect(reading).toEqual({ kind: "not_applicable", reason: "tenant_not_billing" });
    expect(explainCustomerPrice(reading)).toMatch(/does not bill customers through UBB/);
  });

  it("reads the regime off the pinned price, which only a top-level run sold at one price carries", () => {
    expect(soldAtOnePrice(row({ agreed_price_micros: 5_000_000 }))).toBe(true);
    expect(soldAtOnePrice(row({ agreed_price_micros: 0 }))).toBe(true);
    expect(soldAtOnePrice(row({ agreed_price_micros: null }))).toBe(false);
    expect(soldAtOnePrice(row())).toBe(false);
  });
});

describe("the agreed price", () => {
  it("is nothing where nothing was pinned", () => {
    expect(readAgreedPrice(row())).toBeNull();
    expect(readAgreedPrice(row({ agreed_price_micros: null }))).toBeNull();
  });

  it("is owed on delivery and on nothing else", () => {
    const owed = readAgreedPrice(row({ agreed_price_micros: 5_000_000, status: "completed" }));
    expect(owed).toEqual({ kind: "owed", micros: 5_000_000 });
    expect(describeAgreedPrice(owed!, "usd", { meteringOnly: false })).toBe(
      "$5.00 — owed: the run delivered.",
    );
    const pending = readAgreedPrice(row({ agreed_price_micros: 5_000_000, status: "active" }));
    expect(pending).toEqual({ kind: "pending", micros: 5_000_000 });
    for (const status of ["failed", "cancelled", "killed", "expired"] as const) {
      expect(readAgreedPrice(row({ agreed_price_micros: 5_000_000, status }))).toEqual({
        kind: "not_owed",
        micros: 5_000_000,
      });
    }
  });

  it("does not say owed to a workspace that does not bill", () => {
    const owed = readAgreedPrice(row({ agreed_price_micros: 5_000_000, status: "completed" }))!;
    const said = describeAgreedPrice(owed, "usd", { meteringOnly: true });
    expect(said).toMatch(/^\$5\.00/);
    expect(said).not.toMatch(/owed/);
    expect(said).toMatch(/does not bill through UBB/);
  });
});

describe("contained work", () => {
  const pieces = (count: number): RunRow[] =>
    Array.from({ length: count }, (_, index) =>
      row({
        task_id: `piece-${index + 1}`,
        event_count: (index % 3) + 1,
        total_provider_cost_micros: (index + 1) * 1_000,
        unresolved_event_count: index % 7 === 0 ? 1 : 0,
        total_billed_cost_micros: (index + 1) * 2_000,
        unpriced_event_count: index % 5 === 0 ? 1 : 0,
      }),
    );

  it("renders whole when there are no more pieces than the inline bound", () => {
    const few = pieces(CONTAINED_ROWS_SHOWN_INLINE);
    expect(foldContainedWork(few, false)).toEqual({ shown: few, folded: 0 });
  });

  it("folds everything past the bound, and unfolds on request", () => {
    const many = pieces(CONTAINED_ROWS_SHOWN_INLINE + 5);
    const folded = foldContainedWork(many, false);
    expect(folded.shown).toHaveLength(CONTAINED_ROWS_SHOWN_INLINE);
    expect(folded.shown).toEqual(many.slice(0, CONTAINED_ROWS_SHOWN_INLINE));
    expect(folded.folded).toBe(5);
    expect(foldContainedWork(many, true)).toEqual({ shown: many, folded: 0 });
  });

  it("totals every piece, and the counts of what was left out add up like the money", () => {
    const many = pieces(30);
    const totals = containedTotals(many);
    expect(totals.count).toBe(30);
    expect(totals.event_count).toBe(many.reduce((sum, piece) => sum + piece.event_count, 0));
    expect(totals.total_provider_cost_micros).toBe(1_000 * (30 * 31) / 2);
    expect(totals.total_billed_cost_micros).toBe(2_000 * (30 * 31) / 2);
    expect(totals.unresolved_event_count).toBe(5);
    expect(totals.unpriced_event_count).toBe(6);
    // The discriminating check: the totals over the whole list differ from the
    // totals over what a folded table shows, so a roll-up summing only the
    // visible rows would answer a different number.
    const shownOnly = containedTotals(foldContainedWork(many, false).shown);
    expect(shownOnly.total_provider_cost_micros).not.toBe(totals.total_provider_cost_micros);
    expect(shownOnly.event_count).not.toBe(totals.event_count);
  });

  it("reads what was reported against the run itself as the remainder, and refuses a negative one", () => {
    const contained = containedTotals(pieces(4));
    const run = {
      event_count: contained.event_count + 2,
      total_provider_cost_micros: contained.total_provider_cost_micros + 43_000,
      unresolved_event_count: contained.unresolved_event_count,
      total_billed_cost_micros: contained.total_billed_cost_micros + 86_000,
      unpriced_event_count: contained.unpriced_event_count + 1,
    };
    expect(directlyOnRun(run, contained)).toEqual({
      event_count: 2,
      total_provider_cost_micros: 43_000,
      unresolved_event_count: 0,
      total_billed_cost_micros: 86_000,
      unpriced_event_count: 1,
    });
    expect(directlyOnRun({ ...run, event_count: contained.event_count - 1 }, contained)).toBeNull();
  });
});

describe("the runs list's URL state", () => {
  it("keeps a declared state and drops one the registry does not know", () => {
    expect(runsSearchSchema.parse({ status: "expired", task_type: "video-render" })).toEqual({
      status: "expired",
      task_type: "video-render",
    });
    expect(runsSearchSchema.parse({ status: "exploded", task_type: "" })).toEqual({});
  });

  it("offers one entry per whole-work kind, sorted, retired ones included", () => {
    const keys = kindKeysForRuns(MOCK_KINDS);
    expect(keys).toEqual([...keys].sort((a, b) => a.localeCompare(b)));
    expect(new Set(keys).size).toBe(keys.length);
    expect(keys).toContain("legacy-ocr");
    expect(keys).toContain("translate");
    // The contained-work altitude is not a kind a top-level run can be.
    expect(keys).not.toContain("render-frame");
    expect(keys).not.toContain("render-shot");
  });
});
