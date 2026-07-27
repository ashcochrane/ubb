import { Skeleton } from "@/components/ui/skeleton";
import { ErrorCard } from "@/components/shared/error-card";
import { useHasRole } from "@/hooks/use-current-role";

import { useSettingsTenantConfig } from "../api/queries";
import { BillingModeCard } from "./billing-mode-card";
import { PrerequisitesCard } from "./prerequisites-card";
import { ProductsCard } from "./products-card";

export function ProductsPage() {
  const config = useSettingsTenantConfig();
  const isAdmin = useHasRole("admin");

  if (config.isLoading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-56 w-full" />
        <Skeleton className="h-72 w-full" />
      </div>
    );
  }

  if (config.isError || !config.data) {
    return (
      <ErrorCard
        error={config.error}
        onRetry={() => void config.refetch()}
        title="Couldn't load the workspace configuration"
      />
    );
  }

  return (
    <div className="max-w-3xl space-y-6">
      {!isAdmin && (
        <p className="text-[13px] text-muted-foreground">
          You can review what's enabled, but changing it requires the Admin
          role.
        </p>
      )}
      <BillingModeCard config={config.data} isAdmin={isAdmin} />
      <ProductsCard config={config.data} isAdmin={isAdmin} />
      <PrerequisitesCard config={config.data} />
    </div>
  );
}
