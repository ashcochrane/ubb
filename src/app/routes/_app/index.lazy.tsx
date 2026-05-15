import { createLazyFileRoute } from "@tanstack/react-router";
import { DashboardPage } from "@/features/dashboard/components/dashboard-page";

export const Route = createLazyFileRoute("/_app/")({
  component: DashboardPage,
});
