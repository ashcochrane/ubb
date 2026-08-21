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
  // ⚠ THE TABLE SHOWS TWO AXES, NOT THREE (#369). The markup column is deleted
  // with the plan columns behind it, and the two cases below were the ones that
  // named it: the first asserted all three in one row, the second that a plan
  // charging NO fee and only a markup rendered normally. The second claim is
  // the one worth keeping and it survives without the word — a plan with both
  // fees at zero is still a plan, and it is now a plan priced entirely from the
  // book it names.
  it("shows both fee axes in one row", async () => {
    renderPage();
    expect(await screen.findByText("Enterprise")).toBeInTheDocument();
    expect(screen.getByText("$100.00/mo")).toBeInTheDocument();
    expect(screen.getByText("$10.00/seat")).toBeInTheDocument();
  });

  it("renders a usage-only plan as a normal plan, not an error", async () => {
    renderPage();
    expect(await screen.findByText("Personal Lite")).toBeInTheDocument();
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
    expect(screen.getByLabelText(/Per-seat fee/)).toHaveValue("10");
  });
});
