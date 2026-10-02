/**
 * The Shell / raw HTTP target: a Blueprint as the files a tenant is handed.
 *
 * A runnable POSIX shell file that needs curl and jq, the call-site blocks,
 * an environment example, a verify script, and a preview of each request.
 */
import type { ResolvedIntegrationBlueprint } from "../blueprint.ts";
import { COMMENTS, ENVIRONMENT, SHELL_COMMENTS, SHELL_FILE } from "../catalogue.ts";
import { asComments } from "../comments.ts";
import type { RenderedFile } from "../render.ts";
import { renderCallSites } from "./callSites.ts";
import { renderModule } from "./module.ts";
import { plan as planOf, type Plan } from "./plan.ts";
import { renderPreviews } from "./preview.ts";
import { renderVerifyScript } from "./verify.ts";

/**
 * Every variable the artifact reads, as an assignment with nothing after the
 * equals sign. The credential's is the name the Blueprint gave; the value is
 * never something this package could write, because it never holds one.
 */
function renderEnvironmentExample(plan: Plan): string {
  return `${[
    ...asComments(COMMENTS.environmentFile),
    ...asComments(SHELL_COMMENTS.environmentFile),
    "",
    ...asComments(COMMENTS.apiKey),
    `${plan.credential.binding.environmentVariable}=`,
    "",
    ...asComments(COMMENTS.baseUrl),
    `${ENVIRONMENT.baseUrl}=`,
  ].join("\n")}\n`;
}

export function renderShell(blueprint: ResolvedIntegrationBlueprint): RenderedFile[] {
  const plan = planOf(blueprint);
  return [
    { kind: "module", path: SHELL_FILE.moduleFile, contents: renderModule(plan) },
    ...renderCallSites(plan).map(
      (block): RenderedFile => ({ kind: "call_site", ...block }),
    ),
    {
      kind: "environment_example",
      path: SHELL_FILE.environmentFile,
      contents: renderEnvironmentExample(plan),
    },
    { kind: "verify_script", path: SHELL_FILE.verifyFile, contents: renderVerifyScript(plan) },
    ...renderPreviews(plan).map(
      (preview): RenderedFile => ({ kind: "request_preview", ...preview }),
    ),
  ];
}
