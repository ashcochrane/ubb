import { render, screen } from "@testing-library/react";
import { fireEvent } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { EmptyState } from "./empty-state";

describe("EmptyState", () => {
  it("renders the title alone", () => {
    render(<EmptyState title="No customers yet" />);
    expect(screen.getByText("No customers yet")).toBeInTheDocument();
  });

  it("renders the description when provided", () => {
    render(
      <EmptyState
        title="No events"
        description="Try changing the date range."
      />,
    );
    expect(screen.getByText("Try changing the date range.")).toBeInTheDocument();
  });

  it("renders the action button and calls onClick", () => {
    const handleClick = vi.fn();
    render(
      <EmptyState
        title="No pricing cards"
        action={{ label: "Create card", onClick: handleClick }}
      />,
    );
    const button = screen.getByRole("button", { name: "Create card" });
    fireEvent.click(button);
    expect(handleClick).toHaveBeenCalledTimes(1);
  });
});
