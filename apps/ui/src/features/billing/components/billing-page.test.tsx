import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { BillingPage } from "./billing-page";

function renderPage(search: { start_date?: string; end_date?: string } = {}) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <BillingPage search={search} onSearchChange={vi.fn()} />
    </QueryClientProvider>,
  );
}

describe("BillingPage", () => {
  it("renders revenue, budget, and usage invoices from mock data", async () => {
    renderPage();

    // Section headings.
    expect(await screen.findByText("Revenue")).toBeInTheDocument();
    expect(screen.getByText("Workspace budget")).toBeInTheDocument();
    expect(screen.getByText("Customer usage invoices")).toBeInTheDocument();
    expect(screen.getByText("Manual ledger adjustments")).toBeInTheDocument();

    // Revenue tiles resolve ("Provider cost"/"Markup" appear as tile + legend).
    expect((await screen.findAllByText("Provider cost")).length).toBeGreaterThan(0);
    expect(screen.getAllByText("Markup").length).toBeGreaterThan(0);

    // Budget form prefilled from GET (cap 2,500 USD → "2500").
    const capInput = await screen.findByLabelText(/Monthly cap/);
    expect(capInput).toHaveValue(2500);

    // Usage invoice rows with status labels and mono Stripe id.
    expect(await screen.findByText("in_1Pf8kQ2eZvKYlo2C9yTasMx1")).toBeInTheDocument();
    expect(screen.getAllByText("acme-support-bot").length).toBeGreaterThan(0);
    expect(screen.getByText("Failed permanently")).toBeInTheDocument();
    expect(screen.getByText("Skipped")).toBeInTheDocument();

    // Prepaid mock tenant: the postpaid-only section stays hidden.
    expect(screen.queryByText("Postpaid invoicing")).not.toBeInTheDocument();
  });

  // #330: the window's supplier total is a FLOOR whenever it holds events UBB
  // could not cost, and the markup beside it is then a ceiling — billed minus
  // the RESOLVED cost, which is the backend's own statement about that figure
  // (`get_revenue_analytics`). The mock puts uncosted events on today, so every
  // default window is partial and both tiles have to say which way they are
  // wrong.
  it("renders a partial window's cost as a floor and its markup as a ceiling", async () => {
    renderPage();

    expect(await screen.findByText("Revenue")).toBeInTheDocument();
    expect(await screen.findByText(/^at least \$/)).toBeInTheDocument();
    expect(screen.getByText(/^at most \$/)).toBeInTheDocument();
    // The note beside them says how many events are missing and which way the
    // total is wrong — a marker alone would leave the reader to guess.
    expect(screen.getByText(/3 events have a supplier cost/)).toBeInTheDocument();
    // Billed cost is NOT NULL at the column and whole by construction, so it is
    // rendered as the figure it is.
    expect(screen.getAllByText(/^\$[\d,]+\.\d\d$/).length).toBeGreaterThan(0);
  });

  it("shows the empty state when the period filter matches nothing", async () => {
    renderPage();

    await screen.findByText("in_1Pf8kQ2eZvKYlo2C9yTasMx1");
    fireEvent.change(screen.getByLabelText("Filter by billing period"), {
      target: { value: "2025-01" },
    });

    expect(
      await screen.findByText("No usage invoices for this period"),
    ).toBeInTheDocument();

    // The empty state's CTA restores the unfiltered list.
    fireEvent.click(screen.getByRole("button", { name: "Clear filter" }));
    expect(await screen.findByText("in_1Pf8kQ2eZvKYlo2C9yTasMx1")).toBeInTheDocument();
  });

  it("credits a wallet through the confirm dialog and shows the new balance", async () => {
    renderPage();

    const creditHeading = await screen.findByText("Credit a wallet");
    const creditForm = creditHeading.closest("form");
    expect(creditForm).not.toBeNull();
    if (!creditForm) return;

    fireEvent.change(within(creditForm).getByLabelText("Customer external ID"), {
      target: { value: "acme-support-bot" },
    });
    fireEvent.change(within(creditForm).getByLabelText(/^Amount/), {
      target: { value: "25" },
    });
    fireEvent.change(within(creditForm).getByLabelText("Reference"), {
      target: { value: "TICKET-1042" },
    });
    fireEvent.change(within(creditForm).getByLabelText("Source"), {
      target: { value: "support_goodwill" },
    });

    fireEvent.click(within(creditForm).getByRole("button", { name: "Credit…" }));

    // Money moves only after explicit confirmation.
    const dialogTitle = await screen.findByText("Credit this wallet?");
    expect(dialogTitle).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Credit wallet" }));

    // Mock wallet started at $182.50; a $25.00 credit lands at $207.50.
    await waitFor(() =>
      expect(within(creditForm).getByText(/balance is now/)).toBeInTheDocument(),
    );
    expect(within(creditForm).getByText("$207.50")).toBeInTheDocument();

    // Success resets the form for the next adjustment.
    expect(within(creditForm).getByLabelText("Customer external ID")).toHaveValue("");
  });
});
