import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";

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

async function sendEvent(fields: {
  billedCost?: string;
  measurementKey?: string;
  eventType?: string;
}) {
  const customerInput = screen.getByPlaceholderText("…or paste a customer UUID");
  fireEvent.change(customerInput, { target: { value: CUSTOMER_UUID } });
  if (fields.eventType !== undefined) {
    fireEvent.change(screen.getByPlaceholderText("chat_completion"), {
      target: { value: fields.eventType },
    });
  }
  if (fields.billedCost !== undefined) {
    fireEvent.change(screen.getByPlaceholderText("0.60"), {
      target: { value: fields.billedCost },
    });
  }
  if (fields.measurementKey !== undefined) {
    fireEvent.change(screen.getByLabelText("Measurement 1 name"), {
      target: { value: fields.measurementKey },
    });
    fireEvent.change(screen.getByLabelText("Measurement 1 quantity"), {
      target: { value: "100" },
    });
  }
  const sendButton = screen.getByRole("button", { name: "Send test event" });
  await waitFor(() => expect(sendButton).toBeEnabled());
  fireEvent.click(sendButton);
}

describe("TestEventConsole", () => {
  it("sends an event and shows the priced response with the event id", async () => {
    renderConsole();
    await sendEvent({ billedCost: "0.60" });
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
    await sendEvent({ eventType: "anthropic.messages_CREATE", billedCost: "0.60" });

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

  it("shows the stop verdict block when the response says stop", async () => {
    renderConsole();
    // The mock wallet starts at $12.50 — a $20 event tips it past the floor.
    await sendEvent({ billedCost: "20" });
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
    await sendEvent({ billedCost: "0.25" });
    expect(await screen.findByText("$0.2500")).toBeInTheDocument();
    await sendEvent({ billedCost: "0.35" });
    expect(await screen.findByText("$0.3500")).toBeInTheDocument();
    // Both entries visible at once.
    expect(screen.getByText("$0.2500")).toBeInTheDocument();
  });
});
