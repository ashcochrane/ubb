// The full receipt for one usage event: identity, timing, money, metrics,
// tags, stop context, metadata, and the pricing-provenance "why this amount".
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

import { useUsageEvent } from "../api/queries";
import { asStopContextEntries, type UsageEventDetail } from "../api/types";
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

function metricRows(detail: UsageEventDetail): Array<[string, string]> {
  return Object.entries(detail.usage_metrics).map(([metric, quantity]) => [
    metric,
    typeof quantity === "number" ? quantity.toLocaleString() : String(quantity),
  ]);
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
  const margin = detail.billed_cost_micros - detail.provider_cost_micros;
  const metrics = metricRows(detail);
  const tags = detail.tags ?? {};
  const hasTags = Object.keys(tags).length > 0;
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
    ...(detail.product_id !== ""
      ? [{ label: "Product", value: detail.product_id }]
      : []),
    ...(detail.service_id !== ""
      ? [{ label: "Service", value: detail.service_id }]
      : []),
    ...(detail.agent_id !== ""
      ? [{ label: "Agent", value: detail.agent_id }]
      : []),
  ];

  const moneyItems: DetailItem[] = [
    {
      label: "Billed",
      value: formatEventMicros(detail.billed_cost_micros, detail.currency),
    },
    {
      label: "Provider cost",
      value: formatEventMicros(detail.provider_cost_micros, detail.currency),
    },
    {
      label: "Margin on this event",
      value: formatSignedEventMicros(margin, detail.currency),
    },
    { label: "Currency", value: detail.currency.toUpperCase() },
    ...(detail.units !== null && detail.units !== undefined
      ? [{ label: "Units", value: detail.units.toLocaleString() }]
      : []),
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
          <Section title="Cost">
            <DetailList items={moneyItems} />
          </Section>

          {metrics.length > 0 && (
            <Section
              title="Usage metrics"
              description="The measured quantities this event was priced on."
            >
              <DetailList
                items={metrics.map(([metric, quantity]) => ({
                  label: metric,
                  value: quantity,
                }))}
              />
            </Section>
          )}

          {hasTags && (
            <Section title="Tags">
              <DetailList
                items={Object.entries(tags).map(([key, value]) => ({
                  label: key,
                  value: String(value),
                  mono: true,
                }))}
              />
            </Section>
          )}
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
