import { ListChecks } from "lucide-react";

import { EmptyState } from "@/components/shared/empty-state";
import { ErrorCard } from "@/components/shared/error-card";
import { LoadMore } from "@/components/shared/load-more";
import { PageHeader } from "@/components/shared/page-header";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { useIsMeteringOnly, useTenantCurrency } from "@/hooks/use-tenant-config";
import { tenantDefinedLabel } from "@/lib/localisation";
import { taskStatusLabel } from "@/lib/task-status";
import { TASK_STATUS_VALUES } from "@/lib/vocabulary";

import { useKindsOfWork, useRuns } from "../api/queries";
import { kindKeysForRuns, type RunsSearch } from "../lib/runs";
import { RunsTable } from "./runs-table";
import { TasksNav } from "./tasks-nav";

export interface RunsPageProps {
  /** URL-backed: the route passes it down and receives changes back. */
  search: RunsSearch;
  onSearchChange: (next: RunsSearch) => void;
}

/**
 * /tasks/runs — every top-level run of a kind of work, newest first.
 *
 * RUNS ARE A SIBLING OF KINDS OF WORK, NOT THE FRONT DOOR (#424, spec §25 Q2):
 * the nav under the header is what makes the two one tab. A run of contained
 * work is not listed here — it belongs to the run containing it, and the
 * listing counts whole pieces of work rather than what is inside them, which
 * is the route's own rule.
 *
 * Two filters, each a wire parameter the route already takes: the kind of
 * work and the lifecycle state. The state filter is the ONE grouping this
 * surface offers, and it groups by the registry's states exactly — an expired
 * run is under "Expired" and nowhere else (#187 §7).
 */
export function RunsPage({ search, onSearchChange }: RunsPageProps) {
  const currency = useTenantCurrency();
  const meteringOnly = useIsMeteringOnly();
  const kinds = useKindsOfWork();
  const runs = useRuns({ task_type: search.task_type, status: search.status });
  const narrowed = search.task_type !== undefined || search.status !== undefined;
  const update = (patch: Partial<RunsSearch>) => onSearchChange({ ...search, ...patch });

  return (
    <div className="space-y-4">
      <PageHeader
        title="Runs"
        description="Every run of a kind of work — what it cost, what it earned, and how it ended."
      />
      <TasksNav current="runs" />

      <RunsFilters
        search={search}
        kinds={kindKeysForRuns(kinds.data ?? [])}
        narrowed={narrowed}
        onChange={update}
      />

      {runs.isInitialLoading ? (
        <Card size="sm" className="p-3">
          <div className="space-y-2">
            <Skeleton className="h-8 w-full" />
            <Skeleton className="h-8 w-full" />
            <Skeleton className="h-8 w-full" />
          </div>
        </Card>
      ) : runs.isError ? (
        <ErrorCard
          error={runs.error}
          onRetry={() => void runs.refetch()}
          title="Couldn't load your runs"
        />
      ) : runs.rows.length === 0 ? (
        <EmptyState
          icon={ListChecks}
          title={narrowed ? "No runs match these filters" : "No runs yet"}
          description={
            narrowed
              ? "Nothing ran under that kind of work in that state. Clear the filters to see every run."
              : "A run reports here the moment your code starts one. Declare a kind of work first, then start work of that kind from the SDK."
          }
          action={
            narrowed
              ? {
                  label: "Show every run",
                  onClick: () => update({ task_type: undefined, status: undefined }),
                }
              : undefined
          }
        />
      ) : (
        <Card size="sm" className="gap-0 py-0">
          <RunsTable runs={runs.rows} currency={currency} meteringOnly={meteringOnly} />
          <LoadMore
            shownCount={runs.rows.length}
            hasMore={runs.hasMore}
            isFetchingNextPage={runs.isFetchingNextPage}
            onLoadMore={runs.fetchNextPage}
            noun="runs"
          />
        </Card>
      )}
    </div>
  );
}

const ANY = "any";

function RunsFilters({
  search,
  kinds,
  narrowed,
  onChange,
}: {
  search: RunsSearch;
  kinds: readonly string[];
  narrowed: boolean;
  onChange: (patch: Partial<RunsSearch>) => void;
}) {
  return (
    <div className="flex flex-wrap items-end gap-4">
      <div className="space-y-1">
        <Label className="text-[11px] text-text-muted">Kind of work</Label>
        <Select
          value={search.task_type ?? ANY}
          onValueChange={(value) =>
            onChange({
              task_type: typeof value === "string" && value !== ANY ? value : undefined,
            })
          }
        >
          <SelectTrigger className="h-8 w-[190px] text-[12px]" aria-label="Kind of work">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ANY}>Any kind</SelectItem>
            {kinds.map((key) => (
              <SelectItem key={key} value={key}>
                {tenantDefinedLabel(key)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="space-y-1">
        <Label className="text-[11px] text-text-muted">State</Label>
        <Select
          value={search.status ?? ANY}
          onValueChange={(value) =>
            onChange({ status: TASK_STATUS_VALUES.find((status) => status === value) })
          }
        >
          <SelectTrigger className="h-8 w-[150px] text-[12px]" aria-label="State">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ANY}>Any state</SelectItem>
            {TASK_STATUS_VALUES.map((status) => (
              <SelectItem key={status} value={status}>
                {taskStatusLabel(status)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {narrowed && (
        <Button
          variant="ghost"
          size="sm"
          onClick={() => onChange({ task_type: undefined, status: undefined })}
        >
          Clear filters
        </Button>
      )}
    </div>
  );
}
