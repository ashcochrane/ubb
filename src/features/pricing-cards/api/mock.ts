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
