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

export const platformApi = createApiClient<NamespacePaths<"/api/v1/platform">>("/api/v1/platform");
export const meteringApi = createApiClient<NamespacePaths<"/api/v1/metering">>("/api/v1/metering");
export const billingApi = createApiClient<NamespacePaths<"/api/v1/billing">>("/api/v1/billing");
export const tenantApi = createApiClient<NamespacePaths<"/api/v1/tenant">>("/api/v1/tenant");
export const meApi = createApiClient<NamespacePaths<"/api/v1/me">>("/api/v1/me");
