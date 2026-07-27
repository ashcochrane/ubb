// TanStack hooks over the provider. ALL query keys + invalidation live here.
// First key segment is the backend namespace: ['webhooks', ...].
//
// There is NO GET-by-id in the contract — useWebhookConfig resolves a single
// endpoint by walking the cursor-paginated list until found (or exhausted →
// notFound). Mutations over-invalidate the whole ['webhooks'] namespace.

import * as React from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { useCursorList } from "@/api/pagination";

import { webhooksApi } from "./provider";
import type {
  WebhookConfig,
  WebhookConfigCreate,
  WebhookConfigUpdate,
  WebhookDelivery,
  WebhookSecretRotate,
} from "./types";

export const webhookKeys = {
  all: ["webhooks"] as const,
  configs: ["webhooks", "configs"] as const,
  deliveries: (configId: string) => ["webhooks", "deliveries", configId] as const,
};

export function useWebhookConfigs() {
  return useCursorList<WebhookConfig>(webhookKeys.configs, (cursor) =>
    webhooksApi.listConfigs({ cursor }),
  );
}

export function useWebhookDeliveries(configId: string) {
  return useCursorList<WebhookDelivery>(webhookKeys.deliveries(configId), (cursor) =>
    webhooksApi.listDeliveries(configId, { cursor }),
  );
}

export interface WebhookConfigLookup {
  config: WebhookConfig | undefined;
  isLoading: boolean;
  /** The list is fully loaded and the id isn't in it (deleted or never existed). */
  notFound: boolean;
  isError: boolean;
  error: unknown;
  refetch: () => void;
}

/** Resolve one endpoint from the list query (no GET-by-id exists). */
export function useWebhookConfig(configId: string): WebhookConfigLookup {
  const list = useWebhookConfigs();
  const config = list.rows.find((row) => row.id === configId);
  const { hasMore, isFetchingNextPage, isError, fetchNextPage } = list;

  // Keep paging until the id shows up or the list is exhausted.
  React.useEffect(() => {
    if (!config && hasMore && !isFetchingNextPage && !isError) {
      fetchNextPage();
    }
  }, [config, hasMore, isFetchingNextPage, isError, fetchNextPage]);

  const searching =
    !config && !isError && (list.isInitialLoading || hasMore || isFetchingNextPage);

  return {
    config,
    isLoading: searching,
    notFound: !config && !searching && !isError,
    isError,
    error: list.error,
    refetch: () => void list.refetch(),
  };
}

function useInvalidateWebhooks() {
  const queryClient = useQueryClient();
  // Every webhook-config mutation (create/update/delete/rotate) also writes
  // an audit record, so the settings audit ledger must refetch too.
  return () => {
    void queryClient.invalidateQueries({ queryKey: webhookKeys.all });
    void queryClient.invalidateQueries({ queryKey: ["audit"] });
  };
}

export function useCreateWebhookConfig() {
  const invalidate = useInvalidateWebhooks();
  return useMutation({
    mutationFn: (body: WebhookConfigCreate) => webhooksApi.createConfig(body),
    onSuccess: invalidate,
  });
}

export function useUpdateWebhookConfig() {
  const invalidate = useInvalidateWebhooks();
  return useMutation({
    mutationFn: (variables: { configId: string; body: WebhookConfigUpdate }) =>
      webhooksApi.updateConfig(variables.configId, variables.body),
    onSuccess: invalidate,
  });
}

export function useDeleteWebhookConfig() {
  const invalidate = useInvalidateWebhooks();
  return useMutation({
    mutationFn: (variables: { configId: string }) =>
      webhooksApi.deleteConfig(variables.configId),
    onSuccess: invalidate,
  });
}

export function useRotateWebhookSecret() {
  const invalidate = useInvalidateWebhooks();
  return useMutation({
    mutationFn: (variables: { configId: string; body: WebhookSecretRotate }) =>
      webhooksApi.rotateSecret(variables.configId, variables.body),
    onSuccess: invalidate,
  });
}
