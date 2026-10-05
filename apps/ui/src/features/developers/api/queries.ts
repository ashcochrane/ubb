// TanStack Query hooks for the developers feature. ALL query keys and
// invalidation live here. First key segment = backend namespace:
//   ["tenant", "api-keys"]  ["tenant", "sandbox"]
//   ["code-builder", "blueprints", <selection>]
//   ["tasks", "kinds", "code-builder"]  ["event-types", "code-builder"]
// Mutations over-invalidate rather than miss.

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { useCursorList } from "@/api/pagination";
import { ApiProblem } from "@/api/problem";
import { toastOnError, toastSuccess } from "@/lib/mutations";

import { developersApi } from "./provider";
import type { BlueprintSelection, BlueprintVerificationRequest } from "./types";

export function useApiKeys() {
  return useCursorList(["tenant", "api-keys"], (cursor) =>
    developersApi.listApiKeys(cursor),
  );
}

export function useCreateApiKey() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: { label: string; is_test: boolean }) =>
      developersApi.createApiKey(input),
    onSuccess: () => {
      // A live key lands in this list; a sandbox key lands on the sandbox
      // sibling (its prefixes surface via GET /tenant/sandbox). Key minting
      // writes an api_key.created audit record.
      void queryClient.invalidateQueries({ queryKey: ["tenant", "api-keys"] });
      void queryClient.invalidateQueries({ queryKey: ["tenant", "sandbox"] });
      void queryClient.invalidateQueries({ queryKey: ["audit"] });
    },
    // 422s (e.g. mode mismatch) surface inline in the create dialog.
  });
}

export function useRotateApiKey() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (keyId: string) => developersApi.rotateApiKey(keyId),
    onSuccess: () => {
      // Rotation writes an api_key.rotated audit record.
      void queryClient.invalidateQueries({ queryKey: ["tenant", "api-keys"] });
      void queryClient.invalidateQueries({ queryKey: ["audit"] });
    },
    onError: toastOnError("Couldn't rotate the key"),
  });
}

export function useRevokeApiKey() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (keyId: string) => developersApi.revokeApiKey(keyId),
    onSuccess: () => {
      toastSuccess("API key revoked");
      // Revocation writes an api_key.revoked audit record.
      void queryClient.invalidateQueries({ queryKey: ["tenant", "api-keys"] });
      void queryClient.invalidateQueries({ queryKey: ["audit"] });
    },
    onError: (error: unknown) => {
      if (error instanceof ApiProblem && error.code === "last_active_key") {
        // The lockout guard: with zero active keys the tenant could never
        // call the API again to mint a replacement.
        toast.error("This is the last active key", {
          description:
            "Revoking it would lock this workspace out of the API. Rotate the key instead — rotation mints a replacement in the same transaction.",
        });
        return;
      }
      toastOnError("Couldn't revoke the key")(error);
    },
  });
}

export function useSandbox() {
  return useQuery({
    queryKey: ["tenant", "sandbox"] as const,
    queryFn: () => developersApi.getSandbox(),
  });
}

export function useCreateSandbox() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => developersApi.createSandbox(),
    onSuccess: () => {
      // Provisioning writes a sandbox.created audit record.
      void queryClient.invalidateQueries({ queryKey: ["tenant", "sandbox"] });
      void queryClient.invalidateQueries({ queryKey: ["audit"] });
    },
    onError: toastOnError("Couldn't create the sandbox key"),
  });
}

/**
 * The Blueprint for a selection, resolved afresh whenever the page is shown.
 *
 * ⚠ NEVER SERVED STALE FROM CACHE (`staleTime: 0`). A Blueprint is a
 * resolution of configuration that changes on other screens — the round trip
 * goes there to fix it and comes back — so returning to this page, or to its
 * browser tab, must resolve again; the console's 30-second default would show
 * the Blueprint from before the fix. While a new selection resolves, the last
 * one stays on screen (`isPlaceholderData` says so) rather than the page
 * emptying on every click.
 */
export function useBlueprint(selection: BlueprintSelection) {
  return useQuery({
    queryKey: ["code-builder", "blueprints", selection] as const,
    queryFn: () => developersApi.resolveBlueprint(selection),
    staleTime: 0,
    placeholderData: keepPreviousData,
    retry: false,
  });
}

/**
 * The tenant's kinds of work, for Configure to choose from. Under the `tasks`
 * prefix so that declaring a kind on Tasks — which invalidates `["tasks"]` —
 * refreshes these choices too; under a tail of its own because what it caches
 * is a projection (`KindChoice[]`), not the kinds the tasks feature caches
 * under `["tasks", "kinds"]` — same key, same cached shape.
 */
export function useKindChoices() {
  return useQuery({
    queryKey: ["tasks", "kinds", "code-builder"] as const,
    queryFn: () => developersApi.listKindChoices(),
    staleTime: 0,
  });
}

/** The tenant's Event Types, as Configure offers them (a projection). */
export function useEventTypeChoices() {
  return useQuery({
    queryKey: ["event-types", "code-builder"] as const,
    queryFn: () => developersApi.listEventTypeChoices(),
    staleTime: 0,
  });
}

/** What one Verify sends: the fingerprint it runs against, and the samples. */
export interface VerifyInput {
  readonly fingerprint: string;
  readonly body: BlueprintVerificationRequest;
}

/**
 * Verify the Blueprint on screen (#581). It invalidates nothing, because it
 * changes nothing: the run is built and rolled back inside the request, and
 * verifying does not even refresh how long the fingerprint is kept (#580).
 * Refusals render inline in the Verify stage, as the preconditions they are.
 */
export function useVerifyBlueprint() {
  return useMutation({
    mutationFn: ({ fingerprint, body }: VerifyInput) =>
      developersApi.verifyBlueprint(fingerprint, body),
  });
}
