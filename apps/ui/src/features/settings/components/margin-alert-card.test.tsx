import { fireEvent, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { renderWithQuery } from "../test-utils";
import { MarginAlertCard } from "./margin-alert-card";

describe("MarginAlertCard", () => {
  it("prefills the three thresholds from the server config", async () => {
    renderWithQuery(<MarginAlertCard isAdmin />);

    expect(await screen.findByLabelText("Minimum margin (%)")).toHaveValue(10);
    expect(screen.getByLabelText("Consecutive periods")).toHaveValue(2);
    expect(screen.getByLabelText("Provider-cost spike (%)")).toHaveValue(25);

    // Plain-language helpers on every field
    expect(
      screen.getByText(/count as unprofitable/),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/in a row/),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/raises a cost-spike event/),
    ).toBeInTheDocument();

    // Untouched form — nothing to save yet
    expect(
      screen.getByRole("button", { name: "Save margin alerts" }),
    ).toBeDisabled();
  });

  it("rejects a consecutive-periods value below 1 with the field's message", async () => {
    renderWithQuery(<MarginAlertCard isAdmin />);
    const periods = await screen.findByLabelText("Consecutive periods");

    fireEvent.change(periods, { target: { value: "0" } });
    fireEvent.click(screen.getByRole("button", { name: "Save margin alerts" }));

    expect(
      await screen.findByText("Enter a whole number of periods, 1 or more."),
    ).toBeInTheDocument();
  });

  it("saves changed thresholds and resets the form to the server response", async () => {
    renderWithQuery(<MarginAlertCard isAdmin />);
    const minMargin = await screen.findByLabelText("Minimum margin (%)");
    const periods = screen.getByLabelText("Consecutive periods");

    fireEvent.change(minMargin, { target: { value: "15" } });
    fireEvent.change(periods, { target: { value: "3" } });
    const save = screen.getByRole("button", { name: "Save margin alerts" });
    expect(save).toBeEnabled();
    fireEvent.click(save);

    // After the mock PUT resolves the form resets against the response:
    // values persist and the save button returns, disabled (nothing dirty).
    await waitFor(
      () => {
        expect(
          screen.getByRole("button", { name: "Save margin alerts" }),
        ).toBeDisabled();
      },
      { timeout: 3000 },
    );
    expect(minMargin).toHaveValue(15);
    expect(periods).toHaveValue(3);
  });

  it("disables the fields and explains the Admin floor for non-admins", async () => {
    renderWithQuery(<MarginAlertCard isAdmin={false} />);

    expect(await screen.findByLabelText("Minimum margin (%)")).toBeDisabled();
    // DisabledHint wraps the save button so the reason is reachable.
    expect(
      screen.getByLabelText("Requires the Admin role."),
    ).toBeInTheDocument();
  });
});
