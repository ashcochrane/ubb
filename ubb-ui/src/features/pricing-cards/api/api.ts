import { meteringApi, platformApi } from "@/api/client";
import type { CardListResponse, CreateCardRequest, PricingCard } from "./types";

export async function getCards(): Promise<PricingCard[]> {
  const { data } = await meteringApi.GET("/pricing/cards", {});
  if (!data) return [];
  return (data as CardListResponse).data;
}

export async function getCard(cardId: string): Promise<PricingCard | null> {
  const { data } = await meteringApi.GET("/pricing/cards/{card_id}", {
    params: { path: { card_id: cardId } },
  });
  return (data as PricingCard) ?? null;
}

export async function createCard(req: CreateCardRequest): Promise<PricingCard> {
  const { data } = await meteringApi.POST("/pricing/cards", { body: req });
  return data as PricingCard;
}

// Groups are served by the platform API, not the metering API.
export interface GroupSummary {
  id: string;
  name: string;
  slug: string;
  marginPct: number | null;
}

export async function getGroups(): Promise<GroupSummary[]> {
  const { data } = await platformApi.GET("/groups", {});
  if (!data) return [];
  return (data as { data: GroupSummary[] }).data;
}

// Templates are shipped as a static bundle in the UI (no backend endpoint).
// See features/pricing-cards/api/mock-data.ts::mockTemplates.
