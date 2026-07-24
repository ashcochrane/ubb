import { createFileRoute } from "@tanstack/react-router";

import { ReferralsPage } from "@/features/referrals/components/referrals-page";

export const Route = createFileRoute("/_app/referrals/")({
  component: RouteComponent,
});

function RouteComponent() {
  const navigate = Route.useNavigate();
  return (
    <ReferralsPage
      onOpenReferrer={(customerId) =>
        void navigate({ to: "/referrals/$customerId", params: { customerId } })
      }
    />
  );
}
