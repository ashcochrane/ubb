import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import type { ReactElement } from "react";
import { describe, expect, it, vi } from "vitest";

import {
  NOT_APPLICABLE_REASON_EXPLANATIONS,
  PRICING_STATUS_EXPLANATIONS,
  notApplicableReasonLabel,
  pricingStatusLabel,
} from "@/lib/customer-price";
import { ABSENT_LABEL } from "@/lib/localisation";
import {
  COSTING_STATUS_EXPLANATIONS,
  costingStatusLabel,
  unresolvedReasonLabel,
} from "@/lib/supplier-cost";

import {
  CUSTOMER_A_ID,
  EVENT_COST_NOT_APPLICABLE_ID,
  EVENT_PRUNED_ID,
  EVENT_RICH_ID,
  EVENT_TASK_CHARGE_ID,
  EVENT_TASK_KILL_ID,
  EVENT_PRICE_NOT_APPLICABLE_ID,
  EVENT_TIPPING_ID,
  EVENT_UNPRICED_ID,
  EVENT_UNRESOLVED_ID,
  EVENT_WAIVED_ID,
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

/** The receipt's two money sections, by the titles they render under. */
const CUSTOMER_PRICE = "Customer price";
const SUPPLIER_COST = "Supplier cost";

/**
 * Everything one section of the receipt says.
 *
 * ⚠ THE SECTION IS THE UNIT NOW (#371), and it has to be. The catalogue gives
 * `costing_status.known` and `pricing_status.known` the same word, so a
 * page-wide query for "Known" finds two nodes and cannot say which side it
 * found — and the two are opposite facts about the same posting. Scoping the
 * question to a section is what keeps an assertion about the price from
 * passing on the cost.
 */
function sectionText(title: string): string {
  const section = screen.getByText(title).closest("section");
  expect(section).not.toBeNull();
  return section?.textContent ?? "";
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
    // Usage measurements (the key also appears in the receipt).
    expect(screen.getAllByText("input_tokens").length).toBeGreaterThan(0);
    expect(screen.getByText("4,200")).toBeInTheDocument();
    // The receipt renders structured, not as raw JSON.
    expect(screen.getByText("Pricing receipt")).toBeInTheDocument();
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
    // rather than the page, because the page legitimately carries numbers
    // elsewhere — a receipt's own terms are real values and must stay
    // readable.
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

  // --- the supplier cost UBB never learned (#330, #155 §9.2) --------------
  //
  // Same rule as the measurement trio above, one field over: an absence has to
  // render as the absence it is, and the two absences a supplier cost can have
  // must not look alike. Nothing is stubbed — the fixture is a representative
  // payload served by this feature's own mock provider.

  it("renders an unlearned supplier cost AS UNLEARNED — never as zero", async () => {
    renderPage({ eventId: EVENT_UNRESOLVED_ID, customerId: CUSTOMER_A_ID });

    expect(await screen.findByText("Event receipt")).toBeInTheDocument();

    // THE ASSERTION THE TICKET EXISTS FOR. A cost UBB has not learned rendered
    // as `$0.00` would state that the supplier charged nothing, and the margin
    // computed against that zero would read as the whole billed amount — the
    // flattering direction, on the one screen a tenant opens to check a single
    // event.
    expect(sectionText(SUPPLIER_COST)).not.toContain("$0.00");

    // The absence is NAMED, in the catalogue's words rather than the console's.
    expect(sectionText(SUPPLIER_COST)).toContain(costingStatusLabel("unresolved"));
    expect(
      screen.getByText(COSTING_STATUS_EXPLANATIONS.unresolved),
    ).toBeInTheDocument();
    // And the missing INPUT is named beside it: a status saying a cost is
    // missing without saying what would settle it is a shrug.
    expect(screen.getByText("Missing input")).toBeInTheDocument();
    expect(
      screen.getByText(unresolvedReasonLabel("cost_rate_missing")),
    ).toBeInTheDocument();

    // What was billed is still on the receipt, which is what makes the silence
    // about the supplier cost something the tenant can see rather than infer.
    expect(screen.getByText("$0.0310")).toBeInTheDocument();
  });

  // #155 §9.2's owed rendering assertions for the states #351 introduces, and
  // the mirror of the supplier-cost one above. `economic-scenarios.ts` composes
  // all three; this is the surface that proves each renders as ITSELF — an
  // absence — rather than as a charge of nothing.
  //
  // ⚠ EVERY SEED HERE HAS A SETTLED SUPPLIER COST, on purpose. A row missing
  // both amounts would pass against a screen that read either status for both,
  // so the crossed case is the only one that separates them — and the settled
  // cost figure asserted below is what proves the absence is about the price
  // rather than about the screen.
  //
  // NAMING which of the three it is arrives in #371, below. What #351 owed, and
  // what these assert, is that none of them renders as money.
  it.each([
    ["unknown", EVENT_UNPRICED_ID, "$0.0190"],
    ["waived", EVENT_WAIVED_ID, "$0.0125"],
    ["not_applicable", EVENT_PRICE_NOT_APPLICABLE_ID, "$0.0084"],
  ] as const)(
    "renders a %s customer price AS ABSENT — never as zero",
    async (status, eventId, settledCost) => {
      renderPage({ eventId, customerId: CUSTOMER_A_ID });

      expect(await screen.findByText("Event receipt")).toBeInTheDocument();

      // Rendered as `$0.00` this would tell a tenant they charged their
      // customer nothing — the unflattering direction of the identical mistake
      // the cost half makes.
      const billed = screen.getByText("Billed").closest("div");
      expect(billed).not.toBeNull();
      expect(billed?.textContent ?? "").not.toContain("$0.00");
      expect(billed?.textContent ?? "").toContain(ABSENT_LABEL);

      // ⚠ AND #371'S HALF: THE ABSENCE IS NAMED. A dash says something is not
      // there; the status says WHICH not-there this is, and the three mean
      // different things about whether anything is missing — only `unknown` is.
      // In the catalogue's words, never the console's.
      expect(sectionText(CUSTOMER_PRICE)).toContain(pricingStatusLabel(status));
      // No currency amount anywhere in the section, not merely no `$0.00`:
      // "at least $0.00" and "$0.0000" would both slip past the narrower test.
      expect(sectionText(CUSTOMER_PRICE)).not.toMatch(/[$£€]\s*-?[\d,]/);

      // The SUPPLIER cost on the same posting is settled and still a figure —
      // which is what proves the absence is about the price rather than about
      // the screen.
      expect(screen.getByText(settledCost)).toBeInTheDocument();
      expect(sectionText(SUPPLIER_COST)).toContain(costingStatusLabel("known"));

      // And with no price there is nothing to refund.
      expect(screen.queryByText("Refund this charge")).not.toBeInTheDocument();
    },
  );

  // ⚠ AC 5. THE TWO NOT-APPLICABLE REASONS ARE DIFFERENT ANSWERS, and this is
  // the one of them a coherent workspace can seed. `fixed_task_pricing` leaves
  // a real charge to go and look at — it sits on the Task — so the receipt must
  // send the reader there rather than shrug.
  //
  // Its sibling, `tenant_not_billing`, cannot be seeded from this mock: this
  // workspace bills. It is rendered in `event-receipt-price.test.tsx` from a
  // fixture the mock does not author, which is also where the narrowing proof
  // lives.
  it("says WHY a price does not apply, and sends the reader to the Task", async () => {
    renderPage({
      eventId: EVENT_PRICE_NOT_APPLICABLE_ID,
      customerId: CUSTOMER_A_ID,
    });

    expect(await screen.findByText("Event receipt")).toBeInTheDocument();

    expect(screen.getByText("Why")).toBeInTheDocument();
    expect(sectionText(CUSTOMER_PRICE)).toContain(
      notApplicableReasonLabel("fixed_task_pricing"),
    );
    expect(
      screen.getByText(NOT_APPLICABLE_REASON_EXPLANATIONS.fixed_task_pricing),
    ).toBeInTheDocument();

    // NOT the other cause, and NOT the generic status sentence: a screen that
    // fell back to either would answer "why is there no price here?" with the
    // shrug the reason exists to replace.
    expect(
      screen.queryByText(NOT_APPLICABLE_REASON_EXPLANATIONS.tenant_not_billing),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText(PRICING_STATUS_EXPLANATIONS.not_applicable),
    ).not.toBeInTheDocument();
  });

  it("asks WHY only where the status has a reason to give", async () => {
    renderPage({ eventId: EVENT_UNPRICED_ID, customerId: CUSTOMER_A_ID });

    expect(await screen.findByText("Event receipt")).toBeInTheDocument();
    expect(screen.getByText(PRICING_STATUS_EXPLANATIONS.unknown)).toBeInTheDocument();
    expect(screen.queryByText("Why")).not.toBeInTheDocument();
  });

  it("names a settled price as settled", async () => {
    renderPage({ eventId: EVENT_RICH_ID, customerId: CUSTOMER_A_ID });

    expect(await screen.findByText("Event receipt")).toBeInTheDocument();
    expect(sectionText(CUSTOMER_PRICE)).toContain(pricingStatusLabel("known"));
    expect(screen.getByText(PRICING_STATUS_EXPLANATIONS.known)).toBeInTheDocument();
    expect(screen.queryByText("Why")).not.toBeInTheDocument();
  });

  // Slice 3's third canonical cost scenario, which reached nothing but its own
  // unit test until this commit (#371, ruling 10(b)). A cost the Event Type
  // never declared and a cost UBB tried to learn and could not are the SAME
  // null column and opposite facts — one is missing from every total, the other
  // was never in one — so the screen has to tell them apart.
  it("renders a cost that was never owed distinctly from one never learned", async () => {
    renderPage({
      eventId: EVENT_COST_NOT_APPLICABLE_ID,
      customerId: CUSTOMER_A_ID,
    });

    expect(await screen.findByText("Event receipt")).toBeInTheDocument();

    expect(sectionText(SUPPLIER_COST)).toContain(
      costingStatusLabel("not_applicable"),
    );
    expect(
      screen.getByText(COSTING_STATUS_EXPLANATIONS.not_applicable),
    ).toBeInTheDocument();

    // Not the other empty-cost state, and no input is asked for: there is no
    // recovery that would ever fill this in.
    expect(sectionText(SUPPLIER_COST)).not.toContain(
      costingStatusLabel("unresolved"),
    );
    expect(screen.queryByText("Missing input")).not.toBeInTheDocument();
    expect(sectionText(SUPPLIER_COST)).not.toContain("$0.00");

    // The customer price on the same posting is settled and still a figure.
    expect(screen.getByText("$0.0150")).toBeInTheDocument();
  });

  it("names a settled cost as settled, and asks for no missing input", async () => {
    renderPage({ eventId: EVENT_RICH_ID, customerId: CUSTOMER_A_ID });

    expect(await screen.findByText("Event receipt")).toBeInTheDocument();
    // ⚠ SCOPED TO THE SECTION, because `costing_status.known` and
    // `pricing_status.known` are the same word in the catalogue and #371 put
    // both statuses on this page. A page-wide `getByText("Known")` now finds
    // two nodes and throws — and the two are DIFFERENT facts, so the fix is to
    // ask the right side rather than to relax the query to `getAllByText`.
    expect(sectionText(SUPPLIER_COST)).toContain(costingStatusLabel("known"));
    expect(screen.queryByText("Missing input")).not.toBeInTheDocument();
    expect(sectionText(SUPPLIER_COST)).not.toContain(
      costingStatusLabel("unresolved"),
    );
  });

  it("closes a task holding an unlearned cost and says the total is a floor", async () => {
    // The still-open task holds the one unresolved event, so its rolled-up
    // supplier cost can only be higher than it says.
    renderPage({ eventId: EVENT_UNRESOLVED_ID, customerId: CUSTOMER_A_ID });

    fireEvent.click(await screen.findByRole("button", { name: "Close task" }));
    fireEvent.click(await screen.findByRole("button", { name: "Yes, close it" }));

    expect(await screen.findByText(/Task closed/)).toBeInTheDocument();
    expect(screen.getByText(/^at least \$\d/)).toBeInTheDocument();
    expect(screen.getByText("Costs still unknown")).toBeInTheDocument();
  });

  // AC 3, and the case a marker would get wrong. The killed task holds two
  // events costed two different ways — one reported by the caller, one
  // calculated from Cost Rates — and nothing is missing from it. Mixed
  // derivation is COMPLETE: a footnote on every mixed total is a footnote on
  // almost every total, and the completeness question reads the count and
  // nothing else.
  it("reads a task costed BOTH ways as complete, with no caveat", async () => {
    renderPage({ eventId: EVENT_TASK_KILL_ID, customerId: CUSTOMER_A_ID });

    fireEvent.click(await screen.findByRole("button", { name: "Close task" }));
    fireEvent.click(await screen.findByRole("button", { name: "Yes, close it" }));

    expect(await screen.findByText(/Task closed — Killed/)).toBeInTheDocument();
    // Two events, $0.05 reported + $0.03 calculated, and the total is a figure.
    expect(screen.getByText("$0.08")).toBeInTheDocument();
    expect(screen.queryByText(/at least/)).not.toBeInTheDocument();
    expect(screen.queryByText("Costs still unknown")).not.toBeInTheDocument();
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
