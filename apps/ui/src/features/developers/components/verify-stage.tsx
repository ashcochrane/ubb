// Verify: run the Blueprint on screen once, with sample values (#581).
//
// Verify is the page's fourth stage and reads the page's own Blueprint query:
// no second resolution, and no second copy of the selection. It is offered
// only for a stored Blueprint whose verdict is `complete`; otherwise the stage
// says why in the Blueprint's own words and offers nothing.
//
// ⚠ SAMPLES ARE NOT URL STATE (§12). What the developer types lives in this
// form and goes out in one request; the answer lives in the mutation. Neither
// is ever written to the address, so neither reaches the history or a copied
// link.
//
// ⚠ A RESULT BELONGS TO THE FINGERPRINT AND THE EXACT REQUEST IT RAN WITH
// (owner review of #601). The Blueprint re-resolves on focus and on return;
// when it resolves to another fingerprint, the last result — answer or
// refusal — is said to be about a different Blueprint, cause-neutrally, and is
// never shown as the current one's. An edit to the samples that changes the
// request clears it: a Grouping Field sample can select another Cost Rate, a
// Measurement sample changes what is recorded, and an Event Type left out makes
// the run partial, so an answer is evidence about the request that produced it
// and no other. Verify proves the Blueprint on screen, not the files a
// developer took from an earlier one.
//
// Verify is never fused into the renderer, and it changes no configuration
// and no code.

import { zodResolver } from "@hookform/resolvers/zod";
import type { UseQueryResult } from "@tanstack/react-query";
import { useEffect, useId, useState, type ReactNode } from "react";
import { useForm, useWatch } from "react-hook-form";

import { ErrorCard } from "@/components/shared/error-card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useHasRole } from "@/hooks/use-current-role";
import { useTenantCurrency } from "@/hooks/use-tenant-config";
import { tenantDefinedLabel } from "@/lib/localisation";

import { useVerifyBlueprint, type VerifyInput } from "../api/queries";
import type { Blueprint, BlueprintVerificationRequest } from "../api/types";
import { shownValue } from "../lib/blueprint";
import {
  altitudeLabel,
  CALL_TITLES,
  CURRENCY_SAMPLE,
  diagnosticCodeLabel,
  readinessLabel,
  STALE_RESULT_WARNING,
  SUPPLIER_COST_SAMPLE,
} from "../lib/code-builder-words";
import {
  blankSamples,
  DECIMAL_SENT_WHOLE,
  groupingFieldsAsked,
  refusalOf,
  sampleFormSchema,
  standingOf,
  verificationKey,
  verificationRequestOf,
  verifyOfferOf,
  type ResultStanding,
  type SamplePlan,
  type SampleValues,
  type VerifyOffer,
  type VerifyRefusal,
} from "../lib/verification";
import { ShownValue } from "./blueprint-stage";
import { Fingerprint } from "./fingerprint";
import { VerificationResult } from "./verification-result";

const LEGEND = "text-[12px] font-medium text-text-primary";
const HINT = "text-[12px] text-text-secondary";
const CONTROL = "block w-full max-w-xs rounded-md border border-border bg-bg-surface px-2 py-1.5 text-[13px]";
const ERROR = "text-xs text-destructive";

export function VerifyStage({
  query,
  held,
}: {
  query: UseQueryResult<Blueprint>;
  /** The fingerprint of the files the developer last took, if any. */
  held: string | undefined;
}) {
  const verify = useVerifyBlueprint();
  const canWrite = useHasRole("write");
  const currency = useTenantCurrency();
  // What was typed, per fingerprint: component state, never the address. It
  // outlives the form, so returning to a Blueprint brings its samples back —
  // and with them the answer they were sent with.
  const [samples, setSamples] = useState<ReadonlyMap<string, SampleValues>>(() => new Map());

  if (query.isPending) return <Skeleton className="h-24 w-full" />;
  const blueprint = query.data;
  if (blueprint === undefined) {
    return <p className={HINT}>Nothing to verify until the Blueprint resolves.</p>;
  }
  const offer = verifyOfferOf(blueprint);
  const plan = offer.kind === "offered" ? offer.plan : null;
  const typed = plan === null ? null : (samples.get(plan.fingerprint) ?? blankSamples(plan));
  const sent: VerifyInput | undefined = verify.variables;

  /**
   * Keep what was typed; and where the edit changes the request an answer on
   * screen was sent with, clear that answer (owner review of #601). An edit to
   * another Blueprint's samples leaves it alone: that answer is already shown
   * as about a different Blueprint.
   */
  const onSamplesChange = (edited: SamplePlan, values: SampleValues) => {
    setSamples((previous) => new Map(previous).set(edited.fingerprint, values));
    if (
      sent !== undefined &&
      sent.fingerprint === edited.fingerprint &&
      verificationKey(edited.fingerprint, verificationRequestOf(edited, values)) !==
        verificationKey(sent.fingerprint, sent.body)
    ) {
      verify.reset();
    }
  };

  return (
    <div className="space-y-5" aria-busy={query.isPlaceholderData}>
      <Offer
        offer={offer}
        blueprint={blueprint}
        held={held}
        canWrite={canWrite}
        // While a new selection resolves, the Blueprint on screen is the last
        // one's: nothing is sent for it.
        resolving={query.isPlaceholderData}
        pending={verify.isPending}
        typed={typed}
        onSamplesChange={onSamplesChange}
        onVerify={(fingerprint, body) => verify.mutate({ fingerprint, body })}
      />
      {sent !== undefined && !verify.isPending && (
        <Outcome
          standing={standingOf(
            { fingerprint: verify.data?.configuration_fingerprint ?? sent.fingerprint, body: sent.body },
            blueprint,
            plan === null || typed === null ? null : verificationRequestOf(plan, typed),
          )}
        >
          {verify.isError ? (
            <Refused refusal={refusalOf(verify.error)} onResolveAgain={() => void query.refetch()} />
          ) : verify.data !== undefined ? (
            <VerificationResult result={verify.data} currency={currency} />
          ) : null}
        </Outcome>
      )}
    </div>
  );
}

function Offer({
  offer,
  blueprint,
  held,
  canWrite,
  resolving,
  pending,
  typed,
  onSamplesChange,
  onVerify,
}: {
  offer: VerifyOffer;
  blueprint: Blueprint;
  held: string | undefined;
  canWrite: boolean;
  resolving: boolean;
  pending: boolean;
  /** What was typed for the Blueprint on screen, or blank samples. */
  typed: SampleValues | null;
  onSamplesChange: (plan: SamplePlan, values: SampleValues) => void;
  onVerify: (fingerprint: string, body: BlueprintVerificationRequest) => void;
}) {
  switch (offer.kind) {
    case "draft_preview":
      return (
        <p role="note" className={HINT}>
          A draft preview cannot be verified: it is stored nowhere, so it has no fingerprint
          for Verify to run. Verify runs a published Blueprint.
        </p>
      );
    case "not_complete":
      return (
        <div role="note" className="space-y-1">
          <p className={HINT}>
            {`Verify runs a complete Blueprint only, and this one is ${readinessLabel(offer.readiness)}.`}
          </p>
          {blueprint.diagnostics.length > 0 && (
            <ul aria-label="What it is waiting for" className={`list-disc pl-5 ${HINT}`}>
              {blueprint.diagnostics.map((diagnostic, index) => (
                <li key={`${diagnostic.code}:${index}`}>
                  {diagnosticCodeLabel(diagnostic.code)}
                  {diagnostic.key != null && (
                    <>
                      {" — "}
                      <code className="font-mono">{tenantDefinedLabel(diagnostic.key)}</code>
                    </>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
      );
    case "offered":
      return (
        <div className="space-y-3">
          <p className={HINT}>
            Runs this Blueprint once — start, each recording, close — in a workspace built
            from the stored Blueprint and discarded afterwards, with the samples you give
            below. It changes no configuration and no code.
          </p>
          <HeldNote held={held} fingerprint={offer.plan.fingerprint} />
          {canWrite ? (
            <SampleForm
              // A new fingerprint is a new Blueprint: its form starts from what
              // was typed for it, or blank.
              key={offer.plan.fingerprint}
              plan={offer.plan}
              initial={typed ?? blankSamples(offer.plan)}
              disabled={resolving}
              pending={pending}
              onChange={(values) => onSamplesChange(offer.plan, values)}
              onVerify={(body) => onVerify(offer.plan.fingerprint, body)}
            />
          ) : (
            <p role="note" className={HINT}>
              Verifying needs the write role.
            </p>
          )}
        </div>
      );
  }
}

/** Where the files taken differ from the Blueprint on screen, Verify says it proves only the latter. */
function HeldNote({ held, fingerprint }: { held: string | undefined; fingerprint: string }) {
  if (held === undefined) return null;
  if (held === fingerprint) {
    return (
      <p role="note" className={HINT}>
        The files you took were generated from this Blueprint. Verify runs the Blueprint, not
        the files.
      </p>
    );
  }
  return (
    <p role="note" className={HINT} data-held-differs>
      Verify runs the Blueprint on this page, <Fingerprint value={fingerprint} />. The files
      you took were generated from <Fingerprint value={held} />, so a result here says
      nothing about them.
    </p>
  );
}

function SampleForm({
  plan,
  initial,
  disabled,
  pending,
  onChange,
  onVerify,
}: {
  plan: SamplePlan;
  initial: SampleValues;
  disabled: boolean;
  pending: boolean;
  /** Every edit, as the whole of what is typed now. */
  onChange: (values: SampleValues) => void;
  onVerify: (body: BlueprintVerificationRequest) => void;
}) {
  const form = useForm<SampleValues>({
    resolver: zodResolver(sampleFormSchema(plan)),
    defaultValues: initial,
  });
  useEffect(
    () => form.subscribe({ formState: { values: true }, callback: () => onChange(form.getValues()) }),
    [form, onChange],
  );
  const records = useWatch({ control: form.control, name: "records" });
  const asked = new Set(groupingFieldsAsked(plan, { groupingFields: [], records }));
  const errors = form.formState.errors;
  const submit = form.handleSubmit((values) => onVerify(verificationRequestOf(plan, values)));

  return (
    <form onSubmit={(event) => void submit(event)} className="space-y-4" aria-label="Samples">
      {/* Locked while a run is in flight: its answer is about these samples. */}
      <fieldset disabled={pending} className="min-w-0 space-y-4">
      <p className={HINT}>
        Samples go out with this one request and are kept nowhere else — not in the address,
        and not in the page&apos;s history.
      </p>
      {asked.size > 0 && (
        <fieldset className="space-y-2">
          <legend className={LEGEND}>Grouping Field samples</legend>
          <p className={HINT}>
            Each value your code passes when it starts the work. Verify never makes one up.
          </p>
          {plan.groupingFields.map((field, index) =>
            asked.has(index) ? (
              <Field
                key={field.key}
                label={tenantDefinedLabel(field.key)}
                mono
                hint={`Required by ${field.requiredBy
                  .map((kind) => `the ${altitudeLabel(kind.altitude)} kind ${tenantDefinedLabel(kind.kind)}`)
                  .join(" and ")}`}
                error={errors.groupingFields?.[index]?.message}
              >
                {(id) => (
                  <input id={id} type="text" className={CONTROL} {...form.register(`groupingFields.${index}`)} />
                )}
              </Field>
            ) : null,
          )}
        </fieldset>
      )}
      {plan.records.map((record, index) => (
        <fieldset key={`${record.eventType}:${index}`} className="space-y-2 rounded-md border border-border p-3">
          <legend className={LEGEND}>
            {`${CALL_TITLES.record_usage} · ${tenantDefinedLabel(record.eventType)}`}
          </legend>
          <label className="flex items-center gap-2 text-[13px]">
            <input type="checkbox" {...form.register(`records.${index}.included`)} />
            Include in this run
          </label>
          {plan.subtasks.length > 0 && (
            <Field label="Recorded under">
              {(id) => (
                <select id={id} className={CONTROL} {...form.register(`records.${index}.subtaskType`)}>
                  <option value="">
                    {plan.task === null
                      ? "The work itself"
                      : `The work itself · ${tenantDefinedLabel(plan.task.kind)}`}
                  </option>
                  {plan.subtasks.map((kind) => (
                    <option key={kind.kind} value={kind.kind}>
                      {`${altitudeLabel("subtask")} · ${tenantDefinedLabel(kind.kind)}`}
                    </option>
                  ))}
                </select>
              )}
            </Field>
          )}
          {record.measurements.map((measurement, position) => (
            <Field
              key={measurement.code}
              label={tenantDefinedLabel(measurement.code)}
              mono
              hint={
                <>
                  {measurement.facts.map(({ argument, place }) => (
                    <span key={argument.name}>
                      {/* A declared fact: never a value this version
                          cannot generate, which only a value token is. */}
                      <ShownValue shown={shownValue(argument, place, false)} />
                    </span>
                  ))}
                  <span>
                    {measurement.valueType === "decimal"
                      ? DECIMAL_SENT_WHOLE
                      : "A whole number; leave it blank to send none."}
                  </span>
                </>
              }
              error={errors.records?.[index]?.measurements?.[position]?.message}
            >
              {(id) => (
                <input
                  id={id}
                  type="text"
                  inputMode="numeric"
                  className={CONTROL}
                  {...form.register(`records.${index}.measurements.${position}`)}
                />
              )}
            </Field>
          ))}
          {record.costField !== null && (
            <Field
              label={SUPPLIER_COST_SAMPLE[record.costField].label}
              hint={SUPPLIER_COST_SAMPLE[record.costField].hint}
              error={errors.records?.[index]?.providerCost?.message}
            >
              {(id) => (
                <input
                  id={id}
                  type="text"
                  inputMode="numeric"
                  className={CONTROL}
                  {...form.register(`records.${index}.providerCost`)}
                />
              )}
            </Field>
          )}
          {record.readsCurrency && (
            <Field
              label={CURRENCY_SAMPLE.label}
              hint={CURRENCY_SAMPLE.hint}
              error={errors.records?.[index]?.currency?.message}
            >
              {(id) => (
                <input
                  id={id}
                  type="text"
                  maxLength={3}
                  autoComplete="off"
                  className={CONTROL}
                  {...form.register(`records.${index}.currency`)}
                />
              )}
            </Field>
          )}
        </fieldset>
      ))}
      {errors.records?.message && (
        <p role="alert" className={ERROR}>
          {errors.records.message}
        </p>
      )}
      <Button type="submit" size="sm" disabled={disabled || pending}>
        {pending ? "Verifying…" : "Verify this Blueprint"}
      </Button>
      </fieldset>
    </form>
  );
}

/**
 * One sample's field: its label bound to the control by id, so the control's
 * accessible name is the label alone — a declared key, never the hints beside
 * it — and its hint and its error below.
 */
function Field({
  label,
  mono = false,
  hint,
  error,
  children,
}: {
  label: string;
  mono?: boolean;
  hint?: ReactNode;
  error?: string;
  children: (id: string) => ReactNode;
}) {
  const id = useId();
  return (
    <div className="space-y-1">
      <label htmlFor={id} className={`block text-[12px] ${mono ? "font-mono" : ""}`}>
        {label}
      </label>
      {children(id)}
      {hint !== undefined && <div className={`flex flex-wrap gap-x-2 ${HINT}`}>{hint}</div>}
      {error !== undefined && <p className={ERROR}>{error}</p>}
    </div>
  );
}

/**
 * The last outcome, shown only while it is about what is on screen: the same
 * fingerprint and the same request. Edited samples clear it; another
 * fingerprint is said, cause-neutrally, and shows nothing of it.
 */
function Outcome({ standing, children }: { standing: ResultStanding; children: ReactNode }) {
  if (standing.kind === "current") return <>{children}</>;
  if (standing.kind === "another_request") return null;
  return (
    <div role="status" className="space-y-1 rounded-md border border-border p-3" data-stale-result>
      <p className="text-[13px] font-medium text-text-primary">{STALE_RESULT_WARNING}</p>
      <p className={HINT}>
        It ran against <Fingerprint value={standing.ranAgainst} />;{" "}
        {standing.current === null ? (
          "the current Blueprint is a draft preview, which has no fingerprint."
        ) : (
          <>
            the current Blueprint is <Fingerprint value={standing.current} />.
          </>
        )}{" "}
        It says nothing about the current one.
      </p>
    </div>
  );
}

/** A refusal before anything ran: a precondition the request did not meet. */
function Refused({ refusal, onResolveAgain }: { refusal: VerifyRefusal; onResolveAgain: () => void }) {
  switch (refusal.kind) {
    case "not_found":
      return (
        <RefusalBox title="This Blueprint is not stored any more, so nothing ran.">
          <p className={HINT}>
            A Blueprint is kept for 30 days after it was last resolved. Resolving again stores
            it under the same fingerprint only if your configuration still resolves to exactly
            this Blueprint; otherwise generate the files again, because the ones you have
            describe a Blueprint that no longer resolves.
          </p>
          <Button size="sm" variant="outline" onClick={onResolveAgain}>
            Resolve again
          </Button>
        </RefusalBox>
      );
    case "event_type_not_available":
      return (
        <RefusalBox title="The stored Blueprint does not publish every Event Type this run claims, so nothing ran.">
          <ul aria-label="Not available" className={`list-disc pl-5 ${HINT}`}>
            {refusal.eventTypes.map((key) => (
              <li key={key}>
                <code className="font-mono">{tenantDefinedLabel(key)}</code>
              </li>
            ))}
          </ul>
        </RefusalBox>
      );
    case "not_complete":
      return (
        <RefusalBox title="The stored Blueprint is not complete, so it cannot be verified and nothing ran.">
          {refusal.detail !== null && <p className={HINT}>{refusal.detail}</p>}
        </RefusalBox>
      );
    case "invalid":
      return (
        <RefusalBox title="The request was refused before anything ran.">
          {refusal.detail !== null && <p className={HINT}>{refusal.detail}</p>}
        </RefusalBox>
      );
    case "forbidden":
      return <RefusalBox title="Verifying needs the write role, so nothing ran." />;
    case "other":
      return <ErrorCard error={refusal.error} title="Couldn't verify the Blueprint" />;
  }
}

function RefusalBox({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div role="alert" className="space-y-2 rounded-md border border-border p-3" data-refusal>
      <p className="text-[13px] font-medium text-text-primary">{title}</p>
      {children}
    </div>
  );
}
