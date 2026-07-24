import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { TooltipProvider } from "@/components/ui/tooltip";

import { ApiKeysSection } from "./api-keys-section";

function renderSection() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <TooltipProvider>
        <ApiKeysSection />
      </TooltipProvider>
    </QueryClientProvider>,
  );
}

describe("ApiKeysSection", () => {
  it("renders the mock key list with status and approximate last-used", async () => {
    renderSection();
    expect(await screen.findByText("Production backend")).toBeInTheDocument();
    expect(screen.getByText("Staging worker")).toBeInTheDocument();
    // Revoked keys stay listed as history.
    expect(screen.getByText("CI smoke tests (rotated)")).toBeInTheDocument();
    expect(screen.getByText("Revoked")).toBeInTheDocument();
    expect(screen.getAllByText("Active").length).toBeGreaterThanOrEqual(3);
    // The Redis-buffered lag is labeled, and prefixes render in mono.
    expect(screen.getByText(/Last used \(approximate\)/)).toBeInTheDocument();
    expect(screen.getByText(/ubb_live_k3xA/)).toBeInTheDocument();
    // A never-used key shows "Never" rather than a blank.
    expect(screen.getByText("Never")).toBeInTheDocument();
  });

  it("creates a key and surfaces the raw key in the return-once modal", async () => {
    renderSection();
    const createButton = await screen.findByRole("button", { name: "Create key" });
    await waitFor(() => expect(createButton).toBeEnabled());
    fireEvent.click(createButton);

    const labelInput = await screen.findByPlaceholderText("Production backend");
    fireEvent.change(labelInput, { target: { value: "Load test runner" } });
    fireEvent.click(screen.getByRole("button", { name: "Create API key" }));

    expect(
      await screen.findByText("This is the only time UBB shows this key."),
    ).toBeInTheDocument();
    // The raw key is a full ubb_live_ secret, not just the prefix.
    expect(screen.getByText(/^ubb_live_[A-Za-z0-9]{28,}$/)).toBeInTheDocument();

    // The list refreshes with the minted key.
    fireEvent.click(screen.getByRole("button", { name: "Done" }));
    expect(await screen.findByText("Load test runner")).toBeInTheDocument();
  });

  it("asks for confirmation with consequence copy before rotating", async () => {
    renderSection();
    await screen.findByText("Production backend");
    const [firstRotate] = screen.getAllByRole("button", { name: "Rotate" });
    if (!firstRotate) throw new Error("expected a rotate button");
    await waitFor(() => expect(firstRotate).toBeEnabled());
    fireEvent.click(firstRotate);
    expect(await screen.findByText("Rotate this key?")).toBeInTheDocument();
    expect(
      screen.getByText(/the old key stops working on its next request/i),
    ).toBeInTheDocument();
  });
});
