import { createFileRoute } from "@tanstack/react-router";
import { WebhookDetailPage } from "@/features/webhooks/components/webhook-detail-page";

export const Route = createFileRoute("/_app/webhooks/$configId")({
  component: RouteComponent,
});

function RouteComponent() {
  const { configId } = Route.useParams();
  return <WebhookDetailPage configId={configId} />;
}
