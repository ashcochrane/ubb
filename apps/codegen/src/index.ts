/**
 * `ubb-codegen`: a resolved Integration Blueprint becomes integration code.
 *
 * One function. Everything else exported here is what a consumer needs in
 * order to call it, or to say the same fixed things the generated files say.
 */
export { render } from "./render.ts";
export type { FileKind, RenderedFile } from "./render.ts";
export { BlueprintNotRenderable } from "./blueprint.ts";
export type { ResolvedIntegrationBlueprint } from "./blueprint.ts";
export {
  AMOUNT_REPRESENTATION,
  CATALOGUE_VERSION,
  COMMENTS,
  ENVIRONMENT,
  MESSAGES,
  MICROS_PER_MINOR_UNIT,
  PRICING_MODE_COMMENTS,
  PYTHON,
  READINESS_COMMENTS,
  REMEDIATION,
  RESPONSE_REPRESENTATION,
  SHELL,
} from "./catalogue.ts";
