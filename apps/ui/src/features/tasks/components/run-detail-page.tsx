import { Link } from "@tanstack/react-router";
import { ArrowLeft, ListChecks } from "lucide-react";

import { ApiProblem } from "@/api/problem";
import { CopyButton } from "@/components/shared/copy-button";
import { DetailList } from "@/components/shared/detail-list";
import { EmptyState } from "@/components/shared/empty-state";
import { ErrorCard } from "@/components/shared/error-card";
import { PageHeader } from "@/components/shared/page-header";
import { Section } from "@/components/shared/section";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useIsMeteringOnly, useTenantCurrency } from "@/hooks/use-tenant-config";
import { formatDate, formatEventCount, formatMicros, shortId } from "@/lib/format";
import { tenantDefinedLabel } from "@/lib/localisation";
import { TASK_STATUS_EXPLANATIONS } from "@/lib/task-status";

import { useRun } from "../api/queries";
import type { RunDetail } from "../api/types";
import {
  CONTAINED_ROWS_SHOWN_INLINE,
  describeAgreedPrice,
  describeRunTotals,
  outcomeReasonLabel,
  readAgreedPrice,
  readCustomerPrice,
  readSupplierCost,
  soldAtOnePrice,
  type PriceApplicability,
} from "../lib/runs";
import { CustomerPriceReadingView, SupplierCostReadingView } from "./amount-reading";
import { ContainedWorkTable } from "./contained-work-table";
import { RunStatusBadge } from "./run-status-badge";

/**
 * /tasks/runs/{task_id} — one run, as a routed object a colleague can be sent
 * to (#424): how it ended, what it cost and earned, and the work contained in
 * it. A piece of contained work is a run too and has the same page, with the
 * run containing it named at the top.
 *
 * ⚠ THE REGIME IS THE CONTAINING RUN'S, AND IT IS FETCHED BEFORE ANY AMOUNT IS
 * READ. Contained work never pins a price of its own — one agreed price buys
 * the whole unit of work — so a piece opened on its own page cannot say from
 * its own row whether a customer price applies; only the run containing it
 * can. Reading the child's own null pinned price answered "priced per event"
 * for revenue that does not apply, which rendered as `$0.00` — found by
 * review, not by any test, because the test for this page never asserted the
 * money. It does now.
 */
export function RunDetailPage({ taskId }: { taskId: string }) {
  const run = useRun(taskId);
  const parentId = run.data?.parent_task_id ?? null;
  const parent = useRun(parentId ?? "", { enabled: parentId !== null });
  const currency = useTenantCurrency();
  const meteringOnly = useIsMeteringOnly();

  const loading = run.isLoading || (parentId !== null && parent.isLoading);
  const failure = run.isError ? run.error : parentId !== null && parent.isError ? parent.error : null;
  const containing = parentId === null ? run.data : parent.data;

  return (
    <div className="space-y-4">
      <Link
        to="/tasks/runs"
        className="inline-flex items-center gap-1 text-[12px] text-text-secondary hover:text-text-primary"
      >
        <ArrowLeft className="h-3.5 w-3.5" /> All runs
      </Link>

      {loading ? (
        <Card size="sm" className="p-3">
          <div className="space-y-2">
            <Skeleton className="h-8 w-1/3" />
            <Skeleton className="h-8 w-full" />
            <Skeleton className="h-8 w-full" />
          </div>
        </Card>
      ) : failure !== null ? (
        run.isError && isNotFound(run.error) ? (
          <EmptyState
            icon={ListChecks}
            title="No run with that id"
            description={`Nothing in this workspace ran as ${taskId}. It may belong to another workspace, or the id may be mistyped.`}
          />
        ) : (
          <ErrorCard
            error={failure}
            onRetry={() => {
              void run.refetch();
              if (parentId !== null) void parent.refetch();
            }}
            title="Couldn't load this run"
          />
        )
      ) : run.data && containing ? (
        <RunDetailBody
          detail={run.data}
          currency={currency}
          applicability={{ meteringOnly, soldAtOnePrice: soldAtOnePrice(containing) }}
        />
      ) : null}
    </div>
  );
}

/** The route answers 404 for an id nobody has, and for one belonging to somebody else. */
function isNotFound(error: unknown): boolean {
  return error instanceof ApiProblem && error.status === 404;
}

function RunDetailBody({
  detail,
  currency,
  applicability,
}: {
  detail: RunDetail;
  currency: string;
  /** Decided from the CONTAINING run (this one, unless it is contained work) and the posture. */
  applicability: PriceApplicability;
}) {
  const supplierCost = readSupplierCost(detail);
  const customerPrice = readCustomerPrice(detail, applicability);
  const agreedPrice = readAgreedPrice(detail);
  // The route always sends the list (an empty one for a run with nothing in
  // it); the generated type leaves the key optional because the schema gives
  // it a default. Nothing about money is being coalesced here.
  const contained = detail.subtasks ?? [];

  return (
    <>
      <PageHeader
        title={`Run ${shortId(detail.task_id)}`}
        description={
          detail.task_type
            ? `${tenantDefinedLabel(detail.task_type)} · started ${formatDate(detail.created_at)}`
            : `Started ${formatDate(detail.created_at)}`
        }
        actions={<RunStatusBadge status={detail.status} />}
      />

      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[12px]">
        <span className="inline-flex items-center gap-1.5">
          <span className="break-all font-mono text-text-primary">{detail.task_id}</span>
          <CopyButton value={detail.task_id} label="Copy run ID" />
        </span>
        {detail.parent_task_id && (
          <span className="text-text-secondary">
            Contained in run{" "}
            <Link
              to="/tasks/runs/$taskId"
              params={{ taskId: detail.parent_task_id }}
              title={detail.parent_task_id}
              className="font-mono text-text-primary underline-offset-2 hover:underline"
            >
              {shortId(detail.parent_task_id)}
            </Link>
          </span>
        )}
      </div>

      <Section title="How it ended" description={TASK_STATUS_EXPLANATIONS[detail.status]}>
        <DetailList
          items={[
            { label: "State", value: <RunStatusBadge status={detail.status} /> },
            ...(detail.outcome_reason
              ? [
                  {
                    label: "Reason",
                    value: (
                      <span>
                        {outcomeReasonLabel(detail.outcome_reason)}
                        {detail.reason_detail && (
                          <span className="block text-[12px] text-text-secondary">
                            {detail.reason_detail}
                          </span>
                        )}
                      </span>
                    ),
                  },
                ]
              : []),
            { label: "Started", value: formatDate(detail.created_at) },
            {
              label: "Ended",
              value: detail.completed_at ? formatDate(detail.completed_at) : "Still running",
            },
          ]}
        />
      </Section>

      <Section title="What it cost and earned" description={describeRunTotals(applicability)}>
        <DetailList
          items={[
            { label: "Events", value: formatEventCount(detail.event_count) },
            {
              label: "Supplier cost",
              value: (
                <SupplierCostReadingView
                  reading={supplierCost}
                  currency={currency}
                  layout="detail"
                />
              ),
            },
            {
              label: "Customer price",
              value: (
                <CustomerPriceReadingView
                  reading={customerPrice}
                  currency={currency}
                  layout="detail"
                />
              ),
            },
            ...(agreedPrice
              ? [
                  {
                    label: "Agreed price",
                    value: describeAgreedPrice(agreedPrice, currency, applicability),
                  },
                ]
              : []),
            {
              label: "Ceiling",
              value:
                detail.provider_cost_limit_micros != null
                  ? formatMicros(detail.provider_cost_limit_micros, currency)
                  : "Uncapped",
            },
          ]}
        />
      </Section>

      <Section
        title="Contained work"
        description={`Work started under this run, one row each, with a roll-up over all of it. The run's own totals above include everything here, plus any events reported against the run itself. At most ${CONTAINED_ROWS_SHOWN_INLINE} rows show at once; the roll-up counts every one, shown or not.`}
      >
        <ContainedWorkTable
          contained={contained}
          currency={currency}
          applicability={applicability}
        />
      </Section>
    </>
  );
}
