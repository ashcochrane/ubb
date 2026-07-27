import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { DisabledHint } from "./disabled-hint";

describe("DisabledHint", () => {
  it("wraps a disabled control in a focusable span carrying the hint", () => {
    render(
      <DisabledHint disabled hint="Requires the Admin role.">
        <button disabled>Void grant</button>
      </DisabledHint>,
    );
    const wrapper = screen.getByLabelText("Requires the Admin role.");
    expect(wrapper.tagName).toBe("SPAN");
    expect(wrapper).toHaveAttribute("tabindex", "0");
    expect(wrapper).toHaveAttribute("title", "Requires the Admin role.");
    expect(wrapper).toContainElement(screen.getByRole("button", { name: "Void grant" }));
  });

  it("renders children untouched when not disabled", () => {
    render(
      <DisabledHint disabled={false} hint="Requires the Admin role.">
        <button>Void grant</button>
      </DisabledHint>,
    );
    expect(screen.queryByTitle("Requires the Admin role.")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Void grant" })).toBeInTheDocument();
  });

  it("renders children untouched when no hint is provided", () => {
    render(
      <DisabledHint disabled hint={undefined}>
        <button disabled>Void grant</button>
      </DisabledHint>,
    );
    expect(screen.getByRole("button", { name: "Void grant" })).toBeInTheDocument();
    expect(document.querySelector("span[tabindex]")).toBeNull();
  });
});
