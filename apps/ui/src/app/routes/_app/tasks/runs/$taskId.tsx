import { createFileRoute } from "@tanstack/react-router";

import { RunDetailPage } from "@/features/tasks/components/run-detail-page";

export const Route = createFileRoute("/_app/tasks/runs/$taskId")({
  component: RouteComponent,
});

function RouteComponent() {
  const { taskId } = Route.useParams();
  return <RunDetailPage taskId={taskId} />;
}
