import { createFileRoute } from "@tanstack/react-router";
import { PricingPage } from "@/features/pricing/components/pricing-page";

export const Route = createFileRoute("/_app/pricing/")({
  component: PricingPage,
});
