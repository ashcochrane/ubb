export type PricingType = "per_unit" | "flat";
export type PricingPattern = "token" | "request" | "mixed";
export type CardStatus = "draft" | "active" | "archived";
export type SourceType = "template" | "custom";

export interface Dimension {
  key: string;
  type: PricingType;
  price: number;
  label: string;
  unit: string;
  displayPrice?: string;
}

export interface PricingCard {
  id: string;
  cardId: string;
  name: string;
  provider: string;
  pricingPattern: PricingPattern;
  status: CardStatus;
  dimensions: Dimension[];
  description?: string;
  pricingSourceUrl?: string;
  product?: string;
  version: number;
  createdAt: string;
  updatedAt: string;
}

export interface Template {
  id: string;
  name: string;
  provider: string;
  dimensionCount: number;
  pricingPattern: PricingPattern;
  dimensions: Dimension[];
  description?: string;
}

export interface CreateCardRequest {
  name: string;
  cardId: string;
  provider: string;
  pricingPattern: PricingPattern;
  dimensions: Dimension[];
  description?: string;
  pricingSourceUrl?: string;
  product?: string;
  status: CardStatus;
}
