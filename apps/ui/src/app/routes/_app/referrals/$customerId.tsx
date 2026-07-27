import { createFileRoute } from "@tanstack/react-router";

import { ReferrerDetailPage } from "@/features/referrals/components/referrer-detail-page";

export const Route = createFileRoute("/_app/referrals/$customerId")({
  component: RouteComponent,
});

function RouteComponent() {
  const { customerId } = Route.useParams();
  const navigate = Route.useNavigate();
  return (
    <ReferrerDetailPage
      customerId={customerId}
      onBack={() => void navigate({ to: "/referrals" })}
    />
  );
}
