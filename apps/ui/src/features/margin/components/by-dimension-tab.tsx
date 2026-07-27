import { useState } from "react";
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from "@/components/ui/table";
import { Input } from "@/components/ui/input";
import { QueryState } from "@/components/shared/data-states";
import { FormField } from "@/components/shared/form-field";
import { formatMicros, formatEventCount, humanizeLabel } from "@/lib/format";
import { useMarginByDimension } from "../api/queries";
import type { DateRange, DimensionFilters } from "../api/types";

/** Parse a numeric text input into an optional number (blank → undefined). */
function toOptionalNumber(value: string): number | undefined {
  const trimmed = value.trim();
  if (!trimmed) return undefined;
  const n = Number(trimmed);
  return Number.isFinite(n) ? n : undefined;
}

export function ByDimensionTab({
  range,
  currency,
}: {
  range: DateRange;
  currency: string;
}) {
  const [filters, setFilters] = useState<DimensionFilters>({});
  const query = useMarginByDimension(range, filters);

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <FormField label="Provider" hint="Numeric provider id">
          {(id) => (
            <Input
              id={id}
              type="number"
              inputMode="numeric"
              placeholder="Any provider"
              value={filters.provider ?? ""}
              onChange={(e) =>
                setFilters((f) => ({
                  ...f,
                  provider: toOptionalNumber(e.target.value),
                }))
              }
            />
          )}
        </FormField>
        <FormField label="Product" hint="Numeric product id">
          {(id) => (
            <Input
              id={id}
              type="number"
              inputMode="numeric"
              placeholder="Any product"
              value={filters.product ?? ""}
              onChange={(e) =>
                setFilters((f) => ({
                  ...f,
                  product: toOptionalNumber(e.target.value),
                }))
              }
            />
          )}
        </FormField>
        <FormField label="Tag key" hint="Group margins by a tag key">
          {(id) => (
            <Input
              id={id}
              placeholder="e.g. environment"
              value={filters.tag_key ?? ""}
              onChange={(e) =>
                setFilters((f) => ({
                  ...f,
                  tag_key: e.target.value.trim() || undefined,
                }))
              }
            />
          )}
        </FormField>
      </div>

      <QueryState
        query={query}
        isEmpty={(data) => data.rows.length === 0}
        empty={{
          title: "No dimension breakdown for these filters",
          description: "Try a different provider, product, or tag key.",
        }}
      >
        {(data) => (
          <div className="rounded-xl bg-card ring-1 ring-foreground/10">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Dimension</TableHead>
                  <TableHead className="text-right">Provider cost</TableHead>
                  <TableHead className="text-right">Billed cost</TableHead>
                  <TableHead className="text-right">Margin</TableHead>
                  <TableHead className="text-right">Events</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.rows.map((row, i) => (
                  <TableRow key={`${row.dimension ?? "unknown"}-${i}`}>
                    <TableCell>
                      {row.dimension ? (
                        humanizeLabel(row.dimension)
                      ) : (
                        <span className="text-muted-foreground">
                          Unattributed
                        </span>
                      )}
                    </TableCell>
                    <TableCell className="text-right text-muted-foreground">
                      {formatMicros(row.provider_cost_micros, currency)}
                    </TableCell>
                    <TableCell className="text-right">
                      {formatMicros(row.billed_cost_micros, currency)}
                    </TableCell>
                    <TableCell className="text-right">
                      {formatMicros(row.margin_micros, currency)}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {formatEventCount(row.event_count)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </QueryState>
    </div>
  );
}
