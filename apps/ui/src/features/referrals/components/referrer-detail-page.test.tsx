import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { MOCK_CUSTOMER_IDS, resetReferralsMockState } from "../api/mock-data";
import { ReferrerDetailPage } from "./referrer-detail-page";

function renderWithClient(ui: React.ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

const FIND_OPTS = { timeout: 4000 };

describe("ReferrerDetailPage", () => {
  beforeEach(() => {
    resetReferralsMockState();
  });

  it("renders the referrer identity, earnings tiles, and referral rows", async () => {
    renderWithClient(
      <ReferrerDetailPage customerId={MOCK_CUSTOMER_IDS.acme} onBack={vi.fn()} />,
    );

    // Code + link token both rendered (code also appears per referral row).
    const codes = await screen.findAllByText("REF-ACME8821", undefined, FIND_OPTS);
    expect(codes.length).toBeGreaterThan(0);
    expect(screen.getByText("rlt_9f8e7d6c5b4a")).toBeInTheDocument();

    // Earnings tiles: 84.5 + 12.13 + 21 = $117.63 lifetime.
    expect(await screen.findByText("$117.63", undefined, FIND_OPTS)).toBeInTheDocument();
    expect(screen.getByText("Total earned")).toBeInTheDocument();

    // Referral rows with humanized status + reward type labels.
    expect(await screen.findByText("acct-golden-fox", undefined, FIND_OPTS)).toBeInTheDocument();
    expect(screen.getByText("acct-copper-owl")).toBeInTheDocument();
    expect(screen.getByText("Expired")).toBeInTheDocument();
  });

  it("revokes a referral through the destructive confirm", async () => {
    renderWithClient(
      <ReferrerDetailPage customerId={MOCK_CUSTOMER_IDS.acme} onBack={vi.fn()} />,
    );
    await screen.findByText("acct-golden-fox", undefined, FIND_OPTS);

    // No revoked referral in this referrer's list yet.
    expect(screen.queryByText("Revoked")).not.toBeInTheDocument();

    const revokeButtons = screen.getAllByRole("button", { name: "Revoke" });
    expect(revokeButtons.length).toBeGreaterThan(0);
    fireEvent.click(revokeButtons[0]!);

    // Destructive confirm with consequence copy.
    expect(
      await screen.findByText("Revoke this referral?", undefined, FIND_OPTS),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Revoke referral" }));

    // Invalidation refetches; the row's status flips to Revoked.
    expect(await screen.findByText("Revoked", undefined, FIND_OPTS)).toBeInTheDocument();
  });

  it("opens the per-referral reward ledger with humanized calculation methods", async () => {
    renderWithClient(
      <ReferrerDetailPage customerId={MOCK_CUSTOMER_IDS.acme} onBack={vi.fn()} />,
    );
    await screen.findByText("acct-golden-fox", undefined, FIND_OPTS);

    const ledgerButtons = screen.getAllByRole("button", { name: "Ledger" });
    // Rows render newest-first: rfl-0002 (acct-blue-heron), rfl-0001, rfl-0003.
    fireEvent.click(ledgerButtons[1]!);

    expect(await screen.findByText("Reward ledger", undefined, FIND_OPTS)).toBeInTheDocument();
    // rfl-0001's July entry uses the capped method → humanized, never raw.
    expect(
      await screen.findByText("Revenue share capped", undefined, FIND_OPTS),
    ).toBeInTheDocument();
    expect(screen.getByText("$34.50")).toBeInTheDocument();
  });

  it("shows the not-found empty state for an unknown referrer", async () => {
    renderWithClient(
      <ReferrerDetailPage
        customerId="00000000-0000-4000-8000-000000000000"
        onBack={vi.fn()}
      />,
    );
    expect(
      await screen.findByText("Referrer not found", undefined, FIND_OPTS),
    ).toBeInTheDocument();
  });
});
