import { createFileRoute } from "@tanstack/react-router";

import { KindDetailPage } from "@/features/tasks/components/kind-detail-page";

export const Route = createFileRoute("/_app/tasks/kinds/$key")({
  component: RouteComponent,
});

function RouteComponent() {
  const { key } = Route.useParams();
  return <KindDetailPage kindKey={key} />;
}
