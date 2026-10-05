// What a Verify run answered (#581): where it ran, the verdict and what it
// speaks for, the first refusal if the run stopped, then every
// acknowledgement as given.
//
// ⚠ "VERIFIED" IS SAID ONLY OF THE WHOLE BLUEPRINT, AND ONLY OF RECORDING AND
// COSTING (owner ruling on #599). A partial run lists what it left out and is
// never presented as verified (`presentedAsVerified`), and the verdict always
// says it proves no price — each recording's price status reports that.
//
// ⚠ EVERY ID HERE NAMES A RECORD THAT NO LONGER EXISTS. The run is built in a
// workspace that is rolled back, so the ids are the answer's and nothing else's.
// The answer carries no credential, and nothing here renders one.

import { Badge } from "@/components/ui/badge";
import { formatDate, formatEventCount, formatEventMicros } from "@/lib/format";
import { tenantDefinedLabel } from "@/lib/localisation";
import { partialTotalNote } from "@/lib/supplier-cost";
import { taskStatusLabel } from "@/lib/task-status";
import { describeTotal, readTotal } from "@/lib/total-reading";

import type {
  BlueprintVerification,
  CloseTaskResponse,
  StartTaskResponse,
  VerificationRecord,
  VerificationUnit,
} from "../api/types";
import { altitudeLabel, CALL_TITLES, taskOutcomeLabel, VERIFIED_SCOPE } from "../lib/code-builder-words";
import { presentedAsVerified } from "../lib/verification";
import { AcknowledgementCard } from "./acknowledgement-card";
import { Fingerprint } from "./fingerprint";

export function VerificationResult({
  result,
  currency,
}: {
  result: BlueprintVerification;
  currency: string;
}) {
  const refusal = result.refusal ?? null;
  return (
    <section aria-label="Verify result" className="space-y-4">
      <Verdict result={result} />
      <Environment result={result} />
      {refusal !== null && (
        <div role="alert" className="space-y-1 rounded-md border border-border p-3">
          <p className="text-[13px] font-medium text-text-primary">
            The run stopped at its first refusal, at{" "}
            <code className="font-mono text-[12px]">{refusal.operation_id}</code>.
          </p>
          <p className="text-[12px] text-text-secondary">
            {refusal.problem.title} (<code className="font-mono">{refusal.problem.code}</code>)
            {refusal.problem.detail ? `: ${refusal.problem.detail}` : ""}
          </p>
          <p className="text-[12px] text-text-secondary">What ran before it is below, as answered.</p>
        </div>
      )}
      <div className="space-y-3">
        <h4 className="text-[12px] font-medium text-text-primary">The work it started</h4>
        <Unit altitude="task" unit={result.task} currency={currency} />
        {result.subtasks.map((unit, index) => (
          <Unit key={`${unit.task_type}:${index}`} altitude="subtask" unit={unit} currency={currency} />
        ))}
      </div>
      <div className="space-y-3">
        <h4 className="text-[12px] font-medium text-text-primary">What it recorded</h4>
        {result.records.length === 0 && (
          <p className="text-[12px] text-text-secondary">Nothing: the run stopped before any recording.</p>
        )}
        {result.records.map((record, index) => (
          <RecordAnswer key={`${record.event_type}:${index}`} record={record} currency={currency} />
        ))}
      </div>
    </section>
  );
}

function Verdict({ result }: { result: BlueprintVerification }) {
  const verified = presentedAsVerified(result);
  const incomplete = result.records.filter((record) => !record.complete).length;
  const leftOut = [
    ...result.unexercised_event_types.map((key) => `Event Type ${tenantDefinedLabel(key)}`),
    ...result.unexercised_subtask_types.map((key) => `Subtask kind ${tenantDefinedLabel(key)}`),
  ];
  return (
    <div role="status" className="space-y-1.5 rounded-md border border-border p-3" data-verified={verified}>
      <p className="text-[13px] font-medium text-text-primary">
        {verified
          ? "Verified: every Event Type and Subtask kind this Blueprint selects was recorded and costed completely."
          : "Not verified."}
      </p>
      {!verified && (
        <ul aria-label="Why it is not verified" className="list-disc space-y-0.5 pl-5 text-[12px] text-text-secondary">
          {(result.refusal ?? null) !== null && <li>The run was refused before it finished.</li>}
          {leftOut.length > 0 && (
            <li>
              {`This run left out ${leftOut.join(", ")}. A run that leaves part of the Blueprint out never verifies it.`}
            </li>
          )}
          {incomplete > 0 && (
            <li>{`${incomplete} of ${result.records.length} recordings are incomplete.`}</li>
          )}
          {(result.refusal ?? null) === null && leftOut.length === 0 && incomplete === 0 && (
            <li>The platform did not verify it.</li>
          )}
        </ul>
      )}
      <p className="text-[12px] text-text-secondary">{VERIFIED_SCOPE}</p>
    </div>
  );
}

function Environment({ result }: { result: BlueprintVerification }) {
  const { environment } = result;
  return (
    <div className="space-y-1.5">
      <dl aria-label="Where it ran" className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-[12px]">
        <dt className="text-text-secondary">Environment</dt>
        <dd>
          {environment.discarded
            ? "A workspace built from the stored Blueprint for this run alone, then discarded"
            : "A workspace built from the stored Blueprint for this run alone, and not discarded"}
        </dd>
        <dt className="text-text-secondary">Blueprint</dt>
        <dd className="min-w-0">
          <Fingerprint value={result.configuration_fingerprint} />
        </dd>
        <dt className="text-text-secondary">Customer</dt>
        <dd>
          <code className="font-mono">{environment.customer_external_id}</code>
          {" — made up for the run; no stored cost rule names a customer"}
        </dd>
        <dt className="text-text-secondary">Rules in effect from</dt>
        <dd>{formatDate(environment.rules_effective_at)}</dd>
      </dl>
      {environment.discarded && (
        <p className="text-[12px] text-text-secondary">
          Every id below names a record that no longer exists: the run was discarded with
          everything it made.
        </p>
      )}
    </div>
  );
}

function Unit({
  altitude,
  unit,
  currency,
}: {
  altitude: "task" | "subtask";
  unit: VerificationUnit;
  currency: string;
}) {
  const title = `${altitudeLabel(altitude)} · ${tenantDefinedLabel(unit.task_type)}`;
  const start = unit.start ?? null;
  const close = unit.close ?? null;
  return (
    <article aria-label={title} className="space-y-1.5 rounded-md border border-border p-3 text-[12px]">
      <p className="text-[13px] font-medium text-text-primary">{title}</p>
      {start === null ? (
        <p className="text-text-secondary">Not started: the run was refused first.</p>
      ) : (
        <Started start={start} />
      )}
      {close === null ? (
        start !== null && <p className="text-text-secondary">Not closed.</p>
      ) : (
        <Closed close={close} currency={currency} />
      )}
    </article>
  );
}

function Started({ start }: { start: StartTaskResponse }) {
  return (
    <p className="text-text-secondary">
      {`Started — ${taskStatusLabel(start.status)}${start.replayed ? ", a replay" : ""}. Id `}
      <code className="font-mono">{start.task_id}</code>
    </p>
  );
}

function Closed({ close, currency }: { close: CloseTaskResponse; currency: string }) {
  const stillUnknown = partialTotalNote(close.unresolved_event_count);
  return (
    <dl aria-label="Closed" className="grid grid-cols-2 gap-x-4 gap-y-1 sm:grid-cols-4">
      <div>
        <dt className="text-[11px] text-text-muted">Outcome</dt>
        <dd>{`${taskOutcomeLabel(close.outcome)} — ${taskStatusLabel(close.status)}`}</dd>
      </div>
      <div>
        <dt className="text-[11px] text-text-muted">Events</dt>
        <dd>{formatEventCount(close.event_count)}</dd>
      </div>
      <div>
        <dt className="text-[11px] text-text-muted">Total provider cost</dt>
        <dd>
          {describeTotal(
            readTotal(close.total_provider_cost_micros, close.unresolved_event_count),
            currency,
            formatEventMicros,
          )}
        </dd>
      </div>
      <div>
        <dt className="text-[11px] text-text-muted">Total billed</dt>
        <dd>
          {describeTotal(
            readTotal(close.total_billed_cost_micros, close.unpriced_event_count),
            currency,
            formatEventMicros,
          )}
        </dd>
      </div>
      {stillUnknown !== null && <p className="col-span-full text-text-secondary">{stillUnknown}</p>}
    </dl>
  );
}

function RecordAnswer({ record, currency }: { record: VerificationRecord; currency: string }) {
  const under = record.subtask_type ?? null;
  const title = `${CALL_TITLES.record_usage} · ${tenantDefinedLabel(record.event_type)}${
    under === null ? "" : ` · under ${tenantDefinedLabel(under)}`
  }`;
  const acknowledgement = record.acknowledgement ?? null;
  const replay = record.replay ?? null;
  return (
    <article aria-label={title} className="space-y-2 rounded-md border border-border p-3">
      <div className="flex flex-wrap items-center gap-2">
        <p className="text-[13px] font-medium text-text-primary">{title}</p>
        <Badge variant={record.complete ? "secondary" : "outline"}>
          {record.complete ? "Recorded completely" : "Incomplete"}
        </Badge>
      </div>
      {record.missing_required_measurement_keys.length > 0 && (
        <p className="text-[12px] text-text-secondary">
          {"Required Measurements missing: "}
          {record.missing_required_measurement_keys.map((key, index) => (
            <span key={key}>
              {index > 0 && ", "}
              <code className="font-mono">{tenantDefinedLabel(key)}</code>
            </span>
          ))}
        </p>
      )}
      {acknowledgement === null ? (
        <p className="text-[12px] text-text-secondary">Not recorded: the run stopped before it.</p>
      ) : (
        <AcknowledgementCard title="Acknowledgement" response={acknowledgement} currency={currency} />
      )}
      {replay !== null && (
        <>
          <AcknowledgementCard title="Replay of the same request" response={replay} currency={currency} replay />
          {acknowledgement !== null && (
            <p className="text-[12px] text-text-secondary">
              {replay.event_id === acknowledgement.event_id
                ? "The replay names the same event as the acknowledgement: sending it again recorded nothing new."
                : "The replay names a different event from the acknowledgement."}
            </p>
          )}
        </>
      )}
    </article>
  );
}
