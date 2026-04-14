import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Stepper } from "./stepper";

const STEPS = [
  { label: "Source" },
  { label: "Details" },
  { label: "Dimensions" },
  { label: "Review" },
];

describe("Stepper", () => {
  it("renders every step label", () => {
    render(<Stepper steps={STEPS} currentIndex={1} />);
    for (const step of STEPS) {
      expect(screen.getByText(step.label)).toBeInTheDocument();
    }
  });

  it("marks the current step as active", () => {
    render(<Stepper steps={STEPS} currentIndex={1} />);
    // The active step circle contains the 1-based index number "2".
    const activeCircle = screen.getByText("2");
    expect(activeCircle).toHaveAttribute("data-state", "active");
  });

  it("renders a check mark for each completed step", () => {
    render(<Stepper steps={STEPS} currentIndex={2} />);
    // Two steps are completed (indexes 0 and 1).
    const checks = screen.getAllByTestId("stepper-check");
    expect(checks).toHaveLength(2);
  });
});
