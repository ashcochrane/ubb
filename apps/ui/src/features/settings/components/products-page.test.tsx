import { fireEvent, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { renderWithQuery } from "../test-utils";
import { ProductsPage } from "./products-page";

// The three products the contract enumerates, spelled out here rather than
// read from the module the page renders from. Two reasons, and both are rules
// this repo already holds: a loop over `PRODUCTS` compares the page against
// its own source, so it could only fail if rendering broke wholesale; and
// importing `@/lib/labels` into a new file grows the legacy adapter's importer
// ratchet, which may only shrink.
const EXPECTED_PRODUCTS = [
  ["Metering", /Usage events, pricing, analytics/],
  ["Billing", /Wallets, credit grants, budgets/],
  ["Referrals", /Referral programs, attribution/],
] as const;

describe("ProductsPage", () => {
  it("shows the current billing mode and every product with its description", async () => {
    renderWithQuery(<ProductsPage />);

    expect(await screen.findByText("Billing mode")).toBeInTheDocument();
    expect(screen.getByText("Current")).toBeInTheDocument();
    expect(screen.getByText("Prepaid credits")).toBeInTheDocument();

    // Exhaustive over the declared products rather than naming one of them.
    // The predecessor pinned "Async ingestion" and its endpoint, and both
    // outlived the product: it named the row instead of the rule, so it went
    // on asserting the page rendered something the contract had deleted.
    for (const [label, description] of EXPECTED_PRODUCTS) {
      expect(screen.getByRole("switch", { name: label })).toBeInTheDocument();
      expect(screen.getByText(description)).toBeInTheDocument();
    }

    // Prerequisites panel
    expect(screen.getByText("Prerequisites")).toBeInTheDocument();
    expect(screen.getByText("Stripe account")).toBeInTheDocument();
  });

  it("keeps metering always-on and locks billing while the mode needs it", async () => {
    renderWithQuery(<ProductsPage />);
    await screen.findByText("Billing mode");

    expect(screen.getByRole("switch", { name: "Metering" })).toHaveAttribute(
      "aria-disabled",
      "true",
    );
    expect(
      screen.getByText(/the platform core can't be disabled/i),
    ).toBeInTheDocument();

    // Mock tenant is prepaid → billing is locked by the mode.
    expect(screen.getByRole("switch", { name: "Billing" })).toHaveAttribute(
      "aria-disabled",
      "true",
    );
    expect(
      screen.getByText(/switch to Meter only first/i),
    ).toBeInTheDocument();
  });

  it("disables a product through the confirm dialog", async () => {
    renderWithQuery(<ProductsPage />);
    await screen.findByText("Billing mode");

    const referralsSwitch = screen.getByRole("switch", { name: "Referrals" });
    expect(referralsSwitch).toBeChecked();
    fireEvent.click(referralsSwitch);

    expect(await screen.findByText("Disable Referrals?")).toBeInTheDocument();
    expect(
      screen.getByText(/console sections disappear for everyone/),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Disable" }));

    await waitFor(() =>
      expect(
        screen.getByRole("switch", { name: "Referrals" }),
      ).not.toBeChecked(),
    );
  });
});
