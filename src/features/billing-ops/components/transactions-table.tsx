import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { BillingTransaction } from "../api/types";

function microsToDollars(micros: number): string {
  const sign = micros < 0 ? "-" : "";
  return `${sign}$${(Math.abs(micros) / 1_000_000).toFixed(2)}`;
}

function microsToBalance(micros: number): string {
  return (micros / 1_000_000).toFixed(2);
}

export function TransactionsTable({ rows }: { rows: BillingTransaction[] }) {
  if (rows.length === 0) {
    return (
      <div className="rounded-lg border border-dashed p-8 text-center text-sm text-muted-foreground">
        No transactions yet.
      </div>
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
            <TableCell>{r.type}</TableCell>
            <TableCell className="text-muted-foreground">{r.description}</TableCell>
            <TableCell className="text-right">{microsToDollars(r.amountMicros)}</TableCell>
            <TableCell className="text-right">{microsToBalance(r.balanceAfterMicros)}</TableCell>
            <TableCell className="text-muted-foreground">{new Date(r.createdAt).toLocaleString()}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
