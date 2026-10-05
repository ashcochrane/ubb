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
    expect(Object.keys(SOURCES)).toContain("/src/features/developers/lib/sandbox-reset.ts");
    expect(Object.keys(SOURCES)).toContain("/src/features/developers/components/verify-stage.tsx");
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

  // ⚠ THE BUILDER NEVER SENDS A REMEDIATION REQUEST (§11), and no request it
  // is handed. Three facts about the feature's source make that structural:
  // the API module is the only one holding a client; every request it makes
  // goes to a route written in it, never one passed in; and nothing in the
  // feature sends anything round the clients. (The shared hooks it uses make
  // their own fixed reads, and are not this feature's to send through.)
  it("can send nothing but the requests it writes out", () => {
    const holding = Object.entries(SOURCES).filter(([, source]) =>
      /from "@\/api\/client"/.test(source),
    );
    expect(holding.map(([path]) => path)).toEqual(["/src/features/developers/api/api.ts"]);

    const [, api] = holding[0] ?? ["", ""];
    const calls = [...api.matchAll(/Api\.(GET|POST|PUT|PATCH|DELETE)\(\s*([^,)]*)/g)];
    expect(calls.length).toBeGreaterThan(5);
    for (const [call, , route] of calls) {
      expect(route, call).toMatch(/^"\/[^"]*"$/);
    }

    for (const [path, source] of Object.entries(SOURCES)) {
      if (path.includes(".test.")) continue;
      expect(source, path).not.toMatch(/\bfetch\(|XMLHttpRequest|sendBeacon|new WebSocket/);
    }
  });
});
