// A quarantined subscription renders as itself (#564; CLAUDE.md §9.2): where
// the money is and that it was left out of revenue — never a dollar figure,
// never a zero. The fixture is composed here and served through a stubbed
// provider, so the assertion is on a subscription the mock did not author.
import { screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { quarantinedSubscription } from "@/lib/economic-scenarios";

import { CUS_NOVA } from "../api/mock-data";
import { customersApi } from "../api/provider";
import type { StripeSubscriptionOut } from "../api/types";
import { renderWithProviders } from "../test-utils";
import { SubscriptionTab } from "./subscription-tab";

const SLOW = { timeout: 5000 };

describe("SubscriptionTab", () => {
  it("draws a subscription Stripe holds in another currency as left out, never as money", async () => {
    const subscription: StripeSubscriptionOut = {
      id: "8f65f0d7-0000-4000-8000-0000000009a1",
      stripe_subscription_id: "sub_test_jpy",
      stripe_product_name: "Pro (JP)",
      status: "active",
      ...quarantinedSubscription("jpy", 21_000),
      interval: "month",
      current_period_start: "2026-07-01T00:00:00Z",
      current_period_end: "2026-08-01T00:00:00Z",
      last_synced_at: "2026-07-24T06:10:00Z",
    };
    vi.spyOn(customersApi, "getSubscription").mockResolvedValueOnce(subscription);

    renderWithProviders(<SubscriptionTab customerId={CUS_NOVA} externalId="nova" />);

    expect(
      await screen.findByText(/In JPY — left out of revenue/, undefined, SLOW),
    ).toBeInTheDocument();
    expect(screen.queryByText(/\$0\.00/)).not.toBeInTheDocument();
  });
});
