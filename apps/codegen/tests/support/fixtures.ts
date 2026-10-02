/**
 * The committed Blueprints the renderer's tests render.
 *
 * Every one is what the platform's own route answered, held equal to it by
 * `ubb-platform/api/v1/tests/test_the_renderers_fixtures_are_what_the_platform_answers.py`.
 * Nothing here is a Blueprint somebody wrote down: a test that needs one the
 * routes cannot produce derives it from one of these, in the test, and says
 * what it changed.
 */
import { readdirSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import type {
  BlueprintArgument,
  ResolvedIntegrationBlueprint,
} from "../../src/blueprint.ts";

export const PACKAGE_ROOT = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
export const REPO_ROOT = join(PACKAGE_ROOT, "..", "..");
export const FIXTURES = join(PACKAGE_ROOT, "fixtures");
const BLUEPRINTS = join(FIXTURES, "blueprints");

export const FIXTURE_NAMES: readonly string[] = readdirSync(BLUEPRINTS)
  .filter((file) => file.endsWith(".json"))
  .map((file) => file.slice(0, -".json".length))
  .sort();

export function fixtureText(name: string): string {
  return readFileSync(join(BLUEPRINTS, `${name}.json`), "utf-8");
}

/** A fresh copy each time, so a test that changes one changes only its own. */
export function fixture(name: string): ResolvedIntegrationBlueprint {
  return JSON.parse(fixtureText(name)) as ResolvedIntegrationBlueprint;
}

export function everyArgument(
  blueprint: ResolvedIntegrationBlueprint,
): BlueprintArgument[] {
  return blueprint.calls.flatMap((call) => call.arguments);
}
