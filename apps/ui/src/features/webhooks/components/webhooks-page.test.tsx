// Page tests run against the mock provider (automatic in tests: no
// VITE_API_PROVIDER env → "mock"). Mock module state persists within this
// file, so mutation tests use their own targets.

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { WebhooksPage } from "./webhooks-page";

function renderPage(onOpenConfig: (id: string) => void = () => undefined) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <WebhooksPage onOpenConfig={onOpenConfig} />
    </QueryClientProvider>,
  );
}

describe("WebhooksPage", () => {
  it("renders the endpoint list from mock data", async () => {
    renderPage();
    expect(
      await screen.findByText("https://api.acme.dev/webhooks/ubb"),
    ).toBeInTheDocument();
    // "*" renders as the single "All events" chip.
    expect(screen.getByText("All events")).toBeInTheDocument();
    // 4 subscribed types → first 2 chips + "+2 more".
    expect(screen.getByText("+2 more")).toBeInTheDocument();
    expect(screen.getByText("Wallet — Balance low")).toBeInTheDocument();
    // The mid-rotation endpoint shows its rotation-window badge.
    expect(screen.getByText("Rotating secret")).toBeInTheDocument();
  });

  it("opens the detail page when a row is clicked", async () => {
    const onOpenConfig = vi.fn();
    renderPage(onOpenConfig);
    fireEvent.click(await screen.findByText("https://api.acme.dev/webhooks/ubb"));
    expect(onOpenConfig).toHaveBeenCalledWith("3f6c1a52-9d0e-4b6a-8a3d-6a1f0c9b2e71");
  });

  it("resumes a paused endpoint via the row switch (PATCH is_active)", async () => {
    renderPage();
    const resumeSwitch = await screen.findByRole("switch", {
      name: "Resume https://staging.acme.dev/hooks/ubb",
    });
    expect(resumeSwitch).toHaveAttribute("aria-checked", "false");
    fireEvent.click(resumeSwitch);
    // Mock state flips + invalidation refetches → the switch reads active.
    await waitFor(() => {
      expect(
        screen.getByRole("switch", {
          name: "Pause https://staging.acme.dev/hooks/ubb",
        }),
      ).toHaveAttribute("aria-checked", "true");
    });
  });

  it("creates an endpoint and keeps echoing the just-typed secret", { timeout: 20_000 }, async () => {
    renderPage();
    await screen.findByText("https://api.acme.dev/webhooks/ubb");
    fireEvent.click(screen.getByRole("button", { name: "Add endpoint" }));

    fireEvent.change(await screen.findByLabelText("Endpoint URL"), {
      target: { value: "https://new.acme.dev/hooks/ubb" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Generate" }));
    // The generated secret is echoed immediately with the hard warning.
    const echoed = await screen.findByText(/^[0-9a-f]{48}$/);
    const secret = echoed.textContent ?? "";
    expect(
      screen.getByText("Store this now. UBB never displays webhook secrets."),
    ).toBeInTheDocument();

    // "All events (*)" is the default subscription — no catalog interaction.
    expect(
      screen.getByRole("switch", { name: "All events (*)" }),
    ).toHaveAttribute("aria-checked", "true");
    fireEvent.click(screen.getByRole("button", { name: "Create endpoint" }));

    // 201 → success state that KEEPS showing the secret (client-side echo).
    expect(await screen.findByText("Endpoint created")).toBeInTheDocument();
    expect(screen.getByText(secret)).toBeInTheDocument();
    expect(
      screen.getByText("Store this now. UBB never displays webhook secrets."),
    ).toBeInTheDocument();

    // The new endpoint appears in the list behind the dialog.
    expect(
      await screen.findByText("https://new.acme.dev/hooks/ubb"),
    ).toBeInTheDocument();
  });

  it("surfaces the server conflict when the URL already has an endpoint", { timeout: 20_000 }, async () => {
    renderPage();
    await screen.findByText("https://api.acme.dev/webhooks/ubb");
    fireEvent.click(screen.getByRole("button", { name: "Add endpoint" }));

    fireEvent.change(await screen.findByLabelText("Endpoint URL"), {
      target: { value: "https://api.acme.dev/webhooks/ubb" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Generate" }));
    fireEvent.click(screen.getByRole("button", { name: "Create endpoint" }));

    expect(
      await screen.findByText(
        "A webhook endpoint already exists for this URL — edit it instead.",
      ),
    ).toBeInTheDocument();
    // The form (with the user's input) is still there — not blown away.
    expect(screen.getByLabelText("Endpoint URL")).toHaveValue(
      "https://api.acme.dev/webhooks/ubb",
    );
  });
});
