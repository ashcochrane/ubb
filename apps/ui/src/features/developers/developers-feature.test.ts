// Two claims about the Developers feature as a whole (#579), read off its
// source text, because neither is visible in any one rendered page.

import { describe, expect, it } from "vitest";

import { CREDENTIAL_SHAPES, credentialShapeIn, DISPLAY_PREFIX_TAIL } from "./lib/credential-shapes";

const SOURCES: Record<string, string> = import.meta.glob(
  "/src/features/developers/**/*.{ts,tsx}",
  { query: "?raw", import: "default", eager: true },
);

describe("the Developers feature", () => {
  it("is all here to sweep", () => {
    // A glob that matched nothing would let both sweeps below pass over an
    // empty feature.
    expect(Object.keys(SOURCES).length).toBeGreaterThan(25);
    expect(Object.keys(SOURCES)).toContain("/src/features/developers/lib/test-event.ts");
  });

  // ⚠ NO KEY-SHAPED LITERAL, ANYWHERE IN THE FEATURE (#156 §7, §12.1). A
  // placeholder in a key's shape is where a developer pastes a real key, and
  // this feature carried two that contradicted each other. A key's display
  // prefix — what the API returns as `key_prefix` for a list to show — is not
  // a credential and is not this shape.
  it("holds no key-shaped literal", () => {
    const found = Object.entries(SOURCES).flatMap(([path, source]) => {
      const shape = credentialShapeIn(source);
      return shape === null ? [] : [`${path}: ${shape}`];
    });

    expect(found).toEqual([]);
  });

  // The detector's own control: the two placeholders this feature used to
  // carry, and a key's display prefix, which it must let through. Assembled,
  // so that this file is not itself a key-shaped literal.
  it("would have found the placeholders it used to carry", () => {
    const scheme = (mode: string) => ["ubb", mode, ""].join("_");
    const sandboxPlaceholder = `Bearer ${scheme("test")}YOUR_SANDBOX_KEY`;
    const livePlaceholder = `Authorization: Bearer ${scheme("live")}${"x".repeat(24)}`;
    const displayPrefix = `${scheme("live")}${"k".repeat(DISPLAY_PREFIX_TAIL)}`;

    expect(credentialShapeIn(sandboxPlaceholder)).toBe("an API key or a placeholder for one");
    expect(credentialShapeIn(livePlaceholder)).not.toBeNull();
    expect(credentialShapeIn(displayPrefix)).toBeNull();
    expect(Object.keys(CREDENTIAL_SHAPES)).toHaveLength(3);
  });

  // ⚠ THE BUILDER NEVER SENDS A REMEDIATION REQUEST (§11). The page offers
  // the request to copy; only the API module can reach the network, and it
  // has no business with one.
  it("reads a remediation request only where nothing can send it", () => {
    const reaching = Object.entries(SOURCES).filter(([, source]) =>
      /from "@\/api\/client"/.test(source),
    );

    expect(reaching.map(([path]) => path)).toEqual(["/src/features/developers/api/api.ts"]);
    for (const [, source] of reaching) expect(source).not.toMatch(/remediation/i);
  });
});
