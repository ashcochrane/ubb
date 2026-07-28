import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import React from "react";
import type { TenantConfig } from "../api/types";

const updateMutate = vi.fn();

vi.mock("../api/queries", () => ({
  useUpdateConfig: () => ({ mutateAsync: updateMutate, isPending: false }),
}));

import { GeneralTab } from "./general-tab";

function config(overrides: Partial<TenantConfig> = {}): TenantConfig {
  return {
    name: "Acme",
    is_active: true,
    products: [],
    stripe_connected_account_id: "",
    billing_mode: "prepaid",
    default_currency: "USD",
    enforcement_mode: "off",
    min_balance_micros: 0,
    soft_min_balance_micros: null,
    default_task_provider_cost_limit_micros: null,
    require_cost_card_coverage: false,
    automatic_tax_enabled: false,
    arrival_signals_enabled: true,
    ...overrides,
  };
}

describe("GeneralTab enforcement_mode select", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("offers exactly the two real values — off and enforcing, no invented 'monitor'/'enforce'", async () => {
    render(React.createElement(GeneralTab, { config: config({ enforcement_mode: "off" }) }));
    fireEvent.click(screen.getByLabelText(/enforcement mode/i));
    const options = await screen.findAllByRole("option");
    const labels = options.map((o) => o.textContent);
    expect(labels).toEqual(["Off", "Enforcing"]);
    expect(labels).not.toContain("Monitor");
    expect(labels).not.toContain("Enforce");
  });

  it("reflects a valid enforcing value from the server", () => {
    render(React.createElement(GeneralTab, { config: config({ enforcement_mode: "enforcing" }) }));
    expect(screen.getByLabelText(/enforcement mode/i)).toHaveTextContent("enforcing");
  });

  it("falls back to off for a stale/unknown enforcement_mode value (e.g. the old 'monitor'/'enforce')", () => {
    render(React.createElement(GeneralTab, { config: config({ enforcement_mode: "monitor" }) }));
    expect(screen.getByLabelText(/enforcement mode/i)).not.toHaveTextContent("monitor");
    expect(screen.getByLabelText(/enforcement mode/i)).toHaveTextContent("off");
  });
});

describe("GeneralTab tenant-default wallet floors (4d)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows the editable minimum-balance floors for prepaid", () => {
    render(React.createElement(GeneralTab, { config: config({ billing_mode: "prepaid" }) }));
    expect(screen.getByLabelText(/^minimum balance/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/soft minimum balance/i)).toBeInTheDocument();
    expect(screen.queryByText(/wallet floors not used under postpaid/i)).not.toBeInTheDocument();
  });

  it("hides the minimum-balance floors and explains why for postpaid — the 4d gap this fixes", () => {
    render(React.createElement(GeneralTab, { config: config({ billing_mode: "postpaid" }) }));
    expect(screen.queryByLabelText(/^minimum balance/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/soft minimum balance/i)).not.toBeInTheDocument();
    expect(screen.getByText(/wallet floors not used under postpaid/i)).toBeInTheDocument();
    // The provider-cost limit is unrelated to the wallet floor and stays visible.
    expect(screen.getByLabelText(/provider-cost limit/i)).toBeInTheDocument();
  });
});
