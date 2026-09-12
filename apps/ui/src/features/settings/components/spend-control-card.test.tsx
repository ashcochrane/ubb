import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { readMockTenantConfig, writeMockTenantConfig } from "@/hooks/use-tenant-config";

import { renderWithQuery } from "../test-utils";
import { NEW_WORK_PER_MINUTE_LABEL } from "./admission-control-form";
import {
  ENFORCING_LABEL,
  NO_CUSTOMER_WIDE_ENFORCEMENT_LABEL,
  SpendControlCard,
} from "./spend-control-card";

/**
 * The settings card after #462 (slice 6 §6, §10, §18): the switch's copy
 * says "no customer-wide enforcement" and never "off", and admission
 * control's one setting — the new-work rate — is edited here, for every
 * workspace, whichever way it bills.
 *
 * The copy assertions spell the constants rather than import them for the
 * expected text, so the page and the assertion cannot move together (#425's
 * lesson); the constants are imported only to name the card's own words in
 * the "never off" check, which is about every word the card renders.
 */
describe("SpendControlCard", () => {
  const original = readMockTenantConfig();

  beforeEach(() => {
    writeMockTenantConfig({ ...original, max_task_starts_per_minute: 60 });
  });

  afterEach(() => {
    writeMockTenantConfig(original);
  });

  it("describes the switch's positions as enforcing and no customer-wide enforcement, never off", () => {
    const { container } = renderWithQuery(
      <SpendControlCard config={readMockTenantConfig()} isAdmin />,
    );

    expect(
      screen.getByText(/No customer-wide enforcement: none of those signals fire/),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/still suspended and refused new work/),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/every ceiling and window declared on a kind of work still stops/),
    ).toBeInTheDocument();
    expect(screen.getByRole("switch", { name: "Enforcement" })).toBeChecked();

    // Never "off" as a word for the posture — anywhere on the card. The
    // two labels are the card's own vocabulary for the positions.
    expect(container.textContent).not.toMatch(/\boff\b/i);
    expect(container.textContent).toContain(ENFORCING_LABEL);
    expect(container.textContent).toContain(NO_CUSTOMER_WIDE_ENFORCEMENT_LABEL);
  });

  it("asks before stopping customer-wide enforcement, and never says off there either", async () => {
    renderWithQuery(<SpendControlCard config={readMockTenantConfig()} isAdmin />);

    fireEvent.click(screen.getByRole("switch", { name: "Enforcement" }));
    const dialog = await screen.findByRole("dialog");
    expect(
      within(dialog).getByText("Switch to no customer-wide enforcement?"),
    ).toBeInTheDocument();
    expect(within(dialog).getByText(/the new-work rate keep working/)).toBeInTheDocument();
    expect(dialog.textContent).not.toMatch(/\boff\b/i);
    expect(within(dialog).getByRole("button", { name: "Stop enforcing" })).toBeInTheDocument();
  });

  it("shows the workspace's new-work rate and the words that say what it bounds", () => {
    renderWithQuery(<SpendControlCard config={readMockTenantConfig()} isAdmin />);

    expect(screen.getByLabelText(NEW_WORK_PER_MINUTE_LABEL)).toHaveValue(60);
    expect(
      screen.getByText(/bounds how fast work enters, not what it spends/),
    ).toBeInTheDocument();
    expect(screen.getByText(/answers 429 with Retry-After/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save new-work rate" })).toBeDisabled();
  });

  it("saves a changed rate through the one config route", async () => {
    renderWithQuery(<SpendControlCard config={readMockTenantConfig()} isAdmin />);

    const field = screen.getByLabelText(NEW_WORK_PER_MINUTE_LABEL);
    fireEvent.change(field, { target: { value: "12" } });
    const save = screen.getByRole("button", { name: "Save new-work rate" });
    expect(save).toBeEnabled();
    fireEvent.click(save);

    await waitFor(
      () => {
        expect(readMockTenantConfig().max_task_starts_per_minute).toBe(12);
      },
      { timeout: 3000 },
    );
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Save new-work rate" })).toBeDisabled();
    });
    expect(field).toHaveValue(12);
  });

  it("clearing the rate sends an explicit null — no bound", async () => {
    renderWithQuery(<SpendControlCard config={readMockTenantConfig()} isAdmin />);

    fireEvent.change(screen.getByLabelText(NEW_WORK_PER_MINUTE_LABEL), {
      target: { value: "" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save new-work rate" }));

    await waitFor(
      () => {
        expect(readMockTenantConfig().max_task_starts_per_minute).toBeNull();
      },
      { timeout: 3000 },
    );
  });

  it("refuses zero before the request, with the field's message", async () => {
    renderWithQuery(<SpendControlCard config={readMockTenantConfig()} isAdmin />);

    fireEvent.change(screen.getByLabelText(NEW_WORK_PER_MINUTE_LABEL), {
      target: { value: "0" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save new-work rate" }));

    expect(
      await screen.findByText("Enter a whole number of 1 or more, or leave empty for no bound."),
    ).toBeInTheDocument();
    expect(readMockTenantConfig().max_task_starts_per_minute).toBe(60);
  });

  it("keeps the new-work rate editable under postpaid, where the wallet floors hide", () => {
    writeMockTenantConfig({ ...readMockTenantConfig(), billing_mode: "postpaid" });
    renderWithQuery(<SpendControlCard config={readMockTenantConfig()} isAdmin />);

    expect(screen.getByLabelText(NEW_WORK_PER_MINUTE_LABEL)).toBeInTheDocument();
    expect(screen.queryByLabelText(/Allowed overdraft/)).not.toBeInTheDocument();
  });
});
