// src/features/customers/components/customer-table.tsx
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
import { formatCostMicros, formatRelativeDate } from "@/lib/format";
import type { CustomerFilterKey, CustomerMapping, CustomerStatus } from "../api/types";
import { InlineEditCell } from "./customer-row-edit";

interface CustomerTableProps {
  customers: CustomerMapping[];
  activeFilter: CustomerFilterKey;
  onFilterChange: (filter: CustomerFilterKey) => void;
  searchQuery: string;
  onSearchChange: (query: string) => void;
  editingCustomerId: string | null;
  onEditingChange: (id: string | null) => void;
}

type StatusPill = { label: string; className: string };
const STATUS_CONFIG: Record<CustomerStatus, StatusPill> = {
  active: { label: "Active", className: "bg-green-light text-green-text" },
  idle: { label: "Idle", className: "bg-bg-subtle text-text-secondary border border-border" },
  unmapped: { label: "New", className: "bg-blue-light text-blue-text border border-blue-border" },
};

const FILTER_OPTIONS: { key: CustomerFilterKey; label: string }[] = [
  { key: "all", label: "All" },
  { key: "active", label: "Active" },
  { key: "idle", label: "Idle" },
  { key: "unmapped", label: "Unmapped" },
];

function filterMatches(filter: CustomerFilterKey, status: CustomerStatus): boolean {
  return filter === "all" || status === filter;
}

function searchMatches(query: string, c: CustomerMapping): boolean {
  if (!query) return true;
  const q = query.toLowerCase();
  return c.name.toLowerCase().includes(q) || (c.sdkIdentifier?.toLowerCase().includes(q) ?? false) || c.stripeCustomerId.toLowerCase().includes(q);
}

export function CustomerTable({
  customers,
  activeFilter,
  onFilterChange,
  searchQuery,
  onSearchChange,
  editingCustomerId,
  onEditingChange,
}: CustomerTableProps) {
  const filtered = customers.filter(
    (c) => filterMatches(activeFilter, c.status) && searchMatches(searchQuery, c),
  );

  const counts: Record<CustomerFilterKey, number> = {
    all: customers.length,
    active: customers.filter((c) => c.status === "active").length,
    idle: customers.filter((c) => c.status === "idle").length,
    unmapped: customers.filter((c) => c.status === "unmapped").length,
  };

  return (
    <div>
      <div className="mb-2.5 flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-[15px] font-bold text-text-primary">All customers</h2>
        <div className="flex items-center gap-2">
          <input
            type="text"
            placeholder="Search customers…"
            value={searchQuery}
            onChange={(e) => onSearchChange(e.target.value)}
            className="rounded-sm border border-border-mid bg-bg-surface px-2.5 py-1.5 text-[12px] text-text-primary placeholder:text-text-muted outline-none focus:border-accent-base focus:ring-2 focus:ring-accent-base/15"
            style={{ width: 180 }}
          />
          <button
            className="rounded-full border border-border-mid bg-bg-surface px-3 py-1 text-[12px] font-medium text-text-secondary opacity-50"
            disabled
          >
            Auto-match
          </button>
        </div>
      </div>

      <div className="mb-3 flex flex-wrap gap-1">
        {FILTER_OPTIONS.map((f) => (
          <button
            key={f.key}
            className={cn(
              "rounded-full border px-3 py-1 text-[12px] font-medium",
              activeFilter === f.key
                ? "border-accent-base bg-accent-base text-text-inverse"
                : "border-border-mid bg-bg-surface text-text-secondary hover:bg-bg-subtle",
            )}
            onClick={() => onFilterChange(f.key)}
          >
            {f.label} ({counts[f.key]})
          </button>
        ))}
      </div>

      <div className="overflow-hidden rounded-md border border-border bg-bg-surface">
        {filtered.length === 0 ? (
          <EmptyState
            title="All customers are mapped and healthy."
            className="rounded-none border-0"
          />
        ) : (
          <Table className="border-collapse text-[13px]">
            <TableHeader>
              <TableRow className="border-b border-border bg-bg-subtle hover:bg-bg-subtle">
                <TableHead className="h-auto px-3.5 py-2 text-left text-[10px] font-bold uppercase tracking-[0.06em] text-text-muted">
                  Stripe customer
                </TableHead>
                <TableHead className="h-auto px-3.5 py-2 text-left text-[10px] font-bold uppercase tracking-[0.06em] text-text-muted">
                  SDK identifier
                </TableHead>
                <TableHead className="h-auto px-3.5 py-2 text-right text-[10px] font-bold uppercase tracking-[0.06em] text-text-muted">
                  Revenue (30d)
                </TableHead>
                <TableHead className="h-auto px-3.5 py-2 text-right text-[10px] font-bold uppercase tracking-[0.06em] text-text-muted">
                  Events (30d)
                </TableHead>
                <TableHead className="h-auto px-3.5 py-2 text-right text-[10px] font-bold uppercase tracking-[0.06em] text-text-muted">
                  Last event
                </TableHead>
                <TableHead className="h-auto w-[70px] px-3.5 py-2 text-left text-[10px] font-bold uppercase tracking-[0.06em] text-text-muted">
                  Status
                </TableHead>
                <TableHead className="h-auto w-[40px] px-3.5 py-2" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {filtered.map((customer) => {
                const isEditing = editingCustomerId === customer.id;
                const isUnmapped = customer.status === "unmapped";
                const pill = STATUS_CONFIG[customer.status];

                return (
                  <TableRow
                    key={customer.id}
                    className="border-b border-bg-subtle last:border-0 hover:bg-bg-subtle"
                  >
                    <TableCell className="px-3.5 py-2.5">
                      <span className="font-semibold text-text-primary">{customer.name}</span>
                      <span className="mt-0.5 block text-[10px] text-text-muted">
                        {customer.stripeCustomerId} · {customer.email}
                      </span>
                    </TableCell>
                    <TableCell className="px-3.5 py-2.5">
                      {isEditing || isUnmapped ? (
                        <InlineEditCell
                          customerId={customer.id}
                          defaultValue={customer.sdkIdentifier ?? ""}
                          isNew={isUnmapped}
                          onDone={() => onEditingChange(null)}
                        />
                      ) : (
                        <span className="font-mono text-[11px] text-text-secondary">
                          {customer.sdkIdentifier}
                        </span>
                      )}
                    </TableCell>
                    <TableCell className="px-3.5 py-2.5 text-right text-[12px] font-medium text-text-primary">
                      {isUnmapped ? "\u2014" : formatCostMicros(customer.revenue30d)}
                    </TableCell>
                    <TableCell
                      className={cn(
                        "px-3.5 py-2.5 text-right text-[12px] text-text-secondary",
                        (customer.events30d === 0 || isUnmapped) && "text-text-muted",
                      )}
                    >
                      {isUnmapped ? "\u2014" : customer.events30d.toLocaleString()}
                    </TableCell>
                    <TableCell className="px-3.5 py-2.5 text-right text-[12px] text-text-muted">
                      {customer.lastEventAt
                        ? formatRelativeDate(customer.lastEventAt)
                        : "\u2014"}
                    </TableCell>
                    <TableCell className="px-3.5 py-2.5">
                      <span className={cn("inline-flex rounded-full px-2.5 py-0.5 text-[10px] font-semibold", pill.className)}>
                        {pill.label}
                      </span>
                    </TableCell>
                    <TableCell className="px-3.5 py-2.5 text-center">
                      {customer.sdkIdentifier && !isEditing && (
                        <button
                          className="text-[11px] font-medium text-blue hover:underline"
                          onClick={() => onEditingChange(customer.id)}
                        >
                          Edit
                        </button>
                      )}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        )}
      </div>
    </div>
  );
}
