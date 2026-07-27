import { useState } from "react";

import { EmptyState } from "@/components/shared/empty-state";
import { ErrorCard } from "@/components/shared/error-card";
import { Button } from "@/components/ui/button";
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
import { formatDate, formatMicros } from "@/lib/format";

import { usePayoutExport } from "../api/queries";
import { looseDate } from "../lib/dates";
import { downloadJson } from "../lib/download-json";

export function PayoutExportCard() {
  const currency = useTenantCurrency();
  const [requested, setRequested] = useState(false);
  const exportQuery = usePayoutExport(requested);

  const generate = () => {
    if (requested) void exportQuery.refetch();
    else setRequested(true);
  };

  const data = exportQuery.data;

  return (
    <Card>
      <CardHeader className="border-b">
        <CardTitle>Payout export</CardTitle>
        <CardDescription>
          UBB tracks what each referrer has earned but never moves the money. Generate a snapshot
          of lifetime totals per referrer and settle payouts through your own payment system.
        </CardDescription>
        <CardAction>
          <Button
            variant="outline"
            size="sm"
            onClick={generate}
            disabled={exportQuery.isFetching}
          >
            {exportQuery.isFetching ? "Working…" : requested ? "Refresh export" : "Generate export"}
          </Button>
        </CardAction>
      </CardHeader>
      {requested && (
        <CardContent className="px-0">
          {exportQuery.isLoading ? (
            <div className="space-y-2 px-4">
              {Array.from({ length: 3 }).map((_, index) => (
                <Skeleton key={index} className="h-8 w-full" />
              ))}
            </div>
          ) : exportQuery.isError ? (
            <ErrorCard
              error={exportQuery.error}
              onRetry={() => void exportQuery.refetch()}
              title="Couldn't generate the export"
              className="mx-4"
            />
          ) : data ? (
            data.data.length === 0 ? (
              <EmptyState
                title="Nothing to pay out"
                description="No referrer has earned rewards yet."
                className="mx-4"
              />
            ) : (
              <>
                <div className="flex flex-wrap items-center justify-between gap-2 px-4 pb-3 text-[12px] text-text-secondary">
                  <span>
                    Exported {looseDate(data.exported_at, formatDate)} ·{" "}
                    {data.referrer_count.toLocaleString()} referrers
                  </span>
                  <span className="flex items-center gap-3">
                    <span>
                      Total{" "}
                      <span className="font-semibold text-text-primary">
                        {formatMicros(data.total_payout_micros, currency)}
                      </span>
                    </span>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() =>
                        downloadJson(data, `referral-payouts-${data.exported_at.slice(0, 10)}.json`)
                      }
                    >
                      Download JSON
                    </Button>
                  </span>
                </div>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Referrer</TableHead>
                      <TableHead>Code</TableHead>
                      <TableHead className="text-right">Earned</TableHead>
                      <TableHead className="text-right">Referred spend</TableHead>
                      <TableHead className="text-right">Referrals</TableHead>
                      <TableHead className="text-right">Active</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {data.data.map((row) => (
                      <TableRow key={row.referrer_customer_id}>
                        <TableCell>{row.external_id}</TableCell>
                        <TableCell className="font-mono text-[12px]">{row.referral_code}</TableCell>
                        <TableCell className="text-right">
                          {formatMicros(row.total_earned_micros, currency)}
                        </TableCell>
                        <TableCell className="text-right">
                          {formatMicros(row.total_referred_spend_micros, currency)}
                        </TableCell>
                        <TableCell className="text-right">
                          {row.referral_count.toLocaleString()}
                        </TableCell>
                        <TableCell className="text-right">
                          {row.active_referral_count.toLocaleString()}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </>
            )
          ) : null}
        </CardContent>
      )}
    </Card>
  );
}
