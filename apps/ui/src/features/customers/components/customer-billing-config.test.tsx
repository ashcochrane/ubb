import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";

const putBudgetMutate = vi.fn();
const putProfileMutate = vi.fn();
const useAuthMock = vi.fn();
const useBudgetMock = vi.fn();
const useBillingProfileMock = vi.fn();

vi.mock("@/features/auth/hooks/use-auth", () => ({
  useAuth: () => useAuthMock(),
}));

vi.mock("../api/queries", () => ({
  useBudget: () => useBudgetMock(),
  usePutBudget: () => ({ mutate: putBudgetMutate, isPending: false }),
  useBillingProfile: () => useBillingProfileMock(),
  usePutBillingProfile: () => ({ mutate: putProfileMutate, isPending: false }),
}));

// Link needs a router context we don't set up in these unit tests — render
// it as a plain anchor so the pooled-seat disclosure can be asserted without
// pulling in a full TanStack Router.
vi.mock("@tanstack/react-router", () => ({
  Link: ({ children, params }: { children: React.ReactNode; params?: { customerId?: string } }) =>
    React.createElement("a", { href: `/customers/${params?.customerId ?? ""}` }, children),
}));

import { CustomerBudgetForm, CustomerBillingProfileForm } from "./customer-billing-config";

function withProviders(node: React.ReactElement) {
  const qc = new QueryClient();
  return render(
    React.createElement(QueryClientProvider, { client: qc }, node),
  );
}

const defaultAuth = {
  billingMode: "prepaid",
  isBillingMode: true,
  isPrepaid: true,
  isPostpaid: false,
  enforcementMode: "enforcing",
};

describe("CustomerBudgetForm enforce_mode select", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useAuthMock.mockReturnValue(defaultAuth);
  });

  function budgetQuery(enforce_mode: string) {
    return {
      data: {
        cap_micros: 100_000_000,
        enforce_mode,
        hard_stop_pct: 100,
        fail_closed: false,
        alert_levels: [50, 80],
      },
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    };
  }

  it("offers exactly the two real values — alert_only and blocking, nothing invented", async () => {
    useBudgetMock.mockReturnValue(budgetQuery("alert_only"));
    withProviders(React.createElement(CustomerBudgetForm, { customerId: "cus_1" }));

    fireEvent.click(screen.getByRole("combobox"));
    const options = await screen.findAllByRole("option");
    const labels = options.map((o) => o.textContent);
    expect(labels).toHaveLength(2);
    expect(labels.some((l) => /alert only/i.test(l ?? ""))).toBe(true);
    expect(labels.some((l) => /^blocking/i.test(l ?? ""))).toBe(true);
  });

  it("reflects a valid blocking value from the server", () => {
    useBudgetMock.mockReturnValue(budgetQuery("blocking"));
    withProviders(React.createElement(CustomerBudgetForm, { customerId: "cus_1" }));
    expect(screen.getByRole("combobox")).toHaveTextContent("blocking");
  });

  it("coerces an unknown/stale enforce_mode value to alert_only rather than rendering it", () => {
    // Guards the fallback: a stale/unrecognized enforce_mode value (e.g. one of
    // the old advisory/monitor/enforce values from before Task 2's rename)
    // must never reach the field — it should read as "alert_only", not leak
    // through as-is.
    useBudgetMock.mockReturnValue(budgetQuery("monitor"));
    withProviders(React.createElement(CustomerBudgetForm, { customerId: "cus_1" }));
    expect(screen.getByRole("combobox")).not.toHaveTextContent("monitor");
    expect(screen.getByRole("combobox")).toHaveTextContent("alert_only");
  });
});

describe("CustomerBillingProfileForm mode/topology branches", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  function profileQuery(overrides: Record<string, unknown> = {}) {
    return {
      data: {
        billing_owner_id: "cus_1",
        billing_owner_external_id: "cus_1",
        is_pooled_seat: false,
        min_balance_micros: 5_000_000,
        soft_min_balance_micros: 10_000_000,
        topup_grant_expiry_days: 30,
        ...overrides,
      },
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    };
  }

  it("shows editable floor fields for a normal prepaid, non-pooled customer", () => {
    useAuthMock.mockReturnValue(defaultAuth);
    useBillingProfileMock.mockReturnValue(profileQuery());
    withProviders(React.createElement(CustomerBillingProfileForm, { customerId: "cus_1" }));
    expect(screen.getByLabelText(/hard min balance/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/soft min balance/i)).toBeInTheDocument();
  });

  it("hides the floor fields under postpaid and explains why", () => {
    useAuthMock.mockReturnValue({ ...defaultAuth, billingMode: "postpaid", isPrepaid: false, isPostpaid: true });
    useBillingProfileMock.mockReturnValue(profileQuery());
    withProviders(React.createElement(CustomerBillingProfileForm, { customerId: "cus_1" }));
    expect(screen.queryByLabelText(/hard min balance/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/soft min balance/i)).not.toBeInTheDocument();
    expect(screen.getByText(/not used under postpaid/i)).toBeInTheDocument();
  });

  it("renders pooled-seat floors read-only, naming and linking the billing owner", () => {
    useAuthMock.mockReturnValue(defaultAuth);
    useBillingProfileMock.mockReturnValue(
      profileQuery({
        is_pooled_seat: true,
        billing_owner_id: "cus_owner",
        billing_owner_external_id: "acme-corp",
      }),
    );
    withProviders(React.createElement(CustomerBillingProfileForm, { customerId: "cus_1" }));
    expect(screen.queryByLabelText(/hard min balance/i)).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "acme-corp" })).toHaveAttribute(
      "href",
      "/customers/cus_owner",
    );
    // Values are shown, just not as an editable form (Task 3 makes the PUT 422 here).
    expect(screen.getByText("$5.00")).toBeInTheDocument();
  });

  it("notes the soft floor is inactive while tenant enforcement is off", () => {
    useAuthMock.mockReturnValue({ ...defaultAuth, enforcementMode: "off" });
    useBillingProfileMock.mockReturnValue(profileQuery());
    withProviders(React.createElement(CustomerBillingProfileForm, { customerId: "cus_1" }));
    expect(screen.getByText(/inactive while tenant enforcement is off/i)).toBeInTheDocument();
  });
});
