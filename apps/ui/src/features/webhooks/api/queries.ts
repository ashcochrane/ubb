import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { toastOnError } from "@/lib/mutations";
import { useCursorList } from "@/lib/use-cursor-list";
import * as api from "./api";
import type {
  WebhookConfigCreate,
  WebhookConfigUpdate,
  WebhookSecretRotate,
} from "./types";

const CONFIGS_KEY = ["webhooks", "configs"] as const;
const deliveriesKey = (id: string) => ["webhooks", "deliveries", id] as const;

export function useWebhookConfigs() {
  return useCursorList({
    queryKeyBase: CONFIGS_KEY,
    fetchPage: (cursor) => api.listConfigs({ cursor, limit: 50 }),
  });
}

/**
 * Look up a single endpoint. The API has no single-GET route, so we read the
 * first page (up to 100) and find it. Sufficient for realistic endpoint counts;
 * returns undefined if it lives beyond the first page.
 */
export function useWebhookConfig(configId: string) {
  return useQuery({
    queryKey: [...CONFIGS_KEY, "one", configId],
    queryFn: async () => {
      const page = await api.listConfigs({ limit: 100 });
      return page.data.find((c) => c.id === configId) ?? null;
    },
    enabled: !!configId,
  });
}

export function useWebhookDeliveries(configId: string) {
  return useCursorList({
    queryKeyBase: deliveriesKey(configId),
    fetchPage: (cursor) => api.listDeliveries(configId, { cursor, limit: 50 }),
    enabled: !!configId,
  });
}

export function useCreateWebhook() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: WebhookConfigCreate) => api.createConfig(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: CONFIGS_KEY });
      toast.success("Webhook endpoint created");
    },
    onError: toastOnError("Couldn't create webhook endpoint"),
  });
}

export function useUpdateWebhook(configId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: WebhookConfigUpdate) => api.updateConfig(configId, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: CONFIGS_KEY });
      toast.success("Webhook endpoint updated");
    },
    onError: toastOnError("Couldn't update webhook endpoint"),
  });
}

export function useDeleteWebhook() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (configId: string) => api.deleteConfig(configId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: CONFIGS_KEY });
      toast.success("Webhook endpoint deleted");
    },
    onError: toastOnError("Couldn't delete webhook endpoint"),
  });
}

export function useRotateSecret(configId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: WebhookSecretRotate) => api.rotateSecret(configId, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: CONFIGS_KEY });
      toast.success("Secret rotated");
    },
    onError: toastOnError("Couldn't rotate secret"),
  });
}
