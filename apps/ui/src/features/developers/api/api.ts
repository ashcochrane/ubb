// Real API implementation — every call goes through `unwrap` so failures
// reject with a typed ApiProblem. Untyped bodies are narrowed via the
// functions in ./types (the only place their shapes are assumed).

import { marginApi, meteringApi, tenantApi } from "@/api/client";
import type { CursorPage } from "@/api/pagination";
import { unwrap } from "@/api/problem";

import {
  toApiKeyCreated,
  toApiKeyRevoked,
  toApiKeyRotated,
  toSandboxKeyMinted,
  toSandboxStatus,
  type ApiKey,
  type ApiKeyCreated,
  type ApiKeyRevoked,
  type ApiKeyRotated,
  type MarginCustomerRow,
  type RecordUsageRequest,
  type RecordUsageResponse,
  type SandboxKeyMinted,
  type SandboxStatus,
} from "./types";

/** THIS tenant's keys (active and revoked), newest first, house cursor page. */
export async function listApiKeys(cursor?: string): Promise<CursorPage<ApiKey>> {
  return unwrap(
    await tenantApi.GET("/api-keys", { params: { query: { cursor } } }),
  );
}

/**
 * Mint a key. The raw key is in the 201 body exactly once; with is_test=true
 * it lands on the sandbox sibling tenant (response tenant_id says where).
 */
export async function createApiKey(input: {
  label: string;
  is_test: boolean;
}): Promise<ApiKeyCreated> {
  return toApiKeyCreated(
    unwrap(await tenantApi.POST("/api-keys", { body: input })),
  );
}

/** Mint successor + deactivate old in one transaction; raw key shown once. */
export async function rotateApiKey(keyId: string): Promise<ApiKeyRotated> {
  return toApiKeyRotated(
    unwrap(
      await tenantApi.POST("/api-keys/{key_id}/rotate", {
        params: { path: { key_id: keyId } },
      }),
    ),
  );
}

/** Soft-revoke. The last active key answers 409 last_active_key (rotate instead). */
export async function revokeApiKey(keyId: string): Promise<ApiKeyRevoked> {
  return toApiKeyRevoked(
    unwrap(
      await tenantApi.DELETE("/api-keys/{key_id}", {
        params: { path: { key_id: keyId } },
      }),
    ),
  );
}

/** Sandbox status for the calling live tenant. */
export async function getSandbox(): Promise<SandboxStatus> {
  return toSandboxStatus(unwrap(await tenantApi.GET("/sandbox")));
}

/**
 * Provision-or-fetch the sandbox sibling and mint a FRESH ubb_test_ key.
 * Every call mints a new key — this is also the sandbox key rotation path.
 */
export async function createSandbox(): Promise<SandboxKeyMinted> {
  return toSandboxKeyMinted(unwrap(await tenantApi.POST("/sandbox")));
}

/** Customer rows for the test-console picker (current period, no filters). */
export async function listMarginCustomers(): Promise<MarginCustomerRow[]> {
  return unwrap(await marginApi.GET("/customers")).customers;
}

/**
 * Record one usage event. One-rule contract: HTTP 200 even for the tipping
 * event past a limit — the stop instruction rides the response body.
 */
export async function sendTestEvent(
  body: RecordUsageRequest,
): Promise<RecordUsageResponse> {
  return unwrap(await meteringApi.POST("/usage", { body }));
}
