import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it } from "vitest";

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
    // Narrowing reveals the full grouped catalog (35 event types).
    expect(screen.getAllByRole("checkbox").length).toBe(35);
  });

  it("toggles individual event types on and off", () => {
    render(<Harness />);
    const first = screen.getAllByRole("checkbox")[0]!;
    fireEvent.click(first);
    expect(first).toHaveAttribute("aria-checked", "true");
    fireEvent.click(first);
    expect(first).toHaveAttribute("aria-checked", "false");
  });
});
