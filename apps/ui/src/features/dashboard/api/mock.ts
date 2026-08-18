// Mock implementation — same exported signatures as ./api.ts, contract-correct
// shapes, deterministic fixtures (see mock-data.ts for the story).

import { mockDelay } from "@/lib/api-provider";

import {
  MOCK_API_KEYS,
  MOCK_CONNECT_STATUS,
  MOCK_LIFETIME_ANALYTICS,
  MOCK_MARGIN_CUSTOMERS,
  MOCK_RATE_CARD_BOOKS,
  MOCK_UNPROFITABLE,
  mockDailySeries,
  mockMarginSummary,
  mockWindowAnalytics,
} from "./mock-data";
import type {
  ApiKeyList,
  BreakdownDimension,
  ConnectStatus,
  MarginCustomerList,
  MarginSummary,
  RateCardBookList,
  RevenueAnalytics,
  Unprofitable,
  UsageAnalytics,
  UsageTimeseries,
  Window,
} from "./types";

export async function getMarginSummary(window: Window): Promise<MarginSummary> {
  await mockDelay();
  return mockMarginSummary(window);
}

export async function getWindowAnalytics(
  _window: Window,
  groupBy: BreakdownDimension,
): Promise<UsageAnalytics> {
  await mockDelay();
  return mockWindowAnalytics(groupBy);
}

export async function getLifetimeAnalytics(): Promise<UsageAnalytics> {
  await mockDelay();
  return MOCK_LIFETIME_ANALYTICS;
}

export async function getRevenueAnalytics(
  window: Window,
): Promise<RevenueAnalytics> {
  await mockDelay();
  const daily = mockDailySeries(window);
  const billed = daily.reduce((sum, d) => sum + d.billed_cost_micros, 0);
  const provider = daily.reduce((sum, d) => sum + d.provider_cost_micros, 0);
  return {
    daily: daily.map((d) => ({
      day: d.day,
      provider_cost_micros: d.provider_cost_micros,
      billed_cost_micros: d.billed_cost_micros,
      event_count: d.event_count,
    })),
    total_billed_cost_micros: billed,
    total_provider_cost_micros: provider,
    // Nothing was excluded — see the note beside the billing feature's copy.
    unresolved_event_count: 0,
    unpriced_event_count: 0,
    total_markup_micros: billed - provider,
  };
}

export async function getUsageTimeseries(
  window: Window,
): Promise<UsageTimeseries> {
  await mockDelay();
  return {
    granularity: "day",
    group_by: "",
    series: mockDailySeries(window).map((d) => ({
      bucket: `${d.day}T00:00:00+00:00`,
      provider_cost_micros: d.provider_cost_micros,
      billed_cost_micros: d.billed_cost_micros,
      markup_micros: d.billed_cost_micros - d.provider_cost_micros,
      event_count: d.event_count,
    })),
  };
}

export async function getMarginCustomers(
  window: Window,
): Promise<MarginCustomerList> {
  await mockDelay();
  return {
    customers: MOCK_MARGIN_CUSTOMERS,
    period: { start: window.start_date, end: window.end_date },
  };
}

export async function getUnprofitable(): Promise<Unprofitable> {
  await mockDelay();
  return MOCK_UNPROFITABLE;
}

export async function getApiKeysFirstPage(): Promise<ApiKeyList> {
  await mockDelay();
  return MOCK_API_KEYS;
}

export async function getRateCardBooksFirstPage(): Promise<RateCardBookList> {
  await mockDelay();
  return MOCK_RATE_CARD_BOOKS;
}

export async function getConnectStatus(): Promise<ConnectStatus> {
  await mockDelay();
  return MOCK_CONNECT_STATUS;
}
