// The revenue window's three totals, folded from its days WITH their states
// (#510; slice 7 §19).
//
// ⚠ **THE FOLD IS THE SUBJECT.** Until this ticket the section SUMMED its day
// rows as numbers, each coalesced to zero first — so a window reaching back
// past the economic horizon counted its gone days as nothing and printed the
// days UBB still holds as though they were the whole window. The answer is
// composed from `@/lib/economic-scenarios` and served through the provider, so
// the fixture is one the mock does not author and the narrowing is the real
// one.

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import type { ReactElement } from "react";
import { describe, expect, it, vi } from "vitest";

import {
  knownMeasures,
  measuresOutsideRetentionHorizon,
  type EconomicMeasureScenario,
} from "@/lib/economic-scenarios";

import type { Economics } from "../api/types";
import { RevenueSection } from "./revenue-section";

const RANGE = { start_date: "2020-09-16", end_date: "2020-09-18" };

function day(date: string, measures: EconomicMeasureScenario[]): Economics["rows"][number] {
  return {
    bucket_start: `${date}T00:00:00+00:00`,
    grouping_field_value: [],
    grouping_field_value_status: [],
    measures,
  };
}

/** Two days UBB no longer holds, and one it does. */
const ANSWER: Economics = {
  period_start: RANGE.start_date,
  period_end: RANGE.end_date,
  group_by: [],
  bucket: "day",
  basis: "recorded",
  economic_data_available_from: "2020-09-18",
  measurement_data_available_from: "2026-06-01",
  rows: [
    day("2020-09-16", measuresOutsideRetentionHorizon("2020-09-18")),
    day("2020-09-17", measuresOutsideRetentionHorizon("2020-09-18")),
    day("2020-09-18", knownMeasures({ cost_micros: 4_000_000, revenue_micros: 9_000_000, events: 7 })),
  ],
  context: [],
};

vi.mock("../api/provider", () => ({
  billingFeatureApi: { getRevenueWindow: async () => ANSWER },
}));

function renderSection(ui: ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

/** A stat card by its label — the legend names the same series, so the label
 *  is looked up only among nodes inside a card. */
function card(label: string): HTMLElement {
  const node = screen
    .getAllByText(label)
    .map((match) => match.closest("[data-variant]"))
    .find((found) => found !== null);
  if (node === undefined || node === null) throw new Error(`no stat card labelled ${label}`);
  return node as HTMLElement;
}

describe("RevenueSection", () => {
  it("reads the window's totals as the state its gone days leave, never as the day it holds", async () => {
    renderSection(<RevenueSection range={RANGE} onRangeChange={vi.fn()} />);

    expect((await screen.findAllByText("Provider cost")).length).toBeGreaterThan(0);
    for (const label of ["Revenue", "Provider cost", "Gross margin"]) {
      expect(within(card(label)).getByText("Outside retention horizon")).toBeInTheDocument();
    }
    // The one day UBB holds is not the window: its figures appear nowhere as
    // a total, and no gone day became a zero.
    expect(screen.queryByText("$9.00")).not.toBeInTheDocument();
    expect(screen.queryByText("$4.00")).not.toBeInTheDocument();
    expect(screen.queryByText("$5.00")).not.toBeInTheDocument();
    expect(screen.queryByText("$0.00")).not.toBeInTheDocument();
    // And the section says where the records start.
    expect(screen.getByText(/UBB holds economic records from Sep 18, 2020/)).toBeInTheDocument();
  });
});
