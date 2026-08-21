// Type aliases from the generated contract for the /plans surface.

import type { PlatformSchemas } from "@/api/types";

export type Plan = PlatformSchemas["PlanOut"];
export type PlanInput = PlatformSchemas["PlanIn"];
export type PlanUpdateInput = PlatformSchemas["PlanUpdateIn"];

/** Micros -> display money. 1_000_000 micros == 1 major unit. */
export function formatMicros(micros: number): string {
  return `$${(micros / 1_000_000).toFixed(2)}`;
}

// ⚠ NO `formatMarkup` (#369). It rendered the plan's markup percentage column,
// which is deleted. `formatPercentMicros` in `@/lib/format` is the general
// formatter for a percentage held in micros, for whoever needs one next.
