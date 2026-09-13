// Utilisation and headroom renders each of the four ceiling statuses as
// itself, counts the indeterminate work and says its share, labels the
// pool's pair as answering a different question from the wallet's
// affordability, implies no threshold and no amber state, and never renders
// unknown money as a currency figure (#467; slice 6 §3, §14, §18; Testing
// Decisions claims 13 and 15; DoD 7).
//
// THE FIXTURES ARE ASSEMBLED HERE, NOT TAKEN FROM THE MOCK: the provider is
// stubbed and each report is composed in the test from `ceilingAssessment`
// — the composer's second consumer (spec §18) — through the same
// `utilisationRow` / `utilisationReport` the mock composes with, so every
// row below is one the backend can write and the aggregate is the route's
// own rule over exactly the rows shown. The words are the catalogue's
// (`ceiling_status.*`), spelled here rather than asked of the binding, so a
// binding pointed at the wrong concept's keys goes red rather than green.

import { screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ceilingAssessment, completeTotal, incompletePriceTotal, incompleteTotal } from "@/lib/economic-scenarios";
import { ABSENT_LABEL } from "@/lib/localisation";
import { UNKNOWN_TOTAL } from "@/lib/total-reading";

import {
  CUSTOMER_ACME,
  CUSTOMER_LUNA,
  POOL_STATUS_ACME,
  poolStatus,
  utilisationReport,
  utilisationRow,
} from "../api/mock-data";
import type { CeilingUtilisationRow, UtilisationAndHeadroom as Report } from "../api/types";
import {
  INDETERMINATE_HAS_NO_OTHER_HOME,
  NO_COMPLETED_WORK,
  POOL_AND_WALLET_DIFFER,
  STARTS_REFUSED,
} from "../lib/utilisation";
import { renderWithProviders } from "../test-utils";
import { POOL_PAIR_TITLE, UtilisationAndHeadroom } from "./utilisation-and-headroom";

const provider = vi.hoisted(() => ({ getUtilisationAndHeadroom: vi.fn() }));

vi.mock("../api/provider", async () => {
  const mock = await vi.importActual<typeof import("../api/mock")>("../api/mock");
  return {
    spendControlsApi: { ...mock, getUtilisationAndHeadroom: provider.getUtilisationAndHeadroom },
  };
});

const WINDOW = { since: "2026-07-01T00:00:00Z", until: "2026-08-01T00:00:00Z" };
const CEILING = 3_000_000;
const A_CURRENCY_FIGURE = /[$£€]\s*-?[\d,]/;

/** The four statuses, one unit each, composed from the amounts that fix them. */
const UNIT_NOT_APPLICABLE = "11111111-1111-4111-8111-111111111111";
const UNIT_WITHIN = "22222222-2222-4222-8222-222222222222";
const UNIT_INDETERMINATE = "33333333-3333-4333-8333-333333333333";
const UNIT_REACHED = "44444444-4444-4444-8444-444444444444";
const UNIT_COST_UNKNOWN = "55555555-5555-4555-8555-555555555555";

function completed(id: string, at: string, assessment: Parameters<typeof utilisationRow>[0]["assessment"]) {
  return utilisationRow({ id, customer: CUSTOMER_ACME, kind: "video-render", completedAt: at, assessment });
}

const FOUR_STATUSES: readonly CeilingUtilisationRow[] = [
  completed(UNIT_NOT_APPLICABLE, "2026-07-02T10:00:00Z", ceilingAssessment("not_applicable", { cost: completeTotal(180_000) })),
  completed(UNIT_WITHIN, "2026-07-03T10:00:00Z", ceilingAssessment("within_ceiling", { ceiling_micros: CEILING, cost: completeTotal(2_100_000) })),
  completed(UNIT_INDETERMINATE, "2026-07-04T10:00:00Z", ceilingAssessment("indeterminate", { ceiling_micros: CEILING, cost: incompleteTotal(1_240_000, 1) })),
  completed(UNIT_REACHED, "2026-07-05T10:00:00Z", ceilingAssessment("ceiling_reached", { ceiling_micros: CEILING, cost: incompleteTotal(3_420_000, 1) })),
];

function serve(report: Report) {
  provider.getUtilisationAndHeadroom.mockReset();
  provider.getUtilisationAndHeadroom.mockResolvedValue(report);
}

async function rendered(filters: Parameters<typeof UtilisationAndHeadroom>[0]["filters"] = {}) {
  const view = renderWithProviders(<UtilisationAndHeadroom filters={filters} />);
  await screen.findByText(/Work that completed between/);
  return view;
}

function unitRow(id: string): HTMLElement {
  const row = document.querySelector<HTMLElement>(`tr[data-unit="${id}"]`);
  if (!row) throw new Error(`no row for ${id}`);
  return row;
}

function cell(row: HTMLElement, name: string): HTMLElement {
  const found = row.querySelector<HTMLElement>(`[data-cell="${name}"]`);
  if (!found) throw new Error(`no ${name} cell`);
  return found;
}

function aggregate(name: string): HTMLElement {
  const found = document.querySelector<HTMLElement>(`[data-aggregate="${name}"]`);
  if (!found) throw new Error(`no ${name} aggregate`);
  return found;
}

describe("UtilisationAndHeadroom — the four statuses, one fixture and one assertion each", () => {
  // `not_applicable` is nothing evaluated — never within, never
  // indeterminate — and its ceiling, share and headroom are null on the
  // wire, so none of those three cells may render as money or as a share.
  it("says Not applicable where no ceiling applies — never Within ceiling, and no figure for it", async () => {
    serve(utilisationReport(FOUR_STATUSES, WINDOW, null));
    await rendered();

    const row = unitRow(UNIT_NOT_APPLICABLE);
    const status = cell(row, "status").querySelector("[data-reading]");
    expect(status).toHaveAttribute("data-reading", "not_applicable");
    expect(status).toHaveTextContent("Not applicable");
    expect(status).not.toHaveTextContent(/within/i);
    expect(status).not.toHaveTextContent(/indeterminate/i);
    for (const name of ["ceiling", "utilisation", "headroom"]) {
      expect(cell(row, name)).toHaveTextContent(ABSENT_LABEL);
      expect(cell(row, name).textContent).not.toMatch(A_CURRENCY_FIGURE);
      expect(cell(row, name).textContent).not.toMatch(/%/);
    }
    expect(row.textContent).not.toContain("$0.00");
  });

  // Under `indeterminate` the share is a floor and the headroom a most, over
  // what is known: "at least" and "at most", and never "under" anything.
  it("says Indeterminate with at least on the share and at most on the headroom, never under", async () => {
    serve(utilisationReport(FOUR_STATUSES, WINDOW, null));
    await rendered();

    const row = unitRow(UNIT_INDETERMINATE);
    expect(cell(row, "status").querySelector("[data-reading]")).toHaveAttribute("data-reading", "indeterminate");
    expect(cell(row, "status")).toHaveTextContent("Indeterminate");
    expect(cell(row, "utilisation")).toHaveTextContent("at least 41%");
    expect(cell(row, "headroom")).toHaveTextContent("at most $1.76");
    expect(cell(row, "known_cost")).toHaveTextContent("at least $1.24");
    expect(row.textContent).not.toMatch(/\bunder\b/i);
  });

  it("says Ceiling reached on the known total alone, with a settled zero headroom", async () => {
    serve(utilisationReport(FOUR_STATUSES, WINDOW, null));
    await rendered();

    const row = unitRow(UNIT_REACHED);
    expect(cell(row, "status").querySelector("[data-reading]")).toHaveAttribute("data-reading", "ceiling_reached");
    expect(cell(row, "status")).toHaveTextContent("Ceiling reached");
    expect(cell(row, "utilisation")).toHaveTextContent("114%");
    expect(cell(row, "utilisation")).not.toHaveTextContent(/at least/);
    // Past the line the wire clamps the headroom at nothing: a SETTLED zero.
    expect(cell(row, "headroom")).toHaveTextContent("$0.00");
    expect(cell(row, "headroom")).not.toHaveTextContent(/at most/);
    expect(cell(row, "known_cost")).toHaveTextContent("at least $3.42");
  });

  it("says Within ceiling with the figures as figures", async () => {
    serve(utilisationReport(FOUR_STATUSES, WINDOW, null));
    await rendered();

    const row = unitRow(UNIT_WITHIN);
    expect(cell(row, "status").querySelector("[data-reading]")).toHaveAttribute("data-reading", "within_ceiling");
    expect(cell(row, "status")).toHaveTextContent("Within ceiling");
    expect(cell(row, "ceiling")).toHaveTextContent("$3.00");
    expect(cell(row, "utilisation")).toHaveTextContent("70%");
    expect(cell(row, "headroom")).toHaveTextContent("$0.90");
    expect(row.textContent).not.toMatch(/at least|at most/);
  });

  // ⚠ THE ASSERTION THIS SURFACE OWES ABOVE ALL (TD claim 15, DoD 7): a
  // known total none of whose parts UBB learned is unknown, and unknown
  // never renders as a currency figure — not as `$0.00`, not as `at least
  // $0.00`.
  it("renders an unknown known total as unknown, never as money", async () => {
    const row = completed(
      UNIT_COST_UNKNOWN,
      "2026-07-06T10:00:00Z",
      ceilingAssessment("indeterminate", { ceiling_micros: CEILING, cost: incompleteTotal(0, 2) }),
    );
    serve(utilisationReport([row], WINDOW, null));
    await rendered();

    const known = cell(unitRow(UNIT_COST_UNKNOWN), "known_cost").querySelector("[data-reading]");
    expect(known).toHaveAttribute("data-reading", "unknown");
    expect(known).toHaveTextContent(UNKNOWN_TOTAL);
    expect(known?.textContent).not.toMatch(A_CURRENCY_FIGURE);
    expect(unitRow(UNIT_COST_UNKNOWN).textContent).not.toContain("$0.00");
  });
});

describe("UtilisationAndHeadroom — the aggregate", () => {
  // The count the response carries is the count the page shows, and the
  // share beside it is the route's — two of three, rounded down.
  it("renders the indeterminate count and share the response carries", async () => {
    const rows = [
      completed(UNIT_WITHIN, "2026-07-03T10:00:00Z", ceilingAssessment("within_ceiling", { ceiling_micros: CEILING, cost: completeTotal(2_100_000) })),
      completed(UNIT_INDETERMINATE, "2026-07-04T10:00:00Z", ceilingAssessment("indeterminate", { ceiling_micros: CEILING, cost: incompleteTotal(1_240_000, 1) })),
      completed(UNIT_COST_UNKNOWN, "2026-07-06T10:00:00Z", ceilingAssessment("indeterminate", { ceiling_micros: CEILING, cost: incompleteTotal(0, 2) })),
    ];
    const report = utilisationReport(rows, WINDOW, null);
    expect(report.indeterminate_count).toBe(2);
    serve(report);
    await rendered();

    const indeterminate = aggregate("indeterminate");
    expect(indeterminate).toHaveAttribute("data-count", String(report.indeterminate_count));
    expect(indeterminate).toHaveTextContent("2 of 3 · 66%");
    expect(screen.getByText(INDETERMINATE_HAS_NO_OTHER_HOME)).toBeInTheDocument();

    // And the averages over rows that include an indeterminate one are
    // bounds: the mean of 70, 41 and 0 rounded down, said as a floor; the
    // mean of $0.90, $1.76 and $3.00 in micros, rounded down, said as a most.
    expect(aggregate("average_utilisation")).toHaveAttribute("data-bound", "floor");
    expect(aggregate("average_utilisation")).toHaveTextContent("at least 37%");
    expect(aggregate("average_headroom")).toHaveAttribute("data-bound", "most");
    expect(aggregate("average_headroom")).toHaveTextContent("at most $1.89");
    expect(aggregate("ceiling_reached")).toHaveTextContent("0 of 3 · 0%");
  });

  it("averages per unit and then across every unit, as figures where nothing was indeterminate", async () => {
    const rows = [
      completed(UNIT_WITHIN, "2026-07-03T10:00:00Z", ceilingAssessment("within_ceiling", { ceiling_micros: CEILING, cost: completeTotal(2_100_000) })),
      completed(UNIT_REACHED, "2026-07-05T10:00:00Z", ceilingAssessment("ceiling_reached", { ceiling_micros: 800_000, cost: completeTotal(1_600_000) })),
      completed(UNIT_NOT_APPLICABLE, "2026-07-02T10:00:00Z", ceilingAssessment("not_applicable", { cost: completeTotal(180_000) })),
    ];
    serve(utilisationReport(rows, WINDOW, null));
    await rendered();

    // (70 + 200) / 2 over the two that had a ceiling — the unit that cost
    // twice its ceiling weighs exactly one — and nothing evaluated weighs
    // nothing; the shares are of every unit listed.
    expect(aggregate("average_utilisation")).toHaveAttribute("data-bound", "figure");
    expect(aggregate("average_utilisation")).toHaveTextContent("135%");
    expect(aggregate("average_headroom")).toHaveTextContent("$0.45");
    expect(aggregate("ceiling_reached")).toHaveTextContent("1 of 3 · 33%");
    expect(aggregate("indeterminate")).toHaveTextContent("0 of 3 · 0%");
  });

  it("renders no average where no unit had a ceiling — an absence, never zero", async () => {
    const rows = [
      completed(UNIT_NOT_APPLICABLE, "2026-07-02T10:00:00Z", ceilingAssessment("not_applicable", { cost: completeTotal(180_000) })),
    ];
    serve(utilisationReport(rows, WINDOW, null));
    await rendered();

    expect(aggregate("average_utilisation")).toHaveTextContent(ABSENT_LABEL);
    expect(aggregate("average_utilisation").textContent).not.toMatch(/%/);
    expect(aggregate("average_headroom")).toHaveTextContent(ABSENT_LABEL);
    expect(aggregate("average_headroom").textContent).not.toMatch(A_CURRENCY_FIGURE);
  });
});

describe("UtilisationAndHeadroom — the pool's pair", () => {
  it("renders the pool pair beside the sentence that it answers a different question from the wallet's affordability", async () => {
    serve(utilisationReport(FOUR_STATUSES, WINDOW, POOL_STATUS_ACME));
    await rendered({ customer_id: CUSTOMER_ACME });

    const pool = screen.getByRole("region", { name: POOL_PAIR_TITLE });
    expect(pool).toHaveAttribute("data-pool-pair", "2026-07");
    // The pair: known charges a floor beside the one posting it could not
    // price, so the share is a floor — and the headroom past the line is a
    // SETTLED zero (the kernel clamps it, and an unpriced posting can only
    // lower a figure already at its floor), never "at most".
    expect(within(pool).getByText("at least $517.50")).toHaveAttribute("data-reading", "floor");
    expect(pool).toHaveTextContent("of $500.00");
    expect(pool.querySelector('[data-pool-figure="used"]')).toHaveTextContent("at least 103%");
    expect(pool.querySelector('[data-pool-figure="headroom"]')).toHaveTextContent("$0.00");
    expect(pool.querySelector('[data-pool-figure="headroom"]')).not.toHaveTextContent(/at most/);
    expect(within(pool).getByText(STARTS_REFUSED)).toBeInTheDocument();
    expect(within(pool).getByText(POOL_AND_WALLET_DIFFER)).toBeInTheDocument();
  });

  it("renders the pair as figures where every posting is priced, and no refusal under an alerting pool", async () => {
    const pool = poolStatus({
      period: "2026-07",
      cap_micros: 500_000_000,
      enforce_mode: "alert_only",
      hard_stop_pct: 100,
      alert_levels: [50, 80, 100],
      known: incompletePriceTotal(231_400_000, 0),
    });
    serve(utilisationReport(FOUR_STATUSES, WINDOW, pool));
    await rendered({ customer_id: CUSTOMER_ACME });

    const region = screen.getByRole("region", { name: POOL_PAIR_TITLE });
    expect(within(region).getByText("$231.40")).toHaveAttribute("data-reading", "figure");
    expect(region.querySelector('[data-pool-figure="used"]')).toHaveTextContent("46%");
    expect(region.querySelector('[data-pool-figure="headroom"]')).toHaveTextContent("$268.60");
    expect(region.textContent).not.toMatch(/at least|at most/);
    expect(within(region).queryByText(STARTS_REFUSED)).not.toBeInTheDocument();
  });

  it("renders the headroom as a most where the pair is a floor and the line is not yet reached", async () => {
    const pool = poolStatus({
      period: "2026-07",
      cap_micros: 500_000_000,
      enforce_mode: "blocking",
      hard_stop_pct: 100,
      alert_levels: [50, 80, 100],
      known: incompletePriceTotal(231_400_000, 2),
    });
    serve(utilisationReport(FOUR_STATUSES, WINDOW, pool));
    await rendered({ customer_id: CUSTOMER_ACME });

    const region = screen.getByRole("region", { name: POOL_PAIR_TITLE });
    expect(region.querySelector('[data-pool-figure="used"]')).toHaveTextContent("at least 46%");
    expect(region.querySelector('[data-pool-figure="headroom"]')).toHaveTextContent("at most $268.60");
    expect(within(region).queryByText(STARTS_REFUSED)).not.toBeInTheDocument();
  });

  it("renders no pair tenant-wide", async () => {
    serve(utilisationReport(FOUR_STATUSES, WINDOW, null));
    await rendered();

    expect(screen.queryByRole("region", { name: POOL_PAIR_TITLE })).not.toBeInTheDocument();
    expect(screen.queryByText(POOL_AND_WALLET_DIFFER)).not.toBeInTheDocument();
  });
});

describe("UtilisationAndHeadroom — no threshold, no amber, no warning", () => {
  // Enforcement is binary (#150 §9.4; #152 §4): the page renders nothing
  // that could read as a warning state — no meter, no progress bar, no
  // alert, no status region — even with a unit past its ceiling and a pool
  // at its line on the page.
  it("renders nothing of the kind, by role and by word", async () => {
    serve(utilisationReport(FOUR_STATUSES, WINDOW, POOL_STATUS_ACME));
    const { container } = await rendered({ customer_id: CUSTOMER_ACME });

    for (const role of ["meter", "progressbar", "alert", "status", "alertdialog"]) {
      expect(screen.queryAllByRole(role)).toEqual([]);
    }
    expect(container.textContent).not.toMatch(/warning|amber|threshold/i);
    expect(container.querySelector('[class*="danger"], [class*="bg-red"], [class*="amber"]')).toBeNull();
  });
});

describe("UtilisationAndHeadroom — the empty answer and the read", () => {
  it("answers no completed work with its sentence, and still the pair for a named customer", async () => {
    serve(utilisationReport([], WINDOW, POOL_STATUS_ACME));
    await rendered({ customer_id: CUSTOMER_ACME });

    expect(screen.getByText(NO_COMPLETED_WORK)).toBeInTheDocument();
    expect(document.querySelector("[data-aggregate]")).toBeNull();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    expect(screen.getByRole("region", { name: POOL_PAIR_TITLE })).toBeInTheDocument();
  });

  // The proof is the call: the component makes the read with the customer
  // and window it was handed and no family — the report takes none.
  it("applies the customer filter and the window through the read", async () => {
    serve(utilisationReport([], WINDOW, null));
    await rendered({ customer_id: CUSTOMER_LUNA, ...WINDOW });

    expect(provider.getUtilisationAndHeadroom).toHaveBeenCalledWith({
      customer_id: CUSTOMER_LUNA,
      ...WINDOW,
    });
  });
});
