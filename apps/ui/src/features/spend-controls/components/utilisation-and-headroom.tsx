// Utilisation and headroom: how much of each ceiling the completed work
// used, how much headroom it left, and how often UBB could not tell (#467;
// slice 6 §14, §18). The second report the Spend controls tab hosts, over
// the same customer filter and window as the first — on the instant each
// unit completed.
//
// NO THRESHOLD, NO AMBER, NO WARNING AFFORDANCE (#150 §9.4; #152 §4).
// Enforcement is binary: a ceiling stopped a unit or it did not. So there is
// no meter, no progress bar, no coloured band and no alert on this page —
// figures and words only — and the pool's status pair is rendered the same
// way, without the alert level the pair also carries, because an alert
// level drawn beside a ceiling's utilisation would read as the state v1 has
// none of. The pool's posture is said in a sentence, so a reader can tell
// an alert-only pool past its line from a blocking pool short of it.
//
// EVERY FIGURE THAT CAN BE A BOUND OR AN ABSENCE IS A READING, never a
// coalesced number: a per-unit figure through `@/lib/ceiling`, the
// aggregate and the pool pair through `../lib/utilisation`, so a null
// renders as an absence and an indeterminate contribution renders as "at
// least" / "at most". The two amounts that are always whole where they are
// sent at all — a pinned ceiling, a pool's amount — are null-guarded and
// formatted directly.

import { Link } from "@tanstack/react-router";
import { Gauge } from "lucide-react";

import { CopyButton } from "@/components/shared/copy-button";
import { DetailList } from "@/components/shared/detail-list";
import { EmptyState } from "@/components/shared/empty-state";
import { ErrorCard } from "@/components/shared/error-card";
import { Section } from "@/components/shared/section";
import { StatCard } from "@/components/shared/stat-card";
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
import {
  ceilingStatusLabel,
  describeHeadroom,
  describeUtilisation,
  explainCeiling,
} from "@/lib/ceiling";
import { formatDate, formatMicros, shortId } from "@/lib/format";
import { Reading } from "@/components/shared/reading";
import { ABSENT_LABEL, tenantDefinedLabel } from "@/lib/localisation";
import {
  describePoolHeadroom,
  describePoolUtilisation,
  POOL_AND_WALLET_DIFFER,
  POOL_PAIR_TITLE,
  POOL_POSTURE,
  readPoolCharges,
  STARTS_REFUSED,
  type CustomerSpendPoolStatus,
} from "@/lib/spend-pool";

import { useUtilisationAndHeadroom } from "../api/queries";
import type {
  CeilingUtilisationRow,
  UtilisationAndHeadroom as UtilisationAndHeadroomReport,
  UtilisationAndHeadroomFilters,
} from "../api/types";
import {
  anyIndeterminate,
  AVERAGED_PER_UNIT,
  containedUnit,
  describeAverageHeadroom,
  describeAverageUtilisation,
  describeShare,
  INDETERMINATE_HAS_NO_OTHER_HOME,
  NO_COMPLETED_WORK,
  NOT_APPLICABLE_MEANS,
  REACHED_MEANS,
  readKnownCost,
  readUnitCeiling,
} from "../lib/utilisation";

export const UTILISATION_AND_HEADROOM_TITLE = "Utilisation and headroom";

/** A figure the wire left null, rendered as the absence it is. */
function Absent() {
  return <span className="text-text-muted">{ABSENT_LABEL}</span>;
}

function Aggregate({
  report,
  currency,
}: {
  report: UtilisationAndHeadroomReport;
  currency: string;
}) {
  const utilisation = describeAverageUtilisation(report);
  const headroom = describeAverageHeadroom(report, currency);
  const bounded = anyIndeterminate(report);
  return (
    <div className="space-y-2" data-aggregate-over={report.unit_count}>
      <p className="text-[11px] text-text-muted">
        {report.unit_count.toLocaleString()} completed · {report.evaluated_count.toLocaleString()}{" "}
        evaluated · {report.within_ceiling_count.toLocaleString()} within ceiling ·{" "}
        {report.not_applicable_count.toLocaleString()} not applicable
      </p>
      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label="Average utilisation"
          value={
            <span data-aggregate="average_utilisation" data-bound={bounded ? "floor" : "figure"}>
              {utilisation ?? <Absent />}
            </span>
          }
          subtitle={AVERAGED_PER_UNIT}
        />
        <StatCard
          label="Reached their ceiling"
          value={
            <span data-aggregate="ceiling_reached" data-count={report.ceiling_reached_count}>
              {describeShare(
                report.ceiling_reached_count,
                report.ceiling_reached_share_percentage,
                report.unit_count,
              )}
            </span>
          }
          subtitle={REACHED_MEANS}
        />
        <StatCard
          label="Indeterminate"
          value={
            <span data-aggregate="indeterminate" data-count={report.indeterminate_count}>
              {describeShare(
                report.indeterminate_count,
                report.indeterminate_share_percentage,
                report.unit_count,
              )}
            </span>
          }
          subtitle={INDETERMINATE_HAS_NO_OTHER_HOME}
        />
        <StatCard
          label="Average unused headroom"
          value={
            <span data-aggregate="average_headroom" data-bound={bounded ? "most" : "figure"}>
              {headroom ?? <Absent />}
            </span>
          }
          subtitle={AVERAGED_PER_UNIT}
        />
      </div>
    </div>
  );
}

/**
 * The pool's status pair for the customer the filter names, as words —
 * the same pair the customer's Billing tab renders, read through the same
 * module — and the sentence that keeps it apart from the wallet's
 * affordability.
 */
function PoolPair({ pool, currency }: { pool: CustomerSpendPoolStatus; currency: string }) {
  const used = describePoolUtilisation(pool);
  const headroom = describePoolHeadroom(pool, currency);
  return (
    <section
      aria-label={POOL_PAIR_TITLE}
      className="rounded-md border border-border p-3"
      data-pool-pair={pool.period}
    >
      <div className="flex items-baseline justify-between gap-3">
        <h3 className="text-[12px] font-semibold text-text-primary">{POOL_PAIR_TITLE}</h3>
        <span className="text-[11px] text-text-muted">{pool.period}</span>
      </div>
      <DetailList
        items={[
          {
            label: "Known period charges",
            value: (
              <span>
                <Reading reading={readPoolCharges(pool)} currency={currency} /> of{" "}
                {formatMicros(pool.cap_micros, currency)}
              </span>
            ),
          },
          {
            label: "Used",
            value: (
              <span data-pool-figure="used">{used ?? <Absent />}</span>
            ),
          },
          {
            label: "Headroom",
            value: (
              <span data-pool-figure="headroom">{headroom ?? <Absent />}</span>
            ),
          },
        ]}
      />
      <p className="mt-2 text-[12px] text-text-secondary" data-pool-posture={pool.enforce_mode}>
        {POOL_POSTURE[pool.enforce_mode]}
      </p>
      {pool.blocking_occurred && (
        <p className="mt-1 text-[12px] text-text-primary" data-pool-blocking>
          {STARTS_REFUSED}
        </p>
      )}
      <p className="mt-2 text-[12px] text-text-secondary">{POOL_AND_WALLET_DIFFER}</p>
    </section>
  );
}

function UnitRow({ row, currency }: { row: CeilingUtilisationRow; currency: string }) {
  const reading = readUnitCeiling(row);
  const utilisation = describeUtilisation(reading);
  const headroom = describeHeadroom(reading, currency);
  return (
    <TableRow className="hover:bg-transparent" data-unit={row.task_id}>
      <TableCell className="text-[12px]" data-cell="unit">
        <span className="inline-flex flex-wrap items-center gap-x-2 gap-y-0.5">
          <Link
            to="/tasks/runs/$taskId"
            params={{ taskId: row.task_id }}
            className="font-mono underline-offset-2 hover:underline"
            title={row.task_id}
          >
            {shortId(row.task_id)}
          </Link>
          <span className="text-text-secondary">
            {tenantDefinedLabel(row.task_type)}
            {containedUnit(row) ? " · contained work" : ""}
          </span>
        </span>
      </TableCell>
      <TableCell className="text-[12px]" data-cell="customer">
        <span className="inline-flex items-center gap-1">
          <Link
            to="/customers/$customerId"
            params={{ customerId: row.customer_id }}
            className="font-mono underline-offset-2 hover:underline"
            title={row.customer_id}
          >
            {shortId(row.customer_id)}
          </Link>
          <CopyButton value={row.customer_id} label="Copy customer ID" />
        </span>
      </TableCell>
      <TableCell className="text-[12px] text-text-secondary" data-cell="completed">
        {formatDate(row.completed_at)}
      </TableCell>
      <TableCell className="text-right text-[13px] tabular-nums" data-cell="ceiling">
        {row.task_cogs_ceiling_micros == null ? (
          <Absent />
        ) : (
          formatMicros(row.task_cogs_ceiling_micros, currency)
        )}
      </TableCell>
      <TableCell className="text-right text-[13px] tabular-nums" data-cell="known_cost">
        <Reading reading={readKnownCost(row)} currency={currency} />
      </TableCell>
      <TableCell className="text-right text-[13px] tabular-nums" data-cell="utilisation">
        {utilisation ?? <Absent />}
      </TableCell>
      <TableCell className="text-right text-[13px] tabular-nums" data-cell="headroom">
        {headroom ?? <Absent />}
      </TableCell>
      {/* `data-reading` is the ceiling reading's kind here, as it is on the
          run page; the known-cost cell's is a total reading's. A test scopes
          to the cell before reading either. */}
      <TableCell className="text-[12px]" data-cell="status">
        <span data-reading={row.ceiling_status} title={explainCeiling(reading)}>
          {ceilingStatusLabel(row.ceiling_status)}
        </span>
      </TableCell>
    </TableRow>
  );
}

function CompletedWorkTable({
  rows,
  currency,
}: {
  rows: readonly CeilingUtilisationRow[];
  currency: string;
}) {
  return (
    <div className="overflow-x-auto">
      <Table>
        <TableHeader>
          <TableRow className="hover:bg-transparent">
            <TableHead className="text-[11px] text-text-muted">Unit of work</TableHead>
            <TableHead className="text-[11px] text-text-muted">Customer</TableHead>
            <TableHead className="text-[11px] text-text-muted">Completed</TableHead>
            <TableHead className="text-right text-[11px] text-text-muted">Ceiling</TableHead>
            <TableHead className="text-right text-[11px] text-text-muted">Known cost</TableHead>
            <TableHead className="text-right text-[11px] text-text-muted">Utilisation</TableHead>
            <TableHead className="text-right text-[11px] text-text-muted">Headroom</TableHead>
            <TableHead className="text-[11px] text-text-muted">Status</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((row) => (
            <UnitRow key={row.task_id} row={row} currency={currency} />
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

export function UtilisationAndHeadroom({ filters }: { filters: UtilisationAndHeadroomFilters }) {
  const currency = useTenantCurrency();
  const report = useUtilisationAndHeadroom(filters);

  return (
    <Section
      title={UTILISATION_AND_HEADROOM_TITLE}
      description="How much of its ceiling each completed unit of work used and what headroom it left, averaged per unit and then across every unit — and how often UBB could not tell."
    >
      {report.isLoading ? (
        <Skeleton className="h-40 w-full rounded-md" />
      ) : report.isError ? (
        <ErrorCard
          error={report.error}
          onRetry={() => void report.refetch()}
          title="Couldn't load utilisation and headroom"
        />
      ) : !report.data ? null : (
        <div className="space-y-3">
          <p className="text-[11px] text-text-muted">
            Work that completed between {formatDate(report.data.since)} and{" "}
            {formatDate(report.data.until)}.
          </p>
          {report.data.rows.length > 0 && <Aggregate report={report.data} currency={currency} />}
          {report.data.customer_spend_pool && (
            <PoolPair pool={report.data.customer_spend_pool} currency={currency} />
          )}
          {report.data.rows.length === 0 ? (
            <EmptyState icon={Gauge} title="Nothing to measure" description={NO_COMPLETED_WORK} />
          ) : (
            <>
              <CompletedWorkTable rows={report.data.rows} currency={currency} />
              <p className="text-[11px] text-text-muted">{NOT_APPLICABLE_MEANS}</p>
            </>
          )}
        </div>
      )}
    </Section>
  );
}
