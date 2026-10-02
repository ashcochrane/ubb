/**
 * The request previews: what each call sends, laid out to be read.
 *
 * One file per call — the method and URL, the headers, the body — written
 * from the same plan the runnable file is written from, so it is not a second
 * source of what is sent. It is DOCUMENTATION (#180 §1.4): it is not run, it
 * carries no readiness verdict of its own, and it never stands in for the
 * runnable file, whose header is where the verdict is stated.
 *
 * A value is shown in the shape its class has everywhere else: a literal as
 * itself, a runtime value as `$name` under the name the Blueprint gives it,
 * the credential as `$UBB_API_KEY`. Where the API is, is shown as the
 * variable it is read from: no address is written here either.
 */
import { ENVIRONMENT, SHELL_COMMENTS, SHELL_FILE } from "../catalogue.ts";
import { asComments, statement } from "../comments.ts";
import { routeWith, type CallPlan, type Plan, type Value } from "./plan.ts";
import { INDENT, jqLiteral, jqString } from "./syntax.ts";

export interface Preview {
  readonly path: string;
  readonly contents: string;
}

function shown(value: Value): string {
  switch (value.kind) {
    case "literal":
      return jqLiteral(value.value);
    case "parameter":
      return `$${value.parameter.name}`;
    case "read":
      return `$${value.parameter.name}${value.path.map((segment) => `[${jqString(segment)}]`).join("")}`;
    case "unconfigured":
      return `not_configured(${jqString(value.token)})`;
    case "cost":
      return `to_micros($${value.parameter.name}, ${jqString(value.representation)}, ${jqString(value.declared)})`;
  }
}

function lines(entries: readonly (readonly [string, string])[], indent: string): string[] {
  return entries.map(
    ([key, value], index) =>
      `${indent}${jqString(key)}: ${value}${index === entries.length - 1 ? "" : ","}`,
  );
}

function body(call: CallPlan): string[] {
  const out: string[] = ["{"];
  call.body.forEach((field, index) => {
    const comma = index === call.body.length - 1 ? "" : ",";
    if (field.shape === "keyed") {
      const members = field.members.flatMap((member) =>
        member.value === null ? [] : [[member.key, shown(member.value)] as const],
      );
      out.push(
        `${INDENT}${jqString(field.name)}: {`,
        ...lines(members, INDENT.repeat(2)),
        `${INDENT}}${comma}`,
      );
      return;
    }
    out.push(`${INDENT}${jqString(field.name)}: ${shown(field.value)}${comma}`);
  });
  out.push("}");
  return out;
}

function preview(plan: Plan, call: CallPlan): Preview {
  const url = routeWith(call, (parameter) => `$${parameter.name}`);
  return {
    path: `${SHELL_FILE.previewDirectory}/${call.name}.http`,
    contents: `${[
      ...asComments(SHELL_COMMENTS.preview),
      ...asComments([statement("operation_id", call.call.operationId)]),
      "",
      `${call.route.method} $${ENVIRONMENT.baseUrl}${url}`,
      `Authorization: Bearer $${plan.credential.binding.environmentVariable}`,
      "Content-Type: application/json",
      "",
      ...body(call),
    ].join("\n")}\n`,
  };
}

export function renderPreviews(plan: Plan): Preview[] {
  return [plan.start, ...plan.subtasks, ...plan.records, plan.close].map((call) =>
    preview(plan, call),
  );
}
