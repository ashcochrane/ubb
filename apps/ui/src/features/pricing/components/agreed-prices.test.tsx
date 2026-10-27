// A Pricing Book's agreed prices on its editor, and the Pricing Book opened to
// a workspace that meters without billing (#553 stories 13, 17, 24 and 25).
//
// Rendered through the pricing mock, whose standard book holds a repriced
// agreed price WITH its history and whose empty book holds none — the two
// states the list exists to tell apart. The posture is the mock workspace's,
// switched per case and put back after it.

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import {
  readMockTenantConfig,
  writeMockTenantConfig,
} from "@/hooks/use-tenant-config";

import { resetPricingMockState } from "../api/mock";
import { METERING_ONLY_PRICES } from "../lib/agreed-prices";
import { BookDetailPage } from "./book-detail-page";
import { CreateBookDialog } from "./create-book-dialog";

const OPENAI_COST_BOOK = "0b1e6a4e-9c1d-4f2a-8f3b-1a2b3c4d5e01";
const STANDARD_PRICING_BOOK = "0b1e6a4e-9c1d-4f2a-8f3b-1a2b3c4d5e03";
const EMPTY_PRICING_BOOK = "0b1e6a4e-9c1d-4f2a-8f3b-1a2b3c4d5e04";

const ORIGINAL_CONFIG = readMockTenantConfig();

beforeEach(resetPricingMockState);
afterEach(() => writeMockTenantConfig(ORIGINAL_CONFIG));

function meteringOnly() {
  writeMockTenantConfig({
    ...ORIGINAL_CONFIG,
    billing_mode: "external",
    products: ["metering"],
  });
}

function renderWithClient(ui: React.ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

function agreedPrices(): HTMLElement {
  return screen.getByRole("heading", { name: "Agreed prices" }).parentElement
    ?.parentElement as HTMLElement;
}

describe("a Pricing Book's agreed prices", () => {
  it("lists what a delivered run of each kind of work sells for, to the micro", async () => {
    renderWithClient(<BookDetailPage bookId={STANDARD_PRICING_BOOK} />);
    await screen.findByRole("heading", { name: "Agreed prices" });

    const section = within(agreedPrices());
    expect(await section.findByText("video-render")).toBeInTheDocument();
    expect(section.getByText("$5.00")).toBeInTheDocument();
    expect(section.getByText("Active")).toBeInTheDocument();
    // The line the reprice closed is history, hidden by default.
    expect(section.queryByText("$4.50")).not.toBeInTheDocument();
  });

  it("shows the line a reprice closed, with its end date, under history", async () => {
    renderWithClient(<BookDetailPage bookId={STANDARD_PRICING_BOOK} />);
    await screen.findByRole("heading", { name: "Agreed prices" });

    fireEvent.click(within(agreedPrices()).getByRole("switch", { name: "Include agreed-price history" }));

    const section = within(agreedPrices());
    expect(await section.findByText("$4.50")).toBeInTheDocument();
    expect(section.getByText("$5.00")).toBeInTheDocument();
  });

  it("says a book holds no agreed price rather than drawing an empty table", async () => {
    renderWithClient(<BookDetailPage bookId={EMPTY_PRICING_BOOK} />);
    await screen.findByRole("heading", { name: "Agreed prices" });

    expect(await within(agreedPrices()).findByText("No agreed prices")).toBeInTheDocument();
  });

  it("is not part of a cost book, which holds what a supplier charged", async () => {
    renderWithClient(<BookDetailPage bookId={OPENAI_COST_BOOK} />);
    expect(await screen.findByText("OpenAI provider costs")).toBeInTheDocument();

    expect(screen.queryByRole("heading", { name: "Agreed prices" })).not.toBeInTheDocument();
  });
});

describe("a Pricing Book in a workspace that meters without billing", () => {
  it("says the prices are recorded for its own reporting, and what enabling billing would change", async () => {
    meteringOnly();
    renderWithClient(<BookDetailPage bookId={STANDARD_PRICING_BOOK} />);

    // The posture is the tenant config's own query, which may answer after
    // the book does — so wait for the sentence it decides, not for the page.
    expect(await screen.findByText(METERING_ONLY_PRICES)).toBeInTheDocument();
  });

  it("says nothing of the kind in a workspace that bills", async () => {
    renderWithClient(<BookDetailPage bookId={STANDARD_PRICING_BOOK} />);
    await screen.findByRole("heading", { name: "Agreed prices" });

    expect(screen.queryByText(METERING_ONLY_PRICES)).not.toBeInTheDocument();
  });

  it("says nothing of the kind on a cost book", async () => {
    meteringOnly();
    renderWithClient(<BookDetailPage bookId={OPENAI_COST_BOOK} />);
    expect(await screen.findByText("OpenAI provider costs")).toBeInTheDocument();

    await waitFor(() => expect(screen.queryByText(METERING_ONLY_PRICES)).not.toBeInTheDocument());
  });

  it("can declare a Pricing Book: the option is open, not gated on billing", async () => {
    meteringOnly();
    renderWithClient(<CreateBookDialog open onOpenChange={() => undefined} />);

    const option = await screen.findByRole("button", { name: /Pricing book/ });
    expect(option).toBeEnabled();
    expect(screen.queryByText(/need the Billing product/)).not.toBeInTheDocument();
  });
});
