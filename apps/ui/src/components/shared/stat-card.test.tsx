import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { StatCard } from "./stat-card";

describe("StatCard", () => {
  it("renders label and value", () => {
    render(<StatCard label="Revenue" value="$1,247" />);
    expect(screen.getByText("Revenue")).toBeInTheDocument();
    expect(screen.getByText("$1,247")).toBeInTheDocument();
  });

  it("renders the change delta when provided", () => {
    render(
      <StatCard
        label="Revenue"
        value="$1,247"
        change={{ value: "12% vs prev", positive: true }}
      />,
    );
    // Positive change should be prefixed with a + sign.
    expect(screen.getByText("+12% vs prev")).toBeInTheDocument();
  });

  it("renders the subtitle when provided without a change", () => {
    render(
      <StatCard
        label="Mapped"
        value={42}
        subtitle="Fully connected"
      />,
    );
    expect(screen.getByText("Fully connected")).toBeInTheDocument();
  });

  it("applies the purple variant via data attribute", () => {
    render(
      <StatCard
        label="Blended margin"
        value="32%"
        variant="purple"
      />,
    );
    const card = screen.getByText("Blended margin").parentElement;
    expect(card).toHaveAttribute("data-variant", "purple");
  });

  it("renders a DeltaPill when trend is set", () => {
    render(
      <StatCard label="Revenue" value="$8,420" trend="up" trendLabel="+14.2% vs prev" />,
    );
    expect(screen.getByText("+14.2% vs prev")).toBeInTheDocument();
  });

  it("renders a sparkline slot when provided", () => {
    render(
      <StatCard
        label="Revenue"
        value="$8,420"
        variant="raised"
        sparkline={<div data-testid="spark" />}
      />,
    );
    expect(screen.getByTestId("spark")).toBeInTheDocument();
  });

  it("applies the raised variant via data attribute", () => {
    render(<StatCard label="Revenue" value="$8,420" variant="raised" />);
    const card = screen.getByText("Revenue").parentElement;
    expect(card).toHaveAttribute("data-variant", "raised");
  });
});
