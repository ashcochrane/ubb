/**
 * The renderer catalogue: closed, versioned, and in step with the registry
 * (#577, owner ruling of 2026-09-25 item 9).
 *
 * The catalogue's symbols are pinned HERE and are deliberately not registry
 * concepts. What it says ABOUT a registry concept — a sentence per diagnostic
 * code, a sentence per verdict — is held to the registry's own value sets, so
 * a code the registry gains cannot arrive as a diagnostic with nothing said
 * about it.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import * as catalogue from "../src/catalogue.ts";
import {
  AMOUNT_REPRESENTATION,
  CATALOGUE_VERSION,
  COMMENTS,
  ENVIRONMENT,
  MESSAGES,
  MICROS_PER_MINOR_UNIT,
  PRICING_MODE_COMMENTS,
  PYTHON,
  READINESS_COMMENTS,
  REMEDIATION,
  RESPONSE_REPRESENTATION,
  SHELL,
} from "../src/index.ts";
import { FIXTURE_NAMES, fixture, FIXTURES, PACKAGE_ROOT, REPO_ROOT } from "./support/fixtures.ts";
import { registry } from "./support/python.ts";

const REGISTRY = registry(
  "diagnostic_code",
  "integration_readiness",
  "amount_representation",
  "pricing_mode",
  "response_shape_representation",
  "stop_behavior",
);

describe("the catalogue's symbols", () => {
  it("are the ones ruled, spelled as ruled", () => {
    expect(ENVIRONMENT).toEqual({ apiKey: "UBB_API_KEY", baseUrl: "UBB_BASE_URL" });
    expect(SHELL).toEqual({
      stopMetadata: "stop_requested",
      stopExitStatusName: "UBB_EXIT_STOP_REQUESTED",
      stopExitStatus: 20,
    });
  });

  it("hold no host: where the API is, is not the renderer's to say", () => {
    // Owner ruling on PR #597: the renderer keeps no second copy of the
    // platform's service location. Nothing in the catalogue is an address.
    expect(JSON.stringify(catalogue)).not.toMatch(/https?:\/\/|localhost/);
  });

  it("name the credential the server withholds under the same variable", () => {
    for (const name of FIXTURE_NAMES) {
      const variables = fixture(name)
        .calls.flatMap((call) => call.arguments)
        .filter((argument) => argument.binding_class === "secret_reference")
        .map((argument) => argument.environment_variable);

      expect(variables.length, name).toBeGreaterThan(0);
      expect(new Set(variables), name).toEqual(new Set([ENVIRONMENT.apiKey]));
    }
  });

  it("name the SDK major this tree ships, and the one a Blueprint names", () => {
    expect(Number(REGISTRY.sdk_version.split(".")[0])).toBe(PYTHON.sdkMajorVersion);
    expect(fixture("calculated-cost").sdk_major_version).toBe(PYTHON.sdkMajorVersion);
  });

  it("spell the two stop behaviours as the registry does", () => {
    expect([PYTHON.stopBehaviorRaise, PYTHON.stopBehaviorReturn].sort()).toEqual(
      REGISTRY.values.stop_behavior,
    );
  });
});

describe("what the catalogue says about a registry concept", () => {
  it("has remediation for every diagnostic code, and for no other", () => {
    expect(REGISTRY.values.diagnostic_code!.length).toBeGreaterThan(10);
    expect(Object.keys(REMEDIATION).sort()).toEqual(REGISTRY.values.diagnostic_code);
  });

  it("agrees with the committed contract about which codes there are", () => {
    const known = JSON.parse(
      readFileSync(join(REPO_ROOT, "openapi", "known-values.json"), "utf-8"),
    ) as { concepts: Record<string, { values: string[] }> };

    expect(Object.keys(REMEDIATION).sort()).toEqual(
      [...known.concepts.diagnostic_code!.values].sort(),
    );
  });

  it("says what every verdict means, and no other", () => {
    expect(Object.keys(READINESS_COMMENTS).sort()).toEqual(
      REGISTRY.values.integration_readiness,
    );
  });

  it("converts every amount representation, and no other", () => {
    expect(Object.values(AMOUNT_REPRESENTATION).sort()).toEqual(
      REGISTRY.values.amount_representation,
    );
  });

  it("says what delivering means under every pricing mode, and no other", () => {
    expect(Object.keys(PRICING_MODE_COMMENTS).sort()).toEqual(REGISTRY.values.pricing_mode);
  });

  it("reads every response shape representation, and no other", () => {
    expect(Object.values(RESPONSE_REPRESENTATION).sort()).toEqual(
      REGISTRY.values.response_shape_representation,
    );
  });

  it("holds the platform's own currency table", () => {
    const platform = JSON.parse(
      readFileSync(join(FIXTURES, "micros-per-minor-unit.json"), "utf-8"),
    ) as Record<string, number>;

    expect(Object.keys(platform).length).toBeGreaterThan(5);
    expect(MICROS_PER_MINOR_UNIT).toEqual(platform);
  });
});

describe("the catalogue's text", () => {
  const groups = { COMMENTS, READINESS_COMMENTS, REMEDIATION, PRICING_MODE_COMMENTS };
  const lines = Object.values(groups).flatMap((group) => Object.values(group).flat());

  it("is lines a comment can hold: short, plain, and trimmed", () => {
    expect(lines.length).toBeGreaterThan(80);
    for (const line of lines) {
      expect(line.length, line).toBeLessThanOrEqual(76);
      expect(line, line).toMatch(/^[\x20-\x7e]+$/);
      expect(line.trimEnd(), line).toBe(line);
    }
  });

  it("is messages a Python string and an f-string can hold as they stand", () => {
    for (const message of Object.values(MESSAGES)) {
      expect(message, message).toMatch(/^[\x20-\x7e]+$/);
      expect(message, message).not.toMatch(/["{}\\]/);
    }
  });

  it("names its own version in the line that says what generated a file", () => {
    expect(COMMENTS.generated[0]).toContain(`renderer catalogue version ${CATALOGUE_VERSION}`);
  });

  it("is pinned, whole, to its version", async () => {
    // Every exported member, as it stands. A member added, removed or
    // reworded fails here until the file is re-taken. Re-taking it is one
    // command, so what this buys is not a refusal: it is that a change under
    // an unchanged number shows up as a diff of a file named for the version,
    // and a new number as a new file.
    const whole = Object.fromEntries(
      Object.entries(catalogue).sort(([left], [right]) => left.localeCompare(right)),
    );

    await expect(`${JSON.stringify(whole, null, 2)}\n`).toMatchFileSnapshot(
      join(PACKAGE_ROOT, "tests", "__snapshots__", `catalogue.v${CATALOGUE_VERSION}.json`),
    );
  });
});
