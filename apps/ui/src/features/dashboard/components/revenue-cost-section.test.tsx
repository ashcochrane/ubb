// The overview's revenue-vs-cost chart says which revenue view it was drawn
// under (#548; W5 owner ruling 15).
//
// A day of supplied revenue is a whole figure under `recorded` and a slice of
// a period under `recognised`, so a line through it means nothing until the
// card says which. The mock answers `recorded`; the answer here is re-stated
// under each value and reaches the card through the real narrowing, so a card
// that wrote either word itself fails the other.

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { revenueBasisNote } from "@/lib/supplied-revenue";
import { REVENUE_BASIS_VALUES } from "@/lib/vocabulary";

import { mockDailyEconomics } from "../api/mock-data";
import { dashboardApi } from "../api/provider";
import { RevenueCostSection } from "./revenue-cost-section";

// The chart is lazy and draws nothing jsdom can read; this is about the card.
vi.mock("./revenue-cost-chart", () => ({
  default: () => <div data-testid="chart" />,
}));

const WINDOW = { start_date: "2026-07-01", end_date: "2026-07-23" };

describe("RevenueCostSection", () => {
  it.each(REVENUE_BASIS_VALUES)("states the %s basis its answer names", async (basis) => {
    vi.spyOn(dashboardApi, "getDailyEconomics").mockResolvedValueOnce({
      ...mockDailyEconomics(WINDOW),
      basis,
    });

    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { container } = render(
      <QueryClientProvider client={client}>
        <RevenueCostSection window={WINDOW} currency="usd" />
      </QueryClientProvider>,
    );

    expect(await screen.findByTestId("chart")).toBeInTheDocument();
    const notes = container.querySelectorAll("[data-revenue-basis]");
    expect(notes).toHaveLength(1);
    expect(notes[0]).toHaveAttribute("data-revenue-basis", basis);
    expect(notes[0]).toHaveTextContent(revenueBasisNote(basis));
  });
});
