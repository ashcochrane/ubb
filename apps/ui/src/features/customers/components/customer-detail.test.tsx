import { fireEvent, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { readMockTenantConfig, writeMockTenantConfig } from "@/hooks/use-tenant-config";

import { CUS_ACME, CUS_SEAT_ENG } from "../api/mock-data";
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

  it("shows the per-customer usage-invoice push history", async () => {
    renderWithProviders(<BillingTab customerId={CUS_ACME} externalId="acme-corp" />);
    expect(
      await screen.findByText("Usage invoices", undefined, SLOW),
    ).toBeInTheDocument();
    // Acme's June period pushed to Stripe: UTC-safe period, status, invoice id.
    expect(
      await screen.findByText("in_mock_usage_2026_06", undefined, SLOW),
    ).toBeInTheDocument();
    expect(screen.getAllByText("Pushed").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("Jun 1, 2026 → Jul 1, 2026")).toBeInTheDocument();
  });

  it("discloses the billing owner for a pooled seat's balance, with a link", async () => {
    renderWithProviders(
      <BillingTab customerId={CUS_SEAT_ENG} externalId="acme-corp:eng" />,
    );
    // The seat's balance IS the owner's ($258.40 — acme's fixture balance).
    expect(
      await screen.findAllByText("$258.40", undefined, SLOW),
    ).not.toHaveLength(0);
    // The billing-profile card's own read-only disclosure repeats similar
    // wording, so this must resolve to more than zero, not exactly one.
    expect(
      (await screen.findAllByText(/this seat has no wallet of its own/i, undefined, SLOW))
        .length,
    ).toBeGreaterThan(0);
    const ownerLinks = screen.getAllByRole("link", { name: "acme-corp" });
    expect(ownerLinks.length).toBeGreaterThan(0);
    for (const link of ownerLinks) {
      expect(link).toHaveAttribute("href", expect.stringContaining(CUS_ACME));
    }
  });

  it("does not show the billing-owner disclosure for an ordinary customer", async () => {
    renderWithProviders(<BillingTab customerId={CUS_ACME} externalId="acme-corp" />);
    await screen.findByText("Total spendable", undefined, SLOW);
    expect(
      screen.queryByText(/this seat has no wallet of its own/i),
    ).not.toBeInTheDocument();
  });

  it("makes the billing profile read-only for a pooled seat, explaining why", async () => {
    renderWithProviders(
      <BillingTab customerId={CUS_SEAT_ENG} externalId="acme-corp:eng" />,
    );
    expect(
      await screen.findByText("Billing profile", undefined, SLOW),
    ).toBeInTheDocument();
    // The read-only floors are the OWNER's real values (acme's fixture: $25
    // overdraft, $20 wind-down, 90-day top-up expiry) — never a fabricated
    // null, and the PUT would 422 so there's no editable form or save button.
    // ($25.00 also appears in the balance card's promo/expiring figures.)
    expect(
      (await screen.findAllByText("$25.00", undefined, SLOW)).length,
    ).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("$20.00")).toBeInTheDocument();
    expect(screen.getByText("90 days")).toBeInTheDocument();
    expect(
      screen.getByText(/the API refuses \(422\) writing floors/i),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Save profile" }),
    ).not.toBeInTheDocument();
  });

  it("keeps the billing profile editable for an ordinary customer", async () => {
    renderWithProviders(<BillingTab customerId={CUS_ACME} externalId="acme-corp" />);
    expect(
      await screen.findByRole("button", { name: "Save profile" }, SLOW),
    ).toBeInTheDocument();
  });

  describe("mode-aware wallet surfaces", () => {
    const withBillingMode = async (mode: "prepaid" | "postpaid", run: () => Promise<void>) => {
      const original = readMockTenantConfig();
      writeMockTenantConfig({ ...original, billing_mode: mode });
      try {
        await run();
      } finally {
        writeMockTenantConfig(original);
      }
    };

    it("hides top-up, withdraw, auto-top-up, and credit grants under postpaid — with an explanation", async () => {
      await withBillingMode("postpaid", async () => {
        renderWithProviders(<BillingTab customerId={CUS_ACME} externalId="acme-corp" />);
        await screen.findByText("Total spendable", undefined, SLOW);

        expect(screen.queryByRole("button", { name: "Top up" })).not.toBeInTheDocument();
        expect(screen.queryByRole("button", { name: "Withdraw" })).not.toBeInTheDocument();
        // Kept under postpaid: manual credit/debit and the access check.
        expect(screen.getByRole("button", { name: "Manual credit" })).toBeInTheDocument();
        expect(screen.getByRole("button", { name: "Manual debit" })).toBeInTheDocument();
        expect(
          screen.getByText(/top-up and withdraw are hidden under postpaid/i),
        ).toBeInTheDocument();

        expect(
          await screen.findByText(/credit grants aren't used under postpaid/i, undefined, SLOW),
        ).toBeInTheDocument();
        expect(
          screen.queryByRole("button", { name: "Create grant" }),
        ).not.toBeInTheDocument();

        expect(
          screen.getByText(/auto top-up isn't used under postpaid/i),
        ).toBeInTheDocument();
        expect(
          screen.queryByRole("button", { name: "Save auto top-up" }),
        ).not.toBeInTheDocument();

        expect(
          screen.getByText(/overdraft and wind-down floors aren't used under postpaid/i),
        ).toBeInTheDocument();
        expect(
          screen.queryByRole("button", { name: "Save profile" }),
        ).not.toBeInTheDocument();

        // Kept under postpaid: the monthly budget stays a live control.
        expect(screen.getByText("Monthly budget")).toBeInTheDocument();
        expect(screen.getByRole("button", { name: "Save budget" })).toBeInTheDocument();
      });
    });

    it("shows top-up, withdraw, auto-top-up, and credit grants under prepaid", async () => {
      await withBillingMode("prepaid", async () => {
        renderWithProviders(<BillingTab customerId={CUS_ACME} externalId="acme-corp" />);
        expect(
          await screen.findByRole("button", { name: "Top up" }, SLOW),
        ).toBeInTheDocument();
        expect(screen.getByRole("button", { name: "Withdraw" })).toBeInTheDocument();
        expect(
          await screen.findByRole("button", { name: "Create grant" }, SLOW),
        ).toBeInTheDocument();
        expect(
          screen.getByRole("button", { name: "Save auto top-up" }),
        ).toBeInTheDocument();
        expect(
          await screen.findByRole("button", { name: "Save profile" }, SLOW),
        ).toBeInTheDocument();
      });
    });
  });

  // Keep this LAST in the file — it moves acme's mock balance.
  it("requires a confirm step before a manual credit moves money", async () => {
    renderWithProviders(<BillingTab customerId={CUS_ACME} externalId="acme-corp" />);
    fireEvent.click(
      await screen.findByRole("button", { name: "Manual credit" }, SLOW),
    );
    fireEvent.change(await screen.findByLabelText(/Amount/, undefined, SLOW), {
      target: { value: "10" },
    });
    fireEvent.change(screen.getByLabelText("Reference"), {
      target: { value: "goodwill-credit" },
    });
    // Submitting the valid form does NOT move money yet — it opens the confirm.
    fireEvent.click(screen.getByRole("button", { name: "Credit…" }));
    expect(
      await screen.findByText("Credit this wallet?", undefined, SLOW),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/real money moves when you confirm/i),
    ).toBeInTheDocument();
    // Confirming fires the mutation; the invalidated balance card refetches
    // to the new total ($258.40 + $10.00).
    fireEvent.click(screen.getByRole("button", { name: "Credit wallet" }));
    expect(
      (await screen.findAllByText("$268.40", undefined, SLOW)).length,
    ).toBeGreaterThanOrEqual(1);
  });
});
