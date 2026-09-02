// The receipt whose subject is a Charge, rendered from a fixture THIS FILE
// builds (#425, spec §29) — the second economic state slice 5 makes reachable,
// and the one that had no composer until this commit.
//
// ⚠ WHY A SECOND FILE, AND WHY THE PROVIDER IS STUBBED. `event-detail-page.test.tsx`
// renders the events mock's charge posting, and since this commit that seed is
// composed from the same scenarios this file uses — so the mock and the page
// agree by construction, and a change to the composer moves both. The detail
// below is assembled HERE, field by field, and served through a stubbed
// provider: what it asserts is RENDERED OUTPUT for a payload the mock never
// authored. `event-receipt-price.test.tsx` is the shape, for the same reason.
//
// ⚠ THE MUTATION THAT PROVES IT IS NOT VACUOUS. In `event-detail-page.tsx`,
// stop reading `pricing_receipt_subject_type` — render the record tree for
// every receipt, as the page did before #425. The second case below goes red
// on every one of its assertions: the subject is wire-borne and typed, so the
// mock cannot hide that mutation the way it hides a narrowing. What the mock
// CAN hide is a composer drift — a `chargeReceipt` that stopped writing the
// regime, say — because the mock composes from the same function; that is why
// the record's shape is pinned in `economic-scenarios.test.ts` rather than
// here.
//
// ⚠ WHY THIS IS NOT ON THE TASKS SURFACE, THOUGH THE TICKET NAMES IT THERE.
// The run page reads `GET /tasks/{id}` and nothing else. A run carries no
// customer id and no postings; the one usage list the contract publishes is
// per customer; its row, `UsageEventOut`, carries no measurement status; and
// the projection is never accumulated into the run's own counters. There is
// no wire-borne posting for the tasks surface to render, and inventing one
// from the regime would put a payload on the page that nobody read. The one
// surface that renders a charge posting is this one, and the run page says in
// its own words what its totals leave out (`RUN_TOTALS_LEAVE_OUT_THE_CHARGE`
// in `features/tasks/lib/runs.ts`). A per-run read of postings is a contract
// change nobody owns.

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import type { ReactElement } from "react";
import { describe, expect, it, vi } from "vitest";

import { PRICING_STATUS_EXPLANATIONS, pricingStatusLabel } from "@/lib/customer-price";
import { chargeReceipt, measurementsNotApplicable } from "@/lib/economic-scenarios";
import { pricingModeLabel } from "@/lib/pricing-mode";
import { costingStatusLabel } from "@/lib/supplier-cost";

import { correlationId } from "../api/mock-data";
import type { UsageEventDetail } from "../api/types";
import { usageEventKindLabel } from "../lib/kind";
import {
  MEASUREMENTS_STATUS_EXPLANATIONS,
  NO_QUANTITIES_RECORDED,
  measurementsStatusLabel,
} from "../lib/measurements";
import {
  RECEIPT_SUBJECT_EXPLANATIONS,
  pricingReceiptSubjectTypeLabel,
} from "../lib/receipt-subject";
import { EventDetailPage } from "./event-detail-page";

const CHARGE_EVENT_ID = "4c9e2a17-8b53-4d06-a1f8-6e3b7d0c5a92";
const CHARGE_ID = "f1a6d3b8-2e74-4c19-9b05-8d2c4e6a1f37";
const LINE_ID = "7d3b9f21-5a86-4e40-b2c7-0f9e1d8a6c53";
const TASK_ID = "0e8c5a31-7f42-4b96-8d13-2a6f9c4e7b05";
const CHARGED_AT = "2026-08-30T11:31:00Z";

/**
 * One charge posting, as `charge_projection.project_the_charge` writes it.
 *
 * Hand-assembled rather than seeded, for the reason in the header. The two
 * things composed are the two economic states this slice makes reachable: the
 * measurements through slice 2's composer, and the receipt — with the subject
 * it names, the absent method and both amounts — through this commit's. What
 * is left is what a projection carries by being one: the kind, an empty Event
 * Type and provider, the Charge's own derived key, and an empty metadata bag.
 */
const CHARGE_DETAIL: UsageEventDetail = {
  id: CHARGE_EVENT_ID,
  kind: "task_charge",
  ...correlationId(CHARGE_EVENT_ID, { idempotency_key: `task:${TASK_ID}` }),
  ...chargeReceipt({
    charge_id: CHARGE_ID,
    charged_at: CHARGED_AT,
    currency: "usd",
    agreed_price_micros: 5_000_000,
    agreed_price_line_id: LINE_ID,
    book_version: 7,
  }),
  effective_at: CHARGED_AT,
  created_at: CHARGED_AT,
  currency: "usd",
  event_type: "",
  provider: "",
  grouping_fields: {},
  ...measurementsNotApplicable(),
  metadata: {},
  task_id: TASK_ID,
  stop_context: null,
};

vi.mock("../api/provider", () => ({
  eventsApi: {
    // Only what this page asks for; a stub that answered more would be a
    // second mock to keep true.
    getUsageEvent: async () => CHARGE_DETAIL,
  },
}));

function renderReceipt() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const ui: ReactElement = (
    <QueryClientProvider client={queryClient}>
      <EventDetailPage eventId={CHARGE_EVENT_ID} onBack={vi.fn()} />
    </QueryClientProvider>
  );
  return render(ui);
}

/** Everything one section of the receipt says, by the title it renders under. */
function sectionText(title: string): string {
  const section = screen.getByText(title).closest("section");
  expect(section).not.toBeNull();
  return section?.textContent ?? "";
}

describe("a receipt whose subject is a Charge", () => {
  // (a) of spec §29: the measurement state renders as ITSELF. Not as the
  // sentence for a metered posting whose record holds nothing, not as the
  // other empty-bag state — which means the detail was removed on schedule
  // and is a different fact — and with no quantity invented to fill the gap.
  it("renders as never measured: distinct from pruned, and no quantity of nothing", async () => {
    renderReceipt();
    expect(await screen.findByText("Event receipt")).toBeInTheDocument();

    const measurements = sectionText("Usage measurements");
    expect(measurements).toContain(measurementsStatusLabel("not_applicable"));
    expect(measurements).toContain(MEASUREMENTS_STATUS_EXPLANATIONS.not_applicable);
    expect(measurements).not.toContain(measurementsStatusLabel("pruned"));
    expect(measurements).not.toContain(NO_QUANTITIES_RECORDED);
    expect(measurements).not.toMatch(/\d/);

    // And the page says what kind of row this is, in the catalogue's words —
    // the one thing that identifies a posting no caller reported.
    expect(sectionText("Details")).toContain(usageEventKindLabel("task_charge"));
    expect(screen.queryByText("Event type")).not.toBeInTheDocument();
  });

  // (b) of spec §29: the receipt EXPLAINS the agreed price rather than
  // showing a record with nothing in it. Every row here is wire-borne — the
  // subject the payload states, the posting's own settled price, the regime
  // the record carries by value, and the three identifiers the record holds —
  // and the sentence says the emptiness is not a gap.
  it("explains the agreed price, and says nothing is missing", async () => {
    renderReceipt();
    expect(await screen.findByText("Event receipt")).toBeInTheDocument();

    const receipt = sectionText("Pricing receipt");
    expect(receipt).toContain(RECEIPT_SUBJECT_EXPLANATIONS.charge);
    expect(receipt).not.toContain(RECEIPT_SUBJECT_EXPLANATIONS.usage_event);

    expect(receipt).toContain("Explains");
    expect(receipt).toContain(pricingReceiptSubjectTypeLabel("charge"));
    expect(receipt).toContain("Agreed price");
    expect(receipt).toContain("$5.00");
    expect(receipt).toContain("Sold as");
    expect(receipt).toContain(pricingModeLabel("fixed"));
    expect(receipt).toContain(CHARGE_ID);
    expect(receipt).toContain(LINE_ID);
    expect(receipt).toContain("Book version");
    expect(receipt).toContain("7");

    // The record itself is still shown under the explanation — it is the
    // record — and it names the Charge as its subject, not this posting.
    expect(receipt).toContain("subject_type");
    expect(receipt).not.toContain(CHARGE_EVENT_ID);
  });

  // The charge posting reads through every existing price and cost path
  // without a special case: the price is settled at the agreed amount and
  // never `$0.00`; the supplier cost is a settled NOTHING — a real zero, from
  // a `known` status, because no supplier stands behind a Charge — and no
  // method is named on either side, because neither amount was derived.
  it("carries a settled price and a settled cost of nothing, with no method", async () => {
    renderReceipt();
    expect(await screen.findByText("Event receipt")).toBeInTheDocument();

    const price = sectionText("Customer price");
    expect(price).toContain("$5.00");
    expect(price).not.toContain("$0.00");
    expect(price).toContain(pricingStatusLabel("known"));
    expect(price).toContain(PRICING_STATUS_EXPLANATIONS.known);
    expect(screen.queryByText("Priced by")).not.toBeInTheDocument();
    expect(screen.queryByText("Why")).not.toBeInTheDocument();

    const cost = sectionText("Supplier cost");
    expect(cost).toContain("$0.00");
    expect(cost).toContain(costingStatusLabel("known"));
    expect(screen.queryByText("Missing input")).not.toBeInTheDocument();
  });
});
