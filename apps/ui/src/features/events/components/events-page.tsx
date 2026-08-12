// The event ledger: analytics strip + daily chart for the window, a
// per-customer ledger with past-limit/tag filters, and (when the past-limit
// filter is on) the past-limit report. All state is URL-backed — the route
// passes `search` down and receives changes back.

import { Users } from "lucide-react";

import { DateRangePicker } from "@/components/shared/date-range-picker";
import { EmptyState } from "@/components/shared/empty-state";
import { ErrorCard } from "@/components/shared/error-card";
import { LoadMore } from "@/components/shared/load-more";
import { PageHeader } from "@/components/shared/page-header";
import { Skeleton } from "@/components/ui/skeleton";
import { useTenantCurrency } from "@/hooks/use-tenant-config";
import { resolveRange } from "@/lib/date-range";
import { TIMESERIES_GROUP_BY } from "@/lib/labels";

import { useUsageLedger } from "../api/queries";
import type { UsageListFilters } from "../api/types";
import { pastLimitWindow, type EventsSearch } from "../lib/search";
import { AnalyticsStrip } from "./analytics-strip";
import { CustomerScopeCard } from "./customer-scope-card";
import { EventFilters } from "./event-filters";
import { LedgerTable } from "./ledger-table";
import { PastLimitPanel } from "./past-limit-panel";
import { TimeseriesCard } from "./timeseries-card";

export interface EventsPageProps {
  search: EventsSearch;
  onSearchChange: (next: EventsSearch) => void;
  onOpenEvent: (eventId: string, customerId: string) => void;
  onGoToCustomers?: () => void;
}

function LedgerSkeleton() {
  return (
    <div className="space-y-2 p-3">
      {Array.from({ length: 8 }, (_, index) => (
        <Skeleton key={index} className="h-9 w-full" />
      ))}
    </div>
  );
}

export function EventsPage({
  search,
  onSearchChange,
  onOpenEvent,
  onGoToCustomers,
}: EventsPageProps) {
  const currency = useTenantCurrency();
  const customerId = search.customer_id;
  const window = resolveRange({
    start_date: search.start_date,
    end_date: search.end_date,
  });
  const update = (patch: Partial<EventsSearch>) =>
    onSearchChange({ ...search, ...patch });

  // Tag filters only apply as a pair (the API ignores a lone key/value).
  const tagPairActive =
    search.tag_key !== undefined && search.tag_value !== undefined;
  const filters: UsageListFilters = {
    tag_key: tagPairActive ? search.tag_key : undefined,
    tag_value: tagPairActive ? search.tag_value : undefined,
    past_limit: search.past_limit,
    stop_scope: search.stop_scope,
    episode_seq: search.episode_seq,
  };
  const anyFilterActive =
    tagPairActive ||
    search.past_limit !== undefined ||
    search.stop_scope !== undefined ||
    search.episode_seq !== undefined;

  const ledger = useUsageLedger(customerId, filters);

  return (
    <div className="space-y-5">
      <PageHeader
        title="Events"
        description="Everything that was tracked — what happened, what it cost, and what needs attention."
        actions={
          <DateRangePicker
            value={{ start_date: search.start_date, end_date: search.end_date }}
            onChange={(range) =>
              update({ start_date: range.start_date, end_date: range.end_date })
            }
          />
        }
      />

      <AnalyticsStrip
        params={{
          ...window,
          customer_id: customerId,
          past_limit: search.past_limit,
          stop_scope: search.stop_scope,
          episode_seq: search.episode_seq,
        }}
        tagFilterActive={tagPairActive}
      />

      <TimeseriesCard
        window={window}
        customerId={customerId}
        groupBy={search.group_by}
        onGroupByChange={(groupBy) =>
          // Narrow the picker's string back into the schema's grouping enum.
          update({
            group_by: TIMESERIES_GROUP_BY.find((option) => option === groupBy),
          })
        }
      />

      <CustomerScopeCard
        customerId={customerId}
        onSelect={(next) => update({ customer_id: next })}
        onGoToCustomers={onGoToCustomers}
      />

      {customerId === undefined ? (
        <EmptyState
          icon={Users}
          title="Pick a customer to see their ledger"
          description="The event ledger is scoped to one customer at a time. Choose a customer above — the totals and chart keep covering the whole workspace until you do."
        />
      ) : (
        <>
          {search.past_limit === true && (
            <PastLimitPanel
              customerId={customerId}
              window={pastLimitWindow(window)}
            />
          )}

          <div className="rounded-md border border-border bg-bg-surface">
            <div className="border-b border-border px-3 py-2.5">
              <EventFilters search={search} onChange={update} />
            </div>

            {ledger.isInitialLoading ? (
              <LedgerSkeleton />
            ) : ledger.isError ? (
              <ErrorCard
                error={ledger.error}
                onRetry={() => void ledger.refetch()}
                title="Couldn't load the ledger"
                className="m-3"
              />
            ) : ledger.rows.length === 0 ? (
              <EmptyState
                className="m-3"
                title={
                  anyFilterActive
                    ? "No events match these filters"
                    : "No events recorded yet"
                }
                description={
                  anyFilterActive
                    ? "Try widening the date window or clearing a filter."
                    : "Events appear here the moment usage is recorded for this customer via the API."
                }
                action={
                  anyFilterActive
                    ? {
                        label: "Clear filters",
                        onClick: () =>
                          update({
                            past_limit: undefined,
                            stop_scope: undefined,
                            episode_seq: undefined,
                            tag_key: undefined,
                            tag_value: undefined,
                          }),
                      }
                    : undefined
                }
              />
            ) : (
              <>
                <LedgerTable
                  rows={ledger.rows}
                  currency={currency}
                  onOpen={(row) => onOpenEvent(row.id, customerId)}
                />
                <LoadMore
                  shownCount={ledger.rows.length}
                  hasMore={ledger.hasMore}
                  isFetchingNextPage={ledger.isFetchingNextPage}
                  onLoadMore={ledger.fetchNextPage}
                  noun="events"
                />
              </>
            )}
          </div>
        </>
      )}
    </div>
  );
}
