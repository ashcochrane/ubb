// When nobody is calling (#579, §14).
//
// NO WEBHOOK HANDLER IS GENERATED. A kill or an expiry arrives when the
// integration is not running, a handler would make readiness depend on a
// signing secret, and which events to subscribe to is a spend-control choice.
// So the page names the announcements each kind it starts can produce — every
// event the contract's `webhooks` section publishes at that kind's altitude
// (`lib/blueprint.ts`) — and points at Webhooks, where a subscription is made.

import { tenantDefinedLabel } from "@/lib/localisation";

import type { Blueprint } from "../api/types";
import { announcementsOf, type TerminalStopCause } from "../lib/blueprint";
import { altitudeLabel, webhookEventLabel } from "../lib/code-builder-words";
import { ScreenLink } from "./screen-link";

/** Why the work ended, said for a kind whose ceiling posture is known. */
function causeText(cause: TerminalStopCause, uncapped: boolean | null): string {
  switch (cause) {
    case "spend_stop":
      return uncapped === true
        ? "a spend stop: it declares no ceiling, so only a customer-wide stop."
        : "a spend stop: its ceiling, or a customer-wide stop.";
    case "went_quiet":
      return "it went quiet past its silence window, or ran past its absolute deadline.";
  }
}

export function KindWebhooks({ blueprint }: { blueprint: Blueprint }) {
  const kinds = announcementsOf(blueprint);
  if (kinds.length === 0) return null;
  return (
    <section aria-label="When nobody is calling" className="space-y-2">
      <h3 className="text-[12px] font-medium text-text-primary">When nobody is calling</h3>
      <p className="text-[12px] text-text-secondary">
        UBB can end work your code started while your code is not running, and
        announces it as a webhook. No handler is generated for these: subscribe
        to the ones you act on.
      </p>
      <ul className="space-y-1.5 text-[12px]">
        {kinds.map((kind) => (
          <li key={`${kind.altitude}:${kind.kind}`}>
            <span className="font-medium text-text-primary">
              {`${altitudeLabel(kind.altitude)} `}
              <code className="font-mono">{tenantDefinedLabel(kind.kind)}</code>
            </span>
            <ul className="mt-0.5 space-y-0.5 pl-4 text-text-secondary">
              {kind.announcements.map(({ event, cause }) => (
                <li key={event}>
                  <code className="font-mono">{event}</code>
                  {` (${webhookEventLabel(event)}) — ${causeText(cause, kind.uncapped)}`}
                </li>
              ))}
            </ul>
          </li>
        ))}
      </ul>
      <ScreenLink screen={{ to: "/webhooks" }} />
    </section>
  );
}
