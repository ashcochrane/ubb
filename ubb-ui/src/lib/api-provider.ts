const VALID_PROVIDERS = ["mock", "api"] as const;

export type ApiProvider = (typeof VALID_PROVIDERS)[number];

function getApiProvider(): ApiProvider {
  const value = import.meta.env.VITE_API_PROVIDER;
  if (!value || !VALID_PROVIDERS.includes(value as ApiProvider)) {
    return "mock";
  }
  return value as ApiProvider;
}

/** Current API provider — set via VITE_API_PROVIDER env var. Defaults to "mock". */
export const API_PROVIDER = getApiProvider();

/** Select the active implementation from a record of providers. */
export function selectProvider<T>(providers: Record<ApiProvider, T>): T {
  return providers[API_PROVIDER];
}

/** Simulated network delay for mock API providers. */
export function mockDelay(ms = 300): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
