import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";

const topUpMutate = vi.fn();

vi.mock("../api/queries", () => ({
  useBalance: () => ({
    data: { balanceMicros: 12_500_000, currency: "USD" },
    isLoading: false,
  }),
  useTransactions: () => ({
    data: {
      data: [
        {
          id: "tx_1",
          type: "credit",
          amountMicros: 5_000_000,
          balanceAfterMicros: 12_500_000,
          description: "Stripe top-up",
          createdAt: "2026-05-10T10:00:00Z",
        },
      ],
      hasMore: false,
      nextCursor: null,
    },
    isLoading: false,
  }),
  useCreateTopUp: () => ({ mutateAsync: topUpMutate, isPending: false }),
  useWithdraw: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useConfigureAutoTopUp: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));

import { CustomerBillingPanel } from "./customer-billing-panel";

function renderPanel() {
  const qc = new QueryClient();
  return render(
    React.createElement(QueryClientProvider, { client: qc },
      React.createElement(CustomerBillingPanel, { customerId: "cus_1" }),
    ),
  );
}

describe("CustomerBillingPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    topUpMutate.mockResolvedValue(undefined);
  });

  it("renders the balance in dollars", () => {
    renderPanel();
    expect(screen.getByText(/\$12\.50/)).toBeInTheDocument();
  });

  it("renders a transaction row", () => {
    renderPanel();
    expect(screen.getByText("Stripe top-up")).toBeInTheDocument();
  });

  it("submits a top-up", async () => {
    renderPanel();
    fireEvent.click(screen.getByRole("button", { name: /top up/i }));
    const amount = await screen.findByLabelText(/amount/i);
    fireEvent.change(amount, { target: { value: "10" } });
    fireEvent.click(screen.getByRole("button", { name: /start top-up/i }));
    await waitFor(() => {
      expect(topUpMutate).toHaveBeenCalledWith(
        expect.objectContaining({
          amountMicros: 10_000_000,
        }),
      );
    });
  });
});
