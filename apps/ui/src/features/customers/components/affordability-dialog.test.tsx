// The affordability dialog renders the refusal word through the console's one
// open-set helper (#463; slice 6 §18; Testing Decisions claim 15): a value the
// registry knows renders in the catalogue's words, unmarked; a value it has
// never seen renders as the token it is, marked unrecognised, never humanised
// into words UBB did not say. The provider is stubbed so the answer is
// assembled here — the feature mock only ever answers the wallet's word, and
// a fixture the mock authors cannot show the unfamiliar branch at all.

import { fireEvent, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { UNRECOGNISED_MARK } from "@/components/shared/open-set-value";
import { AFFORDABILITY_REASON_KNOWN_VALUES } from "@/lib/vocabulary";

import type { AffordabilityResponse } from "../api/types";
import { renderWithProviders } from "../test-utils";
import { AffordabilityDialog } from "./adjust-dialogs";

/** A refusal no registry entry names — a control UBB has not met, or not yet. */
const UNRECOGNISED = "a_control_from_next_year";

const state = vi.hoisted(() => ({
  answer: null as unknown,
}));

vi.mock("../api/provider", () => ({
  customersApi: {
    affordability: async () => state.answer,
  },
}));

function denied(reason: string): AffordabilityResponse {
  return {
    allowed: false,
    reason,
    balance_micros: -6_000_000,
    available_micros: -6_000_000,
    min_balance_micros: 5_000_000,
    soft_min_balance_micros: 2_000_000,
  };
}

async function ask(answer: AffordabilityResponse) {
  state.answer = answer;
  renderWithProviders(
    <AffordabilityDialog customerId="c1" open onOpenChange={vi.fn()} />,
  );
  fireEvent.click(await screen.findByRole("button", { name: "Ask" }));
  return screen.findByTestId("affordability-reason");
}

describe("the affordability dialog's refusal word", () => {
  it("renders a value the registry knows in the catalogue's words, unmarked", async () => {
    // Vacuity guard on the generated list; not pinned to a count — the
    // concept is open, so a tenth registry value is not a rendering defect.
    expect(AFFORDABILITY_REASON_KNOWN_VALUES.length).toBeGreaterThan(0);
    const known = AFFORDABILITY_REASON_KNOWN_VALUES[0];

    const reason = await ask(denied(known));

    const rendered = reason.querySelector("[data-label]");
    expect(rendered).toHaveAttribute("data-label", "labelled");
    expect(rendered?.textContent?.trim()).not.toBe("");
    expect(rendered?.textContent).not.toBe(known);
    expect(reason).not.toHaveTextContent(UNRECOGNISED_MARK);
    // The money beside the verdict, floors in the wallet's orientation.
    expect(screen.getByText(/Available after reservations/)).toBeInTheDocument();
    expect(screen.getByText(/Hard floor: -\$5\.00 · soft floor: -\$2\.00/)).toBeInTheDocument();
  });

  it("renders a value the registry has never seen as the token, marked, never humanised", async () => {
    const reason = await ask(denied(UNRECOGNISED));

    const rendered = reason.querySelector("[data-label]");
    expect(rendered).toHaveAttribute("data-label", "unfamiliar");
    expect(reason).toHaveTextContent(UNRECOGNISED);
    expect(reason).toHaveTextContent(UNRECOGNISED_MARK);
    expect(reason).not.toHaveTextContent("A control from next year");
  });
});
