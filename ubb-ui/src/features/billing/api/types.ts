// src/features/billing/api/types.ts

export type MarginLevel = "default" | "product" | "card";
export type MarginSource = "set" | "override" | "inherited";
export type ChangeEffectiveness = "immediately" | "scheduled";

export interface MarginNode {
  id: string;
  level: MarginLevel;
  name: string;
  marginPct: number;
  multiplier: number;
  source: MarginSource;
  parentSource: string;
  billings30d: number;
  children?: MarginNode[];
}

export interface MarginStats {
  blendedMargin: number;
  apiCosts30d: number;
  customerBillings30d: number;
  marginEarned30d: number;
}

export interface MarginChange {
  id: string;
  level: MarginLevel;
  targetName: string;
  fromPct: number;
  toPct: number;
  description: string;
  reason: string;
  effectiveness: ChangeEffectiveness;
  effectiveDate?: string;
  appliedBy: string;
  createdAt: string;
  estimatedImpact: number;
}

export interface MarginDashboardData {
  stats: MarginStats;
  hierarchy: MarginNode[];
  changes: MarginChange[];
}

export interface UpdateMarginRequest {
  nodeId: string;
  level: MarginLevel;
  newMarginPct: number;
  inherit: boolean;
  effectiveness: ChangeEffectiveness;
  effectiveDate?: string;
  reason: string;
}
