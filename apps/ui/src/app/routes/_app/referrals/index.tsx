import { createFileRoute } from "@tanstack/react-router";
import { ReferralsPage } from "@/features/referrals/components/referrals-page";

export const Route = createFileRoute("/_app/referrals/")({
  component: ReferralsPage,
});
