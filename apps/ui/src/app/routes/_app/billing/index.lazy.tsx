import { createLazyFileRoute } from "@tanstack/react-router";
import { DefaultMarginPage } from "@/features/billing/components/default-margin-page";

export const Route = createLazyFileRoute("/_app/billing/")({
  component: DefaultMarginPage,
});
