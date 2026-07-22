import { tenantApi, connectApi, sandboxApi } from "@/api/client";
import { requireData } from "@/api/errors";
import type { CursorPage } from "@/lib/use-cursor-list";
import type {
  ApiKey,
  ApiKeyCreate,
  ConnectStart,
  Invitation,
  InvitationCreate,
  Member,
  MemberRoleUpdate,
  SandboxReset,
  TenantConfig,
  TenantConfigUpdate,
  UntypedObject,
} from "./types";

// ── Tenant config ─────────────────────────────────────────────────────────
export function getConfig(): Promise<TenantConfig> {
  return tenantApi
    .GET("/config", {})
    .then((r) => requireData(r, "Failed to load settings"));
}

export function updateConfig(body: TenantConfigUpdate): Promise<TenantConfig> {
  return tenantApi
    .PATCH("/config", { body })
    .then((r) => requireData(r, "Failed to save settings"));
}

// ── API keys ──────────────────────────────────────────────────────────────
export function listApiKeys(params?: {
  cursor?: string;
  limit?: number;
}): Promise<CursorPage<ApiKey>> {
  return tenantApi
    .GET("/api-keys", { params: { query: params } })
    .then((r) => requireData(r, "Failed to load API keys"));
}

/** Returns an untyped object — the raw key lives under one of several fields. */
export function createApiKey(body: ApiKeyCreate): Promise<UntypedObject> {
  return tenantApi
    .POST("/api-keys", { body })
    .then((r) => requireData(r, "Failed to create API key"));
}

export function rotateApiKey(keyId: string): Promise<UntypedObject> {
  return tenantApi
    .POST("/api-keys/{key_id}/rotate", { params: { path: { key_id: keyId } } })
    .then((r) => requireData(r, "Failed to rotate API key"));
}

export function revokeApiKey(keyId: string): Promise<UntypedObject> {
  return tenantApi
    .DELETE("/api-keys/{key_id}", { params: { path: { key_id: keyId } } })
    .then((r) => requireData(r, "Failed to revoke API key"));
}

// ── Members ───────────────────────────────────────────────────────────────
export function listMembers(params?: {
  cursor?: string;
  limit?: number;
}): Promise<CursorPage<Member>> {
  return tenantApi
    .GET("/members", { params: { query: params } })
    .then((r) => requireData(r, "Failed to load team members"));
}

export function updateMemberRole(
  memberId: string,
  body: MemberRoleUpdate,
): Promise<Member> {
  return tenantApi
    .PATCH("/members/{member_id}", {
      params: { path: { member_id: memberId } },
      body,
    })
    .then((r) => requireData(r, "Failed to update role"));
}

export function removeMember(memberId: string): Promise<UntypedObject> {
  return tenantApi
    .DELETE("/members/{member_id}", {
      params: { path: { member_id: memberId } },
    })
    .then((r) => requireData(r, "Failed to remove member"));
}

// ── Invitations ───────────────────────────────────────────────────────────
export function listInvitations(params?: {
  cursor?: string;
  limit?: number;
}): Promise<CursorPage<Invitation>> {
  return tenantApi
    .GET("/invitations", { params: { query: params } })
    .then((r) => requireData(r, "Failed to load invitations"));
}

export function createInvitation(body: InvitationCreate): Promise<Invitation> {
  return tenantApi
    .POST("/invitations", { body })
    .then((r) => requireData(r, "Failed to send invitation"));
}

export function revokeInvitation(invitationId: string): Promise<UntypedObject> {
  return tenantApi
    .DELETE("/invitations/{invitation_id}", {
      params: { path: { invitation_id: invitationId } },
    })
    .then((r) => requireData(r, "Failed to revoke invitation"));
}

// ── Stripe Connect ────────────────────────────────────────────────────────
/** Returns an untyped object — the onboarding redirect url lives under `url`. */
export function connectStart(body: ConnectStart): Promise<UntypedObject> {
  return connectApi
    .POST("/start", { body })
    .then((r) => requireData(r, "Failed to start Stripe onboarding"));
}

export function connectStatus(): Promise<UntypedObject> {
  return connectApi
    .GET("/status", {})
    .then((r) => requireData(r, "Failed to load Stripe status"));
}

// ── Sandbox ───────────────────────────────────────────────────────────────
export function getSandbox(): Promise<UntypedObject> {
  return tenantApi
    .GET("/sandbox", {})
    .then((r) => requireData(r, "Failed to load sandbox"));
}

export function createSandbox(): Promise<UntypedObject> {
  return tenantApi
    .POST("/sandbox", {})
    .then((r) => requireData(r, "Failed to enable sandbox"));
}

export function resetSandbox(body: SandboxReset): Promise<UntypedObject> {
  return sandboxApi
    .POST("/reset", { body })
    .then((r) => requireData(r, "Failed to reset sandbox"));
}
