import { screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import {
  METERING_ONLY_BILLING_MODE,
  readMockTenantConfig,
  writeMockTenantConfig,
} from "@/hooks/use-tenant-config";

import {
  KIND_EVENT_PRICED_KEY,
  KIND_FIXED_KEY,
  MOCK_RUNS,
  RUN_ACTIVE_ID,
  RUN_CANCELLED_ID,
  RUN_DELIVERED_FIXED_ID,
  RUN_EXPIRED_ID,
  RUN_FAILED_ID,
  RUN_KILLED_ID,
  RUN_UNKNOWN_COST_ID,
} from "../api/mock-data";
import type { RunsSearch } from "../lib/runs";
import { renderWithProviders } from "../test-utils";
import { RunsPage } from "./runs-page";

function renderRuns(search: RunsSearch = {}) {
  const onSearchChange = vi.fn();
  const view = renderWithProviders(<RunsPage search={search} onSearchChange={onSearchChange} />);
  return { onSearchChange, ...view };
}

async function loaded(): Promise<void> {
  await screen.findByRole("table");
}

function rowOf(taskId: string): HTMLElement {
  const row = document.querySelector(`a[href="/tasks/runs/${taskId}"]`)?.closest("tr");
  if (!row) throw new Error(`no row holds run ${taskId}`);
  return row;
}

function maybeRowOf(taskId: string): HTMLElement | null {
  return document.querySelector(`a[href="/tasks/runs/${taskId}"]`)?.closest("tr") ?? null;
}

function bodyRows(): HTMLElement[] {
  return Array.from(document.querySelectorAll<HTMLElement>("tbody tr"));
}

const KIND = 1;
const STATE = 2;
const SUPPLIER_COST = 5;
const CUSTOMER_PRICE = 6;

function cell(row: HTMLElement, index: number): HTMLElement {
  const found = row.querySelectorAll<HTMLElement>("td")[index];
  if (!found) throw new Error(`no cell ${index}`);
  return found;
}

function reading(row: HTMLElement, index: number): HTMLElement {
  const found = cell(row, index).querySelector<HTMLElement>("[data-reading]");
  if (!found) throw new Error(`cell ${index} holds no reading`);
  return found;
}

function badge(row: HTMLElement): HTMLElement {
  const found = cell(row, STATE).querySelector<HTMLElement>("[data-tone]");
  if (!found) throw new Error("the state cell holds no drawn state");
  return found;
}

/** The destructive variant, and only it, colours its text; the base class names the colour for aria-invalid states on every variant. */
const DRAWN_AS_FAILURE = /(^|\s)text-destructive(\s|$)/;

describe("RunsPage", () => {
  it("lists every top-level run, newest first, each a link to its own page and to its kind's", async () => {
    renderRuns();
    await loaded();
    expect(bodyRows()).toHaveLength(MOCK_RUNS.length);
    const first = bodyRows()[0];
    if (!first) throw new Error("no rows");
    expect(first.querySelector("a")).toHaveAttribute("href", `/tasks/runs/${RUN_ACTIVE_ID}`);
    expect(cell(first, KIND).querySelector("a")).toHaveAttribute(
      "href",
      `/tasks/kinds/${KIND_FIXED_KEY}`,
    );
  });

  it("says every one of the six states in the catalogue's words", async () => {
    renderRuns();
    await loaded();
    for (const word of ["Active", "Completed", "Failed", "Cancelled", "Killed", "Expired"]) {
      expect(screen.getAllByText(word).length).toBeGreaterThan(0);
    }
  });

  it("renders an expired run as expired — never coloured or drawn as a failure", async () => {
    renderRuns();
    await loaded();
    const expired = badge(rowOf(RUN_EXPIRED_ID));
    const failed = badge(rowOf(RUN_FAILED_ID));
    expect(expired).toHaveAttribute("data-tone", "expired");
    expect(expired).toHaveTextContent("Expired");
    expect(expired.className).not.toMatch(DRAWN_AS_FAILURE);
    expect(expired).toHaveAttribute("title", expect.stringMatching(/Not a failure/));
    expect(failed).toHaveAttribute("data-tone", "failure");
    expect(failed).toHaveTextContent("Failed");
    expect(failed.className).toMatch(DRAWN_AS_FAILURE);
  });

  it("keeps an expired run out of the failure grouping", async () => {
    renderRuns({ status: "failed" });
    await loaded();
    expect(maybeRowOf(RUN_FAILED_ID)).not.toBeNull();
    expect(maybeRowOf(RUN_EXPIRED_ID)).toBeNull();
    expect(maybeRowOf(RUN_KILLED_ID)).toBeNull();
    expect(maybeRowOf(RUN_CANCELLED_ID)).toBeNull();
    for (const row of bodyRows()) expect(row).toHaveAttribute("data-status", "failed");
  });

  it("says Unknown, never a zero amount, for a run whose totals nobody knows", async () => {
    renderRuns();
    await loaded();
    const row = rowOf(RUN_UNKNOWN_COST_ID);
    expect(reading(row, SUPPLIER_COST)).toHaveAttribute("data-reading", "unknown");
    expect(reading(row, SUPPLIER_COST)).toHaveTextContent("Unknown");
    expect(reading(row, CUSTOMER_PRICE)).toHaveAttribute("data-reading", "unknown");
    expect(reading(row, CUSTOMER_PRICE)).toHaveTextContent("Unknown");
    expect(row).not.toHaveTextContent("$0.00");
  });

  it("says Not applicable, never a zero amount, for the customer price of a run sold at one agreed price", async () => {
    renderRuns();
    await loaded();
    const row = rowOf(RUN_DELIVERED_FIXED_ID);
    expect(reading(row, CUSTOMER_PRICE)).toHaveAttribute("data-reading", "not_applicable");
    expect(reading(row, CUSTOMER_PRICE)).toHaveTextContent("Not applicable");
    expect(reading(row, CUSTOMER_PRICE)).toHaveAttribute(
      "title",
      expect.stringMatching(/sold at one agreed price/),
    );
    // Its supplier cost is a real figure, and it renders as one.
    expect(reading(row, SUPPLIER_COST)).toHaveAttribute("data-reading", "figure");
    expect(reading(row, SUPPLIER_COST)).toHaveTextContent("$2.87");
  });

  it("renders a real zero as a zero — a run that withdrew before anything ran", async () => {
    renderRuns();
    await loaded();
    const row = rowOf(RUN_CANCELLED_ID);
    expect(reading(row, SUPPLIER_COST)).toHaveAttribute("data-reading", "figure");
    expect(reading(row, SUPPLIER_COST)).toHaveTextContent("$0.00");
    expect(reading(row, CUSTOMER_PRICE)).toHaveAttribute("data-reading", "figure");
    expect(reading(row, CUSTOMER_PRICE)).toHaveTextContent("$0.00");
  });

  it("says a partial total is a floor", async () => {
    renderRuns();
    await loaded();
    const row = rowOf(RUN_KILLED_ID);
    expect(reading(row, SUPPLIER_COST)).toHaveAttribute("data-reading", "floor");
    expect(reading(row, SUPPLIER_COST)).toHaveTextContent("at least $0.90");
  });

  it("narrows to one kind of work", async () => {
    renderRuns({ task_type: KIND_EVENT_PRICED_KEY });
    await loaded();
    const expected = MOCK_RUNS.filter((run) => run.task_type === KIND_EVENT_PRICED_KEY);
    expect(bodyRows()).toHaveLength(expected.length);
    for (const row of bodyRows()) {
      expect(cell(row, KIND).querySelector("a")).toHaveAttribute(
        "href",
        `/tasks/kinds/${KIND_EVENT_PRICED_KEY}`,
      );
    }
  });

  it("says no run has a customer price when the workspace meters without billing", async () => {
    const original = readMockTenantConfig();
    try {
      writeMockTenantConfig({ ...original, billing_mode: METERING_ONLY_BILLING_MODE });
      renderRuns();
      await loaded();
      for (const row of bodyRows()) {
        expect(reading(row, CUSTOMER_PRICE)).toHaveAttribute("data-reading", "not_applicable");
        expect(reading(row, CUSTOMER_PRICE)).toHaveAttribute(
          "title",
          expect.stringMatching(/does not bill customers through UBB/),
        );
      }
    } finally {
      writeMockTenantConfig(original);
    }
  });

  it("offers the kind and state filters, and the way back to kinds of work", async () => {
    renderRuns();
    await loaded();
    expect(screen.getByRole("combobox", { name: "Kind of work" })).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "State" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Kinds of work" })).toHaveAttribute("href", "/tasks");
    expect(screen.getByRole("link", { name: "Runs" })).toHaveAttribute("aria-current", "page");
  });

  it("says when nothing matches the filters, and offers to clear them", async () => {
    const { onSearchChange } = renderRuns({ task_type: "nothing-of-this-kind" });
    expect(await screen.findByText("No runs match these filters")).toBeInTheDocument();
    screen.getByRole("button", { name: "Show every run" }).click();
    expect(onSearchChange).toHaveBeenCalledWith({ task_type: undefined, status: undefined });
  });
});
