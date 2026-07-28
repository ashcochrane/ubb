import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
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

describe("GeneralTab submit payload (4d follow-up: hidden fields must not be resubmitted)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    updateMutate.mockResolvedValue(undefined);
  });

  it("omits min_balance_micros/soft_min_balance_micros from the PATCH payload under postpaid", async () => {
    // Stored floors from before the tenant switched to postpaid (or typed in
    // this session before flipping the mode) — hidden from the form, but
    // still sitting in react-hook-form state (shouldUnregister defaults to
    // false). The payload must not resubmit them.
    render(
      React.createElement(GeneralTab, {
        config: config({
          billing_mode: "postpaid",
          min_balance_micros: 500_000_000,
          soft_min_balance_micros: 100_000_000,
        }),
      }),
    );
    expect(screen.queryByLabelText(/^minimum balance/i)).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /save changes/i }));

    await waitFor(() => expect(updateMutate).toHaveBeenCalled());
    const payload = updateMutate.mock.calls[0]?.[0] as Record<string, unknown>;
    expect(payload).not.toHaveProperty("min_balance_micros");
    expect(payload).not.toHaveProperty("soft_min_balance_micros");
  });

  it("still includes the floors in the payload under prepaid", async () => {
    render(
      React.createElement(GeneralTab, {
        config: config({
          billing_mode: "prepaid",
          min_balance_micros: 5_000_000,
          soft_min_balance_micros: 1_000_000,
        }),
      }),
    );

    fireEvent.click(screen.getByRole("button", { name: /save changes/i }));

    await waitFor(() => expect(updateMutate).toHaveBeenCalled());
    const payload = updateMutate.mock.calls[0]?.[0] as Record<string, unknown>;
    expect(payload).toHaveProperty("min_balance_micros", 5_000_000);
    expect(payload).toHaveProperty("soft_min_balance_micros", 1_000_000);
  });
});
