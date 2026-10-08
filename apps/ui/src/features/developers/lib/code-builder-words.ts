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
  TASK_OUTCOME_LABEL_KEYS,
  TASK_TYPE_KIND_LABEL_KEYS,
  WEBHOOK_EVENT_TYPE_LABEL_KEYS,
} from "@/lib/vocabulary";

import type { BlueprintCall } from "../api/types";
import { roleOf, subjectOf, type CallRole } from "./blueprint";
import type { SupplierCostField } from "./verification";

export const codeTargetLabel = labelMap(CODE_TARGET_LABEL_KEYS);
export const readinessLabel = labelMap(INTEGRATION_READINESS_LABEL_KEYS);
export const bindingClassLabel = labelMap(BINDING_CLASS_LABEL_KEYS);
export const severityLabel = labelMap(DIAGNOSTIC_SEVERITY_LABEL_KEYS);
export const objectKindLabel = labelMap(CONFIGURATION_OBJECT_KIND_LABEL_KEYS);
export const diagnosticCodeLabel = labelMap(DIAGNOSTIC_CODE_LABEL_KEYS);
export const declarationStatusLabel = labelMap(DECLARATION_STATUS_LABEL_KEYS);
export const altitudeLabel = labelMap(TASK_TYPE_KIND_LABEL_KEYS);
export const webhookEventLabel = labelMap(WEBHOOK_EVENT_TYPE_LABEL_KEYS);
export const taskOutcomeLabel = labelMap(TASK_OUTCOME_LABEL_KEYS);

/** What each call does, as a heading. */
export const CALL_TITLES: Readonly<Record<CallRole, string>> = {
  start_task: "Start the work",
  start_subtask: "Start a Subtask",
  record_usage: "Record usage",
  close_task: "Close the work",
  other: "Another call",
};

/**
 * What the page says when the files last taken do not match the Blueprint now
 * resolved. Cause-neutral on purpose (owner ruling on #600): the selection may
 * have changed as easily as the configuration, and the page knows only that
 * the two fingerprints differ.
 */
export const STALE_FILES_WARNING = "The files you took are stale for the current Blueprint.";

/**
 * What the page says when the last Verify ran against a fingerprint other
 * than the Blueprint now on screen (#581). Cause-neutral on the same ruling as
 * the files': the page knows only that the two fingerprints differ.
 */
export const STALE_RESULT_WARNING = "The last Verify ran against a different Blueprint, not the current one.";

/**
 * What a sample of each supplier cost field is, beside it in the Verify form.
 * A cost the caller supplies is typed as the caller's code sends it. A cost
 * generated code reads off the provider's response is typed as the code
 * would send it once read and converted — and the form says, word for word
 * as the owner ruled (#583 D3), that Verify tests the recording and costing
 * of that figure and never the reading or the conversion, which only running
 * the generated files tests.
 */
export const SUPPLIER_COST_SAMPLE: Readonly<
  Record<SupplierCostField, { label: string; hint: string }>
> = {
  provider_cost_micros: {
    label: "Supplier cost, in micros",
    hint: "What your code reports this call cost, converted to micros as it sends it; leave it blank to send none.",
  },
  provider_response_cost_micros: {
    label: "Supplier cost read off the response, in micros",
    hint:
      "Verify supplies the resulting supplier cost in micros to test UBB recording and costing. " +
      "Generated-artifact execution tests the provider-response read and conversion.",
  },
};

/**
 * What a sample of the event's currency is, where the call reads it off the
 * provider's response (owner review of #608): the resulting currency code
 * generated code sends, sent as the event's own — never the tenant's made up
 * in its place. Said in the same terms as the cost read beside it: Verify
 * samples the value, and only running the generated files tests the read.
 * Whether UBB admits it is UBB's own rule, on the server.
 */
export const CURRENCY_SAMPLE = {
  label: "Currency read off the provider response",
  hint:
    "Verify supplies the resulting currency code to test UBB recording, which admits only your " +
    "UBB currency. Generated-artifact execution tests the provider-response read.",
} as const;

/**
 * What `verified` speaks for (owner ruling on #599): the whole Blueprint, and
 * recording and costing only. Said beside every verdict, because a price is
 * the first thing a reader would take it to prove.
 */
export const VERIFIED_SCOPE =
  "Verify speaks for recording and costing only, and proves no price: each recording's price status says what was priced.";

/**
 * A call's heading: what it does, and the declared object it is about where
 * it names one — in the tenant's own spelling, never re-worded.
 */
export function callHeading(call: BlueprintCall): string {
  const title = CALL_TITLES[roleOf(call)];
  const subject = subjectOf(call);
  return subject === null ? title : `${title} · ${tenantDefinedLabel(subject)}`;
}
