import { describe, expect, it } from "vitest";
import {
  calculateCosts,
  calculateDistribution,
  projectCosts,
} from "./calculations";
import type { Dimension } from "../api/types";

const tokenDimensions: Dimension[] = [
  { key: "input_tokens", type: "per_unit", price: 0.0000001, label: "Input tokens", unit: "per 1M tokens" },
  { key: "output_tokens", type: "per_unit", price: 0.0000004, label: "Output tokens", unit: "per 1M tokens" },
  { key: "grounding_requests", type: "flat", price: 0.035, label: "Grounding requests", unit: "per request" },
];

describe("calculateCosts", () => {
  it("calculates per-unit costs correctly", () => {
    const result = calculateCosts(tokenDimensions, {
      input_tokens: 1500,
      output_tokens: 800,
      grounding_requests: 1,
    });

    expect(result.dimensions[0].cost).toBeCloseTo(0.00015, 8);
    expect(result.dimensions[1].cost).toBeCloseTo(0.00032, 8);
    expect(result.dimensions[2].cost).toBeCloseTo(0.035, 8);
    expect(result.total).toBeCloseTo(0.03547, 5);
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

    expect(dist[0].key).toBe("grounding_requests");
    expect(dist[0].percentage).toBeGreaterThan(90);
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
