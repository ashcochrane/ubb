import { screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import { readMockTenantConfig, writeMockTenantConfig } from "@/hooks/use-tenant-config";

import { resetTasksMockState } from "../api/mock";
import {
  KIND_FIXED_KEY,
  KIND_RETIRED_KEY,
  KIND_STEP_KEY,
  MOCK_KINDS,
} from "../api/mock-data";
import { renderWithProviders } from "../test-utils";
import { TasksPage } from "./tasks-page";

beforeEach(resetTasksMockState);

function rowOf(key: string): HTMLElement {
  const row = screen.getByRole("link", { name: key }).closest("tr");
  if (!row) throw new Error(`no table row holds ${key}`);
  return row;
}

describe("TasksPage", () => {
  it("lands on kinds of work — one row per declaration, each a link to its own page", async () => {
    renderWithProviders(<TasksPage />);
    const link = await screen.findByRole("link", { name: KIND_FIXED_KEY });
    expect(link).toHaveAttribute("href", `/tasks/kinds/${KIND_FIXED_KEY}`);
    // Every declaration has a row, including the two that share one word.
    const rows = screen.getAllByRole("row").slice(1);
    expect(rows).toHaveLength(MOCK_KINDS.length);
  });

  it("says how each kind is sold and what it may spend, in the catalogue's words", async () => {
    renderWithProviders(<TasksPage />);
    await screen.findByRole("link", { name: KIND_FIXED_KEY });
    const fixed = within(rowOf(KIND_FIXED_KEY));
    expect(fixed.getByText("Fixed price")).toBeInTheDocument();
    expect(fixed.getByText("Task")).toBeInTheDocument();
    expect(await fixed.findByText("$3.00")).toBeInTheDocument();
    expect(fixed.getByText("30 min")).toBeInTheDocument();
    expect(within(rowOf(KIND_RETIRED_KEY)).getByText("Retired")).toBeInTheDocument();
  });

  it("shows an inherited ceiling as the workspace default, and uncapped when there is none", async () => {
    const original = readMockTenantConfig();
    try {
      writeMockTenantConfig({ ...original, default_task_provider_cost_limit_micros: null });
      const first = renderWithProviders(<TasksPage />);
      await screen.findByRole("link", { name: KIND_STEP_KEY });
      expect(await within(rowOf(KIND_STEP_KEY)).findByText("Uncapped")).toBeInTheDocument();
      first.unmount();

      writeMockTenantConfig({ ...original, default_task_provider_cost_limit_micros: 9_000_000 });
      renderWithProviders(<TasksPage />);
      await screen.findByRole("link", { name: KIND_STEP_KEY });
      expect(
        await within(rowOf(KIND_STEP_KEY)).findByText("$9.00 (workspace default)"),
      ).toBeInTheDocument();
    } finally {
      writeMockTenantConfig(original);
    }
  });

  it("offers one action, the declaration, and nothing that edits a price or scopes a cap", async () => {
    renderWithProviders(<TasksPage />);
    await screen.findByRole("link", { name: KIND_FIXED_KEY });
    const buttons = screen.getAllByRole("button").map((button) => button.textContent);
    expect(buttons).toEqual(["Declare a kind of work"]);
    expect(screen.queryAllByRole("textbox")).toHaveLength(0);
    expect(screen.queryAllByRole("spinbutton")).toHaveLength(0);
  });
});
