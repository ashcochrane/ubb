import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { resetReferralsMockState } from "../api/mock-data";
import { ProgramSection } from "./program-section";
import { ReferralsPage } from "./referrals-page";

function renderWithClient(ui: React.ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

const FIND_OPTS = { timeout: 4000 };

describe("ReferralsPage", () => {
  beforeEach(() => {
    resetReferralsMockState();
  });

  it("renders the program, analytics tiles, referrers, and payout card from mock data", async () => {
    renderWithClient(<ReferralsPage onOpenReferrer={vi.fn()} />);

    // Program card with the polymorphic reward rendered as a share.
    expect(await screen.findByText("Referral program", undefined, FIND_OPTS)).toBeInTheDocument();
    expect(await screen.findByText("10% of referred revenue", undefined, FIND_OPTS)).toBeInTheDocument();

    // Analytics tiles.
    expect(await screen.findByText("Rewards earned", undefined, FIND_OPTS)).toBeInTheDocument();
    expect(screen.getByText("Referred spend")).toBeInTheDocument();

    // Referrers table (code appears in referrers + earnings tables).
    const codes = await screen.findAllByText("REF-ACME8821", undefined, FIND_OPTS);
    expect(codes.length).toBeGreaterThan(0);
    expect(screen.getByText("REF-KITE9034")).toBeInTheDocument();

    // Payout export card exists but hasn't fetched yet.
    expect(screen.getByText("Payout export")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Generate export" })).toBeInTheDocument();
  });

  it("generates the payout export on demand and shows totals + exported time", async () => {
    renderWithClient(<ReferralsPage onOpenReferrer={vi.fn()} />);

    const generate = await screen.findByRole(
      "button",
      { name: "Generate export" },
      FIND_OPTS,
    );
    fireEvent.click(generate);

    expect(await screen.findByText(/^Exported /, undefined, FIND_OPTS)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Download JSON" })).toBeInTheDocument();
    // Lifetime total across all mock referrals: $162.95.
    const totals = screen.getAllByText("$162.95");
    expect(totals.length).toBeGreaterThan(0);
  });

  it("navigates to the referrer when a row is clicked", async () => {
    const onOpenReferrer = vi.fn();
    renderWithClient(<ReferralsPage onOpenReferrer={onOpenReferrer} />);

    const code = await screen.findAllByText("REF-NOVA4417", undefined, FIND_OPTS);
    const first = code[0];
    expect(first).toBeDefined();
    fireEvent.click(first!);
    expect(onOpenReferrer).toHaveBeenCalledWith("b2c3d4e5-1a2b-4c3d-8e4f-202020202002");
  });
});

describe("ProgramSection empty state", () => {
  it("shows the create CTA when the program GET 404s (no program yet)", async () => {
    resetReferralsMockState({ program: null });
    renderWithClient(<ProgramSection />);

    expect(
      await screen.findByText("No referral program yet", undefined, FIND_OPTS),
    ).toBeInTheDocument();
    const cta = screen.getByRole("button", { name: "Create program" });
    fireEvent.click(cta);
    expect(
      await screen.findByText("Create referral program", undefined, FIND_OPTS),
    ).toBeInTheDocument();
    // The polymorphic reward input defaults to the share flavour.
    expect(screen.getByLabelText("Reward percentage")).toBeInTheDocument();
  });
});
