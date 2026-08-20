// Mock implementation — same exported signatures as ./api. Mutations are
// simulated coherently within a session via module-level state: minted keys
// appear in the list (sandbox keys land on the sandbox's prefix list, not
// here — mirroring the real routing), rotation deactivates the old key, and
// the test console draws down a mock wallet until the stop verdict fires.

import type { CursorPage } from "@/api/pagination";
import { ApiProblem } from "@/api/problem";
import { mockDelay } from "@/lib/api-provider";
import { knownCost, unknownCost } from "@/lib/economic-scenarios";

import {
  MOCK_API_KEYS,
  MOCK_COSTED_MEASUREMENTS,
  MOCK_MARGIN_CUSTOMERS,
  MOCK_MEASUREMENT_RATE_MICROS,
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

  const measurements = body.measurements ?? {};
  const uncosted = Object.keys(measurements).filter(
    (name) => !MOCK_COSTED_MEASUREMENTS.has(name),
  );
  let measuredCost = 0;
  for (const [name, quantity] of Object.entries(measurements)) {
    measuredCost += (MOCK_MEASUREMENT_RATE_MICROS[name] ?? 0) * quantity;
  }

  // WHAT THE CUSTOMER IS CHARGED IS DERIVED HERE AND NOT SENT (#365). The
  // request used to be able to carry the price and this line used to prefer it;
  // the API deleted that field, so the only source left is the same one the
  // real engine uses — the tenant's configured rules over the measurements.
  const billed = measuredCost;
  // A measurement no cost card covers leaves the whole supplier cost UNRESOLVED
  // — not a smaller number (#320). A caller who states the cost outright is
  // answered `known` whatever the measurements say, which is the backend's own
  // order: the supplied figure is the answer and no declaration is consulted.
  const resolved = body.provider_cost_micros != null || uncosted.length === 0;
  // COMPOSED, NEVER ASSEMBLED FIELD BY FIELD (#330). The amount, the status and
  // the missing input are one fact in three properties, and the posting's own
  // check constraint admits only three combinations of them; taking them from
  // the canonical scenarios is what stops this mock inventing a fourth. The
  // reason is `cost_rate_missing` because that is precisely what happened above:
  // a measurement reached the rate lookup and nothing there priced it.
  const cost = resolved
    ? knownCost(body.provider_cost_micros ?? Math.round(billed * 0.62))
    : unknownCost("cost_rate_missing");

  balanceMicros -= billed;
  const stopped = balanceMicros < 0;

  return {
    event_id: crypto.randomUUID(),
    suspended: false,
    // The posting's grouping values under the tenant's own declared keys
    // (#277). Empty here because this mock declares no grouping fields and
    // sends none — which is what the real response answers in that case too,
    // rather than the two arbitrary slot properties this replaces.
    grouping_fields: {},
    billed_cost_micros: billed,
    // The price half of the same rule (#351). This mock always resolves a
    // price — the sandbox recorder is handed one — so it says `known` out loud
    // rather than leaving the field to a default that would be wrong the day it
    // does not.
    pricing_status: "known",
    // The status and the amount are ONE fact and travel together: an absent
    // amount reads `unresolved` and never `known` at zero (#317, #320), and it
    // names the input that would settle it (#330).
    provider_cost_micros: cost.provider_cost_micros,
    costing_status: cost.costing_status,
    unresolved_reason: cost.unresolved_reason,
    new_balance_micros: balanceMicros,
    measurements: body.measurements ?? null,
    // EMPTY WHENEVER THE COST RESOLVED, because that is what the real response
    // does: the backend writes this list on the rate-card branch only, and a
    // caller who states the cost outright never reaches it. Listing the keys
    // anyway would make this panel warn about a declaration the API never
    // complained about.
    uncosted_measurement_keys: resolved ? [] : uncosted,
    pricing_provenance: {
      engine_version: "mock-1",
      // ONE SOURCE, because there is only one: a caller cannot state a price,
      // so "explicit" is a branch nothing can reach any more (#365).
      price_source: "rate_card",
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
