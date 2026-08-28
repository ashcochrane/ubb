// The receipt's customer-price half, rendered from a fixture THIS FILE builds
// (#371, spec §25).
//
// ⚠ WHY A SECOND FILE, AND WHY THE PROVIDER IS STUBBED. Spec §25: *"a rendering
// test cannot see a narrowing defect where the mock returns its fixture object.
// The mutation stays green across every component test."* Every other test on
// this page renders what `features/events/api/mock-data.ts` composed, so the
// mock and the page agree by construction: narrow a type in the fixture module
// and the mock narrows with it, the page keeps receiving exactly what it always
// received, and nothing goes red. A real narrowing mutation survived every
// component test in this codebase once.
//
// So the detail below is assembled HERE, field by field, and served through a
// stubbed provider. The only thing it takes from the fixture module is the one
// object under test — `priceNotApplicable("tenant_not_billing")` — which is the
// point: this asserts on RENDERED OUTPUT for a payload the mock never saw.
//
// ⚠ THE MUTATION THAT PROVES IT IS NOT VACUOUS, and it is chosen to be one the
// mock CANNOT see. In `@/lib/economic-scenarios`, narrow `priceNotApplicable`
// to ignore its argument and return `not_applicable_reason: "fixed_task_pricing"`
// always. EVERY MOCK-AUTHORED RENDERING TEST STAYS GREEN — the events mock
// seeds that very reason, so the fixture it composes is unchanged and the page
// receives exactly what it always received.
//
// Measured on this commit: 5 of 451 fail. Two are unit tests, which call the
// narrowed function directly. The three RENDERING failures are the first two
// below and one in `features/developers/components/test-event-response.test.tsx`
// — and that file assembles its own response for the same reason this one does.
// NOT ONE MOCK-AUTHORED COMPONENT TEST MOVES. That is the shape spec §25
// describes, and it is a narrowing rather than a rename: the CAUSE stops
// reaching the renderer, and no token moves.
//
// AND THIS IS THE SIXTH ECONOMIC STATE'S ONLY POSSIBLE HOME. `tenant_not_billing`
// says the workspace meters and does not bill customers through UBB at all; the
// events mock's workspace has billing enabled, so a posting of its own claiming
// otherwise would be a fixture describing a tenant that is not the one every
// other fixture in that file describes. #155 §9.2 asks for a fixture and a
// rendering assertion, not for an incoherent mock.

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
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
  availableMeasurements,
  knownCost,
  priceNotApplicable,
} from "@/lib/economic-scenarios";

import { correlationId } from "../api/mock-data";
import type { UsageEventDetail } from "../api/types";
import { EventDetailPage } from "./event-detail-page";

const METERING_ONLY_EVENT_ID = "0b4d7e21-5c68-4a39-9d02-8e1f3a6c7b50";

/**
 * One posting on a workspace that meters and does not bill.
 *
 * Hand-assembled rather than seeded, for the reason in the header. Only the
 * price is composed — from the canonical scenario, so the status and its cause
 * cannot disagree — and everything around it is the ordinary case, so a failure
 * below can only be about the price.
 */
const METERING_ONLY_DETAIL: UsageEventDetail = {
  id: METERING_ONLY_EVENT_ID,
  // The correlation id, from the events feature's own helper rather than
  // spelled here. There were TWO until #411, and the helper was plural: one of
  // them was a retired term whose console ledger entry capped the files naming
  // it, so routing through the helper kept this module out of that count (#366,
  // Phase B's second technique). The field and the entry are both gone, and the
  // helper is now singular. It is still a key-shape helper rather than a
  // fixture: nothing about the payload below comes from the mock.
  ...correlationId(METERING_ONLY_EVENT_ID),
  ...priceNotApplicable("tenant_not_billing"),
  ...knownCost(61_000),
  effective_at: "2026-07-09T12:14:07Z",
  created_at: "2026-07-09T12:14:08Z",
  currency: "usd",
  event_type: "chat.completion",
  provider: "openai",
  grouping_fields: {},
  ...availableMeasurements({ input_tokens: 1100, output_tokens: 320 }),
  pricing_receipt: {},
  metadata: {},
  task_id: null,
  stop_context: null,
};

vi.mock("../api/provider", () => ({
  eventsApi: {
    // Only what this page asks for. A stub that answered more would be a second
    // mock to keep true, and the page under test reads exactly one endpoint.
    getUsageEvent: async () => METERING_ONLY_DETAIL,
  },
}));

function renderReceipt() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const ui: ReactElement = (
    <QueryClientProvider client={queryClient}>
      <EventDetailPage eventId={METERING_ONLY_EVENT_ID} onBack={vi.fn()} />
    </QueryClientProvider>
  );
  return render(ui);
}

function priceSectionText(): string {
  const section = screen.getByText("Customer price").closest("section");
  expect(section).not.toBeNull();
  return section?.textContent ?? "";
}

describe("a receipt on a workspace that does not bill", () => {
  // ⚠ THE ASSERTION THE MUTATION ABOVE REDDENS, and the second half of AC 5:
  // the two not-applicable causes have to be visibly different answers.
  // `fixed_task_pricing` leaves a real charge to go and look at; this one says
  // no charge exists anywhere. A receipt that gave both the generic status
  // sentence would answer both questions with the same shrug.
  it("says no charge exists anywhere, not that one is priced at the Task", async () => {
    renderReceipt();

    expect(await screen.findByText("Event receipt")).toBeInTheDocument();

    expect(
      screen.getByText(NOT_APPLICABLE_REASON_EXPLANATIONS.tenant_not_billing),
    ).toBeInTheDocument();
    expect(
      screen.queryByText(NOT_APPLICABLE_REASON_EXPLANATIONS.fixed_task_pricing),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText(PRICING_STATUS_EXPLANATIONS.not_applicable),
    ).not.toBeInTheDocument();
  });

  it("names the cause in the catalogue's words, beside the status", async () => {
    renderReceipt();

    expect(await screen.findByText("Event receipt")).toBeInTheDocument();

    expect(screen.getByText("Why")).toBeInTheDocument();
    expect(priceSectionText()).toContain(
      notApplicableReasonLabel("tenant_not_billing"),
    );
    expect(priceSectionText()).toContain(pricingStatusLabel("not_applicable"));
  });

  // #155 §9.2's standing rule, on the sixth state: the amount is absent and
  // must render as an absence. `$0.00` here would tell a workspace that never
  // bills anybody that it charged a customer nothing.
  it("renders no amount at all, and never a charge of nothing", async () => {
    renderReceipt();

    expect(await screen.findByText("Event receipt")).toBeInTheDocument();

    const billed = screen.getByText("Billed").closest("div");
    expect(billed).not.toBeNull();
    expect(billed?.textContent ?? "").toContain(ABSENT_LABEL);
    expect(priceSectionText()).not.toMatch(/[$£€]\s*-?[\d,]/);

    // The supplier cost on the same posting is settled and still a figure —
    // metering-only workspaces still learn what their suppliers charged, which
    // is the entire point of metering without billing.
    expect(screen.getByText("$0.0610")).toBeInTheDocument();
  });
});
