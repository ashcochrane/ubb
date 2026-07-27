import { createFileRoute } from "@tanstack/react-router";
import { InvoicesPage } from "@/features/billing/components/invoices-page";

export const Route = createFileRoute("/_app/billing/invoices")({
  component: InvoicesPage,
});
