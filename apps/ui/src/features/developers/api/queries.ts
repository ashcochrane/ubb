// TanStack Query hooks for the developers feature. ALL query keys and
// invalidation live here. First key segment = backend namespace:
//   ["tenant", "api-keys"]  ["tenant", "sandbox"]  ["margin", "customers"]
// Mutations over-invalidate rather than miss.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { useCursorList } from "@/api/pagination";
import { ApiProblem } from "@/api/problem";
import { toastOnError, toastSuccess } from "@/lib/mutations";

import { developersApi } from "./provider";
import type { RecordUsageRequest } from "./types";

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
      // sibling (its prefixes surface via GET /tenant/sandbox).
      void queryClient.invalidateQueries({ queryKey: ["tenant", "api-keys"] });
      void queryClient.invalidateQueries({ queryKey: ["tenant", "sandbox"] });
    },
    // 422s (e.g. mode mismatch) surface inline in the create dialog.
  });
}

export function useRotateApiKey() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (keyId: string) => developersApi.rotateApiKey(keyId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["tenant", "api-keys"] });
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
      void queryClient.invalidateQueries({ queryKey: ["tenant", "api-keys"] });
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
      void queryClient.invalidateQueries({ queryKey: ["tenant", "sandbox"] });
    },
    onError: toastOnError("Couldn't create the sandbox key"),
  });
}

export function useMarginCustomers() {
  return useQuery({
    // Projection tail: this entry caches the EXTRACTED customers array, not
    // the raw MarginListOut — a bare ["margin","customers"] key would collide
    // with other features caching the raw response shape.
    queryKey: ["margin", "customers", "picker"] as const,
    queryFn: () => developersApi.listMarginCustomers(),
    staleTime: 60_000,
  });
}

export function useSendTestEvent() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: RecordUsageRequest) => developersApi.sendTestEvent(body),
    onSuccess: () => {
      // A recorded event touches usage lists/analytics, wallet balances,
      // and margin rollups — over-invalidate all three namespaces.
      void queryClient.invalidateQueries({ queryKey: ["metering"] });
      void queryClient.invalidateQueries({ queryKey: ["billing"] });
      void queryClient.invalidateQueries({ queryKey: ["margin"] });
    },
    // Errors render inline in the console's response column.
  });
}
