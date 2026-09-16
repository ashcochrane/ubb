import { fireEvent, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { readMockTenantConfig, writeMockTenantConfig } from "@/hooks/use-tenant-config";
import {
  marginUnavailableAtThisGrain,
  statedMargin,
} from "@/lib/economic-scenarios";

import { CUS_ACME, CUS_SEAT_ENG } from "../api/mock-data";
import type { CustomerEconomics } from "../api/types";
import { renderWithProviders } from "../test-utils";
import { BillingTab } from "./billing-tab";
import { CustomerDetailPage } from "./customer-detail-page";
import { OverviewTab } from "./overview-tab";

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

  // The Usage tab hosts whatever the route injects for Stops and breaches
  // (#466): one rendering, two hosts, and this page renders the injection
  // rather than a second copy of the report. The filter itself is the
  // spend-controls feature's (`stops-and-breaches.test.tsx` proves it is
  // applied); what this page owes is the seam.
  it("renders the injected Stops and breaches on the Usage tab", async () => {
    renderWithProviders(
      <CustomerDetailPage
        customerId={CUS_ACME}
        search={{ tab: "usage" }}
        onSearchChange={vi.fn()}
        stopsAndBreaches={<div data-testid="injected">Stops and breaches, injected</div>}
      />,
    );
    expect(await screen.findByTestId("injected", undefined, SLOW)).toBeInTheDocument();
  });

  // ⚠ A FIXTURE THE MOCK DOES NOT AUTHOR, and that is what makes this case
  // able to fail: it narrows with the module, so a mock-authored one would
  // keep passing across exactly the change this is about.
  //
  // ⚠ **THE THREE-SOURCE BREAKDOWN IT USED TO ASSERT IS GONE (#501).** It named
  // a subscription share, a supplied share and billed usage, all non-zero and
  // distinct, so that dropping a card or wiring one to the wrong field changed
  // the result. The one economic query answers `customer_revenue` from ONE
  // definition and publishes no split, so there are no three cards to add up —
  // and asserting that the console does not invent one is what is left worth
  // asserting.
  it("states the total revenue it is given, and invents no split of it", async () => {
    const margin: CustomerEconomics = {
      customer_id: CUS_ACME,
      ...statedMargin(90_000_000, 390_000_000),
      event_count: 12,
    };

    renderWithProviders(
      <OverviewTab
        customerId={CUS_ACME}
        margin={margin}
        externalId="not-a-business"
        range={{ start_date: "2026-07-01", end_date: "2026-07-24" }}
      />,
    );

    expect(await screen.findByText("$390.00", undefined, SLOW)).toBeInTheDocument();
    for (const gone of [
      "Subscription revenue",
      "Supplied revenue",
      "Usage billed",
      "Usage counted as revenue",
    ]) {
      expect(screen.queryByText(gone)).not.toBeInTheDocument();
    }
  });

  // ⚠ AND A MARGIN UBB CANNOT STATE RENDERS AS AN ABSENCE, NEVER AS $0.00.
  // `gross_margin_micros` is nullable on the one query — a margin it cannot
  // attribute at the grain asked for has no figure at all — and a currency
  // zero here would be the silent zero this whole programme exists to delete.
  //
  // ⚠ **THE STATE IS COMPOSED FROM `economic-scenarios.ts`, NOT WRITTEN OUT
  // HERE** (§9.2). Written by hand, the null and the zero percentage beside
  // it are two independent numbers a later edit can separate — and a fixture
  // pairing a null margin with a plausible-looking share would let a renderer
  // show a percentage for a figure it refuses to show. The scenario refuses to
  // be built that way; the fixture is still one the MOCK does not author, which
  // is what makes this case able to fail.
  it("renders an absent margin as an absence rather than as zero", async () => {
    const margin: CustomerEconomics = {
      customer_id: CUS_ACME,
      ...marginUnavailableAtThisGrain(90_000_000, 390_000_000),
      event_count: 12,
    };

    renderWithProviders(
      <OverviewTab
        customerId={CUS_ACME}
        margin={margin}
        externalId="not-a-business"
        range={{ start_date: "2026-07-01", end_date: "2026-07-24" }}
      />,
    );

    expect(await screen.findByText("$390.00", undefined, SLOW)).toBeInTheDocument();
    expect(screen.queryByText("$0.00")).not.toBeInTheDocument();
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
      await screen.findByText("Open reservations", undefined, SLOW),
    ).toBeInTheDocument();
    expect(screen.getByText("Promo credit")).toBeInTheDocument();
    expect(screen.getAllByText("$258.40").length).toBeGreaterThanOrEqual(1);
    // Promo and expiring credit are both $25.00 in the fixture.
    expect(screen.getAllByText("$25.00").length).toBeGreaterThanOrEqual(1);
  });

  // Three labelled amounts (#461, #468; slice 6 §5): the balance, what is
  // reserved against it by work sold at one agreed price still in flight,
  // and what that leaves available — each its own figure, so "available" is
  // never read as the balance and a large balance is never read as the
  // amount a start is judged on. The fixture: $258.40 with $8.00 reserved.
  it("renders the balance, the open reservations and the available amount as three figures", async () => {
    renderWithProviders(<BillingTab customerId={CUS_ACME} externalId="acme-corp" />);
    await screen.findByText("Open reservations", undefined, SLOW);
    expect(document.querySelector('[data-balance="balance"]')).toHaveTextContent("$258.40");
    expect(document.querySelector('[data-balance="reserved"]')).toHaveTextContent("$8.00");
    expect(document.querySelector('[data-balance="available"]')).toHaveTextContent("$250.40");
    expect(screen.getByText("Available")).toBeInTheDocument();
  });

  // No threshold, no amber, no warning affordance ON THE PAGE (#150 §9.4;
  // #152 §4): the section's own test asserts it alone, and this asserts it
  // with the balance card, the transactions, the grants, the invoices and
  // Wallet policy around it, for the customer whose mock pool is blocking and
  // crossed. By role — no meter and no progress bar anywhere — and by word.
  // (`alert`/`status` roles are not asserted here: the tab's own notices are
  // Base UI Alerts and say nothing about the pool.)
  it("draws no meter, progress bar or warning on the whole Billing tab for a crossed pool", async () => {
    renderWithProviders(<BillingTab customerId={CUS_ACME} externalId="acme-corp" />);
    expect(
      await screen.findByText(/new starts for this customer are being refused/, undefined, SLOW),
    ).toBeInTheDocument();
    expect(screen.queryByRole("meter")).not.toBeInTheDocument();
    expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/warning|amber|threshold reached/i);
  });

  // The pool is behind the billing product gate (slice 6 §4's ruling: a
  // tenant that does not bill through UBB may not declare one). The page
  // renders the gate's explanation and none of the pool's words.
  it("shows no pool surface to a tenant without the billing product", async () => {
    const original = readMockTenantConfig();
    writeMockTenantConfig({ ...original, products: ["metering"] });
    try {
      renderWithProviders(
        <CustomerDetailPage
          customerId={CUS_ACME}
          search={{ tab: "billing" }}
          onSearchChange={vi.fn()}
        />,
      );
      expect(
        await screen.findByText("Billing isn't enabled", undefined, SLOW),
      ).toBeInTheDocument();
      expect(screen.queryByText("Customer spend pool")).not.toBeInTheDocument();
      expect(screen.queryByRole("button", { name: "Save pool" })).not.toBeInTheDocument();
      expect(screen.queryByText("Wallet policy")).not.toBeInTheDocument();
    } finally {
      writeMockTenantConfig(original);
    }
  });

  it("asks the affordability question and branches on the verdict body (HTTP 200)", async () => {
    renderWithProviders(<BillingTab customerId={CUS_ACME} externalId="acme-corp" />);
    fireEvent.click(
      await screen.findByRole("button", { name: "Check affordability" }, SLOW),
    );
    fireEvent.click(await screen.findByRole("button", { name: "Ask" }, SLOW));
    expect(
      await screen.findByText(/Allowed — this customer can start work/i, undefined, SLOW),
    ).toBeInTheDocument();
    expect(screen.getByText(/Available after reservations/i)).toBeInTheDocument();
    expect(screen.getByText(/Hard floor/i)).toBeInTheDocument();
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
    await screen.findByText("Open reservations", undefined, SLOW);
    expect(
      screen.queryByText(/this seat has no wallet of its own/i),
    ).not.toBeInTheDocument();
  });

  it("makes the billing profile read-only for a pooled seat, explaining why", async () => {
    renderWithProviders(
      <BillingTab customerId={CUS_SEAT_ENG} externalId="acme-corp:eng" />,
    );
    expect(
      await screen.findByText("Wallet policy", undefined, SLOW),
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
        await screen.findByText("Open reservations", undefined, SLOW);

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

        // Kept under postpaid: the pool enforces in every billing mode (#459),
        // so its declaration stays a live control and the floors' notice
        // points at it.
        expect(screen.getByText("Customer spend pool")).toBeInTheDocument();
        expect(screen.getByRole("button", { name: "Save pool" })).toBeInTheDocument();
        expect(
          screen.getByText(/the customer spend pool above is the control that applies/i),
        ).toBeInTheDocument();
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
