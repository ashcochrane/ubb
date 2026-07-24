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

function firstDataRowText(): string {
  const rows = screen.getAllByRole("row");
  // rows[0] is the header row.
  return rows[1]?.textContent ?? "";
}

describe("CustomerEconomicsTable", () => {
  it("sorts by revenue by default and re-sorts on toggle", async () => {
    renderWithClient(
      <CustomerEconomicsTable window={WINDOW} meterOnly={false} currency="usd" />,
    );

    // orbit-labs has the highest revenue in the mock story.
    expect(await screen.findByText("3e7f0a41…")).toBeInTheDocument();
    expect(firstDataRowText()).toContain("3e7f0a41…");

    // helios-devtools has the best margin percentage.
    fireEvent.click(screen.getByRole("button", { name: "Margin %" }));
    expect(firstDataRowText()).toContain("5fd0c7a2…");

    // Back to revenue.
    fireEvent.click(screen.getByRole("button", { name: "Revenue" }));
    expect(firstDataRowText()).toContain("3e7f0a41…");
  });

  it("marks negative margins and links every row to the customer page", async () => {
    renderWithClient(
      <CustomerEconomicsTable window={WINDOW} meterOnly={false} currency="usd" />,
    );

    // atlas-fintech: negative gross margin rendered from the API's figures.
    expect(await screen.findByText("-$249.87")).toBeInTheDocument();
    const orbitLink = screen.getByRole("link", { name: "3e7f0a41…" });
    expect(orbitLink).toHaveAttribute(
      "title",
      "3e7f0a41-5c2d-4b8e-9f10-8a64c1d2e301",
    );
  });
});
