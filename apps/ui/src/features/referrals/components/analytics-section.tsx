import { useState } from "react";

import { DateRangePicker } from "@/components/shared/date-range-picker";
import { EmptyState } from "@/components/shared/empty-state";
import { ErrorCard } from "@/components/shared/error-card";
import { StatCard } from "@/components/shared/stat-card";
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
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
import { resolveRange, type DateRange } from "@/lib/date-range";
import { formatMicros, formatShortDate } from "@/lib/format";

import { useAnalyticsEarnings, useAnalyticsSummary } from "../api/queries";
import { calendarDay, looseDate } from "../lib/dates";

export function AnalyticsSection({
  onOpenReferrer,
}: {
  onOpenReferrer: (customerId: string) => void;
}) {
  const currency = useTenantCurrency();
  const summary = useAnalyticsSummary();
  const [range, setRange] = useState<DateRange>({});
  const resolved = resolveRange(range);
  const earnings = useAnalyticsEarnings({
    period_start: resolved.start_date,
    period_end: resolved.end_date,
  });

  return (
    <div className="space-y-4">
      {summary.isLoading ? (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
          {Array.from({ length: 5 }).map((_, index) => (
            <Skeleton key={index} className="h-[72px] w-full" />
          ))}
        </div>
      ) : summary.isError ? (
        <ErrorCard
          error={summary.error}
          onRetry={() => void summary.refetch()}
          title="Couldn't load referral analytics"
        />
      ) : summary.data ? (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
          <StatCard label="Referrers" value={summary.data.total_referrers.toLocaleString()} />
          <StatCard label="Referrals" value={summary.data.total_referrals.toLocaleString()} />
          <StatCard
            label="Active referrals"
            value={summary.data.active_referrals.toLocaleString()}
          />
          <StatCard
            label="Rewards earned"
            value={formatMicros(summary.data.total_rewards_earned_micros, currency)}
          />
          <StatCard
            label="Referred spend"
            value={formatMicros(summary.data.total_referred_spend_micros, currency)}
          />
        </div>
      ) : null}

      <Card>
        <CardHeader className="border-b">
          <CardTitle>Earnings by period</CardTitle>
          <CardDescription>What each referrer earned inside the selected window.</CardDescription>
          <CardAction>
            <DateRangePicker value={range} onChange={setRange} />
          </CardAction>
        </CardHeader>
        <CardContent className="px-0">
          {earnings.isLoading ? (
            <div className="space-y-2 px-4">
              {Array.from({ length: 3 }).map((_, index) => (
                <Skeleton key={index} className="h-8 w-full" />
              ))}
            </div>
          ) : earnings.isError ? (
            <ErrorCard
              error={earnings.error}
              onRetry={() => void earnings.refetch()}
              title="Couldn't load earnings"
              className="mx-4"
            />
          ) : earnings.data ? (
            earnings.data.referrers.length === 0 ? (
              <EmptyState
                title="No referral earnings in this period"
                description="Try a wider window — or register referrers below and share their codes."
                className="mx-4"
              />
            ) : (
              <>
                <div className="flex flex-wrap items-center justify-between gap-2 px-4 pb-2 text-[12px] text-text-secondary">
                  <span>
                    {looseDate(earnings.data.period_start, (iso) => formatShortDate(calendarDay(iso)))} –{" "}
                    {looseDate(earnings.data.period_end, (iso) => formatShortDate(calendarDay(iso)))}
                  </span>
                  <span>
                    Total earned{" "}
                    <span className="font-semibold text-text-primary">
                      {formatMicros(earnings.data.total_earned_micros, currency)}
                    </span>
                  </span>
                </div>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Referrer</TableHead>
                      <TableHead>Code</TableHead>
                      <TableHead className="text-right">Referrals</TableHead>
                      <TableHead className="text-right">Earned</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {earnings.data.referrers.map((row) => (
                      <TableRow
                        key={row.referrer_customer_id}
                        className="cursor-pointer"
                        onClick={() => onOpenReferrer(row.referrer_customer_id)}
                        onKeyDown={(event) => {
                          if (event.key === "Enter") onOpenReferrer(row.referrer_customer_id);
                        }}
                        tabIndex={0}
                        role="link"
                        aria-label={`Open referrer ${row.external_id}`}
                      >
                        <TableCell>{row.external_id}</TableCell>
                        <TableCell className="font-mono text-[12px]">{row.referral_code}</TableCell>
                        <TableCell className="text-right">
                          {row.referral_count.toLocaleString()}
                        </TableCell>
                        <TableCell className="text-right">
                          {formatMicros(row.total_earned_micros, currency)}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </>
            )
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
}
