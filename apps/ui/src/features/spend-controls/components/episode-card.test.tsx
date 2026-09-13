// One episode card, over rows the mock does not author: the stop word renders
// through the console's one open-set helper (#466; slice 6 §18; Testing
// Decisions claim 15) — a registry value in the catalogue's words, unmarked; a
// value the registry has never seen as the token it is, marked unrecognised,
// never humanised — and a balance no suspension announced renders as unknown,
// never as money.

import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { UNRECOGNISED_MARK } from "@/components/shared/open-set-value";
import { knownCost, knownPrice } from "@/lib/economic-scenarios";
import { UNKNOWN_TOTAL } from "@/lib/total-reading";
import { REASON_CODE_KNOWN_VALUES } from "@/lib/vocabulary";

import { CUSTOMER_LUNA, itemised } from "../api/mock-data";
import type { WalletPolicyEpisodeRow } from "../api/types";
import { BALANCE_UNANNOUNCED } from "../lib/episodes";
import { renderWithProviders } from "../test-utils";
import { EpisodeCard } from "./episode-card";

/** A stop word no registry entry names — a control UBB has not met, or not yet. */
const UNRECOGNISED_STOP = "a_stop_from_next_year";

function floorRow(reason: string): WalletPolicyEpisodeRow {
  return {
    control_family: "wallet_policy",
    control_id: "floor-luna",
    reason_code: reason,
    soft_floor: false,
    customer_id: CUSTOMER_LUNA,
    episode_seq: 4,
    floor_micros: -5_000_000,
    // The stop pair carries no balance and no suspension was announced
    // beside it — the wire says null, and null is unknown.
    balance_at_crossing_micros: null,
    opened_at: "2026-08-02T09:14:00Z",
    closed_at: null,
    itemised: itemised([
      {
        event_id: "1a2b3c4d-0000-4000-8000-000000000401",
        customer_id: CUSTOMER_LUNA,
        effective_at: "2026-08-02T09:14:00Z",
        billed_cost_micros: knownPrice(1_000_000).billed_cost_micros,
        pricing_status: knownPrice(1_000_000).pricing_status,
        provider_cost_micros: knownCost(800_000).provider_cost_micros,
        costing_status: knownCost(800_000).costing_status,
        charge_id: null,
        arrived_after: false,
      },
    ]),
  };
}

describe("EpisodeCard — the stop word", () => {
  it("renders a value the registry knows in the catalogue's words, unmarked", async () => {
    expect(REASON_CODE_KNOWN_VALUES.length).toBeGreaterThan(0);
    const known = REASON_CODE_KNOWN_VALUES[0];
    renderWithProviders(<EpisodeCard row={floorRow(known)} currency="usd" />);

    const header = (await screen.findByRole("article")).querySelector("[data-label]");
    expect(header).toHaveAttribute("data-label", "labelled");
    expect(header?.textContent?.trim()).not.toBe("");
    expect(header?.textContent).not.toBe(known);
    expect(screen.queryByText(UNRECOGNISED_MARK)).not.toBeInTheDocument();
  });

  it("renders a value the registry has never seen as the token, marked, never humanised", async () => {
    renderWithProviders(<EpisodeCard row={floorRow(UNRECOGNISED_STOP)} currency="usd" />);

    const header = (await screen.findByRole("article")).querySelector("[data-label]");
    expect(header).toHaveAttribute("data-label", "unfamiliar");
    expect(header).toHaveTextContent(UNRECOGNISED_STOP);
    expect(header).toHaveTextContent(UNRECOGNISED_MARK);
    expect(document.body).not.toHaveTextContent("A stop from next year");
  });
});

describe("EpisodeCard — money the wire left null", () => {
  it("renders an unannounced balance as unknown, never as a currency figure", async () => {
    renderWithProviders(<EpisodeCard row={floorRow("hard_floor")} currency="usd" />);

    const value = (await screen.findByText("Balance at crossing")).parentElement?.querySelector("dd");
    const reading = value?.querySelector("[data-reading]");
    expect(reading).toHaveAttribute("data-reading", "unknown");
    expect(reading).toHaveTextContent(UNKNOWN_TOTAL);
    expect(reading).toHaveAttribute("title", BALANCE_UNANNOUNCED);
    expect(value?.textContent).not.toMatch(/[$£€]\s*-?[\d,]/);
    // An open episode says so rather than inventing a close.
    expect(screen.getByText("Episode 4").parentElement).toHaveTextContent("still open");
  });
});
