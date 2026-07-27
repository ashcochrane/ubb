import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { toastOnError } from "@/lib/mutations";
import { useCursorList } from "@/lib/use-cursor-list";
import * as api from "./api";
import type {
  ApiKeyCreate,
  InvitationCreate,
  MemberRoleUpdate,
  SandboxReset,
  TenantConfigUpdate,
} from "./types";

/** Tenant context lives under ["me"] (see features/auth). Invalidate it after
 *  a config change so nav, product-gating, and currency refresh app-wide. */
const ME_KEY = ["me"] as const;
const API_KEYS_KEY = ["settings", "api-keys"] as const;
const MEMBERS_KEY = ["settings", "members"] as const;
const INVITATIONS_KEY = ["settings", "invitations"] as const;
const CONNECT_STATUS_KEY = ["settings", "connect-status"] as const;
const SANDBOX_KEY = ["settings", "sandbox"] as const;

// ── Config ────────────────────────────────────────────────────────────────
export function useUpdateConfig() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: TenantConfigUpdate) => api.updateConfig(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ME_KEY });
      toast.success("Settings saved");
    },
    onError: toastOnError("Couldn't save settings"),
  });
}

// ── API keys ──────────────────────────────────────────────────────────────
export function useApiKeys() {
  return useCursorList({
    queryKeyBase: API_KEYS_KEY,
    fetchPage: (cursor) => api.listApiKeys({ cursor, limit: 50 }),
  });
}

export function useCreateApiKey() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: ApiKeyCreate) => api.createApiKey(body),
    onSuccess: () => qc.invalidateQueries({ queryKey: API_KEYS_KEY }),
    onError: toastOnError("Couldn't create API key"),
  });
}

export function useRotateApiKey() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (keyId: string) => api.rotateApiKey(keyId),
    onSuccess: () => qc.invalidateQueries({ queryKey: API_KEYS_KEY }),
    onError: toastOnError("Couldn't rotate API key"),
  });
}

export function useRevokeApiKey() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (keyId: string) => api.revokeApiKey(keyId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: API_KEYS_KEY });
      toast.success("API key revoked");
    },
    onError: toastOnError("Couldn't revoke API key"),
  });
}

// ── Members ───────────────────────────────────────────────────────────────
export function useMembers() {
  return useCursorList({
    queryKeyBase: MEMBERS_KEY,
    fetchPage: (cursor) => api.listMembers({ cursor, limit: 50 }),
  });
}

export function useUpdateMemberRole() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { memberId: string; body: MemberRoleUpdate }) =>
      api.updateMemberRole(vars.memberId, vars.body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: MEMBERS_KEY });
      toast.success("Role updated");
    },
    onError: toastOnError("Couldn't update role"),
  });
}

export function useRemoveMember() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (memberId: string) => api.removeMember(memberId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: MEMBERS_KEY });
      toast.success("Member removed");
    },
    onError: toastOnError("Couldn't remove member"),
  });
}

// ── Invitations ───────────────────────────────────────────────────────────
export function useInvitations() {
  return useCursorList({
    queryKeyBase: INVITATIONS_KEY,
    fetchPage: (cursor) => api.listInvitations({ cursor, limit: 50 }),
  });
}

export function useCreateInvitation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: InvitationCreate) => api.createInvitation(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: INVITATIONS_KEY });
      toast.success("Invitation sent");
    },
    onError: toastOnError("Couldn't send invitation"),
  });
}

export function useRevokeInvitation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (invitationId: string) => api.revokeInvitation(invitationId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: INVITATIONS_KEY });
      toast.success("Invitation revoked");
    },
    onError: toastOnError("Couldn't revoke invitation"),
  });
}

// ── Stripe Connect ────────────────────────────────────────────────────────
export function useConnectStatus() {
  return useQuery({
    queryKey: CONNECT_STATUS_KEY,
    queryFn: api.connectStatus,
  });
}

export function useConnectStart() {
  return useMutation({
    mutationFn: (returnUrl: string) => api.connectStart({ return_url: returnUrl }),
    onError: toastOnError("Couldn't start Stripe onboarding"),
  });
}

// ── Sandbox ───────────────────────────────────────────────────────────────
export function useSandbox() {
  return useQuery({
    queryKey: SANDBOX_KEY,
    queryFn: api.getSandbox,
  });
}

export function useCreateSandbox() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.createSandbox(),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: SANDBOX_KEY });
      toast.success("Sandbox enabled");
    },
    onError: toastOnError("Couldn't enable sandbox"),
  });
}

export function useResetSandbox() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: SandboxReset) => api.resetSandbox(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: SANDBOX_KEY });
      toast.success("Sandbox data reset");
    },
    onError: toastOnError("Couldn't reset sandbox"),
  });
}
