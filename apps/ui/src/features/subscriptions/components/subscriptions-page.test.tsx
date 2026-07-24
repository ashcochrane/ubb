import type { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  RouterProvider,
  createMemoryHistory,
  createRootRoute,
  createRouter,
} from "@tanstack/react-router";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ConnectStatusAlert } from "./connect-status-section";
import { CreatePlanCard } from "./create-plan-card";
import { StripeSyncCard } from "./stripe-sync-card";
import { SubscriptionsPage } from "./subscriptions-page";

// The page uses router Links, so tests mount a minimal memory router whose
// root route renders the component under test (mock API provider is automatic
// in tests — VITE_API_PROVIDER is unset).
function renderWithProviders(ui: ReactNode) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const rootRoute = createRootRoute({
    component: () => <QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>,
  });
  const router = createRouter({
    routeTree: rootRoute,
    history: createMemoryHistory({ initialEntries: ["/"] }),
  });
  return render(<RouterProvider router={router} />);
}

const FIND_OPTS = { timeout: 4000 };

describe("SubscriptionsPage", () => {
  it("renders every section against mock data, including the plans-list gap note", async () => {
    renderWithProviders(<SubscriptionsPage />);

    // Product gate resolves (mock tenant has subscriptions), then sections load.
    expect(await screen.findByText("Stripe connected", undefined, FIND_OPTS)).toBeInTheDocument();
    expect(screen.getByText("What lives here")).toBeInTheDocument();
    expect(screen.getByText("Create a plan")).toBeInTheDocument();
    expect(screen.getByText("Edit a plan")).toBeInTheDocument();
    expect(screen.getByText(/can't list plans back/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /sync now/i })).toBeInTheDocument();
    // Connected account id from the mock connect status.
    expect(screen.getByText("acct_1QxTAcmeMock42")).toBeInTheDocument();
  });
});

describe("ConnectStatusAlert", () => {
  it("warns and links to settings when Stripe isn't onboarded", async () => {
    renderWithProviders(
      <ConnectStatusAlert
        status={{ account_id: "", charges_enabled: false, onboarded: false }}
      />,
    );

    expect(
      await screen.findByText("Connect Stripe before charging", undefined, FIND_OPTS),
    ).toBeInTheDocument();
    expect(screen.getByText(/no stripe account is connected yet/i)).toBeInTheDocument();
    const link = screen.getByRole("link", { name: "Settings" });
    expect(link).toHaveAttribute("href", "/settings");
  });
});

describe("CreatePlanCard", () => {
  it("creates a plan and shows the created PlanOut in a result card", async () => {
    renderWithProviders(<CreatePlanCard />);

    fireEvent.change(await screen.findByLabelText("Plan key", undefined, FIND_OPTS), {
      target: { value: "scale-monthly" },
    });
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Scale" } });
    fireEvent.change(screen.getByLabelText(/access fee/i), { target: { value: "199" } });
    fireEvent.click(screen.getByRole("button", { name: /create plan/i }));

    expect(await screen.findByText("Plan created", undefined, FIND_OPTS)).toBeInTheDocument();
    expect(screen.getByText("scale-monthly")).toBeInTheDocument();
    expect(screen.getByText("$199.00")).toBeInTheDocument();
    // "Monthly" appears in the interval select AND the result card's interval row.
    expect(screen.getAllByText("Monthly").length).toBeGreaterThanOrEqual(2);
  });

  it("surfaces the 409 inline when the key already exists", async () => {
    renderWithProviders(<CreatePlanCard />);

    // "team-monthly" is seeded in mock-data.
    fireEvent.change(await screen.findByLabelText("Plan key", undefined, FIND_OPTS), {
      target: { value: "team-monthly" },
    });
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Team again" } });
    fireEvent.click(screen.getByRole("button", { name: /create plan/i }));

    expect(
      await screen.findByText(/a plan with this key already exists/i, undefined, FIND_OPTS),
    ).toBeInTheDocument();
    // User input is kept for correction.
    expect(screen.getByLabelText("Name")).toHaveValue("Team again");
  });
});

describe("StripeSyncCard", () => {
  it("runs a sync and shows the synced/skipped/errors counts", async () => {
    renderWithProviders(<StripeSyncCard />);

    fireEvent.click(await screen.findByRole("button", { name: /sync now/i }, FIND_OPTS));

    expect(await screen.findByText("Synced", undefined, FIND_OPTS)).toBeInTheDocument();
    expect(screen.getByText("14")).toBeInTheDocument();
    expect(screen.getByText("Skipped")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
    expect(screen.getByText("Errors")).toBeInTheDocument();
    expect(screen.getByText(/the mirror is up to date with stripe/i)).toBeInTheDocument();
  });
});
