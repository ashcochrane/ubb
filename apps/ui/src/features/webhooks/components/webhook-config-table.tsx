import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { toastOnError, toastSuccess } from "@/lib/mutations";
import { webhookEventTypeLabel } from "@/lib/labels";
import { formatDate, formatShortDate } from "@/lib/format";

import { useUpdateWebhookConfig } from "../api/queries";
import type { WebhookConfig } from "../api/types";

/** First two event chips + "+N more"; "*" renders as a single "All events". */
export function EventTypeChips({ eventTypes }: { eventTypes: string[] }) {
  if (eventTypes.includes("*")) {
    return <Badge variant="secondary">All events</Badge>;
  }
  const shown = eventTypes.slice(0, 2);
  const rest = eventTypes.slice(2);
  return (
    <div className="flex flex-wrap items-center gap-1">
      {shown.map((eventType) => (
        <Badge key={eventType} variant="outline">
          {webhookEventTypeLabel(eventType)}
        </Badge>
      ))}
      {rest.length > 0 && (
        <Badge
          variant="secondary"
          title={rest.map(webhookEventTypeLabel).join(", ")}
        >
          +{rest.length} more
        </Badge>
      )}
    </div>
  );
}

export function RotationBadge({ expiresAt }: { expiresAt: string | null | undefined }) {
  if (!expiresAt) return null;
  return (
    <Badge
      variant="outline"
      title={`Secret rotation in progress — the old secret keeps signing until ${formatDate(expiresAt)}`}
    >
      Rotating secret
    </Badge>
  );
}

export function WebhookConfigTable({
  rows,
  onOpenConfig,
  canManage,
}: {
  rows: WebhookConfig[];
  onOpenConfig: (configId: string) => void;
  canManage: boolean;
}) {
  const update = useUpdateWebhookConfig();

  const toggleActive = (config: WebhookConfig, next: boolean) => {
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
    <div className="overflow-x-auto rounded-lg border border-border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Endpoint</TableHead>
            <TableHead>Events</TableHead>
            <TableHead>Active</TableHead>
            <TableHead>Created</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((config) => {
            const rowPending =
              update.isPending && update.variables?.configId === config.id;
            return (
              <TableRow
                key={config.id}
                className="cursor-pointer"
                onClick={() => onOpenConfig(config.id)}
                // Enter only when the row itself is focused, so the inner
                // pause/resume switch never doubles as navigation.
                onKeyDown={(event) => {
                  if (event.key === "Enter" && event.target === event.currentTarget) {
                    onOpenConfig(config.id);
                  }
                }}
                tabIndex={0}
                role="link"
                aria-label={`Open endpoint ${config.url}`}
              >
                <TableCell>
                  <div className="flex items-center gap-2">
                    <span
                      className="max-w-[320px] truncate font-mono text-xs"
                      title={config.url}
                    >
                      {config.url}
                    </span>
                    <RotationBadge expiresAt={config.retiring_secret_expires_at} />
                  </div>
                </TableCell>
                <TableCell>
                  <EventTypeChips eventTypes={config.event_types} />
                </TableCell>
                <TableCell>
                  {/* Stop the row click so the switch doesn't also navigate. */}
                  <div
                    onClick={(event) => event.stopPropagation()}
                    className="inline-flex"
                  >
                    <Switch
                      checked={config.is_active}
                      disabled={!canManage || rowPending}
                      onCheckedChange={(next) => toggleActive(config, next)}
                      aria-label={
                        config.is_active
                          ? `Pause ${config.url}`
                          : `Resume ${config.url}`
                      }
                    />
                  </div>
                </TableCell>
                <TableCell className="text-xs text-muted-foreground">
                  {formatShortDate(config.created_at)}
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}
