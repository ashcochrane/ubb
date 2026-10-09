// One recording's acknowledgement, as UBB returned it (#581; story 70).
//
// Lifted from the test-event console's response card, which #581 deleted with
// the console: Verify renders each acknowledgement and each replay through it.
// What it already applied it still applies — #537 and story 70:
//
//   - a null amount is NO FIGURE, never `0`: the cell names the status that
//     left it empty (#330 for the supplier cost, #371 for the customer price);
//   - statuses are shown as given, beside the amounts — so #473's confident
//     price over an unresolved cost is shown as the response states it, not
//     reconciled here;
//   - the Pricing Receipt, `uncosted_measurement_keys` and the stop fields
//     (`event_id`, `stop_scope`, `stop_reason`, and #569's `trigger_source`,
//     `stop_bound_micros` and `stop_measured_micros`, #585) render as
//     returned: the mechanism through the open-set rule, each figure signed
//     at an event's precision, and one that does not apply as no figure.
//
// On a replay of the same request the task totals are null BY DESIGN — a
// replay adds nothing to the work — and the card says so rather than reading
// the absence as a failure.

import type { ReactNode } from "react";
import { AlertTriangle, OctagonAlert } from "lucide-react";

import { CodeBlock } from "@/components/shared/code-block";
import { CopyButton } from "@/components/shared/copy-button";
import { OpenSetValue } from "@/components/shared/open-set-value";
import { Absent } from "@/components/shared/reading";
import { Badge } from "@/components/ui/badge";
import {
  notApplicableReasonLabel,
  pricingMethodLabel,
  pricingStatusLabel,
  settledPriceMicros,
} from "@/lib/customer-price";
import { formatEventMicros, formatMicros } from "@/lib/format";
import { stopScopeLabel } from "@/lib/labels";
import { costingStatusLabel, unresolvedReasonLabel } from "@/lib/supplier-cost";
import { describeTotal, readTotal, type TotalReading } from "@/lib/total-reading";
import { REASON_CODE_LABEL_KEYS, TRIGGER_SOURCE_LABEL_KEYS } from "@/lib/vocabulary";

import type { RecordUsageResponse } from "../api/types";

/** What a replay's empty task totals mean, said where they would be. */
export const REPLAY_TASK_TOTALS = "Not reported on a replay — expected: a replay adds nothing to the work.";

export function AcknowledgementCard({
  title,
  response,
  currency,
  replay = false,
}: {
  title: string;
  response: RecordUsageResponse;
  currency: string;
  /** The same request sent again: its task totals are null by design. */
  replay?: boolean;
}) {
  const settledPrice = settledPriceMicros(response);
  return (
    <div
      role="group"
      aria-label={title}
      className="space-y-3 rounded-lg border border-border bg-bg-surface p-3"
    >
      <div className="flex items-start justify-between gap-2">
        <p className="text-[13px] font-medium text-text-primary">{title}</p>
        <span className="inline-flex items-center gap-1.5 font-mono text-[11px] text-text-secondary">
          <span className="max-w-[140px] truncate" title={response.event_id}>
            {response.event_id}
          </span>
          <CopyButton value={response.event_id} label="Copy event id" />
        </span>
      </div>

      <dl className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-[12px] sm:grid-cols-3">
        {/* Both statuses as the response gives them, beside the amounts. */}
        <ResponseStat label="Costing status" value={costingStatusLabel(response.costing_status)} />
        <ResponseStat label="Price status" value={pricingStatusLabel(response.pricing_status)} />
        {/* An absent customer price is NAMED here too, on the same argument as
            the supplier cost below and one slice later (#351, #371): three of
            the four statuses null this column, they mean different things, and
            a bare dash cannot tell them apart.

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
        {response.pricing_method != null && (
          <ResponseStat label="Pricing method" value={pricingMethodLabel(response.pricing_method)} />
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
        <TaskTotals response={response} currency={currency} replay={replay} />
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
            Measurements without a Cost Rate
          </p>
          <div className="flex flex-wrap gap-1">
            {(response.uncosted_measurement_keys ?? []).map((key) => (
              <Badge key={key} variant="outline" className="font-mono">
                {key}
              </Badge>
            ))}
          </div>
          {/* An uncosted measurement does not add zero: the whole event's
              supplier cost is unresolved until a rate exists (#320). */}
          <p className="text-[11px] text-text-secondary">
            The event was recorded, and its supplier cost is unknown rather than
            zero. A Cost Rate for each of these resolves it.
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
            {/* The stop word through the console's one open-set rule (#466):
                a registry value in the catalogue's words, anything else as
                the token the verdict carried, marked unrecognised. */}
            <ResponseStat
              label="Reason"
              value={
                <OpenSetValue labelKeys={REASON_CODE_LABEL_KEYS} value={response.stop_reason} />
              }
            />
            <ResponseStat label="Scope" value={stopScopeLabel(response.stop_scope)} />
            {/* How the stop was applied and what it was measured on (#569,
                #585), exactly as the acknowledgement carries them: the
                mechanism through the same open-set rule as the reason, and
                each figure at an event's precision with its sign — a hard
                floor's are negative. Nothing here is worked out, and a field
                that does not apply to this stop is NO FIGURE, never `0`. */}
            <ResponseStat
              label="Applied by"
              value={
                <OpenSetValue labelKeys={TRIGGER_SOURCE_LABEL_KEYS} value={response.trigger_source} />
              }
            />
            <ResponseStat
              label="Bound"
              value={<StopFigure micros={response.stop_bound_micros} currency={currency} />}
            />
            <ResponseStat
              label="Measured"
              value={<StopFigure micros={response.stop_measured_micros} currency={currency} />}
            />
          </dl>
          <p className="text-[11px] leading-relaxed text-text-secondary">
            The HTTP status was still 200 — by design. The stop instruction
            rides the response body instead of the status code. Your
            integration should read <span className="font-mono">stop</span>,{" "}
            <span className="font-mono">stop_reason</span>, and{" "}
            <span className="font-mono">stop_scope</span> and halt the named
            scope. <span className="font-mono">trigger_source</span>,{" "}
            <span className="font-mono">stop_bound_micros</span> and{" "}
            <span className="font-mono">stop_measured_micros</span> say how the
            stop was applied and what it was measured against; a dash is a
            field that does not apply to this stop, never a zero.
          </p>
        </div>
      )}

      {response.pricing_receipt != null && (
        <details className="text-[12px]">
          <summary className="cursor-pointer text-text-secondary">Pricing Receipt</summary>
          <CodeBlock value={JSON.stringify(response.pricing_receipt, null, 2)} className="mt-2" />
        </details>
      )}
    </div>
  );
}

/**
 * The work's running totals as of this recording. Each is a total beside the
 * count of what it left out, read once (`@/lib/total-reading`): a figure, a
 * floor, or unknown — never `$0.00` for an amount nobody knows.
 *
 * ⚠ A TOTAL IS READ ONLY WITH ITS OWN COUNT. The contract makes each nullable
 * on its own, and a count defaulted to zero would turn a total of unknown
 * completeness into a whole one. Where either half is missing, that total is
 * not shown at all.
 */
function TaskTotals({
  response,
  currency,
  replay,
}: {
  response: RecordUsageResponse;
  currency: string;
  replay: boolean;
}) {
  const cost = readPair(response.task_total_provider_cost_micros, response.task_total_unresolved_event_count);
  const price = readPair(response.task_total_billed_cost_micros, response.task_total_unpriced_event_count);
  if (cost === null && price === null) {
    return replay ? <ResponseStat label="Task totals" value={REPLAY_TASK_TOTALS} /> : null;
  }
  return (
    <>
      {cost !== null && (
        <ResponseStat label="Task provider cost so far" value={describeTotal(cost, currency, formatEventMicros)} />
      )}
      {price !== null && (
        <ResponseStat label="Task billed so far" value={describeTotal(price, currency, formatEventMicros)} />
      )}
    </>
  );
}

/**
 * One of a stop's figures — its bound, or the amount measured against it — as
 * the acknowledgement carries it: the amount at an event's precision, signed,
 * or, where the figure does not apply to this stop, no figure at all.
 */
function StopFigure({ micros, currency }: { micros: number | null | undefined; currency: string }) {
  return micros == null ? <Absent /> : <>{formatEventMicros(micros, currency)}</>;
}

/** A total and the count of what it left out, read together or not at all. */
function readPair(micros: number | null | undefined, leftOut: number | null | undefined): TotalReading | null {
  return micros == null || leftOut == null ? null : readTotal(micros, leftOut);
}

function ResponseStat({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div>
      <dt className="text-[11px] text-text-muted">{label}</dt>
      <dd className="text-[12px] font-medium text-text-primary">{value}</dd>
    </div>
  );
}
