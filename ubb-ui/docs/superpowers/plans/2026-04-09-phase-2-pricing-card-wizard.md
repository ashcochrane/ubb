# Phase 2: Pricing Card Wizard — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **IMPORTANT:** Do NOT commit. The user handles all git operations. Suggest commit messages when work is ready.
>
> **Design source of truth:** HTML mockups in `docs/design/files/`. Read the relevant mockup before implementing each step.
> **Design rationale:** `docs/design/ui-flow-design-rationale.md` section 2 ("Creating a pricing card").

**Goal:** Build the pricing card list page and 4-step creation wizard matching the HTML mockups, with feature-co-located API layer using the provider pattern.

**Architecture:** Feature module at `src/features/pricing-cards/` with co-located components and API layer. Wizard uses a single React Hook Form instance shared across all 4 steps. Provider pattern selects between mock data and real API. All calculations (cost tester, dry-run) are pure functions in a shared utils file.

**Tech Stack:** React 19, TypeScript, React Hook Form + Zod, TanStack Query, TanStack Router, Recharts (cost distribution bar not needed — use pure CSS), Lucide icons, shadcn/ui components

---

## File Map

### API Layer

| File | Responsibility |
|------|---------------|
| `src/features/pricing-cards/api/types.ts` | Backend-agnostic TypeScript interfaces |
| `src/features/pricing-cards/api/mock-data.ts` | Mock pricing cards, templates |
| `src/features/pricing-cards/api/mock.ts` | Mock adapter (returns fake data with delay) |
| `src/features/pricing-cards/api/api.ts` | Real API adapter (openapi-fetch) |
| `src/features/pricing-cards/api/provider.ts` | selectProvider({ mock, api }) |
| `src/features/pricing-cards/api/queries.ts` | TanStack Query hooks |

### Components

| File | Responsibility |
|------|---------------|
| `src/features/pricing-cards/components/pricing-cards-page.tsx` | Card list page with grid + search |
| `src/features/pricing-cards/components/pricing-card-item.tsx` | Single card in the list |
| `src/features/pricing-cards/components/new-card-wizard.tsx` | Wizard container, form setup, step navigation |
| `src/features/pricing-cards/components/step-source.tsx` | Step 1: Template vs custom selection |
| `src/features/pricing-cards/components/step-details.tsx` | Step 2: Name, provider, pattern, preview |
| `src/features/pricing-cards/components/step-dimensions.tsx` | Step 3: Dimension config + cost tester |
| `src/features/pricing-cards/components/step-review.tsx` | Step 4: Dry-run, product assignment, activation |
| `src/features/pricing-cards/components/dimension-card.tsx` | Single collapsible dimension editor |
| `src/features/pricing-cards/components/cost-tester.tsx` | Live cost calculation widget |
| `src/features/pricing-cards/components/dry-run-simulator.tsx` | Dry-run with breakdown + distribution bar |
| `src/features/pricing-cards/components/card-preview.tsx` | Live preview widget for step 2 |
| `src/features/pricing-cards/components/integration-snippet.tsx` | Copyable SDK code block |
| `src/features/pricing-cards/components/wizard-stepper.tsx` | 4-step progress indicator |

### Utilities

| File | Responsibility |
|------|---------------|
| `src/features/pricing-cards/lib/calculations.ts` | Pure cost calculation functions |
| `src/features/pricing-cards/lib/calculations.test.ts` | Tests for calculations |
| `src/features/pricing-cards/lib/slugify.ts` | Card ID generation from name |
| `src/features/pricing-cards/lib/slugify.test.ts` | Tests for slugify |
| `src/features/pricing-cards/lib/schema.ts` | Zod schema for wizard form |

### Routes

| File | Responsibility |
|------|---------------|
| `src/app/routes/_app/pricing-cards/index.tsx` | Card list route (modify existing stub) |
| `src/app/routes/_app/pricing-cards/new.tsx` | Wizard route |

### shadcn Components Needed

| Component | Used for |
|-----------|---------|
| `card` | Pricing card items, dimension cards |
| `input` | All form fields |
| `label` | Form labels |
| `select` | Provider dropdown |
| `textarea` | Description field |
| `badge` | Draft/active status, pricing type |
| `dialog` | Activation confirmation |
| `tabs` | Could use for pricing type toggle, but plan uses custom toggle |

---

## Task 1: Types + Schema + Utilities

**Files:**
- Create: `src/features/pricing-cards/api/types.ts`
- Create: `src/features/pricing-cards/lib/schema.ts`
- Create: `src/features/pricing-cards/lib/slugify.ts`
- Create: `src/features/pricing-cards/lib/slugify.test.ts`
- Create: `src/features/pricing-cards/lib/calculations.ts`
- Create: `src/features/pricing-cards/lib/calculations.test.ts`

- [ ] **Step 1: Create types.ts**

```typescript
// src/features/pricing-cards/api/types.ts

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

export interface WizardFormValues {
  sourceType: SourceType;
  templateId?: string;
  name: string;
  provider: string;
  providerCustom?: string;
  cardId: string;
  pricingPattern: PricingPattern;
  description?: string;
  pricingSourceUrl?: string;
  dimensions: Dimension[];
  product?: string;
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
```

- [ ] **Step 2: Create slugify.ts**

```typescript
// src/features/pricing-cards/lib/slugify.ts

/** Convert a string to a valid card ID slug: lowercase, underscores, max 40 chars. */
export function slugify(input: string): string {
  return input
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_|_$/g, "")
    .slice(0, 40);
}

/** Regenerate a slug with a random 3-digit suffix. */
export function slugifyWithSuffix(input: string): string {
  const base = slugify(input).slice(0, 36);
  const suffix = Math.floor(100 + Math.random() * 900);
  return `${base}_${suffix}`;
}
```

- [ ] **Step 3: Write slugify tests**

```typescript
// src/features/pricing-cards/lib/slugify.test.ts
import { describe, expect, it } from "vitest";
import { slugify, slugifyWithSuffix } from "./slugify";

describe("slugify", () => {
  it("converts spaces and special chars to underscores", () => {
    expect(slugify("Gemini 2.0 Flash")).toBe("gemini_2_0_flash");
  });

  it("lowercases the input", () => {
    expect(slugify("GPT-4o")).toBe("gpt_4o");
  });

  it("strips leading and trailing underscores", () => {
    expect(slugify("  hello world  ")).toBe("hello_world");
  });

  it("truncates to 40 characters", () => {
    const long = "a".repeat(50);
    expect(slugify(long).length).toBe(40);
  });

  it("handles empty string", () => {
    expect(slugify("")).toBe("");
  });
});

describe("slugifyWithSuffix", () => {
  it("appends a 3-digit suffix", () => {
    const result = slugifyWithSuffix("Gemini Flash");
    expect(result).toMatch(/^gemini_flash_\d{3}$/);
  });

  it("base is truncated to 36 chars to leave room for suffix", () => {
    const long = "a".repeat(50);
    const result = slugifyWithSuffix(long);
    expect(result.length).toBeLessThanOrEqual(40);
  });
});
```

- [ ] **Step 4: Run slugify tests**

Run: `pnpm test -- src/features/pricing-cards/lib/slugify.test.ts`
Expected: All tests pass.

- [ ] **Step 5: Create calculations.ts**

```typescript
// src/features/pricing-cards/lib/calculations.ts
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

/**
 * Calculate costs for a set of dimensions given quantities.
 * Per-unit: cost = quantity * price
 * Flat: cost = price (if quantity > 0, else 0)
 */
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

/**
 * Calculate cost distribution percentages.
 * Returns array of { key, label, percentage } sorted by percentage desc.
 */
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

/**
 * Project costs over time periods.
 */
export function projectCosts(
  costPerEvent: number,
  eventsPerDay: number,
): { daily: number; monthly: number } {
  return {
    daily: costPerEvent * eventsPerDay,
    monthly: costPerEvent * eventsPerDay * 30,
  };
}
```

- [ ] **Step 6: Write calculation tests**

```typescript
// src/features/pricing-cards/lib/calculations.test.ts
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
```

- [ ] **Step 7: Run calculation tests**

Run: `pnpm test -- src/features/pricing-cards/lib/calculations.test.ts`
Expected: All tests pass.

- [ ] **Step 8: Create Zod schema**

```typescript
// src/features/pricing-cards/lib/schema.ts
import { z } from "zod";

export const dimensionSchema = z.object({
  key: z.string().min(1, "Required").max(60),
  type: z.enum(["per_unit", "flat"]),
  price: z.number().min(0, "Must be non-negative"),
  label: z.string().min(1, "Required").max(100),
  unit: z.string().max(50).default(""),
  displayPrice: z.string().optional(),
});

export const wizardSchema = z.object({
  sourceType: z.enum(["template", "custom"]),
  templateId: z.string().optional(),
  name: z.string().min(1, "Card name is required").max(250),
  provider: z.string().min(1, "Provider is required"),
  providerCustom: z.string().optional(),
  cardId: z.string().min(1, "Card ID is required").max(40),
  pricingPattern: z.enum(["token", "request", "mixed"]),
  description: z.string().max(250).optional(),
  pricingSourceUrl: z.string().url().optional().or(z.literal("")),
  dimensions: z.array(dimensionSchema).min(1, "At least one dimension required"),
  product: z.string().optional(),
});

export type WizardFormValues = z.infer<typeof wizardSchema>;
```

- [ ] **Step 9: Verify all tests pass**

Run: `pnpm test`
Expected: All tests pass (format tests + slugify + calculations).

---

## Task 2: Mock Data + API Layer

**Files:**
- Create: `src/features/pricing-cards/api/mock-data.ts`
- Create: `src/features/pricing-cards/api/mock.ts`
- Create: `src/features/pricing-cards/api/api.ts`
- Create: `src/features/pricing-cards/api/provider.ts`
- Create: `src/features/pricing-cards/api/queries.ts`

- [ ] **Step 1: Create mock-data.ts**

```typescript
// src/features/pricing-cards/api/mock-data.ts
import type { PricingCard, Template } from "./types";

export const mockTemplates: Template[] = [
  {
    id: "gem",
    name: "Gemini 2.0 Flash",
    provider: "Google",
    dimensionCount: 3,
    pricingPattern: "token",
    dimensions: [
      { key: "input_tokens", type: "per_unit", price: 0.0000001, label: "Input tokens", unit: "per 1M tokens" },
      { key: "output_tokens", type: "per_unit", price: 0.0000004, label: "Output tokens", unit: "per 1M tokens" },
      { key: "grounding_requests", type: "flat", price: 0.035, label: "Grounding requests", unit: "per request" },
    ],
    description: "Google Gemini 2.0 Flash with grounding",
  },
  {
    id: "gpt",
    name: "GPT-4o",
    provider: "OpenAI",
    dimensionCount: 2,
    pricingPattern: "token",
    dimensions: [
      { key: "input_tokens", type: "per_unit", price: 0.0000025, label: "Input tokens", unit: "per 1M tokens" },
      { key: "output_tokens", type: "per_unit", price: 0.00001, label: "Output tokens", unit: "per 1M tokens" },
    ],
    description: "OpenAI GPT-4o",
  },
  {
    id: "claude",
    name: "Claude Sonnet",
    provider: "Anthropic",
    dimensionCount: 2,
    pricingPattern: "token",
    dimensions: [
      { key: "input_tokens", type: "per_unit", price: 0.000003, label: "Input tokens", unit: "per 1M tokens" },
      { key: "output_tokens", type: "per_unit", price: 0.000015, label: "Output tokens", unit: "per 1M tokens" },
    ],
    description: "Anthropic Claude Sonnet",
  },
];

export const mockPricingCards: PricingCard[] = [
  {
    id: "pc-001",
    cardId: "gemini_2_flash",
    name: "Gemini 2.0 Flash",
    provider: "Google",
    pricingPattern: "token",
    status: "active",
    dimensions: mockTemplates[0].dimensions,
    description: "Google Gemini 2.0 Flash with grounding requests",
    product: "property_search",
    version: 1,
    createdAt: "2026-03-01T10:00:00Z",
    updatedAt: "2026-03-01T10:00:00Z",
  },
  {
    id: "pc-002",
    cardId: "gpt_4o",
    name: "GPT-4o",
    provider: "OpenAI",
    pricingPattern: "token",
    status: "active",
    dimensions: mockTemplates[1].dimensions,
    description: "OpenAI GPT-4o for document summarisation",
    product: "doc_summariser",
    version: 2,
    createdAt: "2026-02-15T08:30:00Z",
    updatedAt: "2026-03-10T14:00:00Z",
  },
  {
    id: "pc-003",
    cardId: "serper_search",
    name: "Serper Web Search",
    provider: "Serper",
    pricingPattern: "request",
    status: "draft",
    dimensions: [
      { key: "requests", type: "flat", price: 0.001, label: "Search requests", unit: "per request" },
    ],
    version: 1,
    createdAt: "2026-04-01T09:00:00Z",
    updatedAt: "2026-04-01T09:00:00Z",
  },
];

export const mockProducts = [
  "property_search",
  "doc_summariser",
  "content_gen",
];
```

- [ ] **Step 2: Create mock.ts adapter**

```typescript
// src/features/pricing-cards/api/mock.ts
import type { PricingCard, Template, CreateCardRequest } from "./types";
import { mockPricingCards, mockTemplates, mockProducts } from "./mock-data";

const delay = (ms = 300) => new Promise((r) => setTimeout(r, ms));

let cards = [...mockPricingCards];

export async function getCards(): Promise<PricingCard[]> {
  await delay();
  return [...cards];
}

export async function getTemplates(): Promise<Template[]> {
  await delay(200);
  return [...mockTemplates];
}

export async function getProducts(): Promise<string[]> {
  await delay(100);
  return [...mockProducts];
}

export async function createCard(req: CreateCardRequest): Promise<PricingCard> {
  await delay(500);
  const card: PricingCard = {
    id: `pc-${Date.now()}`,
    cardId: req.cardId,
    name: req.name,
    provider: req.provider,
    pricingPattern: req.pricingPattern,
    status: req.status,
    dimensions: req.dimensions,
    description: req.description,
    pricingSourceUrl: req.pricingSourceUrl,
    product: req.product,
    version: 1,
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
  };
  cards = [card, ...cards];
  return card;
}
```

- [ ] **Step 3: Create api.ts adapter (placeholder)**

```typescript
// src/features/pricing-cards/api/api.ts
import type { PricingCard, Template, CreateCardRequest } from "./types";
import { meteringApi } from "@/api/client";

export async function getCards(): Promise<PricingCard[]> {
  const { data } = await meteringApi.GET("/rate-cards");
  return data as PricingCard[];
}

export async function getTemplates(): Promise<Template[]> {
  const { data } = await meteringApi.GET("/rate-cards/templates");
  return data as Template[];
}

export async function getProducts(): Promise<string[]> {
  const { data } = await meteringApi.GET("/products");
  return data as string[];
}

export async function createCard(req: CreateCardRequest): Promise<PricingCard> {
  const { data } = await meteringApi.POST("/rate-cards", { body: req });
  return data as PricingCard;
}
```

- [ ] **Step 4: Create provider.ts**

```typescript
// src/features/pricing-cards/api/provider.ts
import { selectProvider } from "@/lib/api-provider";
import * as mock from "./mock";
import * as api from "./api";

export const pricingCardsApi = selectProvider({ mock, api });
```

- [ ] **Step 5: Create queries.ts**

```typescript
// src/features/pricing-cards/api/queries.ts
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { pricingCardsApi } from "./provider";
import type { CreateCardRequest } from "./types";

export function usePricingCards() {
  return useQuery({
    queryKey: ["pricing-cards"],
    queryFn: () => pricingCardsApi.getCards(),
  });
}

export function useTemplates() {
  return useQuery({
    queryKey: ["pricing-card-templates"],
    queryFn: () => pricingCardsApi.getTemplates(),
  });
}

export function useProducts() {
  return useQuery({
    queryKey: ["products"],
    queryFn: () => pricingCardsApi.getProducts(),
  });
}

export function useCreateCard() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (req: CreateCardRequest) => pricingCardsApi.createCard(req),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["pricing-cards"] });
    },
  });
}
```

- [ ] **Step 6: Verify build passes**

Run: `pnpm build`
Expected: Build succeeds.

---

## Task 3: Install shadcn Components + Wizard Stepper

**Files:**
- Create: `src/features/pricing-cards/components/wizard-stepper.tsx`

- [ ] **Step 1: Install shadcn components**

```bash
npx shadcn@latest add card input label select textarea badge dialog --yes
```

- [ ] **Step 2: Create wizard-stepper.tsx**

The 4-step progress indicator. Numbered dots with labels, connecting lines, completed/active states.

```typescript
// src/features/pricing-cards/components/wizard-stepper.tsx
import { Check } from "lucide-react";
import { cn } from "@/lib/utils";

const steps = [
  { label: "Source" },
  { label: "Details" },
  { label: "Dimensions" },
  { label: "Review & test" },
];

interface WizardStepperProps {
  currentStep: number;
}

export function WizardStepper({ currentStep }: WizardStepperProps) {
  return (
    <div className="mb-6 flex items-center justify-center gap-0">
      {steps.map((step, idx) => {
        const isCompleted = idx < currentStep;
        const isActive = idx === currentStep;

        return (
          <div key={step.label} className="flex items-center">
            <div className="flex flex-col items-center">
              <div
                className={cn(
                  "flex h-6 w-6 items-center justify-center rounded-full border-2 text-[11px] font-medium transition-colors",
                  isCompleted && "border-green-600 bg-green-600 text-white",
                  isActive && "border-foreground text-foreground",
                  !isCompleted && !isActive && "border-border text-muted-foreground",
                )}
              >
                {isCompleted ? <Check className="h-3 w-3" /> : idx + 1}
              </div>
              <span className="mt-1 text-[10px] text-muted-foreground">
                {step.label}
              </span>
            </div>
            {idx < steps.length - 1 && (
              <div
                className={cn(
                  "mx-2 h-px w-10 transition-colors",
                  idx < currentStep ? "bg-green-600" : "bg-border",
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

- [ ] **Step 3: Verify build passes**

Run: `pnpm build`
Expected: Build succeeds.

---

## Task 4: Wizard Container + Step 1 (Source Selection)

**Files:**
- Create: `src/features/pricing-cards/components/new-card-wizard.tsx`
- Create: `src/features/pricing-cards/components/step-source.tsx`
- Modify: `src/app/routes/_app/pricing-cards/new.tsx` (create new route)

- [ ] **Step 1: Create step-source.tsx**

```typescript
// src/features/pricing-cards/components/step-source.tsx
import { useFormContext } from "react-hook-form";
import type { WizardFormValues } from "../lib/schema";
import type { Template } from "../api/types";
import { useTemplates } from "../api/queries";
import { cn } from "@/lib/utils";

export function StepSource() {
  const { watch, setValue } = useFormContext<WizardFormValues>();
  const sourceType = watch("sourceType");
  const templateId = watch("templateId");
  const { data: templates = [] } = useTemplates();

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-[14px] font-medium">How do you want to start?</h2>
        <p className="text-[12px] text-muted-foreground">
          Pick a pre-built template or configure from scratch.
        </p>
      </div>

      <div className="grid grid-cols-2 gap-2.5">
        <SourceOption
          selected={sourceType === "template"}
          onClick={() => setValue("sourceType", "template")}
          title="From template"
          subtitle="Pre-filled with current API pricing."
        />
        <SourceOption
          selected={sourceType === "custom"}
          onClick={() => {
            setValue("sourceType", "custom");
            setValue("templateId", undefined);
          }}
          title="Custom card"
          subtitle="Configure from scratch for any API."
        />
      </div>

      {sourceType === "template" && templates.length > 0 && (
        <div className="space-y-2">
          <label className="text-[11px] font-medium text-muted-foreground">
            Choose a template
          </label>
          <div className="grid grid-cols-3 gap-2.5">
            {templates.map((t) => (
              <TemplateOption
                key={t.id}
                template={t}
                selected={templateId === t.id}
                onClick={() => setValue("templateId", t.id)}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function SourceOption({
  selected,
  onClick,
  title,
  subtitle,
}: {
  selected: boolean;
  onClick: () => void;
  title: string;
  subtitle: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "rounded-xl border px-3.5 py-3 text-left transition-colors",
        selected
          ? "border-2 border-foreground"
          : "border-border hover:border-muted-foreground hover:bg-accent",
      )}
    >
      <div className="text-[13px] font-medium">{title}</div>
      <div className="text-[11px] text-muted-foreground">{subtitle}</div>
    </button>
  );
}

function TemplateOption({
  template,
  selected,
  onClick,
}: {
  template: Template;
  selected: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "rounded-xl border px-3 py-2.5 text-left transition-colors",
        selected
          ? "border-2 border-foreground"
          : "border-border hover:border-muted-foreground hover:bg-accent",
      )}
    >
      <div className="text-[12px] font-medium">{template.name}</div>
      <div className="text-[11px] text-muted-foreground">
        {template.dimensionCount} dimensions
      </div>
    </button>
  );
}
```

- [ ] **Step 2: Create new-card-wizard.tsx**

```typescript
// src/features/pricing-cards/components/new-card-wizard.tsx
import { useState, useCallback } from "react";
import { useForm, FormProvider } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useNavigate } from "@tanstack/react-router";
import { WizardStepper } from "./wizard-stepper";
import { StepSource } from "./step-source";
import { wizardSchema, type WizardFormValues } from "../lib/schema";
import { useTemplates } from "../api/queries";

const defaultValues: WizardFormValues = {
  sourceType: "template",
  templateId: undefined,
  name: "",
  provider: "",
  providerCustom: undefined,
  cardId: "",
  pricingPattern: "token",
  description: "",
  pricingSourceUrl: "",
  dimensions: [],
  product: undefined,
};

export function NewCardWizard() {
  const [step, setStep] = useState(0);
  const navigate = useNavigate();
  const { data: templates = [] } = useTemplates();

  const form = useForm<WizardFormValues>({
    resolver: zodResolver(wizardSchema),
    defaultValues,
    mode: "onChange",
  });

  const next = useCallback(() => {
    if (step === 0) {
      const sourceType = form.getValues("sourceType");
      const templateId = form.getValues("templateId");

      // If template selected, pre-fill details + dimensions from template
      if (sourceType === "template" && templateId) {
        const template = templates.find((t) => t.id === templateId);
        if (template) {
          form.setValue("name", template.name);
          form.setValue("provider", template.provider);
          form.setValue("pricingPattern", template.pricingPattern);
          form.setValue("dimensions", template.dimensions);
          form.setValue("description", template.description ?? "");
        }
      }

      // If custom + token pattern, pre-seed token dimensions
      if (sourceType === "custom") {
        const pattern = form.getValues("pricingPattern");
        if (pattern === "token" && form.getValues("dimensions").length === 0) {
          form.setValue("dimensions", [
            { key: "input_tokens", type: "per_unit", price: 0, label: "Input tokens", unit: "per 1M tokens" },
            { key: "output_tokens", type: "per_unit", price: 0, label: "Output tokens", unit: "per 1M tokens" },
          ]);
        }
      }
    }
    setStep((s) => Math.min(s + 1, 3));
  }, [step, form, templates]);

  const prev = useCallback(() => {
    setStep((s) => Math.max(s - 1, 0));
  }, []);

  const goToCards = useCallback(() => {
    navigate({ to: "/pricing-cards" });
  }, [navigate]);

  return (
    <div className="mx-auto max-w-[640px]">
      <WizardStepper currentStep={step} />

      <FormProvider {...form}>
        {step === 0 && <StepSource />}
        {step === 1 && (
          <div className="rounded-lg border border-dashed p-8 text-center text-sm text-muted-foreground">
            Step 2: Details — Task 5
          </div>
        )}
        {step === 2 && (
          <div className="rounded-lg border border-dashed p-8 text-center text-sm text-muted-foreground">
            Step 3: Dimensions — Task 6
          </div>
        )}
        {step === 3 && (
          <div className="rounded-lg border border-dashed p-8 text-center text-sm text-muted-foreground">
            Step 4: Review — Task 7
          </div>
        )}
      </FormProvider>

      {/* Navigation */}
      <div className="mt-6 flex justify-between">
        {step > 0 ? (
          <button
            type="button"
            onClick={prev}
            className="rounded-md border border-border px-4 py-1.5 text-[12.5px] text-muted-foreground hover:bg-accent"
          >
            Back
          </button>
        ) : (
          <button
            type="button"
            onClick={goToCards}
            className="rounded-md border border-border px-4 py-1.5 text-[12.5px] text-muted-foreground hover:bg-accent"
          >
            Cancel
          </button>
        )}
        {step < 3 && (
          <button
            type="button"
            onClick={next}
            className="rounded-md bg-foreground px-5 py-1.5 text-[12.5px] font-medium text-background hover:opacity-90"
          >
            Next
          </button>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Create the wizard route**

```typescript
// src/app/routes/_app/pricing-cards/new.tsx
import { createFileRoute } from "@tanstack/react-router";
import { NewCardWizard } from "@/features/pricing-cards/components/new-card-wizard";

export const Route = createFileRoute("/_app/pricing-cards/new")({
  component: NewCardWizard,
});
```

- [ ] **Step 4: Verify build passes and route works**

Run: `pnpm build`
Expected: Build succeeds. Dev server shows wizard at `/pricing-cards/new` with stepper + source selection.

---

## Task 5: Step 2 — Card Details + Live Preview

**Files:**
- Create: `src/features/pricing-cards/components/step-details.tsx`
- Create: `src/features/pricing-cards/components/card-preview.tsx`
- Modify: `src/features/pricing-cards/components/new-card-wizard.tsx` (replace step 2 stub)

- [ ] **Step 1: Create card-preview.tsx**

```typescript
// src/features/pricing-cards/components/card-preview.tsx
import { useFormContext } from "react-hook-form";
import type { WizardFormValues } from "../lib/schema";

const patternLabels: Record<string, string> = {
  token: "Token-based",
  request: "Per-request",
  mixed: "Mixed / other",
};

export function CardPreview() {
  const { watch } = useFormContext<WizardFormValues>();
  const name = watch("name");
  const provider = watch("provider");
  const providerCustom = watch("providerCustom");
  const cardId = watch("cardId");
  const pricingPattern = watch("pricingPattern");

  const displayProvider = provider === "Other" ? providerCustom : provider;

  return (
    <div className="rounded-xl bg-accent/50 px-3.5 py-3">
      <div className="mb-2 text-[10px] text-muted-foreground">Card preview</div>
      <div className="flex items-start gap-2">
        <div className="mt-0.5 h-2 w-2 rounded-full bg-amber-500" />
        <div className="flex-1">
          <div className="flex items-center gap-2">
            <span className="text-[14px] font-medium">
              {name || "Untitled card"}
            </span>
            <span className="rounded-full bg-muted px-2 py-0.5 text-[10px] text-muted-foreground">
              Draft
            </span>
          </div>
          {displayProvider && (
            <div className="text-[11px] text-muted-foreground">
              {displayProvider}
            </div>
          )}
          {cardId && (
            <div className="font-mono text-[11px] text-muted-foreground">
              {cardId}
            </div>
          )}
          {pricingPattern && (
            <div className="mt-1 text-[10px] text-muted-foreground">
              {patternLabels[pricingPattern]}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Create step-details.tsx**

```typescript
// src/features/pricing-cards/components/step-details.tsx
import { useFormContext } from "react-hook-form";
import type { WizardFormValues } from "../lib/schema";
import { slugify, slugifyWithSuffix } from "../lib/slugify";
import { CardPreview } from "./card-preview";
import { cn } from "@/lib/utils";

const providers = [
  "Google", "OpenAI", "Anthropic", "AWS", "Azure",
  "Cohere", "Replicate", "Twilio", "Mapbox", "Stripe", "Other",
];

const patterns = [
  {
    value: "token" as const,
    label: "Token-based",
    subtitle: "Charges per input and/or output token. Most LLM APIs.",
    hint: "We'll pre-add input_tokens and output_tokens dimensions.",
  },
  {
    value: "request" as const,
    label: "Per-request",
    subtitle: "Flat fee per API call regardless of payload size.",
    hint: "We'll pre-add a single requests dimension.",
  },
  {
    value: "mixed" as const,
    label: "Mixed / other",
    subtitle: "Combination of unit-based and flat charges, or something unique.",
    hint: "We'll start you with a blank dimension list.",
  },
];

export function StepDetails() {
  const { register, watch, setValue, formState: { errors } } = useFormContext<WizardFormValues>();
  const provider = watch("provider");
  const pricingPattern = watch("pricingPattern");
  const description = watch("description") ?? "";

  const handleNameChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const name = e.target.value;
    setValue("name", name);
    setValue("cardId", slugify(name));
  };

  const handleRegenerate = () => {
    const name = watch("name");
    if (name) setValue("cardId", slugifyWithSuffix(name));
  };

  const handlePatternChange = (pattern: "token" | "request" | "mixed") => {
    setValue("pricingPattern", pattern);
    // Pre-seed dimensions based on pattern
    if (pattern === "token") {
      setValue("dimensions", [
        { key: "input_tokens", type: "per_unit", price: 0, label: "Input tokens", unit: "per 1M tokens" },
        { key: "output_tokens", type: "per_unit", price: 0, label: "Output tokens", unit: "per 1M tokens" },
      ]);
    } else if (pattern === "request") {
      setValue("dimensions", [
        { key: "requests", type: "flat", price: 0, label: "Requests", unit: "per request" },
      ]);
    } else {
      setValue("dimensions", []);
    }
  };

  return (
    <div className="space-y-5">
      {/* Identity */}
      <div className="space-y-3">
        <div>
          <label className="mb-1 block text-[11px] font-medium">Card name</label>
          <input
            {...register("name")}
            onChange={handleNameChange}
            placeholder="e.g. Mapbox Geocoding API, Internal OCR Service..."
            className="w-full rounded-lg border border-border bg-background px-3 py-2 text-[13px] outline-none focus:border-muted-foreground"
          />
          <p className="mt-0.5 text-[10px] text-muted-foreground">
            Use the API or model name your team would recognise.
          </p>
          {errors.name && <p className="mt-0.5 text-[10px] text-red-500">{errors.name.message}</p>}
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="mb-1 block text-[11px] font-medium">Provider</label>
            <select
              {...register("provider")}
              className="w-full rounded-lg border border-border bg-background px-3 py-2 text-[13px] outline-none focus:border-muted-foreground"
            >
              <option value="">Select provider...</option>
              {providers.map((p) => (
                <option key={p} value={p}>{p}</option>
              ))}
            </select>
            {provider === "Other" && (
              <input
                {...register("providerCustom")}
                placeholder="Custom provider name"
                className="mt-1.5 w-full rounded-lg border border-border bg-background px-3 py-2 text-[13px] outline-none focus:border-muted-foreground"
              />
            )}
          </div>

          <div>
            <label className="mb-1 block text-[11px] font-medium">Card ID</label>
            <div className="flex gap-1.5">
              <input
                {...register("cardId")}
                placeholder="auto-generated"
                className="flex-1 rounded-lg border border-border bg-background px-3 py-2 font-mono text-[12px] text-muted-foreground outline-none focus:border-muted-foreground"
              />
              <button
                type="button"
                onClick={handleRegenerate}
                className="shrink-0 rounded-lg border border-border px-2.5 py-2 text-[11px] text-muted-foreground hover:bg-accent"
              >
                Regenerate
              </button>
            </div>
            <p className="mt-0.5 text-[10px] text-muted-foreground">
              Referenced in SDK calls. Auto-derived from name.
            </p>
          </div>
        </div>
      </div>

      {/* Pricing Pattern */}
      <div className="border-t border-border pt-4">
        <label className="mb-0.5 block text-[11px] font-medium">Pricing pattern</label>
        <p className="mb-3 text-[11px] text-muted-foreground">
          How does this API charge? This helps us pre-configure dimensions.
        </p>
        <div className="grid grid-cols-3 gap-2.5">
          {patterns.map((p) => (
            <button
              key={p.value}
              type="button"
              onClick={() => handlePatternChange(p.value)}
              className={cn(
                "rounded-xl border px-3 py-2.5 text-left transition-colors",
                pricingPattern === p.value
                  ? "border-2 border-foreground"
                  : "border-border hover:border-muted-foreground hover:bg-accent",
              )}
            >
              <div className="text-[12px] font-medium">{p.label}</div>
              <div className="text-[10px] text-muted-foreground">{p.subtitle}</div>
            </button>
          ))}
        </div>
        {pricingPattern && (
          <div className="mt-2 rounded-lg bg-accent/50 px-3 py-2 font-mono text-[10px] text-muted-foreground">
            {patterns.find((p) => p.value === pricingPattern)?.hint}
          </div>
        )}
      </div>

      {/* Optional context */}
      <div className="border-t border-border pt-4 space-y-3">
        <div>
          <label className="mb-1 block text-[11px] font-medium">Description (optional)</label>
          <textarea
            {...register("description")}
            maxLength={250}
            placeholder="e.g. Used for geocoding property addresses in the search pipeline..."
            className="min-h-[56px] w-full rounded-lg border border-border bg-background px-3 py-2 text-[13px] outline-none focus:border-muted-foreground"
          />
          <div className="text-right text-[10px] text-muted-foreground">
            {description.length} / 250
          </div>
        </div>

        <div>
          <label className="mb-1 block text-[11px] font-medium">Pricing source URL (optional)</label>
          <input
            {...register("pricingSourceUrl")}
            placeholder="https://cloud.google.com/maps-platform/pricing"
            className="w-full rounded-lg border border-border bg-background px-3 py-2 text-[13px] outline-none focus:border-muted-foreground"
          />
          <p className="mt-0.5 text-[10px] text-muted-foreground">
            Link to the provider's pricing page for reference.
          </p>
        </div>
      </div>

      {/* Preview */}
      <CardPreview />
    </div>
  );
}
```

- [ ] **Step 3: Wire step 2 into wizard**

In `src/features/pricing-cards/components/new-card-wizard.tsx`, replace the step 1 stub:

```typescript
// Replace:
//   {step === 1 && (<div>Step 2: Details — Task 5</div>)}
// With:
import { StepDetails } from "./step-details";
// ...
{step === 1 && <StepDetails />}
```

- [ ] **Step 4: Verify build and test**

Run: `pnpm build && pnpm test`
Expected: All pass. Step 2 renders at `/pricing-cards/new` after clicking Next.

---

## Task 6: Step 3 — Dimensions + Cost Tester

**Files:**
- Create: `src/features/pricing-cards/components/dimension-card.tsx`
- Create: `src/features/pricing-cards/components/cost-tester.tsx`
- Create: `src/features/pricing-cards/components/step-dimensions.tsx`
- Modify: `src/features/pricing-cards/components/new-card-wizard.tsx` (replace step 3 stub)

This is the most complex step. I'll describe the components but keep the code within 200 lines per file.

- [ ] **Step 1: Create dimension-card.tsx**

A single collapsible dimension editor with key, pricing type toggle, unit price, display fields, and collapse/duplicate/remove actions.

The component receives `index` (position in the `dimensions` field array), and uses `useFormContext` + `useFieldArray` indirectly via props to manage the dimension's fields.

```typescript
// src/features/pricing-cards/components/dimension-card.tsx
import { useState } from "react";
import { useFormContext } from "react-hook-form";
import { ChevronDown, ChevronUp, Copy, Trash2 } from "lucide-react";
import type { WizardFormValues } from "../lib/schema";
import { cn } from "@/lib/utils";

interface DimensionCardProps {
  index: number;
  onRemove: () => void;
  onDuplicate: () => void;
  duplicateKeys: Set<string>;
}

export function DimensionCard({ index, onRemove, onDuplicate, duplicateKeys }: DimensionCardProps) {
  const [collapsed, setCollapsed] = useState(false);
  const { register, watch, setValue } = useFormContext<WizardFormValues>();

  const prefix = `dimensions.${index}` as const;
  const key = watch(`dimensions.${index}.key`);
  const type = watch(`dimensions.${index}.type`);
  const price = watch(`dimensions.${index}.price`);
  const isDuplicate = key ? duplicateKeys.has(key) : false;

  return (
    <div className="rounded-xl border border-border px-4 py-3 transition-colors hover:border-muted-foreground">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="text-[12px] font-medium">
          Dimension {index + 1}
          {collapsed && key && (
            <span className="ml-2 font-mono text-muted-foreground">{key}</span>
          )}
        </div>
        <div className="flex items-center gap-1">
          <button type="button" onClick={() => setCollapsed(!collapsed)} className="rounded p-1 text-muted-foreground hover:bg-accent">
            {collapsed ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronUp className="h-3.5 w-3.5" />}
          </button>
          <button type="button" onClick={onDuplicate} className="rounded p-1 text-muted-foreground hover:bg-accent">
            <Copy className="h-3.5 w-3.5" />
          </button>
          <button type="button" onClick={onRemove} className="rounded p-1 text-muted-foreground hover:bg-red-50 hover:text-red-500">
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      {/* Expandable body */}
      {!collapsed && (
        <div className="mt-3 space-y-3">
          {/* Row 1: Key + Type */}
          <div className="grid grid-cols-[1fr_auto] gap-3">
            <div>
              <label className="mb-1 block text-[10px] font-medium">Metric key</label>
              <input
                {...register(`dimensions.${index}.key`)}
                placeholder="e.g. input_tokens"
                className={cn(
                  "w-full rounded-lg border bg-background px-3 py-1.5 font-mono text-[12px] outline-none focus:border-muted-foreground",
                  isDuplicate ? "border-red-400" : "border-border",
                )}
              />
              {isDuplicate && (
                <p className="mt-0.5 text-[10px] text-red-500">(duplicate key!)</p>
              )}
              <p className="mt-0.5 text-[10px] text-muted-foreground">
                Must match the key your SDK sends.
              </p>
            </div>
            <div>
              <label className="mb-1 block text-[10px] font-medium">Pricing type</label>
              <div className="flex rounded-lg border border-border">
                <button
                  type="button"
                  onClick={() => setValue(`dimensions.${index}.type`, "per_unit")}
                  className={cn(
                    "px-3 py-1.5 text-[11px] transition-colors",
                    type === "per_unit" ? "bg-foreground text-background" : "text-muted-foreground hover:bg-accent",
                  )}
                >
                  Per unit
                </button>
                <button
                  type="button"
                  onClick={() => setValue(`dimensions.${index}.type`, "flat")}
                  className={cn(
                    "px-3 py-1.5 text-[11px] transition-colors",
                    type === "flat" ? "bg-foreground text-background" : "text-muted-foreground hover:bg-accent",
                  )}
                >
                  Flat
                </button>
              </div>
            </div>
          </div>

          {/* Row 2: Price */}
          <div>
            <label className="mb-1 block text-[10px] font-medium">Unit price ($)</label>
            <div className="relative">
              <span className="absolute left-3 top-1/2 -translate-y-1/2 text-[12px] text-muted-foreground">$</span>
              <input
                type="number"
                step="any"
                {...register(`dimensions.${index}.price`, { valueAsNumber: true })}
                placeholder="0.00000010"
                className="w-full rounded-lg border border-border bg-background py-1.5 pl-7 pr-3 font-mono text-[12px] outline-none focus:border-muted-foreground"
              />
            </div>
            <p className="mt-0.5 text-[10px] text-muted-foreground">
              {type === "per_unit" ? "Price per single unit." : "Fixed cost each time this fires."}
            </p>
            {type === "per_unit" && price > 0.001 && (
              <div className="mt-1 rounded-md bg-amber-50 px-2 py-1 text-[10px] text-amber-700 dark:bg-amber-900/20 dark:text-amber-400">
                This seems high for a per-unit price. Double-check.
              </div>
            )}
          </div>

          {/* Row 3: Display fields */}
          <div className="grid grid-cols-3 gap-3">
            <div>
              <label className="mb-1 block text-[10px] font-medium">Display label</label>
              <input
                {...register(`dimensions.${index}.label`)}
                placeholder="e.g. Input tokens"
                className="w-full rounded-lg border border-border bg-background px-3 py-1.5 text-[12px] outline-none focus:border-muted-foreground"
              />
            </div>
            <div>
              <label className="mb-1 block text-[10px] font-medium">Display unit</label>
              <input
                {...register(`dimensions.${index}.unit`)}
                placeholder="e.g. per 1M tokens"
                className="w-full rounded-lg border border-border bg-background px-3 py-1.5 text-[12px] outline-none focus:border-muted-foreground"
              />
            </div>
            <div>
              <label className="mb-1 block text-[10px] font-medium">Display price</label>
              <input
                {...register(`dimensions.${index}.displayPrice`)}
                placeholder="e.g. $0.10"
                className="w-full rounded-lg border border-border bg-background px-3 py-1.5 text-[12px] outline-none focus:border-muted-foreground"
              />
              <p className="mt-0.5 text-[10px] text-muted-foreground">Auto-calculated if blank.</p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Create cost-tester.tsx**

```typescript
// src/features/pricing-cards/components/cost-tester.tsx
import { useState, useMemo } from "react";
import { useFormContext } from "react-hook-form";
import type { WizardFormValues } from "../lib/schema";
import { calculateCosts, projectCosts } from "../lib/calculations";
import { formatCostMicros } from "@/lib/format";

export function CostTester() {
  const { watch } = useFormContext<WizardFormValues>();
  const dimensions = watch("dimensions");
  const [quantities, setQuantities] = useState<Record<string, number>>({});

  const result = useMemo(
    () => calculateCosts(dimensions, quantities),
    [dimensions, quantities],
  );

  const projection = useMemo(
    () => projectCosts(result.total, 1000),
    [result.total],
  );

  const setQty = (key: string, value: number) => {
    setQuantities((prev) => ({ ...prev, [key]: value }));
  };

  if (dimensions.length === 0) return null;

  return (
    <div className="rounded-xl border border-border bg-accent/30 px-4 py-3.5">
      <div className="mb-0.5 flex items-center gap-2">
        <span className="text-[13px] font-medium">Live cost tester</span>
        <span className="rounded-full bg-blue-50 px-2 py-0.5 text-[10px] text-blue-600 dark:bg-blue-900/20 dark:text-blue-400">
          Updates as you type
        </span>
      </div>
      <p className="mb-3 text-[11px] text-muted-foreground">
        Enter sample quantities to see calculated costs in real time.
      </p>

      <div className="space-y-1.5">
        {result.dimensions.map((d) => (
          <div key={d.key} className="grid grid-cols-[1fr_100px_120px] items-center gap-2">
            <span className="font-mono text-[11px] text-muted-foreground">{d.key}</span>
            <input
              type="number"
              value={quantities[d.key] ?? ""}
              onChange={(e) => setQty(d.key, Number(e.target.value) || 0)}
              placeholder={d.type === "flat" ? "1" : "1000"}
              className="rounded-md border border-border bg-background px-2 py-1 text-right font-mono text-[11px] outline-none focus:border-muted-foreground"
            />
            <span className="text-right font-mono text-[11px] text-muted-foreground">
              {d.quantity > 0
                ? `${d.quantity.toLocaleString()} × $${d.price} = $${d.cost.toFixed(6)}`
                : "—"}
            </span>
          </div>
        ))}
      </div>

      <div className="mt-3 border-t border-border pt-2">
        <div className="flex items-center justify-between">
          <span className="text-[12px] font-medium">Total event cost</span>
          <span className="font-mono text-[13px] font-medium">
            ${result.total.toFixed(6)}
          </span>
        </div>
        {result.total > 0 && (
          <p className="mt-1 text-[10px] text-muted-foreground">
            Approx ${projection.daily.toFixed(2)} per 1,000 events at this volume
          </p>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Create step-dimensions.tsx**

```typescript
// src/features/pricing-cards/components/step-dimensions.tsx
import { useMemo } from "react";
import { useFormContext, useFieldArray } from "react-hook-form";
import { Plus } from "lucide-react";
import type { WizardFormValues } from "../lib/schema";
import type { Dimension } from "../api/types";
import { DimensionCard } from "./dimension-card";
import { CostTester } from "./cost-tester";

const quickAdds: Partial<Dimension>[] = [
  { key: "grounding", label: "Grounding", type: "flat", unit: "per request" },
  { key: "cached_tokens", label: "Cached tokens", type: "per_unit", unit: "per 1M tokens" },
  { key: "image_tokens", label: "Image tokens", type: "per_unit", unit: "per 1M tokens" },
  { key: "requests", label: "Requests", type: "flat", unit: "per request" },
  { key: "search_queries", label: "Search queries", type: "flat", unit: "per query" },
];

export function StepDimensions() {
  const { watch } = useFormContext<WizardFormValues>();
  const { fields, append, remove, insert } = useFieldArray<WizardFormValues>({
    name: "dimensions",
  });
  const dimensions = watch("dimensions");

  // Track duplicate keys
  const duplicateKeys = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const d of dimensions) {
      if (d.key) counts[d.key] = (counts[d.key] ?? 0) + 1;
    }
    const dupes = new Set<string>();
    for (const [key, count] of Object.entries(counts)) {
      if (count > 1) dupes.add(key);
    }
    return dupes;
  }, [dimensions]);

  const existingKeys = new Set(dimensions.map((d) => d.key));

  const addDimension = () => {
    append({ key: "", type: "per_unit", price: 0, label: "", unit: "" });
  };

  const duplicateDimension = (index: number) => {
    const dim = dimensions[index];
    insert(index + 1, { ...dim, key: `${dim.key}_copy` });
  };

  const addQuick = (qa: Partial<Dimension>) => {
    if (existingKeys.has(qa.key!)) return;
    append({
      key: qa.key!,
      type: qa.type ?? "per_unit",
      price: 0,
      label: qa.label ?? "",
      unit: qa.unit ?? "",
    });
  };

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-[14px] font-medium">Define cost dimensions</h2>
        <p className="text-[12px] text-muted-foreground">
          Each dimension is one line item on your cost breakdown.
        </p>
      </div>

      {/* Dimension cards */}
      <div className="space-y-3">
        {fields.map((field, idx) => (
          <DimensionCard
            key={field.id}
            index={idx}
            onRemove={() => remove(idx)}
            onDuplicate={() => duplicateDimension(idx)}
            duplicateKeys={duplicateKeys}
          />
        ))}
      </div>

      {/* Add dimension */}
      <button
        type="button"
        onClick={addDimension}
        className="flex w-full items-center justify-center gap-1.5 rounded-xl border border-dashed border-border py-3 text-[12px] text-muted-foreground hover:border-muted-foreground hover:bg-accent"
      >
        <Plus className="h-3.5 w-3.5" /> Add dimension
      </button>

      {/* Quick add chips */}
      <div className="flex flex-wrap gap-1.5">
        {quickAdds
          .filter((qa) => !existingKeys.has(qa.key!))
          .map((qa) => (
            <button
              key={qa.key}
              type="button"
              onClick={() => addQuick(qa)}
              className="rounded-full border border-border px-2.5 py-0.5 font-mono text-[10px] text-muted-foreground hover:border-muted-foreground hover:bg-accent"
            >
              + {qa.key}
            </button>
          ))}
      </div>

      {/* Cost tester */}
      <CostTester />
    </div>
  );
}
```

- [ ] **Step 4: Wire step 3 into wizard**

In `new-card-wizard.tsx`, replace the step 2 stub:

```typescript
import { StepDimensions } from "./step-dimensions";
// ...
{step === 2 && <StepDimensions />}
```

- [ ] **Step 5: Verify build and test**

Run: `pnpm build && pnpm test`
Expected: All pass.

---

## Task 7: Step 4 — Review, Dry-Run, Activation

**Files:**
- Create: `src/features/pricing-cards/components/dry-run-simulator.tsx`
- Create: `src/features/pricing-cards/components/integration-snippet.tsx`
- Create: `src/features/pricing-cards/components/step-review.tsx`
- Modify: `src/features/pricing-cards/components/new-card-wizard.tsx` (replace step 4 stub, add activation flow)

- [ ] **Step 1: Create dry-run-simulator.tsx**

Dry-run with dimension breakdown, total, projection, cost distribution bar, and sanity warnings.

```typescript
// src/features/pricing-cards/components/dry-run-simulator.tsx
import { useState, useMemo } from "react";
import { useFormContext } from "react-hook-form";
import type { WizardFormValues } from "../lib/schema";
import { calculateCosts, calculateDistribution, projectCosts } from "../lib/calculations";

const BAR_COLORS = ["#378ADD", "#7F77DD", "#D85A30", "#3B6D11", "#854F0B"];

export function DryRunSimulator() {
  const { watch } = useFormContext<WizardFormValues>();
  const dimensions = watch("dimensions");
  const [quantities, setQuantities] = useState<Record<string, number>>(() => {
    const init: Record<string, number> = {};
    for (const d of dimensions) {
      init[d.key] = d.type === "flat" ? 1 : 1000;
    }
    return init;
  });

  const result = useMemo(() => calculateCosts(dimensions, quantities), [dimensions, quantities]);
  const distribution = useMemo(() => calculateDistribution(result), [result]);
  const projection = useMemo(() => projectCosts(result.total, 1000), [result.total]);

  const dominant = distribution.length > 0 && distribution[0].percentage > 90 ? distribution[0] : null;

  const setQty = (key: string, value: number) => {
    setQuantities((prev) => ({ ...prev, [key]: value }));
  };

  return (
    <div className="rounded-xl border border-border bg-accent/30 px-4 py-4">
      <div className="mb-0.5 flex items-center justify-between">
        <span className="text-[13px] font-medium">Dry-run simulator</span>
        {result.total > 0 && (
          <span className="rounded-full bg-green-50 px-2 py-0.5 text-[10px] text-green-700 dark:bg-green-900/20 dark:text-green-400">
            Looks correct
          </span>
        )}
      </div>
      <p className="mb-3 text-[11px] text-muted-foreground">
        Enter realistic sample quantities for a single API call.
      </p>

      {/* Inputs */}
      <div className="space-y-1.5">
        {result.dimensions.map((d) => (
          <div key={d.key} className="grid grid-cols-[130px_100px_1fr] items-center gap-2">
            <span className="font-mono text-[11px] text-muted-foreground">{d.key}</span>
            <input
              type="number"
              value={quantities[d.key] ?? ""}
              onChange={(e) => setQty(d.key, Number(e.target.value) || 0)}
              className="rounded-md border border-border bg-background px-2 py-1 text-right font-mono text-[11px] outline-none focus:border-muted-foreground"
            />
            <span className="text-right font-mono text-[11px] text-muted-foreground">
              {d.quantity > 0
                ? `${d.quantity.toLocaleString()} × $${d.price} = $${d.cost.toFixed(6)}`
                : "—"}
            </span>
          </div>
        ))}
      </div>

      {/* Breakdown */}
      <div className="mt-3 border-t border-border pt-2 space-y-1">
        {result.dimensions.map((d) => (
          <div key={d.key} className="flex justify-between text-[11px]">
            <span className="text-muted-foreground">{d.label}</span>
            <span className="font-mono font-medium">${d.cost.toFixed(6)}</span>
          </div>
        ))}
      </div>

      {/* Total */}
      <div className="mt-2 border-t border-border pt-2 flex justify-between">
        <span className="text-[13px] font-medium">Total per event</span>
        <span className="font-mono text-[14px] font-medium">${result.total.toFixed(6)}</span>
      </div>

      {result.total > 0 && (
        <p className="mt-1 text-[10px] text-muted-foreground">
          At 1,000 events/day: ~${projection.daily.toFixed(2)}/day · ~${projection.monthly.toFixed(0)}/month
        </p>
      )}

      {/* Distribution bar */}
      {distribution.length > 0 && (
        <div className="mt-3">
          <div className="mb-1 text-[10px] text-muted-foreground">Cost distribution</div>
          <div className="flex h-2 overflow-hidden rounded-full">
            {distribution.map((d, i) => (
              <div
                key={d.key}
                className="h-full"
                style={{
                  width: `${Math.max(d.percentage, 0.3)}%`,
                  backgroundColor: BAR_COLORS[i % BAR_COLORS.length],
                }}
              />
            ))}
          </div>
          <div className="mt-1 flex flex-wrap gap-3">
            {distribution.map((d, i) => (
              <div key={d.key} className="flex items-center gap-1 text-[10px] text-muted-foreground">
                <div className="h-2 w-2 rounded-full" style={{ backgroundColor: BAR_COLORS[i % BAR_COLORS.length] }} />
                {d.label} {d.percentage.toFixed(1)}%
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Sanity warning */}
      {dominant && (
        <div className="mt-3 rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 dark:border-amber-700 dark:bg-amber-900/20">
          <div className="text-[11px] font-medium text-amber-700 dark:text-amber-400">
            Dominated by one dimension
          </div>
          <p className="text-[10px] text-amber-600 dark:text-amber-400">
            {dominant.label} accounts for {dominant.percentage.toFixed(1)}% of total cost. Is this expected?
          </p>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Create integration-snippet.tsx**

```typescript
// src/features/pricing-cards/components/integration-snippet.tsx
import { useFormContext } from "react-hook-form";
import type { WizardFormValues } from "../lib/schema";

export function IntegrationSnippet() {
  const { watch } = useFormContext<WizardFormValues>();
  const cardId = watch("cardId");
  const product = watch("product");
  const dimensions = watch("dimensions");

  const usageLines = dimensions
    .map((d) => `    ${d.key}: ${d.type === "flat" ? "1" : `${d.key}Count`}`)
    .join(",\n");

  const productLine = product ? `\n  product: "${product}",` : "";

  const snippet = `meter.track({
  pricing_card: "${cardId}",${productLine}
  usage: {
${usageLines}
  }
})`;

  const copy = () => {
    navigator.clipboard.writeText(snippet);
  };

  return (
    <div className="rounded-xl border border-border px-3.5 py-3">
      <div className="mb-2 flex items-center justify-between">
        <span className="text-[12px] font-medium">Integration snippet</span>
        <button
          type="button"
          onClick={copy}
          className="text-[10px] text-blue-600 hover:underline dark:text-blue-400"
        >
          Copy to clipboard
        </button>
      </div>
      <pre className="overflow-x-auto rounded-lg bg-accent/50 px-3 py-2.5 font-mono text-[10px] leading-[1.8] text-muted-foreground">
        {snippet}
      </pre>
      <p className="mt-1.5 text-[10px] text-muted-foreground">
        This snippet updates automatically when you assign a product.
      </p>
    </div>
  );
}
```

- [ ] **Step 3: Create step-review.tsx**

```typescript
// src/features/pricing-cards/components/step-review.tsx
import { useState } from "react";
import { useFormContext } from "react-hook-form";
import { Check, AlertTriangle } from "lucide-react";
import type { WizardFormValues } from "../lib/schema";
import { useProducts, useCreateCard } from "../api/queries";
import { DryRunSimulator } from "./dry-run-simulator";
import { IntegrationSnippet } from "./integration-snippet";
import { cn } from "@/lib/utils";

export function StepReview() {
  const { watch, setValue, getValues } = useFormContext<WizardFormValues>();
  const { data: products = [] } = useProducts();
  const createCard = useCreateCard();
  const [showConfirm, setShowConfirm] = useState(false);
  const [activated, setActivated] = useState(false);

  const name = watch("name");
  const provider = watch("provider");
  const cardId = watch("cardId");
  const dimensions = watch("dimensions");
  const selectedProduct = watch("product");

  const checks = [
    { label: "All dimensions have non-zero prices", pass: dimensions.every((d) => d.price > 0) },
    { label: "No duplicate metric keys", pass: new Set(dimensions.map((d) => d.key)).size === dimensions.length },
    { label: "Unit prices within expected ranges", pass: dimensions.every((d) => d.type === "flat" ? d.price <= 100 : d.price <= 1) },
    { label: "Card ID is valid", pass: cardId.length > 0 && /^[a-z0-9_]+$/.test(cardId) },
  ];

  const handleActivate = async () => {
    const values = getValues();
    await createCard.mutateAsync({
      name: values.name,
      cardId: values.cardId,
      provider: values.provider === "Other" ? (values.providerCustom ?? values.provider) : values.provider,
      pricingPattern: values.pricingPattern,
      dimensions: values.dimensions,
      description: values.description,
      pricingSourceUrl: values.pricingSourceUrl,
      product: values.product,
      status: "active",
    });
    setActivated(true);
    setShowConfirm(false);
  };

  if (activated) {
    return (
      <div className="space-y-5 text-center">
        <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-green-100 dark:bg-green-900/30">
          <Check className="h-6 w-6 text-green-600" />
        </div>
        <h2 className="text-[16px] font-medium">{name} is live</h2>
        <p className="text-[12px] text-muted-foreground">
          Your card is now actively calculating costs for every event sent to{" "}
          <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-[11px]">{cardId}</code>
        </p>
        <IntegrationSnippet />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Review card */}
      <div className="rounded-xl border border-border px-4 py-3.5">
        <div className="flex items-start justify-between">
          <div>
            <div className="text-[15px] font-medium">{name}</div>
            <div className="text-[11px] text-muted-foreground">
              {provider} <span className="font-mono">{cardId}</span>
            </div>
          </div>
          <span className="rounded-full bg-amber-50 px-2 py-0.5 text-[10px] text-amber-700 dark:bg-amber-900/20 dark:text-amber-400">
            Draft v1
          </span>
        </div>

        <div className="my-3 border-t border-border" />

        <div className="mb-1 text-[11px] text-muted-foreground">
          Cost dimensions ({dimensions.length})
        </div>
        <div className="divide-y divide-border">
          {dimensions.map((d) => (
            <div key={d.key} className="grid grid-cols-[1fr_auto_auto_auto] items-center gap-4 py-1.5">
              <span className="font-mono text-[11px]">{d.key}</span>
              <span className="rounded-full bg-muted px-2 py-0.5 text-[10px]">{d.type === "per_unit" ? "per unit" : "flat"}</span>
              <span className="text-[11px] text-muted-foreground">{d.unit}</span>
              <span className="font-mono text-[12px] font-medium">{d.displayPrice || `$${d.price}`}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Dry-run */}
      <DryRunSimulator />

      {/* Validation checklist */}
      <div className="space-y-1.5">
        {checks.map((c) => (
          <div key={c.label} className="flex items-center gap-2">
            <div className={cn(
              "flex h-4.5 w-4.5 items-center justify-center rounded-full",
              c.pass ? "bg-green-100 dark:bg-green-900/30" : "bg-amber-100 dark:bg-amber-900/30",
            )}>
              {c.pass
                ? <Check className="h-3 w-3 text-green-600" />
                : <AlertTriangle className="h-3 w-3 text-amber-600" />}
            </div>
            <span className="text-[12px]">{c.label}</span>
          </div>
        ))}
      </div>

      {/* Product assignment */}
      <div className="rounded-xl border border-border px-4 py-3.5">
        <div className="mb-0.5 text-[12px] font-medium">Assign to product</div>
        <p className="mb-2 text-[11px] text-muted-foreground">
          Group this card under a product for dashboard aggregation.
        </p>
        <div className="flex flex-wrap gap-1.5">
          {products.map((p) => (
            <button
              key={p}
              type="button"
              onClick={() => setValue("product", selectedProduct === p ? undefined : p)}
              className={cn(
                "rounded-full border px-3 py-1 text-[11px] transition-colors",
                selectedProduct === p
                  ? "border-blue-200 bg-blue-50 text-blue-700 dark:border-blue-800 dark:bg-blue-900/20 dark:text-blue-400"
                  : "border-border text-muted-foreground hover:border-muted-foreground hover:bg-accent",
              )}
            >
              {p.replace(/_/g, " ")}
            </button>
          ))}
        </div>
      </div>

      {/* Integration snippet */}
      <IntegrationSnippet />

      {/* Activation confirmation */}
      {showConfirm && (
        <div className="rounded-xl border-2 border-green-500 p-4 text-center">
          <h3 className="text-[14px] font-medium">Activate this card?</h3>
          <p className="mt-1 text-[11px] text-muted-foreground">
            Once active, this card will calculate real costs for every matching usage event. You can create new versions later.
          </p>
          <div className="mt-3 flex justify-center gap-2">
            <button
              type="button"
              onClick={() => setShowConfirm(false)}
              className="rounded-md border border-border px-4 py-1.5 text-[12px] text-muted-foreground hover:bg-accent"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={handleActivate}
              disabled={createCard.isPending}
              className="rounded-md bg-green-600 px-4 py-1.5 text-[12px] font-medium text-white hover:opacity-90 disabled:opacity-50"
            >
              {createCard.isPending ? "Activating..." : "Yes, activate"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Wire step 4 into wizard and add activation buttons**

In `new-card-wizard.tsx`, replace the step 3 stub and update the navigation for step 4:

```typescript
import { StepReview } from "./step-review";
// ...
{step === 3 && <StepReview />}

// Update navigation: on step 3, show "Save as draft" and "Activate" instead of "Next"
```

The navigation section at the bottom of `new-card-wizard.tsx` should become:

```typescript
{/* Navigation */}
<div className="mt-6 flex justify-between">
  {step > 0 ? (
    <button type="button" onClick={prev} className="rounded-md border border-border px-4 py-1.5 text-[12.5px] text-muted-foreground hover:bg-accent">
      Back
    </button>
  ) : (
    <button type="button" onClick={goToCards} className="rounded-md border border-border px-4 py-1.5 text-[12.5px] text-muted-foreground hover:bg-accent">
      Cancel
    </button>
  )}
  <div className="flex gap-2">
    {step < 3 && (
      <button type="button" onClick={next} className="rounded-md bg-foreground px-5 py-1.5 text-[12.5px] font-medium text-background hover:opacity-90">
        Next
      </button>
    )}
  </div>
</div>
```

Step 4's activation buttons are handled inside `step-review.tsx` itself (via `showConfirm` state).

- [ ] **Step 5: Verify build and test**

Run: `pnpm build && pnpm test`
Expected: All pass.

---

## Task 8: Pricing Cards List Page

**Files:**
- Create: `src/features/pricing-cards/components/pricing-cards-page.tsx`
- Create: `src/features/pricing-cards/components/pricing-card-item.tsx`
- Modify: `src/app/routes/_app/pricing-cards/index.tsx` (replace stub)

- [ ] **Step 1: Create pricing-card-item.tsx**

```typescript
// src/features/pricing-cards/components/pricing-card-item.tsx
import type { PricingCard } from "../api/types";
import { cn } from "@/lib/utils";

interface PricingCardItemProps {
  card: PricingCard;
}

export function PricingCardItem({ card }: PricingCardItemProps) {
  return (
    <div className="rounded-xl border border-border px-4 py-3 transition-colors hover:border-muted-foreground">
      <div className="flex items-start justify-between">
        <div>
          <div className="text-[13px] font-medium">{card.name}</div>
          <div className="text-[11px] text-muted-foreground">{card.provider}</div>
        </div>
        <span
          className={cn(
            "rounded-full px-2 py-0.5 text-[10px] font-medium",
            card.status === "active"
              ? "bg-green-50 text-green-700 dark:bg-green-900/20 dark:text-green-400"
              : "bg-amber-50 text-amber-700 dark:bg-amber-900/20 dark:text-amber-400",
          )}
        >
          {card.status === "active" ? "Active" : "Draft"}
        </span>
      </div>
      <div className="mt-1.5 font-mono text-[10px] text-muted-foreground">{card.cardId}</div>
      <div className="mt-1 text-[10px] text-muted-foreground">
        {card.dimensions.length} dimension{card.dimensions.length !== 1 ? "s" : ""} · v{card.version}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Create pricing-cards-page.tsx**

```typescript
// src/features/pricing-cards/components/pricing-cards-page.tsx
import { useState } from "react";
import { Link } from "@tanstack/react-router";
import { Plus, Search } from "lucide-react";
import { PageHeader } from "@/components/shared/page-header";
import { usePricingCards } from "../api/queries";
import { PricingCardItem } from "./pricing-card-item";
import { Skeleton } from "@/components/ui/skeleton";

export function PricingCardsPage() {
  const { data: cards, isLoading } = usePricingCards();
  const [search, setSearch] = useState("");

  const filtered = cards?.filter((c) =>
    c.name.toLowerCase().includes(search.toLowerCase()) ||
    c.provider.toLowerCase().includes(search.toLowerCase()) ||
    c.cardId.toLowerCase().includes(search.toLowerCase()),
  );

  return (
    <div className="space-y-5">
      <PageHeader
        title="Pricing Cards"
        description="Define how API costs are calculated."
        actions={
          <Link
            to="/pricing-cards/new"
            className="flex items-center gap-1.5 rounded-md bg-foreground px-3.5 py-1.5 text-[12.5px] font-medium text-background hover:opacity-90"
          >
            <Plus className="h-3.5 w-3.5" /> Create card
          </Link>
        }
      />

      {/* Search */}
      <div className="relative max-w-xs">
        <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search cards..."
          className="w-full rounded-lg border border-border bg-background py-1.5 pl-8 pr-3 text-[12.5px] outline-none focus:border-muted-foreground"
        />
      </div>

      {/* Cards grid */}
      {isLoading ? (
        <div className="grid grid-cols-3 gap-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-24 rounded-xl" />
          ))}
        </div>
      ) : filtered && filtered.length > 0 ? (
        <div className="grid grid-cols-3 gap-3">
          {filtered.map((card) => (
            <PricingCardItem key={card.id} card={card} />
          ))}
        </div>
      ) : (
        <div className="rounded-lg border border-dashed p-12 text-center text-sm text-muted-foreground">
          {search ? "No cards match your search." : "No pricing cards yet. Create your first card."}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 3: Update pricing cards route**

```typescript
// src/app/routes/_app/pricing-cards/index.tsx
import { createFileRoute } from "@tanstack/react-router";
import { PricingCardsPage } from "@/features/pricing-cards/components/pricing-cards-page";

export const Route = createFileRoute("/_app/pricing-cards/")({
  component: PricingCardsPage,
});
```

- [ ] **Step 4: Verify build, test, lint**

Run: `pnpm build && pnpm test && pnpm lint`
Expected: All pass.

---

## Task 9: Final Verification + PROGRESS.md

- [ ] **Step 1: Run full verification suite**

```bash
pnpm test
pnpm lint
pnpm build
```

All must pass.

- [ ] **Step 2: Manual verification in browser**

Navigate to:
- `/pricing-cards` — shows 3 mock cards (Gemini, GPT-4o, Serper) with search
- `/pricing-cards/new` — 4-step wizard:
  - Step 1: Source selection (template/custom + template picker)
  - Step 2: Card details with live preview
  - Step 3: Dimension config with cost tester
  - Step 4: Review with dry-run, product assignment, snippet, activation
- "Create card" button on list page links to wizard
- Activation creates card and shows success view

- [ ] **Step 3: Update PROGRESS.md**

Mark Phase 2 complete. Update current status to Phase 3.

```markdown
## Phase 2: Pricing Card Wizard (Complete)

- [x] Pricing cards list page with search
- [x] 4-step creation wizard (source, details, dimensions, review)
- [x] Template selection + custom creation
- [x] Live card preview
- [x] Dimension configuration with cost tester
- [x] Dry-run simulator with breakdown + distribution bar
- [x] Product assignment + SDK snippet
- [x] Activation flow with confirmation
- [x] Feature API layer (types, mock, api, queries, provider)
- [x] Pure calculation functions with tests
- [x] Slugify utility with tests
- [x] Zod schema validation
```
