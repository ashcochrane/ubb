// The words for a webhook event's name, bound where the webhooks feature
// renders them (#464, spec §18 — the `webhook_event_type` console payment,
// in the shape #424 paid `task_status`).
//
// Identity lives in `@/lib/vocabulary` (generated from `domain-vocabulary/`):
// the 37 names, held by reference in `@/lib/labels` under `WEBHOOK_EVENT_TYPES`
// because the registry names that file as the console's consumer. Expression
// lives in `@/locales`, reached through `@/lib/localisation`, which has held
// wording for every one of the 37 under `webhook_event_type.*` since slice 0.
// This module is where the two meet: one binding, read by the subscription
// picker, the endpoint table's chips and the deliveries table.
//
// It replaces `webhookEventTypeLabel` in the legacy adapter, which split a
// name on the dot and title-cased both halves — so the thirteen names #222
// renamed and the five #464 moved rendered under invented wording, and any
// name at all rendered under SOME wording. A closed set has no unfamiliar
// value by contract; if one ever arrived it would render as the token it is,
// which is `resolveLabel`'s rule for every concept (ADR-0008 §4.3/§4.4).
//
// The wildcard `"*"` is a SELECTOR, not a name, and is not in the catalogue:
// the one surface that shows a subscription's selectors renders it as its own
// "All events" chip before any name is looked up (`webhook-config-table.tsx`).

import { labelMap } from "@/lib/localisation";
import { WEBHOOK_EVENT_TYPE_LABEL_KEYS } from "@/lib/vocabulary";

/** The catalogue's words for an event's name; the raw token for an unfamiliar one. */
export const webhookEventTypeLabel = labelMap(WEBHOOK_EVENT_TYPE_LABEL_KEYS);
