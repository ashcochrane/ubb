import { Skeleton } from "@/components/ui/skeleton";
import { ErrorCard } from "@/components/shared/error-card";
import { useHasRole } from "@/hooks/use-current-role";

import { useSettingsTenantConfig } from "../api/queries";
import { CostTaxCard } from "./cost-tax-card";
import { MarginAlertCard } from "./margin-alert-card";
import { SpendControlCard } from "./spend-control-card";
import { StripeConnectCard } from "./stripe-connect-card";
import { WorkspaceCard } from "./workspace-card";

export interface WorkspaceSettingsPageProps {
  /** Stripe OAuth return marker from the URL (?connected=true|false). */
  connected?: string;
  onClearConnected?: () => void;
}

export function WorkspaceSettingsPage({
  connected,
  onClearConnected,
}: WorkspaceSettingsPageProps) {
  const config = useSettingsTenantConfig();
  const isAdmin = useHasRole("admin");

  if (config.isLoading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-48 w-full" />
        <Skeleton className="h-40 w-full" />
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

  const cfg = config.data;
  const showConnect = cfg.products.includes("billing");

  return (
    <div className="max-w-3xl space-y-6">
      {!isAdmin && (
        <p className="text-[13px] text-muted-foreground">
          You can review these settings, but changing them requires the Admin
          role.
        </p>
      )}
      <WorkspaceCard config={cfg} isAdmin={isAdmin} />
      <CostTaxCard config={cfg} isAdmin={isAdmin} />
      <SpendControlCard config={cfg} isAdmin={isAdmin} />
      <MarginAlertCard isAdmin={isAdmin} />
      {showConnect && (
        <StripeConnectCard
          isAdmin={isAdmin}
          connectedParam={connected}
          onClearConnected={onClearConnected}
        />
      )}
    </div>
  );
}
