/** Minimal shape needed for cost calculation — works with both Dimension and DimensionInput */
interface CalcDimension {
  metricName: string;
  pricingType: "per_unit" | "flat";
  costPerUnitMicros: number;
  label: string;
}

export interface DimensionCost {
  metricName: string;
  label: string;
  quantity: number;
  priceDollars: number;
  pricingType: "per_unit" | "flat";
  cost: number;
}

export interface CostResult {
  dimensions: DimensionCost[];
  total: number;
}

export function calculateCosts(
  dimensions: CalcDimension[],
  quantities: Record<string, number>,
): CostResult {
  const results: DimensionCost[] = dimensions.map((dim) => {
    const qty = quantities[dim.metricName] ?? 0;
    const priceDollars = dim.costPerUnitMicros / 1_000_000;
    const cost =
      dim.pricingType === "flat" ? (qty > 0 ? priceDollars : 0) : qty * priceDollars;

    return {
      metricName: dim.metricName,
      label: dim.label,
      quantity: qty,
      priceDollars,
      pricingType: dim.pricingType,
      cost,
    };
  });

  const total = results.reduce((sum, r) => sum + r.cost, 0);
  return { dimensions: results, total };
}

export function calculateDistribution(
  result: CostResult,
): Array<{ metricName: string; label: string; percentage: number }> {
  if (result.total === 0) return [];

  return result.dimensions
    .map((d) => ({
      metricName: d.metricName,
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
