// The form for the workspace's default ceilings for work with no declared
// kind (#453): its schema, and the conversions between what a person types
// and the PATCH the tenant configuration route takes. Amounts stay strings in
// form state and become integer micros exactly once, at submit — the same
// discipline as `declaration-form`.

import { z } from "zod";

import type { TenantConfig, UndeclaredWorkCeilingRung } from "@/hooks/use-tenant-config";

import type { UndeclaredWorkCeilings } from "../api/types";
import { amountAboveZeroOrEmpty, amountToMicros, microsToAmount } from "./declaration-form";

const amountOrEmpty = amountAboveZeroOrEmpty("An amount above zero, or leave it empty for no ceiling.");

export const undeclaredWorkSchema = z.object({
  wholeWork: amountOrEmpty,
  containedWork: amountOrEmpty,
});

export type UndeclaredWorkValues = z.infer<typeof undeclaredWorkSchema>;

/** Which form field carries which rung — one table, read by both directions below. */
const FIELD_OF: Record<UndeclaredWorkCeilingRung, keyof UndeclaredWorkValues> = {
  default_task_cogs_ceiling_micros: "wholeWork",
  default_subtask_cogs_ceiling_micros: "containedWork",
};

const RUNGS = Object.entries(FIELD_OF) as [UndeclaredWorkCeilingRung, keyof UndeclaredWorkValues][];

/** What the form opens holding: the two rungs as the workspace holds them. */
export function undeclaredWorkDefaults(config: TenantConfig): UndeclaredWorkValues {
  return Object.fromEntries(
    RUNGS.map(([rung, field]) => [field, microsToAmount(config[rung])]),
  ) as UndeclaredWorkValues;
}

/**
 * The PATCH the form states: only the rungs that changed, a cleared rung as
 * an EXPLICIT null (the route reads an omitted key as "leave it alone").
 */
export function undeclaredWorkPatch(
  config: TenantConfig,
  values: UndeclaredWorkValues,
): UndeclaredWorkCeilings {
  const patch: UndeclaredWorkCeilings = {};
  for (const [rung, field] of RUNGS) {
    const stated = amountToMicros(values[field]);
    if (stated !== (config[rung] ?? null)) patch[rung] = stated;
  }
  return patch;
}
