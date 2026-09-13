// Stops and breaches renders each of the three row shapes as itself, answers
// admission control with no rows, never renders unknown money as a currency
// figure, and applies the customer filter through the READ rather than in a
// second component (#466; slice 6 §14, §18; Testing Decisions claim 15).
//
// Driven through the feature's mock, whose rows are composed from the
// economic scenarios — so every amount below is one the backend can write.
// The provider is wrapped so the filter's proof is the call the component
// makes, not the rows the mock happened to answer: drop `customer_id` from
// the read and the assertion on the call goes red before the one on the rows.

import { fireEvent, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { formatEventMicros, shortId } from "@/lib/format";
import { costingStatusLabel } from "@/lib/supplier-cost";
import { UNKNOWN_TOTAL } from "@/lib/total-reading";

import {
  CROSSING_CHARGE_ID,
  CROSSING_POSTING_ID,
  CUSTOMER_ACME,
  CUSTOMER_LUNA,
  UNIT_KILLED,
  UNIT_KILLED_EARLIER,
} from "../api/mock-data";
import { CROSSING_REPLAYED, SOFT_FLOOR_MARKER } from "../lib/episodes";
import { NO_EPISODES_FOR } from "../lib/families";
import { renderWithProviders } from "../test-utils";
import { StopsAndBreaches } from "./stops-and-breaches";

const provider = vi.hoisted(() => ({ getStopsAndBreaches: vi.fn() }));

vi.mock("../api/provider", async () => {
  const mock = await vi.importActual<typeof import("../api/mock")>("../api/mock");
  provider.getStopsAndBreaches.mockImplementation(mock.getStopsAndBreaches);
  return {
    spendControlsApi: { ...mock, getStopsAndBreaches: provider.getStopsAndBreaches },
  };
});

const A_CURRENCY_FIGURE = /[$£€]\s*-?[\d,]/;

async function articles(): Promise<HTMLElement[]> {
  await screen.findByText(/Episodes that opened between/);
  return screen.getAllByRole("article");
}

function articleFor(shape: string, predicate: (article: HTMLElement) => boolean): HTMLElement {
  const match = screen
    .getAllByRole("article")
    .find((article) => article.dataset.shape === shape && predicate(article));
  if (!match) throw new Error(`no ${shape} article matched`);
  return match;
}

/**
 * The value beside a label in the card's detail list. Matched on the LABEL
 * element: two concepts can share a word (the family badge says "Ceiling"
 * and so does the row naming the ceiling pinned), and a page-wide text query
 * cannot say which it found.
 */
function valueBeside(article: HTMLElement, label: string): HTMLElement {
  const term = within(article)
    .getAllByText(label)
    .find((element) => element.tagName === "DT");
  const value = term?.parentElement?.querySelector("dd");
  if (!value) throw new Error(`${label} has no value`);
  return value;
}

describe("StopsAndBreaches — the three shapes", () => {
  it("renders a ceiling row explained by its unit and the events after the stop", async () => {
    renderWithProviders(<StopsAndBreaches filters={{ customer_id: CUSTOMER_ACME }} />);
    await articles();

    const row = articleFor("ceiling", (a) =>
      a.querySelector(`a[href="/tasks/runs/${UNIT_KILLED}"]`) !== null,
    );
    expect(row).toHaveAttribute("data-family", "ceiling");
    expect(valueBeside(row, "Ceiling")).toHaveTextContent("$3.00");
    expect(valueBeside(row, "Bounds")).toHaveTextContent("Cost");

    // Both pairs are floors beside the one event whose cost UBB never learned.
    const fired = valueBeside(row, "Known cost when it fired").querySelector("[data-reading]");
    expect(fired).toHaveAttribute("data-reading", "floor");
    expect(fired).toHaveTextContent("at least $3.05");
    const ended = valueBeside(row, "Known cost where it ended").querySelector("[data-reading]");
    expect(ended).toHaveAttribute("data-reading", "floor");
    expect(ended).toHaveTextContent("at least $3.42");

    // The events after the stop, itemised: the unlearned cost is NAMED, and
    // the row still shows what it billed.
    fireEvent.click(within(row).getByRole("button", { name: /Show events/ }));
    const table = within(row).getByRole("table");
    const rows = within(table).getAllByRole("row").slice(1);
    expect(rows).toHaveLength(2);
    expect(within(table).getByText(costingStatusLabel("unresolved"))).toBeInTheDocument();
    expect(within(table).getByText(formatEventMicros(41_000, "usd"))).toBeInTheDocument();
    expect(table.textContent).not.toContain("$0.00");
  });

  // ⚠ THE ASSERTION THIS SURFACE OWES ABOVE ALL: a pair the wire left null is
  // unknown, and unknown never renders as a currency figure.
  it("renders a crossed pair the announcement no longer carries as unknown, never as money", async () => {
    renderWithProviders(<StopsAndBreaches filters={{ customer_id: CUSTOMER_ACME }} />);
    await articles();

    const row = articleFor("ceiling", (a) =>
      a.querySelector(`a[href="/tasks/runs/${UNIT_KILLED_EARLIER}"]`) !== null,
    );
    const fired = valueBeside(row, "Known cost when it fired").querySelector("[data-reading]");
    expect(fired).toHaveAttribute("data-reading", "unknown");
    expect(fired).toHaveTextContent(UNKNOWN_TOTAL);
    expect(fired?.textContent).not.toMatch(A_CURRENCY_FIGURE);
    // The mechanism that applied it was not recorded either: an absence.
    expect(valueBeside(row, "Applied by").querySelector("[data-label]")).toHaveAttribute(
      "data-label",
      "absent",
    );
  });

  it("renders a pool row explained by its Charge and that Charge's posting", async () => {
    renderWithProviders(<StopsAndBreaches filters={{ customer_id: CUSTOMER_ACME }} />);
    await articles();

    const row = articleFor("customer_spend_pool", () => true);
    const crossedBy = valueBeside(row, "Crossed by");
    expect(crossedBy).toHaveTextContent(`Charge ${shortId(CROSSING_CHARGE_ID)}`);
    const posting = crossedBy.querySelector("a");
    expect(posting?.getAttribute("href")).toContain(`/events/${CROSSING_POSTING_ID}`);
    // Found by replaying the period's charges, and the card says so.
    expect(crossedBy.querySelector("[data-crossing]")).toHaveAttribute("data-crossing", "replayed");
    expect(crossedBy).toHaveTextContent(CROSSING_REPLAYED);
    expect(valueBeside(row, "Pool")).toHaveTextContent("$500.00");
    const after = valueBeside(row, "Charged after the crossing").querySelector("[data-reading]");
    expect(after).toHaveAttribute("data-reading", "floor");
    expect(after).toHaveTextContent("at least $12.50");
    expect(valueBeside(row, "Active work stopped")).toHaveTextContent("3");
  });

  it("renders a wallet row with its floor and its episode, and a soft floor as a marker", async () => {
    renderWithProviders(<StopsAndBreaches filters={{ customer_id: CUSTOMER_LUNA }} />);
    await articles();

    const hard = articleFor("wallet_policy", (a) => within(a).queryByText("Hard floor") !== null);
    expect(valueBeside(hard, "Hard floor")).toHaveTextContent("-$5.00");
    expect(valueBeside(hard, "Balance at crossing")).toHaveTextContent("-$6.00");
    expect(within(hard).getByText("Episode 3")).toBeInTheDocument();
    // Three events past the stop, two costs known and one never learned: the
    // episode's supplier total is a floor, exactly as the old report said it.
    expect(hard).toHaveTextContent("at least $1.87");

    const soft = articleFor("wallet_policy", (a) => within(a).queryByText("Soft floor") !== null);
    expect(soft).toHaveTextContent(SOFT_FLOOR_MARKER);
    expect(within(soft).queryByRole("button", { name: /Show events/ })).not.toBeInTheDocument();
  });

  it("totals each family over exactly the events of the rows shown", async () => {
    renderWithProviders(<StopsAndBreaches filters={{ customer_id: CUSTOMER_LUNA }} />);
    await articles();

    const totals = screen.getByText("Totals per family").closest("table");
    if (!totals) throw new Error("no totals table");
    const wallet = within(totals).getByText("Wallet policy").closest("tr");
    expect(wallet).toHaveTextContent("3");
    expect(wallet).toHaveTextContent("$2.98");
    expect(wallet).toHaveTextContent("at least $1.87");
    expect(within(totals).queryByText("Ceiling")).not.toBeInTheDocument();
  });
});

describe("StopsAndBreaches — the empty answers", () => {
  it("answers admission control with no rows and its own sentence, never an error", async () => {
    renderWithProviders(<StopsAndBreaches filters={{ control_family: "admission_control" }} />);

    expect(await screen.findByText(NO_EPISODES_FOR.admission_control)).toBeInTheDocument();
    expect(screen.queryAllByRole("article")).toEqual([]);
    expect(screen.queryByText(/Couldn't load/)).not.toBeInTheDocument();
  });
});

describe("StopsAndBreaches — the customer filter", () => {
  // The proof is the call: this component makes the read with the customer
  // it was handed, and the server narrows. Dropping `customer_id` from the
  // read would leave the mock answering every row — and the first assertion
  // below red before the second.
  it("applies the customer filter through the read, not a second component", async () => {
    provider.getStopsAndBreaches.mockClear();
    renderWithProviders(<StopsAndBreaches filters={{ customer_id: CUSTOMER_LUNA }} />);
    const rows = await articles();

    expect(provider.getStopsAndBreaches).toHaveBeenCalledWith(
      expect.objectContaining({ customer_id: CUSTOMER_LUNA }),
    );
    expect(rows.every((article) => article.dataset.shape === "wallet_policy")).toBe(true);
    expect(rows).toHaveLength(2);
  });
});
