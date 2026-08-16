import { Link } from "@tanstack/react-router";
import { TrendingDown } from "lucide-react";

import { ErrorCard } from "@/components/shared/error-card";
import { formatSignedMicros } from "@/lib/format";
import { marginBound, marginPercentBound } from "@/lib/supplier-cost";

import { useUnprofitable } from "../api/queries";

const MAX_LISTED = 5;

/**
 * Restrained alert listing customers whose margin is below the workspace
 * threshold this period. Renders nothing while loading and nothing when
 * every customer is profitable — absence is the good state.
 */
export function UnprofitableAlert({ currency }: { currency: string }) {
  const query = useUnprofitable();

  if (query.isPending) return null;
  if (query.isError) {
    return (
      <ErrorCard
        error={query.error}
        title="Couldn't check for unprofitable customers"
        onRetry={() => void query.refetch()}
      />
    );
  }

  const rows = query.data.customers;
  if (rows.length === 0) return null;

  const listed = rows.slice(0, MAX_LISTED);
  return (
    <div className="rounded-md border border-border bg-bg-surface p-4">
      <div className="flex items-start gap-3">
        <TrendingDown
          className="mt-0.5 h-4 w-4 shrink-0 text-destructive"
          strokeWidth={1.5}
          aria-hidden="true"
        />
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium text-text-primary">
            {rows.length === 1
              ? "1 customer is unprofitable this period"
              : `${rows.length} customers are unprofitable this period`}
          </p>
          <p className="mt-0.5 text-[12px] text-text-secondary">
            Their margin fell below your workspace margin threshold for this
            period.{" "}
            <Link
              to="/settings"
              className="underline underline-offset-2 hover:text-text-primary"
            >
              Review the threshold in settings
            </Link>
            .
          </p>
          <ul className="mt-2 space-y-1">
            {listed.map((row) => (
              <li
                key={row.customer_id}
                className="flex flex-wrap items-baseline gap-x-3 gap-y-0.5 text-[12px]"
              >
                <Link
                  to="/customers/$customerId"
                  params={{ customerId: row.customer_id }}
                  className="font-mono text-text-primary underline-offset-2 hover:underline"
                >
                  {row.external_id}
                </Link>
                {/* THE SAME ROW'S MARGIN AS THE TABLE ABOVE IT, AND THEY SIT
                    ON ONE PAGE (#330). `/margin/unprofitable` carries its own
                    completeness count, so a customer whose costs are still
                    unresolved has a margin that can only be LOWER than this —
                    and an alert about unprofitability is the last place to
                    overstate it. Rendering the figure here while the economics
                    table renders the bound would be one page disagreeing with
                    itself about one customer. */}
                <span className="text-destructive">
                  {marginBound(
                    row.gross_margin_micros,
                    row,
                    currency,
                    formatSignedMicros,
                  )}{" "}
                  margin
                </span>
                <span className="text-text-muted">
                  {marginPercentBound(row.margin_percentage, row)}
                </span>
              </li>
            ))}
          </ul>
          {rows.length > MAX_LISTED && (
            <p className="mt-1.5 text-[11px] text-text-muted">
              and {rows.length - MAX_LISTED} more — review them on the customers page.
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
