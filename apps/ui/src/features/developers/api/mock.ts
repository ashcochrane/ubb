// Mock implementation — same exported signatures as ./api. Mutations are
// simulated coherently within a session via module-level state: minted keys
// appear in the list (sandbox keys land on the sandbox's prefix list, not
// here — mirroring the real routing) and rotation deactivates the old key.
// The Code Builder's Blueprints and Verify answers are the platform's own
// (`./mock-blueprints`, `./mock-verifications`); none is written here.

import type { CursorPage } from "@/api/pagination";
import { ApiProblem, toApiProblem } from "@/api/problem";
import { currentMockMemberRole, roleIsKnownToMeet } from "@/hooks/use-current-role";
import { mockDelay } from "@/lib/api-provider";

import { MOCK_HAS_NO_VERIFICATION } from "../lib/verification";
import {
  MOCK_API_KEYS,
  MOCK_SANDBOX,
  MOCK_SANDBOX_TENANT_ID,
  MOCK_LIVE_TENANT_ID,
  mockKeyPrefix,
  mockRawKey,
} from "./mock-data";
import { mockAnswers, mockRegistry, selectionKey } from "./mock-blueprints";
import { mockVerifications, verificationKey } from "./mock-verifications";
import type {
  ApiKey,
  ApiKeyCreated,
  ApiKeyRevoked,
  ApiKeyRotated,
  Blueprint,
  BlueprintSelection,
  BlueprintVerification,
  BlueprintVerificationRequest,
  EventTypeChoice,
  KindChoice,
  SandboxKeyMinted,
  SandboxStatus,
} from "./types";

let keys: ApiKey[] = MOCK_API_KEYS.map((key) => ({ ...key }));
let sandbox: SandboxStatus = {
  ...MOCK_SANDBOX,
  key_prefixes: [...MOCK_SANDBOX.key_prefixes],
};

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

// ---------------------------------------------------------------------------
// The Code Builder (#579): the platform's own Blueprints (`./mock-blueprints`)

/**
 * The server's floor, enforced against the one role mock mode has: a draft
 * preview below admin is refused exactly as the route refuses it. The page
 * offers the toggle only to a known admin, so this answers a page whose idea
 * of the caller has gone stale.
 */
export async function resolveBlueprint(selection: BlueprintSelection): Promise<Blueprint> {
  await mockDelay();
  if (selection.draft_preview && !roleIsKnownToMeet(currentMockMemberRole(), "admin")) {
    throw new ApiProblem({
      status: 403,
      code: "forbidden",
      title: "Forbidden",
      detail: "A draft preview requires the admin role.",
    });
  }
  const answer = (await mockAnswers()).get(selectionKey(selection));
  if (answer === undefined) {
    // Not a refusal the platform makes: the mock answers only selections the
    // platform wrote a Blueprint for, and says so rather than inventing one.
    throw new ApiProblem({
      status: 404,
      code: "mock_has_no_blueprint",
      title: "Not in the mock",
      detail:
        "The mock answers each selection with the Blueprint the platform wrote for it, and the platform wrote none for this one.",
    });
  }
  return structuredClone(answer);
}

/**
 * Verify answered with what the platform answered (`./mock-verifications`):
 * the exact request the platform verified, for the fingerprint it verified it
 * against, gets that answer or that refusal; any other request is one the
 * platform never answered, and the mock says so. The route's Write floor is
 * enforced against the one role mock mode has, as the draft floor is.
 */
export async function verifyBlueprint(
  fingerprint: string,
  body: BlueprintVerificationRequest,
): Promise<BlueprintVerification> {
  await mockDelay();
  if (!roleIsKnownToMeet(currentMockMemberRole(), "write")) {
    throw new ApiProblem({
      status: 403,
      code: "forbidden",
      title: "Forbidden",
      detail: "Verifying a Blueprint requires the write role.",
    });
  }
  const committed = (await mockVerifications()).get(verificationKey(fingerprint, body));
  if (committed === undefined) {
    throw new ApiProblem({
      status: 404,
      code: MOCK_HAS_NO_VERIFICATION,
      title: "Not in the mock",
      detail:
        "The mock answers Verify only with what the platform answered, and the platform verified no request like this one for this Blueprint.",
    });
  }
  if (committed.kind === "refused") throw toApiProblem(structuredClone(committed.problem));
  return structuredClone(committed.answer);
}

export async function listKindChoices(): Promise<KindChoice[]> {
  await mockDelay();
  return (await mockRegistry()).kinds;
}

export async function listEventTypeChoices(): Promise<EventTypeChoice[]> {
  await mockDelay();
  return (await mockRegistry()).eventTypes;
}
