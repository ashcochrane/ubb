import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";

const topUpMutate = vi.fn();
const useBalanceMock = vi.fn();

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

const DEFAULT_BALANCE = {
  balance_micros: 12_500_000,
  currency: "USD",
  billing_owner_id: "cus_1",
  billing_owner_external_id: "acme",
  is_pooled_seat: false,
};

vi.mock("../api/queries", () => ({
  useBalance: (...args: unknown[]) => useBalanceMock(...args),
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

// Link needs a router context we don't set up in these unit tests — render
// it as a plain anchor so the pooled-seat disclosure can be asserted without
// pulling in a full TanStack Router.
vi.mock("@tanstack/react-router", () => ({
  Link: ({ children, params }: { children: React.ReactNode; params?: { customerId?: string } }) =>
    React.createElement("a", { href: `/customers/${params?.customerId ?? ""}` }, children),
}));

import { CustomerBillingPanel } from "./customer-billing-panel";

function renderPanel(props: { isPostpaid?: boolean } = {}) {
  const qc = new QueryClient();
  return render(
    React.createElement(
      QueryClientProvider,
      { client: qc },
      React.createElement(CustomerBillingPanel, { customerId: "cus_1", ...props }),
    ),
  );
}

describe("CustomerBillingPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Resolve with an empty checkout_url so the component skips redirecting.
    topUpMutate.mockResolvedValue({ checkout_url: "" });
    useBalanceMock.mockReturnValue({
      data: DEFAULT_BALANCE,
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });
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

  it("shows top-up/withdraw and auto top-up for prepaid (default)", () => {
    renderPanel({ isPostpaid: false });
    expect(screen.getByRole("button", { name: /^top up$/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /withdraw/i })).toBeInTheDocument();
    expect(screen.getByText(/enable auto top-up/i)).toBeInTheDocument();
  });

  it("hides top-up, withdraw, and auto top-up under postpaid, but keeps balance + ledger", () => {
    renderPanel({ isPostpaid: true });
    expect(screen.queryByRole("button", { name: /^top up$/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /withdraw/i })).not.toBeInTheDocument();
    expect(screen.queryByText(/enable auto top-up/i)).not.toBeInTheDocument();
    // Balance and transaction ledger still render — manual adjustments still
    // move a postpaid wallet even though the prepaid credit flow is hidden.
    expect(screen.getByText(/\$12\.50/)).toBeInTheDocument();
    expect(screen.getByText("Stripe top-up")).toBeInTheDocument();
  });

  it("names the billing owner and links to it for a pooled seat", () => {
    useBalanceMock.mockReturnValue({
      data: {
        ...DEFAULT_BALANCE,
        billing_owner_id: "cus_owner",
        billing_owner_external_id: "acme-corp",
        is_pooled_seat: true,
      },
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });
    renderPanel();
    expect(screen.getByText("acme-corp")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "acme-corp" })).toHaveAttribute(
      "href",
      "/customers/cus_owner",
    );
  });

  it("does not show the pooled-seat disclosure for a non-pooled customer", () => {
    renderPanel();
    expect(screen.queryByText(/pooled seat/i)).not.toBeInTheDocument();
  });
});
