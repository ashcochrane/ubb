// src/features/dashboard/api/queries.ts
import { useQuery } from "@tanstack/react-query";
import { dashboardApi } from "./provider";

export function useDashboard() {
  return useQuery({
    queryKey: ["dashboard"],
    queryFn: () => dashboardApi.getDashboard(),
  });
}
