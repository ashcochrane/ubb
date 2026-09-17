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
  it("renders the stat row from the one query", async () => {
    renderWithClient(<OverviewPage search={{}} onSearchChange={() => {}} />);

    // ⚠ THIS CASE NAMED A ROUTE THAT NO LONGER EXISTS UNTIL #507. It said the
    // three figures below came "from the margin summary" — one of the nine
    // reports #501 collapsed, and one of the reads slice 7 §8 severs from the
    // margin snapshot. They are the window's own economics now, ungrouped, and
    // the card after them is the same question grouped by the customer axis.
    // Total revenue / COGS / margin% for the window.
    // ⚠ $764.90 UNTIL #497: the window total excluded nova-ai's $88.00 of
    // billed usage, which the deleted customer-level switch did not count as
    // revenue. Every customer's billed usage is revenue now, so the total is
    // the whole of it and the margin percentage below rises with it.
    expect(await screen.findByText("$852.90")).toBeInTheDocument();
    // THE HEADLINE COGS IS A FLOOR, and it says so (#330). The mock window
    // holds four events whose supplier cost UBB never learned, so the total
    // over them can only be higher — and the margin computed against it can
    // only be lower.
    expect(screen.getByText("at least $563.60")).toBeInTheDocument();
    expect(screen.getByText("at most 33.9% margin")).toBeInTheDocument();
    // ⚠ **AWAITED, NOT READ SYNCHRONOUSLY, AND THE REASON IS #501.** This
    // card used to read `customer_count` off the SAME response as the three
    // above it — the deleted margin summary published the count as a field,
    // so awaiting the revenue figure guaranteed the count had arrived too.
    // Counting customers is now the row count of the window grouped by the
    // customer axis, which is a SECOND request, so the card arrives on its own
    // schedule and a synchronous read races it. (It is not a second round trip:
    // the economics table below asks the identical question and shares the
    // cache entry. It is a second PROMISE, which is what matters here.)
    expect(await screen.findByText("Customers with usage")).toBeInTheDocument();
    // Events total, back on the first response.
    expect(await screen.findByText("93.6k")).toBeInTheDocument();
  });

  it("lists top customers with shortened ids and a view-all link", async () => {
    renderWithClient(<OverviewPage search={{}} onSearchChange={() => {}} />);

    // The customer axis groups by IDENTITY and publishes no external id — a
    // tenant's own word for a row belongs to the surface that renders it — so
    // the table shows short UUIDs (acme-corp has the highest revenue in the
    // shared mock roster).
    expect(await screen.findByText("1f0c9c4e…")).toBeInTheDocument();
    expect(screen.getByText("View all customers")).toBeInTheDocument();
    // nova-ai's gross margin renders bounded: it is the one customer in the
    // mock story holding uncosted events, so its margin is an upper bound —
    // the unlearned costs can only take it further down (#330). It is
    // break-even rather than minus its whole cost since #497; the bound is
    // the claim, and at zero it is at its most load-bearing.
    expect(screen.getByText("at most $0.00")).toBeInTheDocument();
  });

  // The other side of the same fact, on the same page. A count belongs to the
  // customer whose events it is about, so a table that bounded every row on the
  // window's total would caveat four customers for one customer's missing
  // supplier invoice.
  it("bounds only the customer whose costs are incomplete", async () => {
    renderWithClient(<OverviewPage search={{}} onSearchChange={() => {}} />);

    // luna-labs also runs at a loss, and every one of its costs is known.
    expect(await screen.findByText("-$14.70")).toBeInTheDocument();
    expect(screen.queryByText("at most -$14.70")).not.toBeInTheDocument();
  });

  it("surfaces the unprofitable-customers alert when the API reports them", async () => {
    renderWithClient(<OverviewPage search={{}} onSearchChange={() => {}} />);

    expect(
      await screen.findByText("2 customers are unprofitable this period"),
    ).toBeInTheDocument();
    expect(screen.getByText("nova-ai")).toBeInTheDocument();
    expect(screen.getByText("luna-labs")).toBeInTheDocument();
    // ONE PAGE MUST NOT DISAGREE WITH ITSELF ABOUT ONE CUSTOMER (#330). The
    // economics table below already bounds nova-ai's margin, and this alert
    // reads the same customer from a response carrying the same count — an
    // alert about unprofitability is the last place to overstate a margin.
    expect(screen.getByText("at most $0.00 margin")).toBeInTheDocument();
    // luna-labs' costs are all known, so its margin is the figure it is.
    expect(screen.getByText("-$14.70 margin")).toBeInTheDocument();
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
