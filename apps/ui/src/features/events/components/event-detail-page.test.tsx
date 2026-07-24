import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import type { ReactElement } from "react";
import { describe, expect, it, vi } from "vitest";

import {
  CUSTOMER_A_ID,
  EVENT_RICH_ID,
  EVENT_TIPPING_ID,
} from "../api/mock-data";
import { EventDetailPage } from "./event-detail-page";

function renderPage(props: { eventId: string; customerId?: string }) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  const ui: ReactElement = (
    <QueryClientProvider client={queryClient}>
      <EventDetailPage
        eventId={props.eventId}
        customerId={props.customerId}
        onBack={vi.fn()}
      />
    </QueryClientProvider>
  );
  return render(ui);
}

describe("EventDetailPage", () => {
  it("renders the full receipt for the rich mock event", async () => {
    renderPage({ eventId: EVENT_RICH_ID, customerId: CUSTOMER_A_ID });

    expect(await screen.findByText("Event receipt")).toBeInTheDocument();
    // Identity in mono with copy affordances.
    expect(screen.getByText("req_search_reindex_0042")).toBeInTheDocument();
    // Money from the fixture: billed $0.19 (187,500 micros).
    expect(screen.getByText("$0.19")).toBeInTheDocument();
    // Usage metrics (the metric also appears in the provenance receipt).
    expect(screen.getAllByText("input_tokens").length).toBeGreaterThan(0);
    expect(screen.getByText("4,200")).toBeInTheDocument();
    // The provenance receipt renders structured, not as raw JSON.
    expect(screen.getByText("Pricing provenance")).toBeInTheDocument();
    expect(screen.getByText("llm-prices-2026")).toBeInTheDocument();
  });

  it("renders the stop context timeline for a tipping event", async () => {
    renderPage({ eventId: EVENT_TIPPING_ID, customerId: CUSTOMER_A_ID });

    expect(await screen.findByText("Stop context")).toBeInTheDocument();
    expect(screen.getByText("Customer balance floor")).toBeInTheDocument();
    expect(screen.getByText("Tipping event")).toBeInTheDocument();
  });

  it("hides the refund action when arriving without a customer id", async () => {
    renderPage({ eventId: EVENT_RICH_ID });

    expect(await screen.findByText("Event receipt")).toBeInTheDocument();
    expect(screen.queryByText("Refund this charge")).not.toBeInTheDocument();
  });

  it("closes the attributed task and shows the returned totals", async () => {
    renderPage({ eventId: EVENT_RICH_ID, customerId: CUSTOMER_A_ID });

    const closeButton = await screen.findByRole("button", {
      name: "Close task",
    });
    fireEvent.click(closeButton);

    // Confirm inside the dialog.
    const confirm = await screen.findByRole("button", { name: "Yes, close it" });
    fireEvent.click(confirm);

    // The returned status + rolled-up totals render inline.
    expect(
      await screen.findByText(/Task closed — Completed/),
    ).toBeInTheDocument();
    expect(screen.getByText("Total billed")).toBeInTheDocument();
    expect(screen.getByText("Total provider cost")).toBeInTheDocument();
  });

  it("shows the refund dialog with replay-safe copy and issues the refund", async () => {
    renderPage({ eventId: EVENT_TIPPING_ID, customerId: CUSTOMER_A_ID });

    const refundButton = await screen.findByRole("button", {
      name: "Refund this charge",
    });
    fireEvent.click(refundButton);

    expect(await screen.findByText("Refund this charge?")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /^Refund \$/ }));

    // Success feedback: the action collapses into a disabled "Refunded" state.
    expect(
      await screen.findByRole("button", { name: "Refunded" }),
    ).toBeInTheDocument();
  });
});
