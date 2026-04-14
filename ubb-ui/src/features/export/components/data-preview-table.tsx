import { memo } from "react";
import { EmptyState } from "@/components/shared/empty-state";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { cn } from "@/lib/utils";
import type { PreviewColumn } from "../api/types";

interface DataPreviewTableProps {
  columns: PreviewColumn[];
  rows: Record<string, string | number | null>[];
  totalRowCount: number;
}

function DataPreviewTableImpl({
  columns,
  rows,
  totalRowCount,
}: DataPreviewTableProps) {
  if (rows.length === 0) {
    return (
      <div className="overflow-hidden rounded-md border border-border bg-bg-surface">
        <div className="flex items-center justify-between border-b border-border bg-bg-subtle px-3.5 py-2.5">
          <span className="text-[12px] font-semibold text-text-primary">Data preview</span>
          <span className="text-[11px] text-text-muted">0 rows</span>
        </div>
        <EmptyState
          title="No events match"
          description="Try adjusting your filters."
          className="rounded-none border-0"
        />
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-md border border-border bg-bg-surface">
      <div className="flex items-center justify-between border-b border-border bg-bg-subtle px-3.5 py-2.5">
        <span className="text-[12px] font-semibold text-text-primary">Data preview</span>
        <span className="text-[11px] text-text-muted">
          First {rows.length} of {totalRowCount.toLocaleString()} rows
        </span>
      </div>
      <Table className="border-collapse whitespace-nowrap text-muted">
        <TableHeader>
          <TableRow className="hover:bg-transparent">
            {columns.map((col) => (
              <TableHead
                key={col.key}
                className={cn(
                  "h-auto border-b border-border bg-bg-subtle px-2 py-1.5 text-[10px] font-bold uppercase tracking-[0.06em] text-text-muted",
                  col.align === "right" ? "text-right" : "text-left",
                )}
              >
                {col.label}
              </TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((row, i) => (
            <TableRow
              key={i}
              className="border-b border-border last:border-0 hover:bg-bg-subtle"
            >
              {columns.map((col) => {
                const val = row[col.key];
                const isNull = val === null || val === "\u2014";
                const keyLower = col.key.toLowerCase();
                const isTime = keyLower.includes("time") || keyLower.includes("date");
                const isCustomer = keyLower.includes("customer");
                const isProduct = keyLower.includes("product");
                const isCard = keyLower.includes("card");
                const isDimension = keyLower.includes("dimension");
                return (
                  <TableCell
                    key={col.key}
                    className={cn(
                      "px-2 py-1.5",
                      !isDimension && "font-mono",
                      isDimension && "font-sans text-[12px] text-text-primary",
                      col.align === "right" && "text-right",
                      (isNull || col.muted) && "text-muted-foreground",
                      col.bold && !isNull && "font-medium",
                      !isNull && isTime && "text-text-muted",
                      !isNull && isCustomer && "text-accent-text font-medium",
                      !isNull && isProduct && "text-green-text",
                      !isNull && isCard && "text-blue-text",
                    )}
                  >
                    {isNull ? "\u2014" : val}
                  </TableCell>
                );
              })}
            </TableRow>
          ))}
        </TableBody>
      </Table>
      <div className="bg-bg-subtle px-3.5 py-2 text-center text-[11px] text-text-muted">
        {Math.max(0, totalRowCount - rows.length).toLocaleString()} more rows
        match your filters
      </div>
    </div>
  );
}

export const DataPreviewTable = memo(DataPreviewTableImpl);
