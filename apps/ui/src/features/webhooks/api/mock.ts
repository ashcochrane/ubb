// Mock provider — same exported signatures as api.ts, backed by module-level
// state so mutations are coherent within a session. Faithfully mirrors the
// contract's sharp edges: secrets are accepted but NEVER stored or returned;
// duplicate (tenant, url) → 409; https/public-host guard → 422 with the
// server's SSRF detail; rotation sets retiring_secret_expires_at.

import { ApiProblem } from "@/api/problem";
import { mockDelay } from "@/lib/api-provider";
import { WEBHOOK_EVENT_TYPES } from "@/lib/labels";

import { MOCK_WEBHOOK_CONFIGS, MOCK_WEBHOOK_DELIVERIES } from "./mock-data";
import type {
  CursorParams,
  WebhookConfig,
  WebhookConfigCreate,
  WebhookConfigList,
  WebhookConfigUpdate,
  WebhookDeleteStatus,
  WebhookDelivery,
  WebhookDeliveryList,
  WebhookSecretRotate,
} from "./types";

let configs: WebhookConfig[] = MOCK_WEBHOOK_CONFIGS.map((config) => ({ ...config }));
const deliveries = new Map<string, WebhookDelivery[]>(
  Object.entries(MOCK_WEBHOOK_DELIVERIES).map(([id, rows]) => [
    id,
    rows.map((row) => ({ ...row })),
  ]),
);

const KNOWN_EVENT_TYPES = new Set<string>(WEBHOOK_EVENT_TYPES);

const PRIVATE_HOST = /^(localhost$|127\.|10\.|192\.168\.|169\.254\.|0\.|\[::1\]$)/i;

function problem(status: number, code: string, title: string, detail: string): ApiProblem {
  return new ApiProblem({ status, code, title, detail });
}

function validateUrl(url: string, ignoreConfigId?: string): void {
  let parsed: URL;
  try {
    parsed = new URL(url);
  } catch {
    throw problem(422, "validation_error", "Validation error", "url must be a valid URL");
  }
  if (parsed.protocol !== "https:" || PRIVATE_HOST.test(parsed.hostname)) {
    // Mirrors the server's SSRF guard detail — the UI surfaces it verbatim.
    throw problem(
      422,
      "validation_error",
      "Validation error",
      "url must use https and resolve to a public host; private and internal addresses are rejected",
    );
  }
  if (configs.some((config) => config.url === url && config.id !== ignoreConfigId)) {
    throw problem(
      409,
      "conflict",
      "Conflict",
      "A webhook endpoint already exists for this URL — edit it instead.",
    );
  }
}

function validateEventTypes(eventTypes: string[]): void {
  if (eventTypes.length === 0) {
    throw problem(422, "validation_error", "Validation error", "event_types must not be empty");
  }
  const unknown = eventTypes.filter(
    (eventType) => eventType !== "*" && !KNOWN_EVENT_TYPES.has(eventType),
  );
  if (unknown.length > 0) {
    throw problem(
      422,
      "validation_error",
      "Validation error",
      `Unknown event types: ${unknown.join(", ")}`,
    );
  }
}

function validateSecret(secret: string): void {
  if (secret.length < 32 || secret.length > 255) {
    throw problem(
      422,
      "validation_error",
      "Validation error",
      "secret must be between 32 and 255 characters",
    );
  }
}

function requireConfig(configId: string): WebhookConfig {
  const config = configs.find((candidate) => candidate.id === configId);
  if (!config) {
    throw problem(404, "not_found", "Not found", "That webhook endpoint doesn't exist.");
  }
  return config;
}

export async function listConfigs(_params: CursorParams = {}): Promise<WebhookConfigList> {
  await mockDelay();
  return {
    data: configs.map((config) => ({ ...config })),
    has_more: false,
    next_cursor: null,
  };
}

export async function createConfig(body: WebhookConfigCreate): Promise<WebhookConfig> {
  await mockDelay();
  validateUrl(body.url);
  validateSecret(body.secret);
  validateEventTypes(body.event_types);
  const config: WebhookConfig = {
    id: crypto.randomUUID(),
    url: body.url,
    event_types: [...body.event_types],
    is_active: body.is_active,
    retiring_secret_expires_at: null,
    created_at: new Date().toISOString(),
  };
  configs = [config, ...configs];
  deliveries.set(config.id, []);
  // Note: body.secret is deliberately discarded — write-only, never readable.
  return { ...config };
}

export async function updateConfig(
  configId: string,
  body: WebhookConfigUpdate,
): Promise<WebhookConfig> {
  await mockDelay();
  const config = requireConfig(configId);
  if (body.url !== undefined && body.url !== null) {
    validateUrl(body.url, configId);
    config.url = body.url;
  }
  if (body.event_types !== undefined && body.event_types !== null) {
    validateEventTypes(body.event_types);
    config.event_types = [...body.event_types];
  }
  if (body.is_active !== undefined && body.is_active !== null) {
    config.is_active = body.is_active;
  }
  return { ...config };
}

export async function deleteConfig(configId: string): Promise<WebhookDeleteStatus> {
  await mockDelay();
  configs = configs.filter((config) => config.id !== configId);
  deliveries.delete(configId);
  return { status: "deleted" };
}

export async function rotateSecret(
  configId: string,
  body: WebhookSecretRotate,
): Promise<WebhookConfig> {
  await mockDelay();
  const config = requireConfig(configId);
  validateSecret(body.new_secret);
  if (body.overlap_hours < 1 || body.overlap_hours > 168) {
    throw problem(
      422,
      "validation_error",
      "Validation error",
      "overlap_hours must be between 1 and 168",
    );
  }
  config.retiring_secret_expires_at = new Date(
    Date.now() + body.overlap_hours * 3_600_000,
  ).toISOString();
  return { ...config };
}

export async function listDeliveries(
  configId: string,
  _params: CursorParams = {},
): Promise<WebhookDeliveryList> {
  await mockDelay();
  requireConfig(configId);
  const rows = deliveries.get(configId) ?? [];
  return {
    data: rows.map((row) => ({ ...row })),
    has_more: false,
    next_cursor: null,
  };
}
