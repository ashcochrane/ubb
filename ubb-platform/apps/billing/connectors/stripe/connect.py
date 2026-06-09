import secrets
from datetime import timedelta
from urllib.parse import urlencode

import stripe
from django.conf import settings
from django.db import transaction
from django.utils import timezone

STATE_TTL = timedelta(minutes=15)


class ConnectError(Exception):
    pass


def build_authorize_url(tenant, *, return_url=""):
    from apps.platform.tenants.models import ConnectOAuthState
    if not settings.STRIPE_CONNECT_CLIENT_ID:
        raise ConnectError("Stripe Connect is not configured (STRIPE_CONNECT_CLIENT_ID unset)")
    state = secrets.token_urlsafe(32)
    ConnectOAuthState.objects.create(
        tenant=tenant, state=state, return_url=return_url,
        expires_at=timezone.now() + STATE_TTL)
    q = urlencode({"response_type": "code", "client_id": settings.STRIPE_CONNECT_CLIENT_ID,
                   "scope": "read_write", "state": state})
    return f"https://connect.stripe.com/oauth/authorize?{q}"


def complete_oauth(*, code, state):
    from apps.platform.tenants.models import ConnectOAuthState
    with transaction.atomic():
        st = (ConnectOAuthState.objects.select_for_update()
              .filter(state=state, used=False, expires_at__gt=timezone.now()).first())
        if st is None:
            raise ConnectError("invalid or expired state")
        resp = stripe.OAuth.token(grant_type="authorization_code", code=code)
        acct_id = resp.stripe_user_id
        tenant = st.tenant
        tenant.stripe_connected_account_id = acct_id
        try:
            acct = stripe.Account.retrieve(acct_id)
            tenant.charges_enabled = bool(getattr(acct, "charges_enabled", False))
        except Exception:
            tenant.charges_enabled = False
        tenant.save(update_fields=["stripe_connected_account_id", "charges_enabled", "updated_at"])
        st.used = True
        st.save(update_fields=["used", "updated_at"])
    return tenant
