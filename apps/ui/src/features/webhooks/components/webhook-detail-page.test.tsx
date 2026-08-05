// Detail-page tests against the mock provider. The contract has no
// GET-by-id, so the page resolves the endpoint from the list query —
// including the not-found branch when the id isn't anywhere in the list.

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { WebhookDetailPage } from "./webhook-detail-page";

const PROD_CONFIG_ID = "3f6c1a52-9d0e-4b6a-8a3d-6a1f0c9b2e71";
const PAUSED_EMPTY_CONFIG_ID = "c91d2f64-7b3a-42e8-9f15-2d8ab64c0e37";

function renderPage(configId: string, onBack: () => void = () => undefined) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <WebhookDetailPage configId={configId} onBack={onBack} />
    </QueryClientProvider>,
  );
}

describe("WebhookDetailPage", () => {
  it("renders the summary and delivery attempts, including connection failures", async () => {
    renderPage(PROD_CONFIG_ID);
    // Title is the endpoint host; summary carries the write-only secret note.
    expect(await screen.findByText("api.acme.dev")).toBeInTheDocument();
    expect(
      screen.getByText("Write-only — UBB never displays it. Rotate to replace it."),
    ).toBeInTheDocument();

    // Deliveries tab is the default: status codes, labels, null → connection failed.
    expect(await screen.findByText("connection failed")).toBeInTheDocument();
    expect(screen.getByText("500")).toBeInTheDocument();
    expect(
      screen.getByText("Receiver answered 500 Internal Server Error"),
    ).toBeInTheDocument();
    expect(screen.getAllByText("Wallet — Balance low").length).toBeGreaterThan(0);
    expect(
      screen.getByText("9c1f4b82-6a3d-4e7f-b510-27d8e9a6c143"),
    ).toBeInTheDocument();
  });

  it("expands a truncated error message", async () => {
    renderPage(PROD_CONFIG_ID);
    const more = await screen.findByRole("button", { name: "More" });
    fireEvent.click(more);
    expect(
      screen.getByText(/the delivery will be retried on the backoff schedule/),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Less" })).toBeInTheDocument();
  });

  it("shows the deliveries empty state for an endpoint that has none", async () => {
    renderPage(PAUSED_EMPTY_CONFIG_ID);
    expect(await screen.findByText("No deliveries yet")).toBeInTheDocument();
    expect(
      screen.getByText("Deliveries appear when subscribed events fire."),
    ).toBeInTheDocument();
  });

  it("shows a not-found state for an id missing from the list", async () => {
    const onBack = vi.fn();
    renderPage("00000000-0000-0000-0000-000000000000", onBack);
    expect(await screen.findByText("Endpoint not found")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Back to webhooks" }));
    expect(onBack).toHaveBeenCalled();
  });

  it("documents signature verification in the help tab", async () => {
    renderPage(PROD_CONFIG_ID);
    fireEvent.click(await screen.findByRole("tab", { name: "Verifying signatures" }));
    expect(await screen.findByText("X-UBB-Signature-V2")).toBeInTheDocument();
    expect(screen.getByText(/additive-only/)).toBeInTheDocument();
    expect(screen.getByText(/constant_time_equals/)).toBeInTheDocument();
  });

  it("rotates the secret with an overlap window and echoes the new secret", async () => {
    renderPage(PROD_CONFIG_ID);
    await screen.findByText("api.acme.dev");
    fireEvent.click(screen.getByRole("button", { name: "Rotate secret" }));

    expect(await screen.findByText("Rotate signing secret")).toBeInTheDocument();
    const dialog = screen.getByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: "Generate" }));
    const echoed = await within(dialog).findByText(/^[0-9a-f]{48}$/);
    const secret = echoed.textContent ?? "";
    // Default overlap is prefilled at 24 hours.
    expect(within(dialog).getByLabelText("Overlap window (hours)")).toHaveValue(24);

    fireEvent.click(within(dialog).getByRole("button", { name: "Rotate secret" }));
    expect(await screen.findByText("Secret rotated")).toBeInTheDocument();
    // Result reports the overlap expiry and keeps the client-side echo.
    expect(
      screen.getByText(/Deliveries are signed with BOTH secrets until/),
    ).toBeInTheDocument();
    expect(screen.getByText(secret)).toBeInTheDocument();
  });
});
