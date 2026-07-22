import { Link } from "@tanstack/react-router";
import { Webhook, Plus, ChevronRight } from "lucide-react";
import { PageHeader } from "@/components/shared/page-header";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { BoolBadge } from "@/components/shared/status-badge";
import {
  LoadingRows,
  ErrorInline,
} from "@/components/shared/data-states";
import { EmptyState } from "@/components/shared/empty-state";
import { CursorPagerControls } from "@/components/shared/cursor-pager";
import { formatShortDate } from "@/lib/format";
import { useWebhookConfigs } from "../api/queries";
import { WebhookFormDialog } from "./webhook-form-dialog";

export function WebhooksPage() {
  const pager = useWebhookConfigs();

  const createButton = (
    <WebhookFormDialog
      trigger={
        <Button size="sm">
          <Plus />
          New endpoint
        </Button>
      }
    />
  );

  return (
    <div className="space-y-6">
      <PageHeader
        title="Webhooks"
        description="Receive signed, real-time notifications when events happen in your account."
        actions={createButton}
      />

      {pager.isLoading ? (
        <LoadingRows />
      ) : pager.isError ? (
        <ErrorInline error={pager.error} onRetry={pager.refetch} />
      ) : pager.items.length === 0 ? (
        <EmptyState
          icon={Webhook}
          title="No webhook endpoints yet"
          description="Add an endpoint to start receiving events like usage.recorded, stop.fired, and invoice.paid."
        />
      ) : (
        <div className="space-y-3">
          <div className="rounded-xl bg-card ring-1 ring-foreground/10">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Endpoint</TableHead>
                  <TableHead>Events</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Created</TableHead>
                  <TableHead className="w-8" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {pager.items.map((cfg) => (
                  <TableRow key={cfg.id} className="cursor-pointer">
                    <TableCell className="max-w-[22rem] truncate font-mono text-xs">
                      <Link
                        to="/webhooks/$configId"
                        params={{ configId: cfg.id }}
                        className="hover:underline"
                      >
                        {cfg.url}
                      </Link>
                    </TableCell>
                    <TableCell>
                      <div className="flex flex-wrap gap-1">
                        {cfg.event_types.slice(0, 3).map((e) => (
                          <Badge key={e} variant="secondary" className="rounded-md font-normal">
                            {e}
                          </Badge>
                        ))}
                        {cfg.event_types.length > 3 && (
                          <span className="text-xs text-muted-foreground">
                            +{cfg.event_types.length - 3}
                          </span>
                        )}
                      </div>
                    </TableCell>
                    <TableCell>
                      <BoolBadge value={cfg.is_active} trueLabel="Active" falseLabel="Paused" />
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {formatShortDate(cfg.created_at)}
                    </TableCell>
                    <TableCell>
                      <Link to="/webhooks/$configId" params={{ configId: cfg.id }}>
                        <ChevronRight className="size-4 text-muted-foreground" />
                      </Link>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
          <CursorPagerControls pager={pager} />
        </div>
      )}
    </div>
  );
}
