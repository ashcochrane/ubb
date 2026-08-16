// The full receipt for one usage event: identity, timing, money, measurements,
// stop context, the open metadata bag, and the pricing-provenance "why this
// amount".
//
// The detail response does NOT carry the customer's id — the ledger link
// forwards it as a search param. Without it the refund action is hidden
// (refunds POST to /billing/customers/{customer_id}/refund).

import { ArrowLeft } from "lucide-react";

import { CopyButton } from "@/components/shared/copy-button";
import { DetailList, type DetailItem } from "@/components/shared/detail-list";
import { ErrorCard } from "@/components/shared/error-card";
import { PageHeader } from "@/components/shared/page-header";
import { Skeleton } from "@/components/ui/skeleton";
import { useHasProduct } from "@/hooks/use-tenant-config";
import { formatDate } from "@/lib/format";
import { ABSENT_LABEL } from "@/lib/localisation";
import {
  COSTING_STATUS_EXPLANATIONS,
  costingStatusLabel,
  unresolvedReasonLabel,
} from "@/lib/supplier-cost";

import { useUsageEvent } from "../api/queries";
import { asStopContextEntries, type UsageEventDetail } from "../api/types";
import {
  MEASUREMENTS_STATUS_EXPLANATIONS,
  NO_QUANTITIES_RECORDED,
  measurementsStatusLabel,
} from "../lib/measurements";
import { formatEventMicros, formatSignedEventMicros } from "../lib/money";
import { shortId } from "../lib/search";
import { KeyValueTree } from "./key-value-tree";
import { RefundAction } from "./refund-action";
import { Section } from "./section";
import { StopContextTimeline } from "./stop-context-timeline";
import { TaskSection } from "./task-section";

export interface EventDetailPageProps {
  eventId: string;
  customerId?: string;
  onBack: () => void;
}

function BackLink({ onBack }: { onBack: () => void }) {
  return (
    <button
      type="button"
      onClick={onBack}
      className="inline-flex items-center gap-1 text-[12px] text-text-secondary transition-colors hover:text-text-primary"
    >
      <ArrowLeft className="h-3.5 w-3.5" strokeWidth={1.5} />
      Back to events
    </button>
  );
}

function idItem(label: string, value: string): DetailItem {
  return {
    label,
    mono: true,
    value: (
      <span className="inline-flex max-w-full items-center gap-1.5">
        <span className="break-all">{value}</span>
        <CopyButton value={value} label={`Copy ${label.toLowerCase()}`} />
      </span>
    ),
  };
}

function measurementRows(detail: UsageEventDetail): Array<[string, string]> {
  return Object.entries(detail.measurements).map(([key, quantity]) => [
    key,
    typeof quantity === "number" ? quantity.toLocaleString() : String(quantity),
  ]);
}

/**
 * The measured quantities, or why there are none.
 *
 * READ THE STATUS FIRST, and read it before the bag — the same order the
 * registry's own decision rule is written in. This section used to render only
 * when the bag had entries, which meant the two states with an empty bag
 * disappeared off the page: a customer whose measurement detail was removed at
 * its retention horizon saw a receipt that looked exactly like one for a Task
 * that was never measured, and both looked like nothing had happened. The
 * quantities are the answer for one of the three states, not the subject of the
 * section.
 */
function Measurements({ detail }: { detail: UsageEventDetail }) {
  const status = detail.measurements_status;
  const rows = measurementRows(detail);
  return (
    <Section
      title="Usage measurements"
      description={MEASUREMENTS_STATUS_EXPLANATIONS[status]}
    >
      {status !== "available" ? (
        <p className="text-[12px] text-text-muted">
          {measurementsStatusLabel(status)}
        </p>
      ) : rows.length > 0 ? (
        <DetailList
          items={rows.map(([key, quantity]) => ({
            label: key,
            value: quantity,
          }))}
        />
      ) : (
        // Only reachable with the record present and holding nothing, which is
        // the one state this sentence is true of.
        <p className="text-[12px] text-text-muted">{NO_QUANTITIES_RECORDED}</p>
      )}
    </Section>
  );
}

export function EventDetailPage({
  eventId,
  customerId,
  onBack,
}: EventDetailPageProps) {
  const event = useUsageEvent(eventId);
  const hasBilling = useHasProduct("billing");

  if (event.isLoading) {
    return (
      <div className="space-y-4">
        <BackLink onBack={onBack} />
        <Skeleton className="h-8 w-64" />
        <div className="grid gap-4 lg:grid-cols-2">
          <Skeleton className="h-72 w-full rounded-md" />
          <Skeleton className="h-72 w-full rounded-md" />
        </div>
      </div>
    );
  }

  if (event.isError || !event.data) {
    return (
      <div className="space-y-4">
        <BackLink onBack={onBack} />
        <ErrorCard
          error={event.error}
          onRetry={() => void event.refetch()}
          title="Couldn't load this event"
        />
      </div>
    );
  }

  const detail = event.data;
  const stopEntries = asStopContextEntries(detail.stop_context);
  // A SUPPLIER COST UBB HAS NOT LEARNED IS ABSENT, NOT ZERO (#320). Both rows
  // below fall back to the console's absent marker rather than to a number:
  // rendering `£0.00` would state that the call was free, and a margin computed
  // against that zero would read as the whole billed amount — the flattering
  // direction, on the one screen a tenant opens to check a single event.
  //
  // AND THE ABSENCE IS NAMED (#330). A dash says something is not there; the
  // status says WHICH not-there this is, because a cost UBB could not learn and
  // a cost there was never going to be are opposite facts wearing the same
  // empty cell. There is no "at least" on this screen and that is not an
  // omission: one event has no total to be a floor of — it has the mark itself.
  const providerCost = detail.provider_cost_micros ?? null;
  const margin =
    providerCost === null ? null : detail.billed_cost_micros - providerCost;
  const hasMetadata = Object.keys(detail.metadata).length > 0;
  const hasProvenance = Object.keys(detail.pricing_provenance).length > 0;
  const backfilled =
    detail.created_at.slice(0, 10) !== detail.effective_at.slice(0, 10);

  const identityItems: DetailItem[] = [
    idItem("Event ID", detail.id),
    idItem("Request ID", detail.request_id),
    idItem("Idempotency key", detail.idempotency_key),
    { label: "Happened at", value: formatDate(detail.effective_at) },
    {
      label: "Recorded at",
      value: backfilled
        ? `${formatDate(detail.created_at)} (backfilled)`
        : formatDate(detail.created_at),
    },
    ...(detail.event_type !== ""
      ? [{ label: "Event type", value: detail.event_type }]
      : []),
    ...(detail.provider !== ""
      ? [{ label: "Provider", value: detail.provider }]
      : []),
    // The posting's grouping values, labelled with the key the tenant declared
    // (#277). This used to be three rows reading "Dimension 1..3" — console
    // English for a slot number the tenant never chose, and only ever three of
    // the ten that exist. The response is now keyed by the declared key, so the
    // label is the tenant's own word and every declared field shows up.
    ...Object.entries(detail.grouping_fields).map(([key, value]) => ({
      label: key,
      value,
    })),
  ];

  const moneyItems: DetailItem[] = [
    {
      label: "Billed",
      value: formatEventMicros(detail.billed_cost_micros, detail.currency),
    },
    {
      label: "Provider cost",
      value:
        providerCost === null
          ? ABSENT_LABEL
          : formatEventMicros(providerCost, detail.currency),
    },
    { label: "Cost status", value: costingStatusLabel(detail.costing_status) },
    // Read only where the status is `unresolved`, and never on its own: a
    // status saying a cost is missing without saying WHAT would settle it is a
    // shrug rather than something a tenant can act on.
    ...(detail.costing_status === "unresolved"
      ? [
          {
            label: "Missing input",
            value: unresolvedReasonLabel(detail.unresolved_reason),
          },
        ]
      : []),
    {
      label: "Margin on this event",
      value:
        margin === null
          ? ABSENT_LABEL
          : formatSignedEventMicros(margin, detail.currency),
    },
    { label: "Currency", value: detail.currency.toUpperCase() },
  ];

  return (
    <div className="space-y-4">
      <BackLink onBack={onBack} />
      <PageHeader
        title="Event receipt"
        description={`Event ${shortId(detail.id)} — recorded ${formatDate(detail.created_at)}`}
        actions={
          customerId !== undefined && hasBilling ? (
            <RefundAction detail={detail} customerId={customerId} />
          ) : undefined
        }
      />

      <div className="grid items-start gap-4 lg:grid-cols-2">
        <Section title="Details">
          <DetailList items={identityItems} />
        </Section>

        <div className="space-y-4">
          <Section
            title="Cost"
            description={COSTING_STATUS_EXPLANATIONS[detail.costing_status]}
          >
            <DetailList items={moneyItems} />
          </Section>

          <Measurements detail={detail} />
        </div>

        {stopEntries.length > 0 && (
          <Section
            title="Stop context"
            description="This event landed past a spend stop. It was still recorded and billed — every event that reaches UBB is."
          >
            <StopContextTimeline entries={stopEntries} />
          </Section>
        )}

        {detail.task_id && <TaskSection taskId={detail.task_id} />}

        {hasMetadata && (
          <Section title="Metadata" className="lg:col-span-2">
            <KeyValueTree value={detail.metadata} />
          </Section>
        )}

        <Section
          title="Pricing provenance"
          description="Why this amount — the pricing engine's recorded receipt."
          className="lg:col-span-2"
        >
          {hasProvenance ? (
            <KeyValueTree value={detail.pricing_provenance} mono />
          ) : (
            <p className="text-[12px] text-text-muted">
              No provenance was recorded for this event.
            </p>
          )}
        </Section>
      </div>
    </div>
  );
}
