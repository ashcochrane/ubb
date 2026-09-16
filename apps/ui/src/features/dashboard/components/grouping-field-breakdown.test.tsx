import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import * as React from "react";
import { describe, expect, it, vi } from "vitest";
import type { ReactElement, ReactNode } from "react";

import { useGroupedEconomics } from "../api/queries";
import type { BreakdownDimension } from "../api/types";
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
    React.useState<BreakdownDimension>("provider");
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
          data: [],
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
});
