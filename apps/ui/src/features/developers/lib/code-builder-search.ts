// The Code Builder's state, as the URL carries it (#579).
//
// SELECTIONS TRAVEL AS TYPED SEARCH PARAMETERS OF DECLARED KEYS ONLY (owner
// ruling on #184, 2026-09-25): a selection is a set of declared keys, which is
// what makes a configuration round trip, browser history and a deep link work.
// Nothing else goes in it. A key this schema does not declare is dropped, a
// malformed value is caught rather than crashing the route, and a value shaped
// like a credential is refused under every key — the URL is copied into chat
// threads and server logs, and a key pasted into a selection field must not
// ride along.

import { z } from "zod";

import { CODE_TARGET_VALUES, type CodeTarget } from "@/lib/vocabulary";

import type { BlueprintSelection } from "../api/types";
import { credentialShapeIn } from "./credential-shapes";

/**
 * The target a URL that names none asks for. The Python SDK, because it is the
 * target that needs nothing installed beyond the SDK the tenant already has.
 */
export const DEFAULT_TARGET: CodeTarget = "python_sdk";

/** The most of each selection the resolve request takes (`422` beyond it). */
export const MAX_SELECTED = 50;

/** A kind of work's key: the platform declares it a slug of at most 64. */
const KIND_KEY = /^[-a-zA-Z0-9_]{1,64}$/;

/** An Event Type's key is the tenant's own text, of at most 100 characters. */
const EVENT_TYPE_KEY_MAX = 100;

/** `sha256:` and 64 lowercase hexadecimal characters, as the contract states. */
const FINGERPRINT = /^sha256:[0-9a-f]{64}$/;

function isCredentialFree(value: string): boolean {
  return credentialShapeIn(value) === null;
}

const kindKey = z.string().regex(KIND_KEY).refine(isCredentialFree);
const eventTypeKey = z.string().min(1).max(EVENT_TYPE_KEY_MAX).refine(isCredentialFree);

/**
 * A selection of declared keys: a set, in one order, of at most fifty. A bare
 * string is a set of one — the way a hand-typed URL names a single key. A
 * member that is not a key is dropped and the rest kept, and a set left empty
 * is no selection at all; more than fifty is the whole selection refused,
 * because which fifty to keep is not this parser's to choose.
 */
function keySet(member: z.ZodType<string>) {
  return z
    .preprocess(
      (raw) => (typeof raw === "string" ? [raw] : raw),
      z.array(z.unknown()),
    )
    .transform((raw) => {
      const kept = raw.flatMap((item) => {
        const parsed = member.safeParse(item);
        return parsed.success ? [parsed.data] : [];
      });
      return [...new Set(kept)].sort();
    })
    .refine((keys) => keys.length <= MAX_SELECTED)
    .transform((keys) => (keys.length > 0 ? keys : undefined))
    .optional()
    .catch(undefined);
}

export const codeBuilderSearchSchema = z.object({
  target: z.enum(CODE_TARGET_VALUES).optional().catch(undefined),
  task_type: kindKey.optional().catch(undefined),
  event_types: keySet(eventTypeKey),
  subtask_types: keySet(kindKey),
  /** Admin only, enforced by the server; the page offers it only to admins. */
  draft_preview: z.boolean().optional().catch(undefined),
  /**
   * The `configuration_fingerprint` of the files the developer last copied or
   * downloaded. A fingerprint is not a secret: it identifies a stored
   * resolution of the developer's own selection and opens nothing. Where it
   * differs from the Blueprint now resolved, the files held are stale.
   */
  held: z.string().regex(FINGERPRINT).optional().catch(undefined),
});

export type CodeBuilderSearch = z.infer<typeof codeBuilderSearchSchema>;

/** Every key the URL may carry — the schema's own, read off it. */
export const CODE_BUILDER_SEARCH_KEYS: readonly string[] = Object.keys(
  codeBuilderSearchSchema.shape,
);

/**
 * What the page asks the server to resolve, from what the URL says.
 *
 * Exactly the request's published fields: the server drops a key it does not
 * publish without saying so (#505), so `held` — the page's own bookkeeping —
 * must never reach the body.
 */
export function selectionOf(search: CodeBuilderSearch): BlueprintSelection {
  return {
    target: search.target ?? DEFAULT_TARGET,
    task_type: search.task_type ?? null,
    event_types: search.event_types ?? [],
    subtask_types: search.subtask_types ?? [],
    draft_preview: search.draft_preview ?? false,
  };
}
