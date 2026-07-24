import * as React from "react";
import { Webhook } from "lucide-react";

import { EmptyState } from "@/components/shared/empty-state";
import { ErrorCard } from "@/components/shared/error-card";
import { LoadMore } from "@/components/shared/load-more";
import { PageHeader } from "@/components/shared/page-header";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useHasRole } from "@/hooks/use-current-role";

import { useWebhookConfigs } from "../api/queries";
import { CreateEndpointDialog } from "./create-endpoint-dialog";
import { WebhookConfigTable } from "./webhook-config-table";

export function WebhooksPage({
  onOpenConfig,
}: {
  onOpenConfig: (configId: string) => void;
}) {
  const configs = useWebhookConfigs();
  const [createOpen, setCreateOpen] = React.useState(false);
  // UI affordance only (fail-open) — the server enforces the Admin floor.
  const isAdmin = useHasRole("admin");

  return (
    <div className="space-y-4">
      <PageHeader
        title="Webhooks"
        description="UBB POSTs signed event notifications to your endpoints as things happen."
        actions={
          <Button
            onClick={() => setCreateOpen(true)}
            disabled={!isAdmin}
            title={isAdmin ? undefined : "Adding endpoints requires the Admin role"}
          >
            Add endpoint
          </Button>
        }
      />

      {configs.isInitialLoading ? (
        <div className="space-y-2">
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-10 w-full" />
        </div>
      ) : configs.isError ? (
        <ErrorCard error={configs.error} onRetry={() => void configs.refetch()} />
      ) : configs.rows.length === 0 ? (
        <EmptyState
          icon={Webhook}
          title="No webhook endpoints"
          description="Add an endpoint to get notified when things happen — balance alerts, stops, invoice pushes, and more."
          action={{ label: "Add endpoint", onClick: () => setCreateOpen(true) }}
        />
      ) : (
        <div>
          <WebhookConfigTable
            rows={configs.rows}
            onOpenConfig={onOpenConfig}
            canManage={isAdmin}
          />
          <LoadMore
            shownCount={configs.rows.length}
            hasMore={configs.hasMore}
            isFetchingNextPage={configs.isFetchingNextPage}
            onLoadMore={configs.fetchNextPage}
            noun="endpoints"
          />
        </div>
      )}

      <CreateEndpointDialog open={createOpen} onOpenChange={setCreateOpen} />
    </div>
  );
}
