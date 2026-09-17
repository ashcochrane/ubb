// Mock implementation — same exported signatures as ./api.ts, contract-correct
// shapes, deterministic fixtures (see mock-data.ts for the story).

import { mockDelay } from "@/lib/api-provider";

import {
  MOCK_API_KEYS,
  MOCK_CONNECT_STATUS,
  MOCK_LIFETIME_ECONOMICS,
  MOCK_PRICING_BOOKS,
  MOCK_UNPROFITABLE,
  mockCustomerEconomics,
  mockDailyEconomics,
  mockGroupedEconomics,
  mockTenantEconomics,
} from "./mock-data";
import type {
  ApiKeyList,
  BreakdownAxis,
  ConnectStatus,
  Economics,
  PricingBookList,
  Unprofitable,
  Window,
} from "./types";

export async function getTenantEconomics(window: Window): Promise<Economics> {
  await mockDelay();
  return mockTenantEconomics(window);
}

export async function getGroupedEconomics(
  window: Window,
  groupBy: BreakdownAxis,
): Promise<Economics> {
  await mockDelay();
  return mockGroupedEconomics(window, groupBy);
}

export async function getLifetimeEconomics(): Promise<Economics> {
  await mockDelay();
  return MOCK_LIFETIME_ECONOMICS;
}

export async function getDailyEconomics(window: Window): Promise<Economics> {
  await mockDelay();
  return mockDailyEconomics(window);
}

export async function getCustomerEconomics(
  window: Window,
): Promise<Economics> {
  await mockDelay();
  return mockCustomerEconomics(window);
}

export async function getUnprofitable(): Promise<Unprofitable> {
  await mockDelay();
  return MOCK_UNPROFITABLE;
}

export async function getApiKeysFirstPage(): Promise<ApiKeyList> {
  await mockDelay();
  return MOCK_API_KEYS;
}

export async function getPricingBooksFirstPage(): Promise<PricingBookList> {
  await mockDelay();
  return MOCK_PRICING_BOOKS;
}

export async function getConnectStatus(): Promise<ConnectStatus> {
  await mockDelay();
  return MOCK_CONNECT_STATUS;
}
