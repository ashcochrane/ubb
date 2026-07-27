// src/features/billing-ops/api/queries.ts
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { toastOnError } from "@/lib/mutations";
import { useCursorList } from "@/lib/use-cursor-list";
import * as api from "./api";
import type {
  ConfigureAutoTopUpRequest,
  CreateTopUpRequest,
  RefundRequest,
  WithdrawRequest,
} from "./types";

const balanceKey = (id: string) => ["billing-ops", "balance", id] as const;
const txKey = (id: string) => ["billing-ops", "transactions", id] as const;

export function useBalance(customerId: string) {
  return useQuery({
    queryKey: balanceKey(customerId),
    queryFn: () => api.getBalance(customerId),
    enabled: !!customerId,
  });
}

export function useTransactions(customerId: string) {
  return useCursorList({
    queryKeyBase: txKey(customerId),
    fetchPage: (cursor) => api.getTransactions(customerId, { cursor, limit: 50 }),
    enabled: !!customerId,
  });
}

function useWalletRefetch(customerId: string) {
  const qc = useQueryClient();
  return () => {
    qc.invalidateQueries({ queryKey: balanceKey(customerId) });
    qc.invalidateQueries({ queryKey: txKey(customerId) });
  };
}

export function useCreateTopUp(customerId: string) {
  const refresh = useWalletRefetch(customerId);
  return useMutation({
    mutationFn: (body: CreateTopUpRequest) => api.createTopUp(customerId, body),
    onSuccess: refresh,
    onError: toastOnError("Couldn't start top-up"),
  });
}

export function useWithdraw(customerId: string) {
  const refresh = useWalletRefetch(customerId);
  return useMutation({
    mutationFn: (body: WithdrawRequest) => api.withdraw(customerId, body),
    onSuccess: () => {
      refresh();
      toast.success("Withdrawal complete");
    },
    onError: toastOnError("Couldn't withdraw"),
  });
}

export function useRefund(customerId: string) {
  const refresh = useWalletRefetch(customerId);
  return useMutation({
    mutationFn: (body: RefundRequest) => api.refund(customerId, body),
    onSuccess: () => {
      refresh();
      toast.success("Refund issued");
    },
    onError: toastOnError("Couldn't refund"),
  });
}

export function useConfigureAutoTopUp(customerId: string) {
  const refresh = useWalletRefetch(customerId);
  return useMutation({
    mutationFn: (body: ConfigureAutoTopUpRequest) =>
      api.configureAutoTopUp(customerId, body),
    onSuccess: () => {
      refresh();
      toast.success("Auto top-up saved");
    },
    onError: toastOnError("Couldn't configure auto top-up"),
  });
}
