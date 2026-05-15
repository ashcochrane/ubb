"""Thin client for Clerk Backend API.

Used during tenant provisioning to fetch the canonical email for a
Clerk user. Email is never accepted from client request bodies — this
is the security boundary.
"""
import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

CLERK_API_BASE = "https://api.clerk.com/v1"
TIMEOUT_SECONDS = 5


class ClerkAPIError(Exception):
    """Raised on any failure talking to the Clerk Backend API."""


def get_clerk_user(user_id: str) -> dict:
    """Fetch canonical user data from the Clerk Backend API.

    Returns: {"clerk_user_id": str, "email": str}
    Raises: ClerkAPIError on missing secret, non-2xx, timeout, or no primary email.
    """
    if not settings.CLERK_SECRET_KEY:
        raise ClerkAPIError("CLERK_SECRET_KEY not configured")

    url = f"{CLERK_API_BASE}/users/{user_id}"
    headers = {"Authorization": f"Bearer {settings.CLERK_SECRET_KEY}"}

    try:
        response = requests.get(url, headers=headers, timeout=TIMEOUT_SECONDS)
        response.raise_for_status()
    except (requests.RequestException, requests.Timeout) as exc:
        logger.warning("Clerk API request failed: %s", exc)
        raise ClerkAPIError(f"Clerk API request failed: {exc}") from exc

    data = response.json()
    primary_id = data.get("primary_email_address_id")
    email = None
    for addr in data.get("email_addresses", []):
        if addr.get("id") == primary_id:
            email = addr.get("email_address")
            break

    if not email:
        raise ClerkAPIError(f"Clerk user {user_id} has no primary email")

    return {"clerk_user_id": user_id, "email": email}
