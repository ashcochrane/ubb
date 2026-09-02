import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import * as React from "react";
import { beforeEach, describe, expect, it } from "vitest";

import {
  METERING_ONLY_BILLING_MODE,
  readMockTenantConfig,
  writeMockTenantConfig,
} from "@/hooks/use-tenant-config";

import { listKinds, resetTasksMockState } from "../api/mock";
import { KIND_EVENT_PRICED_KEY, KIND_FIXED_KEY, MOCK_KINDS } from "../api/mock-data";
import type { KindOfWork } from "../api/types";
import { REGIME_CANNOT_CHANGE, REGIME_IS_INERT_UNTIL_BILLING } from "../lib/kinds";
import { renderWithProviders } from "../test-utils";
import { DeclareKindDialog } from "./declare-kind-dialog";

beforeEach(resetTasksMockState);

const FIXED = MOCK_KINDS.find((kind) => kind.key === KIND_FIXED_KEY)!;

/**
 * ⚠ THE DIALOG'S OPEN STATE IS REAL, NOT PINNED OPEN. Declaring closes it,
 * which is what a tenant experiences and what the submit cases wait for.
 */
function Harness({ existing }: { existing?: KindOfWork }) {
  const [open, setOpen] = React.useState(true);
  return (
    <DeclareKindDialog
      open={open}
      onOpenChange={setOpen}
      standing={MOCK_KINDS}
      existing={existing}
    />
  );
}

/** Run a case as a workspace that meters without billing. */
async function asMeteringOnly(run: () => Promise<void>) {
  const original = readMockTenantConfig();
  writeMockTenantConfig({
    ...original,
    billing_mode: METERING_ONLY_BILLING_MODE,
    products: ["metering"],
  });
  try {
    await run();
  } finally {
    writeMockTenantConfig(original);
  }
}

async function regimeControl() {
  return within(await screen.findByRole("group", { name: "How it is sold" }));
}

describe("DeclareKindDialog", () => {
  it("tells a metering-only workspace, beside the regime control, that the declaration becomes a start-gate refusal and that the regime cannot change afterwards", async () => {
    await asMeteringOnly(async () => {
      renderWithProviders(<Harness />);
      const regime = await regimeControl();
      expect(await regime.findByText(REGIME_IS_INERT_UNTIL_BILLING)).toBeInTheDocument();
      expect(regime.getByText(REGIME_CANNOT_CHANGE)).toBeInTheDocument();
      // Stated while the choice is still open — every regime is enabled here.
      for (const radio of regime.getAllByRole("radio")) expect(radio).toBeEnabled();
    });
  });

  it("tells a billing workspace only that the regime is frozen", async () => {
    renderWithProviders(<Harness />);
    const regime = await regimeControl();
    expect(await regime.findByText(REGIME_CANNOT_CHANGE)).toBeInTheDocument();
    expect(regime.queryByText(REGIME_IS_INERT_UNTIL_BILLING)).toBeNull();
  });

  it("disables the regime control once a kind of work is declared, and its identity with it", async () => {
    renderWithProviders(<Harness existing={FIXED} />);
    const regime = await regimeControl();
    for (const radio of regime.getAllByRole("radio")) expect(radio).toBeDisabled();
    expect(regime.getByRole("radio", { name: /^Fixed price/ })).toBeChecked();
    expect(regime.getByText(REGIME_CANNOT_CHANGE)).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: /^Key$/ })).toBeDisabled();
    const altitude = within(screen.getByRole("group", { name: "Altitude" }));
    for (const radio of altitude.getAllByRole("radio")) expect(radio).toBeDisabled();
  });

  it("offers exactly these controls: an absolute ceiling, two windows, and no cap scoped to a grouping field or expressed as a share of the price", async () => {
    renderWithProviders(<Harness />);
    const dialog = within(await screen.findByRole("dialog"));
    const textboxes = dialog.getAllByRole("textbox").map((box) => box.getAttribute("id"));
    expect(textboxes).toHaveLength(4);
    expect(dialog.getByRole("textbox", { name: /^Key$/ })).toBeInTheDocument();
    expect(dialog.getByRole("textbox", { name: /^Ceiling \(USD\)$/ })).toBeInTheDocument();
    expect(dialog.getByRole("textbox", { name: /^Silence window \(seconds\)$/ })).toBeInTheDocument();
    expect(dialog.getByRole("textbox", { name: /^Absolute deadline \(seconds\)$/ })).toBeInTheDocument();
    const radios = dialog.getAllByRole("radio").map((radio) => radio.getAttribute("value"));
    expect(radios).toEqual(["task", "subtask", "event_priced", "fixed"]);
    expect(dialog.queryAllByRole("spinbutton")).toHaveLength(0);
    expect(dialog.queryAllByRole("combobox")).toHaveLength(0);
    expect(dialog.queryAllByRole("checkbox")).toHaveLength(0);
    expect(dialog.queryAllByRole("switch")).toHaveLength(0);
    expect(dialog.getByText(/an amount, never a share of the price/)).toBeInTheDocument();
  });

  it("declares a new kind beside every standing one, leaving their ceilings and grouping fields untouched", async () => {
    renderWithProviders(<Harness />);
    const dialog = within(await screen.findByRole("dialog"));
    fireEvent.change(dialog.getByRole("textbox", { name: /^Key$/ }), {
      target: { value: "podcast-cut" },
    });
    fireEvent.click(dialog.getByRole("radio", { name: /^Fixed price/ }));
    fireEvent.change(dialog.getByRole("textbox", { name: /^Ceiling/ }), {
      target: { value: "2.50" },
    });
    fireEvent.click(dialog.getByRole("button", { name: "Declare" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());

    const after = await listKinds();
    expect(after).toHaveLength(MOCK_KINDS.length + 1);
    expect(after.find((kind) => kind.key === "podcast-cut")).toMatchObject({
      kind: "task",
      pricing_mode: "fixed",
      default_provider_cost_limit_micros: 2_500_000,
      silence_window_seconds: null,
      retired: false,
    });
    // The whole vocabulary went back verbatim: a standing kind kept what it had.
    expect(after.find((kind) => kind.key === KIND_EVENT_PRICED_KEY)).toMatchObject({
      default_provider_cost_limit_micros: 2_000_000,
      silence_window_seconds: 600,
      required_dimensions: ["model"],
    });
  });

  it("revises a standing kind's ceiling without touching how it is sold", async () => {
    renderWithProviders(<Harness existing={FIXED} />);
    const dialog = within(await screen.findByRole("dialog"));
    fireEvent.change(dialog.getByRole("textbox", { name: /^Ceiling/ }), {
      target: { value: "4" },
    });
    fireEvent.click(dialog.getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());

    const after = await listKinds();
    expect(after).toHaveLength(MOCK_KINDS.length);
    expect(after.find((kind) => kind.key === KIND_FIXED_KEY)).toMatchObject({
      pricing_mode: "fixed",
      default_provider_cost_limit_micros: 4_000_000,
      silence_window_seconds: FIXED.silence_window_seconds,
      absolute_deadline_seconds: FIXED.absolute_deadline_seconds,
    });
  });
});
