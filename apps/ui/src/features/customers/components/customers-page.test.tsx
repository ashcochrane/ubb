import { fireEvent, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { renderWithProviders } from "../test-utils";
import { CustomersPage } from "./customers-page";

function renderPage(onOpenCustomer = vi.fn()) {
  renderWithProviders(
    <CustomersPage
      search={{}}
      onSearchChange={vi.fn()}
      onOpenCustomer={onOpenCustomer}
    />,
  );
  return onOpenCustomer;
}

describe("CustomersPage", () => {
  it("renders margin rows from the API with formatted money", async () => {
    renderPage();
    // acme-corp's shortened UUID row with derived revenue (sub + usage revenue).
    expect(await screen.findByText("1f0c9c4e…", undefined, { timeout: 5000 })).toBeInTheDocument();
    expect(screen.getByText("$541.50")).toBeInTheDocument();
    // luna-labs' negative margin renders (styled by the restrained red).
    expect(screen.getByText("-$14.70")).toBeInTheDocument();
    // The contract-gap honesty note is visible.
    expect(
      screen.getByText(/the margin list has no external IDs/i),
    ).toBeInTheDocument();
  });

  // #330: nova-ai is the one customer in this roster holding events UBB could
  // not cost, so its COGS is a floor, its margin a ceiling and its margin
  // percentage the same — while every settled row stays a figure. Asserted as
  // a contrast rather than as one row: a table that bounded all five, or none,
  // would pass a single-row test and mislead on the page.
  it("bounds the COGS and margin of the customer whose costs are incomplete", async () => {
    renderPage();

    expect(
      await screen.findByText("at least $88.00", undefined, { timeout: 5000 }),
    ).toBeInTheDocument();
    expect(screen.getByText("at most -$88.00")).toBeInTheDocument();
    // luna-labs also runs at a loss, and every one of its costs is known.
    expect(screen.getByText("-$14.70")).toBeInTheDocument();
    expect(screen.queryByText("at most -$14.70")).not.toBeInTheDocument();
    expect(screen.getByText("$55.90")).toBeInTheDocument();
  });

  it("shows the filtered empty state when no customer ID matches", async () => {
    renderPage();
    await screen.findByText("1f0c9c4e…", undefined, { timeout: 5000 });
    fireEvent.change(screen.getByLabelText("Search customers"), {
      target: { value: "zzz-no-such-id" },
    });
    expect(await screen.findByText("No customers match")).toBeInTheDocument();
    expect(screen.queryByText("1f0c9c4e…")).not.toBeInTheDocument();
  });

  it("creates a customer and navigates to the new detail page", async () => {
    const onOpenCustomer = renderPage();
    await screen.findByText("1f0c9c4e…", undefined, { timeout: 5000 });
    fireEvent.click(screen.getByRole("button", { name: "New customer" }));
    fireEvent.change(await screen.findByLabelText("External ID"), {
      target: { value: "test-co" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create customer" }));
    await waitFor(() => expect(onOpenCustomer).toHaveBeenCalledTimes(1), {
      timeout: 5000,
    });
    expect(onOpenCustomer).toHaveBeenCalledWith(expect.any(String));
  });

  it("surfaces a 409 conflict inline and keeps the dialog open", async () => {
    renderPage();
    await screen.findByText("1f0c9c4e…", undefined, { timeout: 5000 });
    fireEvent.click(screen.getByRole("button", { name: "New customer" }));
    fireEvent.change(await screen.findByLabelText("External ID"), {
      target: { value: "acme-corp" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create customer" }));
    expect(
      await screen.findByText(/already exists — pick another/i, undefined, {
        timeout: 5000,
      }),
    ).toBeInTheDocument();
    // Input is preserved for correction.
    expect(screen.getByLabelText("External ID")).toHaveValue("acme-corp");
  });
});
