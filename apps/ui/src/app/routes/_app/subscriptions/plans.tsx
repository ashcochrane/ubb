import { createFileRoute } from "@tanstack/react-router";
import { PlansPage } from "@/features/subscriptions/components/plans-page";

export const Route = createFileRoute("/_app/subscriptions/plans")({
  component: PlansPage,
});
