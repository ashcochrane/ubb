import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import React from "react";

vi.mock("@/features/auth/api/queries", () => ({
  useMe: vi.fn(),
}));

import { useMe } from "@/features/auth/api/queries";
import { GettingStarted } from "./getting-started";

const baseTenant = {
  id: "t1",
  name: "Acme",
  products: ["metering"],
  pricingCardsCount: 0,
  usageEventsCount: 0,
};

function mockMe(tenantOverrides: Partial<typeof baseTenant> = {}) {
  (useMe as ReturnType<typeof vi.fn>).mockReturnValue({
    data: {
      tenantUser: { id: "u", email: "a@b.c", role: "owner" },
      tenant: { ...baseTenant, ...tenantOverrides },
      onboardingCompleted: true,
    },
  });
}

describe("GettingStarted", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
  });

  it("shows all items when none done", () => {
    mockMe();
    render(React.createElement(GettingStarted));
    expect(screen.getByText("Create your first pricing card")).toBeInTheDocument();
    expect(screen.getByText("Send your first usage event")).toBeInTheDocument();
  });

  it("marks first item done when card count > 0", () => {
    mockMe({ pricingCardsCount: 2 });
    render(React.createElement(GettingStarted));
    const checkboxes = screen.getAllByRole("checkbox");
    expect((checkboxes[0] as HTMLInputElement).checked).toBe(true);
  });

  it("persists dismissal to localStorage", () => {
    mockMe();
    render(React.createElement(GettingStarted));
    const dismissButtons = screen.getAllByRole("button", { name: /Dismiss/ });
    fireEvent.click(dismissButtons[0]);
    expect(localStorage.getItem("getting-started:dismissed")).toContain("create-card");
  });

  it("hides entirely when every visible item is done", () => {
    mockMe({ pricingCardsCount: 1, usageEventsCount: 1 });
    localStorage.setItem("getting-started:dismissed", JSON.stringify(["invite-teammate"]));
    const { container } = render(React.createElement(GettingStarted));
    expect(container.firstChild).toBeNull();
  });
});
