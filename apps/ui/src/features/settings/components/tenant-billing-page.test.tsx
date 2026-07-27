import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { renderWithQuery } from "../test-utils";
import { TenantBillingPage } from "./tenant-billing-page";

describe("TenantBillingPage", () => {
  it("labels the page as UBB's charges to the workspace, not customer invoices", async () => {
    renderWithQuery(<TenantBillingPage />);
    expect(
      screen.getByText(/what UBB charges your workspace/),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/not what your customers owe you/),
    ).toBeInTheDocument();
    expect(await screen.findByText("Billing periods")).toBeInTheDocument();
    expect(screen.getByText("Invoices from UBB")).toBeInTheDocument();
  });

  it("renders billing periods with status labels, money, and event counts", async () => {
    renderWithQuery(<TenantBillingPage />);
    // June platform fee (92_130_000 micros → $92.13) — period row + invoice row.
    const fees = await screen.findAllByText("$92.13");
    expect(fees.length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("Open")).toBeInTheDocument();
    expect(screen.getAllByText("Invoiced").length).toBe(2);
    expect(screen.getByText("1.20M")).toBeInTheDocument();
    expect(screen.getByText("$1,842.55")).toBeInTheDocument();
  });

  it("renders invoices with the Stripe id in mono (or a dash when absent)", async () => {
    renderWithQuery(<TenantBillingPage />);
    expect(await screen.findByText("in_1PXmc2Acme0601")).toBeInTheDocument();
    expect(screen.getByText("Finalized")).toBeInTheDocument();
    expect(screen.getByText("Draft")).toBeInTheDocument();
    // The draft invoice has no Stripe id yet.
    expect(screen.getAllByText("—").length).toBeGreaterThanOrEqual(1);
  });
});
