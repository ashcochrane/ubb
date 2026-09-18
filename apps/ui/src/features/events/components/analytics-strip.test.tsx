// The events page's window totals, drawn as their states allow (#510; slice 7
// §19).
//
// The strip read four numbers coalesced to zero, so a window reaching back past
// the economic horizon printed "0" events and "$0.00" of revenue and cost —
// the silent zero this whole surface exists to delete, on the page a tenant
// opens to find out what happened. Each answer here is composed from
// `@/lib/economic-scenarios` and served through the provider, so the fixture
// is one the mock does not author and the narrowing is the real one.

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import type { ReactElement } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  completePriceTotal,
  incompleteMeasures,
  incompleteTotal,
  measuresOutsideRetentionHorizon,
  type EconomicMeasureScenario,
} from "@/lib/economic-scenarios";

import type { Economics } from "../api/types";
import { AnalyticsStrip } from "./analytics-strip";

const PARAMS = { start_date: "2014-07-01", end_date: "2014-07-31" };

let measures: EconomicMeasureScenario[] = [];

vi.mock("../api/provider", () => ({
  eventsApi: {
    getUsageAnalytics: async (): Promise<Economics> => ({
      period_start: PARAMS.start_date,
      period_end: PARAMS.end_date,
      group_by: [],
      bucket: null,
      basis: "recorded",
      economic_data_available_from: "2020-09-18",
      measurement_data_available_from: "2026-06-01",
      rows: [{ bucket_start: null, grouping_field_value: [], grouping_field_value_status: [], measures }],
      context: [],
    }),
  },
}));

afterEach(() => {
  measures = [];
});

function renderStrip(ui: ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

function card(label: string): HTMLElement {
  const node = screen.getByText(label).closest("[data-variant]");
  if (node === null) throw new Error(`no stat card labelled ${label}`);
  return node as HTMLElement;
}

describe("AnalyticsStrip", () => {
  it("draws a window past the horizon as out-of-horizon, never as zero", async () => {
    measures = measuresOutsideRetentionHorizon("2020-09-18");
    renderStrip(<AnalyticsStrip params={PARAMS} metadataFilterActive={false} />);

    expect(await screen.findByText("Events")).toBeInTheDocument();
    for (const label of ["Events", "Revenue", "Provider cost", "Gross margin"]) {
      const drawn = card(label);
      expect(within(drawn).getByText("Outside retention horizon")).toBeInTheDocument();
      expect(within(drawn).queryByText(/\$0\.00/)).not.toBeInTheDocument();
      expect(within(drawn).queryByText("0")).not.toBeInTheDocument();
    }
  });

  // ⚠ §15 — the margin is incomplete wherever the cost side is, whatever the
  // revenue beside it reads. A `known` revenue is not evidence the cost
  // resolved; #473 owns why it can read known at all.
  it("draws the margin as a bound while the revenue beside it reads known", async () => {
    measures = incompleteMeasures({
      cost: incompleteTotal(3_000_000, 2),
      revenue: completePriceTotal(8_000_000),
      events: 9,
    });
    renderStrip(<AnalyticsStrip params={PARAMS} metadataFilterActive={false} />);

    expect(await screen.findByText("$8.00")).toBeInTheDocument();
    expect(within(card("Provider cost")).getByText("at least $3.00")).toBeInTheDocument();
    expect(within(card("Gross margin")).getByText("at most $5.00")).toBeInTheDocument();
    expect(screen.queryByText("$5.00")).not.toBeInTheDocument();
  });
});
