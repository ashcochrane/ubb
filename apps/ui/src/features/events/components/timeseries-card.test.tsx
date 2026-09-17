import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { ReactElement } from "react";

import { UNRECOGNISED_MARK } from "@/components/shared/open-set-value";
import { groupingOptionsQueryOptions } from "@/hooks/use-grouping-options";
import { axisRequestWord, FIELD_KIND, ROLLUP_KIND } from "@/lib/grouping-axis";
import type { GroupingOption } from "@/lib/grouping-axis";

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
