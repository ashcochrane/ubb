// src/features/billing/api/queries.ts
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toastOnError } from "@/lib/mutations";
import { billingMarginApi } from "./provider";
import type { UpdateMarginRequest } from "./types";

export function useMarginDashboard() {
  return useQuery({
    queryKey: ["margin-dashboard"],
    queryFn: () => billingMarginApi.getMarginDashboard(),
  });
}

export function useUpdateMargin() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (req: UpdateMarginRequest) => billingMarginApi.updateMargin(req),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["margin-dashboard"] }),
    onError: toastOnError("Couldn't update margin"),
  });
}
