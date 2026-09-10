import { describe, expect, it } from "vitest";

import type { KindOfWork } from "../api/types";
import {
  amountToMicros,
  CEILING_BOTH,
  CEILING_NEITHER,
  formDefaults,
  kindFormSchema,
  microsToAmount,
  revisionFormSchema,
  toDeclaration,
} from "./declaration-form";

const STANDING: KindOfWork = {
  key: "legacy.ocr",
  kind: "subtask",
  pricing_mode: "fixed",
  task_cogs_ceiling_micros: 1_500_000,
  uncapped: false,
  silence_window_seconds: 300,
  absolute_deadline_seconds: null,
  required_dimensions: ["model"],
  retired: true,
  retired_at: "2026-06-30T09:00:00Z",
};

describe("an amount on the form", () => {
  it("becomes integer micros exactly once, and an empty one becomes none", () => {
    expect(amountToMicros("2.50")).toBe(2_500_000);
    expect(amountToMicros(" 3 ")).toBe(3_000_000);
    expect(amountToMicros("")).toBeNull();
    expect(microsToAmount(1_500_000)).toBe("1.5");
    expect(microsToAmount(null)).toBe("");
  });
});

describe("the declaration a form states", () => {
  it("reads the identity and the regime off the standing row on a revision, never off the controls", () => {
    const values = {
      ...formDefaults(STANDING),
      key: "something-else",
      kind: "task" as const,
      pricing_mode: "event_priced" as const,
      ceiling: "4",
    };
    expect(toDeclaration(values, STANDING)).toEqual({
      key: "legacy.ocr",
      kind: "subtask",
      pricing_mode: "fixed",
      task_cogs_ceiling_micros: 4_000_000,
      uncapped: false,
      silence_window_seconds: 300,
      absolute_deadline_seconds: null,
      required_dimensions: ["model"],
      retired: true,
    });
  });

  it("starts a new kind with no grouping fields and not retired", () => {
    expect(
      toDeclaration({ ...formDefaults(), key: "podcast-cut", pricing_mode: "fixed", ceiling: "2" }),
    ).toMatchObject({ key: "podcast-cut", pricing_mode: "fixed", required_dimensions: [], retired: false });
  });

  it("states uncapped the way the wire states it: the flag, and no figure beside it", () => {
    expect(toDeclaration({ ...formDefaults(), key: "batch-ocr", uncapped: true })).toMatchObject({
      task_cogs_ceiling_micros: null,
      uncapped: true,
    });
    expect(formDefaults({ ...STANDING, task_cogs_ceiling_micros: null, uncapped: true })).toMatchObject(
      { ceiling: "", uncapped: true },
    );
  });
});

describe("the ceiling rule (#453, #150 §8)", () => {
  const blank = { ...formDefaults(), key: "podcast-cut" };

  function refusal(values: typeof blank): string | undefined {
    const result = kindFormSchema.safeParse(values);
    return result.success ? undefined : result.error.issues.find((i) => i.path[0] === "ceiling")?.message;
  }

  it("refuses a declaration that states neither an amount nor uncapped", () => {
    expect(refusal({ ...blank, ceiling: "", uncapped: false })).toBe(CEILING_NEITHER);
  });

  it("refuses one that states both", () => {
    expect(refusal({ ...blank, ceiling: "2.50", uncapped: true })).toBe(CEILING_BOTH);
  });

  it("accepts exactly one of the two", () => {
    expect(refusal({ ...blank, ceiling: "2.50", uncapped: false })).toBeUndefined();
    expect(refusal({ ...blank, ceiling: "", uncapped: true })).toBeUndefined();
  });

  it("says in so many words that a kind of work never inherits the workspace default", () => {
    expect(CEILING_NEITHER).toMatch(/never inherits the workspace default/);
  });
});

describe("the key rule", () => {
  it("guards a key being minted, and steps aside on a revision so an API-declared spelling stays revisable", () => {
    const values = formDefaults(STANDING);
    expect(kindFormSchema.safeParse(values).success).toBe(false);
    expect(revisionFormSchema.safeParse(values).success).toBe(true);
    expect(
      kindFormSchema.safeParse({ ...formDefaults(), key: "video-render", ceiling: "3" }).success,
    ).toBe(true);
  });
});
