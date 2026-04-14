import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { DeltaPill } from "./delta-pill";

describe("DeltaPill", () => {
  it("renders the label", () => {
    render(<DeltaPill trend="up">+14.2% vs prev</DeltaPill>);
    expect(screen.getByText("+14.2% vs prev")).toBeInTheDocument();
  });

  it.each(["up", "down", "flat"] as const)(
    "exposes data-trend=%s for the %s trend",
    (trend) => {
      render(<DeltaPill trend={trend}>x</DeltaPill>);
      const pill = screen.getByText("x").closest("span");
      expect(pill).toHaveAttribute("data-trend", trend);
    },
  );

  it("renders a distinct icon shape per trend", () => {
    // up + down render a <path>; flat renders a <rect>.
    const { container: up } = render(<DeltaPill trend="up">a</DeltaPill>);
    const { container: down } = render(<DeltaPill trend="down">b</DeltaPill>);
    const { container: flat } = render(<DeltaPill trend="flat">c</DeltaPill>);

    expect(up.querySelector("path")).not.toBeNull();
    expect(down.querySelector("path")).not.toBeNull();
    expect(flat.querySelector("rect")).not.toBeNull();
    expect(flat.querySelector("path")).toBeNull();
  });
});
