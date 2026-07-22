import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";

vi.mock("@/features/auth/api/queries", () => ({
  useMe: vi.fn(() => ({ data: { tenantUser: null, tenant: null, onboardingCompleted: false } })),
}));

const createTenantMutate = vi.fn();
const completeOnboardingMutate = vi.fn();

vi.mock("../api/queries", () => ({
  useCreateTenant: () => ({
    mutateAsync: createTenantMutate,
    isPending: false,
  }),
  useCompleteOnboarding: () => ({
    mutateAsync: completeOnboardingMutate,
    isPending: false,
  }),
}));

vi.mock("@tanstack/react-router", () => ({
  useNavigate: () => vi.fn(),
}));

vi.mock("@/features/pricing-cards/components/new-card-wizard", () => ({
  NewCardWizard: ({ onSuccess, onSkip }: { onSuccess?: () => void; onSkip?: () => void }) =>
    React.createElement("div", { "data-testid": "card-wizard" },
      React.createElement("button", { onClick: () => onSuccess?.() }, "Mock Success"),
      React.createElement("button", { onClick: onSkip }, "Mock Skip")
    ),
}));

import { OnboardingWizard } from "./onboarding-wizard";

function renderWizard() {
  const qc = new QueryClient();
  return render(
    React.createElement(QueryClientProvider, { client: qc },
      React.createElement(OnboardingWizard)
    )
  );
}

describe("OnboardingWizard", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    createTenantMutate.mockResolvedValue({
      tenant: { id: "t1", name: "Acme", products: ["metering"], pricingCardsCount: 0, usageEventsCount: 0 },
      apiKey: "ubb_test_abc123",
    });
    completeOnboardingMutate.mockResolvedValue(undefined);
  });

  it("renders step 1 (name workspace) initially", () => {
    renderWizard();
    expect(screen.getByText("Name your workspace")).toBeInTheDocument();
  });

  it("advances to step 2 after submitting workspace name", async () => {
    renderWizard();
    fireEvent.input(screen.getByPlaceholderText(/Acme Corp/), { target: { value: "Acme" } });
    fireEvent.click(screen.getByText("Continue"));
    await waitFor(() => expect(createTenantMutate).toHaveBeenCalledWith({ name: "Acme" }));
    await screen.findByText("Create your first pricing card");
  });

  it("advances to step 3 when user clicks Skip", async () => {
    renderWizard();
    fireEvent.input(screen.getByPlaceholderText(/Acme Corp/), { target: { value: "Acme" } });
    fireEvent.click(screen.getByText("Continue"));
    const skipBtn = await screen.findByText("Mock Skip");
    fireEvent.click(skipBtn);
    await screen.findByText("Connect the SDK");
  });

  it("shows API key on step 3 and fires complete on Done", async () => {
    renderWizard();
    fireEvent.input(screen.getByPlaceholderText(/Acme Corp/), { target: { value: "Acme" } });
    fireEvent.click(screen.getByText("Continue"));
    fireEvent.click(await screen.findByText("Mock Skip"));
    expect(await screen.findByText("ubb_test_abc123")).toBeInTheDocument();
    fireEvent.click(screen.getByText("Done"));
    await waitFor(() => expect(completeOnboardingMutate).toHaveBeenCalled());
  });
});
