// The five measure states, each composed from `@/lib/economic-scenarios` and
// rendered through the one component every economic surface draws them with
// (#510; slice 7 §19, #155 §9.2). The surfaces carry their own assertions; this
// is where each state's never-clause is held against the renderer itself.

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import {
  completePriceTotal,
  completeTotal,
  incompleteMeasures,
  incompleteTotal,
  knownMeasures,
  measureNotApplicable,
  measuresOutsideRetentionHorizon,
  revenueUnavailableAtThisGrain,
  type EconomicMeasureScenario,
} from "@/lib/economic-scenarios";
import {
  CUSTOMER_REVENUE,
  FIGURES_KEY,
  figureOn,
  GROSS_MARGIN,
  SUPPLIER_COGS,
  type EconomicRow,
} from "@/lib/economic-query";
import type { AnalyticsMeasure } from "@/lib/vocabulary";

import {
  MarginShare,
  MeasureTooltip,
  MeasureValue,
  RevenueContext,
} from "./measure-value";

function rowOf(measures: EconomicMeasureScenario[]): EconomicRow {
  return { grouping_field_value: [], grouping_field_value_status: [], measures };
}

/** Render one measure off a row, and hand back the node it drew. */
function drawn(
  measures: EconomicMeasureScenario[],
  measure: AnalyticsMeasure = CUSTOMER_REVENUE,
) {
  const { container } = render(
    <MeasureValue figure={figureOn(rowOf(measures), measure)} currency="usd" />,
  );
  return container;
}

describe("known — renders as the amount", () => {
  it("draws the figure, stated whole", () => {
    const node = drawn(knownMeasures({ cost_micros: 2_000_000, revenue_micros: 9_000_000, events: 3 }));
    expect(node.textContent).toBe("$9.00");
    expect(node.querySelector("[data-measure-state]")?.getAttribute("data-measure-state")).toBe("known");
  });

  // A genuine zero stays a genuine zero and produces a real loss against
  // known cost — the free service must not disappear.
  it("draws a known zero revenue as zero, and the loss it makes as a loss", () => {
    const measures = knownMeasures({ cost_micros: 2_000_000, revenue_micros: 0, events: 3 });
    expect(drawn(measures).textContent).toBe("$0.00");
    expect(drawn(measures, GROSS_MARGIN).textContent).toBe("-$2.00");
  });
});

describe("incomplete — renders as a floor with its count, never as a total", () => {
  const measures = incompleteMeasures({
    cost: incompleteTotal(4_000_000, 3),
    revenue: completePriceTotal(9_000_000),
    events: 10,
  });

  it("draws the cost as a floor, and names the count that makes it one", () => {
    const node = drawn(measures, SUPPLIER_COGS);
    expect(node.textContent).toBe("at least $4.00");
    expect(node.querySelector("[title]")?.getAttribute("title")).toMatch(/^3 events have/);
  });

  // ⚠ §15 — the margin is incomplete wherever the cost side is, EVEN WHEN the
  // revenue side reads known. A `known` revenue is not evidence the cost
  // resolved (#473 owns why it can read known at all).
  it("draws the margin as incomplete while the revenue beside it reads known", () => {
    expect(drawn(measures, CUSTOMER_REVENUE).textContent).toBe("$9.00");
    const margin = drawn(measures, GROSS_MARGIN);
    expect(margin.querySelector("[data-measure-state]")?.getAttribute("data-measure-state")).toBe("incomplete");
    expect(margin.textContent).toBe("at most $5.00");
  });
});

describe("unavailable at the requested grain — the state, with the coarser figure as context", () => {
  const composed = revenueUnavailableAtThisGrain({
    cost: completeTotal(1_000_000),
    revenue: completePriceTotal(4_000_000),
    events: 2,
    context: [{
      source: "subscription",
      customer_id: "c1",
      amount_micros: 50_000_000,
      window_start: "2026-07-01",
      window_end: "2026-07-31",
      attributable_axes: ["customer"],
      attributable_bucket: "month",
    }],
  });

  // ⚠ The wire carries the PLACED part of the revenue beside this state. It
  // is not the revenue, and drawing it would be a floor drawn as a total.
  it("never draws a currency amount for the revenue or the margin", () => {
    for (const measure of [CUSTOMER_REVENUE, GROSS_MARGIN] as const) {
      const node = drawn(composed.measures, measure);
      expect(node.textContent).toBe("Unavailable at this grain");
    }
  });

  it("states the money it could not place, and where it could", () => {
    render(<RevenueContext context={composed.context} currency="usd" />);
    expect(screen.getByText(/^\$50\.00 of revenue from subscriptions/)).toHaveTextContent(
      "can only be placed by customer, per month — so no margin is drawn at this grain.",
    );
  });

  it("carries the margin's state into its share rather than a 0%", () => {
    const row = rowOf(composed.measures);
    const { container } = render(
      <MarginShare margin={figureOn(row, GROSS_MARGIN)} revenue={figureOn(row, CUSTOMER_REVENUE)} />,
    );
    expect(container.textContent).toBe("Unavailable at this grain");
    expect(container.textContent).not.toMatch(/0(\.0)?%/);
  });
});

describe("not applicable — never known, never within anything", () => {
  it("draws the state and no figure", () => {
    const node = drawn([measureNotApplicable("gross_margin")], GROSS_MARGIN);
    expect(node.textContent).toBe("Not applicable");
  });
});

describe("outside the retention horizon — out-of-horizon with the day, never zero, never no usage", () => {
  const measures = measuresOutsideRetentionHorizon("2020-09-18");

  it.each([SUPPLIER_COGS, CUSTOMER_REVENUE, GROSS_MARGIN] as const)("draws %s as the state", (measure) => {
    const node = drawn(measures, measure);
    expect(node.textContent).toBe("Outside retention horizon");
    expect(node.querySelector("[title]")?.getAttribute("title")).toMatch(/from Sep 18, 2020/);
  });
});

describe("the chart tooltip — each series as its state allows", () => {
  // A line has a GAP where a figure is not stated, so the tooltip is the only
  // place the gap is named; and a state this build cannot read is marked here
  // exactly as it is in a card, through the one open-set helper.
  it("lists a gap as its state and marks an unfamiliar one", () => {
    const row = rowOf([
      ...measuresOutsideRetentionHorizon("2020-09-18", ["supplier_cogs"]),
      {
        measure: "customer_revenue",
        status: "estimated" as EconomicMeasureScenario["status"],
        amount_micros: 4_000_000,
      },
    ]);
    const { container } = render(
      <MeasureTooltip
        active
        payload={[{
          payload: {
            [FIGURES_KEY]: {
              cost: figureOn(row, SUPPLIER_COGS),
              revenue: figureOn(row, CUSTOMER_REVENUE),
            },
          },
        }]}
        label="2020-09-16"
        series={[
          { key: "revenue", name: "Revenue" },
          { key: "cost", name: "Provider cost" },
        ]}
        currency="usd"
        labelFormatter={(label) => String(label)}
      />,
    );

    expect(screen.getByText("Outside retention horizon")).toBeInTheDocument();
    expect(container.querySelector("[data-label]")).toHaveAttribute("data-label", "unfamiliar");
    expect(screen.getByText("Unrecognised")).toBeInTheDocument();
    expect(container.textContent).not.toMatch(/\$4\.00|\$0\.00/);
  });
});

describe("a state this build has never seen", () => {
  it("draws the token, marked, and no figure", () => {
    const node = drawn([
      {
        measure: "customer_revenue",
        // The wire's enum is closed today; a later server's is not (ADR-003).
        status: "estimated" as EconomicMeasureScenario["status"],
        amount_micros: 4_000_000,
      },
    ]);
    expect(node.querySelector("[data-label]")?.getAttribute("data-label")).toBe("unfamiliar");
    expect(node.textContent).toContain("estimated");
    expect(node.textContent).toContain("Unrecognised");
    expect(node.textContent).not.toMatch(/\$4\.00/);
  });
});
