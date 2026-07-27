import { createFileRoute } from "@tanstack/react-router";
import { SubscriptionsPage } from "@/features/subscriptions/components/subscriptions-page";

export const Route = createFileRoute("/_app/subscriptions/")({
  component: SubscriptionsPage,
});
