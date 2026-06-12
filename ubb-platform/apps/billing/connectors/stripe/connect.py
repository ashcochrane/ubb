import secrets
from datetime import timedelta
from urllib.parse import urlencode

import stripe
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.billing.stripe.services.stripe_service import api_key_for_tenant
from core.exceptions import StripeFatalError

STATE_TTL = timedelta(minutes=15)


class ConnectError(Exception):
    pass


def _client_id_for_tenant(tenant):
    """The Connect OAuth client id for the tenant's mode (F4.4).

    A sandbox tenant onboards in Stripe TEST mode, which uses a distinct
    client id (STRIPE_CONNECT_TEST_CLIENT_ID) — never the live one.
    """
    if tenant.is_sandbox:
        if not settings.STRIPE_CONNECT_TEST_CLIENT_ID:
            raise ConnectError(
                "Stripe Connect test mode is not configured "
                "(STRIPE_CONNECT_TEST_CLIENT_ID unset)"
            )
        return settings.STRIPE_CONNECT_TEST_CLIENT_ID
    if not settings.STRIPE_CONNECT_CLIENT_ID:
        raise ConnectError("Stripe Connect is not configured (STRIPE_CONNECT_CLIENT_ID unset)")
    return settings.STRIPE_CONNECT_CLIENT_ID


def _api_key_for_tenant_or_connect_error(tenant):
    """api_key_for_tenant, mapped onto ConnectError for the OAuth flow."""
    try:
        return api_key_for_tenant(tenant)
    except StripeFatalError as e:
        raise ConnectError(str(e)) from e


def build_authorize_url(tenant, *, return_url=""):
    from apps.platform.tenants.models import ConnectOAuthState
    client_id = _client_id_for_tenant(tenant)
    state = secrets.token_urlsafe(32)
    ConnectOAuthState.objects.create(
        tenant=tenant, state=state, return_url=return_url,
        expires_at=timezone.now() + STATE_TTL)
    q = urlencode({"response_type": "code", "client_id": client_id,
                   "scope": "read_write", "state": state})
    return f"https://connect.stripe.com/oauth/authorize?{q}"


def complete_oauth(*, code, state):
    from apps.platform.tenants.models import ConnectOAuthState
    with transaction.atomic():
        st = (ConnectOAuthState.objects.select_for_update()
              .filter(state=state, used=False, expires_at__gt=timezone.now()).first())
        if st is None:
            raise ConnectError("invalid or expired state")
        tenant = st.tenant
        # F4.4: the token exchange + account fetch run in the tenant's Stripe
        # mode — a sandbox tenant completes a TEST-mode connection (sk_test_),
        # a live tenant a live one. The acct_ id is the same in both modes;
        # the tenant row keeps them apart.
        api_key = _api_key_for_tenant_or_connect_error(tenant)
        resp = stripe.OAuth.token(grant_type="authorization_code", code=code,
                                  api_key=api_key)
        acct_id = resp.stripe_user_id
        tenant.stripe_connected_account_id = acct_id
        try:
            acct = stripe.Account.retrieve(acct_id, api_key=api_key)
            tenant.charges_enabled = bool(getattr(acct, "charges_enabled", False))
        except Exception:
            tenant.charges_enabled = False
        tenant.save(update_fields=["stripe_connected_account_id", "charges_enabled", "updated_at"])
        st.used = True
        st.save(update_fields=["used", "updated_at"])
    return tenant
