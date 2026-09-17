// The ledger's filter bar had no rendering assertion at all until #507, which
// is part of how its key pair kept the analytics grouping word right through
// the slice that retires that word from every other surface it reached.
//
// ⚠ **THE PATCH KEY IS THE CLAIM, NOT THE LABEL.** What this component hands
// back is a patch the page puts straight into the URL and then into the request
// — so the key it emits IS the request vocabulary, and a test that only read
// the words on the screen would pass over a component still emitting the old
// ones. Each case below asserts the key and the word together for that reason.
//
// A page test cannot stand in for this: the filter bar renders only once a
// customer is chosen, and `events-page.test.tsx` never chooses one.

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { EventsSearch } from "../lib/search";
import { EventFilters } from "./event-filters";

const EMPTY: EventsSearch = {};

/** Type into an input and commit it the way a reader does — blur. */
function commit(input: HTMLElement, value: string) {
  fireEvent.change(input, { target: { value } });
  fireEvent.blur(input);
}

describe("EventFilters", () => {
  it("names the pair for the bag it filters, on the screen", () => {
    render(<EventFilters search={EMPTY} onChange={() => {}} />);

    // The label an event's own detail page has used for this bag all along.
    expect(screen.getByLabelText("Metadata")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("key")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("value")).toBeInTheDocument();
  });

  it("emits the request word as the patch key when a key is committed", () => {
    const onChange = vi.fn();
    render(<EventFilters search={EMPTY} onChange={onChange} />);

    commit(screen.getByLabelText("Metadata"), "env");

    expect(onChange).toHaveBeenCalledWith({ metadata_key: "env" });
  });

  it("emits the request word as the patch key when a value is committed", () => {
    const onChange = vi.fn();
    render(<EventFilters search={EMPTY} onChange={onChange} />);

    commit(screen.getByPlaceholderText("value"), "prod");

    expect(onChange).toHaveBeenCalledWith({ metadata_value: "prod" });
  });

  it("shows a committed pair back, and clears both under those names", () => {
    const onChange = vi.fn();
    render(
      <EventFilters
        search={{ metadata_key: "env", metadata_value: "prod" }}
        onChange={onChange}
      />,
    );

    expect(screen.getByLabelText("Metadata")).toHaveValue("env");
    expect(screen.getByPlaceholderText("value")).toHaveValue("prod");

    fireEvent.click(screen.getByRole("button", { name: "Clear filters" }));

    // Clearing has to name every filter it clears; a key left out of this patch
    // survives the click and the bar goes on claiming a filter is active.
    expect(onChange).toHaveBeenCalledWith({
      past_limit: undefined,
      stop_scope: undefined,
      episode_seq: undefined,
      metadata_key: undefined,
      metadata_value: undefined,
    });
  });

  // A lone half filters nothing — the route ignores it — so the bar says so
  // rather than leaving a reader with a list that looks filtered and is not.
  it("says a lone half of the pair does not filter", () => {
    render(
      <EventFilters search={{ metadata_key: "env" }} onChange={() => {}} />,
    );

    expect(
      screen.getByText(
        "Both a metadata key and a value are needed for this filter to apply.",
      ),
    ).toBeInTheDocument();
  });

  it("stays quiet once both halves are present", () => {
    render(
      <EventFilters
        search={{ metadata_key: "env", metadata_value: "prod" }}
        onChange={() => {}}
      />,
    );

    expect(screen.queryByText(/Both a metadata key/)).not.toBeInTheDocument();
  });
});
