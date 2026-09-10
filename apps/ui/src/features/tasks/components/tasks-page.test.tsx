import { fireEvent, screen, waitFor, within } from "@testing-library/react";
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
import { UNDECLARED_WORK_LABEL } from "./kinds-table";
import { TasksPage } from "./tasks-page";

beforeEach(resetTasksMockState);

/** The standing row for work with no declared kind (#453). */
function undeclaredWorkRow(): HTMLElement {
  return screen.getByTestId("undeclared-work-row");
}

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
    // Every declaration has a row, including the two that share one word —
    // plus the standing row for work with no declared kind (#453), which is
    // not a link: there is no page for a kind nobody declared.
    const rows = screen.getAllByRole("row").slice(1);
    expect(rows).toHaveLength(MOCK_KINDS.length + 1);
    expect(within(undeclaredWorkRow()).getByText(UNDECLARED_WORK_LABEL)).toBeInTheDocument();
    expect(within(undeclaredWorkRow()).queryAllByRole("link")).toHaveLength(0);
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

  it("says Uncapped only for a kind declared uncapped, whatever the workspace default", async () => {
    // INVERTED at its own address by #453: this case used to show a kind
    // with no figure inheriting the workspace default. A declared kind never
    // inherits — `render-frame` is declared uncapped and says so under both
    // configurations, and the workspace default shows on the standing row.
    const original = readMockTenantConfig();
    try {
      writeMockTenantConfig({
        ...original,
        default_task_cogs_ceiling_micros: null,
        default_subtask_cogs_ceiling_micros: null,
      });
      const first = renderWithProviders(<TasksPage />);
      await screen.findByRole("link", { name: KIND_STEP_KEY });
      expect(await within(rowOf(KIND_STEP_KEY)).findByText("Uncapped")).toBeInTheDocument();
      const standing = within(undeclaredWorkRow());
      expect(standing.getAllByText("No ceiling")).toHaveLength(2);
      expect(standing.queryByText("Uncapped")).toBeNull();
      first.unmount();

      writeMockTenantConfig({
        ...original,
        default_task_cogs_ceiling_micros: 9_000_000,
        default_subtask_cogs_ceiling_micros: 250_000,
      });
      renderWithProviders(<TasksPage />);
      await screen.findByRole("link", { name: KIND_STEP_KEY });
      expect(await within(rowOf(KIND_STEP_KEY)).findByText("Uncapped")).toBeInTheDocument();
      expect(within(undeclaredWorkRow()).getByText("$9.00")).toBeInTheDocument();
      expect(within(undeclaredWorkRow()).getByText("$0.25")).toBeInTheDocument();
    } finally {
      writeMockTenantConfig(original);
    }
  });

  it("edits the workspace's default ceilings from the standing row, at both altitudes", async () => {
    const original = readMockTenantConfig();
    try {
      writeMockTenantConfig({
        ...original,
        default_task_cogs_ceiling_micros: null,
        default_subtask_cogs_ceiling_micros: 250_000,
      });
      renderWithProviders(<TasksPage />);
      await screen.findByRole("link", { name: KIND_FIXED_KEY });
      fireEvent.click(within(undeclaredWorkRow()).getByRole("button", { name: "Edit default ceilings" }));
      const dialog = within(await screen.findByRole("dialog"));
      fireEvent.change(dialog.getByRole("textbox", { name: /^Task ceiling/ }), {
        target: { value: "9" },
      });
      fireEvent.change(dialog.getByRole("textbox", { name: /^Subtask ceiling/ }), {
        target: { value: "" },
      });
      fireEvent.click(dialog.getByRole("button", { name: "Save default ceilings" }));
      await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());

      expect(readMockTenantConfig()).toMatchObject({
        default_task_cogs_ceiling_micros: 9_000_000,
        default_subtask_cogs_ceiling_micros: null,
      });
      expect(await within(undeclaredWorkRow()).findByText("$9.00")).toBeInTheDocument();
      expect(within(undeclaredWorkRow()).getByText("No ceiling")).toBeInTheDocument();
    } finally {
      writeMockTenantConfig(original);
    }
  });

  it("refuses a default ceiling of zero, as the route does", async () => {
    const original = readMockTenantConfig();
    try {
      renderWithProviders(<TasksPage />);
      await screen.findByRole("link", { name: KIND_FIXED_KEY });
      fireEvent.click(within(undeclaredWorkRow()).getByRole("button", { name: "Edit default ceilings" }));
      const dialog = within(await screen.findByRole("dialog"));
      fireEvent.change(dialog.getByRole("textbox", { name: /^Task ceiling/ }), {
        target: { value: "0" },
      });
      fireEvent.click(dialog.getByRole("button", { name: "Save default ceilings" }));
      expect(await dialog.findByText(/above zero/)).toBeInTheDocument();
      expect(readMockTenantConfig()).toEqual(original);
    } finally {
      writeMockTenantConfig(original);
    }
  });

  it("offers two actions — the declaration, and the workspace's default ceilings — and nothing that edits a price or scopes a cap", async () => {
    renderWithProviders(<TasksPage />);
    await screen.findByRole("link", { name: KIND_FIXED_KEY });
    const buttons = screen.getAllByRole("button").map((button) => button.textContent);
    expect(buttons).toEqual(["Declare a kind of work", "Edit default ceilings"]);
    expect(screen.queryAllByRole("textbox")).toHaveLength(0);
    expect(screen.queryAllByRole("spinbutton")).toHaveLength(0);
  });
});
