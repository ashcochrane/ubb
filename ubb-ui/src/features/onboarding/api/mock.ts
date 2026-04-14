import type {
  StripeValidationResult,
  StripeSyncPreview,
  MatchResult,
  MatchCustomersRequest,
  ValidateKeyRequest,
  ActivateRequest,
} from "./types";
import { mockStripeCustomers } from "./mock-data";
import { READ_PERMISSIONS, BILLING_PERMISSIONS } from "../lib/constants";
import { mockDelay } from "@/lib/api-provider";

export async function validateStripeKey(req: ValidateKeyRequest): Promise<{
  validation: StripeValidationResult;
  preview: StripeSyncPreview;
}> {
  await mockDelay(800);

  const invalidResult = (error: string) => ({
    validation: { valid: false, permissions: [], error } as StripeValidationResult,
    preview: { customerCount: 0, activeSubscriptions: 0, revenue30d: 0 },
  });

  if (req.apiKey.startsWith("sk_")) {
    return invalidResult("This is a secret key — it has too much access. Create a restricted key (rk_) with limited permissions instead.");
  }

  if (!req.apiKey.startsWith("rk_")) {
    return invalidResult("Invalid key format. Use a restricted key starting with rk_");
  }

  return {
    validation: {
      valid: true,
      permissions: req.mode === "billing" ? BILLING_PERMISSIONS : READ_PERMISSIONS,
    },
    preview: { customerCount: 21, activeSubscriptions: 18, revenue30d: 8420 },
  };
}

export async function matchCustomers(req: MatchCustomersRequest): Promise<MatchResult> {
  await mockDelay(600);

  const customers = mockStripeCustomers.map((c) => {
    let identifier: string | null = null;
    switch (req.identifierMode) {
      case "stripe_id": identifier = c.stripeId; break;
      case "email": identifier = c.email; break;
      case "internal_id": identifier = c.internalSlug; break;
      case "metadata": identifier = c.metadataKey; break;
    }
    return {
      name: c.name,
      stripeId: c.stripeId,
      identifier,
      revenue30d: c.revenue30d,
      status: identifier ? "matched" as const : "manual" as const,
    };
  });

  const matched = customers.filter((c) => c.status === "matched").length;
  return { total: customers.length, matched, needsManual: customers.length - matched, customers };
}

// eslint-disable-next-line @typescript-eslint/no-unused-vars
export async function activateOnboarding(_req: ActivateRequest): Promise<{ success: boolean }> {
  await mockDelay(500);
  return { success: true };
}
