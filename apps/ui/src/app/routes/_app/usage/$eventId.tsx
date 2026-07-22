import { createFileRoute } from "@tanstack/react-router";
import { UsageEventPage } from "@/features/usage/components/usage-event-page";

export const Route = createFileRoute("/_app/usage/$eventId")({
  component: RouteComponent,
});

function RouteComponent() {
  const { eventId } = Route.useParams();
  return <UsageEventPage eventId={eventId} />;
}
