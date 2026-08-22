// The recorded response's money row, for prices UBB did not settle (#371).
//
// The sandbox recorder always resolves a price, so this feature's mock always
// answers `known` — and it should, because that is what the sandbox does. The
// states that need proving here are the three it cannot produce, so the card is
// rendered DIRECTLY with a response this file assembles.
//
// That is the same reasoning as `features/events/components/event-receipt-price.test.tsx`
// and spec §25's rule behind it: a rendering test cannot see a narrowing defect
// where the mock returns its own fixture object. It is also the only way to
// reach these states at all here — driving the console UI would go through the
// mock, which by design has no branch that fails to price.
//
// ⚠ WHY THIS SURFACE OWES THE ASSERTION SEPARATELY FROM THE RECEIPT. This card
// is what an integrator reads to learn what UBB recorded, and it is a compact
// stat grid rather than a detail list — there is no room for a status row
// beside the amount, so the status goes IN the cell. #330 made the supplier
// cost do exactly that and left the customer price falling back to a bare dash;
// three of the four price statuses null that column and they do not mean the
// same thing, so the dash was the ambiguity the cost half had already fixed.

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import {
  notApplicableReasonLabel,
  pricingStatusLabel,
} from "@/lib/customer-price";
import {
  knownCost,
  knownPrice,
  priceNotApplicable,
  unknownPrice,
  waivedPrice,
  type CustomerPriceScenario,
} from "@/lib/economic-scenarios";

import type { RecordUsageResponse } from "../api/types";
import { TestEventResponseCard, type TestEventEntry } from "./test-event-response";

/**
 * One recorded response, with its price composed and everything else ordinary.
 *
 * Only the price varies, so a failure below can only be about the price.
 */
function entryWith(price: CustomerPriceScenario): TestEventEntry {
  const response: RecordUsageResponse = {
    event_id: "b1c2d3e4-5f60-4718-a92b-3c4d5e6f7081",
    suspended: false,
    grouping_fields: {},
    ...price,
    ...knownCost(61_000),
    new_balance_micros: 4_000_000,
    measurements: { input_tokens: 900 },
    uncosted_measurement_keys: [],
    pricing_receipt: {},
    stop: false,
    stop_reason: null,
    stop_scope: null,
    stop_context: null,
    task_id: null,
    parent_task_id: null,
  };
  return { id: "entry-1", at: "2026-07-22T10:00:00Z", eventType: "chat.completion", response };
}

function priceStat(): string {
  const stat = screen.getByText("Billed cost").closest("div");
  expect(stat).not.toBeNull();
  return stat?.textContent ?? "";
}

describe("TestEventResponseCard — the customer price", () => {
  it("renders a settled price as the figure it is", () => {
    render(<TestEventResponseCard entry={entryWith(knownPrice(187_500))} currency="usd" />);

    expect(priceStat()).toContain("$0.1875");
  });

  // A real, resolved zero stays readable as one — the case the supplier half's
  // test already protects, asserted here so naming the absences cannot take it
  // away. `known` at zero means UBB priced this event at nothing on purpose.
  it("keeps a resolved zero as a zero", () => {
    render(<TestEventResponseCard entry={entryWith(knownPrice(0))} currency="usd" />);

    expect(priceStat()).toContain("$0.00");
  });

  // ⚠ THE ASSERTION THIS FILE EXISTS FOR. All three null the same column, and
  // a bare dash — what shipped before #371 — cannot tell them apart.
  it.each([
    ["unknown", unknownPrice()],
    ["waived", waivedPrice()],
    ["not_applicable", priceNotApplicable("tenant_not_billing")],
  ] as const)("names a %s price in the cell, never zeroes it", (status, price) => {
    render(<TestEventResponseCard entry={entryWith(price)} currency="usd" />);

    expect(priceStat()).toContain(pricingStatusLabel(status));
    expect(priceStat()).not.toContain("$0.00");
    expect(priceStat()).not.toMatch(/[$£€]\s*-?[\d,]/);
  });

  it("names the cause where the status has one", () => {
    render(
      <TestEventResponseCard
        entry={entryWith(priceNotApplicable("tenant_not_billing"))}
        currency="usd"
      />,
    );

    expect(screen.getByText("Why")).toBeInTheDocument();
    expect(
      screen.getByText(notApplicableReasonLabel("tenant_not_billing")),
    ).toBeInTheDocument();
    expect(
      screen.queryByText(notApplicableReasonLabel("fixed_task_pricing")),
    ).not.toBeInTheDocument();
  });

  it("asks WHY only where the status has a cause to give", () => {
    render(<TestEventResponseCard entry={entryWith(waivedPrice())} currency="usd" />);

    expect(screen.queryByText("Why")).not.toBeInTheDocument();
  });
});
