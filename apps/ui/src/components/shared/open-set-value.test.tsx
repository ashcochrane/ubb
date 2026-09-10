// The console's rule for an open set, proved on `trigger_source` (#454; slice
// 6 §18; Testing Decisions claim 15).
//
// WHY THE PROOF IS HERE AND NOT ON A PAGE. The ticket puts `trigger_source`
// "where the run page says how a unit ended", and the contract cannot serve
// that: the field travels on the four terminal webhook payloads
// (`task.killed`, `task.expired` and their contained-work twins) and on
// nothing the console reads — `TaskDetailOut` publishes no stop cause, and
// the deliveries read (`WebhookDeliveryResponse`) publishes no payload body.
// The #425 precedent applies: the assertion is delivered where the subject
// CAN render, and the gap is named. This component is where the rule lives,
// so this is where it is proved; the values themselves are held by reference
// in the legacy adapter, which is the ledger's half of the payment. Putting
// the stop cause on the unit read is a contract change nobody owns yet.
//
// `localisation.test.tsx` proves the lookup's four outcomes in general. What
// is asserted here is the rendering — the mark, and its absence — on the
// generated keys of a real open concept.

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ABSENT_LABEL } from "@/lib/localisation";
import { TRIGGER_SOURCE_KNOWN_VALUES, TRIGGER_SOURCE_LABEL_KEYS } from "@/lib/vocabulary";

import { OpenSetValue, UNRECOGNISED_MARK } from "./open-set-value";

/** A mechanism no registry entry names — one UBB has not met, or has not yet. */
const UNRECOGNISED = "orbital_reaper";

function TriggerSource({ value }: { value: string | null }) {
  return (
    <span data-testid="source">
      <OpenSetValue labelKeys={TRIGGER_SOURCE_LABEL_KEYS} value={value} />
    </span>
  );
}

describe("a value of an open concept, on trigger_source", () => {
  it("renders every value the registry knows in the catalogue's words, unmarked", () => {
    // Vacuity guard: the list is generated, and a loop over an empty one
    // proves nothing. Not pinned to a count — the concept is OPEN, so the
    // registry adding a sixth value is not a rendering defect.
    expect(TRIGGER_SOURCE_KNOWN_VALUES.length).toBeGreaterThan(0);

    for (const value of TRIGGER_SOURCE_KNOWN_VALUES) {
      const { unmount } = render(<TriggerSource value={value} />);
      const rendered = screen.getByTestId("source");
      const words = rendered.textContent ?? "";
      expect(words.trim(), value).not.toBe("");
      // Not the token back: that is the unfamiliar branch's answer, so a
      // binding on the wrong concept's keys would still render something.
      expect(words, value).not.toBe(value);
      expect(rendered.querySelector("[data-label]")).toHaveAttribute("data-label", "labelled");
      expect(rendered).not.toHaveTextContent(UNRECOGNISED_MARK);
      unmount();
    }
  });

  it("renders a value the registry has never seen as the token it is, marked, never humanised", () => {
    render(<TriggerSource value={UNRECOGNISED} />);
    const rendered = screen.getByTestId("source");

    expect(rendered.querySelector("[data-label]")).toHaveAttribute("data-label", "unfamiliar");
    // The token EXACTLY, in its own element — `textContent` rather than a
    // substring match, which would pass on a rendering that title-cased it
    // and appended the token in brackets.
    expect(rendered.querySelector("code")?.textContent).toBe(UNRECOGNISED);
    expect(rendered).toHaveTextContent(UNRECOGNISED_MARK);
    // The humaniser's answer for this input, and the one thing that must
    // never render (ADR-0008 §4.3).
    expect(rendered).not.toHaveTextContent("Orbital reaper");
  });

  it("renders an absent value as an absence, with no mark", () => {
    render(<TriggerSource value={null} />);
    const rendered = screen.getByTestId("source");

    expect(rendered).toHaveTextContent(ABSENT_LABEL);
    expect(rendered.querySelector("[data-label]")).toHaveAttribute("data-label", "absent");
    expect(rendered).not.toHaveTextContent(UNRECOGNISED_MARK);
  });
});
