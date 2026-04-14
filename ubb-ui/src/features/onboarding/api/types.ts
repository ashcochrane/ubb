export type OnboardingMode = "track" | "revenue" | "billing";
export type IdentifierMode = "stripe_id" | "email" | "internal_id" | "metadata";
export type MatchStatus = "matched" | "manual" | "unmatched";

export interface StripePermission {
  resource: string;
  access: "Read" | "Write" | "None";
  required: boolean;
  description?: string;
}

export interface StripeValidationResult {
  valid: boolean;
  permissions: StripePermission[];
  error?: string;
}

export interface StripeSyncPreview {
  customerCount: number;
  activeSubscriptions: number;
  revenue30d: number;
}

export interface StripeCustomer {
  name: string;
  stripeId: string;
  email: string | null;
  internalSlug: string | null;
  metadataKey: string | null;
  revenue30d: number;
}

export interface CustomerMatch {
  name: string;
  stripeId: string;
  identifier: string | null;
  revenue30d: number;
  status: MatchStatus;
}

export interface MatchResult {
  total: number;
  matched: number;
  needsManual: number;
  customers: CustomerMatch[];
}

export interface ValidateKeyRequest {
  apiKey: string;
  mode: OnboardingMode;
}

export interface MatchCustomersRequest {
  identifierMode: IdentifierMode;
  metadataKey?: string;
}

export interface ActivateRequest {
  mode: OnboardingMode;
  stripeKey?: string;
  identifierMode?: IdentifierMode;
  metadataKey?: string;
  defaultMargin?: number;
  alertThresholds?: {
    notifyAt: number;
    remindAt: number;
    pauseAtZero: boolean;
  };
}
