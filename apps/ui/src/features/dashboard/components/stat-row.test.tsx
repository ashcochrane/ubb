// The overview's five figures, and the one of them that can fail on its own.
//
// ⚠ **"CUSTOMERS WITH USAGE" IS A SECOND PROMISE SINCE #501**, and that is the
// whole reason this file exists. The count used to be a FIELD on the same
// response as the three money figures beside it; counting customers is now the
// window grouped by the customer axis, which is its own request with its own
// failure. `data?.length ?? 0` turned that failure into a workspace with no
// customers — the silent zero the gross-margin card two along refuses in the
// same grid, arriving through a query state rather than through a measure.
//
// The provider is stubbed so the failure can be ASKED FOR: no fixture describes
// a broken request, and the mock cannot express one. Everything else the row
// renders comes from the mock's own totals, so a failure below can only be
// about the count.

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import type { ReactElement } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ABSENT_LABEL } from "@/lib/localisation";

import {
  mockCustomerEconomics,
  mockTenantEconomics,
} from "../api/mock-data";
import type { Economics, Window } from "../api/types";
import { StatRow } from "./stat-row";

const WINDOW: Window = { start_date: "2026-07-01", end_date: "2026-07-23" };

/** Swapped per case — the whole point is that this call can go either way. */
let answerCustomers: () => Promise<Economics> = async () =>
  mockCustomerEconomics(WINDOW);

vi.mock("../api/provider", () => ({
  dashboardApi: {
    // Only the two reads this row makes. A stub answering more would be a
    // second mock to keep true.
    getTenantEconomics: async () => mockTenantEconomics(WINDOW),
    getCustomerEconomics: () => answerCustomers(),
  },
}));

afterEach(() => {
  answerCustomers = async () => mockCustomerEconomics(WINDOW);
});

function renderRow(ui: ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

/** A card by its label, so a dash in one is never read as a dash in another. */
function card(label: string): HTMLElement {
  const element = screen.getByText(label).closest("[data-variant]");
  if (element === null) throw new Error(`no stat card labelled ${label}`);
  return element as HTMLElement;
}

describe("StatRow", () => {
  it("counts the customers the window's usage reached", async () => {
    renderRow(<StatRow window={WINDOW} currency="usd" />);

    // The mock roster's five customers, which is the row count of the same
    // question the economics table below asks — and the positive control
    // without which an absence proves nothing.
    expect(await screen.findByText("Customers with usage")).toBeInTheDocument();
    expect(within(card("Customers with usage")).getByText("5")).toBeInTheDocument();
  });

  it("renders a count that did not arrive as an absence, never as none", async () => {
    answerCustomers = async () => {
      throw new Error("the grouped question failed");
    };

    renderRow(<StatRow window={WINDOW} currency="usd" />);

    expect(await screen.findByText("Customers with usage")).toBeInTheDocument();
    const counted = card("Customers with usage");
    expect(within(counted).getByText(ABSENT_LABEL)).toBeInTheDocument();
    expect(
      within(counted).getByText("not available for this window"),
    ).toBeInTheDocument();
    // ⚠ AND NOT A ZERO, said as its own assertion. "0" and an absence are the
    // two answers this card can give, and the defect was that it gave the
    // wrong one — so the test that would have caught it has to refuse the
    // wrong one by name rather than merely find the right one.
    expect(within(counted).queryByText("0")).not.toBeInTheDocument();
  });

  it("still answers the four figures that did arrive", async () => {
    answerCustomers = async () => {
      throw new Error("the grouped question failed");
    };

    renderRow(<StatRow window={WINDOW} currency="usd" />);

    // The whole row does not fail with one refinement: revenue, the cost floor,
    // the margin ceiling and the event count all came back on the first
    // request and are worth more than the count that did not.
    expect(await screen.findByText("$852.90")).toBeInTheDocument();
    expect(screen.getByText("at least $563.60")).toBeInTheDocument();
    expect(screen.getByText("at most 33.9% margin")).toBeInTheDocument();
    expect(screen.getByText("93.6k")).toBeInTheDocument();
  });
});
