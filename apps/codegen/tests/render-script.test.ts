/**
 * `scripts/render.ts`: `render` called from another process (#582).
 *
 * The execution suite at the git root (`tests/code_builder_execution`) asks
 * the platform for a Blueprint and needs the files this package renders from
 * it, in a Python process that cannot import TypeScript. The renderer itself
 * reads no stream and no environment (its lint forbids both under `src/`), so
 * the script that hands it a Blueprint from standard input lives outside it.
 *
 * What makes the script safe to stand between the two is that it adds
 * nothing: for every committed Blueprint, what it prints is exactly what
 * `render` returns in this process, file for file and in order.
 */
import { spawnSync } from "node:child_process";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import { render } from "../src/index.ts";
import { fixture, FIXTURE_NAMES, fixtureText, PACKAGE_ROOT } from "./support/fixtures.ts";

const SCRIPT = join(PACKAGE_ROOT, "scripts", "render.ts");

/** The script, run the way the execution suite runs it. */
function rendered(input: string) {
  return spawnSync(process.execPath, ["--experimental-strip-types", SCRIPT], {
    input,
    encoding: "utf-8",
  });
}

describe("the render script", () => {
  it("has Blueprints of both targets and every readiness to compare with", () => {
    const blueprints = FIXTURE_NAMES.map((name) => fixture(name));

    expect(new Set(blueprints.map((blueprint) => blueprint.target))).toEqual(
      new Set(["python_sdk", "shell_http"]),
    );
    expect(new Set(blueprints.map((blueprint) => blueprint.readiness))).toEqual(
      new Set(["complete", "scaffold", "blocked"]),
    );
  });

  it.each(FIXTURE_NAMES)("prints exactly what render returns for %s", (name) => {
    const ran = rendered(fixtureText(name));

    expect(ran.status, ran.stderr).toBe(0);
    expect(JSON.parse(ran.stdout)).toEqual(render(fixture(name)));
  });

  it("fails, and prints nothing, for a document render refuses", () => {
    const refused = { ...fixture("shell-calculated-cost"), schema_version: 999 };
    let reason = "";
    try {
      render(refused);
    } catch (refusal) {
      reason = (refusal as Error).message;
    }
    const ran = rendered(JSON.stringify(refused));

    expect(reason).toContain("999");
    expect(ran.status).not.toBe(0);
    expect(ran.stdout).toBe("");
    // Render's own refusal, by its own words, and not some other failure.
    expect(ran.stderr).toContain(`BlueprintNotRenderable: ${reason}`);
  });
});
