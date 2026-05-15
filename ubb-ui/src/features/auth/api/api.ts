import { platformApi } from "@/api/client";
import type { Me } from "./types";

export async function getMe(): Promise<Me> {
  const { data, error } = await platformApi.GET("/me", {});
  if (error) throw new Error("Failed to load user");
  return data as Me;
}
