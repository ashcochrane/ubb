import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Sparkline } from "./sparkline";

describe("Sparkline", () => {
  it("renders an svg for non-empty data", () => {
    const { container } = render(
      <Sparkline data={[1, 2, 3, 2, 4]} color="#a16a4a" />,
    );
    const svg = container.querySelector("svg");
    expect(svg).not.toBeNull();
  });

  it("returns null for empty data", () => {
    const { container } = render(<Sparkline data={[]} color="#a16a4a" />);
    expect(container.firstChild).toBeNull();
  });
});
