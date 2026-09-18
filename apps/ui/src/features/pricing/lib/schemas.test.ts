import { describe, expect, it } from "vitest";

import { blankRule, ruleFormSchema } from "./schemas";

describe("a named selector's refusal", () => {
  // ⚠ IN THE WORDS ITS INPUT WEARS (#509). The rule editor labels this field
  // "Kind of work", so a refusal calling it "task type" would put a second word
  // for one column back on the screen, one line under the first.
  it("names the field the way its input is labelled", () => {
    const result = ruleFormSchema.safeParse({
      ...blankRule(),
      measurement_key: "gpt4o_input_tokens",
      task_type: "x".repeat(65),
      subtask_type: "y".repeat(65),
    });

    expect(result.success).toBe(false);
    expect(result.error?.issues.map((issue) => issue.message)).toEqual([
      "Keep the kind of work under 64 characters",
      "Keep the kind of subtask under 64 characters",
    ]);
  });
});
