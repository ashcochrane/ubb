# Phase 4: Onboarding — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **IMPORTANT:** Do NOT commit. The user handles all git operations.
>
> **Design source of truth:** 7 mockup files in `docs/design/files/`. Key rationale in `docs/design/ui-flow-design-rationale.md` section 1.
>
> **Mockup consolidation:** The 7 mockups show overlapping variants of the same flow. This plan consolidates them into one implementation with 3 branching paths that share components.

**Goal:** Build the onboarding flow with 3 paths (track costs, revenue+costs, billing) — mode selection, Stripe key validation, customer mapping, margin configuration, and review/activation.

**Architecture:** Feature module at `src/features/onboarding/`. The onboarding is a multi-step wizard with path-dependent steps. Shared components (Stripe key validator, customer mapper, permissions table) are reused across paths. State is managed with React Hook Form across all steps. The onboarding route is separate from the main `_app` layout (no sidebar — dedicated full-page flow).

**Tech Stack:** React 19, TypeScript, React Hook Form + Zod, TanStack Query, TanStack Router, Lucide icons

---

## The 3 Paths

| Path | Steps | Stripe? | Mockup sources |
|------|-------|---------|---------------|
| Track costs | Mode selection → done (redirect to pricing cards) | No | `complete_onboarding_4_screens.html` (mode selector) |
| Revenue + costs | Mode → Stripe key (read) → Customer mapping → Review/activate | Read-only | `screen_4_stripe_integration.html`, `step_2_customer_identification.html`, `step_3_confirm_and_activate.html` |
| Billing | Mode → Stripe key (read+write) → Customer mapping → Margin config → Review/activate | Read+write | `billing_onboarding_fresh_customer_4_steps.html`, `billing_mode_stripe_adaptation.html` |

---

## File Map

### API Layer

| File | Responsibility |
|------|---------------|
| `src/features/onboarding/api/types.ts` | Onboarding types (modes, Stripe validation, customer matching, margin config) |
| `src/features/onboarding/api/mock-data.ts` | Mock Stripe customers, validation responses |
| `src/features/onboarding/api/mock.ts` | Mock adapter |
| `src/features/onboarding/api/api.ts` | Real API adapter (placeholder) |
| `src/features/onboarding/api/provider.ts` | selectProvider |
| `src/features/onboarding/api/queries.ts` | TanStack Query hooks |

### Shared Onboarding Components

| File | Responsibility |
|------|---------------|
| `src/features/onboarding/components/onboarding-layout.tsx` | Full-page layout (no sidebar, centered content, progress bar) |
| `src/features/onboarding/components/onboarding-progress.tsx` | Step progress bar with completed/active/pending states |
| `src/features/onboarding/components/mode-selector.tsx` | 3-card mode selection (track/revenue/billing) |
| `src/features/onboarding/components/stripe-key-step.tsx` | Stripe key input, validation, permissions table, sync preview |
| `src/features/onboarding/components/permissions-table.tsx` | Required Stripe permissions display |
| `src/features/onboarding/components/customer-mapping-step.tsx` | Identifier mode picker + match results table |
| `src/features/onboarding/components/match-results-table.tsx` | Customer mapping table with manual input for unmatched |
| `src/features/onboarding/components/margin-config-step.tsx` | Default margin slider + billing preview (billing path only) |
| `src/features/onboarding/components/review-step.tsx` | Review cards + activation for both paths |
| `src/features/onboarding/components/activation-success.tsx` | Success state with next steps |

### Wizard Container

| File | Responsibility |
|------|---------------|
| `src/features/onboarding/components/onboarding-wizard.tsx` | Main wizard: form setup, path routing, step navigation |

### Schema

| File | Responsibility |
|------|---------------|
| `src/features/onboarding/lib/schema.ts` | Zod schema for onboarding form |

### Route

| File | Responsibility |
|------|---------------|
| `src/app/routes/onboarding.tsx` | Onboarding route (outside `_app` layout — no sidebar) |

---

## Task 1: Types + Schema + API Layer

**Files:**
- Create: `src/features/onboarding/api/types.ts`
- Create: `src/features/onboarding/lib/schema.ts`
- Create: `src/features/onboarding/api/mock-data.ts`
- Create: `src/features/onboarding/api/mock.ts`
- Create: `src/features/onboarding/api/api.ts`
- Create: `src/features/onboarding/api/provider.ts`
- Create: `src/features/onboarding/api/queries.ts`

- [ ] **Step 1: Create types.ts**

```typescript
// src/features/onboarding/api/types.ts

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
  email: string;
  internalSlug: string;
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
```

- [ ] **Step 2: Create schema.ts**

```typescript
// src/features/onboarding/lib/schema.ts
import { z } from "zod";

export const onboardingSchema = z.object({
  mode: z.enum(["track", "revenue", "billing"]),

  // Stripe (revenue + billing paths)
  stripeKey: z.string().optional(),
  keyValidated: z.boolean().default(false),

  // Customer mapping (revenue + billing paths)
  identifierMode: z.enum(["stripe_id", "email", "internal_id", "metadata"]).optional(),
  metadataKey: z.string().optional(),
  mappingComplete: z.boolean().default(false),

  // Margin config (billing path only)
  defaultMargin: z.number().min(0).max(200).default(50),
  notifyAt: z.number().default(50),
  remindAt: z.number().default(25),
  pauseAtZero: z.boolean().default(false),
});

export type OnboardingFormValues = z.infer<typeof onboardingSchema>;
```

- [ ] **Step 3: Create mock-data.ts**

```typescript
// src/features/onboarding/api/mock-data.ts
import type { StripeCustomer, StripePermission } from "./types";

export const mockStripeCustomers: StripeCustomer[] = [
  { name: "Acme Corp", stripeId: "cus_R4kB9xPm2nQ", email: "billing@acmecorp.com", internalSlug: "acme_corp", metadataKey: "acme_corp", revenue30d: 2400 },
  { name: "BrightPath Ltd", stripeId: "cus_Q7mN3vHj8wL", email: "finance@brightpath.co", internalSlug: "brightpath", metadataKey: "brightpath", revenue30d: 1800 },
  { name: "NovaTech Inc", stripeId: "cus_S2pK5tRn7xY", email: "accounts@novatech.io", internalSlug: "novatech", metadataKey: "novatech", revenue30d: 950 },
  { name: "Helios Digital", stripeId: "cus_U6nR2wKm9xQ", email: "ap@heliosdigital.com", internalSlug: "helios", metadataKey: "helios", revenue30d: 720 },
  { name: "ClearView Analytics", stripeId: "cus_V3bP8sHn5mJ", email: "pay@clearview.ai", internalSlug: "clearview", metadataKey: "clearview", revenue30d: 150 },
  { name: "Eko Systems", stripeId: "cus_W1cT4rFk7pN", email: null as unknown as string, internalSlug: null as unknown as string, metadataKey: null, revenue30d: 90 },
];

export const readPermissions: StripePermission[] = [
  { resource: "Customers", access: "Read", required: true },
  { resource: "Subscriptions", access: "Read", required: true },
  { resource: "Invoices", access: "Read", required: true },
  { resource: "Charges", access: "Read", required: true },
  { resource: "Everything else", access: "None", required: false },
];

export const billingPermissions: StripePermission[] = [
  { resource: "Customers", access: "Read", required: true },
  { resource: "Subscriptions", access: "Read", required: true },
  { resource: "Invoices", access: "Read", required: true },
  { resource: "Charges", access: "Read", required: true },
  { resource: "Customer balance transactions", access: "Write", required: true, description: "Allows debiting customer balances for usage" },
  { resource: "Everything else", access: "None", required: false },
];
```

- [ ] **Step 4: Create mock.ts**

```typescript
// src/features/onboarding/api/mock.ts
import type {
  StripeValidationResult,
  StripeSyncPreview,
  MatchResult,
  MatchCustomersRequest,
  ValidateKeyRequest,
  ActivateRequest,
} from "./types";
import { mockStripeCustomers, readPermissions, billingPermissions } from "./mock-data";

const delay = (ms = 400) => new Promise((r) => setTimeout(r, ms));

export async function validateStripeKey(req: ValidateKeyRequest): Promise<{
  validation: StripeValidationResult;
  preview: StripeSyncPreview;
}> {
  await delay(800);

  // Simulate invalid key
  if (!req.apiKey.startsWith("rk_")) {
    return {
      validation: {
        valid: false,
        permissions: [],
        error: "Invalid key format. Use a restricted key starting with rk_",
      },
      preview: { customerCount: 0, activeSubscriptions: 0, revenue30d: 0 },
    };
  }

  return {
    validation: {
      valid: true,
      permissions: req.mode === "billing" ? billingPermissions : readPermissions,
    },
    preview: {
      customerCount: 21,
      activeSubscriptions: 18,
      revenue30d: 8420,
    },
  };
}

export async function matchCustomers(req: MatchCustomersRequest): Promise<MatchResult> {
  await delay(600);

  const customers = mockStripeCustomers.map((c) => {
    let identifier: string | null = null;
    switch (req.identifierMode) {
      case "stripe_id":
        identifier = c.stripeId;
        break;
      case "email":
        identifier = c.email || null;
        break;
      case "internal_id":
        identifier = c.internalSlug || null;
        break;
      case "metadata":
        identifier = c.metadataKey;
        break;
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

  return {
    total: customers.length,
    matched,
    needsManual: customers.length - matched,
    customers,
  };
}

export async function activateOnboarding(_req: ActivateRequest): Promise<{ success: boolean }> {
  await delay(500);
  return { success: true };
}
```

- [ ] **Step 5: Create api.ts, provider.ts, queries.ts**

```typescript
// src/features/onboarding/api/api.ts
import type {
  StripeValidationResult,
  StripeSyncPreview,
  MatchResult,
  MatchCustomersRequest,
  ValidateKeyRequest,
  ActivateRequest,
} from "./types";
import { tenantApi } from "@/api/client";

export async function validateStripeKey(req: ValidateKeyRequest): Promise<{
  validation: StripeValidationResult;
  preview: StripeSyncPreview;
}> {
  const { data } = await tenantApi.POST("/onboarding/validate-stripe-key", { body: req });
  return data as { validation: StripeValidationResult; preview: StripeSyncPreview };
}

export async function matchCustomers(req: MatchCustomersRequest): Promise<MatchResult> {
  const { data } = await tenantApi.POST("/onboarding/match-customers", { body: req });
  return data as MatchResult;
}

export async function activateOnboarding(req: ActivateRequest): Promise<{ success: boolean }> {
  const { data } = await tenantApi.POST("/onboarding/activate", { body: req });
  return data as { success: boolean };
}
```

```typescript
// src/features/onboarding/api/provider.ts
import { selectProvider } from "@/lib/api-provider";
import * as mock from "./mock";
import * as api from "./api";

export const onboardingApi = selectProvider({ mock, api });
```

```typescript
// src/features/onboarding/api/queries.ts
import { useMutation } from "@tanstack/react-query";
import { onboardingApi } from "./provider";
import type { ValidateKeyRequest, MatchCustomersRequest, ActivateRequest } from "./types";

export function useValidateStripeKey() {
  return useMutation({
    mutationFn: (req: ValidateKeyRequest) => onboardingApi.validateStripeKey(req),
  });
}

export function useMatchCustomers() {
  return useMutation({
    mutationFn: (req: MatchCustomersRequest) => onboardingApi.matchCustomers(req),
  });
}

export function useActivateOnboarding() {
  return useMutation({
    mutationFn: (req: ActivateRequest) => onboardingApi.activateOnboarding(req),
  });
}
```

- [ ] **Step 6: Verify build**

Run: `pnpm build`
Expected: Build succeeds.

---

## Task 2: Onboarding Layout + Progress Bar + Route

**Files:**
- Create: `src/features/onboarding/components/onboarding-layout.tsx`
- Create: `src/features/onboarding/components/onboarding-progress.tsx`
- Create: `src/app/routes/onboarding.tsx`

- [ ] **Step 1: Create onboarding-progress.tsx**

Step progress indicator — numbered segments, completed/active/pending states.

```typescript
// src/features/onboarding/components/onboarding-progress.tsx
import { Check } from "lucide-react";
import { cn } from "@/lib/utils";

interface OnboardingProgressProps {
  steps: string[];
  currentStep: number;
}

export function OnboardingProgress({ steps, currentStep }: OnboardingProgressProps) {
  return (
    <div className="mb-6 flex items-center justify-center">
      {steps.map((label, idx) => {
        const completed = idx < currentStep;
        const active = idx === currentStep;

        return (
          <div key={label} className="flex items-center">
            <div className="flex flex-col items-center">
              <div
                className={cn(
                  "flex h-7 w-7 items-center justify-center rounded-full text-[11px] font-semibold transition-colors",
                  completed && "bg-foreground text-background",
                  active && "border-2 border-foreground text-foreground",
                  !completed && !active && "border border-border text-muted-foreground",
                )}
              >
                {completed ? <Check className="h-3.5 w-3.5" /> : idx + 1}
              </div>
              <span className="mt-1.5 text-[10px] text-muted-foreground">{label}</span>
            </div>
            {idx < steps.length - 1 && (
              <div
                className={cn(
                  "mx-3 h-px w-12",
                  completed ? "bg-foreground" : "bg-border",
                )}
              />
            )}
          </div>
        );
      })}
    </div>
  );
}
```

- [ ] **Step 2: Create onboarding-layout.tsx**

Full-page centered layout (no sidebar). Used by the onboarding route.

```typescript
// src/features/onboarding/components/onboarding-layout.tsx
import type { ReactNode } from "react";

interface OnboardingLayoutProps {
  children: ReactNode;
}

export function OnboardingLayout({ children }: OnboardingLayoutProps) {
  return (
    <div className="flex min-h-screen flex-col bg-background">
      <div className="mx-auto w-full max-w-[640px] px-6 py-8">
        <div className="mb-8 text-lg font-bold tracking-tight">UBB</div>
        {children}
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Create onboarding route**

This route sits outside `_app` (no sidebar). It needs auth but no nav shell.

```typescript
// src/app/routes/onboarding.tsx
import { createFileRoute, redirect } from "@tanstack/react-router";
import { OnboardingLayout } from "@/features/onboarding/components/onboarding-layout";
import { OnboardingWizard } from "@/features/onboarding/components/onboarding-wizard";
import { API_PROVIDER } from "@/lib/api-provider";

const noAuthMode = !import.meta.env.VITE_CLERK_PUBLISHABLE_KEY && API_PROVIDER === "mock";

export const Route = createFileRoute("/onboarding")({
  beforeLoad: ({ context }) => {
    if (!noAuthMode && !context.auth?.isSignedIn) {
      throw redirect({ to: "/sign-in" });
    }
  },
  component: OnboardingPage,
});

function OnboardingPage() {
  return (
    <OnboardingLayout>
      <OnboardingWizard />
    </OnboardingLayout>
  );
}
```

Note: `OnboardingWizard` doesn't exist yet — it'll be created in Task 4. For now create a placeholder so the route compiles:

```typescript
// src/features/onboarding/components/onboarding-wizard.tsx (placeholder)
export function OnboardingWizard() {
  return <div className="text-center text-sm text-muted-foreground">Onboarding wizard — Task 4</div>;
}
```

- [ ] **Step 4: Verify build**

Run: `pnpm build`
Expected: Build succeeds. `/onboarding` route renders with UBB logo + placeholder.

---

## Task 3: Mode Selector

**Files:**
- Create: `src/features/onboarding/components/mode-selector.tsx`

- [ ] **Step 1: Create mode-selector.tsx**

3-card mode selection matching `complete_onboarding_4_screens.html` mode selection screen and `billing_mode_stripe_adaptation.html` 3-path selector.

```typescript
// src/features/onboarding/components/mode-selector.tsx
import { useFormContext } from "react-hook-form";
import { BarChart3, TrendingUp, CreditCard } from "lucide-react";
import type { OnboardingFormValues } from "../lib/schema";
import type { OnboardingMode } from "../api/types";
import { cn } from "@/lib/utils";

interface ModeOption {
  value: OnboardingMode;
  icon: React.ElementType;
  title: string;
  subtitle: string;
  features: string[];
  badge?: { label: string; color: string };
  stripeNeeded: string;
}

const modes: ModeOption[] = [
  {
    value: "track",
    icon: BarChart3,
    title: "Track costs",
    subtitle: "Monitor API costs per customer, per product. No revenue data.",
    features: ["Pricing cards + SDK", "Cost dashboard", "Data export"],
    stripeNeeded: "No Stripe needed",
  },
  {
    value: "revenue",
    icon: TrendingUp,
    title: "Revenue and costs",
    subtitle: "Pull revenue from Stripe and pair it with tracked costs to show profitability.",
    features: ["Everything in Track costs", "Stripe revenue sync", "Profitability dashboard"],
    badge: { label: "Recommended", color: "bg-blue-50 text-blue-700 dark:bg-blue-900/20 dark:text-blue-400" },
    stripeNeeded: "Stripe (read-only)",
  },
  {
    value: "billing",
    icon: CreditCard,
    title: "Bill your customers",
    subtitle: "Everything above, plus debit customer Stripe balances for each API event.",
    features: ["Everything in Revenue + costs", "Balance debiting", "Margin management", "Balance alerts"],
    badge: { label: "New", color: "bg-purple-50 text-purple-700 dark:bg-purple-900/20 dark:text-purple-400" },
    stripeNeeded: "Stripe (read + write)",
  },
];

export function ModeSelector() {
  const { watch, setValue } = useFormContext<OnboardingFormValues>();
  const selectedMode = watch("mode");

  return (
    <div className="space-y-4">
      <div className="text-center">
        <h1 className="text-[18px] font-semibold">How do you want to use the platform?</h1>
        <p className="mt-1 text-[12px] text-muted-foreground">
          You can change this later. Each mode builds on the previous one.
        </p>
      </div>

      <div className="grid grid-cols-3 gap-3">
        {modes.map((m) => (
          <button
            key={m.value}
            type="button"
            onClick={() => setValue("mode", m.value)}
            className={cn(
              "relative flex flex-col rounded-xl border p-4 text-left transition-colors",
              selectedMode === m.value
                ? "border-2 border-foreground"
                : "border-border hover:border-muted-foreground",
            )}
          >
            {m.badge && (
              <span className={cn("absolute -top-2 right-3 rounded-full px-2 py-0.5 text-[9px] font-semibold", m.badge.color)}>
                {m.badge.label}
              </span>
            )}
            <m.icon className="mb-2 h-5 w-5 text-muted-foreground" />
            <div className="text-[13px] font-medium">{m.title}</div>
            <div className="mt-1 text-[10px] text-muted-foreground">{m.subtitle}</div>
            <ul className="mt-3 space-y-1">
              {m.features.map((f) => (
                <li key={f} className="text-[10px] text-muted-foreground">• {f}</li>
              ))}
            </ul>
            <div className="mt-auto pt-3 text-[10px] text-muted-foreground">{m.stripeNeeded}</div>
          </button>
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Verify build**

Run: `pnpm build`

---

## Task 4: Stripe Key Step (Shared)

**Files:**
- Create: `src/features/onboarding/components/permissions-table.tsx`
- Create: `src/features/onboarding/components/stripe-key-step.tsx`

- [ ] **Step 1: Create permissions-table.tsx**

```typescript
// src/features/onboarding/components/permissions-table.tsx
import type { StripePermission } from "../api/types";
import { cn } from "@/lib/utils";

interface PermissionsTableProps {
  permissions: StripePermission[];
}

export function PermissionsTable({ permissions }: PermissionsTableProps) {
  return (
    <div className="rounded-lg border border-border">
      <table className="w-full text-[11px]">
        <thead>
          <tr className="border-b border-border">
            <th className="px-3 py-2 text-left font-medium text-muted-foreground">Resource</th>
            <th className="px-3 py-2 text-left font-medium text-muted-foreground">Permission</th>
          </tr>
        </thead>
        <tbody>
          {permissions.map((p) => (
            <tr key={p.resource} className="border-b border-border/50 last:border-0">
              <td className="px-3 py-1.5">{p.resource}</td>
              <td className="px-3 py-1.5">
                <span
                  className={cn(
                    "rounded-full px-2 py-0.5 text-[10px] font-medium",
                    p.access === "Read" && "bg-blue-50 text-blue-700 dark:bg-blue-900/20 dark:text-blue-400",
                    p.access === "Write" && "bg-purple-50 text-purple-700 dark:bg-purple-900/20 dark:text-purple-400",
                    p.access === "None" && "bg-muted text-muted-foreground",
                  )}
                >
                  {p.access}
                </span>
                {p.description && (
                  <span className="ml-2 text-[10px] text-muted-foreground">{p.description}</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

- [ ] **Step 2: Create stripe-key-step.tsx**

Stripe key input, validation button, permissions display, sync preview. Used by both revenue+costs and billing paths.

```typescript
// src/features/onboarding/components/stripe-key-step.tsx
import { useState } from "react";
import { useFormContext } from "react-hook-form";
import { CheckCircle, AlertCircle, Loader2 } from "lucide-react";
import type { OnboardingFormValues } from "../lib/schema";
import type { StripeSyncPreview, StripePermission } from "../api/types";
import { useValidateStripeKey } from "../api/queries";
import { PermissionsTable } from "./permissions-table";
import { readPermissions, billingPermissions } from "../api/mock-data";

export function StripeKeyStep() {
  const { watch, setValue } = useFormContext<OnboardingFormValues>();
  const mode = watch("mode");
  const stripeKey = watch("stripeKey") ?? "";
  const keyValidated = watch("keyValidated");
  const validateMutation = useValidateStripeKey();
  const [preview, setPreview] = useState<StripeSyncPreview | null>(null);
  const [validatedPermissions, setValidatedPermissions] = useState<StripePermission[]>([]);
  const [error, setError] = useState<string | null>(null);

  const isBilling = mode === "billing";
  const requiredPermissions = isBilling ? billingPermissions : readPermissions;

  const handleValidate = async () => {
    setError(null);
    const result = await validateMutation.mutateAsync({
      apiKey: stripeKey,
      mode: mode,
    });

    if (result.validation.valid) {
      setValue("keyValidated", true);
      setPreview(result.preview);
      setValidatedPermissions(result.validation.permissions);
    } else {
      setError(result.validation.error ?? "Key validation failed.");
      setValue("keyValidated", false);
    }
  };

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-[16px] font-semibold">Connect your Stripe account</h2>
        <p className="mt-1 text-[12px] text-muted-foreground">
          Create a restricted API key in your Stripe dashboard with these permissions:
        </p>
      </div>

      <PermissionsTable permissions={requiredPermissions} />

      {isBilling && (
        <div className="rounded-lg border border-purple-200 bg-purple-50 px-3 py-2 text-[11px] text-purple-700 dark:border-purple-800 dark:bg-purple-900/20 dark:text-purple-400">
          Billing mode requires one additional write permission: Customer balance transactions. This allows debiting customer balances — it cannot create charges, modify customer data, or access payment methods.
        </div>
      )}

      {/* Key input */}
      <div>
        <label className="mb-1 block text-[11px] font-medium">Restricted API key</label>
        <div className="flex gap-2">
          <input
            value={stripeKey}
            onChange={(e) => {
              setValue("stripeKey", e.target.value);
              if (keyValidated) {
                setValue("keyValidated", false);
                setPreview(null);
                setError(null);
              }
            }}
            placeholder="rk_live_..."
            className="flex-1 rounded-lg border border-border bg-background px-3 py-2 font-mono text-[12px] outline-none focus:border-muted-foreground"
          />
          <button
            type="button"
            onClick={handleValidate}
            disabled={!stripeKey || validateMutation.isPending}
            className="rounded-lg bg-foreground px-4 py-2 text-[12px] font-medium text-background hover:opacity-90 disabled:opacity-50"
          >
            {validateMutation.isPending ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              "Validate key"
            )}
          </button>
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 dark:border-red-800 dark:bg-red-900/20">
          <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-red-500" />
          <p className="text-[11px] text-red-700 dark:text-red-400">{error}</p>
        </div>
      )}

      {/* Success + preview */}
      {keyValidated && preview && (
        <div className="space-y-3">
          <div className="flex items-start gap-2 rounded-lg border border-green-200 bg-green-50 px-3 py-2 dark:border-green-800 dark:bg-green-900/20">
            <CheckCircle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-green-600" />
            <div className="text-[11px] text-green-700 dark:text-green-400">
              Key validated successfully. All required permissions confirmed.
            </div>
          </div>

          {validatedPermissions.length > 0 && (
            <PermissionsTable permissions={validatedPermissions} />
          )}

          <div className="grid grid-cols-3 gap-3 rounded-lg bg-accent/50 px-4 py-3">
            <div>
              <div className="text-[18px] font-semibold">{preview.customerCount}</div>
              <div className="text-[10px] text-muted-foreground">Customers</div>
            </div>
            <div>
              <div className="text-[18px] font-semibold">{preview.activeSubscriptions}</div>
              <div className="text-[10px] text-muted-foreground">Active subscriptions</div>
            </div>
            <div>
              <div className="text-[18px] font-semibold">${preview.revenue30d.toLocaleString()}</div>
              <div className="text-[10px] text-muted-foreground">Revenue (last 30d)</div>
            </div>
          </div>
        </div>
      )}

      <p className="text-[10px] text-muted-foreground">
        Your key is encrypted at rest and never stored in plain text.
      </p>
    </div>
  );
}
```

- [ ] **Step 3: Verify build**

Run: `pnpm build`

---

## Task 5: Customer Mapping Step (Shared)

**Files:**
- Create: `src/features/onboarding/components/match-results-table.tsx`
- Create: `src/features/onboarding/components/customer-mapping-step.tsx`

- [ ] **Step 1: Create match-results-table.tsx**

Customer mapping table with editable inputs for unmatched rows.

```typescript
// src/features/onboarding/components/match-results-table.tsx
import { cn } from "@/lib/utils";
import type { CustomerMatch } from "../api/types";

interface MatchResultsTableProps {
  customers: CustomerMatch[];
  onManualUpdate: (stripeId: string, identifier: string) => void;
}

export function MatchResultsTable({ customers, onManualUpdate }: MatchResultsTableProps) {
  return (
    <div className="rounded-lg border border-border">
      <table className="w-full text-[11px]">
        <thead>
          <tr className="border-b border-border">
            <th className="px-3 py-2 text-left font-medium text-muted-foreground">Stripe customer</th>
            <th className="px-3 py-2 text-left font-medium text-muted-foreground">Your identifier</th>
            <th className="px-3 py-2 text-right font-medium text-muted-foreground">Revenue (30d)</th>
            <th className="px-3 py-2 text-right font-medium text-muted-foreground">Status</th>
          </tr>
        </thead>
        <tbody>
          {customers.map((c) => (
            <tr
              key={c.stripeId}
              className={cn(
                "border-b border-border/50 last:border-0",
                c.status === "manual" && "bg-amber-50/50 dark:bg-amber-900/10",
              )}
            >
              <td className="px-3 py-2">
                <div className="font-medium">{c.name}</div>
                <div className="font-mono text-[10px] text-muted-foreground">{c.stripeId}</div>
              </td>
              <td className="px-3 py-2">
                {c.status === "matched" ? (
                  <span className="font-mono">{c.identifier}</span>
                ) : (
                  <input
                    defaultValue={c.identifier ?? ""}
                    onChange={(e) => onManualUpdate(c.stripeId, e.target.value)}
                    placeholder="Enter identifier..."
                    className="w-full rounded border border-amber-300 bg-background px-2 py-1 font-mono text-[11px] outline-none focus:border-muted-foreground dark:border-amber-700"
                  />
                )}
              </td>
              <td className="px-3 py-2 text-right font-mono">${c.revenue30d.toLocaleString()}</td>
              <td className="px-3 py-2 text-right">
                <span
                  className={cn(
                    "rounded-full px-2 py-0.5 text-[10px] font-medium",
                    c.status === "matched"
                      ? "bg-green-50 text-green-700 dark:bg-green-900/20 dark:text-green-400"
                      : "bg-amber-50 text-amber-700 dark:bg-amber-900/20 dark:text-amber-400",
                  )}
                >
                  {c.status === "matched" ? "Matched" : "Manual"}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

- [ ] **Step 2: Create customer-mapping-step.tsx**

Identifier mode picker (4 options) + match button + results table.

```typescript
// src/features/onboarding/components/customer-mapping-step.tsx
import { useState } from "react";
import { useFormContext } from "react-hook-form";
import { Loader2, CheckCircle } from "lucide-react";
import type { OnboardingFormValues } from "../lib/schema";
import type { IdentifierMode, MatchResult } from "../api/types";
import { useMatchCustomers } from "../api/queries";
import { MatchResultsTable } from "./match-results-table";
import { cn } from "@/lib/utils";

const identifierModes: { value: IdentifierMode; title: string; subtitle: string; example: string }[] = [
  { value: "stripe_id", title: "Stripe customer ID", subtitle: "I already use cus_xxxxx in my code", example: "cus_R4kB9xPm2nQ" },
  { value: "email", title: "Email address", subtitle: "Identify users by email", example: "user@company.com" },
  { value: "internal_id", title: "Internal ID or slug", subtitle: "Your own identifier", example: "acme_corp, org_4521" },
  { value: "metadata", title: "Stripe metadata field", subtitle: "Stored in customer metadata", example: "metadata.platform_id" },
];

export function CustomerMappingStep() {
  const { watch, setValue } = useFormContext<OnboardingFormValues>();
  const identifierMode = watch("identifierMode");
  const metadataKey = watch("metadataKey") ?? "";
  const matchMutation = useMatchCustomers();
  const [matchResult, setMatchResult] = useState<MatchResult | null>(null);

  const canMatch = identifierMode && (identifierMode !== "metadata" || metadataKey.length > 0);

  const handleMatch = async () => {
    if (!identifierMode) return;
    const result = await matchMutation.mutateAsync({
      identifierMode,
      metadataKey: identifierMode === "metadata" ? metadataKey : undefined,
    });
    setMatchResult(result);

    if (result.needsManual === 0) {
      setValue("mappingComplete", true);
    }
  };

  const handleManualUpdate = (stripeId: string, identifier: string) => {
    if (!matchResult) return;
    const updated = matchResult.customers.map((c) =>
      c.stripeId === stripeId ? { ...c, identifier, status: identifier ? "matched" as const : "manual" as const } : c,
    );
    const newResult = {
      ...matchResult,
      customers: updated,
      matched: updated.filter((c) => c.status === "matched").length,
      needsManual: updated.filter((c) => c.status !== "matched").length,
    };
    setMatchResult(newResult);

    if (newResult.needsManual === 0) {
      setValue("mappingComplete", true);
    }
  };

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-[16px] font-semibold">How do you identify your customers?</h2>
        <p className="mt-1 text-[12px] text-muted-foreground">
          Your SDK will send a customer identifier with each API event. Tell us how you identify customers so we can match them to Stripe.
        </p>
      </div>

      {/* Identifier mode grid */}
      <div className="grid grid-cols-2 gap-2.5">
        {identifierModes.map((m) => (
          <button
            key={m.value}
            type="button"
            onClick={() => {
              setValue("identifierMode", m.value);
              setMatchResult(null);
              setValue("mappingComplete", false);
            }}
            className={cn(
              "rounded-xl border px-3.5 py-3 text-left transition-colors",
              identifierMode === m.value
                ? "border-2 border-foreground"
                : "border-border hover:border-muted-foreground hover:bg-accent",
            )}
          >
            <div className="text-[12px] font-medium">{m.title}</div>
            <div className="text-[10px] text-muted-foreground">{m.subtitle}</div>
            <div className="mt-1 font-mono text-[10px] text-muted-foreground">{m.example}</div>
          </button>
        ))}
      </div>

      {/* Metadata key input */}
      {identifierMode === "metadata" && (
        <div>
          <label className="mb-1 block text-[11px] font-medium">Which metadata key do you use?</label>
          <input
            value={metadataKey}
            onChange={(e) => setValue("metadataKey", e.target.value)}
            placeholder="e.g. platform_id"
            className="w-full rounded-lg border border-border bg-background px-3 py-2 font-mono text-[12px] outline-none focus:border-muted-foreground"
          />
          <p className="mt-0.5 text-[10px] text-muted-foreground">
            We'll look in each customer's metadata object for this key.
          </p>
        </div>
      )}

      {/* Match button */}
      {identifierMode && !matchResult && (
        <button
          type="button"
          onClick={handleMatch}
          disabled={!canMatch || matchMutation.isPending}
          className="w-full rounded-lg bg-foreground px-4 py-2.5 text-[12px] font-medium text-background hover:opacity-90 disabled:opacity-50"
        >
          {matchMutation.isPending ? (
            <span className="flex items-center justify-center gap-2">
              <Loader2 className="h-3.5 w-3.5 animate-spin" /> Matching customers...
            </span>
          ) : (
            "Match my Stripe customers"
          )}
        </button>
      )}

      {/* Match results */}
      {matchResult && (
        <div className="space-y-3">
          <div className="flex items-center gap-2">
            <span className="text-[12px] font-medium">
              {matchResult.matched} of {matchResult.total} matched
            </span>
            {matchResult.needsManual === 0 ? (
              <span className="rounded-full bg-green-50 px-2 py-0.5 text-[10px] font-medium text-green-700 dark:bg-green-900/20 dark:text-green-400">
                All matched
              </span>
            ) : (
              <span className="rounded-full bg-amber-50 px-2 py-0.5 text-[10px] font-medium text-amber-700 dark:bg-amber-900/20 dark:text-amber-400">
                {matchResult.needsManual} need input
              </span>
            )}
          </div>

          <MatchResultsTable
            customers={matchResult.customers}
            onManualUpdate={handleManualUpdate}
          />

          {matchResult.needsManual === 0 && (
            <div className="flex items-center gap-2 rounded-lg border border-green-200 bg-green-50 px-3 py-2 dark:border-green-800 dark:bg-green-900/20">
              <CheckCircle className="h-3.5 w-3.5 text-green-600" />
              <span className="text-[11px] text-green-700 dark:text-green-400">Customer mapping complete</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 3: Verify build**

Run: `pnpm build`

---

## Task 6: Margin Config Step (Billing Only)

**Files:**
- Create: `src/features/onboarding/components/margin-config-step.tsx`

- [ ] **Step 1: Create margin-config-step.tsx**

Default margin slider + live billing preview + alert configuration. Only shown in billing path.

```typescript
// src/features/onboarding/components/margin-config-step.tsx
import { useState } from "react";
import { useFormContext } from "react-hook-form";
import type { OnboardingFormValues } from "../lib/schema";

export function MarginConfigStep() {
  const { watch, setValue } = useFormContext<OnboardingFormValues>();
  const defaultMargin = watch("defaultMargin");
  const notifyAt = watch("notifyAt");
  const remindAt = watch("remindAt");
  const pauseAtZero = watch("pauseAtZero");
  const [exampleCost, setExampleCost] = useState(2.0);

  const chargeAmount = exampleCost * (1 + defaultMargin / 100);
  const profit = chargeAmount - exampleCost;

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-[16px] font-semibold">Configure billing</h2>
        <p className="mt-1 text-[12px] text-muted-foreground">
          Set a default margin percentage that applies to all API costs. You can override per product or per pricing card later.
        </p>
      </div>

      {/* Margin slider */}
      <div>
        <div className="mb-2 flex items-center justify-between">
          <label className="text-[11px] font-medium">Default margin</label>
          <span className="text-[14px] font-semibold">{defaultMargin}%</span>
        </div>
        <input
          type="range"
          min={0}
          max={200}
          step={5}
          value={defaultMargin}
          onChange={(e) => setValue("defaultMargin", Number(e.target.value))}
          className="w-full accent-foreground"
        />
        <p className="mt-1 text-[10px] text-muted-foreground">
          {defaultMargin}% margin means ${exampleCost.toFixed(2)} API cost becomes ${chargeAmount.toFixed(2)} charged to your customer.
        </p>
      </div>

      {/* Billing preview */}
      <div className="rounded-xl bg-accent/50 px-4 py-4">
        <div className="mb-3 text-[11px] font-medium">Billing preview</div>

        <div className="mb-3">
          <label className="mb-1 block text-[10px] text-muted-foreground">Try different API cost</label>
          <input
            type="range"
            min={0.1}
            max={5}
            step={0.1}
            value={exampleCost}
            onChange={(e) => setExampleCost(Number(e.target.value))}
            className="w-full accent-foreground"
          />
        </div>

        <div className="grid grid-cols-3 gap-2 text-center">
          <div className="rounded-lg bg-background px-3 py-3">
            <div className="text-[18px] font-semibold">${exampleCost.toFixed(2)}</div>
            <div className="text-[10px] text-muted-foreground">API cost</div>
          </div>
          <div className="rounded-lg bg-background px-3 py-3">
            <div className="text-[18px] font-semibold">+${profit.toFixed(2)}</div>
            <div className="text-[10px] text-muted-foreground">Your margin ({defaultMargin}%)</div>
          </div>
          <div className="rounded-lg bg-background px-3 py-3">
            <div className="text-[18px] font-semibold">${chargeAmount.toFixed(2)}</div>
            <div className="text-[10px] text-muted-foreground">Customer charged</div>
          </div>
        </div>
      </div>

      {/* Balance alerts */}
      <div className="space-y-2.5">
        <div className="text-[11px] font-medium">Balance alerts</div>

        <label className="flex items-center gap-3 rounded-lg border border-border px-3 py-2">
          <input
            type="checkbox"
            checked={notifyAt > 0}
            onChange={(e) => setValue("notifyAt", e.target.checked ? 50 : 0)}
            className="accent-foreground"
          />
          <div>
            <div className="text-[12px]">Notify me when balance drops below ${notifyAt}</div>
            <div className="text-[10px] text-muted-foreground">Get an email when a customer's balance is low</div>
          </div>
        </label>

        <label className="flex items-center gap-3 rounded-lg border border-border px-3 py-2">
          <input
            type="checkbox"
            checked={remindAt > 0}
            onChange={(e) => setValue("remindAt", e.target.checked ? 25 : 0)}
            className="accent-foreground"
          />
          <div>
            <div className="text-[12px]">Send customer top-up reminder at ${remindAt}</div>
            <div className="text-[10px] text-muted-foreground">Email your customer when their balance is critically low</div>
          </div>
        </label>

        <label className="flex items-center gap-3 rounded-lg border border-border px-3 py-2">
          <input
            type="checkbox"
            checked={pauseAtZero}
            onChange={(e) => setValue("pauseAtZero", e.target.checked)}
            className="accent-foreground"
          />
          <div>
            <div className="text-[12px]">Auto-pause billing at $0 balance</div>
            <div className="text-[10px] text-muted-foreground">Stop debiting when a customer's balance runs out</div>
          </div>
        </label>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Verify build**

Run: `pnpm build`

---

## Task 7: Review Step + Activation Success

**Files:**
- Create: `src/features/onboarding/components/activation-success.tsx`
- Create: `src/features/onboarding/components/review-step.tsx`

- [ ] **Step 1: Create activation-success.tsx**

```typescript
// src/features/onboarding/components/activation-success.tsx
import { CheckCircle } from "lucide-react";
import { Link } from "@tanstack/react-router";
import { useFormContext } from "react-hook-form";
import type { OnboardingFormValues } from "../lib/schema";

export function ActivationSuccess() {
  const { watch } = useFormContext<OnboardingFormValues>();
  const mode = watch("mode");

  const title = mode === "track"
    ? "You're all set"
    : mode === "revenue"
      ? "Stripe integration is live"
      : "Billing integration is live";

  const subtitle = mode === "track"
    ? "Create your first pricing card to start tracking costs."
    : "Revenue data is syncing now. Historical backfill will complete within the hour.";

  return (
    <div className="space-y-5 text-center">
      <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-green-100 dark:bg-green-900/30">
        <CheckCircle className="h-6 w-6 text-green-600" />
      </div>
      <h2 className="text-[16px] font-semibold">{title}</h2>
      <p className="text-[12px] text-muted-foreground">{subtitle}</p>

      <div className="rounded-xl border border-border px-4 py-3.5 text-left">
        <div className="mb-2 text-[12px] font-medium">What happens next</div>
        <ol className="space-y-2">
          <li className="flex items-start gap-2.5">
            <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-blue-50 text-[10px] font-semibold text-blue-700 dark:bg-blue-900/20 dark:text-blue-400">1</span>
            <span className="text-[11px] text-muted-foreground">Create your first pricing card — pick a template, verify prices, activate.</span>
          </li>
          <li className="flex items-start gap-2.5">
            <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-blue-50 text-[10px] font-semibold text-blue-700 dark:bg-blue-900/20 dark:text-blue-400">2</span>
            <span className="text-[11px] text-muted-foreground">Paste the SDK code into your app wherever you make API calls.</span>
          </li>
          <li className="flex items-start gap-2.5">
            <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-blue-50 text-[10px] font-semibold text-blue-700 dark:bg-blue-900/20 dark:text-blue-400">3</span>
            <span className="text-[11px] text-muted-foreground">Deploy — your dashboard shows live data within minutes.</span>
          </li>
        </ol>
      </div>

      <div className="flex justify-center gap-3">
        <Link
          to="/"
          className="rounded-lg border border-border px-4 py-2 text-[12px] text-muted-foreground hover:bg-accent"
        >
          Go to dashboard
        </Link>
        <Link
          to="/pricing-cards/new"
          className="rounded-lg bg-foreground px-4 py-2 text-[12px] font-medium text-background hover:opacity-90"
        >
          Create my first pricing card
        </Link>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Create review-step.tsx**

Review cards showing configured settings + activate button.

```typescript
// src/features/onboarding/components/review-step.tsx
import { useFormContext } from "react-hook-form";
import { Check, Loader2 } from "lucide-react";
import type { OnboardingFormValues } from "../lib/schema";
import { useActivateOnboarding } from "../api/queries";

interface ReviewStepProps {
  onActivated: () => void;
}

export function ReviewStep({ onActivated }: ReviewStepProps) {
  const { watch, getValues } = useFormContext<OnboardingFormValues>();
  const mode = watch("mode");
  const activateMutation = useActivateOnboarding();

  const handleActivate = async () => {
    const values = getValues();
    await activateMutation.mutateAsync({
      mode: values.mode,
      stripeKey: values.stripeKey,
      identifierMode: values.identifierMode,
      metadataKey: values.metadataKey,
      defaultMargin: mode === "billing" ? values.defaultMargin : undefined,
      alertThresholds: mode === "billing" ? {
        notifyAt: values.notifyAt,
        remindAt: values.remindAt,
        pauseAtZero: values.pauseAtZero,
      } : undefined,
    });
    onActivated();
  };

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-[16px] font-semibold">Review and activate</h2>
        <p className="mt-1 text-[12px] text-muted-foreground">
          Everything looks good. Review your setup and activate when ready.
        </p>
      </div>

      {/* Stripe connection */}
      <ReviewCard
        title="Stripe connection"
        items={[
          { label: "API key", value: maskKey(watch("stripeKey") ?? "") },
          { label: "Permissions", value: mode === "billing" ? "Read + write (balance transactions)" : "Read-only" },
        ]}
      />

      {/* Customer mapping */}
      <ReviewCard
        title="Customer mapping"
        items={[
          { label: "Identifier mode", value: formatIdentifierMode(watch("identifierMode")) },
          { label: "Status", value: watch("mappingComplete") ? "All customers mapped" : "Mapping incomplete" },
        ]}
      />

      {/* Billing config (billing only) */}
      {mode === "billing" && (
        <ReviewCard
          title="Billing configuration"
          items={[
            { label: "Default margin", value: `${watch("defaultMargin")}%` },
            { label: "Effective multiplier", value: `${(1 + watch("defaultMargin") / 100).toFixed(2)}x` },
            { label: "Low balance alert", value: watch("notifyAt") > 0 ? `At $${watch("notifyAt")}` : "Off" },
            { label: "Customer reminder", value: watch("remindAt") > 0 ? `At $${watch("remindAt")}` : "Off" },
            { label: "Auto-pause at $0", value: watch("pauseAtZero") ? "On" : "Off" },
          ]}
        />
      )}

      {/* Sync settings */}
      <ReviewCard
        title="Data sync"
        items={[
          { label: "Sync frequency", value: "Every 6 hours" },
          { label: "Historical backfill", value: "Last 12 months of invoice data" },
          { label: "New customers", value: "Auto-detected on each sync" },
        ]}
      />

      {/* Checklist */}
      <div className="space-y-1.5">
        <CheckItem label="Stripe key validated with correct permissions" />
        <CheckItem label="All customers matched to SDK identifiers" />
        {mode === "billing" && <CheckItem label="Default margin configured" />}
      </div>

      <button
        type="button"
        onClick={handleActivate}
        disabled={activateMutation.isPending}
        className="w-full rounded-lg bg-foreground px-4 py-2.5 text-[12px] font-medium text-background hover:opacity-90 disabled:opacity-50"
      >
        {activateMutation.isPending ? (
          <span className="flex items-center justify-center gap-2">
            <Loader2 className="h-3.5 w-3.5 animate-spin" /> Activating...
          </span>
        ) : (
          "Activate Stripe integration"
        )}
      </button>
    </div>
  );
}

function ReviewCard({ title, items }: { title: string; items: { label: string; value: string }[] }) {
  return (
    <div className="rounded-xl border border-border px-4 py-3">
      <div className="mb-2 flex items-center gap-2">
        <div className="flex h-4 w-4 items-center justify-center rounded-full bg-green-100 dark:bg-green-900/30">
          <Check className="h-2.5 w-2.5 text-green-600" />
        </div>
        <span className="text-[12px] font-medium">{title}</span>
      </div>
      <div className="space-y-1">
        {items.map((item) => (
          <div key={item.label} className="flex justify-between text-[11px]">
            <span className="text-muted-foreground">{item.label}</span>
            <span className="font-mono">{item.value}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function CheckItem({ label }: { label: string }) {
  return (
    <div className="flex items-center gap-2">
      <div className="flex h-4 w-4 items-center justify-center rounded-full bg-green-100 dark:bg-green-900/30">
        <Check className="h-2.5 w-2.5 text-green-600" />
      </div>
      <span className="text-[11px]">{label}</span>
    </div>
  );
}

function maskKey(key: string): string {
  if (key.length < 10) return key;
  return key.slice(0, 8) + "..." + key.slice(-4);
}

function formatIdentifierMode(mode?: string): string {
  switch (mode) {
    case "stripe_id": return "Stripe customer ID";
    case "email": return "Email address";
    case "internal_id": return "Internal ID / slug";
    case "metadata": return "Stripe metadata field";
    default: return "Not selected";
  }
}
```

- [ ] **Step 3: Verify build**

Run: `pnpm build`

---

## Task 8: Onboarding Wizard (Main Container)

**Files:**
- Modify: `src/features/onboarding/components/onboarding-wizard.tsx` (replace placeholder)

- [ ] **Step 1: Replace onboarding-wizard.tsx**

The main wizard container that manages step state and renders path-appropriate components.

```typescript
// src/features/onboarding/components/onboarding-wizard.tsx
import { useState, useCallback } from "react";
import { useForm, FormProvider } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useNavigate } from "@tanstack/react-router";
import { onboardingSchema, type OnboardingFormValues } from "../lib/schema";
import { OnboardingProgress } from "./onboarding-progress";
import { ModeSelector } from "./mode-selector";
import { StripeKeyStep } from "./stripe-key-step";
import { CustomerMappingStep } from "./customer-mapping-step";
import { MarginConfigStep } from "./margin-config-step";
import { ReviewStep } from "./review-step";
import { ActivationSuccess } from "./activation-success";
import { useAuthStore } from "@/stores/auth-store";

const defaultValues: OnboardingFormValues = {
  mode: "revenue",
  stripeKey: "",
  keyValidated: false,
  identifierMode: undefined,
  metadataKey: "",
  mappingComplete: false,
  defaultMargin: 50,
  notifyAt: 50,
  remindAt: 25,
  pauseAtZero: false,
};

function getSteps(mode: OnboardingFormValues["mode"]): string[] {
  switch (mode) {
    case "track":
      return ["Choose mode"];
    case "revenue":
      return ["Choose mode", "Connect Stripe", "Map customers", "Review"];
    case "billing":
      return ["Choose mode", "Connect Stripe", "Map customers", "Configure billing", "Review"];
  }
}

export function OnboardingWizard() {
  const [step, setStep] = useState(0);
  const [activated, setActivated] = useState(false);
  const navigate = useNavigate();

  const form = useForm<OnboardingFormValues>({
    resolver: zodResolver(onboardingSchema),
    defaultValues,
    mode: "onChange",
  });

  const mode = form.watch("mode");
  const steps = getSteps(mode);

  const next = useCallback(() => {
    if (step === 0 && mode === "track") {
      // Track costs: update tenant mode and go to pricing cards
      useAuthStore.getState().setTenant(
        useAuthStore.getState().activeTenantId ?? "tenant-001",
        "track",
      );
      navigate({ to: "/pricing-cards/new" });
      return;
    }
    setStep((s) => Math.min(s + 1, steps.length - 1));
  }, [step, mode, steps.length, navigate]);

  const prev = useCallback(() => {
    setStep((s) => Math.max(s - 1, 0));
  }, []);

  const handleActivated = useCallback(() => {
    const tenantMode = mode === "billing" ? "billing" : "revenue";
    useAuthStore.getState().setTenant(
      useAuthStore.getState().activeTenantId ?? "tenant-001",
      tenantMode,
    );
    setActivated(true);
  }, [mode]);

  // Determine which component to render for current step
  const renderStep = () => {
    if (activated) return <ActivationSuccess />;

    if (step === 0) return <ModeSelector />;

    // Steps 1+ depend on path
    const stepsAfterMode = step - 1;

    if (mode === "revenue") {
      switch (stepsAfterMode) {
        case 0: return <StripeKeyStep />;
        case 1: return <CustomerMappingStep />;
        case 2: return <ReviewStep onActivated={handleActivated} />;
      }
    }

    if (mode === "billing") {
      switch (stepsAfterMode) {
        case 0: return <StripeKeyStep />;
        case 1: return <CustomerMappingStep />;
        case 2: return <MarginConfigStep />;
        case 3: return <ReviewStep onActivated={handleActivated} />;
      }
    }

    return null;
  };

  // Can advance?
  const canAdvance = () => {
    if (step === 0) return true; // mode is always selected (default: revenue)

    const stepsAfterMode = step - 1;

    if (mode === "revenue" || mode === "billing") {
      if (stepsAfterMode === 0) return form.getValues("keyValidated");
      if (stepsAfterMode === 1) return form.getValues("mappingComplete");
    }

    return true;
  };

  // Is current step the review step? (don't show Next on review)
  const isReviewStep = step === steps.length - 1 && step > 0;

  return (
    <div>
      {!activated && <OnboardingProgress steps={steps} currentStep={step} />}

      <FormProvider {...form}>
        {renderStep()}
      </FormProvider>

      {/* Navigation */}
      {!activated && !isReviewStep && (
        <div className="mt-6 flex justify-between">
          {step > 0 ? (
            <button
              type="button"
              onClick={prev}
              className="rounded-lg border border-border px-4 py-2 text-[12px] text-muted-foreground hover:bg-accent"
            >
              Back
            </button>
          ) : (
            <div />
          )}
          <button
            type="button"
            onClick={next}
            disabled={!canAdvance()}
            className="rounded-lg bg-foreground px-5 py-2 text-[12px] font-medium text-background hover:opacity-90 disabled:opacity-50"
          >
            {step === 0 && mode === "track" ? "Continue to pricing cards" : "Continue"}
          </button>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Verify build**

Run: `pnpm build`

---

## Task 9: Final Verification + PROGRESS.md

- [ ] **Step 1: Full verification**

```bash
pnpm test
pnpm lint
pnpm build
```

All must pass.

- [ ] **Step 2: Manual verification in browser**

Navigate to `/onboarding` and verify:
- Mode selector shows 3 paths
- "Track costs" → Continue redirects to `/pricing-cards/new`
- "Revenue + costs" → 4 steps: mode → Stripe key → customer mapping → review/activate
- "Billing" → 5 steps: mode → Stripe key → customer mapping → margin config → review/activate
- Stripe key validation (enter `rk_test_anything` for success, anything else for error)
- Customer mapping with 4 identifier modes, match results table, manual input
- Margin slider + billing preview (billing only)
- Review cards + activation → success view with next steps

- [ ] **Step 3: Update PROGRESS.md**

Mark Phase 4 complete. Update current status to Phase 5.

```markdown
## Phase 4: Onboarding (Complete)

- [x] Onboarding layout (full-page, no sidebar)
- [x] Mode selector (track costs / revenue+costs / billing)
- [x] Path A: Track costs → redirect to pricing cards
- [x] Stripe key step (shared): key input, validation, permissions table, sync preview
- [x] Customer mapping step (shared): 4 identifier modes, match results, manual input
- [x] Margin config step (billing only): slider, billing preview, balance alerts
- [x] Review step: review cards, activation
- [x] Activation success: next steps + navigation
- [x] Feature API layer (types, mock data, mutations)
- [x] Onboarding route (outside _app layout)
```
