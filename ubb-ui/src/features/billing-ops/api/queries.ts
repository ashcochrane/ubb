// src/features/billing-ops/api/queries.ts
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toastOnError } from "@/lib/mutations";
import { billingOpsApi } from "./provider";
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
    queryFn: () => billingOpsApi.getBalance(customerId),
    enabled: !!customerId,
  });
}

export function useTransactions(customerId: string) {
  return useQuery({
    queryKey: txKey(customerId),
    queryFn: () => billingOpsApi.getTransactions(customerId),
    enabled: !!customerId,
  });
}

function useBillingMutation<TVars>(
  customerId: string,
  fn: (vars: TVars) => Promise<void>,
  errorMessage: string,
) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: balanceKey(customerId) });
      qc.invalidateQueries({ queryKey: txKey(customerId) });
    },
    onError: toastOnError(errorMessage),
  });
}

export function useCreateTopUp(customerId: string) {
  return useBillingMutation<CreateTopUpRequest>(
    customerId,
    (body) => billingOpsApi.createTopUp(customerId, body),
    "Couldn't start top-up",
  );
}

export function useWithdraw(customerId: string) {
  return useBillingMutation<WithdrawRequest>(
    customerId,
    (body) => billingOpsApi.withdraw(customerId, body),
    "Couldn't withdraw",
  );
}

export function useRefund(customerId: string) {
  return useBillingMutation<RefundRequest>(
    customerId,
    (body) => billingOpsApi.refund(customerId, body),
    "Couldn't refund",
  );
}

export function useConfigureAutoTopUp(customerId: string) {
  return useBillingMutation<ConfigureAutoTopUpRequest>(
    customerId,
    (body) => billingOpsApi.configureAutoTopUp(customerId, body),
    "Couldn't configure auto top-up",
  );
}
