/**
 * A supplier's cost read off a response (#583): the platform's rows, and the
 * Blueprint each group of them is read through.
 *
 * A row is a response's JSON text with the cost at `["cost","total"]`, read as
 * one representation in one currency. Each group of rows is read through the
 * Blueprint the platform's routes answered for an Event Type that reads that
 * cost and nothing else (`response-cost-reads.json`, one for each target),
 * so the renderers are held to the rows through documents the platform
 * produces (ADR-0016 §5). The one document here the routes cannot produce is
 * a pinned currency UBB does not hold, which they refuse: for that group the
 * same representation's Blueprint is taken and its pinned currency changed,
 * and nothing else.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { expect } from "vitest";

import type { ResolvedIntegrationBlueprint } from "../../src/blueprint.ts";
import { MICROS_PER_MINOR_UNIT } from "../../src/index.ts";
import { FIXTURES } from "./fixtures.ts";

export const CASES = join(FIXTURES, "reported-cost-cases.json");
export const READS = join(FIXTURES, "response-cost-reads.json");

export interface ResponseRow {
  readonly document: string;
  readonly path: string[];
  readonly representation: string;
  readonly currency: string;
  /** For reading, never for comparing: a nineteen-digit answer does not
   * survive `JSON.parse`. The harness compares, reading the file itself. */
  readonly expected: { readonly answer?: number; readonly refused?: string };
}

export function responseRows(): ResponseRow[] {
  return (JSON.parse(readFileSync(CASES, "utf-8")) as { read_off_a_response: ResponseRow[] })
    .read_off_a_response;
}

/** Each representation-and-currency the rows are read as, and the one path
 * they are read at. */
export function rowGroups(): { representation: string; currency: string; path: string[] }[] {
  const seen = new Map<string, { representation: string; currency: string; path: string[] }>();
  for (const row of responseRows()) {
    const key = JSON.stringify([row.representation, row.currency, row.path]);
    if (!seen.has(key)) {
      seen.set(key, { representation: row.representation, currency: row.currency, path: row.path });
    }
  }
  return [...seen.values()];
}

const COST = "provider_response_cost_micros";

function argument(blueprint: ResolvedIntegrationBlueprint, name: string) {
  const record = blueprint.calls.find((call) => call.operation_id.endsWith("record_usage"))!;
  return record.arguments.find((found) => found.name === name);
}

/** The Blueprint `target`'s rows read as `representation` in `currency` at
 * `path` are read through: the platform's, or — for a currency UBB does not
 * hold — the platform's for the same representation with that currency
 * pinned in its place. */
export function aCostReadAt(
  target: "python_sdk" | "shell_http",
  path: readonly string[],
  representation: string,
  currency: string,
): ResolvedIntegrationBlueprint {
  const reads = JSON.parse(readFileSync(READS, "utf-8")) as Record<
    string,
    Record<string, ResolvedIntegrationBlueprint>
  >;
  const resolved = reads[`${representation} ${currency}`]?.[target];
  if (resolved === undefined && currency in MICROS_PER_MINOR_UNIT) {
    throw new Error(`the routes answer ${representation} in ${currency}; the platform's test holds none`);
  }
  const blueprint = resolved ?? structuredClone(reads[`${representation} usd`]![target]!);
  if (resolved === undefined) argument(blueprint, "currency")!.value = currency;
  // The rows and the Blueprints are written by one test, at one path.
  expect(argument(blueprint, `${COST}.source_path`)?.value).toEqual([...path]);
  expect(argument(blueprint, `${COST}.amount_representation`)?.value).toBe(representation);
  expect(argument(blueprint, "currency")?.value).toBe(currency);
  return blueprint;
}
