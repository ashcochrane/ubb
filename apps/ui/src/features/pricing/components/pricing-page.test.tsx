import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import { resetPricingMockState } from "../api/mock";
import { PricingPage } from "./pricing-page";

// ⚠ THE MOCK'S STATE IS THIS FILE'S SUBJECT, so it is put back between
// cases. Declaring, publishing and discarding all move module-level state
// and vitest isolates modules per FILE rather than per test — without this,
// "discard leaves the book unchanged" would run against a book an earlier
// case had already changed, and would pass or fail on the order the file
// happens to be written in.
beforeEach(resetPricingMockState);

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
    expect(screen.getByText("How a price is resolved")).toBeInTheDocument();
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

/**
 * The explainer, which is the screen a tenant reads to learn what decides their
 * customers' prices — so a wrong one is worse than none.
 *
 * ⚠ **THE OLD ONE WAS FALSE FOR ANY TENANT WITH RULES.** It drew *base cost →
 * markup → final charge*: three steps with an arrow between them, which the
 * resolver does not do. Markup is a rung, reached only where no rule matched;
 * a tenant reading the pipeline would expect their negotiated $4 per million to
 * come out at $5.12 after a declared 28%, and it comes out at $4. These
 * assertions are on the claims a tenant would act on, not on the wording.
 */
describe("how a price is resolved", () => {
  it("shows four rungs, most specific first", async () => {
    renderPage();
    expect(await screen.findByText("How a price is resolved")).toBeInTheDocument();

    const ladder = within(screen.getByRole("list", { name: "The pricing ladder" }));
    const rungs = ladder.getAllByRole("listitem").map((item) => item.textContent ?? "");

    expect(rungs).toHaveLength(4);
    // Rung 1 is the customer's own rule for the exact usage; rung 3 is their
    // blanket one. Specificity outranks source, so the SELECTED BOOK's exact
    // match sits between them — which is the whole ruling, and the ordering a
    // reader would otherwise assume backwards.
    expect(rungs[0]).toContain("own rule for this exact usage");
    expect(rungs[1]).toContain("selected book’s rule for this exact usage");
    expect(rungs[2]).toContain("blanket rule");
    expect(rungs[3]).toContain("selected book’s default rule");
  });

  it("says specificity decides before the book does", async () => {
    renderPage();
    expect(await screen.findByText("How a price is resolved")).toBeInTheDocument();

    expect(
      screen.getByText(/every rule in all of them competes in one ranking/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/which book the rule came from is only the tie-break/i),
    ).toBeInTheDocument();
  });

  it("says there is no fallthrough between books", async () => {
    renderPage();
    expect(await screen.findByText("How a price is resolved")).toBeInTheDocument();

    expect(
      screen.getByText(/There is no fallthrough between books/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/does not hand the question to the next book/i),
    ).toBeInTheDocument();
  });

  // ⚠ THE ASSERTION THAT WOULD HAVE CAUGHT THE OLD SCREEN. It is on the CLAIM
  // rather than on the absence of an arrow: a redrawn pipeline with different
  // punctuation would slip past a test that only looked for "→".
  it("presents markup as a rung and denies that it multiplies a rule's price", async () => {
    renderPage();
    expect(await screen.findByText("How a price is resolved")).toBeInTheDocument();

    expect(
      screen.getByText(/Your markup is a rung, not a multiplier/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/never applied on top of a rule’s price/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/a rule that says \$4 charges \$4/i)).toBeInTheDocument();
  });

  it("says an undeclared markup leaves the price unknown, never zero", async () => {
    renderPage();
    expect(await screen.findByText("How a price is resolved")).toBeInTheDocument();

    expect(
      screen.getByText(/nobody has said what to charge, so no amount is billed/i),
    ).toBeInTheDocument();
  });
});

describe("the tenant's default markup rung", () => {
  it("shows what has been declared, on the page the ladder is on", async () => {
    renderPage();

    expect(await screen.findByText("Your default markup")).toBeInTheDocument();
    expect(await screen.findByText("28%")).toBeInTheDocument();
    expect(screen.getByText("Declared")).toBeInTheDocument();
  });

  // ⚠ WITHDRAWING IS NOT DECLARING ZERO, and the card has to say so in the one
  // state where a reader would otherwise assume it. `0%` for a workspace that
  // has decided nothing would tell them they had chosen to charge their
  // customers exactly what their calls cost.
  it("says an absent declaration is not a zero", async () => {
    renderPage();
    expect(await screen.findByText("28%")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Withdraw" }));

    // ⚠ THE CONFIRMATION IS WHERE THE DIFFERENCE IS SPELT OUT, because this is
    // the moment a tenant would otherwise assume withdrawal means zero.
    const confirm = within(await screen.findByRole("dialog"));
    expect(confirm.getByText(/NOT the same as declaring 0%/)).toBeInTheDocument();
    expect(
      confirm.getByText(/will resolve to unknown — no amount billed/i),
    ).toBeInTheDocument();
    fireEvent.click(confirm.getByRole("button", { name: "Withdraw" }));

    expect(await screen.findByText("Nothing declared")).toBeInTheDocument();
    expect(screen.queryByText("0%")).not.toBeInTheDocument();
    expect(
      screen.getByText(/which is not the same as declaring zero/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/resolves to/i)).toBeInTheDocument();
  });
});

/**
 * Declaring a book — the first half of the ticket's second acceptance
 * criterion, and the act every other one is downstream of.
 *
 * ⚠ **THE TWO KINDS TAKE TWO BODIES, WHICH IS WHY THE CHOICE IS A ROUTE AND
 * NOT A FIELD (#368).** A cost book names the supplier it records and the
 * currency that supplier bills in; a Pricing Book names neither. The
 * discriminating assertion is therefore that the supplier field is OFFERED for
 * one and absent for the other — a dialog that merely rendered would pass
 * whichever body it happened to send.
 */
describe("declaring a book", () => {
  it("declares a Pricing Book, and it appears in the list", async () => {
    renderPage();
    expect(await screen.findByText("Standard price list")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "New book" }));
    const dialog = within(await screen.findByRole("dialog"));

    fireEvent.click(dialog.getByRole("button", { name: /Pricing book/ }));
    // A Pricing Book has no supplier to name, so the field is not there to fill.
    expect(dialog.queryByLabelText(/^Supplier/)).not.toBeInTheDocument();

    fireEvent.change(dialog.getByLabelText("Key"), {
      target: { value: "partner-2027" },
    });
    fireEvent.change(dialog.getByLabelText("Name (optional)"), {
      target: { value: "Partner rates 2027" },
    });
    fireEvent.click(dialog.getByRole("button", { name: "Declare book" }));

    expect(await screen.findByText("Partner rates 2027")).toBeInTheDocument();
    expect(screen.getByText("partner-2027")).toBeInTheDocument();
  });

  it("declares a cost book, which DOES name a supplier", async () => {
    renderPage();
    expect(await screen.findByText("Standard price list")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "New book" }));
    const dialog = within(await screen.findByRole("dialog"));

    // The dialog opens on the cost half, which is the one with a supplier.
    fireEvent.change(dialog.getByLabelText("Key"), {
      target: { value: "mistral-cogs" },
    });
    fireEvent.change(dialog.getByLabelText(/^Supplier/), {
      target: { value: "mistral" },
    });
    fireEvent.click(dialog.getByRole("button", { name: "Declare book" }));

    fireEvent.click(await screen.findByRole("tab", { name: "Cost books" }));
    // Twice, and that is the row's shape rather than a duplicate: a book with
    // no name falls back to its key for the title and shows the key beneath it.
    expect(await screen.findAllByText("mistral-cogs")).toHaveLength(2);
    expect(screen.getByText("mistral")).toBeInTheDocument();
  });

  it("refuses a key the workspace already uses, and says so", async () => {
    renderPage();
    expect(await screen.findByText("Standard price list")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "New book" }));
    const dialog = within(await screen.findByRole("dialog"));
    fireEvent.change(dialog.getByLabelText("Key"), {
      target: { value: "openai-cogs" },
    });
    fireEvent.click(dialog.getByRole("button", { name: "Declare book" }));

    expect(await screen.findByText(/already exists/i)).toBeInTheDocument();
  });
});
