// The words the Code Builder page renders (#579), bound once.
//
// Every value of a registry concept is worded by the catalogue
// (`src/locales/en.json`) through its generated label keys; nothing here is a
// value list. The rest is the console's own copy about this page's objects —
// what a call does, where a link goes — which is prose, not catalogue content.

import { labelMap, tenantDefinedLabel } from "@/lib/localisation";
import {
  BINDING_CLASS_LABEL_KEYS,
  CODE_TARGET_LABEL_KEYS,
  CONFIGURATION_OBJECT_KIND_LABEL_KEYS,
  DECLARATION_STATUS_LABEL_KEYS,
  DIAGNOSTIC_CODE_LABEL_KEYS,
  DIAGNOSTIC_SEVERITY_LABEL_KEYS,
  INTEGRATION_READINESS_LABEL_KEYS,
  TASK_TYPE_KIND_LABEL_KEYS,
  WEBHOOK_EVENT_TYPE_LABEL_KEYS,
} from "@/lib/vocabulary";

import type { BlueprintCall } from "../api/types";
import { roleOf, subjectOf, type CallRole } from "./blueprint";

export const codeTargetLabel = labelMap(CODE_TARGET_LABEL_KEYS);
export const readinessLabel = labelMap(INTEGRATION_READINESS_LABEL_KEYS);
export const bindingClassLabel = labelMap(BINDING_CLASS_LABEL_KEYS);
export const severityLabel = labelMap(DIAGNOSTIC_SEVERITY_LABEL_KEYS);
export const objectKindLabel = labelMap(CONFIGURATION_OBJECT_KIND_LABEL_KEYS);
export const diagnosticCodeLabel = labelMap(DIAGNOSTIC_CODE_LABEL_KEYS);
export const declarationStatusLabel = labelMap(DECLARATION_STATUS_LABEL_KEYS);
export const altitudeLabel = labelMap(TASK_TYPE_KIND_LABEL_KEYS);
export const webhookEventLabel = labelMap(WEBHOOK_EVENT_TYPE_LABEL_KEYS);

/** What each call does, as a heading. */
export const CALL_TITLES: Readonly<Record<CallRole, string>> = {
  start_task: "Start the work",
  start_subtask: "Start a Subtask",
  record_usage: "Record usage",
  close_task: "Close the work",
  other: "Another call",
};

/**
 * A call's heading: what it does, and the declared object it is about where
 * it names one — in the tenant's own spelling, never re-worded.
 */
export function callHeading(call: BlueprintCall): string {
  const title = CALL_TITLES[roleOf(call)];
  const subject = subjectOf(call);
  return subject === null ? title : `${title} · ${tenantDefinedLabel(subject)}`;
}
