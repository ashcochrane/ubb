import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import React from "react";

const useAuthMock = vi.fn();

vi.mock("@/features/auth/hooks/use-auth", () => ({
  useAuth: () => useAuthMock(),
}));

vi.mock("@/features/billing-ops/components/customer-billing-panel", () => ({
  CustomerBillingPanel: ({ isPostpaid }: { isPostpaid?: boolean }) =>
    React.createElement("div", { "data-testid": "billing-panel" }, `isPostpaid=${String(isPostpaid)}`),
}));

vi.mock("./customer-grants-section", () => ({
  CustomerGrantsSection: () => React.createElement("div", { "data-testid": "grants-section" }, "grants"),
}));

vi.mock("./customer-billing-config", () => ({
  CustomerBudgetForm: () => React.createElement("div", { "data-testid": "budget-form" }, "budget"),
  CustomerBillingProfileForm: () =>
    React.createElement("div", { "data-testid": "profile-form" }, "profile"),
}));

import { CustomerWalletTab } from "./customer-wallet-tab";

describe("CustomerWalletTab mode branching", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows grants and no banner for prepaid, and forwards isPostpaid=false to the billing panel", () => {
    useAuthMock.mockReturnValue({ isPostpaid: false });
    render(React.createElement(CustomerWalletTab, { customerId: "cus_1" }));
    expect(screen.getByTestId("grants-section")).toBeInTheDocument();
    expect(screen.getByTestId("billing-panel")).toHaveTextContent("isPostpaid=false");
    expect(screen.queryByText(/wallet isn't the billing mechanism/i)).not.toBeInTheDocument();
  });

  it("hides grants and shows the postpaid explanation banner, forwarding isPostpaid=true", () => {
    useAuthMock.mockReturnValue({ isPostpaid: true });
    render(React.createElement(CustomerWalletTab, { customerId: "cus_1" }));
    expect(screen.queryByTestId("grants-section")).not.toBeInTheDocument();
    expect(screen.getByTestId("billing-panel")).toHaveTextContent("isPostpaid=true");
    expect(screen.getByText(/wallet isn't the billing mechanism/i)).toBeInTheDocument();
  });

  it("always renders the budget and billing-profile forms regardless of mode", () => {
    useAuthMock.mockReturnValue({ isPostpaid: true });
    render(React.createElement(CustomerWalletTab, { customerId: "cus_1" }));
    expect(screen.getByTestId("budget-form")).toBeInTheDocument();
    expect(screen.getByTestId("profile-form")).toBeInTheDocument();
  });
});
