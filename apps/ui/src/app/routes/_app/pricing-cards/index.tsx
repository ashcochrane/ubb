import { createFileRoute } from "@tanstack/react-router";
import { PricingCardsPage } from "@/features/pricing-cards/components/pricing-cards-page";

export const Route = createFileRoute("/_app/pricing-cards/")({
  component: PricingCardsPage,
});
