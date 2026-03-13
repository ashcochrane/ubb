import { useQuery } from "@tanstack/react-query";
import { platformApi } from "../client";

export function useDashboardStats() {
  return useQuery({
    queryKey: ["dashboard", "stats"],
    queryFn: async () => {
      const [customersRes, walletsRes] = await Promise.all([
        platformApi.GET("/customers", { params: { query: { limit: 1 } } }),
        platformApi.GET("/wallets", { params: { query: { limit: 1 } } }),
      ]);
      return { customers: customersRes.data, wallets: walletsRes.data };
    },
  });
}
