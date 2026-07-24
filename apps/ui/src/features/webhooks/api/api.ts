// Real API calls for /api/v1/webhooks/** (tenant-console auth).
// Floors: list/deliveries = read; create/update/delete/rotate = admin.

import { webhooksApi as client } from "@/api/client";
import { unwrap } from "@/api/problem";

import type {
  CursorParams,
  WebhookConfig,
  WebhookConfigCreate,
  WebhookConfigList,
  WebhookConfigUpdate,
  WebhookDeleteStatus,
  WebhookDeliveryList,
  WebhookSecretRotate,
} from "./types";

export async function listConfigs(params: CursorParams = {}): Promise<WebhookConfigList> {
  return unwrap(await client.GET("/configs", { params: { query: params } }));
}

export async function createConfig(body: WebhookConfigCreate): Promise<WebhookConfig> {
  return unwrap(await client.POST("/configs", { body }));
}

export async function updateConfig(
  configId: string,
  body: WebhookConfigUpdate,
): Promise<WebhookConfig> {
  return unwrap(
    await client.PATCH("/configs/{config_id}", {
      params: { path: { config_id: configId } },
      body,
    }),
  );
}

export async function deleteConfig(configId: string): Promise<WebhookDeleteStatus> {
  return unwrap(
    await client.DELETE("/configs/{config_id}", {
      params: { path: { config_id: configId } },
    }),
  );
}

export async function rotateSecret(
  configId: string,
  body: WebhookSecretRotate,
): Promise<WebhookConfig> {
  return unwrap(
    await client.POST("/configs/{config_id}/rotate-secret", {
      params: { path: { config_id: configId } },
      body,
    }),
  );
}

export async function listDeliveries(
  configId: string,
  params: CursorParams = {},
): Promise<WebhookDeliveryList> {
  return unwrap(
    await client.GET("/configs/{config_id}/deliveries", {
      params: { path: { config_id: configId }, query: params },
    }),
  );
}
