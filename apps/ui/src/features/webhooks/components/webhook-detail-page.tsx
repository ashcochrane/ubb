import { useNavigate } from "@tanstack/react-router";
import {
  ArrowLeft,
  Pencil,
  KeyRound,
  Trash2,
  Power,
  CheckCircle2,
  XCircle,
} from "lucide-react";
import { PageHeader } from "@/components/shared/page-header";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from "@/components/ui/table";
import {
  QueryState,
  Section,
  DetailGrid,
  DetailRow,
  LoadingRows,
  ErrorInline,
} from "@/components/shared/data-states";
import { EmptyState } from "@/components/shared/empty-state";
import { StatusBadge, BoolBadge } from "@/components/shared/status-badge";
import { CursorPagerControls } from "@/components/shared/cursor-pager";
import { ConfirmDialog } from "@/components/shared/confirm-dialog";
import { formatDate, formatShortDate } from "@/lib/format";
import {
  useWebhookConfig,
  useWebhookDeliveries,
  useUpdateWebhook,
  useDeleteWebhook,
} from "../api/queries";
import { WebhookFormDialog } from "./webhook-form-dialog";
import { RotateSecretDialog } from "./rotate-secret-dialog";

export function WebhookDetailPage({ configId }: { configId: string }) {
  const navigate = useNavigate();
  const query = useWebhookConfig(configId);
  const update = useUpdateWebhook(configId);
  const del = useDeleteWebhook();

  return (
    <div className="space-y-6">
      <PageHeader
        title="Webhook endpoint"
        actions={
          <Button
            variant="ghost"
            size="sm"
            onClick={() => navigate({ to: "/webhooks" })}
          >
            <ArrowLeft />
            Back
          </Button>
        }
      />

      <QueryState
        query={query}
        isEmpty={(c) => c === null}
        empty={{
          title: "Endpoint not found",
          description: "It may have been deleted, or it lives beyond the first page of endpoints.",
        }}
      >
        {(cfg) =>
          cfg && (
            <div className="space-y-6">
              <Section
                title="Configuration"
                actions={
                  <div className="flex items-center gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={update.isPending}
                      onClick={() =>
                        update.mutate({ is_active: !cfg.is_active })
                      }
                    >
                      <Power />
                      {cfg.is_active ? "Pause" : "Activate"}
                    </Button>
                    <RotateSecretDialog
                      configId={cfg.id}
                      trigger={
                        <Button variant="outline" size="sm">
                          <KeyRound />
                          Rotate secret
                        </Button>
                      }
                    />
                    <WebhookFormDialog
                      existing={cfg}
                      trigger={
                        <Button variant="outline" size="sm">
                          <Pencil />
                          Edit
                        </Button>
                      }
                    />
                    <ConfirmDialog
                      destructive
                      title="Delete this endpoint?"
                      description="Deliveries to this URL will stop immediately. This can't be undone."
                      confirmLabel="Delete endpoint"
                      onConfirm={async () => {
                        await del.mutateAsync(cfg.id);
                        navigate({ to: "/webhooks" });
                      }}
                      trigger={
                        <Button variant="destructive" size="sm">
                          <Trash2 />
                          Delete
                        </Button>
                      }
                    />
                  </div>
                }
              >
                <DetailGrid>
                  <DetailRow label="Endpoint URL">
                    <span className="font-mono text-xs break-all">{cfg.url}</span>
                  </DetailRow>
                  <DetailRow label="Status">
                    <BoolBadge value={cfg.is_active} trueLabel="Active" falseLabel="Paused" />
                  </DetailRow>
                  <DetailRow label="Created">{formatDate(cfg.created_at)}</DetailRow>
                  <DetailRow label="Retiring secret expires">
                    {cfg.retiring_secret_expires_at
                      ? formatDate(cfg.retiring_secret_expires_at)
                      : "—"}
                  </DetailRow>
                  <DetailRow label="Subscribed events">
                    <div className="flex flex-wrap gap-1">
                      {cfg.event_types.map((e) => (
                        <Badge key={e} variant="secondary" className="rounded-md font-normal">
                          {e}
                        </Badge>
                      ))}
                    </div>
                  </DetailRow>
                </DetailGrid>
              </Section>

              <DeliveriesSection configId={cfg.id} />
            </div>
          )
        }
      </QueryState>
    </div>
  );
}

function DeliveriesSection({ configId }: { configId: string }) {
  const pager = useWebhookDeliveries(configId);
  return (
    <Section
      title="Recent deliveries"
      description="The most recent delivery attempts, newest first."
    >
      {pager.isLoading ? (
        <LoadingRows rows={4} />
      ) : pager.isError ? (
        <ErrorInline error={pager.error} onRetry={pager.refetch} />
      ) : pager.items.length === 0 ? (
        <EmptyState
          title="No deliveries yet"
          description="Once a subscribed event fires, its delivery attempts appear here."
        />
      ) : (
        <div className="space-y-3">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-8" />
                <TableHead>Event</TableHead>
                <TableHead>Result</TableHead>
                <TableHead>Response</TableHead>
                <TableHead>When</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {pager.items.map((d) => (
                <TableRow key={d.id}>
                  <TableCell>
                    {d.success ? (
                      <CheckCircle2 className="size-4 text-foreground" />
                    ) : (
                      <XCircle className="size-4 text-destructive" />
                    )}
                  </TableCell>
                  <TableCell>
                    <div className="font-medium">{d.event_type}</div>
                    <div className="font-mono text-xs text-muted-foreground">{d.event_id}</div>
                  </TableCell>
                  <TableCell>
                    <StatusBadge
                      value={d.success ? "Delivered" : "Failed"}
                      tone={d.success ? "solid" : "danger"}
                    />
                  </TableCell>
                  <TableCell>
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-xs">
                        {d.status_code ?? "—"}
                      </span>
                      {!d.success && d.error_message && (
                        <span className="max-w-[16rem] truncate text-xs text-muted-foreground" title={d.error_message}>
                          {d.error_message}
                        </span>
                      )}
                    </div>
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {formatShortDate(d.created_at)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          <CursorPagerControls pager={pager} />
        </div>
      )}
    </Section>
  );
}
