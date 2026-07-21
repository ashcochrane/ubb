"""Clerk server-side token verification (identity build 1, #79).

The second tenant-principal scheme (beside the tenant API key): a Clerk session
JWT presented as a bearer token. Verification is entirely server-side and
offline — we check the token's signature and standard claims ourselves and never
call Clerk at request time.

Two verification modes, chosen by config and mutually exclusive by algorithm so
there is no algorithm-confusion surface:

  * **Production — RS256** against Clerk's JWKS. Set ``CLERK_ISSUER`` and one
    RS256 key source: ``CLERK_JWT_PUBLIC_KEY`` (a PEM pinned in config) or
    ``CLERK_JWKS_URL`` (fetched and cached). RS256 needs the ``cryptography``
    package — imported lazily so this module loads without it, and a clear
    ``RuntimeError`` surfaces if it is configured but missing.
  * **Local / dev / test — HS256** against ``CLERK_HS256_SECRET``. Real Clerk
    tokens are never HS256, so this mode can never accept a live Clerk token; it
    exists only so the suite and local dev can mint principals without a JWKS
    round-trip. It is ignored the moment an RS256 key is configured (RS256 wins),
    so a production deployment can never be downgraded to a shared secret.

``verify_member_token`` returns the decoded claims (a dict) or ``None``; it never
raises — a malformed, expired, or forged token is simply an unauthenticated
request, not a 500. When no Clerk config is present member auth is OFF (every
token returns ``None``), so a deployment that has not wired Clerk keeps
API-key-only auth with zero behaviour change.
"""
import logging

import jwt
from django.conf import settings

logger = logging.getLogger("ubb.auth")

# JWKS clients are keyed by URL and reused — each caches its signing keys.
_jwks_clients = {}


def _mode_and_key(token):
    """Resolve (key, algorithms) for the current config, or (None, None) when
    member auth is unconfigured. RS256 sources win over the HS256 secret."""
    public_key = getattr(settings, "CLERK_JWT_PUBLIC_KEY", "") or ""
    jwks_url = getattr(settings, "CLERK_JWKS_URL", "") or ""
    hs256_secret = getattr(settings, "CLERK_HS256_SECRET", "") or ""

    if public_key:
        return public_key, ["RS256"]
    if jwks_url:
        return _jwks_signing_key(jwks_url, token), ["RS256"]
    if hs256_secret:
        return hs256_secret, ["HS256"]
    return None, None


def _jwks_signing_key(jwks_url, token):
    """The RS256 signing key for ``token`` from Clerk's JWKS (cached per URL).

    Lazy: PyJWK's RS256 verification pulls in ``cryptography``. A misconfigured
    deployment (JWKS set but crypto missing / JWKS unreachable) surfaces the
    error here, where the caller turns it into a clean ``None`` (401)."""
    client = _jwks_clients.get(jwks_url)
    if client is None:
        client = jwt.PyJWKClient(jwks_url)
        _jwks_clients[jwks_url] = client
    return client.get_signing_key_from_jwt(token).key


def verify_member_token(token):
    """Verify a Clerk session JWT and return its claims, or ``None``.

    Never raises: any verification failure (bad signature, expired, wrong
    issuer, unconfigured, or an RS256 backend problem) is an unauthenticated
    request."""
    if not token:
        return None
    try:
        key, algorithms = _mode_and_key(token)
    except Exception:
        # JWKS fetch / crypto-backend problems: fail closed, but loudly in logs
        # (this is a deployment misconfiguration, not a bad caller token).
        logger.warning("clerk.verification_key_unavailable", exc_info=True)
        return None
    if key is None:
        return None

    issuer = getattr(settings, "CLERK_ISSUER", "") or None
    options = {"require": ["exp"], "verify_aud": False}
    try:
        return jwt.decode(
            token, key, algorithms=algorithms, issuer=issuer, options=options
        )
    except jwt.InvalidTokenError:
        return None
