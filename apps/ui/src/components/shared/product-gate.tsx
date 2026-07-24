import type { ReactNode } from "react";
import { Link } from "@tanstack/react-router";
import { Lock } from "lucide-react";

import { Skeleton } from "@/components/ui/skeleton";
import { useTenantConfig } from "@/hooks/use-tenant-config";
import { productDescription, productLabel, type Product } from "@/lib/labels";

/**
 * Gate a page (or section) on an enabled tenant product. Direct URL access to
 * a disabled product renders an honest explanation instead of dead controls
 * or a raw 403.
 */
export function ProductGate({
  product,
  children,
}: {
  product: Product;
  children: ReactNode;
}) {
  const { data: config, isLoading } = useTenantConfig();

  if (isLoading) {
    return (
      <div className="space-y-3">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-40 w-full" />
      </div>
    );
  }

  if (!config?.products.includes(product)) {
    return (
      <div className="mx-auto max-w-md rounded-lg border border-border bg-bg-surface p-8 text-center">
        <Lock className="mx-auto h-6 w-6 text-text-muted" strokeWidth={1.5} />
        <h2 className="mt-3 text-base font-semibold text-text-primary">
          {productLabel(product)} isn't enabled
        </h2>
        <p className="mt-2 text-sm text-text-secondary">
          {productDescription(product)}
        </p>
        <p className="mt-4 text-[13px] text-text-muted">
          See{" "}
          <Link to="/settings/products" className="underline hover:text-text-primary">
            Settings → Products
          </Link>{" "}
          for what's enabled in this workspace and how to change it.
        </p>
      </div>
    );
  }

  return <>{children}</>;
}
