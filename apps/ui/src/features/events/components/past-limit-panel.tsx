// Compact past-limit report: per-episode what tripped, when it resumed, and
// what landed past the stop — in both denominations — plus totals per limit.

import { ErrorCard } from "@/components/shared/error-card";
import { Badge } from "@/components/ui/badge";
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
import {
  pastLimitFamilyLabel,
  stopReasonLabel,
  stopScopeLabel,
} from "@/lib/labels";

import { usePastLimitReport } from "../api/queries";
import {
  asPastLimitEpisodes,
  asTotalsPerLimit,
  type PastLimitEpisode,
  type ReportWindow,
} from "../api/types";
import { shortId } from "../lib/search";

function EpisodeRow({
  episode,
  currency,
}: {
  episode: PastLimitEpisode;
  currency: string;
}) {
  if (episode.family === "soft_floor") {
    return (
      <li className="rounded-md bg-bg-subtle px-3 py-2 text-[12px] text-text-secondary">
        Soft floor crossed{" "}
        {episode.tripped_at ? formatDate(episode.tripped_at) : "—"}
        {episode.resumed_at
          ? ` — cleared ${formatDate(episode.resumed_at)}`
          : " — not cleared yet"}
        . New task starts were refused; running work continued, so there are no
        past-limit events for this marker.
      </li>
    );
  }

  const isUnitKill = episode.family === "task";
  return (
    <li className="rounded-md border border-border px-3 py-2.5">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-[13px] font-medium text-text-primary">
          {episode.limit
            ? stopReasonLabel(episode.limit)
            : pastLimitFamilyLabel(episode.family)}
        </span>
        <Badge variant="outline">{stopScopeLabel(episode.stop_scope)}</Badge>
        {episode.episode_seq !== null && (
          <span className="text-[11px] text-text-muted">
            Episode {episode.episode_seq}
          </span>
        )}
        {episode.task_id && (
          <span className="font-mono text-[11px] text-text-muted">
            task {shortId(episode.task_id)}
          </span>
        )}
      </div>
      <div className="mt-1 text-[12px] text-text-secondary">
        Tripped {episode.tripped_at ? formatDate(episode.tripped_at) : "—"}
        {episode.resumed_at
          ? ` → resumed ${formatDate(episode.resumed_at)}`
          : isUnitKill
            ? " → never resumes (kills are final)"
            : " → not resumed yet"}
      </div>
      {episode.provider_cost_limit_micros !== null && (
        <div className="mt-0.5 text-[12px] text-text-secondary">
          The limit was {formatMicros(episode.provider_cost_limit_micros, currency)}{" "}
          of provider cost.
        </div>
      )}
      <div className="mt-1 text-[12px] text-text-primary">
        {episode.event_count} event{episode.event_count === 1 ? "" : "s"} landed
        past the stop · billed{" "}
        {formatMicros(episode.total_billed_cost_micros, currency)} · provider
        cost {formatMicros(episode.total_provider_cost_micros, currency)}
      </div>
    </li>
  );
}

export function PastLimitPanel({
  customerId,
  window,
}: {
  customerId: string;
  window: ReportWindow;
}) {
  const currency = useTenantCurrency();
  const report = usePastLimitReport(customerId, window);

  if (report.isLoading) {
    return <Skeleton className="h-40 w-full rounded-md" />;
  }
  if (report.isError) {
    return (
      <ErrorCard
        error={report.error}
        onRetry={() => void report.refetch()}
        title="Couldn't load the past-limit report"
      />
    );
  }
  const data = report.data;
  if (!data) return null;

  const episodes = asPastLimitEpisodes(data.episodes);
  const totals = asTotalsPerLimit(data.totals_per_limit);

  return (
    <section className="rounded-md border border-border bg-bg-surface p-4">
      <h2 className="text-[13px] font-semibold text-text-primary">
        Past-limit report
      </h2>
      <p className="mt-0.5 text-[12px] text-text-secondary">
        Every stop episode in this window, with what still landed after each
        stop — in both what it cost you and what was billed.
      </p>
      {data.billing_owner_id !== data.customer_id && (
        <p className="mt-1 text-[11px] text-text-muted">
          This customer draws a pooled wallet — episodes belong to billing owner{" "}
          <span className="font-mono">{shortId(data.billing_owner_id)}</span>,
          shown with this customer's events.
        </p>
      )}

      {episodes.length === 0 ? (
        <p className="mt-3 rounded-md bg-bg-subtle px-3 py-2 text-[12px] text-text-secondary">
          No stop episodes in this window — nothing was spent past a limit.
        </p>
      ) : (
        <ul className="mt-3 space-y-2">
          {episodes.map((episode, index) => (
            <EpisodeRow key={index} episode={episode} currency={currency} />
          ))}
        </ul>
      )}

      {totals.length > 0 && (
        <div className="mt-4">
          <h3 className="text-[12px] font-medium text-text-secondary">
            Totals per limit
          </h3>
          <div className="mt-1.5 overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow className="hover:bg-transparent">
                  <TableHead className="text-[11px] text-text-muted">
                    Limit
                  </TableHead>
                  <TableHead className="text-right text-[11px] text-text-muted">
                    Events
                  </TableHead>
                  <TableHead className="text-right text-[11px] text-text-muted">
                    Billed
                  </TableHead>
                  <TableHead className="text-right text-[11px] text-text-muted">
                    Provider cost
                  </TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {totals.map((row) => (
                  <TableRow key={row.limit} className="hover:bg-transparent">
                    <TableCell className="text-[13px]">
                      {stopReasonLabel(row.limit)}
                    </TableCell>
                    <TableCell className="text-right text-[13px] tabular-nums">
                      {row.event_count}
                    </TableCell>
                    <TableCell className="text-right text-[13px] tabular-nums">
                      {formatMicros(row.billed_cost_micros, currency)}
                    </TableCell>
                    <TableCell className="text-right text-[13px] tabular-nums">
                      {formatMicros(row.provider_cost_micros, currency)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </div>
      )}
    </section>
  );
}
