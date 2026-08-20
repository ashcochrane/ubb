import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { costingStatusLabel, unresolvedReasonLabel } from "@/lib/supplier-cost";

import { TestEventConsole } from "./test-event-console";

const CUSTOMER_UUID = "c1a2b3d4-0001-4abc-9def-000000000001";

function renderConsole() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <TestEventConsole />
    </QueryClientProvider>,
  );
}

/**
 * A priced measurement, and how many of it buys a chosen amount.
 *
 * ⚠ THE FORM NO LONGER HAS A PRICE INPUT, so a case that wants a particular
 * billed figure has to buy it (#365). These cases used to type the amount
 * straight into a "Billed cost" box hinted "overrides pricing" — the bypass the
 * API deleted — and the amounts they assert are the same ones, now reached the
 * way a real tenant reaches them: quantities, priced by configuration.
 */
const PRICED_MEASUREMENT = "requests";
const MICROS_PER_REQUEST = 50_000;

function requestsWorth(micros: number): string {
  // Refuses an amount the rate cannot reach rather than rounding to one it can
  // — its Python twin `priced_at` does the same, and for the same reason: a
  // case silently asserting 12.5 requests would be asserting a figure nothing
  // in it chose. The form takes whole quantities only.
  if (micros % MICROS_PER_REQUEST !== 0) {
    throw new Error(
      `${micros} is not a whole number of priced requests at ${MICROS_PER_REQUEST} micros each`,
    );
  }
  return String(micros / MICROS_PER_REQUEST);
}

async function sendEvent(fields: {
  measurementKey?: string;
  quantity?: string;
  eventType?: string;
}) {
  const customerInput = screen.getByPlaceholderText("…or paste a customer UUID");
  fireEvent.change(customerInput, { target: { value: CUSTOMER_UUID } });
  if (fields.eventType !== undefined) {
    fireEvent.change(screen.getByPlaceholderText("chat_completion"), {
      target: { value: fields.eventType },
    });
  }
  if (fields.measurementKey !== undefined) {
    fireEvent.change(screen.getByLabelText("Measurement 1 name"), {
      target: { value: fields.measurementKey },
    });
    fireEvent.change(screen.getByLabelText("Measurement 1 quantity"), {
      target: { value: fields.quantity ?? "100" },
    });
  }
  const sendButton = screen.getByRole("button", { name: "Send test event" });
  await waitFor(() => expect(sendButton).toBeEnabled());
  fireEvent.click(sendButton);
}

/** Send an event whose configured price comes to exactly `micros`. */
async function sendEventPricedAt(micros: number, eventType?: string) {
  await sendEvent({
    measurementKey: PRICED_MEASUREMENT,
    quantity: requestsWorth(micros),
    ...(eventType !== undefined && { eventType }),
  });
}

describe("TestEventConsole", () => {
  it("sends an event and shows the priced response with the event id", async () => {
    renderConsole();
    await sendEventPricedAt(600_000);
    expect(await screen.findByText("Usage event recorded")).toBeInTheDocument();
    expect(screen.getByText("Billed cost")).toBeInTheDocument();
    // Per-event amounts under 1 unit keep 4-decimal precision.
    expect(screen.getByText("$0.6000")).toBeInTheDocument();
    expect(screen.getByLabelText("Copy event id")).toBeInTheDocument();
    // No stop verdict on an affordable event.
    expect(screen.queryByText("Stop verdict")).not.toBeInTheDocument();
  });

  it("names the tenant's Event Type key exactly as they typed it", async () => {
    // The teaching surface is where a manufactured name does the most damage:
    // an integrator reads this card to learn what UBB recorded, and a key it
    // title-cased is a key they cannot find again. #279 — a `tenant_defined`
    // value renders as the tenant declared it.
    renderConsole();
    // Chosen so the retired humaniser is visible in the failure rather than
    // merely absent from it: it lower-cased, stripped the underscore and
    // capitalised the first letter, turning this into "Anthropic.messages
    // create".
    await sendEventPricedAt(600_000, "anthropic.messages_CREATE");

    // `textContent` on the heading, not `getByText`: a substring matcher would
    // pass on "Anthropic.messages CREATE (anthropic.messages_CREATE)", which is
    // still English UBB wrote for somebody else's identifier.
    const heading = await screen.findByText(/recorded$/);
    expect(heading.textContent).toBe("anthropic.messages_CREATE recorded");
  });

  it("flags measurements without a cost card as uncosted", async () => {
    renderConsole();
    await sendEvent({ measurementKey: "gpu_seconds" });
    expect(
      await screen.findByText("Measurements without a cost card"),
    ).toBeInTheDocument();
    expect(screen.getByText("gpu_seconds")).toBeInTheDocument();
  });

  // #330: the same response, read from the money row. An integrator learning
  // what UBB recorded must not be shown a supplier cost of zero for a cost UBB
  // never learned — and a bare dash would leave them unable to tell that from
  // an event whose type has no supplier cost at all.
  it("names an unlearned supplier cost rather than zeroing or dashing it", async () => {
    renderConsole();
    await sendEvent({ measurementKey: "gpu_seconds" });

    expect(
      await screen.findByText(costingStatusLabel("unresolved")),
    ).toBeInTheDocument();
    expect(screen.getByText("Missing input")).toBeInTheDocument();
    expect(
      screen.getByText(unresolvedReasonLabel("cost_rate_missing")),
    ).toBeInTheDocument();

    // Scoped to the supplier-cost stat, not the card: the BILLED zero beside it
    // is a real, resolved zero — this request priced nothing because nothing
    // priced its measurement — and must stay readable as one.
    const stat = screen.getByText("Provider cost").closest("div");
    expect(stat?.textContent ?? "").not.toContain("$0.00");
    expect(stat?.textContent ?? "").toContain(costingStatusLabel("unresolved"));
  });

  it("shows the stop verdict block when the response says stop", async () => {
    renderConsole();
    // The mock wallet starts at $12.50 — a $20 event tips it past the floor.
    await sendEventPricedAt(20_000_000);
    expect(await screen.findByText("Stop verdict")).toBeInTheDocument();
    expect(screen.getByText("Customer balance floor")).toBeInTheDocument();
    // Scope label ("Customer") joins the form's own "Customer" label.
    expect(screen.getAllByText("Customer").length).toBeGreaterThanOrEqual(2);
    // The teaching line: HTTP was still 200 by design.
    expect(
      screen.getByText(/HTTP status was still 200/),
    ).toBeInTheDocument();
  });

  it("keeps earlier responses so runs can be compared", async () => {
    renderConsole();
    await sendEventPricedAt(250_000);
    expect(await screen.findByText("$0.2500")).toBeInTheDocument();
    await sendEventPricedAt(350_000);
    expect(await screen.findByText("$0.3500")).toBeInTheDocument();
    // Both entries visible at once.
    expect(screen.getByText("$0.2500")).toBeInTheDocument();
  });
});
