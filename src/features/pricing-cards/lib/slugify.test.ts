import { describe, expect, it } from "vitest";
import { slugify, slugifyWithSuffix } from "./slugify";

describe("slugify", () => {
  it("converts spaces and special chars to underscores", () => {
    expect(slugify("Gemini 2.0 Flash")).toBe("gemini_2_0_flash");
  });

  it("lowercases the input", () => {
    expect(slugify("GPT-4o")).toBe("gpt_4o");
  });

  it("strips leading and trailing underscores", () => {
    expect(slugify("  hello world  ")).toBe("hello_world");
  });

  it("truncates to 40 characters", () => {
    const long = "a".repeat(50);
    expect(slugify(long).length).toBe(40);
  });

  it("handles empty string", () => {
    expect(slugify("")).toBe("");
  });
});

describe("slugifyWithSuffix", () => {
  it("appends a 3-digit suffix", () => {
    const result = slugifyWithSuffix("Gemini Flash");
    expect(result).toMatch(/^gemini_flash_\d{3}$/);
  });

  it("base is truncated to leave room for suffix", () => {
    const long = "a".repeat(50);
    const result = slugifyWithSuffix(long);
    expect(result.length).toBeLessThanOrEqual(40);
  });
});
