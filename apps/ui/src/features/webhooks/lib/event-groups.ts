// The subscription picker's groups, derived from the registry's own
// namespaces (#464, spec §16 and §18).
//
// Every event UBB publishes is `<owner>.<state entered>` (ADR-0006 §5): the
// owner is the resource whose lifecycle moved or the declared control family
// whose own state changed, never a product and never a mechanism. So the
// picker groups by owner, and the owners are READ OFF THE GENERATED SET —
// `WEBHOOK_EVENT_TYPE_VALUES` from `@/lib/vocabulary` — rather than off the
// legacy adapter's list or a hand-kept table. A namespace the registry adds
// appears as a group the day it is generated.
//
// The WORDS are not derived. Each option carries the catalogue's wording for
// its event (`webhookEventTypeLabel`, bound beside this file), and each group
// heading is one of two things:
//
//   - for a control family — `wallet_policy`, `customer_spend_pool` — the
//     catalogue's own word for the family (`control_family.*`), so the heading
//     the picker shows is the word the Spend controls surfaces show;
//   - for a resource owner — the wallet, the customer, the credit grant — a
//     console-owned heading in `OWNER_HEADINGS` below. The catalogue holds
//     wording for the 37 EVENTS and the four FAMILIES and none for a resource
//     owner as such, and a heading is a console layout choice rather than a
//     registry value's label (ADR-0008 §4.5's category), so it lives here as
//     `PRODUCT_DESCRIPTIONS` does in `@/lib/products`: TOTAL over the owner
//     union derived from the generated type, so a namespace the registry adds
//     and this has no heading for fails `tsc` rather than rendering blank or
//     humanised. That is the whole difference between this and the humaniser
//     it replaces, which title-cased whatever prefix it was handed.
//
// `"*"` is NOT part of any group — it is the separate "All events" toggle.

import { controlFamilyLabel } from "@/lib/control-family";
import {
  CONTROL_FAMILY_LABEL_KEYS,
  WEBHOOK_EVENT_TYPE_VALUES,
  type ControlFamily,
  type WebhookEventType,
} from "@/lib/vocabulary";

import { webhookEventTypeLabel } from "./event-type-label";

/** The namespace of one event name — `wallet.balance_low` → `wallet`. */
type OwnerOf<T> = T extends `${infer Owner}.${string}` ? Owner : never;

/** Every namespace the catalogue uses: resources and control families. */
export type EventOwner = OwnerOf<WebhookEventType>;

/**
 * Headings for the resource owners — console-owned copy, total over the
 * owners that are not control families. Read by indexing on purpose: a
 * namespace with no heading here is a compile error, never a guess.
 */
export const OWNER_HEADINGS = {
  auto_top_up: "Automatic top-up",
  credit_grant: "Credit grant",
  customer: "Customer",
  invitation: "Invitation",
  member: "Member",
  provider: "Provider",
  referral: "Referral",
  refund: "Refund",
  sandbox: "Sandbox",
  subtask: "Subtask",
  task: "Task",
  tenant: "Tenant",
  top_up: "Top-up",
  usage: "Usage",
  usage_invoice: "Usage invoice",
  wallet: "Wallet",
  withdrawal: "Withdrawal",
} as const satisfies Record<Exclude<EventOwner, ControlFamily>, string>;

function isControlFamily(owner: EventOwner): owner is EventOwner & ControlFamily {
  return owner in CONTROL_FAMILY_LABEL_KEYS;
}

/** The heading for a group: the family's catalogue word, or the owner's. */
export function ownerHeading(owner: EventOwner): string {
  return isControlFamily(owner) ? controlFamilyLabel(owner) : OWNER_HEADINGS[owner];
}

export interface EventTypeOption {
  value: WebhookEventType;
  /** The catalogue's words for the event: "wallet.balance_low" → "Wallet balance low". */
  label: string;
}

export interface EventTypeGroup {
  key: EventOwner;
  label: string;
  options: EventTypeOption[];
}

function ownerOf(eventType: WebhookEventType): EventOwner {
  return eventType.slice(0, eventType.indexOf(".")) as EventOwner;
}

/** Group the catalogue by owner, preserving the registry's declaration order. */
export function groupedEventTypes(): EventTypeGroup[] {
  const groups = new Map<EventOwner, EventTypeOption[]>();
  for (const eventType of WEBHOOK_EVENT_TYPE_VALUES) {
    const owner = ownerOf(eventType);
    const options = groups.get(owner) ?? [];
    options.push({ value: eventType, label: webhookEventTypeLabel(eventType) });
    groups.set(owner, options);
  }
  return Array.from(groups, ([key, options]) => ({
    key,
    label: ownerHeading(key),
    options,
  }));
}
