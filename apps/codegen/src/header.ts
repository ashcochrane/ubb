/**
 * What a generated file's header states, whichever target wrote it.
 *
 * The three versions, the target, the fingerprint, the verdict with what it
 * means, every diagnostic with its remediation, and every declaration the
 * file was resolved from (#184 §6). Target-neutral but for two things a
 * target passes in: what each verdict means in that target's own words, and
 * the legend of the shapes its values take.
 *
 * Returned as comment TEXT, a blank string where a line is blank. Each target
 * writes the comment marker itself.
 */
import { refuse, type IntegrationReadiness, type Json } from "./blueprint.ts";
import { COMMENTS, REMEDIATION } from "./catalogue.ts";
import { publication, statement } from "./comments.ts";
import type { Header } from "./lifecycle.ts";
import type { Call, Token } from "./tokens.ts";

/** Every token of a call, with the declaration each was read from. */
function everyToken(call: Call): Token[] {
  const tokens: Token[] = [...call.credentials];
  for (const field of call.fields) {
    if (field.shape === "scalar") {
      tokens.push(field.token, ...field.facts.map((fact) => fact.token));
      continue;
    }
    for (const entry of field.entries) {
      tokens.push(entry.key, ...entry.facts.map((fact) => fact.token));
      if (entry.value !== null) tokens.push(entry.value);
    }
  }
  return tokens;
}

export function headerText(
  blueprint: Header,
  calls: readonly Call[],
  readinessComments: Readonly<Record<IntegrationReadiness, readonly string[]>>,
  legend: readonly string[],
): string[] {
  const fingerprint = blueprint.configuration_fingerprint ?? null;
  const lines: string[] = [
    ...COMMENTS.generated,
    "",
    statement("schema_version", blueprint.schema_version),
    statement("renderer_contract_version", blueprint.renderer_contract_version),
    statement("sdk_major_version", blueprint.sdk_major_version ?? null),
    statement("target", blueprint.target),
    statement("configuration_fingerprint", fingerprint),
    ...(fingerprint === null ? COMMENTS.draftPreview : COMMENTS.fingerprint),
    "",
    statement("readiness", blueprint.readiness),
    ...readinessComments[blueprint.readiness],
    "",
  ];

  if (blueprint.diagnostics.length === 0) {
    lines.push(...COMMENTS.noDiagnostics);
  } else {
    lines.push(...COMMENTS.diagnostics);
    for (const diagnostic of blueprint.diagnostics) {
      const remediation = REMEDIATION[diagnostic.code];
      if (remediation === undefined) {
        refuse(`the catalogue has no remediation for the diagnostic ${diagnostic.code}`);
      }
      lines.push(
        "",
        statement("diagnostic", diagnostic.code, [
          ["severity", diagnostic.severity],
          [diagnostic.object_kind, diagnostic.key ?? null],
          ["field", diagnostic.field ?? null],
        ]),
        ...remediation,
      );
      if (diagnostic.remediation_request != null) {
        lines.push(
          ...COMMENTS.remediationRequest,
          statement("remediation_request", diagnostic.remediation_request as unknown as Json),
        );
      }
    }
  }

  // Every declaration anything in this file was read from, each once, with
  // the publication it was read from where there was one.
  const declarations: string[] = [];
  for (const call of calls) {
    for (const token of everyToken(call)) {
      if (token.provenance === null) continue;
      const line = statement(
        token.provenance.object_kind,
        token.provenance.key,
        publication(token.provenance),
      );
      if (!declarations.includes(line)) declarations.push(line);
    }
  }
  if (declarations.length > 0) {
    lines.push("", ...COMMENTS.resolvedFrom, ...declarations);
  }

  lines.push("", ...legend);
  return lines;
}
