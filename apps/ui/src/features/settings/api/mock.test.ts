// The settings mock enforced its own copy of the backend's strict
// cost-coverage rule: patching the setting on with no active cost pricing book
// threw 422 `no_cost_cards`. #321 deleted the setting, the backend guard and
// that problem code, so the mock's copy had to go too — a mock that keeps a
// rule the server has dropped is a SECOND definition of the behaviour, and it
// is the one a developer meets first, because mock mode is this console's
// default.
//
// The absence is asserted rather than merely not exercised: a test that simply
// stopped patching the setting would pass just as well against a mock that
// still refused, and would go on passing if someone reinstated the rule.

import { describe, expect, it } from "vitest";

import { ApiProblem } from "@/api/problem";
import {
  readMockTenantConfig,
  writeMockTenantConfig,
} from "@/hooks/use-tenant-config";

import { updateTenantConfig } from "./mock";

describe("the settings mock has no cost-coverage rule left to enforce", () => {
  it("patches an unrelated setting without asking about cost pricing books", async () => {
    const before = readMockTenantConfig();
    try {
      const next = await updateTenantConfig({ automatic_tax_enabled: true });
      expect(next.automatic_tax_enabled).toBe(true);
    } finally {
      writeMockTenantConfig(before);
    }
  });

  it("never throws the retired enable-time refusal, whatever is patched", async () => {
    // Every key the mock still honours, driven through in one call. Under the
    // deleted rule the coverage branch ran before the tax branch, so a
    // reinstated refusal would surface here rather than being ordered around.
    const before = readMockTenantConfig();
    try {
      const next = await updateTenantConfig({
        automatic_tax_enabled: true,
        enforcement_mode: "off",
      });
      expect(next.enforcement_mode).toBe("off");
    } catch (error) {
      // Fail loudly and specifically if the retired code ever comes back.
      expect(
        error instanceof ApiProblem ? error.code : String(error),
      ).not.toBe("no_cost_cards");
      throw error;
    } finally {
      writeMockTenantConfig(before);
    }
  });

  it("carries no message for the retired problem code", async () => {
    // `problem.ts`'s message map is the console's own copy of the registry's
    // vocabulary, and nothing compares the two — so the entry for a code the
    // API can no longer return would sit there indefinitely.
    const { problemMessage } = await import("@/api/problem");
    const retired = new ApiProblem({
      status: 422,
      code: "no_cost_cards",
      title: "No cost cards",
    });

    expect(problemMessage(retired)).toBe("No cost cards");
  });
});
