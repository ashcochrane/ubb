import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { PlansPage } from "./plans-page";

vi.mock("../api/queries", () => ({
  usePlans: () => ({
    data: {
      plans: [
        {
          id: "1",
          key: "enterprise",
          name: "Enterprise",
          access_fee_micros: 100_000_000,
          per_seat_micros: 10_000_000,
          markup_percentage_micros: 20_000_000,
          fixed_uplift_micros: 0,
          interval: "month",
          pricing_version: 1,
          archived_at: null,
        },
        {
          id: "3",
          key: "personal-lite",
          name: "Personal Lite",
          access_fee_micros: 0,
          per_seat_micros: 0,
          markup_percentage_micros: 50_000_000,
          fixed_uplift_micros: 0,
          interval: "month",
          pricing_version: 1,
          archived_at: null,
        },
      ],
    },
    isLoading: false,
    error: null,
  }),
  useCreatePlan: () => ({
    mutate: vi.fn(),
    isPending: false,
    isError: false,
    error: null,
    reset: vi.fn(),
  }),
  useUpdatePlan: () => ({
    mutate: vi.fn(),
    isPending: false,
    isError: false,
    error: null,
    reset: vi.fn(),
  }),
}));

// PlansPage gates on the real (unmocked) useTenantConfig hook, which is a
// TanStack Query hook that resolves asynchronously against the mock API
// provider (mock tenant config includes "billing") — same pattern as every
// other ProductGate-style page test in this app (e.g. billing-page.test.tsx).
function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <PlansPage />
    </QueryClientProvider>,
  );
}

describe("PlansPage", () => {
  it("shows all three axes in one row", async () => {
    renderPage();
    expect(await screen.findByText("Enterprise")).toBeInTheDocument();
    expect(screen.getByText("$100.00/mo")).toBeInTheDocument();
    expect(screen.getByText("$10.00/seat")).toBeInTheDocument();
    expect(screen.getByText("20%")).toBeInTheDocument();
  });

  it("renders a markup-only plan as a normal plan, not an error", async () => {
    renderPage();
    expect(await screen.findByText("Personal Lite")).toBeInTheDocument();
    expect(screen.getByText("50%")).toBeInTheDocument();
    expect(screen.queryByText(/invalid|error|unsupported/i)).not.toBeInTheDocument();
  });

  it("opens the create dialog from the New plan button", async () => {
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "New plan" }));
    expect(screen.getByText("Create a plan")).toBeInTheDocument();
    expect(screen.getByLabelText("Plan key")).toHaveValue("");
  });

  it("opens the edit dialog prefilled with the plan being edited", async () => {
    renderPage();
    const editButtons = await screen.findAllByRole("button", { name: "Edit" });
    fireEvent.click(editButtons[0]!);
    expect(screen.getByText("Edit Enterprise")).toBeInTheDocument();
    expect(screen.getByLabelText("Name")).toHaveValue("Enterprise");
    expect(screen.getByLabelText(/Access fee/)).toHaveValue("100");
    expect(screen.getByLabelText(/Markup/)).toHaveValue("20");
  });
});
