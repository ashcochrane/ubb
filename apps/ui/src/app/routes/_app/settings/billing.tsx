import { createFileRoute } from "@tanstack/react-router";
import { TenantBillingPage } from "@/features/settings/components/tenant-billing-page";

export const Route = createFileRoute("/_app/settings/billing")({
  component: TenantBillingPage,
});
