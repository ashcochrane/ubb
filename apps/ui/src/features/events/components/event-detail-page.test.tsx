import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import type { ReactElement } from "react";
import { describe, expect, it, vi } from "vitest";

import {
  CUSTOMER_A_ID,
  EVENT_PRUNED_ID,
  EVENT_RICH_ID,
  EVENT_TASK_CHARGE_ID,
  EVENT_TIPPING_ID,
} from "../api/mock-data";
import {
  MEASUREMENTS_STATUS_EXPLANATIONS,
  NO_QUANTITIES_RECORDED,
  measurementsStatusLabel,
} from "../lib/measurements";
import { EventDetailPage } from "./event-detail-page";

function renderPage(props: { eventId: string; customerId?: string }) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  const ui: ReactElement = (
    <QueryClientProvider client={queryClient}>
      <EventDetailPage
        eventId={props.eventId}
        customerId={props.customerId}
        onBack={vi.fn()}
      />
    </QueryClientProvider>
  );
  return render(ui);
}

describe("EventDetailPage", () => {
  it("renders the full receipt for the rich mock event", async () => {
    renderPage({ eventId: EVENT_RICH_ID, customerId: CUSTOMER_A_ID });

    expect(await screen.findByText("Event receipt")).toBeInTheDocument();
    // Identity in mono with copy affordances.
    expect(screen.getByText("req_search_reindex_0042")).toBeInTheDocument();
    // Money from the fixture: billed 187,500 micros — sub-unit amounts keep
    // 4-decimal precision so micro-priced events never round to $0.00.
    expect(screen.getByText("$0.1875")).toBeInTheDocument();
    // Usage measurements (the key also appears in the provenance receipt).
    expect(screen.getAllByText("input_tokens").length).toBeGreaterThan(0);
    expect(screen.getByText("4,200")).toBeInTheDocument();
    // The provenance receipt renders structured, not as raw JSON.
    expect(screen.getByText("Pricing provenance")).toBeInTheDocument();
    expect(screen.getByText("llm-prices-2026")).toBeInTheDocument();
  });

  it("labels each grouping value with the key the tenant declared", async () => {
    // #277: the receipt used to carry three rows reading "Dimension 1..3" —
    // console English for a slot number the tenant never chose, and only ever
    // three of the ten slots that exist. Each declared key is now its own row,
    // labelled with the tenant's own word and rendered VERBATIM: a declared key
    // is tenant-authored data, not a registry concept, so there is nothing to
    // look up and nothing to title-case (ADR-0008 §4.3).
    renderPage({ eventId: EVENT_RICH_ID, customerId: CUSTOMER_A_ID });

    expect(await screen.findByText("Event receipt")).toBeInTheDocument();
    expect(screen.getByText("copilot")).toBeInTheDocument();
    expect(screen.getByText("realtime-api")).toBeInTheDocument();
    expect(screen.getByText("agent-7")).toBeInTheDocument();
    expect(screen.queryByText("Dimension 1")).not.toBeInTheDocument();
  });

  it("omits a grouping row entirely when the posting carried no value", async () => {
    // An unset slot is absent from the object rather than present as "", so
    // there is no row and no empty-looking cell to explain away.
    renderPage({ eventId: EVENT_TIPPING_ID, customerId: CUSTOMER_A_ID });

    expect(await screen.findByText("Event receipt")).toBeInTheDocument();
    expect(screen.queryByText("Dimension 2")).not.toBeInTheDocument();
    expect(screen.queryByText("Dimension 3")).not.toBeInTheDocument();
  });

  it("renders the stop context timeline for a tipping event", async () => {
    renderPage({ eventId: EVENT_TIPPING_ID, customerId: CUSTOMER_A_ID });

    expect(await screen.findByText("Stop context")).toBeInTheDocument();
    expect(screen.getByText("Customer balance floor")).toBeInTheDocument();
    expect(screen.getByText("Tipping event")).toBeInTheDocument();
  });

  it("hides the refund action when arriving without a customer id", async () => {
    renderPage({ eventId: EVENT_RICH_ID });

    expect(await screen.findByText("Event receipt")).toBeInTheDocument();
    expect(screen.queryByText("Refund this charge")).not.toBeInTheDocument();
  });

  it("closes the attributed task and shows the returned totals", async () => {
    renderPage({ eventId: EVENT_RICH_ID, customerId: CUSTOMER_A_ID });

    const closeButton = await screen.findByRole("button", {
      name: "Close task",
    });
    fireEvent.click(closeButton);

    // Confirm inside the dialog.
    const confirm = await screen.findByRole("button", { name: "Yes, close it" });
    fireEvent.click(confirm);

    // The returned status + rolled-up totals render inline.
    expect(
      await screen.findByText(/Task closed — Completed/),
    ).toBeInTheDocument();
    expect(screen.getByText("Total billed")).toBeInTheDocument();
    expect(screen.getByText("Total provider cost")).toBeInTheDocument();
  });

  // --- the three measurement states (#281, #155 §9.2) ---------------------
  //
  // The receipt is the one consumer that has to tell these three apart, and
  // #155 §9.5 is the rule being satisfied: a semantic state is not complete
  // until one real consumer demonstrates its intended rendering. Nothing is
  // stubbed here — the scenarios are representative payloads served by the
  // feature's own mock provider, so what these assert is the page, not a
  // double of it.

  it("renders a pruned payload AS PRUNED — never as no usage", async () => {
    renderPage({ eventId: EVENT_PRUNED_ID, customerId: CUSTOMER_A_ID });

    expect(await screen.findByText("Event receipt")).toBeInTheDocument();

    // The section is there at all. An empty bag used to remove it, which is
    // the quietest version of this defect: nothing on the page is wrong
    // because nothing on the page is there.
    expect(screen.getByText("Usage measurements")).toBeInTheDocument();
    // THE ASSERTION THIS TICKET EXISTS FOR, and it is first on purpose.
    // `makeDetail` defaults an unstated status to `available` with `??`, and
    // `available` over an empty bag renders the sentence below — a confident
    // "no usage" for a payload that expired on schedule. This fixture states
    // `pruned` through the canonical scenario, so the default cannot fire.
    // Replace `...prunedMeasurements()` in the seed with a bare
    // `measurements: {}` and this is the line that goes red, naming the wrong
    // sentence in its failure rather than merely missing the right one.
    //
    // THE DEFAULT IS THE FIXTURE'S, AND THAT IS THE ONLY ONE THERE CAN BE.
    // `measurements_status` is `required` on `UsageEventDetailOut`, so the
    // generated type is non-optional and a production `??` over it would not
    // compile. #155 §9.1's rendering-path defect therefore cannot be written
    // here — what CAN be written, and is what this guards, is a fixture that
    // omits the status and a renderer that believes it.
    expect(screen.queryByText(NO_QUANTITIES_RECORDED)).not.toBeInTheDocument();
    // Nor the other empty-bag state, which means something else entirely.
    expect(
      screen.queryByText(measurementsStatusLabel("not_applicable")),
    ).not.toBeInTheDocument();

    // Named in the catalogue's words, not the console's.
    expect(
      screen.getByText(measurementsStatusLabel("pruned")),
    ).toBeInTheDocument();
    expect(
      screen.getByText(MEASUREMENTS_STATUS_EXPLANATIONS.pruned),
    ).toBeInTheDocument();

    // And no quantity was invented to fill the gap. Scoped to the section
    // rather than the page, because the page legitimately carries zeroes
    // elsewhere — a provenance receipt's `fixed_uplift_micros: 0` is a real
    // zero and must stay readable.
    const section = screen.getByText("Usage measurements").closest("section");
    expect(section).not.toBeNull();
    expect(section?.textContent ?? "").not.toMatch(/\d/);

    // What was pruned is the measurement detail. The money it was billed at is
    // still on the receipt, which is what makes the silence about the
    // quantities a thing the customer can see rather than infer.
    expect(screen.getByText("$0.0940")).toBeInTheDocument();
  });

  it("renders a task charge as never-measured, distinctly from pruned", async () => {
    renderPage({ eventId: EVENT_TASK_CHARGE_ID, customerId: CUSTOMER_A_ID });

    expect(await screen.findByText("Event receipt")).toBeInTheDocument();
    expect(screen.getByText(measurementsStatusLabel("not_applicable"))).toBeInTheDocument();
    expect(
      screen.getByText(MEASUREMENTS_STATUS_EXPLANATIONS.not_applicable),
    ).toBeInTheDocument();

    expect(
      screen.queryByText(measurementsStatusLabel("pruned")),
    ).not.toBeInTheDocument();
    expect(screen.queryByText(NO_QUANTITIES_RECORDED)).not.toBeInTheDocument();
  });

  it("renders the quantities themselves when the record is still there", async () => {
    renderPage({ eventId: EVENT_RICH_ID, customerId: CUSTOMER_A_ID });

    expect(await screen.findByText("Event receipt")).toBeInTheDocument();
    expect(screen.getByText("4,200")).toBeInTheDocument();
    expect(
      screen.getByText(MEASUREMENTS_STATUS_EXPLANATIONS.available),
    ).toBeInTheDocument();

    // The available case renders quantities, so neither absence sentence
    // belongs to it either.
    expect(
      screen.queryByText(measurementsStatusLabel("pruned")),
    ).not.toBeInTheDocument();
    expect(screen.queryByText(measurementsStatusLabel("not_applicable"))).not.toBeInTheDocument();
    expect(screen.queryByText(NO_QUANTITIES_RECORDED)).not.toBeInTheDocument();
  });

  it("shows the refund dialog with replay-safe copy and issues the refund", async () => {
    renderPage({ eventId: EVENT_TIPPING_ID, customerId: CUSTOMER_A_ID });

    const refundButton = await screen.findByRole("button", {
      name: "Refund this charge",
    });
    fireEvent.click(refundButton);

    expect(await screen.findByText("Refund this charge?")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /^Refund \$/ }));

    // Success feedback: the action collapses into a disabled "Refunded" state.
    expect(
      await screen.findByRole("button", { name: "Refunded" }),
    ).toBeInTheDocument();
  });
});
