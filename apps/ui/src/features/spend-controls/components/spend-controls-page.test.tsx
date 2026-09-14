// The Spend controls tab (#466, #467; slice 6 §18 Q6): reports across every
// family, configures nothing, shows the workspace's enforcement posture
// through the map spec §18 keeps for slice 8, hosts its two reports under
// one URL-backed choice, and hands its URL-backed filters to each — proved
// by the sentence the family filter's empty answer renders, and by the rows
// the customer filter leaves.

import { fireEvent, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { readMockTenantConfig, writeMockTenantConfig } from "@/hooks/use-tenant-config";
import { POOL_PAIR_TITLE } from "@/lib/spend-pool";

import { CUSTOMER_ACME, CUSTOMER_LUNA } from "../api/mock-data";
import { NO_EPISODES_FOR } from "../lib/families";
import type { SpendControlsSearch } from "../lib/search";
import { renderWithProviders } from "../test-utils";
import { CONFIGURES_NOTHING, SpendControlsPage } from "./spend-controls-page";
import { STOPS_AND_BREACHES_TITLE } from "./stops-and-breaches";
import { UTILISATION_AND_HEADROOM_TITLE } from "./utilisation-and-headroom";

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

describe("SpendControlsPage — the two reports (#467)", () => {
  it("offers both reports and hosts Stops and breaches by default", async () => {
    renderTab();

    const tabs = (await screen.findAllByRole("tab")).map((tab) => tab.textContent);
    expect(tabs).toEqual([STOPS_AND_BREACHES_TITLE, UTILISATION_AND_HEADROOM_TITLE]);
    expect(await screen.findByRole("region", { name: STOPS_AND_BREACHES_TITLE })).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: UTILISATION_AND_HEADROOM_TITLE })).not.toBeInTheDocument();
  });

  // The utilisation report is the Ceiling's alone, so the family filter has
  // nothing to narrow there and is not offered; the customer filter and the
  // window reach both reports.
  it("hosts Utilisation and headroom when the URL names it, with the customer filter and no family filter", async () => {
    renderTab({ report: "utilisation", customer_id: CUSTOMER_ACME });

    expect(await screen.findByRole("region", { name: UTILISATION_AND_HEADROOM_TITLE })).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: STOPS_AND_BREACHES_TITLE })).not.toBeInTheDocument();
    expect(await screen.findByLabelText("Customer")).toBeInTheDocument();
    expect(screen.queryByLabelText("Family")).not.toBeInTheDocument();
    // The customer filter reached the read: the named customer's pool pair
    // is on the page, and only that customer's work.
    expect(await screen.findByRole("region", { name: POOL_PAIR_TITLE })).toBeInTheDocument();
    await screen.findByRole("table");
    const customers = [...document.querySelectorAll<HTMLElement>("tr[data-unit]")].map(
      (row) => row.querySelector('[data-cell="customer"] a')?.getAttribute("href"),
    );
    expect(customers.length).toBeGreaterThan(0);
    expect(customers.every((href) => href === `/customers/${CUSTOMER_ACME}`)).toBe(true);
  });

  // The absence the report's own test asserts, asserted again on the PAGE —
  // the posture card, the nav and the filters are on it too, and #467's
  // criterion is that nothing on the page reads as a warning state.
  it("puts no threshold, no amber and no warning affordance on the page around the report", async () => {
    renderTab({ report: "utilisation", customer_id: CUSTOMER_ACME });
    await screen.findByRole("region", { name: POOL_PAIR_TITLE });
    await screen.findByRole("table");

    for (const role of ["meter", "progressbar", "alert", "status", "alertdialog"]) {
      expect(screen.queryAllByRole(role)).toEqual([]);
    }
    expect(document.body.textContent).not.toMatch(/warning|amber|threshold/i);
  });

  it("switches to the second report through the URL", async () => {
    const onSearchChange = renderTab();
    await screen.findByRole("region", { name: STOPS_AND_BREACHES_TITLE });

    fireEvent.click(screen.getByRole("tab", { name: UTILISATION_AND_HEADROOM_TITLE }));
    expect(onSearchChange).toHaveBeenLastCalledWith(
      expect.objectContaining({ report: "utilisation" }),
    );
  });

  it("switches back to the first report by leaving it out of the URL", async () => {
    const onSearchChange = renderTab({ report: "utilisation" });
    await screen.findByRole("region", { name: UTILISATION_AND_HEADROOM_TITLE });

    fireEvent.click(screen.getByRole("tab", { name: STOPS_AND_BREACHES_TITLE }));
    expect(onSearchChange).toHaveBeenLastCalledWith(expect.objectContaining({ report: undefined }));
  });
});
