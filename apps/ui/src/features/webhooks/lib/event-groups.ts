// The event-type catalog grouped by prefix ("billing.balance_low" → group
// "billing") for the subscription picker. "*" is NOT part of any group — it is
// the separate "All events" toggle.

import { humanize, WEBHOOK_EVENT_TYPES } from "@/lib/labels";

export interface EventTypeOption {
  value: string;
  /** Suffix label inside its group: "billing.balance_low" → "Balance low". */
  label: string;
}

export interface EventTypeGroup {
  key: string;
  label: string;
  options: EventTypeOption[];
}

/** Group the catalog by prefix, preserving catalog (alphabetical) order. */
export function groupedEventTypes(): EventTypeGroup[] {
  const groups = new Map<string, EventTypeOption[]>();
  for (const eventType of WEBHOOK_EVENT_TYPES) {
    const [prefix = eventType, rest = ""] = eventType.split(".", 2);
    const options = groups.get(prefix) ?? [];
    options.push({
      value: eventType,
      label: rest ? humanize(rest) : humanize(eventType),
    });
    groups.set(prefix, options);
  }
  return Array.from(groups, ([key, options]) => ({
    key,
    label: humanize(key),
    options,
  }));
}
