/**
 * The API origin this console talks to (env override or same origin).
 *
 * The console's own address for the API it calls — which is what a link into
 * the API's reference, or a command the developer runs against this
 * workspace's sandbox, needs. It is never written into generated code: where
 * the API is, is the integration's environment to say (ADR-0016 §8).
 */
export function apiOrigin(): string {
  return import.meta.env.VITE_API_URL || window.location.origin;
}
