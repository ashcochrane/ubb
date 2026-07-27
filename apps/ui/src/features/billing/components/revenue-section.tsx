import { useState } from "react";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  DetailRow,
  ErrorInline,
  LoadingRows,
  Section,
} from "@/components/shared/data-states";
import { EmptyState } from "@/components/shared/empty-state";
import { FormField } from "@/components/shared/form-field";
import { formatMicros, humanizeLabel } from "@/lib/format";
import { useRevenueAnalytics } from "../api/queries";
import type { DateRange } from "../api/types";

/** Render one defensively-typed daily cell: money keys as currency, else text. */
function renderCell(key: string, value: unknown): string {
  if (value == null) return "—";
  if (key.endsWith("_micros") && typeof value === "number") {
    return formatMicros(value);
  }
  if (typeof value === "number" || typeof value === "string") return String(value);
  if (typeof value === "boolean") return value ? "Yes" : "No";
  return JSON.stringify(value);
}

function DailyTable({ daily }: { daily: Record<string, unknown>[] }) {
  if (daily.length === 0) {
    return (
      <EmptyState
        title="No daily rows"
        description="No revenue activity in this window."
      />
    );
  }
  // Union of keys across rows so a sparse row never drops a column.
  const columns = Array.from(
    daily.reduce((set, row) => {
      Object.keys(row).forEach((k) => set.add(k));
      return set;
    }, new Set<string>()),
  );
  return (
    <div className="overflow-x-auto">
      <Table>
        <TableHeader>
          <TableRow>
            {columns.map((c) => (
              <TableHead key={c}>{humanizeLabel(c)}</TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {daily.map((row, i) => (
            <TableRow key={i}>
              {columns.map((c) => (
                <TableCell key={c} className="tabular-nums">
                  {renderCell(c, row[c])}
                </TableCell>
              ))}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

export function RevenueSection() {
  const [range, setRange] = useState<DateRange>({});
  const query = useRevenueAnalytics(range);

  return (
    <Section
      title="Revenue"
      description="Provider cost is what you pay upstream; customer charge is what you bill; markup is your gross revenue on top."
      actions={
        <div className="flex items-end gap-2">
          <FormField label="From" className="w-40">
            {(id) => (
              <Input
                id={id}
                type="date"
                value={range.start_date ?? ""}
                onChange={(e) =>
                  setRange((r) => ({ ...r, start_date: e.target.value || undefined }))
                }
              />
            )}
          </FormField>
          <FormField label="To" className="w-40">
            {(id) => (
              <Input
                id={id}
                type="date"
                value={range.end_date ?? ""}
                onChange={(e) =>
                  setRange((r) => ({ ...r, end_date: e.target.value || undefined }))
                }
              />
            )}
          </FormField>
        </div>
      }
    >
      {query.isLoading ? (
        <LoadingRows rows={3} />
      ) : query.isError ? (
        <ErrorInline error={query.error} onRetry={() => query.refetch()} />
      ) : query.data ? (
        <div className="space-y-5">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <div className="rounded-lg border border-border p-4">
              <DetailRow label="Provider cost (what you pay)">
                <span className="text-lg font-semibold tabular-nums">
                  {formatMicros(query.data.total_provider_cost_micros)}
                </span>
              </DetailRow>
            </div>
            <div className="rounded-lg border border-border p-4">
              <DetailRow label="Customer charge (billed)">
                <span className="text-lg font-semibold tabular-nums">
                  {formatMicros(query.data.total_billed_cost_micros)}
                </span>
              </DetailRow>
            </div>
            <div className="rounded-lg border border-border p-4">
              <DetailRow label="Platform markup (your revenue)">
                <span className="text-lg font-semibold tabular-nums">
                  {formatMicros(query.data.total_markup_micros)}
                </span>
              </DetailRow>
            </div>
          </div>
          <DailyTable daily={(query.data.daily ?? []) as Record<string, unknown>[]} />
        </div>
      ) : null}
    </Section>
  );
}
