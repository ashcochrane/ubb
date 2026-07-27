import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { ReactElement, ReactNode } from "react";

import { OverviewPage } from "./overview-page";

// The page renders real <Link>s; swap them for anchors so no router is needed.
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

describe("OverviewPage", () => {
  it("renders the stat row from the margin summary and analytics", async () => {
    renderWithClient(<OverviewPage search={{}} onSearchChange={() => {}} />);

    // Total revenue / COGS / margin% from the mock margin summary.
    expect(await screen.findByText("$764.90")).toBeInTheDocument();
    expect(screen.getByText("$563.60")).toBeInTheDocument();
    expect(screen.getByText("26.3% margin")).toBeInTheDocument();
    expect(screen.getByText("Customers with usage")).toBeInTheDocument();
    // Events total from the windowed usage analytics.
    expect(await screen.findByText("93.6k")).toBeInTheDocument();
  });

  it("lists top customers with shortened ids and a view-all link", async () => {
    renderWithClient(<OverviewPage search={{}} onSearchChange={() => {}} />);

    // Margin list rows have no external_id — the table shows short UUIDs
    // (acme-corp has the highest revenue in the shared mock roster).
    expect(await screen.findByText("1f0c9c4e…")).toBeInTheDocument();
    expect(screen.getByText("View all customers")).toBeInTheDocument();
    // nova-ai's negative gross margin renders signed in the table.
    expect(screen.getByText("-$88.00")).toBeInTheDocument();
  });

  it("surfaces the unprofitable-customers alert when the API reports them", async () => {
    renderWithClient(<OverviewPage search={{}} onSearchChange={() => {}} />);

    expect(
      await screen.findByText("2 customers are unprofitable this period"),
    ).toBeInTheDocument();
    expect(screen.getByText("nova-ai")).toBeInTheDocument();
    expect(screen.getByText("luna-labs")).toBeInTheDocument();
    // Threshold-aware copy links to the margin-alert settings.
    expect(
      screen.getByRole("link", { name: "Review the threshold in settings" }),
    ).toHaveAttribute("href", "/settings");
  });

  it("renders the provider breakdown and no getting-started card for an active workspace", async () => {
    renderWithClient(<OverviewPage search={{}} onSearchChange={() => {}} />);

    expect(await screen.findByText("openai")).toBeInTheDocument();
    // Lifetime events > 0 in the mock story → the workspace is not new.
    expect(screen.queryByText("Get started with UBB")).not.toBeInTheDocument();
  });
});
