// Empty-state branches: no API keys yet + no sandbox yet. The provider is
// stubbed at the module level so these tests see an empty workspace.

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { TooltipProvider } from "@/components/ui/tooltip";

import { ApiKeysSection } from "./api-keys-section";
import { SandboxSection } from "./sandbox-section";

// vi.mock is hoisted above the imports, so both sections see the stub.
vi.mock("../api/provider", () => ({
  developersApi: {
    listApiKeys: async () => ({ data: [], has_more: false, next_cursor: null }),
    getSandbox: async () => ({
      exists: false,
      sandbox_tenant_id: null,
      key_prefixes: [],
    }),
  },
}));

function renderWithClient(children: React.ReactNode) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <TooltipProvider>{children}</TooltipProvider>
    </QueryClientProvider>,
  );
}

describe("developers empty states", () => {
  it("shows the API-keys empty state with a create CTA", async () => {
    renderWithClient(<ApiKeysSection />);
    expect(await screen.findByText("No API keys yet")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Create API key" }),
    ).toBeInTheDocument();
  });

  it("shows the sandbox empty state with a create CTA", async () => {
    renderWithClient(<SandboxSection />);
    expect(await screen.findByText("No sandbox yet")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Create sandbox" }),
    ).toBeInTheDocument();
  });
});
