// The customers feature's four views of the one query keep the revenue view
// their answer was stated under (#548). The mock answers `recorded`, so each
// answer is re-stated under both values — a narrowing that wrote either word in
// place of the answer's would fail the other.

import { describe, expect, it } from "vitest";

import { REVENUE_BASIS_VALUES } from "@/lib/vocabulary";

import {
  CUS_ACME,
  mockCustomerList,
} from "./mock-data";
import { customersApi } from "./provider";
import {
  toCustomerRows,
  toOneCustomer,
  toTrendPoints,
  toUsageSeries,
} from "./types";

const RANGE = { start_date: "2026-07-01", end_date: "2026-07-31" };

describe("the customers narrowings keep the answer's basis", () => {
  it.each(REVENUE_BASIS_VALUES)("keeps %s on the list, the cards, the trend and the usage series", async (basis) => {
    expect(toCustomerRows({ ...mockCustomerList(RANGE), basis }).basis).toBe(basis);

    const one = await customersApi.getCustomerMargin(CUS_ACME, RANGE);
    expect(toOneCustomer({ ...one, basis }).basis).toBe(basis);

    const trend = await customersApi.getMarginTrend(CUS_ACME, 6);
    expect(toTrendPoints({ ...trend, basis }).basis).toBe(basis);

    const usage = await customersApi.getUsageTimeseries(CUS_ACME, RANGE);
    expect(toUsageSeries({ ...usage, basis }).basis).toBe(basis);
  });
});
