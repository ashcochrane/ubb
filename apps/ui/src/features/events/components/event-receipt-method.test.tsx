// Two events of one Event Type, reading differently — spec §21.
//
// ⚠ **THIS IS NOT A BUG FOR THE UI TO SMOOTH OVER.** One customer is on a
// margin over what their calls cost; another has negotiated a flat price for
// the same work. Both record `embedding.create`, both against the same
// provider, with the same measured quantities — and their receipts say
// different things about how the amount was arrived at, because the receipt
// records the method and the applied value PER EVENT, BY VALUE, precisely so it
// can be shown. A console that took the method from the Event Type would have
// to pick one of the two and be wrong for the other customer, on the screen a
// tenant opens to check a single charge.
//
// These render from the FEATURE MOCK rather than from a hand-built payload,
// deliberately: the point is that the console shows what it is sent, and the
// mock is what it is sent. The hand-built half of this slice's rendering
// evidence is `features/pricing/components/publish-diff.test.tsx`, which
// carries the narrowing mutation.

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { EVENT_DIRECTLY_PRICED_ID, EVENT_MARGIN_PRICED_ID } from "../api/mock-data";
import { EventDetailPage } from "./event-detail-page";

function renderReceipt(eventId: string) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <EventDetailPage eventId={eventId} onBack={vi.fn()} />
    </QueryClientProvider>,
  );
}

/** The customer-price section, scoped: the two sides share status words. */
function priceSection() {
  return within(screen.getByText("Customer price").closest("section") as HTMLElement);
}

describe("two events of the same Event Type", () => {
  it("says a margin-priced event was priced by a margin over cost", async () => {
    const view = renderReceipt(EVENT_MARGIN_PRICED_ID);
    expect(await screen.findByText("Event receipt")).toBeInTheDocument();

    expect(priceSection().getByText("Priced by")).toBeInTheDocument();
    expect(priceSection().getByText("Margin over cost")).toBeInTheDocument();
    expect(priceSection().queryByText("Direct event price")).not.toBeInTheDocument();
    view.unmount();
  });

  it("says a directly-priced event of the SAME type was priced directly", async () => {
    // ⚠ THE DISCRIMINATING HALF. A receipt that merely rendered a method would
    // pass the case above whether or not the two events differ; what makes the
    // per-event record visible is that the same Event Type reads the other way
    // one customer over.
    const view = renderReceipt(EVENT_DIRECTLY_PRICED_ID);
    expect(await screen.findByText("Event receipt")).toBeInTheDocument();

    expect(priceSection().getByText("Direct event price")).toBeInTheDocument();
    expect(priceSection().queryByText("Margin over cost")).not.toBeInTheDocument();
    // Same Event Type, same provider, same measured quantity — so nothing but
    // the deal itself is different between the two.
    expect(screen.getByText("embedding.create")).toBeInTheDocument();
    expect(screen.getByText("openai")).toBeInTheDocument();
    view.unmount();
  });

  it("carries the method inside the receipt record too, not only on the column", async () => {
    // The column is written off the record's own pricing section, so the two
    // cannot disagree — and the record is what a tenant reading a six-year-old
    // receipt will have.
    renderReceipt(EVENT_MARGIN_PRICED_ID);
    expect(await screen.findByText("Event receipt")).toBeInTheDocument();

    const receipt = within(
      screen.getByText("Pricing receipt").closest("section") as HTMLElement,
    );
    expect(receipt.getByText("margin_over_cost")).toBeInTheDocument();
    // A margin's terms ride in the price section's detail BY VALUE: the
    // percentage and the basis it was taken over. A receipt naming a margin
    // without saying over what would explain nothing.
    expect(receipt.getByText("micro_percent")).toBeInTheDocument();
    expect(receipt.getByText("basis_micros")).toBeInTheDocument();
  });
});

describe("what a Pricing Receipt is, and is not", () => {
  // ⚠ THE QUALIFICATION #370 HANDED FORWARD, IN THE CONSOLE'S OWN WORDS. A
  // receipt is the record of an ECONOMIC RESOLUTION and every event has one —
  // including on a workspace that meters and never bills anybody. A heading
  // reading "Pricing receipt" over a block of numbers is, on its own, an
  // invitation to read the presence of a receipt as proof that a customer was
  // charged.
  it("says a receipt is not evidence a customer was charged", async () => {
    renderReceipt(EVENT_MARGIN_PRICED_ID);
    expect(await screen.findByText("Event receipt")).toBeInTheDocument();

    expect(
      screen.getByText(/is not evidence that a customer was charged/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/including on a workspace that only meters/i),
    ).toBeInTheDocument();
  });

  it("records the shape it was written in, and the engine that wrote it", async () => {
    // Two versions, not one: a writer declares a SHAPE and a reader knows a set
    // of them, so a receipt written last year stays readable when the code
    // moves on. A record carrying only "the engine version" — which is what the
    // console's fixture used to invent — cannot answer either question.
    renderReceipt(EVENT_MARGIN_PRICED_ID);
    expect(await screen.findByText("Event receipt")).toBeInTheDocument();

    const receipt = within(
      screen.getByText("Pricing receipt").closest("section") as HTMLElement,
    );
    expect(receipt.getByText("receipt_schema_version")).toBeInTheDocument();
    expect(receipt.getByText("pricing_engine_version")).toBeInTheDocument();
    expect(receipt.getByText("subject_type")).toBeInTheDocument();
    // The four sections the record actually has.
    for (const section of ["costing", "pricing", "totals", "provenance"]) {
      expect(receipt.getByText(section)).toBeInTheDocument();
    }
  });
});
