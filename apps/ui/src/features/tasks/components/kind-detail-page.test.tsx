import { screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import { resetTasksMockState } from "../api/mock";
import {
  KIND_EVENT_PRICED_KEY,
  KIND_FIXED_KEY,
  KIND_FIXED_NEGOTIATED_KEY,
  KIND_FIXED_UNSOLD_KEY,
  KIND_SHARED_WORD_KEY,
} from "../api/mock-data";
import { renderWithProviders } from "../test-utils";
import { KindDetailPage } from "./kind-detail-page";

beforeEach(resetTasksMockState);

async function soldSection(key: string) {
  await screen.findByRole("heading", { name: key });
  return within(screen.getByRole("region", { name: "How it is sold" }));
}

/** The value cell beside the "Ceiling against price" label. */
function ceilingAgainstPrice(section: ReturnType<typeof within>) {
  const label = section.getByText("Ceiling against price");
  const row = label.parentElement;
  if (!row) throw new Error("the label has no row");
  return within(row);
}

describe("KindDetailPage", () => {
  it("renders a kind of work from its routed key", async () => {
    renderWithProviders(<KindDetailPage kindKey={KIND_FIXED_KEY} />);
    const sold = await soldSection(KIND_FIXED_KEY);
    expect(sold.getByText("Fixed price")).toBeInTheDocument();
    expect(screen.getByText("Task · Fixed price")).toBeInTheDocument();
  });

  it("shows the price as a read-only link into the book — nothing on this surface edits it", async () => {
    renderWithProviders(<KindDetailPage kindKey={KIND_FIXED_KEY} />);
    const sold = await soldSection(KIND_FIXED_KEY);
    expect(sold.getByRole("link", { name: /pricing books/i })).toHaveAttribute("href", "/pricing");
    expect(sold.queryAllByRole("textbox")).toHaveLength(0);
    expect(sold.queryAllByRole("spinbutton")).toHaveLength(0);
    expect(sold.queryAllByRole("button")).toHaveLength(0);
    expect(sold.queryAllByRole("radio")).toHaveLength(0);
  });

  it("shows the ceiling against the price a fixed-price kind's runs were quoted", async () => {
    renderWithProviders(<KindDetailPage kindKey={KIND_FIXED_KEY} />);
    const sold = await soldSection(KIND_FIXED_KEY);
    const against = ceilingAgainstPrice(sold);
    expect(await against.findByText(/3 runs were quoted \$5\.00\./)).toBeInTheDocument();
    expect(against.getByText("The $3.00 ceiling is 60% of that price.")).toBeInTheDocument();
    expect(against.getByText(/Raising the price without moving the ceiling tightens it/)).toBeInTheDocument();
    // The evidence lags a repricing by one run, and the page says so.
    expect(against.getByText(/shows here from the next run/)).toBeInTheDocument();
  });

  it("shows a range when different customers' books quoted the runs differently", async () => {
    renderWithProviders(<KindDetailPage kindKey={KIND_FIXED_NEGOTIATED_KEY} />);
    const sold = await soldSection(KIND_FIXED_NEGOTIATED_KEY);
    const against = ceilingAgainstPrice(sold);
    expect(
      await against.findByText(/2 runs were quoted between \$4\.00 and \$8\.00\./),
    ).toBeInTheDocument();
    expect(
      against.getByText("The $3.00 ceiling is between 37% and 75% of the price."),
    ).toBeInTheDocument();
  });

  it("says when no run has pinned a price yet, rather than inventing one", async () => {
    renderWithProviders(<KindDetailPage kindKey={KIND_FIXED_UNSOLD_KEY} />);
    const sold = await soldSection(KIND_FIXED_UNSOLD_KEY);
    expect(
      await ceilingAgainstPrice(sold).findByText(/No run of this kind has pinned a price yet/),
    ).toBeInTheDocument();
  });

  it("holds no price comparison for a kind priced per event", async () => {
    renderWithProviders(<KindDetailPage kindKey={KIND_EVENT_PRICED_KEY} />);
    const sold = await soldSection(KIND_EVENT_PRICED_KEY);
    expect(sold.getByText("Event priced")).toBeInTheDocument();
    expect(sold.getByText(/Set per event by the rules in the pricing book/)).toBeInTheDocument();
    expect(sold.queryByText("Ceiling against price")).toBeNull();
    expect(sold.getByRole("link", { name: /pricing books/i })).toHaveAttribute("href", "/pricing");
  });

  it("renders every declaration sharing a word, whole-work altitude first", async () => {
    renderWithProviders(<KindDetailPage kindKey={KIND_SHARED_WORD_KEY} />);
    const headings = await screen.findAllByRole("heading", { name: KIND_SHARED_WORD_KEY });
    expect(headings).toHaveLength(2);
    const descriptions = screen.getAllByText(/· Event priced$/).map((node) => node.textContent);
    expect(descriptions).toEqual(["Task · Event priced", "Subtask · Event priced"]);
  });

  it("says so when nothing is declared under the key", async () => {
    renderWithProviders(<KindDetailPage kindKey="nothing-here" />);
    expect(await screen.findByText("No kind of work named nothing-here")).toBeInTheDocument();
  });
});
