import { meteringApi, platformApi } from "@/api/client";
import type { CardListResponse, CreateCardRequest, PricingCard } from "./types";
import type { MeteringSchemas } from "@/api/types";

export type UpdateCardRequest = MeteringSchemas["UpdateCardRequest"];
export type DimensionIn = MeteringSchemas["DimensionIn"];

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

export async function updateCard(
  cardId: string,
  req: UpdateCardRequest,
): Promise<PricingCard> {
  const { data, error } = await meteringApi.PATCH(
    "/pricing/cards/{card_id}",
    {
      params: { path: { card_id: cardId } },
      body: req,
    },
  );
  if (error || !data) throw error ?? new Error("Failed to update card");
  return data as PricingCard;
}

export async function deleteCard(cardId: string): Promise<void> {
  const { error } = await meteringApi.DELETE("/pricing/cards/{card_id}", {
    params: { path: { card_id: cardId } },
  });
  if (error) throw error;
}

export async function createRate(
  cardId: string,
  body: DimensionIn,
): Promise<void> {
  const { error } = await meteringApi.POST("/pricing/cards/{card_id}/rates", {
    params: { path: { card_id: cardId } },
    body,
  });
  if (error) throw error;
}

export async function updateRate(
  cardId: string,
  rateId: string,
  body: DimensionIn,
): Promise<void> {
  const { error } = await meteringApi.PUT(
    "/pricing/cards/{card_id}/rates/{rate_id}",
    {
      params: { path: { card_id: cardId, rate_id: rateId } },
      body,
    },
  );
  if (error) throw error;
}

export async function deleteRate(
  cardId: string,
  rateId: string,
): Promise<void> {
  const { error } = await meteringApi.DELETE(
    "/pricing/cards/{card_id}/rates/{rate_id}",
    { params: { path: { card_id: cardId, rate_id: rateId } } },
  );
  if (error) throw error;
}
