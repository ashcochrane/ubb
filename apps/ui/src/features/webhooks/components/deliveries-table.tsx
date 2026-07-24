import * as React from "react";
import { Check, X } from "lucide-react";

import { EmptyState } from "@/components/shared/empty-state";
import { ErrorCard } from "@/components/shared/error-card";
import { LoadMore } from "@/components/shared/load-more";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { formatDate } from "@/lib/format";
import { webhookEventTypeLabel } from "@/lib/labels";

import { useWebhookDeliveries } from "../api/queries";
import type { WebhookDelivery } from "../api/types";

const TRUNCATE_AT = 64;

function ErrorMessageCell({ message }: { message: string }) {
  const [expanded, setExpanded] = React.useState(false);
  if (!message) return <span className="text-muted-foreground">—</span>;
  const long = message.length > TRUNCATE_AT;
  return (
    <div className="max-w-[360px] whitespace-normal text-xs">
      <span>{expanded || !long ? message : `${message.slice(0, TRUNCATE_AT)}…`}</span>
      {long && (
        <button
          type="button"
          className="ml-1 text-muted-foreground underline underline-offset-2 hover:text-foreground"
          onClick={() => setExpanded((value) => !value)}
        >
          {expanded ? "Less" : "More"}
        </button>
      )}
    </div>
  );
}

function ResultCell({ delivery }: { delivery: WebhookDelivery }) {
  return (
    <div className="flex items-center gap-1.5">
      {delivery.success ? (
        <Check
          className="h-4 w-4 text-foreground"
          strokeWidth={2}
          aria-label="Delivered"
        />
      ) : (
        <X
          className="h-4 w-4 text-destructive"
          strokeWidth={2}
          aria-label="Failed"
        />
      )}
      <span className="font-mono text-xs">
        {delivery.status_code === null || delivery.status_code === undefined
          ? "connection failed"
          : delivery.status_code}
      </span>
    </div>
  );
}

/**
 * The delivery-debugging surface: per-endpoint attempts, newest first.
 * The contract exposes NO payload bodies, per-delivery retry, or replay —
 * this is a read-only ledger of what was attempted and how it went.
 */
export function DeliveriesTable({ configId }: { configId: string }) {
  const deliveries = useWebhookDeliveries(configId);

  if (deliveries.isInitialLoading) {
    return (
      <div className="space-y-2">
        <Skeleton className="h-10 w-full" />
        <Skeleton className="h-10 w-full" />
        <Skeleton className="h-10 w-full" />
      </div>
    );
  }
  if (deliveries.isError) {
    return (
      <ErrorCard error={deliveries.error} onRetry={() => void deliveries.refetch()} />
    );
  }
  if (deliveries.rows.length === 0) {
    return (
      <EmptyState
        title="No deliveries yet"
        description="Deliveries appear when subscribed events fire."
      />
    );
  }

  return (
    <div>
      <div className="overflow-x-auto rounded-lg border border-border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Result</TableHead>
              <TableHead>Event</TableHead>
              <TableHead>Error</TableHead>
              <TableHead>Event ID</TableHead>
              <TableHead>When</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {deliveries.rows.map((delivery) => (
              <TableRow key={delivery.id}>
                <TableCell>
                  <ResultCell delivery={delivery} />
                </TableCell>
                <TableCell className="text-xs">
                  {webhookEventTypeLabel(delivery.event_type)}
                </TableCell>
                <TableCell>
                  <ErrorMessageCell message={delivery.error_message} />
                </TableCell>
                <TableCell>
                  <span
                    className="font-mono text-[11px] text-muted-foreground"
                    title={delivery.event_id}
                  >
                    {delivery.event_id}
                  </span>
                </TableCell>
                <TableCell className="text-xs text-muted-foreground">
                  {formatDate(delivery.created_at)}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
      <LoadMore
        shownCount={deliveries.rows.length}
        hasMore={deliveries.hasMore}
        isFetchingNextPage={deliveries.isFetchingNextPage}
        onLoadMore={deliveries.fetchNextPage}
        noun="deliveries"
      />
    </div>
  );
}
