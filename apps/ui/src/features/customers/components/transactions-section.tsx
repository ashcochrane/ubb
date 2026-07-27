import { ReceiptText } from "lucide-react";

import { EmptyState } from "@/components/shared/empty-state";
import { ErrorCard } from "@/components/shared/error-card";
import { LoadMore } from "@/components/shared/load-more";
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
import { formatDate, formatMicros, formatSignedMicros } from "@/lib/format";
import { transactionTypeLabel } from "@/lib/labels";
import { cn } from "@/lib/utils";

import { useTransactionsList } from "../api/queries";

export function TransactionsSection({ customerId }: { customerId: string }) {
  const currency = useTenantCurrency();
  const list = useTransactionsList(customerId);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Transactions</CardTitle>
      </CardHeader>
      <CardContent>
        {list.isInitialLoading ? (
          <Skeleton className="h-32 w-full" />
        ) : list.isError ? (
          <ErrorCard error={list.error} onRetry={() => void list.refetch()} />
        ) : list.rows.length === 0 ? (
          <EmptyState
            icon={ReceiptText}
            title="No transactions yet"
            description="Top-ups, usage deductions, grants, and adjustments will appear here newest first."
          />
        ) : (
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>When</TableHead>
                  <TableHead>Type</TableHead>
                  <TableHead className="text-right">Amount</TableHead>
                  <TableHead className="text-right">Balance after</TableHead>
                  <TableHead>Description</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {list.rows.map((row) => (
                  <TableRow key={row.id}>
                    <TableCell className="whitespace-nowrap text-[12px]">
                      {formatDate(row.created_at)}
                    </TableCell>
                    <TableCell>{transactionTypeLabel(row.transaction_type)}</TableCell>
                    <TableCell
                      className={cn(
                        "text-right tabular-nums",
                        row.amount_micros < 0 && "text-text-secondary",
                      )}
                    >
                      {formatSignedMicros(row.amount_micros, currency)}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {formatMicros(row.balance_after_micros, currency)}
                    </TableCell>
                    <TableCell
                      className="max-w-56 truncate text-[12px] text-text-secondary"
                      title={row.description || row.reference_id}
                    >
                      {row.description || row.reference_id || "—"}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            <LoadMore
              shownCount={list.rows.length}
              hasMore={list.hasMore}
              isFetchingNextPage={list.isFetchingNextPage}
              onLoadMore={list.fetchNextPage}
              noun="transactions"
            />
          </div>
        )}
      </CardContent>
    </Card>
  );
}
