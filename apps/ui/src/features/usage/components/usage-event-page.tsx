import type { ReactNode } from "react";
import { useNavigate } from "@tanstack/react-router";
import { ArrowLeft } from "lucide-react";
import { PageHeader } from "@/components/shared/page-header";
import { Button } from "@/components/ui/button";
import {
  QueryState,
  Section,
  DetailGrid,
  DetailRow,
} from "@/components/shared/data-states";
import { StatusBadge } from "@/components/shared/status-badge";
import { formatMicros, formatDate, humanizeLabel } from "@/lib/format";
import { useUsageEvent } from "../api/queries";

/** Format one untyped value: `*_micros` numbers as money, objects as JSON. */
function renderValue(key: string, value: unknown): ReactNode {
  if (value === null || value === undefined || value === "") {
    return <span className="text-muted-foreground">—</span>;
  }
  if (key.endsWith("_micros") && typeof value === "number") return formatMicros(value);
  if (typeof value === "object") {
    return <code className="text-xs break-all">{JSON.stringify(value)}</code>;
  }
  return String(value);
}

/** Render an untyped object as a key/value list (not a raw JSON dump). */
function KeyValueList({ data }: { data: Record<string, unknown> | null | undefined }) {
  const entries = data ? Object.entries(data) : [];
  if (entries.length === 0) {
    return <p className="text-sm text-muted-foreground">None.</p>;
  }
  return (
    <DetailGrid>
      {entries.map(([k, v]) => (
        <DetailRow key={k} label={humanizeLabel(k)}>
          {renderValue(k, v)}
        </DetailRow>
      ))}
    </DetailGrid>
  );
}

export function UsageEventPage({ eventId }: { eventId: string }) {
  const navigate = useNavigate();
  const query = useUsageEvent(eventId);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Usage event"
        actions={
          <Button variant="ghost" size="sm" onClick={() => navigate({ to: "/usage" })}>
            <ArrowLeft />
            Back
          </Button>
        }
      />

      <QueryState
        query={query}
        empty={{
          title: "Event not found",
          description: "This usage event could not be loaded. It may have been removed.",
        }}
      >
        {(ev) => {
          const markup = ev.billed_cost_micros - ev.provider_cost_micros;
          const stopContext = ev.stop_context ?? [];
          return (
            <div className="space-y-6">
              <Section title="Event">
                <DetailGrid>
                  <DetailRow label="Event ID">
                    <span className="font-mono text-xs break-all">{ev.id}</span>
                  </DetailRow>
                  <DetailRow label="Request ID">
                    <span className="font-mono text-xs break-all">{ev.request_id}</span>
                  </DetailRow>
                  <DetailRow label="Idempotency key">
                    <span className="font-mono text-xs break-all">{ev.idempotency_key}</span>
                  </DetailRow>
                  <DetailRow label="Event type">
                    {ev.event_type ? (
                      <StatusBadge value={ev.event_type} tone="neutral" />
                    ) : (
                      "—"
                    )}
                  </DetailRow>
                  <DetailRow label="Provider">{ev.provider || "—"}</DetailRow>
                  <DetailRow label="Product ID">{ev.product_id || "—"}</DetailRow>
                  <DetailRow label="Service ID">{ev.service_id || "—"}</DetailRow>
                  <DetailRow label="Agent ID">{ev.agent_id || "—"}</DetailRow>
                  <DetailRow label="Units">
                    {ev.units != null ? ev.units.toLocaleString() : "—"}
                  </DetailRow>
                  <DetailRow label="Currency">{ev.currency?.toUpperCase() || "—"}</DetailRow>
                  <DetailRow label="Task ID">
                    {ev.task_id ? (
                      <span className="font-mono text-xs break-all">{ev.task_id}</span>
                    ) : (
                      "—"
                    )}
                  </DetailRow>
                  <DetailRow label="Effective at">{formatDate(ev.effective_at)}</DetailRow>
                  <DetailRow label="Created at">{formatDate(ev.created_at)}</DetailRow>
                </DetailGrid>
              </Section>

              <Section
                title="Cost & margin"
                description="Provider cost is what upstream charged you; billed is the customer charge; markup is the difference."
              >
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
                  <div className="rounded-lg bg-muted p-3">
                    <div className="text-xs text-muted-foreground">Provider cost</div>
                    <div className="mt-1 text-lg font-semibold">
                      {formatMicros(ev.provider_cost_micros)}
                    </div>
                  </div>
                  <div className="rounded-lg bg-muted p-3">
                    <div className="text-xs text-muted-foreground">Billed (customer charge)</div>
                    <div className="mt-1 text-lg font-semibold">
                      {formatMicros(ev.billed_cost_micros)}
                    </div>
                  </div>
                  <div className="rounded-lg bg-muted p-3">
                    <div className="text-xs text-muted-foreground">Markup (billed − provider)</div>
                    <div className="mt-1 text-lg font-semibold">{formatMicros(markup)}</div>
                  </div>
                </div>
              </Section>

              {stopContext.length > 0 && (
                <Section
                  title="Stop context"
                  description="Spend-control stop signals attached to this event."
                >
                  <code className="block whitespace-pre-wrap break-all text-xs">
                    {JSON.stringify(stopContext, null, 2)}
                  </code>
                </Section>
              )}

              <Section title="Usage metrics">
                <KeyValueList data={ev.usage_metrics} />
              </Section>

              <Section title="Pricing provenance">
                <KeyValueList data={ev.pricing_provenance} />
              </Section>

              <Section title="Tags">
                <KeyValueList data={ev.tags} />
              </Section>

              <Section title="Metadata">
                <KeyValueList data={ev.metadata} />
              </Section>
            </div>
          );
        }}
      </QueryState>
    </div>
  );
}
