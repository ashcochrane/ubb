import type { PricingCard, CreateCardRequest, Template } from "./types";
import type { GroupSummary } from "./api";
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
