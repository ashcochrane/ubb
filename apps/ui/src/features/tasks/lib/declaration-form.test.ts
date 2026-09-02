import { describe, expect, it } from "vitest";

import type { KindOfWork } from "../api/types";
import {
  amountToMicros,
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
  default_provider_cost_limit_micros: 1_500_000,
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
      default_provider_cost_limit_micros: 4_000_000,
      silence_window_seconds: 300,
      absolute_deadline_seconds: null,
      required_dimensions: ["model"],
      retired: true,
    });
  });

  it("starts a new kind with no grouping fields and not retired", () => {
    expect(
      toDeclaration({ ...formDefaults(), key: "podcast-cut", pricing_mode: "fixed" }),
    ).toMatchObject({ key: "podcast-cut", pricing_mode: "fixed", required_dimensions: [], retired: false });
  });
});

describe("the key rule", () => {
  it("guards a key being minted, and steps aside on a revision so an API-declared spelling stays revisable", () => {
    const values = formDefaults(STANDING);
    expect(kindFormSchema.safeParse(values).success).toBe(false);
    expect(revisionFormSchema.safeParse(values).success).toBe(true);
    expect(kindFormSchema.safeParse({ ...formDefaults(), key: "video-render" }).success).toBe(true);
  });
});
