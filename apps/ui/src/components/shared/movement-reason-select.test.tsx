// The reason control offers the registry's six in the catalogue's words, each
// carrying its token, and "none" first (#479).
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { MOVEMENT_REASONS } from "@/lib/movement-reason";

import { MovementReasonSelect } from "./movement-reason-select";

describe("MovementReasonSelect", () => {
  it("offers none, then every reason by its words with its token as the value", () => {
    render(<MovementReasonSelect aria-label="Reason" />);

    const options = screen.getAllByRole("option") as HTMLOptionElement[];
    expect(options.map((option) => option.value)).toEqual(["", ...MOVEMENT_REASONS]);
    expect(options[0]?.textContent).toBe("No reason given");
    expect(screen.getByRole("option", { name: "Write-off" })).toHaveValue("write_off");
  });
});
