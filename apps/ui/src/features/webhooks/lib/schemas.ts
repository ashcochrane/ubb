// Client-side validation mirroring the contract's constraints:
// - url: https only, ≤500 chars (the server additionally rejects private /
//   internal hosts — that SSRF 422 detail is surfaced verbatim, not predicted).
// - secret / new_secret: 32–255 chars, caller-supplied, write-only.
// - event_types: minItems 1 unless subscribing to all events ("*").
// - overlap_hours: integer 1–168 (1 hour – 7 days), default 24.

import { z } from "zod";

import { WEBHOOK_EVENT_TYPE_VALUES, type WebhookEventType } from "@/lib/vocabulary";

/** What a subscription's `event_types` may hold: a published name, or the wildcard. */
export type EventSelector = WebhookEventType | "*";

export const endpointUrlSchema = z
  .string()
  .trim()
  .min(1, "Endpoint URL is required")
  .max(500, "Keep the URL under 500 characters")
  .refine(
    (value) => {
      try {
        return new URL(value).protocol === "https:";
      } catch {
        return false;
      }
    },
    { message: "Must be a valid https:// URL — plain http isn't accepted" },
  );

export const secretSchema = z
  .string()
  .min(32, "Use at least 32 characters — Generate makes a strong one")
  .max(255, "Keep the secret under 256 characters");

// The names are the registry's closed set, held by reference (#464): the
// contract's `items` enum admits exactly these, so a form value outside them
// is refused here rather than by the API's 422.
const eventSelection = {
  allEvents: z.boolean(),
  eventTypes: z.array(z.enum(WEBHOOK_EVENT_TYPE_VALUES)),
};

const requireSelection = {
  path: ["eventTypes"],
  message: "Pick at least one event type, or subscribe to all events",
};

export const createEndpointSchema = z
  .object({
    url: endpointUrlSchema,
    secret: secretSchema,
    ...eventSelection,
    isActive: z.boolean(),
  })
  .refine((values) => values.allEvents || values.eventTypes.length > 0, requireSelection);

export type CreateEndpointValues = z.infer<typeof createEndpointSchema>;

export const editEndpointSchema = z
  .object({
    url: endpointUrlSchema,
    ...eventSelection,
  })
  .refine((values) => values.allEvents || values.eventTypes.length > 0, requireSelection);

export type EditEndpointValues = z.infer<typeof editEndpointSchema>;

export const rotateSecretSchema = z.object({
  newSecret: secretSchema,
  overlapHours: z
    .number({ message: "Enter the overlap window in hours" })
    .int("Whole hours only")
    .min(1, "At least 1 hour")
    .max(168, "At most 168 hours (7 days)"),
});

export type RotateSecretValues = z.infer<typeof rotateSecretSchema>;

/** The event_types selector list the API expects. */
export function toEventTypesPayload(values: {
  allEvents: boolean;
  eventTypes: WebhookEventType[];
}): EventSelector[] {
  return values.allEvents ? ["*"] : [...values.eventTypes];
}
