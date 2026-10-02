/**
 * The Integration Blueprint, as the committed contract publishes it.
 *
 * Read off `openapi/v1.json` — `pnpm contract:types` generates the module
 * imported here on every typecheck — so this package holds no copy of the
 * document's shape and cannot come to disagree with it. A field the contract
 * renames stops compiling here.
 */
import type { components } from "./generated/v1";

type Schemas = components["schemas"];

export type ResolvedIntegrationBlueprint =
  Schemas["ResolvedIntegrationBlueprint"];
export type BlueprintCall = Schemas["IntegrationBlueprintCall"];
export type BlueprintArgument = Schemas["IntegrationBlueprintArgument"];
export type BlueprintProvenance = Schemas["IntegrationBlueprintProvenance"];
export type BlueprintDiagnostic = Schemas["IntegrationBlueprintDiagnostic"];
export type BlueprintRemediationRequest =
  Schemas["IntegrationBlueprintRemediationRequest"];

export type CodeTarget = ResolvedIntegrationBlueprint["target"];
export type IntegrationReadiness = ResolvedIntegrationBlueprint["readiness"];
export type BindingClass = BlueprintArgument["binding_class"];
export type DiagnosticCode = BlueprintDiagnostic["code"];
export type DiagnosticSeverity = BlueprintDiagnostic["severity"];
export type ConfigurationObjectKind = BlueprintProvenance["object_kind"];

/** A literal as it travels in the document: untyped JSON. */
export type Json =
  | null
  | boolean
  | number
  | string
  | readonly Json[]
  | { readonly [key: string]: Json };

/**
 * A document this renderer cannot turn into files: one of a shape it does not
 * know, or one that breaks what the contract promises about a token. Never
 * raised for a Blueprint that is merely not ready — that one renders, as a
 * file that says what is missing and refuses to run.
 */
export class BlueprintNotRenderable extends Error {
  constructor(message: string) {
    super(message);
    this.name = "BlueprintNotRenderable";
  }
}
