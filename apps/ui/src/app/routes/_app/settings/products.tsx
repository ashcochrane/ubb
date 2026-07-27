import { createFileRoute } from "@tanstack/react-router";
import { ProductsPage } from "@/features/settings/components/products-page";

export const Route = createFileRoute("/_app/settings/products")({
  component: ProductsPage,
});
