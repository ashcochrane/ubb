// src/features/customers/api/queries.ts
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toastOnError } from "@/lib/mutations";
import { customersApi } from "./provider";
import type { CustomerMappingData } from "./types";

const QUERY_KEY = ["customer-mapping"] as const;

export { QUERY_KEY };

export function useCustomerMapping() {
  return useQuery({
    queryKey: QUERY_KEY,
    queryFn: () => customersApi.getCustomerMapping(),
  });
}

export function useUpdateMapping() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      customerId,
      sdkIdentifier,
    }: {
      customerId: string;
      sdkIdentifier: string;
    }) => customersApi.updateMapping(customerId, sdkIdentifier),
    onMutate: async ({ customerId, sdkIdentifier }) => {
      await queryClient.cancelQueries({ queryKey: QUERY_KEY });
      const previous =
        queryClient.getQueryData<CustomerMappingData>(QUERY_KEY);
      if (previous) {
        const customer = previous.customers.find((c) => c.id === customerId);
        const wasUnmapped = customer && !customer.sdkIdentifier;
        queryClient.setQueryData<CustomerMappingData>(QUERY_KEY, {
          ...previous,
          customers: previous.customers.map((c) =>
            c.id === customerId
              ? {
                  ...c,
                  sdkIdentifier,
                  status: wasUnmapped ? ("idle" as const) : c.status,
                  events30d: wasUnmapped ? 0 : c.events30d,
                }
              : c,
          ),
          stats: wasUnmapped
            ? {
                ...previous.stats,
                mapped: previous.stats.mapped + 1,
                unmapped: previous.stats.unmapped - 1,
              }
            : previous.stats,
        });
      }
      return { previous };
    },
    onError: (error, _vars, context) => {
      if (context?.previous) {
        queryClient.setQueryData(QUERY_KEY, context.previous);
      }
      toastOnError("Couldn't update customer mapping")(error);
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEY });
    },
  });
}

export function useAssignOrphan() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      orphanId,
      stripeCustomerId,
    }: {
      orphanId: string;
      stripeCustomerId: string;
    }) => customersApi.assignOrphan(orphanId, stripeCustomerId),
    onMutate: async ({ orphanId }) => {
      await queryClient.cancelQueries({ queryKey: QUERY_KEY });
      const previous =
        queryClient.getQueryData<CustomerMappingData>(QUERY_KEY);
      if (previous) {
        const orphan = previous.orphanedIdentifiers.find(
          (o) => o.id === orphanId,
        );
        queryClient.setQueryData<CustomerMappingData>(QUERY_KEY, {
          ...previous,
          orphanedIdentifiers: previous.orphanedIdentifiers.filter(
            (o) => o.id !== orphanId,
          ),
          stats: {
            ...previous.stats,
            orphanedEvents:
              previous.stats.orphanedEvents - (orphan?.eventCount ?? 0),
            orphanedIdentifiers: previous.stats.orphanedIdentifiers - 1,
          },
        });
      }
      return { previous };
    },
    onError: (error, _vars, context) => {
      if (context?.previous) {
        queryClient.setQueryData(QUERY_KEY, context.previous);
      }
      toastOnError("Couldn't assign orphaned identifier")(error);
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEY });
    },
  });
}

export function useDismissOrphans() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => customersApi.dismissOrphans(),
    onMutate: async () => {
      await queryClient.cancelQueries({ queryKey: QUERY_KEY });
      const previous =
        queryClient.getQueryData<CustomerMappingData>(QUERY_KEY);
      if (previous) {
        queryClient.setQueryData<CustomerMappingData>(QUERY_KEY, {
          ...previous,
          orphanedIdentifiers: [],
          stats: {
            ...previous.stats,
            orphanedEvents: 0,
            orphanedIdentifiers: 0,
          },
        });
      }
      return { previous };
    },
    onError: (error, _vars, context) => {
      if (context?.previous) {
        queryClient.setQueryData(QUERY_KEY, context.previous);
      }
      toastOnError("Couldn't dismiss orphaned identifiers")(error);
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEY });
    },
  });
}

export function useTriggerSync() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => customersApi.triggerSync(),
    onMutate: async () => {
      await queryClient.cancelQueries({ queryKey: QUERY_KEY });
      const previous =
        queryClient.getQueryData<CustomerMappingData>(QUERY_KEY);
      if (previous) {
        queryClient.setQueryData<CustomerMappingData>(QUERY_KEY, {
          ...previous,
          syncStatus: { ...previous.syncStatus, syncing: true },
        });
      }
      return { previous };
    },
    onError: (error, _vars, context) => {
      if (context?.previous) {
        queryClient.setQueryData(QUERY_KEY, context.previous);
      }
      toastOnError("Couldn't start customer sync")(error);
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEY });
    },
  });
}
