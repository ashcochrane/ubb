import { fireEvent, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { CUS_ACME } from "../api/mock-data";
import { renderWithProviders } from "../test-utils";
import { BillingTab } from "./billing-tab";
import { CustomerDetailPage } from "./customer-detail-page";

const SLOW = { timeout: 5000 };

describe("CustomerDetailPage — overview", () => {
  it("renders the header identity and period economics", async () => {
    renderWithProviders(
      <CustomerDetailPage
        customerId={CUS_ACME}
        search={{}}
        onSearchChange={vi.fn()}
      />,
    );
    // external_id big in the header; UUID shown in mono alongside.
    expect(await screen.findByText("acme-corp", undefined, SLOW)).toBeInTheDocument();
    expect(screen.getByText(CUS_ACME)).toBeInTheDocument();
    // Overview economics from GET /margin/customers/{id}.
    expect(await screen.findByText("$541.50", undefined, SLOW)).toBeInTheDocument();
    // getAllBy — the async business-rollup table repeats the label as a
    // column header once it loads, so a single-match query is timing-fragile.
    expect(screen.getAllByText("Gross margin").length).toBeGreaterThan(0);
    expect(screen.getByText("$267.50")).toBeInTheDocument();
  });

  it("shows the not-found state for an unknown customer", async () => {
    renderWithProviders(
      <CustomerDetailPage
        customerId="00000000-0000-4000-8000-000000000000"
        search={{}}
        onSearchChange={vi.fn()}
      />,
    );
    expect(
      await screen.findByText("Customer not found", undefined, SLOW),
    ).toBeInTheDocument();
  });
});

describe("BillingTab", () => {
  it("shows the balance card with promo and expiring credit", async () => {
    renderWithProviders(<BillingTab customerId={CUS_ACME} externalId="acme-corp" />);
    // Wait for the balance card itself (the amount also appears in the
    // transactions table, so anchor on the card's own labels).
    expect(
      await screen.findByText("Total spendable", undefined, SLOW),
    ).toBeInTheDocument();
    expect(screen.getByText("Promo credit")).toBeInTheDocument();
    expect(screen.getAllByText("$258.40").length).toBeGreaterThanOrEqual(1);
    // Promo and expiring credit are both $25.00 in the fixture.
    expect(screen.getAllByText("$25.00").length).toBeGreaterThanOrEqual(1);
  });

  it("runs an access check and branches on the verdict body (HTTP 200)", async () => {
    renderWithProviders(<BillingTab customerId={CUS_ACME} externalId="acme-corp" />);
    fireEvent.click(
      await screen.findByRole("button", { name: "Run access check" }, SLOW),
    );
    fireEvent.click(await screen.findByRole("button", { name: "Run check" }, SLOW));
    expect(
      await screen.findByText(/Allowed — this customer can spend/i, undefined, SLOW),
    ).toBeInTheDocument();
    expect(screen.getByText(/Balance at check/i)).toBeInTheDocument();
  });
});
