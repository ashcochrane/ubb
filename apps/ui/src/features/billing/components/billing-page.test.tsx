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
  it("renders revenue, the seat-default pool, and usage invoices from mock data", async () => {
    renderPage();

    // Section headings.
    //
    // ⚠ **BY ROLE, NOT BY TEXT, BECAUSE "Revenue" NOW NAMES TWO THINGS ON
    // THIS PAGE (#501).** The section is titled Revenue and — since the
    // one economic query answers revenue from one definition — so is the
    // first tile inside it, which used to be "Billed". A page-wide
    // `findByText("Revenue")` therefore matches ONE node until the query
    // resolves and TWO afterwards, and `findBy*` throws on multiple matches:
    // the assertion would pass or fail purely on whether the fixture landed
    // before the first poll. `apps/ui/CLAUDE.md` names this hazard — two
    // concepts sharing a word — and its remedy is to scope the query, which
    // for a heading is to ask for the heading.
    expect(
      await screen.findByRole("heading", { name: "Revenue" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Customer spend pool default")).toBeInTheDocument();
    // The default is the seats' alone, and the card says so in words (slice 6 §4).
    expect(screen.getByText(/It reaches seats only: a business with no pool of its own has none/)).toBeInTheDocument();
    expect(screen.getByText("Customer usage invoices")).toBeInTheDocument();
    expect(screen.getByText("Manual ledger adjustments")).toBeInTheDocument();

    // Revenue tiles resolve ("Provider cost"/"Markup" appear as tile + legend).
    expect((await screen.findAllByText("Provider cost")).length).toBeGreaterThan(0);
    expect(screen.getAllByText("Markup").length).toBeGreaterThan(0);

    // The pool form prefilled from GET (cap 2,500 USD → "2500").
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

  // ⚠ **THE BILLED FIGURE INCLUDES WHAT TENANTS SUPPLIED, AND ONE OF THE TWO
  // VIEWS SPREADS IT (#508; slice 7 §5).** This window adds three revenue
  // sources, so it has no single source reference and no single recognition
  // method to show — what it owes is the view it was drawn under, which the one
  // economic query states on every answer and which this console threw away
  // until now.
  it("says which revenue view the window was drawn under", async () => {
    renderPage();

    const note = await screen.findByText(/Revenue stated as/);
    expect(note.getAttribute("data-revenue-basis")).toBe("recorded");
    expect(note).toHaveTextContent("Nothing is divided");
  });

  // #330: the window's supplier total is a FLOOR whenever it holds events UBB
  // could not cost, and the markup beside it is then a ceiling — billed minus
  // the RESOLVED cost, which the contract states on the measure itself since
  // #501 (`EconomicMeasureOut.status` = `incomplete`, where the figure "is a
  // bound rather than a total"; it used to be `get_revenue_analytics`, one of
  // the five definitions that collapsed). The mock puts uncosted events on today, so every
  // default window is partial and both tiles have to say which way they are
  // wrong.
  it("renders a partial window's cost as a floor and its markup as a ceiling", async () => {
    renderPage();

    // By role, for the reason the first case gives: two nodes say "Revenue".
    expect(
      await screen.findByRole("heading", { name: "Revenue" }),
    ).toBeInTheDocument();
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
