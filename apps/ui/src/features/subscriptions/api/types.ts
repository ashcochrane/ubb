// Type aliases from the generated contract, plus local interfaces for the
// contract's UNTYPED responses (additionalProperties: true).

import type { PlatformSchemas, SubscriptionSchemas } from "@/api/types";

export type PlanIn = PlatformSchemas["PlanIn"];
export type PlanOut = PlatformSchemas["PlanOut"];
export type PlanUpdateIn = PlatformSchemas["PlanUpdateIn"];
export type SyncResponse = SubscriptionSchemas["SyncResponse"];

// GET /connect/status is untyped in the schema ({additionalProperties: true}).
// [backend-verified shape — see discovery spec]
// { account_id: "acct_… or empty string", charges_enabled: bool, onboarded: bool }
// onboarded = account_id set AND charges_enabled.
export interface ConnectStatus {
  account_id: string;
  charges_enabled: boolean;
  onboarded: boolean;
}

/** Narrow the untyped /connect/status body into ConnectStatus (defensive, no casts). */
export function toConnectStatus(raw: Record<string, unknown>): ConnectStatus {
  const accountId = raw["account_id"];
  return {
    account_id: typeof accountId === "string" ? accountId : "",
    charges_enabled: raw["charges_enabled"] === true,
    onboarded: raw["onboarded"] === true,
  };
}

// PATCH /platform/plans/{key} also answers with an untyped object (unlike the
// typed 201 PlanOut on create). The UI treats it as a bare acknowledgement and
// echoes the submitted values instead — no interface needed.
