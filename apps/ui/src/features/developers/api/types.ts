// Developers feature — type aliases from the generated schema map, plus local
// interfaces for the contract's UNTYPED responses (additionalProperties: true).
//
// The API-key mint/rotate/revoke and sandbox bodies are declared as open
// objects in the OpenAPI schema, so the generated types are
// `Record<string, unknown>`. The interfaces + narrowing functions below are
// the single place those shapes are assumed; everything else consumes the
// narrowed types. The narrowers read fields with typeof checks (no casts), so
// a drifted backend degrades to empty strings instead of crashing the UI.

import type { MarginSchemas, MeteringSchemas, TenantSchemas } from "@/api/types";

export type ApiKey = TenantSchemas["ApiKeyOut"];
export type RecordUsageRequest = MeteringSchemas["RecordUsageRequest"];
export type RecordUsageResponse = MeteringSchemas["RecordUsageResponse"];
export type MarginCustomerRow = MarginSchemas["CustomerMarginListRow"];

// ---------------------------------------------------------------------------
// [backend-verified shape — see discovery spec] POST /tenant/api-keys → 201.
// `api_key` is the RAW key, returned exactly once; `tenant_id` says which
// tenant the key landed on (the sandbox sibling when is_test=true).
export interface ApiKeyCreated {
  id: string;
  key_prefix: string;
  label: string;
  tenant_id: string;
  api_key: string;
}

// [backend-verified shape — see discovery spec] POST /tenant/api-keys/{id}/rotate → 200.
export interface ApiKeyRotated {
  id: string;
  key_prefix: string;
  label: string;
  revoked_key_id: string;
  api_key: string;
}

// [backend-verified shape — see discovery spec] DELETE /tenant/api-keys/{id} → 200.
export interface ApiKeyRevoked {
  id: string;
  is_active: boolean;
}

// [backend-verified shape — see discovery spec] GET /tenant/sandbox → 200.
export interface SandboxStatus {
  exists: boolean;
  sandbox_tenant_id: string | null;
  key_prefixes: string[];
}

// [backend-verified shape — see discovery spec] POST /tenant/sandbox → 200.
// Every call mints a fresh ubb_test_ key (that is also the rotation path).
export interface SandboxKeyMinted {
  sandbox_tenant_id: string;
  api_key: string;
}

// ---------------------------------------------------------------------------
// Narrowers — typeof-checked field reads, no type assertions.

function str(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function strOrNull(value: unknown): string | null {
  return typeof value === "string" ? value : null;
}

function strArray(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string")
    : [];
}

export function toApiKeyCreated(raw: Record<string, unknown>): ApiKeyCreated {
  return {
    id: str(raw["id"]),
    key_prefix: str(raw["key_prefix"]),
    label: str(raw["label"]),
    tenant_id: str(raw["tenant_id"]),
    api_key: str(raw["api_key"]),
  };
}

export function toApiKeyRotated(raw: Record<string, unknown>): ApiKeyRotated {
  return {
    id: str(raw["id"]),
    key_prefix: str(raw["key_prefix"]),
    label: str(raw["label"]),
    revoked_key_id: str(raw["revoked_key_id"]),
    api_key: str(raw["api_key"]),
  };
}

export function toApiKeyRevoked(raw: Record<string, unknown>): ApiKeyRevoked {
  return {
    id: str(raw["id"]),
    is_active: raw["is_active"] === true,
  };
}

export function toSandboxStatus(raw: Record<string, unknown>): SandboxStatus {
  return {
    exists: raw["exists"] === true,
    sandbox_tenant_id: strOrNull(raw["sandbox_tenant_id"]),
    key_prefixes: strArray(raw["key_prefixes"]),
  };
}

export function toSandboxKeyMinted(raw: Record<string, unknown>): SandboxKeyMinted {
  return {
    sandbox_tenant_id: str(raw["sandbox_tenant_id"]),
    api_key: str(raw["api_key"]),
  };
}
