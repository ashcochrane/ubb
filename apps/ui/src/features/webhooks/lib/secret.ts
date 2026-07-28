// Webhook signing secrets are CALLER-SUPPLIED and write-only: the API never
// returns them on any response, and there is no reveal. The console can only
// ever show a secret the user just typed or generated in this session
// (a client-side echo), so generation happens here, in the browser.

/** Generate a 48-hex-char signing secret (24 random bytes) client-side. */
export function generateWebhookSecret(): string {
  const bytes = new Uint8Array(24);
  crypto.getRandomValues(bytes);
  return Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
}

/** "https://api.acme.dev/webhooks/ubb" → "api.acme.dev" (raw value if unparseable). */
export function hostOf(url: string): string {
  try {
    return new URL(url).host;
  } catch {
    return url;
  }
}
