// Real API calls for the CFO overview. Every call goes through unwrap() so
// callers always reject with a typed ApiProblem.
//
// ⚠ **FIVE CALLS BECAME FOUR SHAPES OF ONE QUESTION (#501).** The margin
// summary, the per-customer margin list, the usage report, its timeseries and
// the billing revenue report were five routes; they are one now, and what
// distinguishes these functions is the MEASURES they ask for and whether they
// group or bucket. Two of them used to differ by which product a workspace had
// — the billing revenue report for billing tenants, the metering timeseries for
// everyone else — and that fork is gone with them: the same question answers
// both, which is the whole point of collapsing a duplicate.

import {
  connectApi,
  marginApi,
  meteringApi,
  tenantApi,
} from "@/api/client";
import { unwrap } from "@/api/problem";
import {
  EVERY_MEASURE,
  FIELD_AXIS,
  MONEY_MEASURES,
} from "@/lib/economic-query";

import {
  toConnectStatus,
  type ApiKeyList,
  type BreakdownDimension,
  type ConnectStatus,
  type Economics,
  type PricingBookList,
  type Unprofitable,
  type Window,
} from "./types";

/** The workspace's cost, revenue, margin and recorded work for the window. */
export async function getTenantEconomics(window: Window): Promise<Economics> {
  return unwrap(
    await meteringApi.GET("/analytics/economics", {
      params: { query: { ...window, measures: [...EVERY_MEASURE] } },
    }),
  );
}

/**
 * The same question grouped by one axis — the cost breakdown's bars.
 *
 * ⚠ **MONEY ONLY, AND THE ABSENT COUNT IS A REFUSAL RATHER THAN AN OVERSIGHT.**
 * The breakdown rows used to carry an event count per bar. `recorded_events`
 * counts records at the granularity each Event Type declares, so rows that mix
 * Event Types are not comparable — a workspace metering one type per token and
 * another per request reads the first as ten thousand times the second — and
 * the server REFUSES the combination rather than answering it subtly wrongly.
 * Three of the four axes this picker offers mix Event Types, so asking for the
 * count here would be asking for a 422 on three of them and a misleading number
 * on none. The window's own total is on the stat row, where it compares with
 * nothing.
 */
export async function getGroupedEconomics(
  window: Window,
  groupBy: BreakdownDimension,
): Promise<Economics> {
  return unwrap(
    await meteringApi.GET("/analytics/economics", {
      params: {
        query: {
          ...window,
          measures: [...MONEY_MEASURES],
          group_by: [FIELD_AXIS(groupBy)],
        },
      },
    }),
  );
}

/**
 * All-time totals — used only to decide whether the workspace looks brand new
 * (no recorded work) for the getting-started card.
 *
 * ⚠ **NO WINDOW, WHICH MEANS THE HORIZON RATHER THAN THE BEGINNING OF TIME.**
 * The server defaults an absent start date to the earliest day it can still
 * answer for and says so on the answer, so "all-time" here is exactly as much
 * history as UBB holds — which is the honest reading of the question this card
 * asks.
 */
export async function getLifetimeEconomics(): Promise<Economics> {
  return unwrap(
    await meteringApi.GET("/analytics/economics", {
      params: { query: { measures: [...EVERY_MEASURE] } },
    }),
  );
}

/** Day-bucketed revenue and cost — the chart source for every workspace. */
export async function getDailyEconomics(window: Window): Promise<Economics> {
  return unwrap(
    await meteringApi.GET("/analytics/economics", {
      params: {
        query: { ...window, measures: [...EVERY_MEASURE], bucket: "day" },
      },
    }),
  );
}

/** Per-customer rows for the window, from the same question grouped. */
export async function getCustomerEconomics(
  window: Window,
): Promise<Economics> {
  return getGroupedEconomics(window, "customer");
}

/** Unprofitable customers for the current period (server defaults the period).
 *
 *  ⚠ THIS ONE IS NOT THE COLLAPSE'S. It reads the ALERTING record rather than a
 *  margin figure, so it keeps its own contract — and the count of customers a
 *  threshold rule has named survived the tenant-wide margin total precisely
 *  because it is this, and not a report. */
export async function getUnprofitable(): Promise<Unprofitable> {
  return unwrap(await marginApi.GET("/unprofitable"));
}

/** First page of API keys — existence check for the getting-started card. */
export async function getApiKeysFirstPage(): Promise<ApiKeyList> {
  return unwrap(
    await tenantApi.GET("/api-keys", { params: { query: { limit: 1 } } }),
  );
}

/** First page of pricing books — existence check for the getting-started card.
 *
 * ⚠ THE PRICING HALF, DELIBERATELY (#368). The card asks whether this
 * workspace has begun configuring what it CHARGES; a cost book records what a
 * supplier charges and answers a different question. Before the split one list
 * held both and this read could not tell them apart. */
export async function getPricingBooksFirstPage(): Promise<PricingBookList> {
  return unwrap(
    await meteringApi.GET("/pricing/pricing-books", {
      params: { query: { limit: 1 } },
    }),
  );
}

/** Stripe Connect onboarding state (billing tenants). */
export async function getConnectStatus(): Promise<ConnectStatus> {
  return toConnectStatus(unwrap(await connectApi.GET("/status")));
}
