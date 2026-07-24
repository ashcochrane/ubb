import * as React from "react";
import { SearchX } from "lucide-react";

import { ConfirmDialog } from "@/components/shared/confirm-dialog";
import { CopyButton } from "@/components/shared/copy-button";
import { DetailList } from "@/components/shared/detail-list";
import { EmptyState } from "@/components/shared/empty-state";
import { ErrorCard } from "@/components/shared/error-card";
import { PageHeader } from "@/components/shared/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useHasRole } from "@/hooks/use-current-role";
import { formatDate } from "@/lib/format";
import { toastOnError, toastSuccess } from "@/lib/mutations";

import {
  useDeleteWebhookConfig,
  useUpdateWebhookConfig,
  useWebhookConfig,
} from "../api/queries";
import type { WebhookConfig } from "../api/types";
import { hostOf } from "../lib/secret";
import { DeliveriesTable } from "./deliveries-table";
import { EditEndpointDialog } from "./edit-endpoint-dialog";
import { RotateSecretDialog } from "./rotate-secret-dialog";
import { SignatureHelp } from "./signature-help";
import { EventTypeChips } from "./webhook-config-table";

function DetailSkeleton() {
  return (
    <div className="space-y-4">
      <Skeleton className="h-8 w-64" />
      <Skeleton className="h-44 w-full" />
      <Skeleton className="h-64 w-full" />
    </div>
  );
}

function ConfigSummary({ config }: { config: WebhookConfig }) {
  return (
    <div className="rounded-lg border border-border px-4 py-1">
      <DetailList
        items={[
          {
            label: "Endpoint URL",
            value: (
              <span className="inline-flex max-w-full items-center gap-1.5">
                <span className="truncate" title={config.url}>
                  {config.url}
                </span>
                <CopyButton value={config.url} />
              </span>
            ),
            mono: true,
          },
          {
            label: "Endpoint ID",
            value: (
              <span className="inline-flex items-center gap-1.5">
                {config.id}
                <CopyButton value={config.id} />
              </span>
            ),
            mono: true,
          },
          {
            label: "Status",
            value: config.is_active ? (
              <Badge variant="outline">Active</Badge>
            ) : (
              <Badge variant="secondary">Paused</Badge>
            ),
          },
          {
            label: "Subscribed events",
            value: <EventTypeChips eventTypes={config.event_types} />,
          },
          {
            label: "Signing secret",
            value:
              "Write-only — UBB never displays it. Rotate to replace it.",
          },
          ...(config.retiring_secret_expires_at
            ? [
                {
                  label: "Secret rotation",
                  value: `Both secrets sign until ${formatDate(config.retiring_secret_expires_at)}`,
                },
              ]
            : []),
          { label: "Created", value: formatDate(config.created_at) },
        ]}
      />
    </div>
  );
}

export function WebhookDetailPage({
  configId,
  onBack,
}: {
  configId: string;
  onBack: () => void;
}) {
  const lookup = useWebhookConfig(configId);
  const update = useUpdateWebhookConfig();
  const del = useDeleteWebhookConfig();
  // UI affordance only (fail-open) — the server enforces the Admin floor.
  const isAdmin = useHasRole("admin");

  const [editOpen, setEditOpen] = React.useState(false);
  const [rotateOpen, setRotateOpen] = React.useState(false);
  const [deleteOpen, setDeleteOpen] = React.useState(false);

  if (lookup.isLoading) return <DetailSkeleton />;
  if (lookup.isError) {
    return <ErrorCard error={lookup.error} onRetry={lookup.refetch} />;
  }
  const config = lookup.config;
  if (!config) {
    return (
      <EmptyState
        icon={SearchX}
        title="Endpoint not found"
        description="This webhook endpoint doesn't exist — it may have been deleted."
        action={{ label: "Back to webhooks", onClick: onBack }}
      />
    );
  }

  const adminTitle = (label: string) =>
    isAdmin ? undefined : `${label} requires the Admin role`;

  const togglePause = () => {
    const next = !config.is_active;
    update.mutate(
      { configId: config.id, body: { is_active: next } },
      {
        onSuccess: () =>
          toastSuccess(next ? "Endpoint resumed" : "Endpoint paused", config.url),
        onError: toastOnError(
          next ? "Couldn't resume the endpoint" : "Couldn't pause the endpoint",
        ),
      },
    );
  };

  return (
    <div className="space-y-4">
      <PageHeader
        title={hostOf(config.url)}
        description="Webhook endpoint"
        actions={
          <>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setEditOpen(true)}
              disabled={!isAdmin}
              title={adminTitle("Editing")}
            >
              Edit
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={togglePause}
              disabled={!isAdmin || update.isPending}
              title={adminTitle("Pausing and resuming")}
            >
              {update.isPending ? "Working…" : config.is_active ? "Pause" : "Resume"}
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setRotateOpen(true)}
              disabled={!isAdmin}
              title={adminTitle("Rotating the secret")}
            >
              Rotate secret
            </Button>
            <Button
              variant="destructive"
              size="sm"
              onClick={() => setDeleteOpen(true)}
              disabled={!isAdmin}
              title={adminTitle("Deleting")}
            >
              Delete
            </Button>
          </>
        }
      />

      <ConfigSummary config={config} />

      <Tabs defaultValue="deliveries">
        <TabsList>
          <TabsTrigger value="deliveries">Deliveries</TabsTrigger>
          <TabsTrigger value="signatures">Verifying signatures</TabsTrigger>
        </TabsList>
        <TabsContent value="deliveries">
          <DeliveriesTable configId={config.id} />
        </TabsContent>
        <TabsContent value="signatures">
          <SignatureHelp />
        </TabsContent>
      </Tabs>

      <EditEndpointDialog config={config} open={editOpen} onOpenChange={setEditOpen} />
      <RotateSecretDialog
        configId={config.id}
        open={rotateOpen}
        onOpenChange={setRotateOpen}
      />
      <ConfirmDialog
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        title="Delete webhook endpoint"
        description={`Deliveries to ${config.url} stop immediately and its delivery history goes with it. This can't be undone — re-adding the endpoint means supplying a new secret.`}
        confirmLabel="Delete endpoint"
        destructive
        typeToConfirm={hostOf(config.url)}
        pending={del.isPending}
        onConfirm={() =>
          del.mutate(
            { configId: config.id },
            {
              onSuccess: () => {
                toastSuccess("Endpoint deleted", config.url);
                setDeleteOpen(false);
                onBack();
              },
              onError: toastOnError("Couldn't delete the endpoint"),
            },
          )
        }
      />
    </div>
  );
}
