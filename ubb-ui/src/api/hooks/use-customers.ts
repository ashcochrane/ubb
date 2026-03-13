import { useQuery } from "@tanstack/react-query";
import { platformApi } from "../client";

export function useCustomers(params?: {
  status?: string;
  search?: string;
  cursor?: string;
  limit?: number;
}) {
  return useQuery({
    queryKey: ["customers", params],
    queryFn: async () => {
      const { data, error } = await platformApi.GET("/customers", {
        params: { query: params },
      });
      if (error) throw error;
      return data;
    },
  });
}

export function useCustomer(customerId: string) {
  return useQuery({
    queryKey: ["customers", customerId],
    queryFn: async () => {
      const { data, error } = await platformApi.GET("/customers/{customer_id}", {
        params: { path: { customer_id: customerId } },
      });
      if (error) throw error;
      return data;
    },
    enabled: !!customerId,
  });
}
