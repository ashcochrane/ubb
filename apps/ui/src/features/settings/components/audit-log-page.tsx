import * as React from "react";
import { ChevronDown, ChevronRight, ScrollText } from "lucide-react";

import { CopyButton } from "@/components/shared/copy-button";
import { EmptyState } from "@/components/shared/empty-state";
import { ErrorCard } from "@/components/shared/error-card";
import { LoadMore } from "@/components/shared/load-more";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { formatDate, formatRelativeDate } from "@/lib/format";
import { actorKindLabel, humanize } from "@/lib/labels";

import { useAuditRecords } from "../api/queries";
import type { AuditFilters } from "../api/types";
import { auditActionLabel, truncateId, type AuditSearch } from "../lib/settings";
import { MetadataTree } from "./metadata-tree";

export interface AuditLogPageProps {
  search?: AuditSearch;
  onSearchChange?: (next: AuditSearch) => void;
}

function clean(values: AuditSearch): AuditSearch {
  const next: AuditSearch = {};
  if (values.action) next.action = values.action;
  if (values.resource_type) next.resource_type = values.resource_type;
  if (values.resource_id) next.resource_id = values.resource_id;
  return next;
}

export function AuditLogPage({ search = {}, onSearchChange }: AuditLogPageProps) {
  const filters: AuditFilters = clean(search);
  const hasFilters = Object.keys(filters).length > 0;
  const records = useAuditRecords(filters);
  const [expanded, setExpanded] = React.useState<Record<string, boolean>>({});

  // Draft state for the filter strip — debounced into the URL so deep links
  // stay shareable without a navigation per keystroke.
  const [draft, setDraft] = React.useState<AuditSearch>(search);
  React.useEffect(() => {
    setDraft(clean(search));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search.action, search.resource_type, search.resource_id]);
  React.useEffect(() => {
    const timer = window.setTimeout(() => {
      const next = clean(draft);
      if (
        next.action !== filters.action ||
        next.resource_type !== filters.resource_type ||
        next.resource_id !== filters.resource_id
      ) {
        onSearchChange?.(next);
      }
    }, 350);
    return () => window.clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draft.action, draft.resource_type, draft.resource_id]);

  return (
    <div className="space-y-4">
      <p className="max-w-2xl text-[13px] text-muted-foreground">
        Every change made in this workspace — who did it, what it touched, and
        the details, append-only.
      </p>

      <div className="flex flex-wrap items-center gap-2">
        <Input
          value={draft.action ?? ""}
          onChange={(event) =>
            setDraft((d) => ({ ...d, action: event.target.value }))
          }
          placeholder="Action (e.g. config.updated)"
          aria-label="Filter by action"
          className="w-[220px]"
        />
        <Input
          value={draft.resource_type ?? ""}
          onChange={(event) =>
            setDraft((d) => ({ ...d, resource_type: event.target.value }))
          }
          placeholder="Resource type (e.g. pricing_book)"
          aria-label="Filter by resource type"
          className="w-[220px]"
        />
        <Input
          value={draft.resource_id ?? ""}
          onChange={(event) =>
            setDraft((d) => ({ ...d, resource_id: event.target.value }))
          }
          placeholder="Resource id"
          aria-label="Filter by resource id"
          className="w-[220px]"
        />
        {hasFilters && (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              setDraft({});
              onSearchChange?.({});
            }}
          >
            Clear filters
          </Button>
        )}
      </div>

      {records.isInitialLoading ? (
        <div className="space-y-2">
          <Skeleton className="h-9 w-full" />
          <Skeleton className="h-9 w-full" />
          <Skeleton className="h-9 w-full" />
          <Skeleton className="h-9 w-full" />
        </div>
      ) : records.isError ? (
        <ErrorCard error={records.error} onRetry={() => void records.refetch()} />
      ) : records.rows.length === 0 ? (
        <EmptyState
          icon={ScrollText}
          title={hasFilters ? "No matching records" : "No activity yet"}
          description={
            hasFilters
              ? "Nothing matches these filters. Filters match exact values."
              : "Changes made by your team, API keys, and UBB itself will appear here."
          }
          action={
            hasFilters
              ? {
                  label: "Clear filters",
                  onClick: () => {
                    setDraft({});
                    onSearchChange?.({});
                  },
                }
              : undefined
          }
        />
      ) : (
        <div className="rounded-lg border border-border">
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-8" />
                  <TableHead>Time</TableHead>
                  <TableHead>Actor</TableHead>
                  <TableHead>Action</TableHead>
                  <TableHead>Resource</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {records.rows.map((record) => {
                  const hasMetadata = Object.keys(record.metadata).length > 0;
                  const isOpen = expanded[record.id] === true;
                  return (
                    <React.Fragment key={record.id}>
                      <TableRow>
                        <TableCell>
                          {hasMetadata && (
                            <button
                              type="button"
                              aria-label={
                                isOpen ? "Hide details" : "Show details"
                              }
                              aria-expanded={isOpen}
                              onClick={() =>
                                setExpanded((state) => ({
                                  ...state,
                                  [record.id]: !isOpen,
                                }))
                              }
                              className="flex h-6 w-6 items-center justify-center rounded text-muted-foreground hover:text-foreground"
                            >
                              {isOpen ? (
                                <ChevronDown className="h-3.5 w-3.5" />
                              ) : (
                                <ChevronRight className="h-3.5 w-3.5" />
                              )}
                            </button>
                          )}
                        </TableCell>
                        <TableCell className="text-muted-foreground">
                          <span title={formatDate(record.created_at)}>
                            {formatRelativeDate(record.created_at)}
                          </span>
                        </TableCell>
                        <TableCell>
                          <span className="flex items-center gap-1.5">
                            <span className="max-w-[180px] truncate" title={record.actor_display}>
                              {record.actor_display}
                            </span>
                            <Badge variant="outline">
                              {actorKindLabel(record.actor_kind)}
                            </Badge>
                          </span>
                        </TableCell>
                        <TableCell className="font-medium">
                          {auditActionLabel(record.action)}
                        </TableCell>
                        <TableCell>
                          <span className="flex items-center gap-1.5">
                            <span className="text-muted-foreground">
                              {humanize(record.resource_type)}
                            </span>
                            <span
                              className="font-mono text-[12px]"
                              title={record.resource_id}
                            >
                              {truncateId(record.resource_id, 10)}
                            </span>
                            <CopyButton value={record.resource_id} />
                          </span>
                        </TableCell>
                      </TableRow>
                      {isOpen && (
                        <TableRow className="hover:bg-transparent">
                          <TableCell />
                          <TableCell colSpan={4} className="whitespace-normal py-3">
                            <MetadataTree data={record.metadata} />
                          </TableCell>
                        </TableRow>
                      )}
                    </React.Fragment>
                  );
                })}
              </TableBody>
            </Table>
          </div>
          <LoadMore
            shownCount={records.rows.length}
            hasMore={records.hasMore}
            isFetchingNextPage={records.isFetchingNextPage}
            onLoadMore={records.fetchNextPage}
            noun="records"
          />
        </div>
      )}
    </div>
  );
}
