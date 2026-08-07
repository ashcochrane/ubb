import { fireEvent, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { labelMap } from "@/lib/localisation";
import {
  TENANT_PRODUCT_LABEL_KEYS,
  TENANT_PRODUCT_VALUES,
  type TenantProduct,
} from "@/lib/vocabulary";

import { renderWithQuery } from "../test-utils";
import { ProductsPage } from "./products-page";

/** The registry's products, in the catalogue's words — reached independently
 * of `@/lib/products`, which is what the page renders through. #240 left this
 * test naming the three by hand because the page rendered from the console's
 * OWN literal, and a loop over that array could only fail if rendering broke
 * wholesale. The page now renders from the generated vocabulary, so this
 * compares what a reader sees against the registry itself. */
const productWords = labelMap(TENANT_PRODUCT_LABEL_KEYS);

/** Each product's row copy, spelled out rather than imported: the sentences
 * are console-owned (ADR-0008 §4.5), and reading them from the module the page
 * renders them from would be the comparison-with-itself this test just left
 * behind. Total over the generated type, so a fourth product cannot be added
 * to the registry without someone writing the row this test then demands. */
const DESCRIPTION_OF = {
  metering: /Usage events, pricing, analytics/,
  billing: /Wallets, credit grants, budgets/,
  referrals: /Referral programs, attribution/,
} as const satisfies Record<TenantProduct, RegExp>;

describe("ProductsPage", () => {
  it("shows the current billing mode and every product with its description", async () => {
    renderWithQuery(<ProductsPage />);

    expect(await screen.findByText("Billing mode")).toBeInTheDocument();
    expect(screen.getByText("Current")).toBeInTheDocument();
    expect(screen.getByText("Prepaid credits")).toBeInTheDocument();

    // EXACTLY the declared products: the set of toggles, compared with the
    // registry's set, so an extra row fails as loudly as a missing one. The
    // products card holds the only switches on this page. The predecessor
    // pinned "Async ingestion" and its endpoint, and both outlived the
    // product — it named the rows instead of the rule.
    const rendered = screen
      .getAllByRole("switch")
      .map((toggle) => toggle.getAttribute("aria-label"));
    expect(rendered.sort()).toEqual(
      TENANT_PRODUCT_VALUES.map(productWords).sort(),
    );

    for (const product of TENANT_PRODUCT_VALUES) {
      expect(screen.getByText(DESCRIPTION_OF[product])).toBeInTheDocument();
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
