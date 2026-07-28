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
  it("renders the rate-card books", async () => {
    renderPage();
    // Books with name + mono key, type badges, and the default badge.
    expect(await screen.findByText("OpenAI provider costs")).toBeInTheDocument();
    expect(screen.getByText("openai-cogs")).toBeInTheDocument();
    expect(screen.getByText("Standard price list")).toBeInTheDocument();
    expect(screen.getAllByText("Cost card").length).toBeGreaterThanOrEqual(2);
    expect(screen.getAllByText("Default").length).toBeGreaterThanOrEqual(1);
    // The resolution explainer is present in plain language.
    expect(screen.getByText("How pricing resolves")).toBeInTheDocument();
  });

  it("filters books by card type via the tabs", async () => {
    renderPage();
    expect(await screen.findByText("OpenAI provider costs")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: "Price cards" }));
    await waitFor(() =>
      expect(screen.queryByText("OpenAI provider costs")).not.toBeInTheDocument(),
    );
    expect(await screen.findByText("Standard price list")).toBeInTheDocument();
    expect(screen.getByText("Enterprise 2026 negotiated")).toBeInTheDocument();
  });

  it("navigates to a book when its row is clicked", async () => {
    const opened: string[] = [];
    renderPage((bookId) => opened.push(bookId));
    fireEvent.click(await screen.findByText("OpenAI provider costs"));
    expect(opened).toEqual(["0b1e6a4e-9c1d-4f2a-8f3b-1a2b3c4d5e01"]);
  });
});
