import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it } from "vitest";

import { WEBHOOK_EVENT_TYPE_VALUES } from "@/lib/vocabulary";

import { EventTypePicker } from "./event-type-picker";

function Harness({ initialAll = false }: { initialAll?: boolean }) {
  const [allEvents, setAllEvents] = useState(initialAll);
  const [selected, setSelected] = useState<string[]>([]);
  return (
    <EventTypePicker
      allEvents={allEvents}
      onAllEventsChange={setAllEvents}
      selected={selected}
      onSelectedChange={setSelected}
    />
  );
}

describe("EventTypePicker", () => {
  it("hides the catalog under the wildcard and reveals it when narrowing", () => {
    render(<Harness initialAll />);
    // Wildcard on → no checkbox catalog rendered at all.
    expect(screen.queryAllByRole("checkbox")).toHaveLength(0);

    fireEvent.click(screen.getByRole("switch", { name: "All events (*)" }));
    // Narrowing reveals the full grouped catalog, held against the REGISTRY's
    // own generated value set rather than against a literal or against the
    // console list the picker is built from.
    //
    // ⚠ THE SOURCE MATTERS MORE THAN THE COUNT HERE. A literal said 35 until
    // the terminal stop events became four, which is what a running tally in
    // an assertion does; but deriving from `@/lib/labels` — which is what the
    // picker itself reads — would have made both sides one source and pinned
    // nothing at all. `WEBHOOK_EVENT_TYPE_VALUES` is generated from
    // `concepts/webhooks.yaml`, so this is the one place the console's
    // hand-held catalogue is held to the registry's, and it goes red if the
    // two ever disagree rather than merely if somebody miscounts.
    expect(screen.getAllByRole("checkbox").length).toBe(
      WEBHOOK_EVENT_TYPE_VALUES.length,
    );
  });

  it("toggles individual event types on and off", () => {
    render(<Harness />);
    const first = screen.getAllByRole("checkbox")[0]!;
    fireEvent.click(first);
    expect(first).toHaveAttribute("aria-checked", "true");
    fireEvent.click(first);
    expect(first).toHaveAttribute("aria-checked", "false");
  });

  it("renders the regrouped events under the subject that owns them", () => {
    // #222 dissolved the `billing` group of eight and the `margin` group of
    // two. Asserted on what a tenant actually SEES rather than on the grouping
    // function's return value: the group heading, the option label beside its
    // checkbox, and the checkbox being reachable by that label — which is also
    // #155 §9.2's floor, since a value with no wording renders as a blank a
    // `getByLabelText` cannot find.
    render(<Harness />);

    for (const heading of ["Wallet", "Credit grant", "Top up", "Provider"]) {
      expect(screen.getByText(heading)).toBeInTheDocument();
    }
    expect(screen.queryByText("Billing")).not.toBeInTheDocument();
    expect(screen.queryByText("Margin")).not.toBeInTheDocument();

    // By ROLE and accessible name: Base UI pairs each visible checkbox with a
    // hidden native input carrying the same label, so `getByLabelText` finds
    // two elements for one control.
    const balanceLow = screen.getByRole("checkbox", { name: "Balance low" });
    fireEvent.click(balanceLow);
    expect(balanceLow).toHaveAttribute("aria-checked", "true");
    expect(
      screen.getByRole("checkbox", { name: "Cost spike" }),
    ).toBeInTheDocument();
  });
});
