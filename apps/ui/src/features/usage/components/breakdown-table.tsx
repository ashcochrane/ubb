import type { ReactNode } from "react";
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from "@/components/ui/table";
import { Section } from "@/components/shared/data-states";
import { EmptyState } from "@/components/shared/empty-state";
import { formatMicros, humanizeLabel } from "@/lib/format";
import type { BreakdownRow } from "../api/types";

/**
 * Render one untyped cell defensively: `*_micros` numbers become money, objects
 * are JSON-stringified, everything else is coerced to a string.
 */
function renderCell(key: string, value: unknown): ReactNode {
  if (value === null || value === undefined) return "—";
  if (key.endsWith("_micros") && typeof value === "number") {
    return formatMicros(value);
  }
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

/**
 * Defensive table over untyped `{ [key: string]: unknown }[]` rows (the
 * analytics `by_*` breakdowns and timeseries `series`): columns are the keys of
 * the first row, humanized. Renders an empty message when there are no rows.
 */
export function DefensiveTable({
  rows,
  emptyMessage = "No data for the selected range.",
}: {
  rows: BreakdownRow[];
  emptyMessage?: string;
}) {
  const first = Array.isArray(rows) ? rows[0] : undefined;
  const keys = first ? Object.keys(first) : [];

  if (!first || keys.length === 0) {
    return <EmptyState title="No data" description={emptyMessage} />;
  }

  return (
    <div className="overflow-x-auto">
      <Table>
        <TableHeader>
          <TableRow>
            {keys.map((k) => (
              <TableHead key={k}>{humanizeLabel(k)}</TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((row, i) => (
            <TableRow key={i}>
              {keys.map((k) => (
                <TableCell key={k}>{renderCell(k, row[k])}</TableCell>
              ))}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

/** A titled Section wrapping a DefensiveTable — used for the analytics breakdowns. */
export function BreakdownTable({
  title,
  description,
  rows,
}: {
  title: string;
  description?: string;
  rows: BreakdownRow[];
}) {
  return (
    <Section title={title} description={description}>
      <DefensiveTable rows={rows} />
    </Section>
  );
}
