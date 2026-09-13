// The stop-context timeline renders a stop word through the console's one
// open-set helper (#466; slice 6 §18; Testing Decisions claim 15): a value the
// registry knows renders in the catalogue's words, unmarked; a value it has
// never seen renders as the token it is, marked unrecognised, never humanised
// into words UBB did not say.
//
// The entries are assembled here rather than taken from the events mock: the
// mock's seeds carry the registry's words, and a fixture the mock authors
// cannot show the unfamiliar branch at all. That branch is not hypothetical
// on this surface — `stop_context` is immutable with its posting and was not
// migrated when the stop vocabulary was (#457), so a posting tagged before
// the registry's words carries the spelling of its day forever.

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { UNRECOGNISED_MARK } from "@/components/shared/open-set-value";
import { REASON_CODE_KNOWN_VALUES } from "@/lib/vocabulary";

import type { StopContextEntry } from "../api/types";
import { StopContextTimeline } from "./stop-context-timeline";

/** A spelling no registry entry names — a tag written before the words were. */
const A_SPELLING_OF_ITS_DAY = "a_stop_word_from_before_the_registry";

function entry(limit: string): StopContextEntry {
  return {
    limit,
    stop_scope: "customer",
    tripped_at: "2026-07-18T14:02:11Z",
    episode_seq: 3,
    task_id: null,
    subtask_id: null,
    arrived_after: true,
  };
}

describe("the stop-context timeline's stop word", () => {
  it("renders a value the registry knows in the catalogue's words, unmarked", () => {
    // Vacuity guard on the generated list; not pinned to a count — the
    // concept is open, so an eighth registry value is not a rendering defect.
    expect(REASON_CODE_KNOWN_VALUES.length).toBeGreaterThan(0);
    const known = REASON_CODE_KNOWN_VALUES[0];

    render(<StopContextTimeline entries={[entry(known)]} />);

    const rendered = document.querySelector("[data-label]");
    expect(rendered).toHaveAttribute("data-label", "labelled");
    expect(rendered?.textContent?.trim()).not.toBe("");
    expect(rendered?.textContent).not.toBe(known);
    expect(screen.queryByText(UNRECOGNISED_MARK)).not.toBeInTheDocument();
  });

  it("renders a spelling the registry has never seen as the token, marked, never humanised", () => {
    render(<StopContextTimeline entries={[entry(A_SPELLING_OF_ITS_DAY)]} />);

    const rendered = document.querySelector("[data-label]");
    expect(rendered).toHaveAttribute("data-label", "unfamiliar");
    expect(rendered).toHaveTextContent(A_SPELLING_OF_ITS_DAY);
    expect(rendered).toHaveTextContent(UNRECOGNISED_MARK);
    expect(document.body).not.toHaveTextContent("A stop word from before the registry");
  });
});
