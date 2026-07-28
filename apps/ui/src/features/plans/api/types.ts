// Type aliases from the generated contract for the /plans surface.

import type { PlatformSchemas } from "@/api/types";

export type Plan = PlatformSchemas["PlanOut"];
export type PlanInput = PlatformSchemas["PlanIn"];
export type PlanUpdateInput = PlatformSchemas["PlanUpdateIn"];

/** Micros -> display money. 1_000_000 micros == 1 major unit. */
export function formatMicros(micros: number): string {
  return `$${(micros / 1_000_000).toFixed(2)}`;
}

/** Markup micros -> percent. 1_000_000 micros == 1%. */
export function formatMarkup(micros: number): string {
  const pct = micros / 1_000_000;
  return `${Number.isInteger(pct) ? pct : pct.toFixed(2)}%`;
}
