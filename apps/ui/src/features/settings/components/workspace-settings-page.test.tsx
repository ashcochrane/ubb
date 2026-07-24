import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { renderWithQuery } from "../test-utils";
import { WorkspaceSettingsPage } from "./workspace-settings-page";

describe("WorkspaceSettingsPage", () => {
  it("renders the workspace config from mock data", async () => {
    renderWithQuery(<WorkspaceSettingsPage />);

    // Workspace card
    expect(await screen.findByText("Acme AI")).toBeInTheDocument();
    expect(screen.getByText("USD — US Dollar")).toBeInTheDocument();
    expect(screen.getByText("Active")).toBeInTheDocument();

    // Spend control card with explanatory copy
    expect(screen.getByText("Spend control")).toBeInTheDocument();
    expect(
      screen.getByText(/UBB refuses new work for customers past their limits/),
    ).toBeInTheDocument();
    expect(screen.getByRole("switch", { name: "Enforcement" })).toBeChecked();

    // Allowed-overdraft copy reflects the inversion (not a reserve floor)
    expect(
      screen.getByText(/allowed overdraft, not a reserve/i),
    ).toBeInTheDocument();
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
});
