// Every webhook operation is fully typed in the generated schema — no
// untyped (additionalProperties: true) responses on this surface.
//
// Contract fact worth restating: WebhookConfigResponse has NO secret field.
// Secrets are caller-supplied (32–255 chars), write-only, and never returned
// by any endpoint — there is no reveal, only rotation with an overlap window.

import type { WebhookSchemas } from "@/api/types";

export type WebhookConfig = WebhookSchemas["WebhookConfigResponse"];
export type WebhookConfigList = WebhookSchemas["WebhookConfigListResponse"];
export type WebhookConfigCreate = WebhookSchemas["WebhookConfigCreateRequest"];
export type WebhookConfigUpdate = WebhookSchemas["WebhookConfigUpdateRequest"];
export type WebhookSecretRotate = WebhookSchemas["WebhookSecretRotateRequest"];
export type WebhookDelivery = WebhookSchemas["WebhookDeliveryResponse"];
export type WebhookDeliveryList = WebhookSchemas["WebhookDeliveryListResponse"];
export type WebhookDeleteStatus = WebhookSchemas["StatusResponse"];

export interface CursorParams {
  cursor?: string;
  limit?: number;
}
