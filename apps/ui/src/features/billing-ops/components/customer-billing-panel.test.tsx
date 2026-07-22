import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";

const topUpMutate = vi.fn();

function pager<T>(items: T[]) {
  return {
    items,
    isLoading: false,
    isFetching: false,
    isError: false,
    error: null,
    page: 1,
    hasPrev: false,
    hasNext: false,
    next: vi.fn(),
    prev: vi.fn(),
    reset: vi.fn(),
    refetch: vi.fn(),
  };
}

vi.mock("../api/queries", () => ({
  useBalance: () => ({
    data: { balance_micros: 12_500_000, currency: "USD" },
    isLoading: false,
    isError: false,
    refetch: vi.fn(),
  }),
  useTransactions: () =>
    pager([
      {
        id: "tx_1",
        transaction_type: "credit",
        amount_micros: 5_000_000,
        balance_after_micros: 7_500_000,
        description: "Stripe top-up",
        reference_id: "ref_1",
        created_at: "2026-05-10T10:00:00Z",
      },
    ]),
  useCreateTopUp: () => ({ mutateAsync: topUpMutate, isPending: false }),
  useWithdraw: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useRefund: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useConfigureAutoTopUp: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));

import { CustomerBillingPanel } from "./customer-billing-panel";

function renderPanel() {
  const qc = new QueryClient();
  return render(
    React.createElement(
      QueryClientProvider,
      { client: qc },
      React.createElement(CustomerBillingPanel, { customerId: "cus_1" }),
    ),
  );
}

describe("CustomerBillingPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Resolve with an empty checkout_url so the component skips redirecting.
    topUpMutate.mockResolvedValue({ checkout_url: "" });
  });

  it("renders the balance in dollars", () => {
    renderPanel();
    expect(screen.getByText(/\$12\.50/)).toBeInTheDocument();
  });

  it("renders a transaction row", () => {
    renderPanel();
    expect(screen.getByText("Stripe top-up")).toBeInTheDocument();
  });

  it("submits a top-up in micros", async () => {
    renderPanel();
    fireEvent.click(screen.getByRole("button", { name: /top up/i }));
    const amount = await screen.findByLabelText(/amount/i);
    fireEvent.change(amount, { target: { value: "10" } });
    fireEvent.click(screen.getByRole("button", { name: /continue to payment/i }));
    await waitFor(() => {
      expect(topUpMutate).toHaveBeenCalledWith(
        expect.objectContaining({ amount_micros: 10_000_000 }),
      );
    });
  });
});
