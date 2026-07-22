import { createFileRoute } from "@tanstack/react-router";
import { WebhooksPage } from "@/features/webhooks/components/webhooks-page";

export const Route = createFileRoute("/_app/webhooks/")({
  component: WebhooksPage,
});
