import { createFileRoute } from "@tanstack/react-router";
import { CustomerMappingPage } from "@/features/customers/components/customer-mapping-page";

export const Route = createFileRoute("/_app/customers/")({
  component: CustomerMappingPage,
});
