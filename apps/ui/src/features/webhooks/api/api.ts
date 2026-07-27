import { webhooksApi } from "@/api/client";
import { requireData } from "@/api/errors";
import type { CursorPage } from "@/lib/use-cursor-list";
import type {
  WebhookConfig,
  WebhookConfigCreate,
  WebhookConfigUpdate,
  WebhookDelivery,
  WebhookSecretRotate,
} from "./types";

export function listConfigs(params?: {
  cursor?: string;
  limit?: number;
}): Promise<CursorPage<WebhookConfig>> {
  return webhooksApi
    .GET("/configs", { params: { query: params } })
    .then((r) => requireData(r, "Failed to load webhook endpoints"));
}

export function createConfig(body: WebhookConfigCreate): Promise<WebhookConfig> {
  return webhooksApi
    .POST("/configs", { body })
    .then((r) => requireData(r, "Failed to create webhook endpoint"));
}

export function updateConfig(
  configId: string,
  body: WebhookConfigUpdate,
): Promise<WebhookConfig> {
  return webhooksApi
    .PATCH("/configs/{config_id}", {
      params: { path: { config_id: configId } },
      body,
    })
    .then((r) => requireData(r, "Failed to update webhook endpoint"));
}

export function deleteConfig(configId: string) {
  return webhooksApi
    .DELETE("/configs/{config_id}", {
      params: { path: { config_id: configId } },
    })
    .then((r) => requireData(r, "Failed to delete webhook endpoint"));
}

export function rotateSecret(
  configId: string,
  body: WebhookSecretRotate,
): Promise<WebhookConfig> {
  return webhooksApi
    .POST("/configs/{config_id}/rotate-secret", {
      params: { path: { config_id: configId } },
      body,
    })
    .then((r) => requireData(r, "Failed to rotate secret"));
}

export function listDeliveries(
  configId: string,
  params?: { cursor?: string; limit?: number },
): Promise<CursorPage<WebhookDelivery>> {
  return webhooksApi
    .GET("/configs/{config_id}/deliveries", {
      params: { path: { config_id: configId }, query: params },
    })
    .then((r) => requireData(r, "Failed to load deliveries"));
}
