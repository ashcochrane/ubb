import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { ReactElement, ReactNode } from "react";

import { GettingStartedCard } from "./getting-started-card";

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

describe("GettingStartedCard", () => {
  it("derives checklist state from real workspace state", async () => {
    renderWithClient(<GettingStartedCard needsStripe={true} />);

    // Mock story: a key, a rate-card book, and Stripe all exist; no events yet.
    expect(await screen.findByText("3 of 4 complete.")).toBeInTheDocument();

    expect(
      screen.getByText("Create an API key").closest("li"),
    ).toHaveAttribute("data-state", "done");
    expect(
      screen.getByText("Set up pricing").closest("li"),
    ).toHaveAttribute("data-state", "done");
    expect(
      screen.getByText("Connect Stripe").closest("li"),
    ).toHaveAttribute("data-state", "done");

    const recordStep = screen
      .getByText("Record your first usage event")
      .closest("li");
    expect(recordStep).toHaveAttribute("data-state", "todo");
    expect(
      screen.getByRole("link", { name: /Send a test event/ }),
    ).toHaveAttribute("href", "/developers");
  });

  it("omits the Stripe step for tenants without the billing product", async () => {
    renderWithClient(<GettingStartedCard needsStripe={false} />);

    expect(await screen.findByText("2 of 3 complete.")).toBeInTheDocument();
    expect(screen.queryByText("Connect Stripe")).not.toBeInTheDocument();
  });
});
