// The Spend controls tab (#466; slice 6 §18 Q6): reports across every family,
// configures nothing, shows the workspace's enforcement posture through the
// map spec §18 keeps for slice 8, and hands its URL-backed filters to Stops
// and breaches — proved by the sentence the family filter's empty answer
// renders, and by the rows the customer filter leaves.

import { screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { readMockTenantConfig, writeMockTenantConfig } from "@/hooks/use-tenant-config";

import { CUSTOMER_LUNA } from "../api/mock-data";
import { NO_EPISODES_FOR } from "../lib/families";
import type { SpendControlsSearch } from "../lib/search";
import { renderWithProviders } from "../test-utils";
import { CONFIGURES_NOTHING, SpendControlsPage } from "./spend-controls-page";
import { STOPS_AND_BREACHES_TITLE } from "./stops-and-breaches";

function renderTab(search: SpendControlsSearch = {}) {
  const onSearchChange = vi.fn();
  renderWithProviders(<SpendControlsPage search={search} onSearchChange={onSearchChange} />);
  return onSearchChange;
}

describe("SpendControlsPage", () => {
  it("hosts Stops and breaches, both filters and the date window, and configures nothing", async () => {
    renderTab();

    expect(await screen.findByRole("region", { name: STOPS_AND_BREACHES_TITLE })).toBeInTheDocument();
    expect(screen.getByText(CONFIGURES_NOTHING)).toBeInTheDocument();
    expect(await screen.findByLabelText("Customer")).toBeInTheDocument();
    expect(screen.getByLabelText("Family")).toBeInTheDocument();
    // Nothing on this tab writes a control: no form, no switch.
    expect(screen.queryByRole("switch")).not.toBeInTheDocument();
    expect(screen.queryByRole("form")).not.toBeInTheDocument();
  });

  // The posture's word is the legacy map's, by spec §18's ruling: the words
  // are spelled here rather than asked of the map, so a re-wording under
  // slice 8 fails this test on purpose.
  it("shows the workspace's enforcement posture through its existing map", async () => {
    const before = readMockTenantConfig();
    try {
      writeMockTenantConfig({ ...before, enforcement_mode: "enforcing" });
      renderTab();
      const posture = await screen.findByText("Enforcing");
      expect(posture).toHaveAttribute("data-posture", "enforcing");
    } finally {
      writeMockTenantConfig(before);
    }
  });

  it("hands the family filter to the report — admission control answers its own empty sentence", async () => {
    renderTab({ control_family: "admission_control" });

    expect(await screen.findByText(NO_EPISODES_FOR.admission_control)).toBeInTheDocument();
    expect(screen.queryAllByRole("article")).toEqual([]);
  });

  it("hands the customer filter to the report", async () => {
    renderTab({ customer_id: CUSTOMER_LUNA });

    await screen.findByText(/Episodes that opened between/);
    const rows = screen.getAllByRole("article");
    expect(rows.length).toBeGreaterThan(0);
    expect(rows.every((article) => article.dataset.shape === "wallet_policy")).toBe(true);
  });
});
