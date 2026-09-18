import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import * as React from "react";
import { describe, expect, it, vi } from "vitest";
import type { ReactElement, ReactNode } from "react";

import { useGroupedEconomics } from "../api/queries";
import type { BreakdownAxis } from "../api/types";
import { GroupingFieldBreakdown } from "./grouping-field-breakdown";

vi.mock("@tanstack/react-router", async (importOriginal) => {
  const actual =
    await importOriginal<typeof import("@tanstack/react-router")>();
  return {
    ...actual,
    Link: (props: {
      to?: string;
      children?: ReactNode;
      className?: string;
    }) => (
      <a className={props.className} href={props.to ?? "#"}>
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

/** Stateful harness mirroring how the page wires picker + query together. */
function Harness() {
  const [groupBy, setGroupBy] =
    React.useState<BreakdownAxis>("provider");
  const query = useGroupedEconomics(WINDOW, groupBy);
  return (
    <GroupingFieldBreakdown
      query={query}
      groupBy={groupBy}
      onGroupByChange={setGroupBy}
      currency="usd"
    />
  );
}

describe("GroupingFieldBreakdown", () => {
  it("switches the breakdown when a different axis is picked", async () => {
    renderWithClient(<Harness />);

    expect(await screen.findByText("openai")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Event type" }));

    expect(await screen.findByText("chat.completion")).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.queryByText("openai")).not.toBeInTheDocument(),
    );
    // Ten event types → top 8 plus a folded Other bar.
    expect(screen.getByText("Other (2)")).toBeInTheDocument();
  });

  it("shows an empty state with a real CTA when the window has no usage", () => {
    // ⚠ NO ROWS AT ALL, which is what a GROUPED question over an empty window
    // answers (#501). The report this replaced always returned its breakdown
    // blocks, empty or not; a grouped answer's rows ARE the groups the data
    // produced, so a window with no usage produces none — and that is the
    // shape this empty state has to handle.
    renderWithClient(
      <GroupingFieldBreakdown
        query={{
          data: { rows: [], context: [], held_from: null, measurement_horizon: false },
          isPending: false,
          isError: false,
          error: null,
          refetch: () => {},
        }}
        groupBy="provider"
        onGroupByChange={() => {}}
        currency="usd"
      />,
    );

    expect(screen.getByText("No usage in this window")).toBeInTheDocument();
    const cta = screen.getByRole("link", { name: "Send a test event" });
    expect(cta).toHaveAttribute("href", "/developers");
  });

  // ⚠ THE SAME EMPTY LIST, OVER A WINDOW REACHING BACK PAST THE RECORDS IT
  // READS, IS NOT "NO USAGE" (#510) — it is a stretch UBB no longer holds.
  it("says the window is past the horizon rather than that nothing happened", () => {
    renderWithClient(
      <GroupingFieldBreakdown
        query={{
          data: { rows: [], context: [], held_from: "2020-09-18", measurement_horizon: false },
          isPending: false,
          isError: false,
          error: null,
          refetch: () => {},
        }}
        groupBy="provider"
        onGroupByChange={() => {}}
        currency="usd"
      />,
    );

    expect(screen.queryByText("No usage in this window")).not.toBeInTheDocument();
    expect(screen.getByText(/UBB holds economic records from Sep 18, 2020/)).toBeInTheDocument();
  });

  // ⚠ Grouped by a supplier, the workspace's subscription cannot be placed
  // (#510): each row's revenue reads unavailable at that grain. The bars used
  // to plot the usage alone as "Revenue by provider", dropping $199 without a
  // word. Now the bars draw the cost, the revenue is named as its state, and
  // the subscription is stated as the coarser figure — never as a zero.
  it("draws revenue it cannot place as its state, with the subscription as context", async () => {
    const { container } = renderWithClient(<Harness />);

    expect(await screen.findByText("openai")).toBeInTheDocument();
    expect(
      screen.getByText("Provider cost by provider, top 8 shown. Revenue by provider: Unavailable at this grain."),
    ).toBeInTheDocument();
    expect(container.querySelector("[data-revenue-context]")).toHaveTextContent(
      "$199.00 of revenue from subscriptions can only be placed by customer, per day",
    );
    expect(screen.queryByText("$0.00")).not.toBeInTheDocument();
  });
});
