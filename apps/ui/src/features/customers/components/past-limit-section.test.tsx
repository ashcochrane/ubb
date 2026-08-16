// The past-limit report is where a zeroed unknown cost reads as exoneration.
//
// It itemizes the events that landed past a customer's own spend stop, so every
// figure on it is read as "this is what the overrun cost me". A supplier cost
// UBB never learned, rendered as `$0.00`, says that particular event was free —
// on the one report a tenant opens precisely because they are worried about
// money already spent.
//
// THE SURFACE WAS MISSED ONCE, AND THE REASON IS WORTH KEEPING. The whole
// report is `additionalProperties: true` in the contract, so a scan of the
// spec's typed schemas — which is how #330's surface list was first derived —
// cannot see that its rows carry `unresolved_event_count` at all. #328 put it
// there; nothing typed says so; only reading `api/v1/past_limit.py` does.

import { fireEvent, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { costingStatusLabel } from "@/lib/supplier-cost";

import { CUS_LUNA } from "../api/mock-data";
import { renderWithProviders } from "../test-utils";
import { PastLimitSection } from "./past-limit-section";

describe("PastLimitSection", () => {
  it("renders an episode's supplier total as a floor when a cost is missing", async () => {
    renderWithProviders(<PastLimitSection customerId={CUS_LUNA} />);

    // The floor-stop episode: three events past the stop, two costs known
    // ($1.16 + $0.712 = $1.872) and one never learned.
    expect(
      await screen.findByText(/at least \$1\.87 cost/),
    ).toBeInTheDocument();
  });

  it("renders the per-limit total as a floor on the same terms", async () => {
    renderWithProviders(<PastLimitSection customerId={CUS_LUNA} />);

    expect(await screen.findByText("Totals per limit")).toBeInTheDocument();
    expect(screen.getByText("at least $1.87")).toBeInTheDocument();
    // The task-limit episode's costs are all known, so its total is a figure.
    expect(screen.getByText("$0.90")).toBeInTheDocument();
  });

  it("names an itemized event's unlearned cost instead of zeroing it", async () => {
    renderWithProviders(<PastLimitSection customerId={CUS_LUNA} />);

    // Expand the floor-stop episode to itemize its events.
    const episode = await screen.findByText(/at least \$1\.87 cost/);
    const toggle = episode.closest("button");
    expect(toggle).not.toBeNull();
    if (toggle) fireEvent.click(toggle);

    const cell = await screen.findByText(costingStatusLabel("unresolved"));
    expect(cell).toBeInTheDocument();
    // The row still shows what it BILLED — the silence is about the supplier
    // cost alone, which is what makes it something a tenant can see.
    expect(screen.getByText("$0.64")).toBeInTheDocument();
    // And no row invented a zero to fill the gap.
    const table = cell.closest("table");
    expect(table?.textContent ?? "").not.toContain("$0.00");
  });
});
