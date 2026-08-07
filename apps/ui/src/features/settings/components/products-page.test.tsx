import { fireEvent, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { PRODUCTS, productDescription, productLabel } from "@/lib/labels";

import { renderWithQuery } from "../test-utils";
import { ProductsPage } from "./products-page";

describe("ProductsPage", () => {
  it("shows the current billing mode and every product with its description", async () => {
    renderWithQuery(<ProductsPage />);

    expect(await screen.findByText("Billing mode")).toBeInTheDocument();
    expect(screen.getByText("Current")).toBeInTheDocument();
    expect(screen.getByText("Prepaid credits")).toBeInTheDocument();

    // Exhaustive over the declared products rather than naming one of them.
    // The predecessor pinned "Async ingestion" and its endpoint, and both
    // outlived the product: the test named the row instead of the rule, so it
    // asserted the page still rendered something the contract had deleted.
    //
    // The card maps `PRODUCTS` too, so this pins that every product gets a
    // switch AND a description — not that the SET is right. Nothing here can
    // check that yet: `PRODUCTS` is still the console's own literal. It
    // becomes checkable when the console binds to the generated vocabulary.
    for (const product of PRODUCTS) {
      expect(
        screen.getByRole("switch", { name: productLabel(product) }),
      ).toBeInTheDocument();
      expect(
        screen.getByText(productDescription(product)),
      ).toBeInTheDocument();
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
