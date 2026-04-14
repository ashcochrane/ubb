// src/features/onboarding/components/match-results-table.tsx
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { cn } from "@/lib/utils";
import type { CustomerMatch } from "../api/types";

interface MatchResultsTableProps {
  customers: CustomerMatch[];
  onManualUpdate: (stripeId: string, identifier: string) => void;
}

export function MatchResultsTable({
  customers,
  onManualUpdate,
}: MatchResultsTableProps) {
  return (
    <div className="rounded-lg border border-border">
      <Table className="text-label">
        <TableHeader>
          <TableRow className="border-b border-border hover:bg-transparent">
            <TableHead className="h-auto px-3 py-2 text-left font-medium text-muted-foreground">
              Stripe customer
            </TableHead>
            <TableHead className="h-auto px-3 py-2 text-left font-medium text-muted-foreground">
              Your identifier
            </TableHead>
            <TableHead className="h-auto px-3 py-2 text-right font-medium text-muted-foreground">
              Revenue (30d)
            </TableHead>
            <TableHead className="h-auto px-3 py-2 text-right font-medium text-muted-foreground">
              Status
            </TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {customers.map((c) => (
            <TableRow
              key={c.stripeId}
              className={cn(
                "border-b border-border/50 last:border-0 hover:bg-transparent",
                c.status === "manual" && "bg-amber-50/50 dark:bg-amber-900/10",
              )}
            >
              <TableCell className="px-3 py-2">
                <div className="font-medium">{c.name}</div>
                <div className="font-mono text-muted text-muted-foreground">
                  {c.stripeId}
                </div>
              </TableCell>
              <TableCell className="px-3 py-2">
                {c.status === "matched" ? (
                  <span className="font-mono">{c.identifier}</span>
                ) : (
                  <input
                    defaultValue={c.identifier ?? ""}
                    onChange={(e) => onManualUpdate(c.stripeId, e.target.value)}
                    placeholder="Enter identifier..."
                    className="w-full rounded border border-amber-300 bg-background px-2 py-1 font-mono text-label outline-none focus:border-muted-foreground dark:border-amber-700"
                  />
                )}
              </TableCell>
              <TableCell className="px-3 py-2 text-right font-mono">
                ${c.revenue30d.toLocaleString()}
              </TableCell>
              <TableCell className="px-3 py-2 text-right">
                <span
                  className={cn(
                    "rounded-full px-2 py-0.5 text-muted font-medium",
                    c.status === "matched"
                      ? "bg-green-50 text-green-700 dark:bg-green-900/20 dark:text-green-400"
                      : "bg-amber-50 text-amber-700 dark:bg-amber-900/20 dark:text-amber-400",
                  )}
                >
                  {c.status === "matched" ? "Matched" : "Manual"}
                </span>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
