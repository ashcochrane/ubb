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
// object under test — `priceNotApplicable("fixed_task_pricing")` — which is the
// point: this asserts on RENDERED OUTPUT for a payload the mock never saw.
//
// ⚠ THE WORKSPACE IS ONE THAT DOES NOT BILL, AND THAT IS THE #553 CASE. The
// posture used to win here — such a workspace's fixed-price postings carried
// `tenant_not_billing`, "no charge exists anywhere" — and the C2 ruling
// replaced it: the regime decides the reason for every workspace, so this
// posting says what a billing workspace's says, the revenue sits on the run's
// own charge. The events mock's workspace bills, so a workspace that does not
// is assembled here rather than seeded into a mock describing another tenant.
//
// ⚠ THE MUTATION THAT PROVES IT IS NOT VACUOUS: in `@/lib/customer-price`,
// give `NOT_APPLICABLE_REASON_EXPLANATIONS.fixed_task_pricing` a posture-shaped
// sentence ("…does not bill customers…"). The first case below goes red on
// the sentence it reads.

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import type { ReactElement } from "react";
import { describe, expect, it, vi } from "vitest";

import {
  NOT_APPLICABLE_REASON_EXPLANATIONS,
  PRICING_STATUS_EXPLANATIONS,
  PRICING_STATUS_REASON_EXPLANATIONS,
  UNKNOWN_PRICE_WITHOUT_A_REASON,
  notApplicableReasonLabel,
  pricingStatusLabel,
  pricingStatusReasonLabel,
} from "@/lib/customer-price";
import { ABSENT_LABEL } from "@/lib/localisation";
import {
  availableMeasurements,
  heldForRemediation,
  knownCost,
  negativePriceUnsupported,
  priceNotApplicable,
} from "@/lib/economic-scenarios";
import { costingStatusLabel, unresolvedReasonLabel } from "@/lib/supplier-cost";

import { correlationId } from "../api/mock-data";
import type { UsageEventDetail } from "../api/types";
import { sectionText } from "../test-utils";
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
  // A real metered call, which is what this case is about: a workspace that
  // meters and does not bill still records every event it is sent, and the
  // price is the only thing that does not apply. A `task_charge` here would
  // change the subject to a projection nobody reported (#417).
  kind: "metered_usage",
  // The correlation id, from the events feature's own helper rather than
  // spelled here. There were TWO until #411, and the helper was plural: one of
  // them was a retired term whose console ledger entry capped the files naming
  // it, so routing through the helper kept this module out of that count (#366,
  // Phase B's second technique). The field and the entry are both gone, and the
  // helper is now singular. It is still a key-shape helper rather than a
  // fixture: nothing about the payload below comes from the mock.
  ...correlationId(METERING_ONLY_EVENT_ID),
  ...priceNotApplicable("fixed_task_pricing"),
  ...knownCost(61_000),
  effective_at: "2026-07-09T12:14:07Z",
  created_at: "2026-07-09T12:14:08Z",
  currency: "usd",
  event_type: "chat.completion",
  provider: "openai",
  grouping_fields: {},
  ...availableMeasurements({ input_tokens: "1100", output_tokens: "320" }),
  // A version-2 receipt, the only shape the contract publishes (#558): the
  // price section says the regime decided it does not apply.
  pricing_receipt: {
    receipt_schema_version: 2,
    pricing_engine_version: "3.0.0",
    subject_type: "usage_event",
    subject_id: "fixed-task-event",
    effective_at: "2026-07-09T12:14:07Z",
    currency: "usd",
    costing: { method: "calculated", status: "known", detail: {} },
    pricing: {
      method: null,
      status: "not_applicable",
      detail: { pricing_mode: "fixed", not_applicable_reason: "fixed_task_pricing" },
    },
    totals: { provider_cost_micros: 61_000, billed_cost_micros: null },
    provenance: {},
  },
  pricing_receipt_subject_type: "usage_event",
  metadata: {},
  task_id: null,
  stop_context: null,
};

const NEGATIVE_PRICE_EVENT_ID = "5e2c9a71-0b4d-4f86-a3c2-7d1e6b9f0a24";

/**
 * One posting whose configuration calculated a NEGATIVE customer price (#603
 * A2) — a billing workspace this time, so the price applies and was
 * calculated, and UBB cannot carry it. Assembled here for the header's reason:
 * the events mock never authors this state, so only a payload built outside it
 * can show the reason reaching the page. The quantity is negative too, which
 * is how such a price arises, and renders as the exact text it was recorded as.
 */
const NEGATIVE_PRICE_DETAIL: UsageEventDetail = {
  ...METERING_ONLY_DETAIL,
  id: NEGATIVE_PRICE_EVENT_ID,
  ...correlationId(NEGATIVE_PRICE_EVENT_ID),
  ...negativePriceUnsupported(),
  ...availableMeasurements({ returned_documents: "-3" }),
};

const HELD_EVENT_ID = "8c1f5e02-7a3d-4b69-9e14-2d6a0b8f3c71";

/**
 * One posting HELD for remediation (#568): it named an Event Type nobody
 * published, so UBB costed and priced nothing and holds it until the tenant
 * says what the name meant. Assembled here for the header's reason — the
 * events mock never authors this state — and composed whole from
 * `heldForRemediation`, so the cost and the price cannot come apart.
 */
const HELD_DETAIL: UsageEventDetail = {
  ...METERING_ONLY_DETAIL,
  id: HELD_EVENT_ID,
  ...correlationId(HELD_EVENT_ID),
  ...heldForRemediation("event_type_not_declared"),
  event_type: "chat.completion.v2",
};

const DETAILS: Readonly<Record<string, UsageEventDetail>> = {
  [METERING_ONLY_EVENT_ID]: METERING_ONLY_DETAIL,
  [NEGATIVE_PRICE_EVENT_ID]: NEGATIVE_PRICE_DETAIL,
  [HELD_EVENT_ID]: HELD_DETAIL,
};

vi.mock("../api/provider", () => ({
  eventsApi: {
    // Only what this page asks for. A stub that answered more would be a second
    // mock to keep true, and the page under test reads exactly one endpoint.
    getUsageEvent: async (eventId: string) => DETAILS[eventId],
  },
}));

function renderReceipt(eventId: string = METERING_ONLY_EVENT_ID) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const ui: ReactElement = (
    <QueryClientProvider client={queryClient}>
      <EventDetailPage eventId={eventId} onBack={vi.fn()} />
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
  // The C2 ruling (#553) at the console: the price does not apply for the
  // regime's reason, whatever the workspace's billing mode, so the receipt
  // sends the reader to the run's charge — and never to the generic status
  // sentence, which would answer "why is there no price here?" with a shrug.
  it("says the revenue sits on the run's charge, as for any workspace", async () => {
    renderReceipt();

    expect(await screen.findByText("Event receipt")).toBeInTheDocument();

    expect(
      screen.getByText(NOT_APPLICABLE_REASON_EXPLANATIONS.fixed_task_pricing),
    ).toBeInTheDocument();
    expect(screen.queryByText(/does not bill customers/)).not.toBeInTheDocument();
    expect(
      screen.queryByText(PRICING_STATUS_EXPLANATIONS.not_applicable),
    ).not.toBeInTheDocument();
  });

  it("names the cause in the catalogue's words, beside the status", async () => {
    renderReceipt();

    expect(await screen.findByText("Event receipt")).toBeInTheDocument();

    expect(screen.getByText("Why")).toBeInTheDocument();
    expect(priceSectionText()).toContain(
      notApplicableReasonLabel("fixed_task_pricing"),
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

// ⚠ #603 A2: a negative calculated price is `unknown` WITH ITS REASON, and the
// reason is the whole difference from a price UBB has no input for — both
// carry no amount. The mutation that reddens these and nothing mock-authored:
// drop `pricing_status_reason` from `negativePriceUnsupported()`.
describe("a receipt whose configuration calculated a negative price", () => {
  it("names the status WITH its reason, in the catalogue's words", async () => {
    renderReceipt(NEGATIVE_PRICE_EVENT_ID);

    expect(await screen.findByText("Event receipt")).toBeInTheDocument();
    expect(priceSectionText()).toContain(
      `${pricingStatusLabel("unknown")} · ${pricingStatusReasonLabel("negative_price_unsupported")}`,
    );
  });

  it("explains it with the shared unknown sentence and then the reason's, never as missing", async () => {
    renderReceipt(NEGATIVE_PRICE_EVENT_ID);

    expect(await screen.findByText("Event receipt")).toBeInTheDocument();
    expect(
      screen.getByText(
        `${PRICING_STATUS_EXPLANATIONS.unknown} ${PRICING_STATUS_REASON_EXPLANATIONS.negative_price_unsupported}`,
      ),
    ).toBeInTheDocument();
    expect(priceSectionText()).not.toContain(UNKNOWN_PRICE_WITHOUT_A_REASON);
    expect(priceSectionText()).not.toMatch(/missing/i);
  });

  it("renders no amount — never the negative figure, never a zero — and the quantity as recorded", async () => {
    renderReceipt(NEGATIVE_PRICE_EVENT_ID);

    expect(await screen.findByText("Event receipt")).toBeInTheDocument();
    const billed = screen.getByText("Billed").closest("div");
    expect(billed?.textContent ?? "").toContain(ABSENT_LABEL);
    expect(priceSectionText()).not.toMatch(/[$£€]\s*-?[\d,]/);
    expect(screen.getByText("-3")).toBeInTheDocument();
  });
});

// #568 / #473 row 4 at the console: a held posting renders AS HELD — the name
// it waits on, no cost, no price, and never a charge of nothing. The mutation
// that reddens these and nothing mock-authored: give `heldForRemediation` a
// `waivedPrice()` where it composes `unknownPrice()`.
describe("a receipt for an event held for remediation", () => {
  it("names the undeclared Event Type as the missing input, beside an unresolved cost", async () => {
    renderReceipt(HELD_EVENT_ID);

    expect(await screen.findByText("Event receipt")).toBeInTheDocument();
    const cost = sectionText("Supplier cost");
    expect(cost).toContain(costingStatusLabel("unresolved"));
    expect(cost).toContain(unresolvedReasonLabel("event_type_not_declared"));
    expect(cost).not.toMatch(/[$£€]\s*-?[\d,]/);
  });

  it("leaves the price unknown with its stated reason — never waived, never a figure", async () => {
    renderReceipt(HELD_EVENT_ID);

    expect(await screen.findByText("Event receipt")).toBeInTheDocument();
    expect(priceSectionText()).toContain(
      `${pricingStatusLabel("unknown")} · ${pricingStatusReasonLabel("event_type_not_declared")}`,
    );
    expect(
      screen.getByText(
        `${PRICING_STATUS_EXPLANATIONS.unknown} ${PRICING_STATUS_REASON_EXPLANATIONS.event_type_not_declared}`,
      ),
    ).toBeInTheDocument();
    expect(priceSectionText()).not.toContain(pricingStatusLabel("waived"));
    expect(priceSectionText()).not.toMatch(/[$£€]\s*-?[\d,]/);
  });
});
