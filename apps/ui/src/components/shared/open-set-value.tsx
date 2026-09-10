// The console's rule for a value of an OPEN concept, in one place (#454;
// slice 6 §18).
//
// An open concept is one whose set grows without a schema change — the
// registry records the values UBB knows today and a consumer must accept one
// it has not seen (ADR-0003; `@/lib/vocabulary` writes `<CONCEPT>_KNOWN_VALUES`
// for it rather than `<CONCEPT>_VALUES`). So a surface rendering one WILL meet
// a value the catalogue has no words for, and the rule for that moment is
// set here, once:
//
//   a known value renders its catalogue word;
//   an unknown value renders the token itself, visibly marked as
//   unrecognised, and is never humanised into words UBB did not say.
//
// The second half is ADR-0008 §4.3/§4.4 — `resolveLabel` already answers the
// raw token for an unfamiliar value, and `@/lib/localisation` explains why a
// title-cased guess is the defect rather than the soft landing. What this
// component adds is the MARK. A bare token beside catalogue words reads as a
// word somebody forgot to translate; marked, it reads as what it is — a value
// the server sent that this console has no name for, which is exactly the
// thing an operator needs to know before acting on it. The mark is console
// copy (ADR-0008 §4.5), not a label key: no concept declares "unrecognised"
// as a value.
//
// ⚠ ONE COPY. Slice 6's three open concepts are the first the console pays,
// and this is the helper all three render through — `trigger_source` here,
// `affordability_reason` and `reason_code` when their surfaces land (spec
// §18, tickets 12 and 15). A second rendering of the rule in a feature is a
// defect, because two copies drift and the day one of them humanises is the
// day ADR-0008 §4.3 is reversed by accident.
//
// THE FIRST BINDING HAS NO WIRE SURFACE YET, AND THAT IS STATED RATHER THAN
// PAPERED OVER. `trigger_source` — the mechanism that applied a stop —
// travels on the four terminal webhook payloads and on nothing this console
// reads: `TaskDetailOut` carries no stop cause (`outcome_reason` is the
// caller's declared verdict, a different closed concept), and
// `WebhookDeliveryResponse` carries no payload body. So the value is held by
// reference in the legacy adapter, the rule is proved for it in this
// component's test, and the run page's "How it ended" section does not
// render a field the unit read does not publish. A later contract change
// putting the stop cause on the unit read is nobody's yet; the test header
// names it as a residual.

import { Badge } from "@/components/ui/badge";
import { resolveLabel } from "@/lib/localisation";

/** The mark beside a value the catalogue has no words for. Console copy, not a label. */
export const UNRECOGNISED_MARK = "Unrecognised";

/** What the mark means, for the hover: the token is the server's, verbatim. */
export const UNRECOGNISED_EXPLANATION =
  "A value UBB has no words for yet. Shown exactly as the server sent it.";

/**
 * One value of an open concept, rendered by the rule above.
 *
 * `labelKeys` is the concept's generated `<CONCEPT>_LABEL_KEYS` map, which is
 * what makes the concept's kind irrelevant to the call: the map knows the
 * registry's values and nothing else, and `resolveLabel` derives the outcome
 * from that alone. `data-label` carries the resolution's kind, so a test
 * asserts WHICH outcome rendered rather than matching prose an unrecognised
 * token could happen to contain.
 */
export function OpenSetValue({
  labelKeys,
  value,
}: {
  labelKeys: Readonly<Record<string, string>>;
  value: string | null | undefined;
}) {
  const resolved = resolveLabel(labelKeys, value);
  if (resolved.kind !== "unfamiliar") {
    return <span data-label={resolved.kind}>{resolved.text}</span>;
  }
  return (
    <span data-label={resolved.kind} className="inline-flex items-center gap-1.5">
      <code className="font-mono text-[12px] text-text-primary">{resolved.value}</code>
      <Badge variant="outline" title={UNRECOGNISED_EXPLANATION}>
        {UNRECOGNISED_MARK}
      </Badge>
    </span>
  );
}
