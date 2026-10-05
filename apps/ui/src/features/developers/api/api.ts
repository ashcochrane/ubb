// Real API implementation — every call goes through `unwrap` so failures
// reject with a typed ApiProblem. Untyped bodies are narrowed via the
// functions in ./types (the only place their shapes are assumed).

import { meteringApi, rootApi, tenantApi } from "@/api/client";
import type { CursorPage } from "@/api/pagination";
import { unwrap } from "@/api/problem";
import {
  customerIdsIn,
  FIELD_AXIS,
  SUPPLIER_COGS,
} from "@/lib/economic-query";


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
  type Blueprint,
  type BlueprintSelection,
  type CustomerChoice,
  type EventTypeChoice,
  type KindChoice,
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

/** Customer choices for the test-console picker (current period, no filters).
 *
 *  The window is left to the server, which defaults it to the current month to
 *  date — the same default the margin list had. */
export async function listCustomerChoices(): Promise<CustomerChoice[]> {
  const answer = unwrap(
    await meteringApi.GET("/analytics/economics", {
      params: {
        query: { measures: [SUPPLIER_COGS], group_by: [FIELD_AXIS("customer")] },
      },
    }),
  );
  return customerIdsIn(answer).map((customer_id) => ({ customer_id }));
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

// ---------------------------------------------------------------------------
// The Code Builder (#579)

/**
 * Resolve a selection into an Integration Blueprint. A read at the Read floor
 * that stores one content-addressed snapshot and changes no configuration; a
 * draft preview needs the admin role (`403` below it) and stores nothing.
 */
export async function resolveBlueprint(selection: BlueprintSelection): Promise<Blueprint> {
  return unwrap(await rootApi.POST("/code-builder/blueprints", { body: selection }));
}

/** Every declared kind of work, retired ones included — the choices Configure offers. */
export async function listKindChoices(): Promise<KindChoice[]> {
  return unwrap(await rootApi.GET("/task-types")).task_types.map(({ key, kind, retired }) => ({
    key,
    kind,
    retired,
  }));
}

/** The most pages of Event Types Configure walks before it stops asking. */
const EVENT_TYPE_PAGES = 10;

/**
 * Every declared Event Type, walked page by page. Configure lists them all to
 * choose from, and a registry is small; the walk still stops after a bounded
 * number of pages rather than trusting `has_more` forever.
 */
export async function listEventTypeChoices(): Promise<EventTypeChoice[]> {
  const declared: EventTypeChoice[] = [];
  let cursor: string | undefined;
  for (let page = 0; page < EVENT_TYPE_PAGES; page++) {
    const answer = unwrap(
      await rootApi.GET("/event-types", { params: { query: { cursor, limit: 100 } } }),
    );
    declared.push(
      ...answer.data.map(({ key, declaration_status }) => ({ key, declaration_status })),
    );
    if (!answer.has_more || !answer.next_cursor) break;
    cursor = answer.next_cursor;
  }
  return declared;
}
