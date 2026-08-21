// One priced response from the test console — the teaching moment. Shows the
// event id, both cost denominations, the balance after debit, warnings for the
// measurements nothing priced, and the STOP VERDICT block when stop=true (HTTP
// was still 200 — the one-rule contract).
//
// The Event Type key in the heading is the TENANT'S, and #279 renders it
// exactly as they declared it. This card used to title-case it, which is the
// worst place in the console to do so: an integrator reads it to learn what UBB
// recorded, and a key UBB reworded is one they cannot find again on any other
// surface.

import { AlertTriangle, OctagonAlert } from "lucide-react";

import { CopyButton } from "@/components/shared/copy-button";
import { Badge } from "@/components/ui/badge";
import {
  notApplicableReasonLabel,
  pricingStatusLabel,
  settledPriceMicros,
} from "@/lib/customer-price";
import { formatDate, formatMicros } from "@/lib/format";
import { stopReasonLabel, stopScopeLabel } from "@/lib/labels";
import { tenantDefinedLabel } from "@/lib/localisation";
import { costingStatusLabel, unresolvedReasonLabel } from "@/lib/supplier-cost";

import type { RecordUsageResponse } from "../api/types";
import { formatEventMicros } from "../lib/money";

export interface TestEventEntry {
  /** Local entry id (event_id can repeat on idempotent replays). */
  id: string;
  at: string;
  eventType: string;
  response: RecordUsageResponse;
}

export function TestEventResponseCard({
  entry,
  currency,
}: {
  entry: TestEventEntry;
  currency: string;
}) {
  const { response } = entry;
  const settledPrice = settledPriceMicros(response);
  return (
    <div className="space-y-3 rounded-lg border border-border bg-bg-surface p-3">
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="text-[13px] font-medium text-text-primary">
            {entry.eventType ? tenantDefinedLabel(entry.eventType) : "Usage event"}{" "}
            recorded
          </p>
          <p className="text-[11px] text-text-muted">{formatDate(entry.at)}</p>
        </div>
        <span className="inline-flex items-center gap-1.5 font-mono text-[11px] text-text-secondary">
          <span className="max-w-[140px] truncate" title={response.event_id}>
            {response.event_id}
          </span>
          <CopyButton value={response.event_id} label="Copy event id" />
        </span>
      </div>

      <dl className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-[12px] sm:grid-cols-3">
        {/* An absent customer price is NAMED here too, on the same argument as
            the supplier cost below and one slice later (#351, #371). It used to
            fall back to a bare dash, which is the asymmetry #330 fixed on the
            cost half and left standing on this one: three of the four statuses
            null this column, they mean different things, and an integrator
            reading this card cannot tell them apart from the absence.

            ⚠ IT ASKS `settledPriceMicros`, NOT THE COLUMN. A zero beside
            `waived` would render as money under a null test and as the decided
            loss it is under this one. */}
        <ResponseStat
          label="Billed cost"
          value={
            settledPrice !== null
              ? formatEventMicros(settledPrice, currency)
              : pricingStatusLabel(response.pricing_status)
          }
        />
        {response.pricing_status === "not_applicable" &&
          response.not_applicable_reason != null && (
            <ResponseStat
              label="Why"
              value={notApplicableReasonLabel(response.not_applicable_reason)}
            />
          )}
        {/* An absent supplier cost is NAMED here, never zeroed (#320, #330).
            This card is what an integrator reads to learn what UBB recorded, so
            a dash that could mean "could not learn it" or "never had one" is
            the one place those must not look alike. */}
        <ResponseStat
          label="Provider cost"
          value={
            response.provider_cost_micros != null
              ? formatEventMicros(response.provider_cost_micros, currency)
              : costingStatusLabel(response.costing_status)
          }
        />
        {response.costing_status === "unresolved" && (
          <ResponseStat
            label="Missing input"
            value={unresolvedReasonLabel(response.unresolved_reason)}
          />
        )}
        {response.new_balance_micros != null && (
          <ResponseStat
            label="Balance after"
            value={formatMicros(response.new_balance_micros, currency)}
          />
        )}
      </dl>

      {response.suspended && (
        <p className="text-[12px] text-text-secondary">
          The billing owner is suspended — the event still recorded.
        </p>
      )}

      {(response.uncosted_measurement_keys ?? []).length > 0 && (
        <div className="space-y-1.5 rounded-md border border-dashed border-border p-2.5">
          <p className="inline-flex items-center gap-1.5 text-[12px] font-medium text-text-primary">
            <AlertTriangle className="h-3.5 w-3.5" strokeWidth={1.5} />
            Measurements without a cost card
          </p>
          <div className="flex flex-wrap gap-1">
            {(response.uncosted_measurement_keys ?? []).map((key) => (
              <Badge key={key} variant="outline" className="font-mono">
                {key}
              </Badge>
            ))}
          </div>
          {/* The old copy said these "contributed nothing to cost", which was
              true when an uncosted measurement silently added zero. It does not
              add zero any more: the whole event's supplier cost is unresolved
              until a rate exists (#320). */}
          <p className="text-[11px] text-text-secondary">
            The event was recorded, and its supplier cost is unknown rather than
            zero. Add a rate for these to a cost card to resolve it.
          </p>
        </div>
      )}

      {response.stop && (
        <div className="space-y-2 rounded-md border-2 border-foreground/30 bg-bg-subtle p-3">
          <p className="inline-flex items-center gap-1.5 text-[13px] font-semibold text-text-primary">
            <OctagonAlert className="h-4 w-4" strokeWidth={1.75} />
            Stop verdict
          </p>
          <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-[12px]">
            <ResponseStat label="Reason" value={stopReasonLabel(response.stop_reason)} />
            <ResponseStat label="Scope" value={stopScopeLabel(response.stop_scope)} />
          </dl>
          <p className="text-[11px] leading-relaxed text-text-secondary">
            The HTTP status was still 200 — by design. Every event that reaches
            UBB is priced, recorded, and billed; the stop instruction rides the
            response body instead of the status code. Your integration should
            read <span className="font-mono">stop</span>,{" "}
            <span className="font-mono">stop_reason</span>, and{" "}
            <span className="font-mono">stop_scope</span> and halt the named
            scope.
          </p>
        </div>
      )}
    </div>
  );
}

function ResponseStat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-[11px] text-text-muted">{label}</dt>
      <dd className="text-[12px] font-medium text-text-primary">{value}</dd>
    </div>
  );
}
