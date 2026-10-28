// A usage invoice says why it was skipped, and an invoice that was not skipped
// says null — never the empty string it published until R10-W4. The two
// invoices are composed here and served through a stubbed provider, so the
// assertion is on a value the mock did not author: a narrowed type is held on a
// fixture the mock cannot narrow along with it (apps/ui/CLAUDE.md).
import { screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { CUS_NOVA } from "../api/mock-data";
import { customersApi } from "../api/provider";
import type { UsageInvoiceOut } from "../api/types";
import { renderWithProviders } from "../test-utils";
import { UsageInvoicesSection } from "./usage-invoices-section";

const SLOW = { timeout: 5000 };

describe("UsageInvoicesSection", () => {
  it("names a skipped invoice's reason and gives any other none", async () => {
    const skipped: UsageInvoiceOut = {
      period_start: "2026-08-01",
      period_end: "2026-08-31",
      total_billed_micros: 0,
      currency: "usd",
      status: "skipped",
      skip_reason: "no_usage",
      stripe_invoice_id: "",
    };
    const pushed: UsageInvoiceOut = {
      period_start: "2026-09-01",
      period_end: "2026-09-30",
      total_billed_micros: 4_200_000,
      currency: "usd",
      status: "pushed",
      skip_reason: null,
      stripe_invoice_id: "in_test_1",
    };
    vi.spyOn(customersApi, "listCustomerUsageInvoices").mockResolvedValueOnce({
      data: [pushed, skipped],
      has_more: false,
      next_cursor: null,
    });

    renderWithProviders(<UsageInvoicesSection customerId={CUS_NOVA} />);

    const skippedBadge = await screen.findByText("Skipped", undefined, SLOW);
    expect(skippedBadge.getAttribute("title")).toBe("No usage recorded");
    expect(screen.getByText("Pushed").hasAttribute("title")).toBe(false);
  });
});
