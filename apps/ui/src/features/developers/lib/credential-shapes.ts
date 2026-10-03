// What a credential looks like, said once for the Developers feature: the
// Code Builder's URL refuses any value of this shape (#579), and the feature's
// sweep for key-shaped literals reads the same patterns.

/**
 * The scheme a UBB API key is minted under, and how much of a key the API
 * hands back for display.
 *
 * A key is `ubb_live_` or `ubb_test_` followed by 43 characters; the API's
 * `key_prefix` is the first 16 characters of it (`tenants/models.py`), so a
 * display prefix carries at most 7 characters after the scheme. Anything
 * longer is a key, or a placeholder standing in for one — which is the shape a
 * developer pastes a real key into.
 */
export const DISPLAY_PREFIX_TAIL = 7;

const KEY_SHAPED = new RegExp(
  `ubb_(?:live|test)_[A-Za-z0-9_\\-]{${DISPLAY_PREFIX_TAIL + 1},}`,
);

/** A signed session token: three base64url segments, the first a JSON header. */
const TOKEN_SHAPED = /eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]*/;

/**
 * An authorization header carrying a value rather than a variable's name —
 * the header, not the word: prose may say "bearer credentials".
 */
const BEARER_VALUE = /Authorization:\s*Bearer\s+(?!\$)[^\s"'`]/;

/** The shapes, named, so a failing sweep can say which one it found. */
export const CREDENTIAL_SHAPES: Readonly<Record<string, RegExp>> = {
  "an API key or a placeholder for one": KEY_SHAPED,
  "a signed session token": TOKEN_SHAPED,
  "an authorization header holding a value": BEARER_VALUE,
};

/** The first credential shape `text` contains, or null. */
export function credentialShapeIn(text: string): string | null {
  for (const [name, shape] of Object.entries(CREDENTIAL_SHAPES)) {
    if (shape.test(text)) return name;
  }
  return null;
}
