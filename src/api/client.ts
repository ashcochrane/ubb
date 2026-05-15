import createClient, { type Middleware } from "openapi-fetch";

import type { paths as BillingPaths } from "./generated/billing";
import type { paths as MeteringPaths } from "./generated/metering";
import type { paths as MePaths } from "./generated/me";
import type { paths as PlatformPaths } from "./generated/platform";
import type { paths as TenantPaths } from "./generated/tenant";

let _getToken: (() => Promise<string | null>) | null = null;

/**
 * Register the auth token getter. Called once after Clerk initialises.
 * The getter is invoked on every outgoing request so the Authorization
 * header always carries a fresh JWT.
 */
export function setAuthTokenGetter(fn: () => Promise<string | null>) {
  _getToken = fn;
}

const authMiddleware: Middleware = {
  async onRequest({ request }) {
    if (_getToken) {
      const token = await _getToken();
      if (token) {
        request.headers.set("Authorization", `Bearer ${token}`);
      }
    }
    return request;
  },
};

function createApiClient<Paths extends {}>(basePath: string) {
  const client = createClient<Paths>({
    baseUrl: `${import.meta.env.VITE_API_URL || ""}${basePath}`,
  });
  client.use(authMiddleware);
  return client;
}

export const platformApi = createApiClient<PlatformPaths>("/api/v1/platform");
export const meteringApi = createApiClient<MeteringPaths>("/api/v1/metering");
export const billingApi = createApiClient<BillingPaths>("/api/v1/billing");
export const tenantApi = createApiClient<TenantPaths>("/api/v1/tenant");
export const meApi = createApiClient<MePaths>("/api/v1/me");
