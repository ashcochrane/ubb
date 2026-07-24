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
    expect(await screen.findByText("$9,370.40")).toBeInTheDocument();
    expect(screen.getByText("$5,330.42")).toBeInTheDocument();
    expect(screen.getByText("43.1% margin")).toBeInTheDocument();
    expect(screen.getByText("Customers with usage")).toBeInTheDocument();
    // Events total from the windowed usage analytics.
    expect(await screen.findByText("184.2k")).toBeInTheDocument();
  });

  it("lists top customers with shortened ids and a view-all link", async () => {
    renderWithClient(<OverviewPage search={{}} onSearchChange={() => {}} />);

    // Margin list rows have no external_id — the table shows short UUIDs.
    expect(await screen.findByText("3e7f0a41…")).toBeInTheDocument();
    expect(screen.getByText("View all customers")).toBeInTheDocument();
    // The unprofitable customer's negative margin renders signed.
    expect(screen.getByText("-$249.87")).toBeInTheDocument();
  });

  it("surfaces the unprofitable-customers alert when the API reports one", async () => {
    renderWithClient(<OverviewPage search={{}} onSearchChange={() => {}} />);

    expect(
      await screen.findByText("1 customer is unprofitable this period"),
    ).toBeInTheDocument();
    expect(screen.getByText("atlas-fintech")).toBeInTheDocument();
  });

  it("renders the provider breakdown and no getting-started card for an active workspace", async () => {
    renderWithClient(<OverviewPage search={{}} onSearchChange={() => {}} />);

    expect(await screen.findByText("openai")).toBeInTheDocument();
    // Lifetime events > 0 in the mock story → the workspace is not new.
    expect(screen.queryByText("Get started with UBB")).not.toBeInTheDocument();
  });
});
