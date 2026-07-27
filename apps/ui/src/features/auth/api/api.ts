import { tenantApi } from "@/api/client";
import { requireData } from "@/api/errors";
import type { Me } from "./types";

/** Load the current tenant's configuration — the app's identity/context source. */
export async function getMe(): Promise<Me> {
  const tenant = await tenantApi
    .GET("/config", {})
    .then((r) => requireData(r, "Failed to load tenant"));
  return { tenant };
}
