// The family words are SPELLED here rather than asked of the binding, so a
// binding pointed at the wrong concept's keys goes red rather than green.

import { describe, expect, it } from "vitest";

import { CONTROL_FAMILY_VALUES } from "@/lib/vocabulary";

import {
  controlFamilyLabel,
  CUSTOMER_SPEND_POOL_TITLE,
  WALLET_POLICY_TITLE,
} from "./control-family";

describe("the family words", () => {
  it("binds the catalogue's wording for each of the registry's four families", () => {
    expect(CONTROL_FAMILY_VALUES).toHaveLength(4);
    expect(controlFamilyLabel("ceiling")).toBe("Ceiling");
    expect(controlFamilyLabel("customer_spend_pool")).toBe("Customer spend pool");
    expect(controlFamilyLabel("wallet_policy")).toBe("Wallet policy");
    expect(controlFamilyLabel("admission_control")).toBe("Admission control");
  });

  it("heads the two families' surfaces with the same words", () => {
    expect(CUSTOMER_SPEND_POOL_TITLE).toBe("Customer spend pool");
    expect(WALLET_POLICY_TITLE).toBe("Wallet policy");
  });
});
