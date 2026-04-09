import type { Dimension } from "../api/types";

export interface DimensionCost {
  key: string;
  label: string;
  quantity: number;
  price: number;
  type: "per_unit" | "flat";
  cost: number;
}

export interface CostResult {
  dimensions: DimensionCost[];
  total: number;
}

export function calculateCosts(
  dimensions: Dimension[],
  quantities: Record<string, number>,
): CostResult {
  const results: DimensionCost[] = dimensions.map((dim) => {
    const qty = quantities[dim.key] ?? 0;
    const cost =
      dim.type === "flat" ? (qty > 0 ? dim.price : 0) : qty * dim.price;

    return {
      key: dim.key,
      label: dim.label,
      quantity: qty,
      price: dim.price,
      type: dim.type,
      cost,
    };
  });

  const total = results.reduce((sum, r) => sum + r.cost, 0);
  return { dimensions: results, total };
}

export function calculateDistribution(
  result: CostResult,
): Array<{ key: string; label: string; percentage: number }> {
  if (result.total === 0) return [];

  return result.dimensions
    .map((d) => ({
      key: d.key,
      label: d.label,
      percentage: (d.cost / result.total) * 100,
    }))
    .sort((a, b) => b.percentage - a.percentage);
}

export function projectCosts(
  costPerEvent: number,
  eventsPerDay: number,
): { daily: number; monthly: number } {
  return {
    daily: costPerEvent * eventsPerDay,
    monthly: costPerEvent * eventsPerDay * 30,
  };
}
