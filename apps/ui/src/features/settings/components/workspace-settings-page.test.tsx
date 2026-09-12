import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { readMockTenantConfig, writeMockTenantConfig } from "@/hooks/use-tenant-config";

import { renderWithQuery } from "../test-utils";
import { WorkspaceSettingsPage } from "./workspace-settings-page";

describe("WorkspaceSettingsPage", () => {
  it("renders the workspace config from mock data", async () => {
    renderWithQuery(<WorkspaceSettingsPage />);

    // Workspace card
    expect(await screen.findByText("Acme AI")).toBeInTheDocument();
    expect(screen.getByText("USD — US Dollar")).toBeInTheDocument();
    expect(screen.getByText("Active")).toBeInTheDocument();

    // Spend control card with explanatory copy — the position the wire
    // spells `off` is "no customer-wide enforcement" (#462, slice 6 §10),
    // honest about what stays (suspension, every declared ceiling) and what
    // goes (the customer-wide signal suite).
    expect(screen.getByText("Spend control")).toBeInTheDocument();
    expect(
      screen.getByText(/No customer-wide enforcement: none of those signals fire/),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/still suspended and refused new work/),
    ).toBeInTheDocument();
    expect(screen.getByRole("switch", { name: "Enforcement" })).toBeChecked();
    // Admission control's one setting lives on this card (#462).
    expect(screen.getByLabelText(/New work per minute/)).toHaveValue(60);

    // Allowed-overdraft copy reflects the inversion (not a reserve floor)
    expect(
      screen.getByText(/allowed overdraft, not a reserve/i),
    ).toBeInTheDocument();

    // Wind-down floor copy matches the wire sign convention
    expect(
      screen.getByText(/How far into the allowed overdraft/),
    ).toBeInTheDocument();

    // Margin-alert configuration card is present on the workspace tab
    expect(await screen.findByText("Margin alerts")).toBeInTheDocument();
  });

  it("shows the Stripe Connect card for a billing tenant", async () => {
    renderWithQuery(<WorkspaceSettingsPage />);
    expect(await screen.findByText("Stripe")).toBeInTheDocument();
    expect(
      await screen.findByText("Ready to charge customers"),
    ).toBeInTheDocument();
    expect(await screen.findByText("acct_mock123")).toBeInTheDocument();
  });

  it("shows the failure banner when returning from Stripe with ?connected=false", async () => {
    renderWithQuery(<WorkspaceSettingsPage connected="false" />);
    expect(
      await screen.findByText("Stripe connection didn't complete"),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/canceled or failed on Stripe's side/),
    ).toBeInTheDocument();
  });

  it("hides the tenant-default wallet floors under postpaid, with an explanation", async () => {
    const original = readMockTenantConfig();
    writeMockTenantConfig({ ...original, billing_mode: "postpaid" });
    try {
      renderWithQuery(<WorkspaceSettingsPage />);
      expect(
        await screen.findByText(
          /allowed-overdraft and wind-down floors aren't used under postpaid/i,
        ),
      ).toBeInTheDocument();
      expect(screen.queryByLabelText(/Allowed overdraft/)).not.toBeInTheDocument();
      expect(screen.queryByLabelText(/Wind-down floor/)).not.toBeInTheDocument();
      // The default ceilings for work with no declared kind LEFT this page
      // (#453): a ceiling is a kernel setting, edited on the Tasks page beside
      // the declared kinds of work. Under postpaid nothing is left to edit.
      expect(screen.queryByLabelText(/Default task spend limit/)).not.toBeInTheDocument();
      expect(screen.queryByLabelText(/ceiling/i)).not.toBeInTheDocument();
    } finally {
      writeMockTenantConfig(original);
    }
  });

  it("shows the tenant-default wallet floors under prepaid", async () => {
    renderWithQuery(<WorkspaceSettingsPage />);
    expect(
      await screen.findByLabelText(/Allowed overdraft/),
    ).toBeInTheDocument();
    expect(screen.getByLabelText(/Wind-down floor/)).toBeInTheDocument();
  });
});
