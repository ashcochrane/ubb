import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { StatusBadge } from "@/components/shared/status-badge";
import { EmptyState } from "@/components/shared/empty-state";
import { formatSignedMicros, formatMicros, formatShortDate } from "@/lib/format";
import type { WalletTransaction } from "../api/types";

export function TransactionsTable({
  rows,
  currency = "USD",
}: {
  rows: WalletTransaction[];
  currency?: string;
}) {
  if (rows.length === 0) {
    return (
      <EmptyState
        title="No transactions yet"
        description="Top-ups, debits, credits, and refunds will appear here."
      />
    );
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Type</TableHead>
          <TableHead>Description</TableHead>
          <TableHead className="text-right">Amount</TableHead>
          <TableHead className="text-right">Balance after</TableHead>
          <TableHead>When</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map((r) => (
          <TableRow key={r.id}>
            <TableCell>
              <StatusBadge value={r.transaction_type} />
            </TableCell>
            <TableCell className="max-w-[20rem] truncate text-muted-foreground" title={r.description}>
              {r.description || "—"}
            </TableCell>
            <TableCell className="text-right font-medium tabular-nums">
              {formatSignedMicros(r.amount_micros, currency)}
            </TableCell>
            <TableCell className="text-right tabular-nums text-muted-foreground">
              {formatMicros(r.balance_after_micros, currency)}
            </TableCell>
            <TableCell className="text-muted-foreground">
              {formatShortDate(r.created_at)}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
