import type { PricingCard, CreateCardRequest, Template, PricingType, CardStatus } from "./types";
import type { GroupSummary, DimensionIn, UpdateCardRequest } from "./api";
import { mockPricingCards, mockTemplates, mockGroups } from "./mock-data";
import { mockDelay } from "@/lib/api-provider";

let cards: PricingCard[] = [...mockPricingCards];

export async function getCards(): Promise<PricingCard[]> {
  await mockDelay();
  return [...cards];
}

export async function getCard(cardId: string): Promise<PricingCard | null> {
  await mockDelay();
  return cards.find((c) => c.id === cardId) ?? null;
}

export async function createCard(req: CreateCardRequest): Promise<PricingCard> {
  await mockDelay(500);
  const now = new Date().toISOString();
  const card: PricingCard = {
    id: `pc-${Date.now()}`,
    slug: req.slug,
    name: req.name,
    provider: req.provider,
    description: req.description,
    pricingSourceUrl: req.pricingSourceUrl,
    groupId: req.groupId,
    groupName: req.groupId
      ? mockGroups.find((g) => g.id === req.groupId)?.name ?? null
      : null,
    status: req.status,
    dimensions: req.dimensions.map((d, i) => ({
      ...d,
      id: `dim-${Date.now()}-${i}`,
      validFrom: now,
      validTo: null,
    })),
    createdAt: now,
    updatedAt: now,
  };
  cards = [card, ...cards];
  return card;
}

export async function getGroups(): Promise<GroupSummary[]> {
  await mockDelay(100);
  return [...mockGroups];
}

// UI-only templates. Not a backend endpoint, but exposed via the same provider for symmetry.
export async function getTemplates(): Promise<Template[]> {
  await mockDelay(200);
  return [...mockTemplates];
}

export async function updateCard(
  cardId: string,
  req: UpdateCardRequest,
): Promise<PricingCard> {
  await mockDelay();
  const idx = cards.findIndex((c) => c.id === cardId);
  if (idx < 0) throw new Error("not found");
  // eslint-disable-next-line @typescript-eslint/no-non-null-assertion
  const existing = cards[idx]!;
  const next: PricingCard = {
    ...existing,
    name: req.name != null ? req.name : existing.name,
    description: req.description != null ? req.description : existing.description,
    groupId: req.groupId !== undefined ? req.groupId : existing.groupId,
    pricingSourceUrl:
      req.pricingSourceUrl != null
        ? req.pricingSourceUrl
        : existing.pricingSourceUrl,
    status: req.status != null ? (req.status as CardStatus) : existing.status,
  };
  cards[idx] = next;
  return next;
}

export async function deleteCard(cardId: string): Promise<void> {
  await mockDelay();
  const idx = cards.findIndex((c) => c.id === cardId);
  if (idx >= 0) cards.splice(idx, 1);
}

export async function createRate(
  cardId: string,
  body: DimensionIn,
): Promise<void> {
  await mockDelay();
  const card = cards.find((c) => c.id === cardId);
  if (!card) throw new Error("not found");
  card.dimensions = [
    ...card.dimensions,
    {
      id: `rate_${Math.random().toString(36).slice(2, 8)}`,
      validFrom: new Date().toISOString(),
      validTo: null,
      metricName: body.metricName,
      pricingType: body.pricingType as PricingType,
      costPerUnitMicros: body.costPerUnitMicros,
      providerCostPerUnitMicros: body.providerCostPerUnitMicros ?? null,
      unitQuantity: body.unitQuantity,
      currency: body.currency,
      label: body.label,
      unit: body.unit,
    },
  ];
}

export async function updateRate(
  cardId: string,
  rateId: string,
  body: DimensionIn,
): Promise<void> {
  await mockDelay();
  const card = cards.find((c) => c.id === cardId);
  if (!card) throw new Error("not found");
  card.dimensions = card.dimensions.map((d) =>
    d.id === rateId
      ? {
          ...d,
          metricName: body.metricName,
          pricingType: body.pricingType as PricingType,
          costPerUnitMicros: body.costPerUnitMicros,
          providerCostPerUnitMicros: body.providerCostPerUnitMicros ?? null,
          unitQuantity: body.unitQuantity,
          currency: body.currency,
          label: body.label,
          unit: body.unit,
        }
      : d,
  );
}

export async function deleteRate(
  cardId: string,
  rateId: string,
): Promise<void> {
  await mockDelay();
  const card = cards.find((c) => c.id === cardId);
  if (!card) throw new Error("not found");
  card.dimensions = card.dimensions.filter((d) => d.id !== rateId);
}
