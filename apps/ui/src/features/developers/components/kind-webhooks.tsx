// When nobody is calling (#579, §14).
//
// NO WEBHOOK HANDLER IS GENERATED. A kill or an expiry arrives when the
// integration is not running, a handler would make readiness depend on a
// signing secret, and which events to subscribe to is a spend-control choice.
// So the page names the announcements each kind it starts can produce — read
// off the contract's `webhooks` section through `TERMINAL_STOP_EVENTS` — and
// points at Webhooks, where a subscription is made.

import { tenantDefinedLabel } from "@/lib/localisation";

import type { Blueprint } from "../api/types";
import { announcementsOf } from "../lib/blueprint";
import { altitudeLabel, webhookEventLabel } from "../lib/code-builder-words";
import { ScreenLink } from "./screen-link";

export function KindWebhooks({ blueprint }: { blueprint: Blueprint }) {
  const announcements = announcementsOf(blueprint);
  if (announcements.length === 0) return null;
  return (
    <section aria-label="When nobody is calling" className="space-y-2">
      <h3 className="text-[12px] font-medium text-text-primary">When nobody is calling</h3>
      <p className="text-[12px] text-text-secondary">
        UBB can end work your code started while your code is not running, and
        announces it as a webhook. No handler is generated for these: subscribe
        to the ones you act on.
      </p>
      <ul className="space-y-1.5 text-[12px]">
        {announcements.map((announcement) => (
          <li key={`${announcement.altitude}:${announcement.kind}`}>
            <span className="font-medium text-text-primary">
              {`${altitudeLabel(announcement.altitude)} `}
              <code className="font-mono">{tenantDefinedLabel(announcement.kind)}</code>
            </span>
            <ul className="mt-0.5 space-y-0.5 pl-4 text-text-secondary">
              <li>
                <code className="font-mono">{announcement.events.killed}</code>
                {` (${webhookEventLabel(announcement.events.killed)}) — a spend stop: `}
                {announcement.uncapped === true
                  ? "it declares no ceiling, so only a customer-wide stop."
                  : "its ceiling, or a customer-wide stop."}
              </li>
              <li>
                <code className="font-mono">{announcement.events.expired}</code>
                {` (${webhookEventLabel(announcement.events.expired)}) — it went quiet past its silence window, or ran past its absolute deadline.`}
              </li>
            </ul>
          </li>
        ))}
      </ul>
      <ScreenLink screen={{ to: "/webhooks" }} />
    </section>
  );
}
