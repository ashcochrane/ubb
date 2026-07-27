import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { resetReferralsMockState } from "../api/mock-data";
import { ReferrersSection } from "./referrers-section";

function renderWithClient(ui: React.ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

const FIND_OPTS = { timeout: 4000 };
const NEW_CUSTOMER_ID = "deadbeef-0000-4000-8000-000000000001";

describe("ReferrersSection — register referrer mutation flow", () => {
  beforeEach(() => {
    resetReferralsMockState();
  });

  it("registers a new referrer and shows it in the refreshed list", async () => {
    renderWithClient(<ReferrersSection onOpenReferrer={vi.fn()} />);

    // List loaded from mock data.
    expect(await screen.findByText("REF-ACME8821", undefined, FIND_OPTS)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Register referrer" }));
    const input = await screen.findByLabelText("Customer UUID", undefined, FIND_OPTS);
    fireEvent.change(input, { target: { value: NEW_CUSTOMER_ID } });
    fireEvent.click(screen.getByRole("button", { name: "Register" }));

    // Mock mints REF-<first 8 uppercased>; invalidation refetches the list.
    expect(await screen.findByText("REF-DEADBEEF", undefined, FIND_OPTS)).toBeInTheDocument();
  });

  it("keeps input and shows the problem near the submit on a conflict", async () => {
    renderWithClient(<ReferrersSection onOpenReferrer={vi.fn()} />);
    await screen.findByText("REF-ACME8821", undefined, FIND_OPTS);

    fireEvent.click(screen.getByRole("button", { name: "Register referrer" }));
    const input = await screen.findByLabelText("Customer UUID", undefined, FIND_OPTS);
    // Already registered in mock data → 409 conflict.
    fireEvent.change(input, { target: { value: "a1b2c3d4-9f10-4e8b-b2aa-101010101001" } });
    fireEvent.click(screen.getByRole("button", { name: "Register" }));

    expect(
      await screen.findByText(
        "This customer is already registered as a referrer.",
        undefined,
        FIND_OPTS,
      ),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Customer UUID")).toHaveValue(
      "a1b2c3d4-9f10-4e8b-b2aa-101010101001",
    );
  });
});
