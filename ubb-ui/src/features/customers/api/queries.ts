// src/features/customers/api/queries.ts
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toastOnError } from "@/lib/mutations";
import { customersApi } from "./provider";
import type {
  CreateCustomerRequest,
  UpdateCustomerRequest,
} from "./types";

const LIST_KEY = ["customers", "list"] as const;
const detailKey = (id: string) => ["customers", "detail", id] as const;

export function useCustomers() {
  return useQuery({
    queryKey: LIST_KEY,
    queryFn: () => customersApi.listCustomers(),
  });
}

export function useCustomer(customerId: string) {
  return useQuery({
    queryKey: detailKey(customerId),
    queryFn: () => customersApi.getCustomer(customerId),
    enabled: !!customerId,
  });
}

export function useCreateCustomer() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (req: CreateCustomerRequest) => customersApi.createCustomer(req),
    onSuccess: () => qc.invalidateQueries({ queryKey: LIST_KEY }),
    onError: toastOnError("Couldn't create customer"),
  });
}

export function useUpdateCustomer(customerId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (req: UpdateCustomerRequest) =>
      customersApi.updateCustomer(customerId, req),
    onSuccess: (data) => {
      qc.setQueryData(detailKey(customerId), data);
      qc.invalidateQueries({ queryKey: LIST_KEY });
    },
    onError: toastOnError("Couldn't update customer"),
  });
}

export function useDeleteCustomer() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (customerId: string) => customersApi.deleteCustomer(customerId),
    onSuccess: () => qc.invalidateQueries({ queryKey: LIST_KEY }),
    onError: toastOnError("Couldn't delete customer"),
  });
}
