import { describe, expect, it } from "vitest";
import {
  calculateCosts,
  calculateDistribution,
  projectCosts,
} from "./calculations";
import type { Dimension } from "../api/types";

// Prices in micros (integer). $0.000001/token, $0.000002/token, $0.10/request flat.
const tokenDimensions: Dimension[] = [
  {
    id: "dim-1",
    metricName: "input_tokens",
    pricingType: "per_unit",
    costPerUnitMicros: 1, // $0.000001 per token
    providerCostPerUnitMicros: null,
    unitQuantity: 1,
    currency: "USD",
    label: "Input tokens",
    unit: "per token",
    validFrom: "2024-01-01T00:00:00Z",
    validTo: null,
  },
  {
    id: "dim-2",
    metricName: "output_tokens",
    pricingType: "per_unit",
    costPerUnitMicros: 2, // $0.000002 per token
    providerCostPerUnitMicros: null,
    unitQuantity: 1,
    currency: "USD",
    label: "Output tokens",
    unit: "per token",
    validFrom: "2024-01-01T00:00:00Z",
    validTo: null,
  },
  {
    id: "dim-3",
    metricName: "grounding_requests",
    pricingType: "flat",
    costPerUnitMicros: 100_000, // $0.10 per request
    providerCostPerUnitMicros: null,
    unitQuantity: 1,
    currency: "USD",
    label: "Grounding requests",
    unit: "per request",
    validFrom: "2024-01-01T00:00:00Z",
    validTo: null,
  },
];

describe("calculateCosts", () => {
  it("calculates per-unit costs correctly", () => {
    const result = calculateCosts(tokenDimensions, {
      input_tokens: 1500,
      output_tokens: 800,
      grounding_requests: 1,
    });

    // 1500 * (1/1_000_000) = 0.0015
    expect(result.dimensions[0]!.cost).toBeCloseTo(0.0015, 6);
    // 800 * (2/1_000_000) = 0.0016
    expect(result.dimensions[1]!.cost).toBeCloseTo(0.0016, 6);
    // flat $0.10
    expect(result.dimensions[2]!.cost).toBeCloseTo(0.1, 6);
    // total = 0.0015 + 0.0016 + 0.1 = 0.1031
    expect(result.total).toBeCloseTo(0.1031, 5);
  });

  it("returns zero cost for flat dimension with zero quantity", () => {
    const result = calculateCosts(tokenDimensions, {
      input_tokens: 0,
      output_tokens: 0,
      grounding_requests: 0,
    });
    expect(result.total).toBe(0);
  });

  it("handles missing quantities as zero", () => {
    const result = calculateCosts(tokenDimensions, {});
    expect(result.total).toBe(0);
  });
});

describe("calculateDistribution", () => {
  it("calculates percentages sorted by highest first", () => {
    const costs = calculateCosts(tokenDimensions, {
      input_tokens: 1500,
      output_tokens: 800,
      grounding_requests: 1,
    });
    const dist = calculateDistribution(costs);

    // grounding_requests ($0.10) dominates over input ($0.0015) and output ($0.0016)
    expect(dist[0]!.metricName).toBe("grounding_requests");
    expect(dist[0]!.percentage).toBeGreaterThan(90);
    expect(dist.reduce((s, d) => s + d.percentage, 0)).toBeCloseTo(100, 1);
  });

  it("returns empty array when total is zero", () => {
    const costs = calculateCosts(tokenDimensions, {});
    expect(calculateDistribution(costs)).toEqual([]);
  });
});

describe("projectCosts", () => {
  it("projects daily and monthly costs", () => {
    const result = projectCosts(0.035, 1000);
    expect(result.daily).toBeCloseTo(35, 1);
    expect(result.monthly).toBeCloseTo(1050, 0);
  });
});
