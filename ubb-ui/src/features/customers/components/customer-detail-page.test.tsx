import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";

const updateMutate = vi.fn();
const deleteMutate = vi.fn();

vi.mock("../api/queries", () => ({
  useCustomer: () => ({
    data: {
      id: "cus_1",
      externalId: "acme",
      stripeCustomerId: "cus_stripe_1",
      status: "active",
      minBalanceMicros: null,
      metadata: {},
      createdAt: "2026-05-01T00:00:00Z",
    },
    isLoading: false,
  }),
  useUpdateCustomer: () => ({ mutateAsync: updateMutate, isPending: false }),
  useDeleteCustomer: () => ({ mutateAsync: deleteMutate, isPending: false }),
}));

vi.mock("@tanstack/react-router", () => ({
  useNavigate: () => vi.fn(),
}));

import { CustomerDetailPage } from "./customer-detail-page";

function renderPage() {
  const qc = new QueryClient();
  return render(
    React.createElement(QueryClientProvider, { client: qc },
      React.createElement(CustomerDetailPage, { customerId: "cus_1" }),
    ),
  );
}

describe("CustomerDetailPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    updateMutate.mockResolvedValue(undefined);
    deleteMutate.mockResolvedValue(undefined);
  });

  it("renders the customer's external id and stripe id", () => {
    renderPage();
    expect(screen.getByDisplayValue("acme")).toBeInTheDocument();
    expect(screen.getByDisplayValue("cus_stripe_1")).toBeInTheDocument();
  });

  it("submits a status change", async () => {
    renderPage();
    const select = screen.getByLabelText(/status/i);
    fireEvent.change(select, { target: { value: "suspended" } });
    fireEvent.click(screen.getByRole("button", { name: /save changes/i }));
    await waitFor(() => {
      expect(updateMutate).toHaveBeenCalledWith(
        expect.objectContaining({ status: "suspended" }),
      );
    });
  });
});
