// Pure helpers + zod schemas for the settings feature.

import { z } from "zod";

import { humanize } from "@/lib/labels";

import type {
  MarginThreshold,
  MarginThresholdInput,
  TenantConfig,
  TenantConfigPatch,
} from "../api/types";

// ---------------------------------------------------------------------------
// Currencies — the supported 2-decimal set (PATCH config default_currency).

export const SUPPORTED_CURRENCIES: { code: string; name: string }[] = [
  { code: "usd", name: "US Dollar" },
  { code: "eur", name: "Euro" },
  { code: "gbp", name: "British Pound" },
  { code: "aud", name: "Australian Dollar" },
  { code: "cad", name: "Canadian Dollar" },
  { code: "chf", name: "Swiss Franc" },
  { code: "nzd", name: "New Zealand Dollar" },
  { code: "sgd", name: "Singapore Dollar" },
  { code: "hkd", name: "Hong Kong Dollar" },
  { code: "sek", name: "Swedish Krona" },
  { code: "nok", name: "Norwegian Krone" },
  { code: "dkk", name: "Danish Krone" },
  { code: "pln", name: "Polish Zloty" },
  { code: "czk", name: "Czech Koruna" },
  { code: "mxn", name: "Mexican Peso" },
  { code: "brl", name: "Brazilian Real" },
  { code: "inr", name: "Indian Rupee" },
  { code: "zar", name: "South African Rand" },
];

// ---------------------------------------------------------------------------
// Money input conversion — inputs are entered in currency units, the API
// speaks integer micros.

export function inputToMicros(value: string): number {
  return Math.round(Number(value) * 1_000_000);
}

export function microsToInput(micros: number | null | undefined): string {
  if (micros === null || micros === undefined) return "";
  return (micros / 1_000_000).toString();
}

// ---------------------------------------------------------------------------
// Spend-control form. All fields are entered as currency-unit strings; empty
// means "no value" for the clearable fields.
//
// Sign convention — the form value IS the wire value, for both floors:
// `min_balance_micros` is the allowed overdraft MAGNITUDE (≥ 0; the hard stop
// line sits at minus this value), and `soft_min_balance_micros` is the same
// orientation for the wind-down line (line at minus the value; a NEGATIVE
// value places the wind-down line above zero, i.e. wind-down starts while the
// balance is still positive). The server rule is soft value ≤ hard value —
// i.e. the wind-down line may never sit below the hard stop line.

const numericOrEmpty = (message: string) =>
  z
    .string()
    .trim()
    .refine((v) => v === "" || !Number.isNaN(Number(v)), { message });

export const spendControlSchema = z
  .object({
    allowedOverdraft: z
      .string()
      .trim()
      .refine((v) => v !== "" && !Number.isNaN(Number(v)), {
        message: "Enter an amount (0 for none).",
      })
      .refine((v) => v === "" || Number(v) >= 0, {
        message: "The allowed overdraft can't be negative.",
      }),
    softFloor: numericOrEmpty("Enter an amount, or leave empty for no wind-down floor."),
    taskLimit: z
      .string()
      .trim()
      .refine((v) => v === "" || (!Number.isNaN(Number(v)) && Number(v) > 0), {
        message: "Must be more than zero, or empty for no default limit.",
      }),
    taskFloorSnapshot: numericOrEmpty("Enter an amount, or leave empty."),
  })
  .superRefine((values, ctx) => {
    if (values.softFloor === "") return;
    const soft = Number(values.softFloor);
    const overdraft = Number(values.allowedOverdraft || "0");
    if (Number.isNaN(soft) || Number.isNaN(overdraft)) return;
    // Mirrors the server rule: soft value ≤ hard value (a larger value would
    // put the wind-down line below the hard stop line).
    if (soft > overdraft) {
      ctx.addIssue({
        code: "custom",
        path: ["softFloor"],
        message: `Can't be more than the allowed overdraft (${overdraft}) — that would put the wind-down line below the hard stop point.`,
      });
    }
  });

export type SpendControlValues = z.infer<typeof spendControlSchema>;

export function configToSpendValues(config: TenantConfig): SpendControlValues {
  return {
    allowedOverdraft: microsToInput(config.min_balance_micros ?? 0),
    softFloor: microsToInput(config.soft_min_balance_micros),
    taskLimit: microsToInput(config.default_task_provider_cost_limit_micros),
    taskFloorSnapshot: microsToInput(config.default_task_floor_snapshot_micros),
  };
}

/**
 * Build the PATCH body for the spend-control form: only changed fields are
 * present; a field cleared to empty becomes an EXPLICIT null (clears it
 * server-side) while unchanged fields are omitted entirely (preserved).
 */
export function buildSpendPatch(
  config: TenantConfig,
  values: SpendControlValues,
): TenantConfigPatch {
  const patch: TenantConfigPatch = {};

  const overdraft = inputToMicros(values.allowedOverdraft);
  if (overdraft !== (config.min_balance_micros ?? 0)) {
    patch.min_balance_micros = overdraft;
  }

  const soft = values.softFloor === "" ? null : inputToMicros(values.softFloor);
  if (soft !== (config.soft_min_balance_micros ?? null)) {
    patch.soft_min_balance_micros = soft;
  }

  const taskLimit = values.taskLimit === "" ? null : inputToMicros(values.taskLimit);
  if (taskLimit !== (config.default_task_provider_cost_limit_micros ?? null)) {
    patch.default_task_provider_cost_limit_micros = taskLimit;
  }

  const floorSnapshot =
    values.taskFloorSnapshot === "" ? null : inputToMicros(values.taskFloorSnapshot);
  if (floorSnapshot !== (config.default_task_floor_snapshot_micros ?? null)) {
    patch.default_task_floor_snapshot_micros = floorSnapshot;
  }

  return patch;
}

// ---------------------------------------------------------------------------
// Margin-alert form (GET/PUT /margin/threshold). Percent fields are plain
// numbers 0–100 scale (NOT micros); periods is a whole number ≥ 1. Only the
// server's own constraints are mirrored — nothing extra.

export const marginAlertSchema = z.object({
  minMarginPct: z
    .string()
    .trim()
    .refine((v) => v !== "" && !Number.isNaN(Number(v)), {
      message: "Enter a percentage (0 flags only money-losing customers).",
    }),
  consecutivePeriods: z
    .string()
    .trim()
    .refine(
      (v) => v !== "" && Number.isInteger(Number(v)) && Number(v) >= 1,
      { message: "Enter a whole number of periods, 1 or more." },
    ),
  providerCostSpikePct: z
    .string()
    .trim()
    .refine((v) => v !== "" && !Number.isNaN(Number(v)), {
      message: "Enter a percentage.",
    }),
});

export type MarginAlertValues = z.infer<typeof marginAlertSchema>;

/** Prefill with full precision — String(n), never toFixed, so an untouched save round-trips identically. */
export function thresholdToValues(threshold: MarginThreshold): MarginAlertValues {
  return {
    minMarginPct: String(threshold.min_margin_pct),
    consecutivePeriods: String(threshold.consecutive_periods),
    providerCostSpikePct: String(threshold.provider_cost_spike_pct),
  };
}

export function valuesToThreshold(values: MarginAlertValues): MarginThresholdInput {
  return {
    min_margin_pct: Number(values.minMarginPct),
    consecutive_periods: Number(values.consecutivePeriods),
    provider_cost_spike_pct: Number(values.providerCostSpikePct),
  };
}

// ---------------------------------------------------------------------------
// Audit helpers.

const AUDIT_NOUN_LABELS: Record<string, string> = {
  api_key: "API key",
};

/** "config.updated" → "Config updated"; "api_key.rotated" → "API key rotated". */
export function auditActionLabel(action: string): string {
  const dot = action.indexOf(".");
  if (dot === -1) return humanize(action);
  const noun = action.slice(0, dot);
  const verb = action.slice(dot + 1);
  const nounLabel = AUDIT_NOUN_LABELS[noun] ?? humanize(noun);
  return `${nounLabel} ${verb.replace(/[._-]+/g, " ").toLowerCase()}`.trim();
}

/** "rc-openai-price-v4" → "rc-opena…" (title/copy carry the full value). */
export function truncateId(id: string, length = 8): string {
  if (id.length <= length) return id;
  return `${id.slice(0, length)}…`;
}

// ---------------------------------------------------------------------------
// URL search schemas (zod .catch so bad URLs never crash the route).

export const auditSearchSchema = z
  .object({
    action: z.string().optional(),
    resource_type: z.string().optional(),
    resource_id: z.string().optional(),
  })
  .catch({});

export type AuditSearch = z.infer<typeof auditSearchSchema>;

export const workspaceSearchSchema = z
  .object({
    /** Stripe Connect OAuth return marker: "true" | "false" when present. */
    connected: z.string().optional(),
  })
  .catch({});

export type WorkspaceSearch = z.infer<typeof workspaceSearchSchema>;
