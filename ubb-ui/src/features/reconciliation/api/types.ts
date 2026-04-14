// src/features/reconciliation/api/types.ts

export type VersionStatus = "active" | "superseded" | "retroactive";
export type AdjustmentType = "credit_refund" | "missing_costs";
export type DistributionMode = "lump_sum" | "even_daily" | "proportional" | "manual";
export type AuditEntryType = "period_insert" | "boundary_shift" | "price_edit" | "credit_recorded";

export interface DimensionPrice {
  key: string;
  type: "per_unit" | "flat";
  unitPrice: number;
  displayPrice: string;
}

export interface PricingVersion {
  id: string;
  label: string;
  status: VersionStatus;
  startDate: string;
  endDate: string | null;
  durationDays: number;
  eventCount: number;
  cost: number;
  dimensions: DimensionPrice[];
}

export interface TimelineSegment {
  id: string;
  versionId: string;
  label: string;
  cost: number;
  flex: number;
  color: string;
}

export interface TimelineData {
  originalTrack: TimelineSegment[];
  reconciledTrack: TimelineSegment[];
  originalTotal: number;
  reconciledTotal: number;
  adjustmentTotal: number;
  dateMarkers: string[];
}

export interface AuditEntry {
  id: string;
  type: AuditEntryType;
  title: string;
  description: string;
  metadata: string;
  delta: number;
  deltaLabel: string;
}

export interface Adjustment {
  id: string;
  type: AdjustmentType;
  amount: number;
  product: string | null;
  distributionMode: DistributionMode;
  reason: string;
  evidence: string | null;
  date: string;
}

export interface ReconciliationData {
  card: {
    id: string;
    name: string;
    provider: string;
    cardId: string;
    status: "active" | "inactive";
  };
  stats: {
    originalTracked: number;
    reconciledTotal: number;
    netAdjustments: number;
    adjustmentCount: number;
    eventCount: number;
    currentVersion: string;
    since: string;
  };
  versions: PricingVersion[];
  timeline: TimelineData;
  adjustments: Adjustment[];
  auditTrail: AuditEntry[];
}

export interface EditPricesRequest {
  versionId: string;
  newPrices: Record<string, number>;
  reason: string;
}

export interface AdjustBoundaryRequest {
  fromVersionId: string;
  toVersionId: string;
  newBoundaryDate: string;
  newBoundaryTime: string;
  reason: string;
}

export interface InsertPeriodRequest {
  versionId: string;
  splitDate: string;
  splitTime: string;
  newPrices: Record<string, number>;
  reason: string;
}

export interface RecordAdjustmentRequest {
  type: AdjustmentType;
  amount: number;
  product: string | null;
  distributionMode: DistributionMode;
  distributionConfig: Record<string, unknown>;
  reason: string;
  evidence: string | null;
}
