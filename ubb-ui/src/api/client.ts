import createClient, { type Middleware } from "openapi-fetch";

let _getToken: (() => Promise<string | null>) | null = null;

/**
 * Register the auth token getter (called once from InnerApp after Clerk
 * initializes). The getter is invoked on every outgoing API request so
 * the Authorization header always carries a fresh JWT.
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

function createApiClient(basePath: string) {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const client = createClient<any>({
    baseUrl: `${import.meta.env.VITE_API_URL || ""}${basePath}`,
  });
  client.use(authMiddleware);
  return client;
}

// Untyped until codegen runs. After running `pnpm api:generate`, replace
// `any` above with the generated paths types for full type safety.
export const platformApi = createApiClient("/api/v1/platform");
export const meteringApi = createApiClient("/api/v1/metering");
export const billingApi = createApiClient("/api/v1/billing");
export const tenantApi = createApiClient("/api/v1/tenant");
