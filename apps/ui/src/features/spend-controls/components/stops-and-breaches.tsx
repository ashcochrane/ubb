// Stops and breaches: what was spent past a stop, and why — one rendering,
// two hosts (#466; slice 6 §14, §18). The Spend controls tab renders it
// tenant-wide with the customer and family filters; the customer's Usage tab
// renders THIS component with the customer filter fixed, injected through the
// customer route because a feature may not import another's components. The
// filters are the route's own and the server applies them; what this
// component owns is the rendering and the empty answer's sentence.
//
// `admission_control` RENDERS AS NO ROWS, NEVER AS A DEFECT (spec §6): a
// refused start spent nothing, so the family has nothing to itemise, and the
// empty state says so in its own sentence rather than the ordinary one.

import { ShieldCheck } from "lucide-react";

import { EmptyState } from "@/components/shared/empty-state";
import { ErrorCard } from "@/components/shared/error-card";
import { Section } from "@/components/shared/section";
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
import { formatDate } from "@/lib/format";
import { describeTotal } from "@/lib/total-reading";

import { useStopsAndBreaches } from "../api/queries";
import type { FamilyTotalsRow, StopsAndBreachesFilters } from "../api/types";
import { readItemisedCost, readItemisedPrice } from "../lib/episodes";
import { controlFamilyLabel, NO_EPISODES_FOR } from "../lib/families";
import { EpisodeCard } from "./episode-card";

export const STOPS_AND_BREACHES_TITLE = "Stops and breaches";

/** The ordinary empty answer, for no family filter: nothing fired in the window. */
export const NO_EPISODES = "No spend control fired and stopped work in this window.";

function FamilyTotalsTable({
  totals,
  currency,
}: {
  totals: readonly FamilyTotalsRow[];
  currency: string;
}) {
  return (
    <div className="overflow-x-auto">
      <Table>
        <TableHeader>
          <TableRow className="hover:bg-transparent">
            <TableHead className="text-[11px] text-text-muted">Totals per family</TableHead>
            <TableHead className="text-right text-[11px] text-text-muted">Events</TableHead>
            <TableHead className="text-right text-[11px] text-text-muted">Billed</TableHead>
            <TableHead className="text-right text-[11px] text-text-muted">
              Provider cost
            </TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {totals.map((row) => (
            <TableRow
              key={row.control_family}
              className="hover:bg-transparent"
              data-family={row.control_family}
            >
              <TableCell className="text-[13px]">
                {controlFamilyLabel(row.control_family)}
              </TableCell>
              <TableCell className="text-right text-[13px] tabular-nums">
                {row.event_count.toLocaleString()}
              </TableCell>
              {/* Each total is over exactly the itemised events of the rows
                  shown, each event once per family, and each is a floor
                  wherever those events hold an amount UBB never resolved. */}
              <TableCell className="text-right text-[13px] tabular-nums">
                {describeTotal(readItemisedPrice(row), currency)}
              </TableCell>
              <TableCell className="text-right text-[13px] tabular-nums">
                {describeTotal(readItemisedCost(row), currency)}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

export function StopsAndBreaches({ filters }: { filters: StopsAndBreachesFilters }) {
  const currency = useTenantCurrency();
  const report = useStopsAndBreaches(filters);
  const family = filters.control_family;

  return (
    <Section
      title={STOPS_AND_BREACHES_TITLE}
      description="Every spend control that fired and stopped work, with what still landed after each stop — in what it cost you and in what was billed."
    >
      {report.isLoading ? (
        <Skeleton className="h-40 w-full rounded-md" />
      ) : report.isError ? (
        <ErrorCard
          error={report.error}
          onRetry={() => void report.refetch()}
          title="Couldn't load stops and breaches"
        />
      ) : !report.data ? null : (
        <div className="space-y-3">
          <p className="text-[11px] text-text-muted">
            Episodes that opened between {formatDate(report.data.since)} and{" "}
            {formatDate(report.data.until)}.
          </p>
          {report.data.rows.length === 0 ? (
            <EmptyState
              icon={ShieldCheck}
              title="Nothing to itemise"
              description={family === undefined ? NO_EPISODES : NO_EPISODES_FOR[family]}
            />
          ) : (
            <>
              <div className="space-y-2">
                {report.data.rows.map((row, index) => (
                  <EpisodeCard key={`${row.control_family}-${index}`} row={row} currency={currency} />
                ))}
              </div>
              {report.data.totals.length > 0 && (
                <FamilyTotalsTable totals={report.data.totals} currency={currency} />
              )}
            </>
          )}
        </div>
      )}
    </Section>
  );
}
