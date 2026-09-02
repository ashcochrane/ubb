// Test-only readers for the event receipt page, shared by the component
// tests that render it.
//
// ⚠ THE SECTION IS THE UNIT (#371), and it has to be. The catalogue gives
// `costing_status.known` and `pricing_status.known` the same word, so a
// page-wide query for "Known" finds two nodes and cannot say which side it
// found — and the two are opposite facts about the same posting. Scoping the
// question to a section is what keeps an assertion about the price from
// passing on the cost. And the ROW is the unit one level down (#425): the
// receipt section renders the record as a tree of every leaf, so an assertion
// about what the page SAID about the record has to read the summary list and
// the row, or the tree satisfies it whether the page said anything or not.

import { screen, within } from "@testing-library/react";
import { expect } from "vitest";

/** Everything one section of the receipt says, by the title it renders under. */
export function sectionText(title: string): string {
  const section = screen.getByText(title).closest("section");
  expect(section).not.toBeNull();
  return section?.textContent ?? "";
}

/**
 * The summary list a section opens with — the `DetailList` above whatever
 * else it renders — for an assertion that must NOT be satisfied by the record
 * tree below it, which renders every leaf of the record verbatim.
 */
export function summaryListOf(title: string): HTMLElement {
  const section = screen.getByText(title).closest("section");
  const list = section?.querySelector<HTMLElement>("dl");
  if (!list) throw new Error(`${title} opens with no summary list`);
  return list;
}

/** The row of a detail list holding a label and the value beside it. */
export function rowBeside(scope: HTMLElement, label: string): HTMLElement {
  const row = within(scope).getByText(label).parentElement;
  if (!row) throw new Error(`${label} has no row`);
  return row;
}
