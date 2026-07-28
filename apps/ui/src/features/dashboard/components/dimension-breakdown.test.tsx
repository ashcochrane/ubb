import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import * as React from "react";
import { describe, expect, it, vi } from "vitest";
import type { ReactElement, ReactNode } from "react";

import { useWindowAnalytics } from "../api/queries";
import type { BreakdownDimension, UsageAnalytics } from "../api/types";
import { DimensionBreakdown } from "./dimension-breakdown";

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
  const [dimension, setDimension] =
    React.useState<BreakdownDimension>("provider");
  const query = useWindowAnalytics(WINDOW, dimension);
  return (
    <DimensionBreakdown
      query={query}
      dimension={dimension}
      onDimensionChange={setDimension}
      currency="usd"
    />
  );
}

describe("DimensionBreakdown", () => {
  it("switches the breakdown when a different dimension is picked", async () => {
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
    const empty: UsageAnalytics = {
      total_events: 0,
      total_billed_cost_micros: 0,
      total_provider_cost_micros: 0,
      usage_markup_margin_micros: 0,
      by_provider: [],
      by_event_type: [],
      by_task_type: [],
      by_customer: [],
      by_tag: [],
      breakdowns: { provider: [] },
    };
    renderWithClient(
      <DimensionBreakdown
        query={{
          data: empty,
          isPending: false,
          isError: false,
          error: null,
          refetch: () => {},
        }}
        dimension="provider"
        onDimensionChange={() => {}}
        currency="usd"
      />,
    );

    expect(screen.getByText("No usage in this window")).toBeInTheDocument();
    const cta = screen.getByRole("link", { name: "Send a test event" });
    expect(cta).toHaveAttribute("href", "/developers");
  });
});
