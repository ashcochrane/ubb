"""Clerk JWT authentication for tenant dashboard users."""

import logging
import time

import jwt
import requests
from django.conf import settings
from ninja.security import HttpBearer

from apps.platform.tenants.models import TenantUser

logger = logging.getLogger(__name__)

_jwks_cache = {"keys": None, "fetched_at": 0}
JWKS_CACHE_TTL = 3600


def _get_jwks():
    """Fetch Clerk's JWKS keys, with caching."""
    now = time.time()
    if _jwks_cache["keys"] and (now - _jwks_cache["fetched_at"]) < JWKS_CACHE_TTL:
        return _jwks_cache["keys"]

    clerk_issuer = settings.CLERK_ISSUER_URL
    jwks_url = f"{clerk_issuer}/.well-known/jwks.json"
    try:
        resp = requests.get(jwks_url, timeout=5)
        resp.raise_for_status()
        keys = resp.json()["keys"]
        _jwks_cache["keys"] = keys
        _jwks_cache["fetched_at"] = now
        return keys
    except Exception:
        logger.exception("Failed to fetch Clerk JWKS")
        return _jwks_cache["keys"]


def verify_clerk_token(token: str) -> dict | None:
    """Verify a Clerk JWT and return its claims, or None if invalid."""
    jwks = _get_jwks()
    if not jwks:
        return None

    try:
        unverified_header = jwt.get_unverified_header(token)
        kid = unverified_header.get("kid")
        if not kid:
            return None

        matching_key = None
        for key in jwks:
            if key.get("kid") == kid:
                matching_key = key
                break
        if not matching_key:
            return None

        public_key = jwt.algorithms.RSAAlgorithm.from_jwk(matching_key)
        claims = jwt.decode(
            token,
            public_key,
            algorithms=["RS256"],
            issuer=settings.CLERK_ISSUER_URL,
            options={"require": ["sub", "iss", "exp"]},
        )
        return claims
    except jwt.PyJWTError:
        logger.debug("Clerk JWT verification failed", exc_info=True)
        return None


class ClerkJWTAuth(HttpBearer):
    """Authenticate dashboard users via Clerk JWT.

    Sets request.tenant and request.tenant_user, matching the shape
    that existing endpoints expect from ApiKeyAuth.
    """

    def authenticate(self, request, token: str):
        claims = verify_clerk_token(token)
        if claims is None:
            return None

        clerk_user_id = claims.get("sub")
        if not clerk_user_id:
            return None

        try:
            tenant_user = TenantUser.objects.select_related("tenant").get(
                clerk_user_id=clerk_user_id
            )
        except TenantUser.DoesNotExist:
            return None

        request.tenant = tenant_user.tenant
        request.tenant_user = tenant_user
        return tenant_user
