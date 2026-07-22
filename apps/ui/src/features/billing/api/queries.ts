// src/features/billing/api/queries.ts
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toastOnError } from "@/lib/mutations";
import { billingMarginApi } from "./provider";
import type { UpdateDefaultMarginRequest } from "./types";

const QUERY_KEY = ["default-margin"] as const;

export function useDefaultMargin() {
  return useQuery({
    queryKey: QUERY_KEY,
    queryFn: () => billingMarginApi.getDefaultMargin(),
  });
}

export function useUpdateDefaultMargin() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (req: UpdateDefaultMarginRequest) =>
      billingMarginApi.updateDefaultMargin(req),
    onSuccess: (data) => qc.setQueryData(QUERY_KEY, data),
    onError: toastOnError("Couldn't update default margin"),
  });
}
