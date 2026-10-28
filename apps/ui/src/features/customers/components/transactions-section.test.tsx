// A wallet movement's type is the registry's LOWERCASE token since R10-W4
// (ruling 7), and the console words it from the catalogue. The row is composed
// here and served through a stubbed provider, so the assertion is on a type the
// mock did not author: a narrowed type is held on a fixture the mock cannot
// narrow along with it (apps/ui/CLAUDE.md).
import { screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { CUS_NOVA } from "../api/mock-data";
import { customersApi } from "../api/provider";
import type { WalletTransactionOut } from "../api/types";
import { renderWithProviders } from "../test-utils";
import { TransactionsSection } from "./transactions-section";

const SLOW = { timeout: 5000 };

describe("TransactionsSection", () => {
  it("words a lowercase transaction type from the catalogue, never as its token", async () => {
    const row: WalletTransactionOut = {
      id: "6a0c1d2e-0000-4000-8000-0000000000a1",
      transaction_type: "usage_deduction",
      amount_micros: -1_500_000,
      balance_after_micros: 8_500_000,
      description: "",
      reference_id: "",
      created_at: "2026-10-27T09:00:00Z",
    };
    vi.spyOn(customersApi, "listTransactions").mockResolvedValueOnce({
      data: [row],
      has_more: false,
      next_cursor: null,
    });

    renderWithProviders(<TransactionsSection customerId={CUS_NOVA} />);

    expect(await screen.findByText("Usage deduction", undefined, SLOW)).toBeInTheDocument();
    expect(screen.queryByText("usage_deduction")).not.toBeInTheDocument();
  });
});
