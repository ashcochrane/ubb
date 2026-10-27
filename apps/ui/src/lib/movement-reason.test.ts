// Why money moved by hand (#479): the form field admits the registry's six
// reasons or none, and "none" is sent as null rather than as an empty string
// the route would refuse.
import { describe, expect, it } from "vitest";

import {
  MOVEMENT_REASONS,
  movementReasonField,
  movementReasonLabel,
  movementReasonToSend,
} from "@/lib/movement-reason";
import { REASON_CODE_KNOWN_VALUES } from "@/lib/vocabulary";

describe("movement reason", () => {
  it("admits every registry reason, and none", () => {
    for (const reason of ["", ...MOVEMENT_REASONS]) {
      expect(movementReasonField.safeParse(reason).success).toBe(true);
    }
  });

  it("refuses anything else — a stop cause above all, the field's old namesake", () => {
    for (const wrong of ["bogus", REASON_CODE_KNOWN_VALUES[0]]) {
      expect(movementReasonField.safeParse(wrong).success).toBe(false);
    }
  });

  it("sends none as null and a reason as itself", () => {
    expect(movementReasonToSend("")).toBeNull();
    expect(movementReasonToSend("write_off")).toBe("write_off");
  });

  it("words every reason from the catalogue", () => {
    expect(MOVEMENT_REASONS.map((reason) => movementReasonLabel(reason))).toEqual([
      "Correction",
      "Goodwill",
      "Chargeback",
      "Write-off",
      "Migration",
      "Other",
    ]);
  });
});
