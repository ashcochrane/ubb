import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { BookDetailPage } from "./book-detail-page";

const OPENAI_COST_BOOK = "0b1e6a4e-9c1d-4f2a-8f3b-1a2b3c4d5e01";
const EMPTY_PRICE_BOOK = "0b1e6a4e-9c1d-4f2a-8f3b-1a2b3c4d5e04";

const onShowAuditTrail = vi.fn();

function renderPage(bookId: string) {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={client}>
      <BookDetailPage bookId={bookId} onShowAuditTrail={onShowAuditTrail} />
    </QueryClientProvider>,
  );
}

describe("BookDetailPage", () => {
  it("renders the book header and only its active rates by default", async () => {
    renderPage(OPENAI_COST_BOOK);
    expect(await screen.findByText("OpenAI provider costs")).toBeInTheDocument();
    expect(screen.getByText("v3")).toBeInTheDocument();
    expect(screen.getByText("Cost card")).toBeInTheDocument();
    // Active rates with formatted prices.
    expect(await screen.findByText("gpt4o_input_tokens")).toBeInTheDocument();
    expect(screen.getByText("$2.5 / 1M")).toBeInTheDocument();
    expect(screen.getByText("image_generation")).toBeInTheDocument();
    expect(screen.getByText("Flat")).toBeInTheDocument();
    // The superseded $5/1M version is history — hidden in the default view.
    expect(screen.queryByText("$5 / 1M")).not.toBeInTheDocument();
    // Audit-trail affordance fires the injected navigation callback (the
    // route file wires it to /settings/audit filtered to this book).
    fireEvent.click(
      screen.getByRole("button", { name: "Who changed this book?" }),
    );
    expect(onShowAuditTrail).toHaveBeenCalled();
  });

  it("shows an empty state for a book without rates", async () => {
    renderPage(EMPTY_PRICE_BOOK);
    expect(await screen.findByText("Enterprise 2026 negotiated")).toBeInTheDocument();
    expect(await screen.findByText("No rates yet")).toBeInTheDocument();
  });

  it("publishes new prices for edited rates and bumps the version", async () => {
    renderPage(OPENAI_COST_BOOK);
    expect(await screen.findByText("v3")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Publish new prices" }));

    // The dialog lists the active rates with editable values.
    const rateInput = await screen.findByLabelText("Rate for gpt4o_input_tokens (USD)");
    expect(await screen.findByText(/0 of 3 rates will be repriced/)).toBeInTheDocument();
    fireEvent.change(rateInput, { target: { value: "3" } });
    expect(await screen.findByText(/1 of 3 rates will be repriced/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Publish v4" }));
    // Mock supersedes the matched rate and bumps the book; header refetches.
    expect(await screen.findByText("v4")).toBeInTheDocument();
    expect(await screen.findByText("$3 / 1M")).toBeInTheDocument();
  });
});
