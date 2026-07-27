import createClient, { type Middleware } from "openapi-fetch";

import type { paths as ApiPaths } from "./generated/api";

type NamespacePaths<Prefix extends string> = {
  [Path in keyof ApiPaths as Path extends `${Prefix}${infer RelativePath}`
    ? RelativePath extends ""
      ? "/"
      : RelativePath
    : never]: ApiPaths[Path];
};

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

// eslint-disable-next-line @typescript-eslint/no-empty-object-type
function createApiClient<Paths extends {}>(basePath: string) {
  const client = createClient<Paths>({
    baseUrl: `${import.meta.env.VITE_API_URL || ""}${basePath}`,
  });
  client.use(authMiddleware);
  return client;
}

// One typed client per backend namespace. The tenant console authenticates all
// of them with the same bearer scheme (Clerk member JWT or a tenant API key).
// The /api/v1/me/** surface is deliberately absent: it is the END-CUSTOMER
// widget portal (WidgetJWTAuth) and must not be called from the console.
export const platformApi = createApiClient<NamespacePaths<"/api/v1/platform">>("/api/v1/platform");
export const meteringApi = createApiClient<NamespacePaths<"/api/v1/metering">>("/api/v1/metering");
export const billingApi = createApiClient<NamespacePaths<"/api/v1/billing">>("/api/v1/billing");
export const tenantApi = createApiClient<NamespacePaths<"/api/v1/tenant">>("/api/v1/tenant");
export const marginApi = createApiClient<NamespacePaths<"/api/v1/margin">>("/api/v1/margin");
export const webhooksApi = createApiClient<NamespacePaths<"/api/v1/webhooks">>("/api/v1/webhooks");
export const referralsApi = createApiClient<NamespacePaths<"/api/v1/referrals">>("/api/v1/referrals");
export const subscriptionsApi =
  createApiClient<NamespacePaths<"/api/v1/subscriptions">>("/api/v1/subscriptions");
export const connectApi = createApiClient<NamespacePaths<"/api/v1/connect">>("/api/v1/connect");

// Root client for the handful of endpoints that live directly under /api/v1:
// /audit/records, /customers/{id}/past-limit-report, /sandbox/reset, /health, /ready.
export const rootApi = createApiClient<NamespacePaths<"/api/v1">>("/api/v1");
