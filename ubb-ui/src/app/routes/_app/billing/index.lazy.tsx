import { createLazyFileRoute } from "@tanstack/react-router";
import { MarginPage } from "@/features/billing/components/margin-page";

export const Route = createLazyFileRoute("/_app/billing/")({
  component: MarginPage,
});
