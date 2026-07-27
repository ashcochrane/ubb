import { fireEvent, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { renderWithQuery } from "../test-utils";
import { ProductsPage } from "./products-page";

describe("ProductsPage", () => {
  it("shows the current billing mode and every product with its description", async () => {
    renderWithQuery(<ProductsPage />);

    expect(await screen.findByText("Billing mode")).toBeInTheDocument();
    expect(screen.getByText("Current")).toBeInTheDocument();
    expect(screen.getByText("Prepaid credits")).toBeInTheDocument();

    expect(screen.getByText("Async ingestion")).toBeInTheDocument();
    expect(
      screen.getByText(/Wallets, credit grants, budgets/),
    ).toBeInTheDocument();

    // Prerequisites panel
    expect(screen.getByText("Prerequisites")).toBeInTheDocument();
    expect(
      screen.getByText(/POST \/usage\/ingest/),
    ).toBeInTheDocument();
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
