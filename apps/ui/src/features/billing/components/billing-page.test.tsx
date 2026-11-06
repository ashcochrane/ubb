import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { NOT_YET_COLLECTIBLE } from "@/lib/usage-invoice";

import { MOCK_CUSTOMER_UUIDS } from "../api/mock-data";
import { billingFeatureApi } from "../api/provider";
import { PLATFORM_CUSTOMER_UUID_MESSAGE } from "../lib/billing-forms";
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

    // Revenue tiles resolve ("Provider cost"/"Gross margin" appear as tile +
    // legend; the legend read "Markup" until #510, the word #501 retired).
    expect((await screen.findAllByText("Provider cost")).length).toBeGreaterThan(0);
    expect(screen.getAllByText("Gross margin").length).toBeGreaterThan(1);
    expect(screen.queryByText("Markup")).not.toBeInTheDocument();

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

  // #330: the window's supplier total is INCOMPLETE whenever it holds events
  // UBB could not cost, and so is the markup beside it — billed minus the
  // RESOLVED cost, which the contract states on the measure itself since #501
  // (`EconomicMeasureOut.status` = `incomplete`: the sum of the inputs that
  // resolved). Since #603 neither is a bound: a cost left out may be negative,
  // so neither tile says which way it is wrong, only that it is partial. The
  // mock puts uncosted events on today, so every default window is partial.
  it("renders a partial window's cost and its markup marked incomplete, never as a bound", async () => {
    renderPage();

    // By role, for the reason the first case gives: two nodes say "Revenue".
    expect(
      await screen.findByRole("heading", { name: "Revenue" }),
    ).toBeInTheDocument();
    // The cost tile and the markup tile, both marked.
    expect(
      (await screen.findAllByText(/^-?\$[\d,]+\.\d\d \(Incomplete\)$/)).length,
    ).toBeGreaterThanOrEqual(2);
    expect(screen.queryByText(/at least|at most/)).not.toBeInTheDocument();
    // The note beside them says how many events are missing — a mark alone
    // would leave the reader to wonder what is left out.
    expect(screen.getByText(/3 events have a supplier cost/)).toBeInTheDocument();
    // Every price in this fixture resolved, so the revenue reads `known` and is
    // drawn as the figure it is — while the margin beside it is incomplete,
    // from the cost side alone (§15).
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
    // F-13: what goes out is the platform Customer UUID, as typed.
    const credit = vi.spyOn(billingFeatureApi, "creditWallet");
    renderPage();

    const creditHeading = await screen.findByText("Credit a wallet");
    const creditForm = creditHeading.closest("form");
    expect(creditForm).not.toBeNull();
    if (!creditForm) return;

    fireEvent.change(within(creditForm).getByLabelText("Platform Customer UUID"), {
      target: { value: MOCK_CUSTOMER_UUIDS.acmeSupportBot },
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

    expect(credit).toHaveBeenCalledWith(
      expect.objectContaining({ customer_id: MOCK_CUSTOMER_UUIDS.acmeSupportBot }),
    );
    credit.mockRestore();

    // Success resets the form for the next adjustment.
    expect(within(creditForm).getByLabelText("Platform Customer UUID")).toHaveValue("");
  });

  // F-13 (PLAN §7 item 44): the ledger routes take the platform Customer UUID
  // and nothing else, so the forms say exactly that — and never call the
  // field a Customer external ID, which the route would answer 404 to.
  it("labels the customer on both ledger forms as the Platform Customer UUID, never an external ID", async () => {
    renderPage();

    for (const heading of ["Credit a wallet", "Debit a wallet"]) {
      const form = (await screen.findByText(heading)).closest("form");
      expect(form).not.toBeNull();
      if (!form) return;
      expect(within(form).getByLabelText("Platform Customer UUID")).toBeInTheDocument();
      expect(within(form).queryByLabelText(/external/i)).not.toBeInTheDocument();
      expect(form.textContent).not.toMatch(/external[ _]id/i);
    }
  });

  it("refuses a value that is not a UUID before anything is sent", async () => {
    const credit = vi.spyOn(billingFeatureApi, "creditWallet");
    renderPage();

    const creditForm = (await screen.findByText("Credit a wallet")).closest("form");
    expect(creditForm).not.toBeNull();
    if (!creditForm) return;

    // A tenant-side id — the thing the route no longer takes.
    fireEvent.change(within(creditForm).getByLabelText("Platform Customer UUID"), {
      target: { value: "acme-support-bot" },
    });
    fireEvent.change(within(creditForm).getByLabelText(/^Amount/), {
      target: { value: "25" },
    });
    fireEvent.change(within(creditForm).getByLabelText("Reference"), {
      target: { value: "TICKET-1043" },
    });
    fireEvent.change(within(creditForm).getByLabelText("Source"), {
      target: { value: "support_goodwill" },
    });
    fireEvent.click(within(creditForm).getByRole("button", { name: "Credit…" }));

    expect(
      await within(creditForm).findByText(PLATFORM_CUSTOMER_UUID_MESSAGE),
    ).toBeInTheDocument();
    expect(screen.queryByText("Credit this wallet?")).not.toBeInTheDocument();
    expect(credit).not.toHaveBeenCalled();
    credit.mockRestore();
  });

  // F-15: the sweep says where each pushed invoice stands as a receivable,
  // from the catalogue, and a not-yet-collectible one says that rather than
  // nothing.
  it("words each usage invoice's payment status, null as not yet collectible", async () => {
    renderPage();

    expect(await screen.findByText("in_1Pf8kQ2eZvKYlo2C9yTasMx1")).toBeInTheDocument();
    expect(screen.getAllByText("Paid").length).toBeGreaterThan(0);
    expect(screen.getByText("Uncollectible")).toBeInTheDocument();
    expect(screen.getAllByText(NOT_YET_COLLECTIBLE).length).toBeGreaterThan(0);
    expect(
      screen.getAllByRole("link", { name: "Open the hosted Stripe invoice" }).length,
    ).toBeGreaterThan(0);
  });
});
