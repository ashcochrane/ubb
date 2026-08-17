import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import type { ReactElement } from "react";
import { describe, expect, it, vi } from "vitest";

import {
  COSTING_STATUS_EXPLANATIONS,
  costingStatusLabel,
} from "@/lib/supplier-cost";

import { CUSTOMER_A_ID } from "../api/mock-data";
import type { EventsSearch } from "../lib/search";
import { EventsPage } from "./events-page";

function renderPage(search: EventsSearch) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  const ui: ReactElement = (
    <QueryClientProvider client={queryClient}>
      <EventsPage
        search={search}
        onSearchChange={vi.fn()}
        onOpenEvent={vi.fn()}
        onGoToCustomers={vi.fn()}
      />
    </QueryClientProvider>
  );
  return render(ui);
}

describe("EventsPage", () => {
  it("renders the ledger and analytics for a selected customer", async () => {
    renderPage({ customer_id: CUSTOMER_A_ID });

    // Analytics strip labels ("Billed"/"Provider cost" also head table columns).
    expect((await screen.findAllByText("Billed")).length).toBeGreaterThan(0);
    expect(screen.getAllByText("Provider cost").length).toBeGreaterThan(0);
    expect(screen.getByText("Markup margin")).toBeInTheDocument();

    // Ledger rows from the mock fixture set (multiple chat.completion rows).
    const rows = await screen.findAllByText("chat.completion");
    expect(rows.length).toBeGreaterThan(0);

    // Cursor pagination is a Load more footer, never page numbers.
    expect(
      await screen.findByRole("button", { name: "Load more" }),
    ).toBeInTheDocument();
  });

  it("shows the per-customer empty state when no customer is selected", async () => {
    renderPage({});
    expect(
      await screen.findByText("Pick a customer to see their ledger"),
    ).toBeInTheDocument();
    // The picker still renders so the user can act on the empty state.
    expect(
      await screen.findByLabelText("Select customer"),
    ).toBeInTheDocument();
  });

  it("shows the past-limit report when the past-limit filter is on", async () => {
    renderPage({ customer_id: CUSTOMER_A_ID, past_limit: true });

    expect(await screen.findByText("Past-limit report")).toBeInTheDocument();
    // The customer-floor episode from the fixture report.
    expect(
      (await screen.findAllByText("Customer balance floor")).length,
    ).toBeGreaterThan(0);
    expect(screen.getByText("Totals per limit")).toBeInTheDocument();
  });

  it("marks stopped events in the ledger", async () => {
    renderPage({ customer_id: CUSTOMER_A_ID, past_limit: true });
    const stopped = await screen.findAllByText("Stopped");
    expect(stopped.length).toBeGreaterThan(0);
  });

  // #330: the window holds one event whose supplier cost UBB never learned, so
  // the strip's total can only be higher and its markup only lower. Both say
  // so, and the note says how many events are behind it.
  it("says the window's supplier total is a floor, and its markup a ceiling", async () => {
    // An explicit July window: this fixture's story is July 2026, and the
    // page's own default is month-to-date, which selects none of it.
    renderPage({
      customer_id: CUSTOMER_A_ID,
      start_date: "2026-07-01",
      end_date: "2026-07-31",
    });

    expect(await screen.findByText(/^at least \$/)).toBeInTheDocument();
    expect(screen.getByText(/^at most \$/)).toBeInTheDocument();
    expect(screen.getByText(/1 event has a supplier cost/)).toBeInTheDocument();
  });

  // The ledger cell for that same event. A bare dash is the right rendering for
  // a value nobody asked about and the wrong one here: a supplier cost is
  // absent for two opposite reasons, and a column of identical dashes hides
  // which rows the tenant can act on. Zero is not an option either way.
  it("names an unlearned cost in the ledger instead of dashing or zeroing it", async () => {
    renderPage({ customer_id: CUSTOMER_A_ID });

    const cells = await screen.findAllByText(costingStatusLabel("unresolved"));
    expect(cells.length).toBeGreaterThan(0);
    expect(cells[0]).toHaveAttribute(
      "title",
      COSTING_STATUS_EXPLANATIONS.unresolved,
    );
  });
});
