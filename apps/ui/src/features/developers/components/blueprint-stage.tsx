// Blueprint: what the integration code must mean, read-only (#579).
//
// Every inferred fact is shown with the declaration it was read from — the
// provider, the costing method, each Measurement's type, unit and required
// flag, the required Grouping Fields, the kind's declared ceiling or
// `uncapped`, and its frozen pricing mode — and every one of them is a token
// of the Blueprint, read through `lib/blueprint.ts`. Nothing is re-derived
// here; a fact the Blueprint does not carry is not shown.

import type { UseQueryResult } from "@tanstack/react-query";

import { isForbidden } from "@/api/problem";
import { ErrorCard } from "@/components/shared/error-card";
import { OpenSetValue } from "@/components/shared/open-set-value";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useTenantCurrency } from "@/hooks/use-tenant-config";
import { formatDate, formatMicros } from "@/lib/format";
import { tenantDefinedLabel } from "@/lib/localisation";

import type { Blueprint, BlueprintArgument, BlueprintCall } from "../api/types";
import { notRenderableAddresses } from "ubb-codegen";

import {
  isNotRenderable,
  placesOf,
  screenFor,
  shownValue,
  type Shown,
  type TokenPlace,
} from "../lib/blueprint";
import {
  bindingClassLabel,
  callHeading,
  codeTargetLabel,
  objectKindLabel,
  readinessLabel,
} from "../lib/code-builder-words";
import { DiagnosticsList } from "./diagnostics-list";
import { Fingerprint } from "./fingerprint";
import { KindWebhooks } from "./kind-webhooks";
import { ScreenLink } from "./screen-link";

export function BlueprintStage({
  query,
  draftRequested,
  onLeaveDraftPreview,
}: {
  query: UseQueryResult<Blueprint>;
  draftRequested: boolean;
  onLeaveDraftPreview: () => void;
}) {
  if (query.isPending) return <Skeleton className="h-40 w-full" />;
  if (query.isError) {
    if (draftRequested && isForbidden(query.error)) {
      return (
        <div role="alert" className="space-y-2 rounded-md border border-border p-4">
          <p className="text-[13px] font-medium text-text-primary">
            A draft preview needs the admin role.
          </p>
          <p className="text-[12px] text-text-secondary">
            The published Blueprint is what production code is built from.
          </p>
          <Button size="sm" variant="outline" onClick={onLeaveDraftPreview}>
            Show the published Blueprint
          </Button>
        </div>
      );
    }
    return (
      <ErrorCard
        error={query.error}
        title="Couldn't resolve the Blueprint"
        onRetry={() => void query.refetch()}
      />
    );
  }
  const blueprint = query.data;
  const notRenderable = notRenderableAddresses(blueprint);
  return (
    <div className="space-y-5" aria-busy={query.isPlaceholderData}>
      <Verdict blueprint={blueprint} />
      <div className="space-y-2">
        <h3 className="text-[12px] font-medium text-text-primary">Diagnostics</h3>
        <DiagnosticsList diagnostics={blueprint.diagnostics} />
      </div>
      <div className="space-y-3">
        <h3 className="text-[12px] font-medium text-text-primary">Calls</h3>
        {blueprint.calls.map((call, index) => (
          <CallFacts
            key={`${call.operation_id}:${index}`}
            call={call}
            notRenderable={notRenderable}
          />
        ))}
      </div>
      <KindWebhooks blueprint={blueprint} />
    </div>
  );
}

function Verdict({ blueprint }: { blueprint: Blueprint }) {
  const fingerprint = blueprint.configuration_fingerprint ?? null;
  return (
    <div className="space-y-2">
      <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-[13px]">
        <dt className="text-text-secondary">Readiness</dt>
        <dd>
          <Badge variant={blueprint.readiness === "complete" ? "secondary" : "outline"}>
            {readinessLabel(blueprint.readiness)}
          </Badge>
        </dd>
        <dt className="text-text-secondary">Target</dt>
        <dd>
          {codeTargetLabel(blueprint.target)}
          {blueprint.sdk_major_version != null && ` · SDK version ${blueprint.sdk_major_version}`}
        </dd>
        <dt className="text-text-secondary">Configuration fingerprint</dt>
        <dd className="min-w-0">
          {fingerprint === null ? (
            <span className="text-text-secondary">None — a draft preview is stored nowhere</span>
          ) : (
            <Fingerprint value={fingerprint} />
          )}
        </dd>
      </dl>
      {fingerprint === null && (
        <p role="note" className="text-[12px] text-text-secondary">
          Draft preview — not production-ready. Resolved from draft declarations;
          it cannot be verified, and code generated from it is never current.
        </p>
      )}
    </div>
  );
}

function CallFacts({
  call,
  notRenderable,
}: {
  call: BlueprintCall;
  notRenderable: ReadonlySet<string>;
}) {
  const title = callHeading(call);
  const places = placesOf(call);
  return (
    <article aria-label={title} className="rounded-md border border-border">
      <header className="flex flex-wrap items-center gap-2 border-b border-border bg-bg-subtle px-3 py-2">
        <h4 className="text-[13px] font-medium text-text-primary">{title}</h4>
        <Badge variant="outline">{readinessLabel(call.readiness)}</Badge>
        <code className="font-mono text-[11px] text-text-secondary">{call.operation_id}</code>
      </header>
      <table className="w-full text-left text-[12px]">
        <thead className="text-text-secondary">
          <tr>
            <th className="px-3 py-1.5 font-medium">Token</th>
            <th className="px-3 py-1.5 font-medium">Value</th>
            <th className="px-3 py-1.5 font-medium">Bound</th>
            <th className="px-3 py-1.5 font-medium">Declared by</th>
          </tr>
        </thead>
        <tbody>
          {call.arguments.map((argument, index) => {
            const place: TokenPlace = places[index] ?? { kind: "field", field: argument.name };
            return (
              <TokenRow
                key={`${argument.name}:${index}`}
                argument={argument}
                place={place}
                notRenderable={isNotRenderable(call, place, notRenderable)}
              />
            );
          })}
        </tbody>
      </table>
    </article>
  );
}

function TokenRow({
  argument,
  place,
  notRenderable,
}: {
  argument: BlueprintArgument;
  place: TokenPlace;
  notRenderable: boolean;
}) {
  const screen = screenFor(argument, place);
  const provenance = argument.provenance ?? null;
  return (
    <tr className="border-t border-border align-top" data-token={argument.name}>
      <td className="px-3 py-1.5">
        <code className="font-mono">{argument.name}</code>
      </td>
      <td className="px-3 py-1.5">
        <ShownValue shown={shownValue(argument, place, notRenderable)} />
        {screen !== null && (
          <div>
            <ScreenLink screen={screen} />
          </div>
        )}
      </td>
      <td className="px-3 py-1.5 text-text-secondary">{bindingClassLabel(argument.binding_class)}</td>
      <td className="px-3 py-1.5 text-text-secondary" data-provenance>
        {provenance === null ? (
          "—"
        ) : (
          <>
            {objectKindLabel(provenance.object_kind)}{" "}
            <code className="font-mono">{tenantDefinedLabel(provenance.key)}</code>
            {provenance.published_revision != null &&
              ` · published revision ${provenance.published_revision}`}
            {provenance.published_at != null && `, ${formatDate(provenance.published_at)}`}
          </>
        )}
      </td>
    </tr>
  );
}

/** One token's value as the Blueprint stage shows it; Verify shows a Measurement's facts through it too. */
export function ShownValue({ shown }: { shown: Shown }) {
  const currency = useTenantCurrency();
  switch (shown.kind) {
    case "secret":
      return (
        <span>
          From the environment variable <code className="font-mono">{shown.variable}</code>
        </span>
      );
    case "parameter":
      return (
        <span>
          Your code passes <code className="font-mono">{shown.parameter}</code>
        </span>
      );
    case "unconfigured":
      return <span className="text-text-secondary">Not declared yet</span>;
    case "not_renderable":
      return (
        <span className="text-text-secondary">
          Valid platform configuration. This Code Builder version cannot yet generate its use.
        </span>
      );
    case "concept":
      return <OpenSetValue labelKeys={shown.labelKeys} value={shown.value} />;
    case "words":
      return <span>{shown.text}</span>;
    case "money":
      return <span>{formatMicros(shown.micros, currency)}</span>;
    case "no_ceiling_declared":
      return <span>None of its own — the workspace default applies</span>;
    case "path":
      return <code className="font-mono">{shown.segments.join(" › ")}</code>;
    case "text":
      return <code className="font-mono">{tenantDefinedLabel(shown.text)}</code>;
  }
}
