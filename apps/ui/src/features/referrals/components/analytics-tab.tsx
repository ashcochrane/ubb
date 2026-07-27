import { useState } from "react";
import { StatCard } from "@/components/shared/stat-card";
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from "@/components/ui/table";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Section,
  QueryState,
  LoadingRows,
  CopyField,
} from "@/components/shared/data-states";
import { formatMicros, formatEventCount } from "@/lib/format";
import { useAuth } from "@/features/auth/hooks/use-auth";
import { useAnalyticsSummary, useAnalyticsEarnings } from "../api/queries";

export function AnalyticsTab() {
  return (
    <div className="space-y-6">
      <SummaryCards />
      <EarningsByPeriod />
    </div>
  );
}

function SummaryCards() {
  const { defaultCurrency } = useAuth();
  const query = useAnalyticsSummary();

  if (query.isLoading) return <LoadingRows rows={2} />;

  return (
    <QueryState query={query}>
      {(s) => (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
          <StatCard label="Referrers" value={formatEventCount(s.total_referrers)} />
          <StatCard label="Referrals" value={formatEventCount(s.total_referrals)} />
          <StatCard
            label="Active referrals"
            value={formatEventCount(s.active_referrals)}
          />
          <StatCard
            label="Rewards earned"
            value={formatMicros(s.total_rewards_earned_micros, defaultCurrency)}
          />
          <StatCard
            label="Referred spend"
            value={formatMicros(s.total_referred_spend_micros, defaultCurrency)}
          />
        </div>
      )}
    </QueryState>
  );
}

function EarningsByPeriod() {
  const { defaultCurrency } = useAuth();
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const query = useAnalyticsEarnings({
    period_start: start || undefined,
    period_end: end || undefined,
  });

  return (
    <Section
      title="Earnings by period"
      description="Reward earnings per referrer over the selected window."
      actions={
        <div className="flex items-end gap-2">
          <div className="flex flex-col gap-1">
            <Label htmlFor="ref-earn-start" className="text-xs">
              From
            </Label>
            <Input
              id="ref-earn-start"
              type="date"
              value={start}
              onChange={(e) => setStart(e.target.value)}
              className="h-8"
            />
          </div>
          <div className="flex flex-col gap-1">
            <Label htmlFor="ref-earn-end" className="text-xs">
              To
            </Label>
            <Input
              id="ref-earn-end"
              type="date"
              value={end}
              onChange={(e) => setEnd(e.target.value)}
              className="h-8"
            />
          </div>
        </div>
      }
    >
      <QueryState
        query={query}
        isEmpty={(d) => d.referrers.length === 0}
        empty={{
          title: "No earnings in this period",
          description: "Try widening the date range.",
        }}
      >
        {(data) => (
          <div className="space-y-3">
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
                {data.referrers.map((r) => (
                  <TableRow key={r.referrer_customer_id}>
                    <TableCell>
                      <div className="font-medium">{r.external_id || "—"}</div>
                      <div className="font-mono text-xs text-muted-foreground">
                        {r.referrer_customer_id}
                      </div>
                    </TableCell>
                    <TableCell className="max-w-[12rem]">
                      <CopyField value={r.referral_code} />
                    </TableCell>
                    <TableCell className="text-right">{r.referral_count}</TableCell>
                    <TableCell className="text-right">
                      {formatMicros(r.total_earned_micros, defaultCurrency)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            <div className="flex items-center justify-between border-t border-border pt-2 text-sm">
              <span className="text-muted-foreground">
                {data.period_start || "start"} → {data.period_end || "now"}
              </span>
              <span className="font-medium">
                Total earned {formatMicros(data.total_earned_micros, defaultCurrency)}
              </span>
            </div>
          </div>
        )}
      </QueryState>
    </Section>
  );
}
