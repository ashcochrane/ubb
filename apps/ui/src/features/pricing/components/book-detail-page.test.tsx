import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { BookDetailPage } from "./book-detail-page";

const OPENAI_COST_BOOK = "0b1e6a4e-9c1d-4f2a-8f3b-1a2b3c4d5e01";
const STANDARD_PRICING_BOOK = "0b1e6a4e-9c1d-4f2a-8f3b-1a2b3c4d5e03";
const EMPTY_PRICING_BOOK = "0b1e6a4e-9c1d-4f2a-8f3b-1a2b3c4d5e04";

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
  it("renders a cost book's header and only its active rules by default", async () => {
    renderPage(OPENAI_COST_BOOK);
    expect(await screen.findByText("OpenAI provider costs")).toBeInTheDocument();
    expect(screen.getByText("v3")).toBeInTheDocument();
    expect(screen.getByText("Cost book")).toBeInTheDocument();
    // A cost book names the supplier it records and the currency that
    // supplier bills in (#368).
    expect(screen.getByText("Default for openai")).toBeInTheDocument();
    expect(screen.getByText("usd")).toBeInTheDocument();
    // Active rules with formatted prices.
    expect(await screen.findByText("gpt4o_input_tokens")).toBeInTheDocument();
    expect(screen.getByText("$2.5 / 1M")).toBeInTheDocument();
    expect(screen.getByText("image_generation")).toBeInTheDocument();
    // The arithmetic shape's wording, which followed the value's rename
    // (#366): a rule that charges once regardless of quantity is a
    // `fixed_component`, and the label catalogue already spelled it that way.
    expect(screen.getByText("Fixed component")).toBeInTheDocument();
    // The superseded $5/1M version is history — hidden in the default view.
    expect(screen.queryByText("$5 / 1M")).not.toBeInTheDocument();
    // Audit-trail affordance fires the injected navigation callback (the
    // route file wires it to /settings/audit filtered to this book).
    fireEvent.click(
      screen.getByRole("button", { name: "Who changed this book?" }),
    );
    expect(onShowAuditTrail).toHaveBeenCalled();
  });

  it("renders a pricing book's header, which names neither of those", async () => {
    // ⚠ THE DISCRIMINATING HALF (#368). A header that merely rendered would
    // pass the case above whether or not the two entities differ; what makes
    // the split visible is that the supplier and the currency are ABSENT here,
    // because a Pricing Book has no such columns.
    renderPage(STANDARD_PRICING_BOOK);

    expect(await screen.findByText("Standard price list")).toBeInTheDocument();
    expect(screen.getByText("Pricing book")).toBeInTheDocument();
    expect(screen.getByText("Default")).toBeInTheDocument();
    expect(screen.queryByText("Default for openai")).not.toBeInTheDocument();
    expect(screen.queryByText("usd")).not.toBeInTheDocument();
  });

  it("shows an empty state for a book without rules", async () => {
    renderPage(EMPTY_PRICING_BOOK);
    expect(await screen.findByText("Enterprise 2026 negotiated")).toBeInTheDocument();
    expect(await screen.findByText("No rates yet")).toBeInTheDocument();
  });

  it("offers no way to change what is in a book", async () => {
    /**
     * ⚠ THIS REPLACES `publishes new prices for edited rates and bumps the
     * version` (#368), and it is the honest successor rather than a deletion.
     *
     * That case drove the immediate reprice — a route that versioned a book
     * the instant it was called, with no diff a tenant could read first. It is
     * deleted with the last of the retired audit action names it wrote, so
     * every change to a book is a declared publish now and this console cannot
     * make one until #372 rebuilds the feature around books, rules and
     * publishes. The gap is asserted rather than left to be discovered: a page
     * that silently regrew a write affordance pointed at a route answering 405
     * would otherwise look fine.
     */
    renderPage(OPENAI_COST_BOOK);
    expect(await screen.findByText("v3")).toBeInTheDocument();

    expect(
      screen.queryByRole("button", { name: /publish/i }),
    ).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /add rate/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /retire/i })).not.toBeInTheDocument();
  });
});
