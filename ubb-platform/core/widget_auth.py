import time
import uuid
import logging

import jwt

logger = logging.getLogger(__name__)


def create_widget_token(secret, customer_id, tenant_id, expires_in=900):
    """Create a signed JWT for widget authentication."""
    payload = {
        "sub": customer_id,
        "tid": tenant_id,
        "iss": "ubb",
        "exp": int(time.time()) + expires_in,
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def verify_widget_token(token):
    """
    Verify a widget JWT via two-step decode:
    1. Decode without verification to extract tid
    2. Validate tid is a UUID (prevents arbitrary DB queries)
    3. Look up tenant to get the real secret
    4. Verify signature with tenant's secret

    Returns decoded payload dict or None if invalid/expired.
    """
    try:
        # Step 1: decode unverified to get tenant_id
        unverified = jwt.decode(token, options={"verify_signature": False})
        tenant_id = unverified.get("tid")
        if not tenant_id:
            return None

        # Step 2: validate UUID format before any DB query
        try:
            uuid.UUID(str(tenant_id))
        except (ValueError, AttributeError):
            return None

        # Step 3: look up tenant
        from apps.tenants.models import Tenant
        try:
            tenant = Tenant.objects.get(id=tenant_id, is_active=True)
        except Tenant.DoesNotExist:
            return None

        # Step 4: verify with real secret
        return jwt.decode(token, tenant.widget_secret, algorithms=["HS256"], issuer="ubb")

    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None
