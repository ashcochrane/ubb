import type { PricingCard, Template, CreateCardRequest } from "./types";
import { meteringApi } from "@/api/client";

export async function getCards(): Promise<PricingCard[]> {
  const { data } = await meteringApi.GET("/rate-cards", {});
  return data as PricingCard[];
}

export async function getTemplates(): Promise<Template[]> {
  const { data } = await meteringApi.GET("/rate-cards/templates", {});
  return data as Template[];
}

export async function getProducts(): Promise<string[]> {
  const { data } = await meteringApi.GET("/products", {});
  return data as string[];
}

export async function createCard(req: CreateCardRequest): Promise<PricingCard> {
  const { data } = await meteringApi.POST("/rate-cards", { body: req });
  return data as PricingCard;
}
