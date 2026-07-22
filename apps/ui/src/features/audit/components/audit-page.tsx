import { useState } from "react";
import { ScrollText, ChevronRight, ChevronDown } from "lucide-react";
import { PageHeader } from "@/components/shared/page-header";
import { FormField } from "@/components/shared/form-field";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from "@/components/ui/table";
import { LoadingRows, ErrorInline } from "@/components/shared/data-states";
import { StatusBadge } from "@/components/shared/status-badge";
import { EmptyState } from "@/components/shared/empty-state";
import { CursorPagerControls } from "@/components/shared/cursor-pager";
import { formatDate, humanizeLabel } from "@/lib/format";
import { useAuditRecords } from "../api/queries";
import type { AuditFilters, AuditRecord } from "../api/types";

export function AuditPage() {
  const [filters, setFilters] = useState<AuditFilters>({
    action: "",
    resource_type: "",
    resource_id: "",
  });

  const set = (key: keyof AuditFilters, value: string) =>
    setFilters((prev) => ({ ...prev, [key]: value }));

  return (
    <div className="space-y-6">
      <PageHeader
        title="Audit log"
        description="Every privileged action taken in this tenant, newest first."
      />

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <FormField label="Action">
          {(id) => (
            <Input
              id={id}
              placeholder="e.g. api_key.created"
              value={filters.action}
              onChange={(e) => set("action", e.target.value)}
            />
          )}
        </FormField>
        <FormField label="Resource type">
          {(id) => (
            <Input
              id={id}
              placeholder="e.g. api_key"
              value={filters.resource_type}
              onChange={(e) => set("resource_type", e.target.value)}
            />
          )}
        </FormField>
        <FormField label="Resource ID">
          {(id) => (
            <Input
              id={id}
              placeholder="Exact id"
              value={filters.resource_id}
              onChange={(e) => set("resource_id", e.target.value)}
            />
          )}
        </FormField>
      </div>

      {/* Keying on the active filters remounts the list so its cursor pager
          resets to the first page whenever a filter changes. */}
      <AuditRecordsList
        key={`${filters.action}|${filters.resource_type}|${filters.resource_id}`}
        filters={filters}
      />
    </div>
  );
}

function AuditRecordsList({ filters }: { filters: AuditFilters }) {
  const pager = useAuditRecords(filters);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  const toggle = (id: string) =>
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  if (pager.isLoading) return <LoadingRows />;
  if (pager.isError) return <ErrorInline error={pager.error} onRetry={pager.refetch} />;
  if (pager.items.length === 0) {
    return (
      <EmptyState
        icon={ScrollText}
        title="No audit records"
        description="No actions match these filters yet."
      />
    );
  }

  return (
    <div className="space-y-3">
      <div className="rounded-xl bg-card ring-1 ring-foreground/10">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-8" />
              <TableHead>Action</TableHead>
              <TableHead>Actor</TableHead>
              <TableHead>Resource</TableHead>
              <TableHead>When</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {pager.items.map((record) => (
              <AuditRow
                key={record.id}
                record={record}
                open={expanded.has(record.id)}
                onToggle={() => toggle(record.id)}
              />
            ))}
          </TableBody>
        </Table>
      </div>
      <CursorPagerControls pager={pager} />
    </div>
  );
}

function AuditRow({
  record,
  open,
  onToggle,
}: {
  record: AuditRecord;
  open: boolean;
  onToggle: () => void;
}) {
  const metaEntries = Object.entries(record.metadata ?? {});
  const hasMeta = metaEntries.length > 0;

  return (
    <>
      <TableRow
        className={hasMeta ? "cursor-pointer" : undefined}
        onClick={hasMeta ? onToggle : undefined}
      >
        <TableCell>
          {hasMeta ? (
            open ? (
              <ChevronDown className="size-4 text-muted-foreground" />
            ) : (
              <ChevronRight className="size-4 text-muted-foreground" />
            )
          ) : null}
        </TableCell>
        <TableCell>
          <StatusBadge value={record.action} tone="neutral" />
        </TableCell>
        <TableCell>
          <div className="font-medium">{record.actor_display}</div>
          <div className="text-xs text-muted-foreground">{humanizeLabel(record.actor_kind)}</div>
        </TableCell>
        <TableCell>
          <div className="font-mono text-xs">{record.resource_type}</div>
          <div className="font-mono text-xs text-muted-foreground break-all">
            {record.resource_id}
          </div>
        </TableCell>
        <TableCell className="whitespace-nowrap text-muted-foreground">
          {formatDate(record.created_at)}
        </TableCell>
      </TableRow>
      {open && hasMeta && (
        <TableRow>
          <TableCell colSpan={5} className="bg-muted/30">
            <div className="px-2 py-1">
              <p className="mb-2 text-xs font-medium text-muted-foreground">Metadata</p>
              <dl className="grid grid-cols-1 gap-x-8 gap-y-1.5 sm:grid-cols-2">
                {metaEntries.map(([key, value]) => (
                  <div key={key} className="flex flex-col gap-0.5">
                    <dt className="text-xs text-muted-foreground">{humanizeLabel(key)}</dt>
                    <dd className="font-mono text-xs break-all">{renderValue(value)}</dd>
                  </div>
                ))}
              </dl>
              {record.correlation_id && (
                <p className="mt-2 text-xs text-muted-foreground">
                  Correlation ID:{" "}
                  <span className="font-mono break-all">{record.correlation_id}</span>
                </p>
              )}
            </div>
          </TableCell>
        </TableRow>
      )}
    </>
  );
}

/** Render a single metadata value without dumping raw nested JSON blobs. */
function renderValue(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  if (Array.isArray(value)) return value.map((v) => renderValue(v)).join(", ");
  return JSON.stringify(value);
}
