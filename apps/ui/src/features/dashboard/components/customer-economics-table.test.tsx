import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { ReactElement, ReactNode } from "react";

import { CustomerEconomicsTable } from "./customer-economics-table";

vi.mock("@tanstack/react-router", async (importOriginal) => {
  const actual =
    await importOriginal<typeof import("@tanstack/react-router")>();
  return {
    ...actual,
    Link: (props: {
      to?: string;
      children?: ReactNode;
      className?: string;
      title?: string;
    }) => (
      <a className={props.className} href={props.to ?? "#"} title={props.title}>
        {props.children}
      </a>
    ),
  };
});

function renderWithClient(ui: ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>{ui}</QueryClientProvider>,
  );
}

const WINDOW = { start_date: "2026-07-01", end_date: "2026-07-23" };

function dataRowText(index: number): string {
  const rows = screen.getAllByRole("row");
  // rows[0] is the header row.
  return rows[index + 1]?.textContent ?? "";
}

describe("CustomerEconomicsTable", () => {
  it("sorts by revenue by default and re-sorts on toggle", async () => {
    renderWithClient(
      <CustomerEconomicsTable window={WINDOW} meterOnly={false} currency="usd" />,
    );

    // acme-corp leads on every sort; the runner-up distinguishes the keys.
    // Revenue: acme-corp:eng ($120.40) is second.
    expect(await screen.findByText("1f0c9c4e…")).toBeInTheDocument();
    expect(dataRowText(0)).toContain("1f0c9c4e…");
    expect(dataRowText(1)).toContain("4c3f6d51…");

    // Margin %: acme-corp:research (20.1%) edges out :eng (20%).
    fireEvent.click(screen.getByRole("button", { name: "Margin %" }));
    expect(dataRowText(1)).toContain("5d4a5e62…");

    // Back to revenue.
    fireEvent.click(screen.getByRole("button", { name: "Revenue" }));
    expect(dataRowText(1)).toContain("4c3f6d51…");
  });

  it("marks negative margins and links every row to the customer page", async () => {
    renderWithClient(
      <CustomerEconomicsTable window={WINDOW} meterOnly={false} currency="usd" />,
    );

    // nova-ai: negative gross margin rendered from the API's figures — and
    // bounded, because it is the one customer holding uncosted events (#330).
    expect(await screen.findByText("at most -$88.00")).toBeInTheDocument();
    const acmeLink = screen.getByRole("link", { name: "1f0c9c4e…" });
    expect(acmeLink).toHaveAttribute(
      "title",
      "1f0c9c4e-8f2a-4a1e-9d3b-6a1f00000001",
    );
  });

  // The rule this table has to get right, stated as a contrast rather than as
  // one assertion: nova-ai's COGS can only be higher and its margin only lower,
  // while acme-corp's are figures. A row that bounded both, or neither, would
  // pass a single-row test and mislead on the page.
  it("says which COGS is a floor and leaves the settled ones alone", async () => {
    renderWithClient(
      <CustomerEconomicsTable window={WINDOW} meterOnly={false} currency="usd" />,
    );

    expect(await screen.findByText("at least $88.00")).toBeInTheDocument();
    // acme-corp's COGS is whole, and renders as the figure it is.
    expect(screen.getByText("$274.00")).toBeInTheDocument();
    expect(screen.queryByText("at least $274.00")).not.toBeInTheDocument();
  });
});
