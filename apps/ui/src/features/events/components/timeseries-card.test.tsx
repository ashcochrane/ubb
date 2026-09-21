import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { ReactElement } from "react";

import { UNRECOGNISED_MARK } from "@/components/shared/open-set-value";
import {
  groupingOptionsQueryOptions,
  MOCK_GROUPING_OPTIONS,
} from "@/hooks/use-grouping-options";
import { MEASUREMENT_CONCEPT_AXIS } from "@/lib/economic-query";
import { axisRequestWord, FIELD_KIND, ROLLUP_KIND } from "@/lib/grouping-axis";
import type { GroupingOption } from "@/lib/grouping-axis";

import {
  completePriceTotal,
  completeTotal,
  revenueUnavailableAtThisGrain,
} from "@/lib/economic-scenarios";

import { MEASUREMENT_HORIZON } from "../api/mock-data";
import { eventsApi } from "../api/provider";
import { TimeseriesCard } from "./timeseries-card";

// The chart itself is lazy and irrelevant here — this is a test about the axis
// list the picker offers, which is decided before any data arrives.
vi.mock("./usage-timeseries-chart", () => ({
  default: () => <div data-testid="chart" />,
}));

const WINDOW = { start_date: "2026-07-01", end_date: "2026-07-23" };

/** One row of the discovery contract. The BASE is typed; only the overrides
 *  escape, so that a value newer than this build's generated union can be
 *  handed to it — see `lib/grouping-axis.test.ts`, which explains why that is
 *  reachable and why casting the whole literal would have given away the half
 *  worth keeping. */
const BASE_AXIS: GroupingOption = {
  key: "field:provider",
  kind: FIELD_KIND,
  label: "",
  rollup: null,
  source_grain: "event",
  supported_surfaces: ["analytics"],
  unsupported_measures: [],
  max_cardinality: null,
};

function axis(key: string, over: Record<string, unknown> = {}): GroupingOption {
  return { ...BASE_AXIS, key, ...over } as GroupingOption;
}

const field = (name: string, label = "") =>
  axis(axisRequestWord({ kind: FIELD_KIND, name }), { label });
const rollup = (name: string) =>
  axis(axisRequestWord({ kind: ROLLUP_KIND, name }),
       { kind: ROLLUP_KIND, rollup: name });

/** What one workspace's discovery contract answers. */
const ACME = [
  field("provider"),
  field("model", "model"),
  field("region", "region"),
  rollup("event_category"),
];

/** Another workspace, which declared different axes. */
const HELIOS = [field("provider"), field("tier", "tier")];

function renderCard(
  options: GroupingOption[],
  onGroupByChange = vi.fn(),
  groupBy?: string,
) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  // Seeded rather than stubbed: the component reads through the real hook, so
  // the query key it asks under is part of what this proves.
  client.setQueryData(groupingOptionsQueryOptions.queryKey, options);
  const ui: ReactElement = (
    <TimeseriesCard
      window={WINDOW}
      groupBy={groupBy}
      onGroupByChange={onGroupByChange}
    />
  );
  render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
  return { onGroupByChange };
}

/** Open the picker and hand back the axes it offers. */
function openPicker(): HTMLElement[] {
  fireEvent.click(screen.getByRole("combobox", { name: "Group chart by" }));
  return screen.getAllByRole("option");
}

const textOf = (options: HTMLElement[]) =>
  options.map((option) => option.textContent?.trim() ?? "");


describe("the group-by picker's axis list", () => {
  it("offers this tenant's declared axes and the rollups, each marked", async () => {
    renderCard(ACME);

    expect(textOf(openPicker())).toEqual([
      "No grouping",
      "ProviderField",
      "modelField",
      "regionField",
      "Event CategoryRoll-up",
    ]);
  });

  it("offers a different workspace a different list", () => {
    // The point of the discovery contract: the axes are the TENANT's, computed
    // per tenant, never a list UBB ships. A picker that answered the same
    // either way would have made the whole endpoint decoration.
    renderCard(HELIOS);

    expect(textOf(openPicker())).toEqual([
      "No grouping",
      "ProviderField",
      "tierField",
    ]);
  });

  it("offers no physical slot name, whatever the tenant has declared", () => {
    // The list this replaced was written into `@/lib/labels` and held `dim1`,
    // `dim2` and `dim3` — the SLOTS a declared key binds to, offered as axes to
    // every workspace including ones that had declared nothing at all. Neither
    // that list nor the map wording it had anything to do with what a tenant
    // could actually group by, and nothing failed while it was wrong.
    renderCard(ACME);
    const offered = textOf(openPicker());

    expect(offered.length).toBeGreaterThan(1);
    for (const text of offered) {
      // The slot token itself, and the shape the deleted map gave it — a noun
      // with a slot NUMBER after it, which is the tell that a console was
      // wording a storage location rather than an axis somebody declared.
      // ⚠ Written as a shape rather than spelled out: the singular of the word
      // that map was named for is a retired term under a SPREAD ceiling, and a
      // new file spelling it fails the sweep before any payment is attempted.
      expect(text).not.toMatch(/\bdim\d\b/i);
      expect(text).not.toMatch(/^\S+\s\d+$/);
    }
  });

  it("offers each axis under its whole request word, kind and all", () => {
    // ⚠ ASSERTED THROUGH THE TRIGGER, which is the only place this widget
    // exposes what an option's VALUE is: the item elements carry the value in
    // React state rather than in an attribute. Handing the card a request word
    // selects the item whose value equals it, so the trigger showing that
    // axis's words is the picker saying "this is what I would submit". Under
    // the retired vocabulary the values were bare names — `provider`, not
    // `field:provider` — and the call site prefixed one on the way out, which
    // a rollup could never have survived.
    renderCard(ACME, vi.fn(), "rollup:event_category");

    const trigger = screen.getByRole("combobox", { name: "Group chart by" });
    expect(trigger).toHaveTextContent("Event Category");
    expect(trigger).not.toHaveTextContent("No grouping");
  });

  it("marks an axis this tenant does not offer rather than naming it", () => {
    // A bookmark from before the tenant retired an axis, or a link from
    // another workspace. Left to itself this widget prints the raw value — the
    // whole request word, `field:tier`, in the chart's own header — so the
    // trigger goes through the same lookup the list does. The chart below is
    // still asking for it and the server will answer; the header's job is not
    // to invent a name for it.
    renderCard(ACME, vi.fn(), "field:tier");

    const trigger = screen.getByRole("combobox", { name: "Group chart by" });
    expect(trigger).toHaveTextContent("field:tier");
    expect(trigger).toHaveTextContent(UNRECOGNISED_MARK);
    expect(trigger).not.toHaveTextContent("No grouping");
  });
});

describe("an axis this console has no words for", () => {
  it("renders as the token, marked, and never title-cased into English", () => {
    // Two ways this happens and both are ordinary: a tenant declares an axis
    // (its own word, and UBB must never invent one), and a server ahead of
    // this build answers a reserved axis or a rollup that postdates it.
    renderCard([axis("field:federation_id"), rollup("supplier_family")]);

    const options = openPicker();
    const texts = textOf(options);

    expect(texts[1]).toContain("federation_id");
    expect(texts[1]).toContain(UNRECOGNISED_MARK);
    expect(texts[1]).not.toContain("Federation id");
    expect(texts[2]).toContain("supplier_family");
    expect(texts[2]).toContain(UNRECOGNISED_MARK);
    expect(texts[2]).not.toContain("Supplier family");

    // Through the one helper, which is what carries the mark.
    expect(options[1]?.querySelector("[data-label]"))
      .toHaveAttribute("data-label", "unfamiliar");
  });

  it("leaves a tenant's own word unmarked, because nothing about it is unknown", () => {
    renderCard([field("model", "model")]);

    const option = openPicker()[1];
    expect(option?.textContent).toContain("model");
    expect(option?.textContent).not.toContain(UNRECOGNISED_MARK);
    expect(option?.querySelector("[data-axis]"))
      .toHaveAttribute("data-axis", "tenant");
  });
});

// ⚠ THE PRUNED SERIES (#510; slice 7 §19). A grouping by what was measured
// reads the measurement records, which the shorter clock releases — so over a
// stretch before the measurement horizon the answer has NO ROWS (#500), and
// this card used to call that "No usage recorded in this window". The data is
// the events mock's, which groups its seeds by their own measurement bags: the
// May seed is `prunedMeasurements()`, its bag is empty because its record was
// removed, and it therefore contributes nothing to that grouping — the same
// answer a server gives. The same window, ungrouped, is economic and held.
describe("a series whose measurement records were pruned", () => {
  function renderOver(window: { start_date: string; end_date: string }, groupBy?: string) {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    client.setQueryData(groupingOptionsQueryOptions.queryKey, MOCK_GROUPING_OPTIONS);
    const { container } = render(
      <QueryClientProvider client={client}>
        <TimeseriesCard window={window} groupBy={groupBy} onGroupByChange={vi.fn()} />
      </QueryClientProvider>,
    );
    return container;
  }

  const MAY = { start_date: "2026-05-01", end_date: "2026-05-31" };

  it("renders as pruned, never as no usage", async () => {
    const container = renderOver(MAY, MEASUREMENT_CONCEPT_AXIS);

    expect(
      await screen.findByText(/have been pruned at their retention horizon/, undefined, { timeout: 5000 }),
    ).toHaveTextContent("it is not a stretch with no usage");
    expect(screen.queryByText(/No usage recorded/)).not.toBeInTheDocument();
    expect(container.querySelector("[data-retention-horizon]"))
      .toHaveAttribute("data-retention-horizon", MEASUREMENT_HORIZON);
  });

  // One clock, two grains: the economic records of the same stretch are held,
  // so the ungrouped chart draws them and says nothing was pruned.
  it("draws the same stretch ungrouped, where nothing was released", async () => {
    const container = renderOver(MAY);

    expect(await screen.findByTestId("chart", undefined, { timeout: 5000 })).toBeInTheDocument();
    expect(container.querySelector("[data-retention-horizon]")).toBeNull();
  });

  it("draws what it holds and says where the pruned stretch ends", async () => {
    const container = renderOver({ start_date: "2026-05-01", end_date: "2026-07-23" }, MEASUREMENT_CONCEPT_AXIS);

    expect(await screen.findByTestId("chart", undefined, { timeout: 5000 })).toBeInTheDocument();
    expect(container.querySelector("[data-retention-horizon]"))
      .toHaveAttribute("data-retention-horizon", MEASUREMENT_HORIZON);
    expect(container.querySelector("[data-plotted-measure]")).toHaveTextContent(
      "Lines: Recorded events by group, per day. This axis answers no money.",
    );
  });
});

// ⚠ REVENUE A GROUPING CANNOT PLACE (#510). Grouped by a supplier, a
// subscription names none, so every row's revenue reads unavailable at that
// grain: the lines draw the supplier cost, the caption names the revenue's
// state, and the subscription is stated as the coarser figure — never dropped,
// and never drawn as the placed part of itself.
describe("a grouped chart whose revenue cannot be placed", () => {
  it("draws the cost, names the revenue's state and states the context", async () => {
    const subscription = {
      source: "subscription",
      customer_id: "c1",
      amount_micros: 199_000_000,
      window_start: WINDOW.start_date,
      window_end: WINDOW.end_date,
      attributable_axes: ["customer"],
      attributable_bucket: "day",
    };
    const row = (group: string, cost: number, revenue: number) => ({
      bucket_start: "2026-07-01T00:00:00Z",
      grouping_field_value: [group],
      grouping_field_value_status: ["recorded"],
      measures: revenueUnavailableAtThisGrain({
        cost: completeTotal(cost),
        revenue: completePriceTotal(revenue),
        events: 1,
        context: [subscription],
      }).measures.filter((entry) => entry.measure !== "recorded_events"),
    });
    vi.spyOn(eventsApi, "getUsageTimeseries").mockResolvedValueOnce({
      period_start: WINDOW.start_date,
      period_end: WINDOW.end_date,
      group_by: ["field:provider"],
      bucket: "day",
      basis: "recorded",
      economic_data_available_from: "2020-07-01",
      measurement_data_available_from: MEASUREMENT_HORIZON,
      rows: [row("openai", 70_000_000, 90_000_000), row("anthropic", 60_000_000, 80_000_000)],
      context: [subscription],
    });

    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    client.setQueryData(groupingOptionsQueryOptions.queryKey, ACME);
    const { container } = render(
      <QueryClientProvider client={client}>
        <TimeseriesCard window={WINDOW} groupBy="field:provider" onGroupByChange={vi.fn()} />
      </QueryClientProvider>,
    );

    expect(await screen.findByTestId("chart", undefined, { timeout: 5000 })).toBeInTheDocument();
    const caption = container.querySelector("[data-plotted-measure]");
    expect(caption).toHaveAttribute("data-plotted-measure", "supplier_cogs");
    expect(caption).toHaveTextContent(
      "Lines: Supplier COGS by group, per day. Customer revenue by group: Unavailable at this grain.",
    );
    expect(container.querySelector("[data-revenue-context]")).toHaveTextContent(
      "$199.00 of revenue from subscriptions can only be placed by customer, per day",
    );
  });
});