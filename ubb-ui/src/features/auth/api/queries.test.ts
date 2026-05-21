import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";
import { useMe } from "./queries";

vi.mock("./provider", () => ({
  authApi: {
    getMe: vi.fn(),
  },
}));

import { authApi } from "./provider";

function withQueryClient() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client: queryClient }, children);
}

describe("useMe", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("returns Me payload on success", async () => {
    (authApi.getMe as ReturnType<typeof vi.fn>).mockResolvedValue({
      tenantUser: { id: "tu1", email: "a@b.com", role: "owner" },
      tenant: {
        id: "t1", name: "X", products: ["metering"],
        pricingCardsCount: 0, usageEventsCount: 0,
      },
      onboardingCompleted: false,
    });
    const { result } = renderHook(() => useMe(), { wrapper: withQueryClient() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.onboardingCompleted).toBe(false);
  });

  it("surfaces error state when API fails", async () => {
    (authApi.getMe as ReturnType<typeof vi.fn>).mockRejectedValue(new Error("401"));
    const { result } = renderHook(() => useMe(), { wrapper: withQueryClient() });
    await waitFor(() => expect(result.current.isError).toBe(true));
  });
});
