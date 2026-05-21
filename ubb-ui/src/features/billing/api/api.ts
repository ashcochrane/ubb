// src/features/billing/api/api.ts
import { platformApi } from "@/api/client";
import type { DefaultMargin, UpdateDefaultMarginRequest } from "./types";

export async function getDefaultMargin(): Promise<DefaultMargin> {
  const { data, error } = await platformApi.GET("/tenant/default-margin", {});
  if (error || !data) throw error ?? new Error("Failed to load default margin");
  return data;
}

export async function updateDefaultMargin(
  req: UpdateDefaultMarginRequest,
): Promise<DefaultMargin> {
  const { data, error } = await platformApi.PATCH("/tenant/default-margin", {
    body: req,
  });
  if (error || !data) throw error ?? new Error("Failed to update default margin");
  return data;
}
