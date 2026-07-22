export type PricingType = "per_unit" | "flat";
export type CardStatus = "draft" | "active" | "archived";

export interface Dimension {
  id: string;
  metricName: string;
  pricingType: PricingType;
  costPerUnitMicros: number;
  providerCostPerUnitMicros: number | null;
  unitQuantity: number;
  currency: string;
  label: string;
  unit: string;
  validFrom: string;
  validTo: string | null;
}

export interface DimensionInput {
  metricName: string;
  pricingType: PricingType;
  costPerUnitMicros: number;
  providerCostPerUnitMicros: number | null;
  unitQuantity: number;
  currency: string;
  label: string;
  unit: string;
}

export interface PricingCard {
  id: string;
  slug: string;
  name: string;
  provider: string;
  description: string;
  pricingSourceUrl: string;
  groupId: string | null;
  groupName: string | null;
  status: CardStatus;
  dimensions: Dimension[];
  createdAt: string;
  updatedAt: string;
}

export interface CreateCardRequest {
  name: string;
  slug: string;
  provider: string;
  description: string;
  pricingSourceUrl: string;
  groupId: string | null;
  status: CardStatus;
  dimensions: DimensionInput[];
}

export interface CardListResponse {
  data: PricingCard[];
  nextCursor: string | null;
  hasMore: boolean;
}

// UI-only: bundled card-creation templates. Not a backend type.
export interface Template {
  id: string;
  name: string;
  provider: string;
  description: string;
  dimensions: DimensionInput[];
}
