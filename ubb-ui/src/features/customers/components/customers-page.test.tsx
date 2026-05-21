import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";

const createMutate = vi.fn();

vi.mock("../api/queries", () => ({
  useCustomers: () => ({
    data: {
      data: [
        {
          id: "cus_1",
          externalId: "acme",
          stripeCustomerId: "cus_stripe_1",
          status: "active",
          minBalanceMicros: null,
          metadata: {},
          createdAt: "2026-05-01T00:00:00Z",
        },
      ],
      hasMore: false,
      nextCursor: null,
    },
    isLoading: false,
  }),
  useCreateCustomer: () => ({ mutateAsync: createMutate, isPending: false }),
}));

vi.mock("@tanstack/react-router", () => ({
  Link: ({ to, children }: { to: string; children: React.ReactNode }) =>
    React.createElement("a", { href: to }, children),
  useNavigate: () => vi.fn(),
}));

import { CustomersPage } from "./customers-page";

function renderPage() {
  const qc = new QueryClient();
  return render(
    React.createElement(QueryClientProvider, { client: qc },
      React.createElement(CustomersPage),
    ),
  );
}

describe("CustomersPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    createMutate.mockResolvedValue({
      id: "cus_new",
      externalId: "wayne",
      stripeCustomerId: "",
      status: "active",
    });
  });

  it("renders customer rows", () => {
    renderPage();
    expect(screen.getByText("acme")).toBeInTheDocument();
    expect(screen.getByText(/active/i)).toBeInTheDocument();
  });

  it("opens the create dialog and submits", async () => {
    renderPage();
    fireEvent.click(screen.getByRole("button", { name: /new customer/i }));
    const externalIdInput = await screen.findByLabelText(/external id/i);
    fireEvent.change(externalIdInput, { target: { value: "wayne" } });
    fireEvent.click(screen.getByRole("button", { name: /^create$/i }));
    await waitFor(() => {
      expect(createMutate).toHaveBeenCalledWith({
        externalId: "wayne",
        stripeCustomerId: "",
        metadata: {},
      });
    });
  });
});
