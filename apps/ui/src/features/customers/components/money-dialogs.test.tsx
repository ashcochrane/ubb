// A top-up has two answers (R10 Stage C5, F-5). With a Stripe connector the
// route answers a checkout to open; without one it answers 202 — the request
// was recorded and handed to the workspace to settle out of band — and the
// console must open NOTHING. The accepted answer is assembled here and served
// through a stubbed provider, so the branch is decided on a body the mock did
// not author, against the registry's closed `top_up_request_status`.

import { fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { readMockTenantConfig, writeMockTenantConfig } from "@/hooks/use-tenant-config";
import { TOP_UP_REQUEST_STATUS_VALUES } from "@/lib/vocabulary";

import { CUS_ACME } from "../api/mock-data";
import { customersApi } from "../api/provider";
import type { TopUpAcceptedResponse, TopUpCheckoutResponse } from "../api/types";
import { isTopUpAccepted } from "../lib/top-up";
import { renderWithProviders } from "../test-utils";
import { TopUpDialog } from "./money-dialogs";

const SLOW = { timeout: 5000 };

// The registry's one value, read off the generated list rather than spelled
// here: the fixture carries whatever the registry declares.
const [REQUESTED] = TOP_UP_REQUEST_STATUS_VALUES;
if (REQUESTED === undefined) throw new Error("top_up_request_status declares no value");

const ACCEPTED: TopUpAcceptedResponse = {
  status: REQUESTED,
  message: "Recorded and handed to the workspace to settle.",
};
const CHECKOUT: TopUpCheckoutResponse = {
  checkout_url: "https://checkout.stripe.com/c/pay/test-session",
};

async function startTopUp(answer: TopUpAcceptedResponse | TopUpCheckoutResponse) {
  vi.spyOn(customersApi, "createTopUp").mockResolvedValueOnce(answer);
  const open = vi.spyOn(window, "open").mockImplementation(() => null);
  const onOpenChange = vi.fn();
  renderWithProviders(<TopUpDialog customerId={CUS_ACME} open onOpenChange={onOpenChange} />);
  fireEvent.change(await screen.findByLabelText(/Amount/, undefined, SLOW), {
    target: { value: "25" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Start top-up" }));
  await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false), SLOW);
  return open;
}

describe("TopUpDialog", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("opens nothing on an accepted (202) top-up request", async () => {
    const open = await startTopUp(ACCEPTED);
    expect(open).not.toHaveBeenCalled();
  });

  it("opens the checkout on a checkout (200) answer", async () => {
    const open = await startTopUp(CHECKOUT);
    expect(open).toHaveBeenCalledWith(CHECKOUT.checkout_url, "_blank", "noopener");
  });

  it("decides the branch on the body, against the registry's value list", () => {
    expect(isTopUpAccepted(ACCEPTED)).toBe(true);
    expect(isTopUpAccepted(CHECKOUT)).toBe(false);
  });

  // The mock's rule mirrors the server's: no Stripe connector on the
  // workspace, no checkout — the request is accepted instead.
  it("is answered an accepted request by the mock where the workspace has no connector", async () => {
    const original = readMockTenantConfig();
    writeMockTenantConfig({ ...original, stripe_connected_account_id: "" });
    try {
      const result = await customersApi.createTopUp(CUS_ACME, {
        amount_micros: 1_000_000,
        success_url: "https://example.test/ok",
        cancel_url: "https://example.test/cancel",
        idempotency_key: crypto.randomUUID(),
      });
      expect(isTopUpAccepted(result)).toBe(true);
      expect("checkout_url" in result).toBe(false);
    } finally {
      writeMockTenantConfig(original);
    }
  });
});
