// A usage invoice says why it was skipped, and an invoice that was not skipped
// says null — never the empty string it published until R10-W4. Since R10
// Stage C5 (F-15) every route serves ONE usage-invoice shape, and the row says
// where its Stripe invoice stands as a receivable: `payment_status` renders
// through the catalogue, and null — not yet collectible — renders as that
// meaning, never as a fifth value and never as "—". The invoices are composed
// here and served through a stubbed provider, so the assertion is on a value
// the mock did not author: a narrowed type is held on a fixture the mock
// cannot narrow along with it (apps/ui/CLAUDE.md).
import { screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { NOT_YET_COLLECTIBLE } from "@/lib/usage-invoice";

import { CUS_NOVA } from "../api/mock-data";
import { customersApi } from "../api/provider";
import type { UsageInvoiceOut } from "../api/types";
import { renderWithProviders } from "../test-utils";
import { UsageInvoicesSection } from "./usage-invoices-section";

const SLOW = { timeout: 5000 };

/** The whole shared base, every field spelled, so a dropped one is a `tsc` failure here. */
function invoice(overrides: Partial<UsageInvoiceOut> & Pick<UsageInvoiceOut, "id">): UsageInvoiceOut {
  return {
    customer_id: CUS_NOVA,
    external_id: "nova-ai",
    period_start: "2026-09-01",
    period_end: "2026-09-30",
    currency: "usd",
    total_billed_micros: 4_200_000,
    status: "pushed",
    skip_reason: null,
    stripe_invoice_id: "in_test_1",
    pushed_at: "2026-10-01T00:10:00Z",
    payment_status: null,
    paid_at: null,
    payment_failed_at: null,
    hosted_invoice_url: "",
    invoice_pdf: "",
    created_at: "2026-10-01T00:05:00Z",
    push_attempts: 1,
    last_attempt_error: "",
    ...overrides,
  };
}

function serve(rows: UsageInvoiceOut[]) {
  vi.spyOn(customersApi, "listCustomerUsageInvoices").mockResolvedValueOnce({
    data: rows,
    has_more: false,
    next_cursor: null,
  });
}

describe("UsageInvoicesSection", () => {
  it("names a skipped invoice's reason and gives any other none", async () => {
    const skipped = invoice({
      id: "inv-skipped",
      period_start: "2026-08-01",
      period_end: "2026-08-31",
      total_billed_micros: 0,
      status: "skipped",
      skip_reason: "no_usage",
      stripe_invoice_id: "",
      pushed_at: null,
      push_attempts: 0,
    });
    const pushed = invoice({ id: "inv-pushed" });
    serve([pushed, skipped]);

    renderWithProviders(<UsageInvoicesSection customerId={CUS_NOVA} />);

    const skippedBadge = await screen.findByText("Skipped", undefined, SLOW);
    expect(skippedBadge.getAttribute("title")).toBe("No usage recorded");
    expect(screen.getByText("Pushed").hasAttribute("title")).toBe(false);
  });

  // F-15: the payment status is the registry's closed concept, worded from the
  // catalogue; null is "not yet collectible" and nothing else. A paid invoice
  // says when, and a pushed one links its hosted Stripe invoice.
  it("words the payment status from the catalogue, null as not yet collectible", async () => {
    const paid = invoice({
      id: "inv-paid",
      payment_status: "paid",
      paid_at: "2026-10-03T09:30:00Z",
      hosted_invoice_url: "https://invoice.stripe.com/i/acct_test/in_test_1",
    });
    const open = invoice({
      id: "inv-open",
      period_start: "2026-10-01",
      period_end: "2026-10-31",
      stripe_invoice_id: "in_test_2",
      payment_status: "open",
    });
    const notYet = invoice({
      id: "inv-not-yet",
      period_start: "2026-11-01",
      period_end: "2026-11-30",
      status: "pending",
      stripe_invoice_id: "",
      pushed_at: null,
      payment_status: null,
      push_attempts: 0,
    });
    serve([notYet, open, paid]);

    renderWithProviders(<UsageInvoicesSection customerId={CUS_NOVA} />);

    expect(await screen.findByText("Paid", undefined, SLOW)).toBeInTheDocument();
    expect(screen.getByText("Open")).toBeInTheDocument();
    expect(screen.getByText(NOT_YET_COLLECTIBLE)).toBeInTheDocument();
    // Never the raw token, never a dash standing in for the null's meaning.
    expect(screen.queryByText("paid")).not.toBeInTheDocument();
    const cells = document.querySelectorAll("[data-payment-status]");
    expect(Array.from(cells).map((cell) => cell.getAttribute("data-payment-status"))).toEqual([
      "",
      "open",
      "paid",
    ]);
    expect(screen.getByRole("link", { name: "Open the hosted Stripe invoice" })).toHaveAttribute(
      "href",
      "https://invoice.stripe.com/i/acct_test/in_test_1",
    );
    expect(screen.getAllByRole("link", { name: "Open the hosted Stripe invoice" })).toHaveLength(1);
  });
});
