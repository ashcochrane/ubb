import * as React from "react";
import { Link } from "@tanstack/react-router";
import { UsersRound } from "lucide-react";

import { CopyButton } from "@/components/shared/copy-button";
import { DateRangePicker } from "@/components/shared/date-range-picker";
import { EmptyState } from "@/components/shared/empty-state";
import { ErrorCard } from "@/components/shared/error-card";
import { PageHeader } from "@/components/shared/page-header";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
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
import { resolveRange, type DateRange } from "@/lib/date-range";
import { formatMicros } from "@/lib/format";
import {
  marginBound,
  marginPercentBound,
  supplierCostTotal,
} from "@/lib/supplier-cost";
import { cn } from "@/lib/utils";

import { useCustomerMargins } from "../api/queries";
import {
  CUSTOMER_SORT_OPTIONS,
  filterMarginRows,
  listRowRevenueMicros,
  shortId,
  sortMarginRows,
  type CustomerSort,
} from "../lib/helpers";
import { CreateCustomerDialog } from "./create-customer-dialog";

interface CustomersPageProps {
  search: DateRange;
  onSearchChange: (next: DateRange) => void;
  onOpenCustomer: (customerId: string) => void;
}

export function CustomersPage({
  search,
  onSearchChange,
  onOpenCustomer,
}: CustomersPageProps) {
  const range = resolveRange(search);
  const currency = useTenantCurrency();
  const query = useCustomerMargins(range);
  const [filter, setFilter] = React.useState("");
  const [sort, setSort] = React.useState<CustomerSort>("revenue");
  const [createOpen, setCreateOpen] = React.useState(false);

  const rows = query.data?.customers ?? [];
  const visible = filterMarginRows(sortMarginRows(rows, sort), filter);

  return (
    <div className="space-y-4">
      <PageHeader
        title="Customers"
        description="Per-customer revenue, provider cost, and margin for the selected window."
        actions={
          <>
            <DateRangePicker value={search} onChange={onSearchChange} />
            <Button onClick={() => setCreateOpen(true)}>New customer</Button>
          </>
        }
      />

      <div className="flex flex-wrap items-center gap-2">
        <Input
          value={filter}
          onChange={(event) => setFilter(event.target.value)}
          placeholder="Search by customer ID…"
          aria-label="Search customers"
          className="h-8 w-64 text-[12px]"
        />
        <Select
          value={sort}
          onValueChange={(value) => {
            if (value === "revenue" || value === "margin" || value === "margin_pct") {
              setSort(value);
            }
          }}
        >
          <SelectTrigger className="h-8 text-[12px]" aria-label="Sort customers">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {CUSTOMER_SORT_OPTIONS.map((option) => (
              <SelectItem key={option.value} value={option.value}>
                Sort: {option.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <span className="text-[11px] text-text-muted">
          This list carries internal customer IDs only — the margin list has no
          external IDs. Open a customer to see its external ID.
        </span>
      </div>

      {query.isLoading ? (
        <div className="space-y-2">
          {Array.from({ length: 6 }, (_, index) => (
            <Skeleton key={index} className="h-10 w-full" />
          ))}
        </div>
      ) : query.isError ? (
        <ErrorCard error={query.error} onRetry={() => void query.refetch()} />
      ) : rows.length === 0 ? (
        <EmptyState
          icon={UsersRound}
          title="No customers yet"
          description="Create your first customer to start metering usage and tracking margin."
          action={{ label: "Create customer", onClick: () => setCreateOpen(true) }}
        />
      ) : visible.length === 0 ? (
        <EmptyState
          title="No customers match"
          description={`No customer ID contains "${filter}".`}
          action={{ label: "Clear search", onClick: () => setFilter("") }}
        />
      ) : (
        <div
          className={cn(
            "overflow-x-auto rounded-md border border-border bg-bg-surface transition-opacity",
            // keepPreviousData: range changes dim the old rows instead of blanking.
            query.isPlaceholderData && "opacity-60",
          )}
        >
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Customer</TableHead>
                <TableHead className="text-right">Revenue</TableHead>
                <TableHead className="text-right">COGS</TableHead>
                <TableHead className="text-right">Gross margin</TableHead>
                <TableHead className="text-right">Margin %</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {visible.map((row) => (
                <TableRow key={row.customer_id}>
                  <TableCell>
                    <span className="flex items-center gap-1.5">
                      <Link
                        to="/customers/$customerId"
                        params={{ customerId: row.customer_id }}
                        search={{
                          start_date: search.start_date,
                          end_date: search.end_date,
                        }}
                        className="font-mono text-[12px] underline-offset-2 hover:underline"
                        title={row.customer_id}
                      >
                        {shortId(row.customer_id)}
                      </Link>
                      <CopyButton value={row.customer_id} label="Copy customer ID" />
                    </span>
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {formatMicros(listRowRevenueMicros(row), currency)}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {supplierCostTotal(row.provider_cost_micros, row, currency)}
                  </TableCell>
                  <TableCell
                    className={cn(
                      "text-right tabular-nums",
                      row.gross_margin_micros < 0 && "text-danger-dark",
                    )}
                  >
                    {marginBound(row.gross_margin_micros, row, currency)}
                  </TableCell>
                  <TableCell
                    className={cn(
                      "text-right tabular-nums",
                      row.margin_percentage < 0 && "text-danger-dark",
                    )}
                  >
                    {marginPercentBound(row.margin_percentage, row)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          {query.isFetching && (
            <div className="border-t border-border px-3 py-1.5 text-[11px] text-text-muted">
              Refreshing…
            </div>
          )}
        </div>
      )}

      <CreateCustomerDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        onCreated={onOpenCustomer}
      />
    </div>
  );
}
