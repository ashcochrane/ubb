import type { WebhookSchemas } from "@/api/types";

export type WebhookConfig = WebhookSchemas["WebhookConfigResponse"];
export type WebhookDelivery = WebhookSchemas["WebhookDeliveryResponse"];
export type WebhookConfigCreate = WebhookSchemas["WebhookConfigCreateRequest"];
export type WebhookConfigUpdate = WebhookSchemas["WebhookConfigUpdateRequest"];
export type WebhookSecretRotate = WebhookSchemas["WebhookSecretRotateRequest"];
