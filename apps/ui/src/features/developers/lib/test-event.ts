// Pure helpers for the developers feature: the send-test-event form schema,
// the form-values → RecordUsageRequest builder (currency units → micros), and
// the copy snippets for the API basics / sandbox reset panels.

import { z } from "zod";

import type { RecordUsageRequest } from "../api/types";

export const UUID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

const INT_RE = /^\d+$/;
const MONEY_RE = /^\d+(\.\d{1,6})?$/;

export const testEventFormSchema = z.object({
  customer_id: z
    .string()
    .trim()
    .regex(UUID_RE, "Enter a valid customer UUID"),
  event_type: z.string().trim().max(100, "Max 100 characters"),
  provider: z.string().trim().max(100, "Max 100 characters"),
  product_id: z.string().trim().max(100, "Max 100 characters"),
  provider_cost: z
    .string()
    .trim()
    .refine((value) => value === "" || MONEY_RE.test(value), {
      message: "Amount like 1.25 (up to 6 decimals)",
    }),
  billed_cost: z
    .string()
    .trim()
    .refine((value) => value === "" || MONEY_RE.test(value), {
      message: "Amount like 1.25 (up to 6 decimals)",
    }),
  effective_at: z.string(),
  idempotency_key: z.string().trim().min(1, "Required — regenerate one"),
  metrics: z
    .array(z.object({ key: z.string().trim(), value: z.string().trim() }))
    .superRefine((rows, ctx) => {
      const seen = new Set<string>();
      rows.forEach((row, index) => {
        if (row.key === "" && row.value === "") return;
        if (row.key === "") {
          ctx.addIssue({
            code: "custom",
            path: [index, "key"],
            message: "Metric name required",
          });
        } else if (seen.has(row.key)) {
          ctx.addIssue({
            code: "custom",
            path: [index, "key"],
            message: "Duplicate metric name",
          });
        }
        seen.add(row.key);
        if (!INT_RE.test(row.value)) {
          ctx.addIssue({
            code: "custom",
            path: [index, "value"],
            message: "Whole-number quantity",
          });
        }
      });
    }),
});

export type TestEventFormValues = z.infer<typeof testEventFormSchema>;

export const EMPTY_METRIC_ROW = { key: "", value: "" };

/** Currency units entered as a string → integer micros. Never float math beyond this. */
export function toMicros(value: string): number {
  return Math.round(Number(value) * 1_000_000);
}

/**
 * Build the POST /metering/usage body from validated form values. Empty
 * optionals are omitted entirely; costs convert to integer micros;
 * effective_at converts to a tz-aware UTC ISO string (the API rejects naive
 * timestamps).
 */
export function buildTestEventRequest(
  values: TestEventFormValues,
  requestId: string,
): RecordUsageRequest {
  const metrics: Record<string, number> = {};
  for (const row of values.metrics) {
    if (row.key !== "" && INT_RE.test(row.value)) {
      metrics[row.key] = Number(row.value);
    }
  }
  return {
    customer_id: values.customer_id,
    request_id: requestId,
    idempotency_key: values.idempotency_key,
    ...(values.event_type !== "" && { event_type: values.event_type }),
    ...(values.provider !== "" && { provider: values.provider }),
    ...(values.product_id !== "" && { product_id: values.product_id }),
    ...(values.provider_cost !== "" && {
      provider_cost_micros: toMicros(values.provider_cost),
    }),
    ...(values.billed_cost !== "" && {
      billed_cost_micros: toMicros(values.billed_cost),
    }),
    ...(Object.keys(metrics).length > 0 && { measurements: metrics }),
    ...(values.effective_at !== "" && {
      effective_at: new Date(values.effective_at).toISOString(),
    }),
  };
}

/** "c1a2b3d4-0001-…" → "c1a2b3d4…" for compact pickers/labels. */
export function shortenUuid(id: string): string {
  return `${id.slice(0, 8)}…`;
}

/** The API origin this console talks to (env override or same origin). */
export function apiOrigin(): string {
  return import.meta.env.VITE_API_URL || window.location.origin;
}

/**
 * Copyable sandbox-reset command. The endpoint only accepts a sandbox
 * (ubb_test_) key — the console's live credentials get 403 — so this runs
 * from the user's terminal, never from a console button.
 */
export function sandboxResetCurl(origin: string): string {
  return [
    `curl -X POST ${origin}/api/v1/sandbox/reset \\`,
    `  -H "Authorization: Bearer ubb_test_YOUR_SANDBOX_KEY" \\`,
    `  -H "Content-Type: application/json" \\`,
    `  -d '{"keep_config": true}'`,
  ].join("\n");
}

/** Placeholder auth header for the basics card — never a real key. */
export const AUTH_HEADER_EXAMPLE =
  "Authorization: Bearer ubb_live_xxxxxxxxxxxxxxxxxxxxxxxx";
