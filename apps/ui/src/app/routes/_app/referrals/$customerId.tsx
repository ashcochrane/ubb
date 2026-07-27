import { createFileRoute } from "@tanstack/react-router";
import { ReferrerDetailPage } from "@/features/referrals/components/referrer-detail-page";

export const Route = createFileRoute("/_app/referrals/$customerId")({
  component: RouteComponent,
});

function RouteComponent() {
  const { customerId } = Route.useParams();
  return <ReferrerDetailPage customerId={customerId} />;
}
