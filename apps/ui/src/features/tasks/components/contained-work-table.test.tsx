import { fireEvent, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { formatEventCount } from "@/lib/format";

import { containedId, RUN_ACTIVE_ID } from "../api/mock-data";
import type { RunRow } from "../api/types";
import { CONTAINED_ROWS_SHOWN_INLINE, type PriceApplicability } from "../lib/runs";
import { DRAWN_AS_FAILURE, renderWithProviders } from "../test-utils";
import { ContainedWorkTable } from "./contained-work-table";

/** One piece of contained work, costed at ten thousand micros per ordinal so sums come out in whole cents. */
function piece(ordinal: number, overrides: Partial<RunRow> = {}): RunRow {
  return {
    task_id: containedId(ordinal),
    parent_task_id: RUN_ACTIVE_ID,
    task_type: "render-shot",
    status: "completed",
    total_provider_cost_micros: ordinal * 10_000,
    unresolved_event_count: 0,
    total_billed_cost_micros: 0,
    unpriced_event_count: 0,
    event_count: (ordinal % 3) + 1,
    created_at: `2026-09-01T14:${String(ordinal % 60).padStart(2, "0")}:00Z`,
    ...overrides,
  };
}

const THIRTY = Array.from({ length: 30 }, (_, index) => piece(index + 1));
const EVENTS_OVER_THIRTY = THIRTY.reduce((sum, row) => sum + row.event_count, 0);
// 10,000 × (1 + … + 30) = 4,650,000 micros; over the first 25 alone it is 3,250,000.
const COST_OVER_THIRTY = "$4.65";
const COST_OVER_THE_SHOWN_TWENTY_FIVE = "$3.25";

// The decision the CONTAINING run makes, handed in the way the run page hands
// it — no row in the table is asked about its own regime.
const UNDER_A_FIXED_PRICE_RUN: PriceApplicability = { meteringOnly: false, soldAtOnePrice: true };
const UNDER_AN_EVENT_PRICED_RUN: PriceApplicability = { meteringOnly: false, soldAtOnePrice: false };
const IN_A_WORKSPACE_THAT_DOES_NOT_BILL: PriceApplicability = {
  meteringOnly: true,
  soldAtOnePrice: false,
};

function renderTable(contained: readonly RunRow[], applicability = UNDER_A_FIXED_PRICE_RUN) {
  return renderWithProviders(
    <ContainedWorkTable contained={contained} currency="usd" applicability={applicability} />,
  );
}

function shownRows(): HTMLElement[] {
  return Array.from(document.querySelectorAll<HTMLElement>("tbody tr[data-contained-row]"));
}

function rollupRow(): HTMLElement {
  const row = document.querySelector<HTMLElement>("tfoot tr[data-rollup-row]");
  if (!row) throw new Error("no roll-up row");
  return row;
}

/**
 * The cells of a row as text, one entry per COLUMN: a footer cell spanning
 * three columns fills three entries, so the same index names the same column
 * in a body row and in the roll-up.
 */
function cellsOf(row: HTMLElement): string[] {
  return Array.from(row.querySelectorAll("td")).flatMap((cell) =>
    Array.from({ length: cell.colSpan }, () => cell.textContent ?? ""),
  );
}

/** The drawn reading in a row's column, whatever the row's cells span. */
function readingIn(row: HTMLElement, column: number): HTMLElement | null {
  let reached = 0;
  for (const cell of Array.from(row.querySelectorAll("td"))) {
    if (reached === column) return cell.querySelector<HTMLElement>("[data-reading]");
    reached += cell.colSpan;
  }
  return null;
}

const EVENTS = 3;
const SUPPLIER_COST = 4;
const CUSTOMER_PRICE = 5;

describe("ContainedWorkTable", () => {
  it(`renders at most ${CONTAINED_ROWS_SHOWN_INLINE} rows inline and folds the rest into the roll-up row, which says how many and offers to show them all`, async () => {
    renderTable(THIRTY);
    await screen.findByText("All contained work");
    expect(shownRows()).toHaveLength(CONTAINED_ROWS_SHOWN_INLINE);
    expect(rollupRow()).toHaveTextContent("30 pieces of contained work, 5 not shown");

    fireEvent.click(screen.getByRole("button", { name: "Show all 30" }));

    expect(shownRows()).toHaveLength(30);
    expect(screen.queryByRole("button", { name: /show all/i })).toBeNull();
    expect(rollupRow()).toHaveTextContent("30 pieces of contained work");
    expect(rollupRow()).not.toHaveTextContent("not shown");
  });

  it("totals every piece in the roll-up whether or not rows are folded — the assertion the bound exists to protect", async () => {
    renderTable(THIRTY);
    await screen.findByText("All contained work");
    const folded = cellsOf(rollupRow());

    fireEvent.click(screen.getByRole("button", { name: "Show all 30" }));
    const unfolded = cellsOf(rollupRow());

    // The label cell changes ("5 not shown" goes); the totals do not.
    expect(unfolded.slice(EVENTS)).toEqual(folded.slice(EVENTS));
    expect(folded[EVENTS]).toBe(formatEventCount(EVENTS_OVER_THIRTY));
    expect(folded[SUPPLIER_COST]).toBe(COST_OVER_THIRTY);
    // The discriminating half: a roll-up over only the visible rows would
    // answer a different number, and this is that number.
    expect(folded[SUPPLIER_COST]).not.toBe(COST_OVER_THE_SHOWN_TWENTY_FIVE);
  });

  it("renders an expired piece of contained work as expired, never as a failure", async () => {
    const rows = [
      piece(1),
      piece(2, { status: "expired" }),
      piece(3, { status: "failed", outcome_reason: "timeout" }),
    ];
    renderTable(rows);
    await screen.findByText("All contained work");
    const expired = document.querySelector<HTMLElement>('tbody tr[data-status="expired"] [data-status]');
    const failed = document.querySelector<HTMLElement>('tbody tr[data-status="failed"] [data-status]');
    if (!expired || !failed) throw new Error("both rows should carry a drawn state");
    expect(expired).toHaveTextContent("Expired");
    expect(expired.className).not.toMatch(DRAWN_AS_FAILURE);
    expect(failed).toHaveTextContent("Failed");
    expect(failed.className).toMatch(DRAWN_AS_FAILURE);
  });

  it("says a customer price is not applicable to every piece under a run sold at one agreed price — and to the roll-up — with the reason", async () => {
    renderTable(THIRTY.slice(0, 3));
    await screen.findByText("All contained work");
    for (const row of [...shownRows(), rollupRow()]) {
      const reading = readingIn(row, CUSTOMER_PRICE);
      expect(reading).toHaveAttribute("data-reading", "not_applicable");
      expect(reading).toHaveTextContent("Not applicable");
      expect(reading).toHaveTextContent("Priced at the task");
      expect(reading).not.toHaveTextContent("$");
    }
  });

  it("says Unknown for a piece whose cost nobody knows, beside a sibling that really cost nothing", async () => {
    const rows = [
      piece(1, { total_provider_cost_micros: 0, unresolved_event_count: 1 }),
      piece(2, { total_provider_cost_micros: 0, event_count: 0 }),
      piece(3),
    ];
    renderTable(rows);
    await screen.findByText("All contained work");
    const [unknown, realZero] = shownRows().map((row) => readingIn(row, SUPPLIER_COST));
    expect(unknown).toHaveAttribute("data-reading", "unknown");
    expect(unknown).toHaveTextContent("Unknown");
    expect(realZero).toHaveAttribute("data-reading", "figure");
    expect(realZero).toHaveTextContent("$0.00");
    // And the roll-up, with one piece uncosted, is a floor rather than a figure.
    const rollup = cellsOf(rollupRow());
    expect(rollup[SUPPLIER_COST]).toBe("at least $0.03");
  });

  it("prices contained work under an event-priced run as figures, and as not applicable for a workspace that does not bill", async () => {
    const rows = [
      piece(1, { total_billed_cost_micros: 200_000 }),
      piece(2, { total_billed_cost_micros: 150_000 }),
    ];
    const bills = renderTable(rows, UNDER_AN_EVENT_PRICED_RUN);
    await screen.findByText("All contained work");
    expect(cellsOf(rollupRow())[CUSTOMER_PRICE]).toBe("$0.35");
    bills.unmount();

    renderTable(rows, IN_A_WORKSPACE_THAT_DOES_NOT_BILL);
    await screen.findByText("All contained work");
    const reading = readingIn(rollupRow(), CUSTOMER_PRICE);
    expect(reading).toHaveAttribute("data-reading", "not_applicable");
    expect(reading).toHaveTextContent("Metering only");
    expect(reading).toHaveAttribute(
      "title",
      expect.stringMatching(/does not bill customers through UBB/),
    );
  });

  it("says so when nothing is contained, rather than drawing an empty table", async () => {
    renderTable([]);
    expect(await screen.findByText(/Nothing is contained in this run/)).toBeInTheDocument();
    expect(screen.queryByRole("table")).toBeNull();
  });
});
