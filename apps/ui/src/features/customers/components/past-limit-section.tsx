// Past-limit report: per-customer stop episodes with the events that landed
// past each stop, itemized in both denominations (billed + provider cost).

import * as React from "react";
import { Link } from "@tanstack/react-router";
import { ChevronDown, ChevronRight, ShieldCheck } from "lucide-react";

import { EmptyState } from "@/components/shared/empty-state";
import { ErrorCard } from "@/components/shared/error-card";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useTenantCurrency } from "@/hooks/use-tenant-config";
import { formatDate, formatMicros } from "@/lib/format";
import { pastLimitFamilyLabel, stopReasonLabel, stopScopeLabel } from "@/lib/labels";

import { usePastLimitReport } from "../api/queries";
import type { PastLimitEpisode } from "../api/types";
import { shortId } from "../lib/helpers";

export function PastLimitSection({ customerId }: { customerId: string }) {
  const query = usePastLimitReport(customerId);
  const currency = useTenantCurrency();

  return (
    <Card>
      <CardHeader>
        <CardTitle>Past-limit report</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {query.isLoading ? (
          <Skeleton className="h-32 w-full" />
        ) : query.isError ? (
          <ErrorCard error={query.error} onRetry={() => void query.refetch()} />
        ) : !query.data || query.data.episodes.length === 0 ? (
          <EmptyState
            icon={ShieldCheck}
            title="No past-limit activity"
            description="When a balance-floor stop or task kill trips, the events that still landed past it appear here."
          />
        ) : (
          <>
            {query.data.billing_owner_id !== query.data.customer_id && (
              <p className="text-[11px] text-text-muted">
                This seat is funded by billing owner{" "}
                <span className="font-mono">{shortId(query.data.billing_owner_id)}</span>{" "}
                — episodes belong to the owner; itemized events are this seat's.
              </p>
            )}
            <div className="space-y-2">
              {query.data.episodes.map((episode, index) => (
                <EpisodeRow
                  key={index}
                  episode={episode}
                  currency={currency}
                  customerId={customerId}
                />
              ))}
            </div>
            {Object.keys(query.data.totals_per_limit).length > 0 && (
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Totals per limit</TableHead>
                      <TableHead className="text-right">Events</TableHead>
                      <TableHead className="text-right">Billed</TableHead>
                      <TableHead className="text-right">Provider cost</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {Object.entries(query.data.totals_per_limit).map(
                      ([limit, totals]) => (
                        <TableRow key={limit}>
                          <TableCell>{stopReasonLabel(limit)}</TableCell>
                          <TableCell className="text-right tabular-nums">
                            {totals.event_count.toLocaleString()}
                          </TableCell>
                          <TableCell className="text-right tabular-nums">
                            {formatMicros(totals.billed_cost_micros, currency)}
                          </TableCell>
                          <TableCell className="text-right tabular-nums">
                            {formatMicros(totals.provider_cost_micros, currency)}
                          </TableCell>
                        </TableRow>
                      ),
                    )}
                  </TableBody>
                </Table>
              </div>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}

function EpisodeRow({
  episode,
  currency,
  customerId,
}: {
  episode: PastLimitEpisode;
  currency: string;
  customerId: string;
}) {
  const [open, setOpen] = React.useState(false);
  const isSoftFloor = episode.family === "soft_floor";
  const expandable = !isSoftFloor && episode.events.length > 0;

  return (
    <div className="rounded-md border border-border">
      <button
        type="button"
        className="flex w-full flex-wrap items-center gap-x-3 gap-y-1 px-3 py-2 text-left"
        onClick={() => expandable && setOpen((current) => !current)}
        aria-expanded={expandable ? open : undefined}
        disabled={!expandable}
      >
        {expandable &&
          (open ? (
            <ChevronDown className="h-3.5 w-3.5 shrink-0 text-text-muted" />
          ) : (
            <ChevronRight className="h-3.5 w-3.5 shrink-0 text-text-muted" />
          ))}
        <Badge variant="outline">{pastLimitFamilyLabel(episode.family)}</Badge>
        {episode.limit !== null && (
          <Badge variant="secondary">{stopReasonLabel(episode.limit)}</Badge>
        )}
        <span className="text-[11px] text-text-muted">
          Scope: {stopScopeLabel(episode.stop_scope)}
          {episode.episode_seq !== null && ` · episode #${episode.episode_seq}`}
          {episode.task_id !== null && (
            <span className="font-mono"> · task {shortId(episode.task_id)}</span>
          )}
        </span>
        <span className="text-[12px] text-text-secondary">
          {episode.tripped_at ? formatDate(episode.tripped_at) : "—"} →{" "}
          {episode.resumed_at
            ? formatDate(episode.resumed_at)
            : episode.family === "task"
              ? "terminal (task kills don't resume)"
              : "not resumed"}
        </span>
        {isSoftFloor ? (
          <span className="ml-auto text-[11px] text-text-muted">
            Crossed/cleared marker — soft floors never tag events.
          </span>
        ) : (
          <span className="ml-auto text-[12px] tabular-nums text-text-secondary">
            {episode.event_count.toLocaleString()} events ·{" "}
            {formatMicros(episode.total_billed_cost_micros, currency)} billed ·{" "}
            {formatMicros(episode.total_provider_cost_micros, currency)} cost
          </span>
        )}
      </button>
      {open && expandable && (
        <div className="overflow-x-auto border-t border-border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Event</TableHead>
                <TableHead>Effective at</TableHead>
                <TableHead>Arrival</TableHead>
                <TableHead className="text-right">Billed</TableHead>
                <TableHead className="text-right">Provider cost</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {episode.events.map((event) => (
                <TableRow key={event.event_id}>
                  <TableCell>
                    <Link
                      to="/events/$eventId"
                      params={{ eventId: event.event_id }}
                      // customer_id in search keeps the receipt's Refund
                      // action available (the event body carries no owner id).
                      search={{ customer_id: customerId }}
                      className="font-mono text-[12px] underline-offset-2 hover:underline"
                      title={event.event_id}
                    >
                      {shortId(event.event_id)}
                    </Link>
                  </TableCell>
                  <TableCell className="text-[12px]">
                    {formatDate(event.effective_at)}
                  </TableCell>
                  <TableCell>
                    <Badge variant={event.arrived_after ? "secondary" : "outline"}>
                      {event.arrived_after ? "Late arrival" : "Tipping event"}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {formatMicros(event.billed_cost_micros, currency)}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {formatMicros(event.provider_cost_micros, currency)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  );
}
