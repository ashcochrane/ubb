// What stands in the way, and where it is fixed (#579, §11).
//
// ⚠ THE PAGE NEVER SENDS A REMEDIATION REQUEST. The builder reads and
// generates; only the owning surface changes configuration, even for an admin
// (#156 §9). Where the console has a screen for the object, the diagnostic
// links there. Where it has none — Event Types, Measurements, reported-cost
// mappings, providers, Grouping Fields are API-only — it offers the request
// the server wrote, to copy, with its API reference: the same artifact a
// member without permission hands to an admin.

import { CopyButton } from "@/components/shared/copy-button";
import { Badge } from "@/components/ui/badge";
import { tenantDefinedLabel } from "@/lib/localisation";

import type { BlueprintDiagnostic, RemediationRequest } from "../api/types";
import { apiReferenceUrl, fixFor, remediationText } from "../lib/blueprint";
import { diagnosticCodeLabel, objectKindLabel, severityLabel } from "../lib/code-builder-words";
import { apiOrigin } from "../lib/api-origin";
import { ScreenLink } from "./screen-link";

export function DiagnosticsList({ diagnostics }: { diagnostics: readonly BlueprintDiagnostic[] }) {
  if (diagnostics.length === 0) {
    return <p className="text-[12px] text-text-secondary">Nothing stands in the way.</p>;
  }
  return (
    <ul aria-label="Diagnostics" className="space-y-2">
      {diagnostics.map((diagnostic, index) => (
        <li
          key={`${diagnostic.code}:${diagnostic.key ?? ""}:${index}`}
          className="space-y-1.5 rounded-md border border-border p-3"
        >
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant={diagnostic.severity === "blocking" ? "destructive" : "outline"}>
              {severityLabel(diagnostic.severity)}
            </Badge>
            <span className="text-[13px] font-medium text-text-primary">
              {diagnosticCodeLabel(diagnostic.code)}
            </span>
          </div>
          <p className="text-[12px] text-text-secondary">
            {objectKindLabel(diagnostic.object_kind)}
            {diagnostic.key != null && (
              <>
                {" "}
                <code className="font-mono">{tenantDefinedLabel(diagnostic.key)}</code>
              </>
            )}
            {diagnostic.field != null && (
              <>
                {" · "}
                <code className="font-mono">{diagnostic.field}</code>
              </>
            )}
          </p>
          <DiagnosticFix diagnostic={diagnostic} />
        </li>
      ))}
    </ul>
  );
}

function DiagnosticFix({ diagnostic }: { diagnostic: BlueprintDiagnostic }) {
  const fix = fixFor(diagnostic);
  switch (fix.kind) {
    case "screen":
      return <ScreenLink screen={fix.screen} />;
    case "request":
      return <RemediationRequestBlock request={fix.request} />;
    case "select":
      return (
        <p className="text-[12px] text-text-secondary">Choose one under Configure.</p>
      );
    case "none":
      return null;
  }
}

function RemediationRequestBlock({ request }: { request: RemediationRequest }) {
  const text = remediationText(request);
  return (
    <div className="space-y-1.5" data-remediation={request.operation_id}>
      <p className="text-[12px] text-text-secondary">
        The console has no screen for this. An admin makes the change with this
        request; this page never sends it.
      </p>
      <div className="flex items-start gap-2 rounded-md border border-border bg-bg-subtle px-3 py-2">
        <pre className="min-w-0 flex-1 overflow-x-auto font-mono text-[12px] leading-relaxed text-text-primary">
          {text}
        </pre>
        <CopyButton value={text} label="Copy request" />
      </div>
      <a
        href={apiReferenceUrl(apiOrigin(), request.operation_id)}
        target="_blank"
        rel="noreferrer"
        className="text-[12px] underline underline-offset-2 hover:text-text-primary"
      >
        {`API reference: ${request.operation_id}`}
      </a>
    </div>
  );
}
