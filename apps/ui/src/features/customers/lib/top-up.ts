// The two answers of a top-up (R10 Stage C5, F-5), told apart on the body.
//
// A checkout answer carries `checkout_url`; an ACCEPTED answer (the 202 —
// the workspace has no Stripe connector, so the request was recorded and
// handed to the tenant to settle out of band) carries a `status` of the
// registry's closed `top_up_request_status`. The guard decides against the
// generated value list, never a spelled-out token, and never against a status
// code the api layer has already unwrapped away.

import { TOP_UP_REQUEST_STATUS_VALUES } from "@/lib/vocabulary";

import type { TopUpAcceptedResponse, TopUpResult } from "../api/types";

export function isTopUpAccepted(result: TopUpResult): result is TopUpAcceptedResponse {
  return (
    "status" in result &&
    (TOP_UP_REQUEST_STATUS_VALUES as readonly string[]).includes(result.status)
  );
}
