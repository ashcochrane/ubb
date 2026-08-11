// Mock implementation — same exported signatures as ./api. Mutations are
// simulated coherently within a session via module-level state: minted keys
// appear in the list (sandbox keys land on the sandbox's prefix list, not
// here — mirroring the real routing), rotation deactivates the old key, and
// the test console draws down a mock wallet until the stop verdict fires.

import type { CursorPage } from "@/api/pagination";
import { ApiProblem } from "@/api/problem";
import { mockDelay } from "@/lib/api-provider";

import {
  MOCK_API_KEYS,
  MOCK_COSTED_METRICS,
  MOCK_MARGIN_CUSTOMERS,
  MOCK_METRIC_RATE_MICROS,
  MOCK_SANDBOX,
  MOCK_SANDBOX_TENANT_ID,
  MOCK_LIVE_TENANT_ID,
  MOCK_STARTING_BALANCE_MICROS,
  mockKeyPrefix,
  mockRawKey,
} from "./mock-data";
import type {
  ApiKey,
  ApiKeyCreated,
  ApiKeyRevoked,
  ApiKeyRotated,
  MarginCustomerRow,
  RecordUsageRequest,
  RecordUsageResponse,
  SandboxKeyMinted,
  SandboxStatus,
} from "./types";

let keys: ApiKey[] = MOCK_API_KEYS.map((key) => ({ ...key }));
let sandbox: SandboxStatus = {
  ...MOCK_SANDBOX,
  key_prefixes: [...MOCK_SANDBOX.key_prefixes],
};
let balanceMicros = MOCK_STARTING_BALANCE_MICROS;
let eventCounter = 0;

export async function listApiKeys(_cursor?: string): Promise<CursorPage<ApiKey>> {
  await mockDelay();
  return { data: keys.map((key) => ({ ...key })), has_more: false, next_cursor: null };
}

export async function createApiKey(input: {
  label: string;
  is_test: boolean;
}): Promise<ApiKeyCreated> {
  await mockDelay();
  const prefix = mockKeyPrefix(input.is_test ? "test" : "live");
  const created: ApiKey = {
    id: crypto.randomUUID(),
    key_prefix: prefix,
    label: input.label,
    is_active: true,
    created_at: new Date().toISOString(),
    last_used_at: null,
  };
  if (input.is_test) {
    // Routed to the sandbox sibling — shows up in ITS key list, not this one.
    sandbox = {
      exists: true,
      sandbox_tenant_id: sandbox.sandbox_tenant_id ?? MOCK_SANDBOX_TENANT_ID,
      key_prefixes: [prefix, ...sandbox.key_prefixes],
    };
  } else {
    keys = [created, ...keys];
  }
  return {
    id: created.id,
    key_prefix: prefix,
    label: input.label,
    tenant_id: input.is_test
      ? (sandbox.sandbox_tenant_id ?? MOCK_SANDBOX_TENANT_ID)
      : MOCK_LIVE_TENANT_ID,
    api_key: mockRawKey(prefix),
  };
}

export async function rotateApiKey(keyId: string): Promise<ApiKeyRotated> {
  await mockDelay();
  const old = keys.find((key) => key.id === keyId);
  if (!old) {
    throw new ApiProblem({
      status: 404,
      code: "not_found",
      title: "Not Found",
      detail: "Unknown API key.",
    });
  }
  const prefix = mockKeyPrefix("live");
  const successor: ApiKey = {
    id: crypto.randomUUID(),
    key_prefix: prefix,
    label: `${old.label} (rotated)`,
    is_active: true,
    created_at: new Date().toISOString(),
    last_used_at: null,
  };
  keys = [
    successor,
    ...keys.map((key) => (key.id === keyId ? { ...key, is_active: false } : key)),
  ];
  return {
    id: successor.id,
    key_prefix: prefix,
    label: successor.label,
    revoked_key_id: keyId,
    api_key: mockRawKey(prefix),
  };
}

export async function revokeApiKey(keyId: string): Promise<ApiKeyRevoked> {
  await mockDelay();
  const target = keys.find((key) => key.id === keyId);
  if (!target) {
    throw new ApiProblem({
      status: 404,
      code: "not_found",
      title: "Not Found",
      detail: "Unknown API key.",
    });
  }
  const activeCount = keys.filter((key) => key.is_active).length;
  if (target.is_active && activeCount <= 1) {
    throw new ApiProblem({
      status: 409,
      code: "last_active_key",
      title: "Conflict",
      detail:
        "Revoking this tenant's last active key would lock it out of the API. Rotate the key instead.",
    });
  }
  keys = keys.map((key) => (key.id === keyId ? { ...key, is_active: false } : key));
  return { id: keyId, is_active: false };
}

export async function getSandbox(): Promise<SandboxStatus> {
  await mockDelay();
  return { ...sandbox, key_prefixes: [...sandbox.key_prefixes] };
}

export async function createSandbox(): Promise<SandboxKeyMinted> {
  await mockDelay();
  const prefix = mockKeyPrefix("test");
  const tenantId = sandbox.sandbox_tenant_id ?? MOCK_SANDBOX_TENANT_ID;
  sandbox = {
    exists: true,
    sandbox_tenant_id: tenantId,
    key_prefixes: [prefix, ...sandbox.key_prefixes],
  };
  return { sandbox_tenant_id: tenantId, api_key: mockRawKey(prefix) };
}

export async function listMarginCustomers(): Promise<MarginCustomerRow[]> {
  await mockDelay();
  return MOCK_MARGIN_CUSTOMERS.map((row) => ({ ...row }));
}

export async function sendTestEvent(
  body: RecordUsageRequest,
): Promise<RecordUsageResponse> {
  await mockDelay();
  eventCounter += 1;

  const metrics = body.usage_metrics ?? {};
  const uncosted = Object.keys(metrics).filter(
    (name) => !MOCK_COSTED_METRICS.has(name),
  );
  let metricCost = 0;
  for (const [name, quantity] of Object.entries(metrics)) {
    metricCost += (MOCK_METRIC_RATE_MICROS[name] ?? 0) * quantity;
  }

  const billed = body.billed_cost_micros ?? metricCost;
  const provider = body.provider_cost_micros ?? Math.round(billed * 0.62);

  balanceMicros -= billed;
  const stopped = balanceMicros < 0;

  return {
    event_id: crypto.randomUUID(),
    suspended: false,
    dim2: "",
    dim3: "",
    billed_cost_micros: billed,
    provider_cost_micros: provider,
    new_balance_micros: balanceMicros,
    usage_metrics: body.usage_metrics ?? null,
    uncosted_metrics: uncosted,
    pricing_provenance: {
      engine_version: "mock-1",
      price_source: body.billed_cost_micros != null ? "explicit" : "rate_card",
      sequence: eventCounter,
    },
    stop: stopped,
    stop_reason: stopped ? "customer_floor" : null,
    stop_scope: stopped ? "customer" : null,
    stop_context: stopped
      ? [
          {
            limit: "customer_floor",
            stop_scope: "customer",
            tripped_at: new Date().toISOString(),
            episode_seq: 1,
            task_id: null,
            subtask_id: null,
            arrived_after: false,
          },
        ]
      : null,
    task_id: body.task_id ?? null,
    parent_task_id: null,
  };
}
