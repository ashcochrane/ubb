import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { PricingPage } from "./pricing-page";

function renderPage(onOpenBook: (bookId: string) => void = () => {}) {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={client}>
      <PricingPage onOpenBook={onOpenBook} />
    </QueryClientProvider>,
  );
}

describe("PricingPage", () => {
  it("opens on the pricing books, which are what this tenant charges", async () => {
    renderPage();

    expect(await screen.findByText("Standard price list")).toBeInTheDocument();
    expect(screen.getByText("standard-price")).toBeInTheDocument();
    expect(screen.getByText("Enterprise 2026 negotiated")).toBeInTheDocument();
    expect(screen.getAllByText("Default").length).toBeGreaterThanOrEqual(1);
    // The resolution explainer is present in plain language.
    expect(screen.getByText("How pricing resolves")).toBeInTheDocument();
  });

  it("shows the cost books on their own tab, with the columns they have", async () => {
    // ⚠ THE DISCRIMINATING ASSERTION IS THE SUPPLIER COLUMN (#368). Two lists
    // that merely held different rows would be satisfied by one table filtered
    // two ways — which is what this screen used to be. A cost book names the
    // supplier it records and the currency that supplier bills in, and a
    // pricing book has no such columns to show, so the two tabs render
    // different SHAPES and that is what the split bought.
    renderPage();
    expect(await screen.findByText("Standard price list")).toBeInTheDocument();
    expect(screen.queryByText("Supplier")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: "Cost books" }));

    expect(await screen.findByText("OpenAI provider costs")).toBeInTheDocument();
    expect(screen.getByText("Anthropic provider costs")).toBeInTheDocument();
    expect(screen.getByText("Supplier")).toBeInTheDocument();
    expect(screen.getByText("openai")).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.queryByText("Standard price list")).not.toBeInTheDocument(),
    );
  });

  it("navigates to a book when its row is clicked", async () => {
    const opened: string[] = [];
    renderPage((bookId) => opened.push(bookId));

    fireEvent.click(await screen.findByText("Standard price list"));

    expect(opened).toEqual(["0b1e6a4e-9c1d-4f2a-8f3b-1a2b3c4d5e03"]);
  });
});
