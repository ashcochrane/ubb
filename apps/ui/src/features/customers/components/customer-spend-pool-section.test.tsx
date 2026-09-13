// The customer's Billing tab renders the pool under the family's noun with
// its level in words, the different-questions sentence, the fixed-price
// sentence, the status pair with unknown revenue shown as excluded, the mode
// as the catalogue's word, and a declaration form over the registry's two
// modes (#468; slice 6 §4, §18; Testing Decisions claim 4's console half).
//
// THE PAIRS ARE ASSEMBLED HERE, NOT TAKEN FROM THE MOCK: the provider is
// stubbed and each standing is composed in the test from
// `spendPoolAssessment` — the composer's consumer on this surface (spec §18)
// — so every pair below is one the kernel would conclude. The words are
// SPELLED here rather than asked of the binding, so a binding pointed at the
// wrong concept's keys goes red rather than green. The one test that saves
// runs against the feature's real mock, so the declaration lands where the
// next read finds it.

import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import {
  completePriceTotal,
  incompletePriceTotal,
  spendPoolAssessment,
} from "@/lib/economic-scenarios";

import { CUS_ACME, CUS_LUNA } from "../api/mock-data";
import type { CustomerSpendPoolOut, CustomerSpendPoolStatusOut } from "../api/types";
import { renderWithProviders } from "../test-utils";
import {
  CustomerSpendPoolSection,
  POOL_STANDING_TITLE,
} from "./customer-spend-pool-section";

const provider = vi.hoisted(() => ({
  getCustomerSpendPool: vi.fn(),
  getCustomerSpendPoolStatus: vi.fn(),
}));

vi.mock("../api/provider", async () => {
  const mock = await vi.importActual<typeof import("../api/mock")>("../api/mock");
  provider.getCustomerSpendPool.mockImplementation(mock.getCustomerSpendPool);
  provider.getCustomerSpendPoolStatus.mockImplementation(mock.getCustomerSpendPoolStatus);
  return {
    customersApi: {
      ...mock,
      getCustomerSpendPool: provider.getCustomerSpendPool,
      getCustomerSpendPoolStatus: provider.getCustomerSpendPoolStatus,
    },
  };
});

const SLOW = { timeout: 5000 };

const NONE_DECLARED: CustomerSpendPoolOut = {
  cap_micros: 0,
  enforce_mode: "alert_only",
  hard_stop_pct: 100,
  alert_levels: [],
  fail_closed: false,
};

const ACME_DECLARED: CustomerSpendPoolOut = {
  cap_micros: 500_000_000,
  enforce_mode: "blocking",
  hard_stop_pct: 100,
  alert_levels: [50, 80, 100],
  fail_closed: false,
};

function serve(declared: CustomerSpendPoolOut, status: CustomerSpendPoolStatusOut) {
  provider.getCustomerSpendPool.mockResolvedValueOnce(declared);
  provider.getCustomerSpendPoolStatus.mockResolvedValueOnce(status);
}

async function standing() {
  renderWithProviders(<CustomerSpendPoolSection customerId={CUS_ACME} />);
  return screen.findByRole("region", { name: POOL_STANDING_TITLE }, SLOW);
}

describe("the level, in words", () => {
  it("says a pool declared on the customer is theirs", async () => {
    serve(
      ACME_DECLARED,
      spendPoolAssessment({ period: "2026-07", ...ACME_DECLARED, known: completePriceTotal(231_400_000) }),
    );
    const region = await standing();
    expect(region).toHaveAttribute("data-pool-level", "declared_here");
    expect(within(region).getByText(/^Declared on this customer\./)).toBeInTheDocument();
  });

  it("says the workspace default for seats applies where none is declared here", async () => {
    serve(
      NONE_DECLARED,
      spendPoolAssessment({
        period: "2026-07",
        cap_micros: 2_500_000_000,
        enforce_mode: "alert_only",
        hard_stop_pct: 120,
        alert_levels: [50, 80, 100],
        known: completePriceTotal(41_200_000),
      }),
    );
    const region = await standing();
    expect(region).toHaveAttribute("data-pool-level", "seat_default");
    expect(
      within(region).getByText(/No pool is declared on this customer, so the workspace default for seats applies/),
    ).toBeInTheDocument();
    expect(within(region).getByText("$41.20")).toHaveAttribute("data-reading", "figure");
    expect(within(region).getByText(/of \$2,500\.00/)).toBeInTheDocument();
  });

  it("says no pool applies where none reaches the customer, and still reads the charges", async () => {
    serve(
      NONE_DECLARED,
      spendPoolAssessment({ period: "2026-07", ...NONE_DECLARED, known: completePriceTotal(55_900_000) }),
    );
    const region = await standing();
    expect(region).toHaveAttribute("data-pool-level", "none");
    expect(within(region).getByText(/^No pool applies to this customer/)).toBeInTheDocument();
    // The charges are real whether or not a pool bounds them; the assessment is not.
    expect(within(region).getByText("$55.90")).toHaveAttribute("data-reading", "figure");
    expect(region.querySelector("[data-pool-figure]")).toBeNull();
    expect(region.querySelector("[data-pool-mode]")).toBeNull();
    expect(region.querySelector("[data-pool-posture]")).toBeNull();
    expect(region.textContent).not.toMatch(/0%|\$0\.00/);
  });
});

describe("the two sentences that keep the pool apart from the wallet", () => {
  it("labels the pool and the wallet's affordability as answering different questions", async () => {
    renderWithProviders(<CustomerSpendPoolSection customerId={CUS_ACME} />);
    expect(
      await screen.findByText(
        /^The pool answers a different question from the wallet's affordability\./,
        undefined,
        SLOW,
      ),
    ).toBeInTheDocument();
  });

  it("says the pool is blind to an agreed price until delivery, where the reservation is not", async () => {
    renderWithProviders(<CustomerSpendPoolSection customerId={CUS_ACME} />);
    expect(
      await screen.findByText(
        /^The pool is blind to work sold at one agreed price until that work is delivered; the wallet's reservation sees the price at start\./,
        undefined,
        SLOW,
      ),
    ).toBeInTheDocument();
  });
});

describe("the status pair", () => {
  it("renders a crossed pool's pair as a floor with the unknown revenue excluded, never as zero", async () => {
    serve(
      ACME_DECLARED,
      spendPoolAssessment({
        period: "2026-07",
        ...ACME_DECLARED,
        known: incompletePriceTotal(517_500_000, 1),
      }),
    );
    const region = await standing();

    expect(within(region).getByText("at least $517.50")).toHaveAttribute("data-reading", "floor");
    expect(within(region).getByText(/of \$500\.00/)).toBeInTheDocument();
    expect(region.querySelector("[data-pool-excluded]")).toHaveTextContent(
      "1 posting whose revenue UBB has not resolved is excluded from the known figure, not counted as zero.",
    );
    expect(region.querySelector('[data-pool-figure="used"]')).toHaveTextContent("at least 103%");
    // Past the line the headroom is a settled zero, even under a floor pair.
    expect(region.querySelector('[data-pool-figure="headroom"]')).toHaveTextContent("$0.00");
    expect(region.querySelector('[data-pool-figure="headroom"]')).not.toHaveTextContent(/at most/);
    // The mode as the catalogue's word, and the posture in a sentence.
    expect(region.querySelector('[data-pool-mode="blocking"]')).toHaveTextContent("Blocking");
    expect(region.querySelector('[data-pool-posture="blocking"]')).toHaveTextContent(/^This pool stops:/);
    expect(region.querySelector("[data-pool-blocking]")).toHaveTextContent(
      /new starts for this customer are being refused\.$/,
    );
  });

  it("renders a whole pair as figures under an alerting pool, with no exclusion and no refusal", async () => {
    serve(
      { ...ACME_DECLARED, enforce_mode: "alert_only" },
      spendPoolAssessment({
        period: "2026-07",
        ...ACME_DECLARED,
        enforce_mode: "alert_only",
        known: completePriceTotal(231_400_000),
      }),
    );
    const region = await standing();

    expect(within(region).getByText("$231.40")).toHaveAttribute("data-reading", "figure");
    expect(region.querySelector('[data-pool-figure="used"]')).toHaveTextContent("46%");
    expect(region.querySelector('[data-pool-figure="headroom"]')).toHaveTextContent("$268.60");
    expect(region.textContent).not.toMatch(/at least|at most/);
    expect(region.querySelector("[data-pool-excluded]")).toBeNull();
    expect(region.querySelector('[data-pool-mode="alert_only"]')).toHaveTextContent("Alert only");
    expect(region.querySelector('[data-pool-posture="alert_only"]')).toHaveTextContent(/never stops/);
    expect(region.querySelector("[data-pool-blocking]")).toBeNull();
  });

  it("says an alerting pool past its line refuses nothing", async () => {
    serve(
      { ...ACME_DECLARED, enforce_mode: "alert_only" },
      spendPoolAssessment({
        period: "2026-07",
        ...ACME_DECLARED,
        enforce_mode: "alert_only",
        known: completePriceTotal(517_500_000),
      }),
    );
    const region = await standing();
    expect(region.querySelector('[data-pool-figure="used"]')).toHaveTextContent("103%");
    expect(region.querySelector("[data-pool-blocking]")).toBeNull();
    expect(region.querySelector('[data-pool-posture="alert_only"]')).toHaveTextContent(
      /no start is refused by it/,
    );
  });

  it("renders known charges of nothing beside an unresolved posting as Unknown, never as $0.00", async () => {
    serve(
      ACME_DECLARED,
      spendPoolAssessment({
        period: "2026-07",
        ...ACME_DECLARED,
        known: incompletePriceTotal(0, 2),
      }),
    );
    const region = await standing();
    expect(within(region).getByText("Unknown")).toHaveAttribute("data-reading", "unknown");
    expect(region.querySelector("[data-pool-excluded]")).toHaveTextContent(/^2 postings whose revenue/);
    expect(within(region).queryByText("$0.00")).not.toBeInTheDocument();
  });

  it("draws no meter, no progress bar and no alert level", async () => {
    serve(
      ACME_DECLARED,
      spendPoolAssessment({
        period: "2026-07",
        ...ACME_DECLARED,
        known: incompletePriceTotal(517_500_000, 1),
      }),
    );
    await standing();
    for (const role of ["meter", "progressbar", "alert", "status", "alertdialog"]) {
      expect(screen.queryByRole(role)).not.toBeInTheDocument();
    }
    expect(document.body.textContent).not.toMatch(/warning|amber|threshold reached/i);
  });
});

describe("the declaration", () => {
  it("offers the registry's two modes as the catalogue's words and saves the whole declaration", async () => {
    renderWithProviders(<CustomerSpendPoolSection customerId={CUS_ACME} />);
    // Prefilled from the mock's declaration: acme's pool is blocking at $500.
    const cap = await screen.findByLabelText(/Monthly cap/, undefined, SLOW);
    await waitFor(() => expect(cap).toHaveValue("500"));
    expect(screen.getByRole("combobox", { name: "Enforce mode" })).toHaveTextContent("Blocking");

    fireEvent.change(cap, { target: { value: "750" } });
    fireEvent.click(screen.getByRole("button", { name: "Save pool" }));

    // The declaration landed where the next read finds it, every field sent.
    const mock = await vi.importActual<typeof import("../api/mock")>("../api/mock");
    await waitFor(async () => {
      expect(await mock.getCustomerSpendPool(CUS_ACME)).toEqual({
        ...ACME_DECLARED,
        cap_micros: 750_000_000,
      });
    }, SLOW);
  });

  it("prefills an undeclared pool as an amount of nothing in the default mode", async () => {
    renderWithProviders(<CustomerSpendPoolSection customerId={CUS_LUNA} />);
    const cap = await screen.findByLabelText(/Monthly cap/, undefined, SLOW);
    await waitFor(() => expect(cap).toHaveValue("0"));
    expect(screen.getByRole("combobox", { name: "Enforce mode" })).toHaveTextContent("Alert only");
  });
});
