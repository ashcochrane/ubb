// Where an integration starts: the API-basics card, absorbed (#579, §12).
//
// The Developers page used to carry a hand-written "API basics" card beside a
// second key convention eight lines away in another file — two integration
// examples that could only drift from the code this page generates. What it
// taught survives here, as the onboarding state of the builder itself: shown
// while the Blueprint is a scaffold, labelled with the Blueprint's own verdict,
// teaching the lifecycle in the order of the Blueprint's own calls, and naming
// what must be configured from its own diagnostics. It is not a second
// example: the lifecycle it teaches — its order, its verdict, the credential's
// variable and what is missing — is read off the Blueprint or the renderer's
// catalogue. The notes on lists and errors under it are the API's general
// conventions, kept from the card in its words; they describe no call.

import { Link } from "@tanstack/react-router";
import { ENVIRONMENT } from "ubb-codegen";

import { Section } from "@/components/shared/section";
import { Badge } from "@/components/ui/badge";

import type { Blueprint } from "../api/types";
import { roleOf, type CallRole } from "../lib/blueprint";
import { CALL_TITLES, diagnosticCodeLabel, readinessLabel } from "../lib/code-builder-words";

/** What each part of the lifecycle is for, for someone who has not met it. */
const WHAT_IT_IS_FOR: Readonly<Record<CallRole, string>> = {
  start_task:
    "A Task is one whole unit of work for one customer. Start it before the work begins; everything it causes is recorded against it.",
  start_subtask:
    "Contained work your code starts itself, inside the Task, so its cost rolls up into the Task's.",
  record_usage:
    "Each thing that happens inside the work, recorded with the Measurements its Event Type declares. The answer can ask your code to stop.",
  close_task:
    "Say how the work ended, so its cost and its price are final.",
  other: "",
};

export function LifecycleScaffold({ blueprint }: { blueprint: Blueprint }) {
  const credential = blueprint.calls
    .flatMap((call) => call.arguments)
    .find((argument) => argument.binding_class === "secret_reference");
  return (
    <Section
      title="Start here"
      description="The calls every integration makes, in order. Configure below to make them yours."
    >
      <div className="space-y-4">
        <Badge variant="outline">{readinessLabel(blueprint.readiness)}</Badge>
        <ol className="list-decimal space-y-2 pl-5 text-[13px] text-text-primary">
          <li>
            <span className="font-medium">Authenticate.</span>{" "}
            <span className="text-text-secondary">
              Every call sends your API key as a bearer token, read from{" "}
              <code className="font-mono">{credential?.environment_variable ?? ENVIRONMENT.apiKey}</code>
              , and goes to the API at{" "}
              <code className="font-mono">{ENVIRONMENT.baseUrl}</code>. Generated files hold
              neither: set both in the environment they run in. Keys are minted under{" "}
              <Link to="/developers" className="underline underline-offset-2">
                API keys
              </Link>
              .
            </span>
          </li>
          {blueprint.calls.map((call, index) => {
            const role = roleOf(call);
            return (
              <li key={`${call.operation_id}:${index}`}>
                <span className="font-medium">{`${CALL_TITLES[role]}.`}</span>{" "}
                <span className="text-text-secondary">{WHAT_IT_IS_FOR[role]}</span>
              </li>
            );
          })}
        </ol>
        {blueprint.diagnostics.length > 0 && (
          <div className="space-y-1">
            <p className="text-[12px] font-medium text-text-primary">What must be configured</p>
            <ul aria-label="What must be configured" className="list-disc pl-5 text-[12px] text-text-secondary">
              {blueprint.diagnostics.map((diagnostic, index) => (
                <li key={`${diagnostic.code}:${index}`}>{diagnosticCodeLabel(diagnostic.code)}</li>
              ))}
            </ul>
          </div>
        )}
        <div className="space-y-1 text-[12px] text-text-secondary">
          <p>
            <span className="font-medium text-text-primary">Lists</span> return{" "}
            <span className="font-mono">{"{ data, has_more, next_cursor }"}</span> — pass{" "}
            <span className="font-mono">next_cursor</span> back as{" "}
            <span className="font-mono">cursor</span> for the next page (up to 100, newest
            first, no total counts).
          </p>
          <p>
            <span className="font-medium text-text-primary">Errors:</span> any non-2xx
            answer is an RFC 9457 <span className="font-mono">problem+json</span> body with a
            stable <span className="font-mono">code</span>; branch on the code, not the
            wording.
          </p>
          <p>
            See also{" "}
            <Link to="/webhooks" className="underline underline-offset-2">
              Webhooks
            </Link>{" "}
            for what UBB announces, and{" "}
            <Link to="/settings/audit" className="underline underline-offset-2">
              the audit ledger
            </Link>{" "}
            for who changed what.
          </p>
        </div>
      </div>
    </Section>
  );
}
