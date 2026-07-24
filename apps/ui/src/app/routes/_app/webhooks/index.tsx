import { createFileRoute } from "@tanstack/react-router";

import { WebhooksPage } from "@/features/webhooks/components/webhooks-page";

export const Route = createFileRoute("/_app/webhooks/")({
  component: RouteComponent,
});

function RouteComponent() {
  const navigate = Route.useNavigate();
  return (
    <WebhooksPage
      onOpenConfig={(configId) =>
        void navigate({ to: "/webhooks/$configId", params: { configId } })
      }
    />
  );
}
