import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it } from "vitest";

import { WEBHOOK_EVENT_TYPE_VALUES, type WebhookEventType } from "@/lib/vocabulary";

import { EventTypePicker } from "./event-type-picker";

function Harness({ initialAll = false }: { initialAll?: boolean }) {
  const [allEvents, setAllEvents] = useState(initialAll);
  const [selected, setSelected] = useState<WebhookEventType[]>([]);
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
    // Narrowing reveals the full grouped catalogue, held against the
    // REGISTRY's own generated value set rather than against a literal.
    //
    // ⚠ THE SOURCE MATTERS MORE THAN THE COUNT HERE. A literal said 35 until
    // the terminal stop events became four, which is what a running tally in
    // an assertion does. Since #464 the picker itself derives its groups from
    // `WEBHOOK_EVENT_TYPE_VALUES`, so this is no longer two sources held to
    // each other — it is the vacuity floor for the render: every declared
    // event reaches the screen as a checkbox, and none is dropped on the way
    // from the registry to the group it belongs to.
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
    // two; #464 moved the five control events under the customer and the two
    // control families. Asserted on what a tenant actually SEES rather than
    // on the grouping function's return value: the group heading, the option
    // label beside its checkbox, and the checkbox being reachable by that
    // label — which is also #155 §9.2's floor, since a value with no wording
    // renders as a blank a `getByLabelText` cannot find.
    render(<Harness />);

    for (const heading of ["Wallet", "Credit grant", "Top-up", "Provider"]) {
      expect(screen.getByText(heading)).toBeInTheDocument();
    }
    expect(screen.queryByText("Billing")).not.toBeInTheDocument();
    expect(screen.queryByText("Margin")).not.toBeInTheDocument();
    // The mechanism namespaces are gone with their events; the two control
    // families head their groups under the catalogue's own family words.
    expect(screen.queryByText("Stop")).not.toBeInTheDocument();
    expect(screen.queryByText("Soft floor")).not.toBeInTheDocument();
    expect(screen.queryByText("Budget")).not.toBeInTheDocument();
    expect(screen.getByText("Wallet policy")).toBeInTheDocument();
    expect(screen.getByText("Customer spend pool")).toBeInTheDocument();

    // By ROLE and accessible name — the catalogue's wording for the event,
    // whole, never a humanised suffix: Base UI pairs each visible checkbox
    // with a hidden native input carrying the same label, so
    // `getByLabelText` finds two elements for one control.
    const balanceLow = screen.getByRole("checkbox", { name: "Wallet balance low" });
    fireEvent.click(balanceLow);
    expect(balanceLow).toHaveAttribute("aria-checked", "true");
    expect(
      screen.getByRole("checkbox", { name: "Provider cost spike" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("checkbox", { name: "Customer stopped" }),
    ).toBeInTheDocument();
  });
});
