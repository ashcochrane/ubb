// The ledger's one reader of a posting's KIND (#425).
//
// A component test rather than a page test, because the events mock's charge
// posting is June traffic and the ledger's first page is July's: a page test
// would have to click through the cursor to reach it, and what is under test
// is one cell's rule, not the paging. The rows are assembled here, as the
// list route serves them — `UsageEventOut` carries the kind and no receipt.

import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { knownCost, knownPrice } from "@/lib/economic-scenarios";

import type { UsageEventRow } from "../api/types";
import { usageEventKindLabel } from "../lib/kind";
import { LedgerTable } from "./ledger-table";

const METERED_ROW: UsageEventRow = {
  id: "2a7f4c19-6d83-4b05-9e12-8c5b3a0d7f61",
  kind: "metered_usage",
  effective_at: "2026-08-30T11:20:00Z",
  event_type: "chat.completion",
  provider: "openai",
  metadata: {},
  ...knownPrice(31_000),
  ...knownCost(12_000),
  stop_context: null,
};

/**
 * A charge posting as the list serves it: no Event Type and no provider,
 * because no caller reported it — its kind is the only thing that says what
 * it is, and the row carries nothing else that could.
 */
const CHARGE_ROW: UsageEventRow = {
  id: "9c3a5f71-2d86-4b04-8e19-5a7c1d0e2f95",
  kind: "task_charge",
  effective_at: "2026-08-30T11:31:00Z",
  event_type: "",
  provider: "",
  metadata: {},
  ...knownPrice(5_000_000),
  ...knownCost(0),
  stop_context: null,
};

describe("LedgerTable", () => {
  // A dash in the Event type column read as a row with something missing
  // from it. The catalogue's word for the kind is what the row is.
  it("names a charge posting by its kind, and a metered posting by its event type", () => {
    render(
      <LedgerTable rows={[METERED_ROW, CHARGE_ROW]} currency="usd" onOpen={vi.fn()} />,
    );

    const cell = screen.getByText(usageEventKindLabel("task_charge"));
    expect(cell).toHaveAttribute("data-kind", "task_charge");
    expect(screen.getByText("chat.completion")).toBeInTheDocument();
    expect(screen.queryByText(usageEventKindLabel("metered_usage"))).not.toBeInTheDocument();

    // The charge's amounts read as they are: the agreed price, and a settled
    // supplier cost of nothing.
    expect(screen.getByText("$5.00")).toBeInTheDocument();
    expect(screen.getByText("$0.0310")).toBeInTheDocument();
  });
});
