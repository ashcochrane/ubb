// The dashboard's customer table, drawing a measure state the mock does not
// author (#510; slice 7 §19).
//
// ⚠ **A SIBLING OF THE TABLE'S OWN TEST, AND WHY.** `snapshot-severance.test.ts`
// holds `customer-economics-table.test.tsx` to importing the component alone,
// so that nothing it renders can arrive from a stub of the ALERTING read — the
// severed margin snapshot (#501, #507). A state the mock never serves needs a
// fixture the mock does not author, which means stubbing a read; so the stub
// lives here instead, and that guard holds THIS file to stubbing the one
// economic query and nothing else. The fixture is composed, never hand-typed.

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import { MONEY_MEASURES } from "@/lib/economic-query";
import { measuresOutsideRetentionHorizon } from "@/lib/economic-scenarios";

import { mockCustomerEconomics } from "../api/mock-data";
import { dashboardApi } from "../api/provider";
import { CustomerEconomicsTable } from "./customer-economics-table";

vi.mock("@tanstack/react-router", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@tanstack/react-router")>();
  return {
    ...actual,
    Link: (props: { to?: string; children?: ReactNode; className?: string }) => (
      <a className={props.className} href={props.to ?? "#"}>
        {props.children}
      </a>
    ),
  };
});

const WINDOW = { start_date: "2026-07-01", end_date: "2026-07-23" };

describe("CustomerEconomicsTable — the measure states", () => {
  // ⚠ A WINDOW PAST THE HORIZON: every cell of every row is its state, and none
  // is the zero the narrowing used to coalesce it to — nor the "0%" a margin
  // percentage computed for a margin UBB would not state.
  it("draws a window past the horizon as its state in every cell, never as zero", async () => {
    const served = mockCustomerEconomics(WINDOW);
    vi.spyOn(dashboardApi, "getCustomerEconomics").mockResolvedValueOnce({
      ...served,
      rows: served.rows.map((row) => ({
        ...row,
        measures: measuresOutsideRetentionHorizon("2020-09-18", [...MONEY_MEASURES]),
      })),
    });

    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <CustomerEconomicsTable window={WINDOW} currency="usd" />
      </QueryClientProvider>,
    );

    expect(await screen.findByText("1f0c9c4e…")).toBeInTheDocument();
    // Four figures per row, five rows.
    expect(screen.getAllByText("Outside retention horizon")).toHaveLength(20);
    expect(screen.queryByText("$0.00")).not.toBeInTheDocument();
    expect(screen.queryByText(/^0(\.0)?%$/)).not.toBeInTheDocument();
  });
});
